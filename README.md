# Pi Web Launcher

[简体中文](./README.zh-CN.md) | English

Windows Python/Tkinter launcher for the globally installed `pi-web` command.

## Run

Double-click `start-pi-web-launcher.cmd`, or run:

```powershell
python .\pi_web_launcher.py
```

The launcher reads CLIProxyAPI credentials and model metadata from `~/.pi/agent`, and saves launcher settings to `pi-web-launcher.json` beside the script. The CLIProxyAPI API key is not copied into the launcher settings.

The default pi-web Basic Auth username is `pi`; the launcher password defaults to `123456`. Change the password before exposing pi-web to a network you do not fully trust.

## Test

```powershell
python -m unittest -v
```
