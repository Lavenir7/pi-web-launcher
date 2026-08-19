# Pi Web 启动器

简体中文 | [English](./README.md)

Pi Web 启动器是一个用于管理本机 [pi-web](https://github.com/agegr/pi-web) 的 Windows 桌面及系统托盘程序。它提供图形界面，用来选择生图模型、配置访问方式，以及启动、停止、重启、检测和打开 pi-web。

## 有什么用

- 从已配置的 CLIProxyAPI 提供商发现可用的生图模型。
- 支持选择已发现的模型，也支持直接输入自定义模型名称。
- 配置 hostname、port 和可选的密码保护。
- 启动、停止、重启、检测和打开本机 pi-web 服务。
- 显示本机及局域网访问地址。
- 常驻 Windows 通知区域，并提供状态图标和快捷操作。
- 将用户配置保存在 `%LOCALAPPDATA%\Pi Web Launcher`。

## 安装

### 1. 安装前置环境

需要：

- Windows 10 或更高版本
- Node.js 22.19.0 或更高版本
- 已全局安装 pi-web
- 已在 Pi 中配置 CLIProxyAPI

如未安装 pi-web，请在 PowerShell 中运行：

```powershell
npm install -g @agegr/pi-web@latest
```

### 2. 安装 Pi Web 启动器

1. 从 GitHub Releases 页面下载 `PiWebLauncher-v1.0.0-windows-x64.zip`。
2. 将 ZIP 完整解压到任意目录。
3. 运行解压后 `PiWebLauncher` 目录中的 `PiWebLauncher.exe`。

请保留完整程序目录，不要只单独复制 exe。便携版已包含所需运行环境，不需要另外安装 Python。

## 使用方法

1. 选择已发现的生图模型，或直接在模型输入框中填写自定义模型名称。
2. 设置 hostname 和 port：
   - `127.0.0.1` 仅允许本机访问。
   - `0.0.0.0` 允许局域网中的其他设备访问，启动时需要确认。
3. 除非明确需要无认证访问，否则建议保持密码保护开启。pi-web 用户名为 `pi`。
4. 点击“启动”。服务就绪后，启动器会使用默认浏览器打开 pi-web。
5. 可按需使用“检测连接”“打开”“重启”或“停止”。
6. 关闭窗口后，启动器会继续在 Windows 通知区域运行。

托盘操作：

- **停止时单击：** 使用已保存配置启动 pi-web。
- **运行时单击：** 打开 pi-web。
- **双击：** 显示启动器窗口。
- **右键：** 显示窗口、启动或停止 pi-web、打开 pi-web，或者退出启动器。

不要通过 HTTP 将 pi-web 直接暴露到公网。仅应在可信局域网中使用 `0.0.0.0`。
