# Pi Web 启动器

简体中文 | [English](./README.md)

Pi Web 启动器是一个 Windows 桌面应用，用于配置和管理本机安装的 [pi-web](https://github.com/agegr/pi-web)。它提供图形界面，可以选择生图模型，设置 hostname、port 和访问密码，并启动、停止或重启 pi-web。

## 环境要求

- Windows
- Python 3.10 或更高版本，并包含 Tkinter
- Node.js 22.19.0 或更高版本
- 已全局安装 pi-web
- 已在 Pi 中配置 CLIProxyAPI

如未安装 pi-web，请运行：

```powershell
npm install -g @agegr/pi-web@latest
```

## 使用方法

1. 下载或克隆本仓库。
2. 双击 `start-pi-web-launcher.cmd`，或者运行：

   ```powershell
   python .\pi_web_launcher.py
   ```

3. 选择生图模型，并设置 hostname、port 和访问密码。
4. 点击“启动”。服务就绪后，启动器会在浏览器中打开 pi-web。
5. 修改配置后点击“重启”使其生效；点击“打开”可重新打开正在运行的网页；点击“停止”关闭服务。

HTTP Basic Auth 用户名为 `pi`。默认密码为 `123456`，允许其他设备访问前请先修改密码。

将 hostname 设置为 `0.0.0.0` 会把 pi-web 暴露到局域网。请仅在可信网络中使用，不要通过 HTTP 将 pi-web 直接暴露到公网。
