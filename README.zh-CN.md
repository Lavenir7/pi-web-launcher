# Pi Web 启动器

简体中文 | [English](./README.md)

Pi Web 启动器是一个 Windows 桌面应用，用于配置和管理本机安装的 [pi-web](https://github.com/agegr/pi-web)。它提供图形界面，可以选择生图模型，设置 hostname、port 和访问密码，并启动、停止或重启 pi-web。

## 环境要求

- Windows
- Node.js 22.19.0 或更高版本
- 已全局安装 pi-web
- 已在 Pi 中配置 CLIProxyAPI

使用 `PiWebLauncher.exe` 不需要安装 Python。只有从源码运行时才需要 Python 3.10 或更高版本，并包含 Tkinter。

如未安装 pi-web，请运行：

```powershell
npm install -g @agegr/pi-web@latest
```

## 使用方法

1. 从 `dist` 目录获取 `PiWebLauncher.exe`，或下载、克隆本仓库。
2. 双击 `PiWebLauncher.exe`，启动时不会出现终端黑框。
3. 如果从源码运行，可以双击 `start-pi-web-launcher.cmd`，或者运行：

   ```powershell
   python .\pi_web_launcher.py
   ```

4. 选择生图模型，并设置 hostname、port 和访问密码。点击“生成”可生成随机 16 位密码，点击“复制”可复制当前密码。
5. 点击“启动”。服务就绪后，启动器会在浏览器中打开 pi-web。
6. 启动器打开时会自动进行一次严格状态检查；点击“刷新状态”可随时再次检查。修改配置后点击“重启”使其生效；点击“打开”可重新打开正在运行的网页；点击“停止”关闭服务。

HTTP Basic Auth 用户名为 `pi`。默认密码为 `123456`，允许其他设备访问前请先修改密码。

将 hostname 设置为 `0.0.0.0` 会把 pi-web 暴露到局域网。请仅在可信网络中使用，不要通过 HTTP 将 pi-web 直接暴露到公网。
