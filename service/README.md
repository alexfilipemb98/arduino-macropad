# MacroPad Service

A Python service that connects the Arduino MacroPad to actions in Windows (keyboard shortcuts, typing text and snippets, opening apps and driving the RGB LEDs), running in the background with an icon in the system tray.

## Features

- **Two-way serial link**: finds and connects to the Arduino on a COM port you pick.
- **Clock sync**: sends the current date and time every second, for the MacroPad's OLED screen.
- **Macros**: runs a macro for each `KEY:x` the device sends.
- **Reliable typing**: special and accented characters typed right in Windows (`SendInput` following the keyboard layout, with a Unicode fallback).
- **Settings window (`Tkinter`)**: pick the COM port and the baud rate.
- **Runs in the background (`pystray`)**: a tray icon to pause and resume the service, open the settings or quit.
- **NeoPixel LEDs**: turns the RGB LEDs on and off to show a state.

## Requirements

- Windows 10 / 11
- Python 3.10+
- An Arduino with the firmware uploaded (`arduino/arduino.ino`)

## Installation

From the project folder or the `service/` folder, install the packages it needs:

```powershell
py -m pip install pyserial pyautogui pystray pyperclip pillow
```

## Settings

The service keeps the COM port and baud rate you pick in `user.dat`.
- An example is provided in `user.dat.example`.
- `user.dat` is created the first time you save the settings in the settings window.
- Settings saved by older versions, with the port under `"porta"`, are still read.
- **Note**: `user.dat` is ignored by Git (`.gitignore`), so your machine's settings aren't pushed to the public repository.

## Running it

To start the service while developing:

```powershell
py service.py
```

When it starts:
1. The service loads the settings from `user.dat` (or `user.dat.example` when there's none) and connects to the Arduino.
2. An icon shows in the system tray (by the Windows clock), with:
   - **Settings**: opens the window to pick the COM port and baud rate.
   - **Start / Stop service**: pauses reading the serial port for a while.
   - **Quit**: closes the COM port and exits.

## Building an executable (.exe)

To build a standalone `.exe` that runs without a console window:

1. Install PyInstaller:
   ```powershell
   py -m pip install pyinstaller
   ```
2. Run the build script:
   ```powershell
   deploy.bat
   ```
   Or by hand:
   ```powershell
   py -m PyInstaller --noconsole --onefile --name "MacroPadService" service.py
   ```
3. The executable is built at `dist/MacroPadService.exe`.

## Demo key mappings

`service.py` comes with a set of demo macros:

| Key | Action | OLED message | What it shows |
| :---: | :--- | :--- | :--- |
| **0** | `Print Screen` | `Print Screen` | Windows' own screenshot |
| **1** | Types the clipboard | `Typing` / `Clipboard empty` | Types the text last copied |
| **2** | Types a demo text | `Demo text` | A snippet typed for you |
| **3** | LED + text | `Demo 3` | An LED on while it types |
| **4** | Opens Notepad | `Notepad` | Opening an app (`notepad.exe`) |
| **5** | Types a demo email | `Demo email` | Typing an email address or a template |
| **6** | Toggles LED 1 | `Spotify` / `Spotify OFF` | A state as a switch, with a green LED (media, for instance) |
| **7** | Toggles LED 2 | `Discord` / `Discord OFF` | A state as a switch, with a crimson LED (an app's mute, for instance) |
| **8** | Mutes the sound | `Audio Mute` | Sends Windows' `volumemute` key |
| **9** | Opens Calculator | `Calculator` | Opening a tool (`calc.exe`) |

## Customising, and keeping it safe

> [!WARNING]
> **Good practice in public repositories**:
> - **Never put passwords or private credentials in the source code.**
> - For macros that need a sign-in or a personal token, use environment variables (`os.getenv("MY_VARIABLE")`) or a local file Git doesn't track (such as `.env`, or a JSON file listed in `.gitignore`).
> - When you change file paths (executables or work folders), check they don't hold your user name or other paths private to your machine before publishing.
