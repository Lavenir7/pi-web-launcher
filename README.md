# Pi Web Launcher

[简体中文](./README.zh-CN.md) | English

Pi Web Launcher is a Windows desktop application for configuring and managing a locally installed [pi-web](https://github.com/agegr/pi-web). It provides a graphical interface for selecting an image-generation model, setting the hostname, port, and access password, and starting, stopping, or restarting pi-web.

## Requirements

- Windows
- Node.js 22.19.0 or newer
- pi-web installed globally
- CLIProxyAPI configured in Pi

Python is not required when using `PiWebLauncher.exe`. Python 3.10 or newer with Tkinter is required only when running from source.

Install pi-web if needed:

```powershell
npm install -g @agegr/pi-web@latest
```

## Usage

1. Download `PiWebLauncher.exe` from the `dist` directory, or download and clone this repository.
2. Double-click `PiWebLauncher.exe` to open the launcher without a terminal window.
3. If running from source, use `start-pi-web-launcher.cmd` or run:

   ```powershell
   python .\pi_web_launcher.py
   ```

4. Select an image model and configure the hostname, port, and password. Use **Generate** to create a random 16-character password, or **Copy** to copy the current password.
5. Click **Start**. The launcher opens pi-web in your browser when the service is ready.
6. Use **Refresh Status** to perform a strict status check at startup or at any time, **Restart** to apply changed settings, **Open** to reopen the running service, and **Stop** to shut it down.

The Basic Auth username is `pi`. The default password is `123456`; change it before allowing access from other devices.

Binding to `0.0.0.0` exposes pi-web to your local network. Use it only on a trusted network, and do not expose pi-web directly to the public internet over HTTP.
