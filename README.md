# Pi Web Launcher

[简体中文](./README.zh-CN.md) | English

Pi Web Launcher is a Windows desktop and system-tray launcher for a locally installed [pi-web](https://github.com/agegr/pi-web). It provides a graphical way to choose an image model, configure access settings, and start, stop, restart, detect, or open pi-web.

## What it does

- Discovers available image-generation models from the configured CLIProxyAPI provider.
- Supports discovered models and manually entered model names.
- Configures hostname, port, and optional password protection.
- Starts, stops, restarts, detects, and opens the local pi-web service.
- Displays local and LAN access addresses.
- Runs in the Windows notification area with status icons and quick actions.
- Saves user settings under `%LOCALAPPDATA%\Pi Web Launcher`.

## Installation

### 1. Install the prerequisites

You need:

- Windows 10 or newer
- Node.js 22.19.0 or newer
- pi-web installed globally
- CLIProxyAPI configured in Pi

Install pi-web from PowerShell if needed:

```powershell
npm install -g @agegr/pi-web@latest
```

### 2. Install Pi Web Launcher

1. Download `PiWebLauncher-v1.0.0-windows-x64.zip` from the GitHub Releases page.
2. Extract the complete ZIP to a directory of your choice.
3. Run `PiWebLauncher.exe` inside the extracted `PiWebLauncher` directory.

Keep the complete directory together. The portable release includes its required runtime, so Python does not need to be installed.

## Usage

1. Choose a discovered image model, or type a custom model name into the model field.
2. Set the hostname and port:
   - `127.0.0.1` allows access from this computer only.
   - `0.0.0.0` allows access from other devices on the local network and requires confirmation when starting.
3. Keep password protection enabled unless you intentionally need unauthenticated access. The pi-web username is `pi`.
4. Click **Start**. The launcher opens pi-web in the default browser when it is ready.
5. Use **Detect Connection**, **Open**, **Restart**, or **Stop** as needed.
6. Close the window to keep the launcher running in the notification area.

Tray controls:

- **Single-click while stopped:** start pi-web with the saved configuration.
- **Single-click while running:** open pi-web.
- **Double-click:** show the launcher window.
- **Right-click:** show the window, start or stop pi-web, open pi-web, or exit.

Do not expose pi-web directly to the public internet over HTTP. Use `0.0.0.0` only on a trusted local network.
