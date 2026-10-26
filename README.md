# Arduino MacroPad

An interactive, DIY 10-key MacroPad powered by Arduino, featuring an SSD1306 OLED display, WS2812B RGB NeoPixels, a DHT22 temperature/humidity sensor, and a companion Windows background service.

---

## Overview

This project combines an Arduino-based hardware controller with a lightweight Windows background service. When keys are pressed on the matrix keypad, the Arduino communicates with the PC over USB Serial, triggering customizable macros such as keystrokes, clipboard actions, system shortcuts, application launchers, and dynamic RGB lighting feedback, while keeping the OLED display synchronized with the PC clock and ambient sensor data.

```
+--------------------------------------------------------------+
|                     Arduino MacroPad                         |
|                                                              |
|   +-----------------------+     +------------------------+   |
|   |   SSD1306 OLED 128x32 |     |  WS2812B RGB NeoPixels |   |
|   | [ Clock / Temp / Msg ]|     |      (x3 status LEDs)  |   |
|   +-----------------------+     +------------------------+   |
|                                                              |
|   +------------------------------------------------------+   |
|   |                  2x5 Keypad Matrix                   |   |
|   |         [ 0 ] [ 1 ] [ 2 ] [ 3 ] [ 4 ]                |   |
|   |         [ 5 ] [ 6 ] [ 7 ] [ 8 ] [ 9 ]                |   |
|   +------------------------------------------------------+   |
|                                                              |
|   +-----------------------+                                  |
|   |      DHT22 Sensor     |                                  |
|   |    [ Temp & Humidity ]|                                  |
|   +-----------------------+                                  |
+------------------------------+-------------------------------+
                               |
                        USB Serial (9600 baud)
                               |
+------------------------------v-------------------------------+
|                    Windows Companion Service                 |
|                                                              |
|  - System Tray icon (Pystray) & Tkinter config window         |
|  - Win32 SendInput (Portuguese / standard layout support)    |
|  - Application launching, clipboard typing, multimedia keys  |
|  - Configurable persistent COM port & baud rate (user.dat)   |
+--------------------------------------------------------------+
```

---

## Features

- **10 Programmable Macro Keys**: Arranged in a 2x5 matrix.
- **OLED Status Display (128x32)**:
  - Default view: PC synchronized date & time + ambient temperature & humidity, which keeps showing without the PC ("Waiting for PC...").
  - Active view: Real-time visual feedback of the currently pressed macro or custom status messages; longer messages switch to small letters.
- **Ambient Sensor**: Continuous temperature and humidity reading via DHT22.
- **RGB Visual Feedback**: 3x individually addressable WS2812B NeoPixel LEDs controlled dynamically from the PC.
- **Windows Companion Service**:
  - Runs in the background with a system tray menu.
  - Interactive COM port auto-detection and baud rate configuration GUI.
  - Accurate keystroke emulation with Unicode and AltGr modifier support.
  - Standalone executable build script included via PyInstaller.

---

## Hardware Configuration & Pinout

| Component | Arduino Pin | Description |
| :--- | :--- | :--- |
| **OLED Display (SSD1306)** | `SDA` / `SCL` (A4/A5 on Uno/Nano) | I2C communication (Address `0x3C`) |
| **NeoPixel LEDs (WS2812B)** | `D2` | Data In (3 LEDs in series) |
| **Keypad Rows (2)** | `D3`, `D4` | Matrix row lines |
| **Keypad Columns (5)** | `D5`, `D6`, `D7`, `D8`, `D9` | Matrix column lines |
| **DHT22 Sensor** | `D12` | Digital data pin |
| **Status Indicator** | `LED_BUILTIN` (`D13`) | On while the PC is connected |

---

## Serial Communication Protocol

The Arduino firmware and the Python service communicate over USB Serial at **9600 baud**, one line of text per command, ending in `\n`:

### PC to Arduino Commands

| Command | Syntax | Description | Example |
| :--- | :--- | :--- | :--- |
| **Date & Time** | `TIME:<dd/mm/yyyy hh:mm:ss>` | Updates display clock, every second; 5 s without one and the PC counts as gone | `TIME:24/10/2026 14:30:00` |
| **OLED Message** | `MSG:<text>` | Displays temporary message (3s) | `MSG:Print Screen` |
| **NeoPixel Color** | `PIXEL:<id>,<r>,<g>,<b>` | Sets color of LED index `id` (0-2) | `PIXEL:1,0,255,0` |

### Arduino to PC Commands

| Command | Syntax | Description | Example |
| :--- | :--- | :--- | :--- |
| **Key Press** | `KEY:<id>` | Sent immediately when key is pressed | `KEY:0` |
| **Temperature** | `TEMP:<val>` | Ambient temperature in °C, as the PC connects and every minute after | `TEMP:21.50` |
| **Humidity** | `HUM:<val>` | Relative humidity in %, sent with the temperature | `HUM:55.00` |
| **Boot State** | `SYSTEM:Started` | Sent on Arduino startup/reset | `SYSTEM:Started` |

---

## Demo Macro Key Mappings

The companion service includes safe, generic demo macros ready to use and customize:

| Key | Action | OLED Display | Description |
| :---: | :--- | :--- | :--- |
| **0** | `Print Screen` | `Print Screen` | Native Windows screenshot |
| **1** | Paste Clipboard | `Typing` / `Clipboard empty` | Safely types current clipboard content |
| **2** | Type Demo Text | `Demo text` | Types: `"Hello from Arduino MacroPad!"` |
| **3** | Visual Feedback + Text | `Demo 3` | Flashes RGB LED and types demo string |
| **4** | Open Application | `Notepad` | Launches Notepad (`notepad.exe`) |
| **5** | Type Demo Email | `Demo email` | Types: `"demo.user@example.com"` |
| **6** | Toggle Green LED | `Spotify` / `Spotify OFF` | Media / app toggle status demo |
| **7** | Toggle Crimson LED | `Discord` / `Discord OFF` | App mute / connection status demo |
| **8** | Mute Audio | `Audio Mute` | Toggles system volume mute (`volumemute`) |
| **9** | Launch Utility | `Calculator` | Opens Windows Calculator (`calc.exe`) |

---

## Getting Started

### 1. Arduino Firmware

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. Install the required libraries via **Sketch -> Include Library -> Manage Libraries...**:
   - `Keypad` by Mark Stanley, Alexander Brevig
   - `Adafruit NeoPixel` by Adafruit
   - `Adafruit SSD1306` by Adafruit
   - `Adafruit GFX Library` by Adafruit
   - `Adafruit BusIO` by Adafruit
   - `DHT sensor library` by Adafruit
   - `Adafruit Unified Sensor` by Adafruit
3. Open `arduino/arduino.ino`.
4. Select your board and serial port, then click **Upload**. For an Arduino Nano with the old bootloader, pick **Processor -> ATmega328P (Old Bootloader)**. Close anything using the port first, such as the service.

### 2. Python Companion Service

1. Ensure Python 3.10+ is installed on Windows.
2. Navigate to the `service` directory and install the required packages:
   ```powershell
   cd service
   py -m pip install pyserial pyautogui pystray pyperclip pillow
   ```
3. Run the service:
   ```powershell
   py service.py
   ```
4. Right-click the **ARD** icon in your system tray and select **Settings** to choose your Arduino's COM port.

### 3. Build Standalone Executable (.exe)

To generate a standalone executable that runs without a console window:

```powershell
cd service
deploy.bat
```

Or run PyInstaller directly:

```powershell
py -m pip install pyinstaller
py -m PyInstaller --noconsole --onefile --name "MacroPadService" service.py
```

The resulting binary will be placed in `service/dist/MacroPadService.exe`.

---

## Security & Customization

- **No Hardcoded Secrets**: This public repository uses clean demo texts and generic paths. Never commit plain-text passwords, personal emails, or sensitive API keys.
- **Local Configurations Ignored**: The runtime configuration file `service/user.dat` is excluded via `.gitignore`. A sample template is provided at [`service/user.dat.example`](service/user.dat.example).
- **Environment Variables**: For personal macros requiring credentials or custom paths, load them using `os.getenv("VARIABLE_NAME")` or a local untracked configuration file.

---

## License

This project is licensed under the [MIT License](LICENSE).
