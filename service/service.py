import serial
import serial.tools.list_ports
import pyautogui
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import pystray
import pyperclip
from PIL import Image, ImageDraw
import sys
import os
import subprocess
import ctypes
import json
from ctypes import wintypes

# --- GLOBAL STATE ---
arduino = None
running = False
serial_thread = None
current_port = "COM3"
current_baud = 9600
service_state = "stopped"  # stopped | starting | active
tray_icon = None

TIME_SEND_INTERVAL = 1  # Seconds between TIME: lines; the Arduino counts the PC as gone after 5 without one

NO_PORTS_FOUND = "No ports found"


def get_settings_path():
    if getattr(sys, "frozen", False):
        app_directory = os.path.dirname(sys.executable)
    else:
        app_directory = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_directory, "user.dat")


def apply_settings(settings):
    """Takes the port and baud rate from a settings dictionary, when they're valid."""
    global current_port, current_baud

    # "porta" is the key older versions saved the port under.
    saved_port = settings.get("port", settings.get("porta"))
    saved_baud = settings.get("baud")

    if isinstance(saved_port, str) and saved_port:
        current_port = saved_port
    if isinstance(saved_baud, int) and saved_baud > 0:
        current_baud = saved_baud


def load_settings():
    settings_path = get_settings_path()
    if not os.path.exists(settings_path):
        # Falls back to user.dat.example, if there is one
        example_path = settings_path + ".example"
        if os.path.exists(example_path):
            try:
                with open(example_path, "r", encoding="utf-8") as file:
                    apply_settings(json.load(file))
            except (OSError, ValueError, TypeError, AttributeError) as error:
                print(f"Couldn't load the example settings: {error}")
        return

    try:
        with open(settings_path, "r", encoding="utf-8") as file:
            apply_settings(json.load(file))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f"Couldn't load the settings: {error}")


def save_settings():
    settings = {
        "port": current_port,
        "baud": current_baud
    }

    with open(get_settings_path(), "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)


# Each LED's on/off state, for the keys that toggle one
pixel_states = {
    0: False,
    1: False,
    2: False
}


# --- TALKING TO THE ARDUINO ---
def send_command(command):
    """Sends one line of the protocol to the Arduino."""
    global arduino
    if arduino and arduino.is_open:
        try:
            arduino.write(f"{command}\n".encode('utf-8'))
            arduino.flush()
        except Exception as e:
            print(f"Sending failed: {e}")


def set_pixel(pixel_id, r, g, b):
    """Sets the colour of one of the Arduino's LEDs."""
    send_command(f"PIXEL:{pixel_id},{r},{g},{b}")


def type_text(text):
    """Types text as if on the keyboard, following the keyboard layout (AltGr included)."""
    ULONG_PTR = wintypes.WPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_I(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("ii", INPUT_I),
        ]

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12  # Alt

    SendInput = ctypes.windll.user32.SendInput
    SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    SendInput.restype = wintypes.UINT
    VkKeyScanExW = ctypes.windll.user32.VkKeyScanExW
    VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HKL)
    VkKeyScanExW.restype = ctypes.c_short
    LoadKeyboardLayoutW = ctypes.windll.user32.LoadKeyboardLayoutW
    LoadKeyboardLayoutW.argtypes = (wintypes.LPCWSTR, wintypes.UINT)
    LoadKeyboardLayoutW.restype = wintypes.HKL
    GetKeyboardLayout = ctypes.windll.user32.GetKeyboardLayout
    GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    GetKeyboardLayout.restype = wintypes.HKL

    # The Portuguese (Portugal) layout when Windows has it, the active one otherwise.
    KLF_NOTELLSHELL = 0x00000080
    hkl_portuguese = LoadKeyboardLayoutW("00000816", KLF_NOTELLSHELL)
    hkl_active = GetKeyboardLayout(0)
    hkl_used = hkl_portuguese if hkl_portuguese else hkl_active

    def send_input(inp):
        sent = SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent == 0:
            raise ctypes.WinError()

    def press_vk(vk, keyup=False):
        flags = KEYEVENTF_KEYUP if keyup else 0
        inp = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(vk, 0, flags, 0, 0)),
        )
        send_input(inp)

    def press_modifiers(shift, ctrl, alt):
        if shift:
            press_vk(VK_SHIFT, keyup=False)
        if ctrl:
            press_vk(VK_CONTROL, keyup=False)
        if alt:
            press_vk(VK_MENU, keyup=False)

    def release_modifiers(shift, ctrl, alt):
        if alt:
            press_vk(VK_MENU, keyup=True)
        if ctrl:
            press_vk(VK_CONTROL, keyup=True)
        if shift:
            press_vk(VK_SHIFT, keyup=True)

    def press_unicode(character):
        code = ord(character)
        key_down = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)),
        )
        key_up = INPUT(
            type=INPUT_KEYBOARD,
            ii=INPUT_I(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)),
        )
        send_input(key_down)
        send_input(key_up)

    try:
        for character in text:
            vk_pack = VkKeyScanExW(character, hkl_used)
            if vk_pack == -1:
                # Not on the layout: sent as the character itself.
                press_unicode(character)
                continue

            vk = vk_pack & 0xFF
            shift_state = (vk_pack >> 8) & 0xFF
            uses_shift = bool(shift_state & 0x01)
            uses_ctrl = bool(shift_state & 0x02)
            uses_alt = bool(shift_state & 0x04)

            press_modifiers(uses_shift, uses_ctrl, uses_alt)
            press_vk(vk, keyup=False)
            press_vk(vk, keyup=True)
            release_modifiers(uses_shift, uses_ctrl, uses_alt)
            time.sleep(0.005)
    except Exception as e:
        print(f"Keyboard simulation failed ({e}), falling back to pyautogui.write")
        pyautogui.write(text, interval=0.01)


# --- THE SERVICE (WHAT RUNS IN THE BACKGROUND) ---
def update_menu():
    if tray_icon:
        tray_icon.update_menu()


def set_state(new_state):
    global service_state
    service_state = new_state
    update_menu()


def listen_to_arduino():
    global arduino, running, current_port, current_baud, pixel_states

    last_time_sent = 0

    try:
        arduino = serial.Serial(current_port, current_baud, timeout=0.1)
        time.sleep(2)  # The Arduino restarts as the port opens: gives it time to wake up
        running = True
        set_state("active")
        print(f"Connected to the Arduino on {current_port}")
        last_time_sent = time.time() - TIME_SEND_INTERVAL
    except Exception as e:
        print(f"Couldn't connect to {current_port}: {e}")
        running = False
        set_state("stopped")
        return  # Leaves the thread when it can't connect

    while running:
        now = time.time()

        # 1. SEND THE TIME EVERY SECOND
        if now - last_time_sent > TIME_SEND_INTERVAL:
            current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            send_command(f"TIME:{current_time}")
            last_time_sent = now

        # 2. LISTEN TO THE ARDUINO AND RUN THE MACROS
        try:
            if arduino.in_waiting > 0:
                line = arduino.readline().decode('utf-8').strip()

                # TEMP:, HUM: and SYSTEM: lines are left alone here.
                if line.startswith("KEY:"):
                    key = line.split(":")[1]

                    # === KEY 0 ===
                    if key == '0':
                        pyautogui.press('printscreen')
                        send_command("MSG:Print Screen")

                    # === KEY 1 ===
                    elif key == '1':
                        text = pyperclip.paste()
                        if text:
                            type_text(text)
                            send_command("MSG:Typing")
                        else:
                            send_command("MSG:Clipboard empty")

                    # === KEY 2 ===
                    elif key == '2':
                        # Demo: types a preset text
                        type_text("Hello from Arduino MacroPad!")
                        send_command("MSG:Demo text")

                    # === KEY 3 ===
                    elif key == '3':
                        # Demo: lights an LED while it types a text
                        set_pixel(2, 100, 20, 60)
                        type_text("MacroPad Demo 3")
                        send_command("MSG:Demo 3")
                        set_pixel(2, 0, 0, 0)

                    # === KEY 4 ===
                    elif key == '4':
                        # Demo: opens an app (Notepad, for instance)
                        # Swap it for the program you want
                        try:
                            subprocess.Popen(["notepad.exe"])
                            send_command("MSG:Notepad")
                        except Exception as e:
                            print(f"Couldn't open the app: {e}")
                            send_command("MSG:App error")

                    # === KEY 5 ===
                    elif key == '5':
                        # Demo: types an email address or a template
                        set_pixel(2, 100, 20, 60)
                        type_text("demo.user@example.com")
                        send_command("MSG:Demo email")
                        set_pixel(2, 0, 0, 0)

                    # === KEY 6 ===
                    elif key == '6':
                        # Demo: a state on an LED, as a switch (Spotify / media play-pause, for instance)
                        pixel_states[1] = not pixel_states[1]
                        if pixel_states[1]:
                            set_pixel(1, 0, 255, 0)  # GREEN ON
                            send_command("MSG:Spotify")
                            # pyautogui.press('playpause') # Optional media key
                        else:
                            set_pixel(1, 0, 0, 0)  # OFF
                            send_command("MSG:Spotify OFF")

                    # === KEY 7 ===
                    elif key == '7':
                        # Demo: a state on an LED, as a switch (Discord mute, for instance)
                        pixel_states[2] = not pixel_states[2]
                        if pixel_states[2]:
                            set_pixel(2, 220, 20, 60)  # CRIMSON ON
                            send_command("MSG:Discord")
                        else:
                            set_pixel(2, 0, 0, 0)  # OFF
                            send_command("MSG:Discord OFF")

                    # === KEY 8 ===
                    elif key == '8':
                        # Demo: mutes or unmutes the PC's sound
                        pyautogui.press('volumemute')
                        send_command("MSG:Audio Mute")

                    # === KEY 9 ===
                    elif key == '9':
                        # Demo: runs a tool (Calculator, for instance)
                        try:
                            subprocess.Popen(["calc.exe"])
                            send_command("MSG:Calculator")
                        except Exception as e:
                            print(f"Couldn't open the program: {e}")
                            send_command("MSG:Calc error")

        except Exception as e:
            print(f"Reading failed: {e}")
            continue

        time.sleep(0.01)  # A short pause so the loop doesn't keep the CPU busy

    # Stopping the service closes the port
    if arduino and arduino.is_open:
        arduino.close()
        print("Port closed.")
    set_state("stopped")


# --- SERVICE CONTROLS ---
def start_service():
    global serial_thread, running
    if running:
        return
    if serial_thread and serial_thread.is_alive():
        return
    running = True
    set_state("starting")
    serial_thread = threading.Thread(target=listen_to_arduino, daemon=True)
    serial_thread.start()


def stop_service():
    global running, serial_thread
    running = False  # Ends the loop in listen_to_arduino
    if serial_thread:
        serial_thread.join(timeout=2)
    serial_thread = None
    set_state("stopped")


# --- SETTINGS WINDOW (Tkinter) ---
def create_window():
    root = tk.Tk()
    root.title("Arduino Macro Settings")
    root.geometry("300x200")

    tk.Label(root, text="COM port:").pack(pady=5)

    available_ports = [port.device for port in serial.tools.list_ports.comports()]
    if not available_ports:
        available_ports = [NO_PORTS_FOUND]

    port_combo = ttk.Combobox(root, values=available_ports)
    port_combo.set(current_port)
    port_combo.pack(pady=5)

    tk.Label(root, text="Baud rate:").pack(pady=5)
    baud_combo = ttk.Combobox(root, values=["4800", "9600", "19200", "115200"])
    baud_combo.set(str(current_baud))
    baud_combo.pack(pady=5)

    def save():
        global current_port, current_baud
        if port_combo.get() != NO_PORTS_FOUND:
            current_port = port_combo.get()
            current_baud = int(baud_combo.get())

            try:
                save_settings()
            except OSError as error:
                messagebox.showerror(
                    "Error",
                    f"The settings couldn't be saved:\n{error}"
                )
                return

            # When it's running, it stops and starts again on the new port
            was_running = running
            if was_running:
                stop_service()
                time.sleep(1)  # Gives the COM port time to close
                start_service()

            messagebox.showinfo("Saved", f"Settings saved.\nPort: {current_port}")
            root.quit()
            root.destroy()

    tk.Button(root, text="Save and apply", command=save).pack(pady=15)
    root.mainloop()


def open_settings(icon, item):
    threading.Thread(target=create_window, daemon=True).start()


# --- SYSTEM TRAY ICON ---
def create_icon_image():
    image = Image.new('RGB', (64, 64), color=(0, 120, 215))
    dc = ImageDraw.Draw(image)
    dc.text((10, 20), "ARD", fill=(255, 255, 255))
    return image


def quit_app(icon, item):
    stop_service()
    icon.stop()


def toggle_service(icon, item):
    if service_state in ("starting", "active"):
        stop_service()
    else:
        start_service()
    update_menu()


# The icon's right-click menu
menu = pystray.Menu(
    pystray.MenuItem("Settings", open_settings),
    pystray.MenuItem(lambda text: "Stop service" if service_state in ("starting", "active") else "Start service", toggle_service),
    pystray.MenuItem("Quit", quit_app)
)

# Starts the app
if __name__ == "__main__":
    load_settings()
    start_service()
    tray_icon = pystray.Icon("ArduinoMacro", create_icon_image(), "Arduino MacroKeys", menu)
    tray_icon.run()
