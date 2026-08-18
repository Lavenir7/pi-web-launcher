# Pi Web 启动器

简体中文 | [English](./README.md)

这是一个面向 Windows 的 Python/Tkinter 桌面启动器，用于配置、启动、停止和重启全局安装的 `pi-web`。

## 功能

- 自动读取 CLIProxyAPI 配置并发现生图模型
- 支持刷新生图模型列表和填写自定义模型名称
- 配置 pi-web 的 hostname、port 和访问密码
- 密码默认隐藏，可通过按钮显示或再次隐藏
- 启动、停止和重启 pi-web
- 显示当前运行服务的本机和局域网访问地址
- 服务运行后可通过“打开”按钮重新打开网页
- 使用深色 Tkinter 界面
- 自动保存启动器配置

## 环境要求

- Windows
- Python 3.10 或更高版本，并包含 Tkinter
- Node.js 22.19.0 或更高版本
- 已全局安装 `pi-web`
- 已配置 CLIProxyAPI

全局安装 pi-web：

```powershell
npm install -g @agegr/pi-web@latest
```

启动器从以下文件读取 CLIProxyAPI 配置和模型元数据：

```text
~/.pi/agent/cliproxyapi.json
~/.pi/agent/cliproxyapi-models.json
```

CLIProxyAPI API Key 只用于请求模型列表，不会复制到启动器配置中，也不会显示在状态信息里。

## 运行

双击：

```text
start-pi-web-launcher.cmd
```

也可以在 PowerShell 中运行：

```powershell
python .\pi_web_launcher.py
```

## 使用

1. 等待启动器自动刷新生图模型列表，或点击模型选择框旁边的“刷新”。
2. 选择一个生图模型；也可以选择“自定义”并填写模型名称。
3. 设置 hostname、port 和 `PI_WEB_PASSWORD`。
4. 点击“启动”。
5. 服务就绪后，启动器会显示访问地址并打开浏览器。
6. 修改模型或其他配置后，点击“重启”应用新配置。
7. 点击“停止”结束 pi-web 及其子进程。

启动器配置保存在脚本旁边：

```text
pi-web-launcher.json
```

默认配置：

```text
hostname: 127.0.0.1
port: 30141
用户名: pi
密码: 123456
```

## 网络访问安全

当 hostname 为 `127.0.0.1` 时，pi-web 仅供本机访问。

当 hostname 为 `0.0.0.0` 时，同一网络中的其他设备可能访问 pi-web。首次启动前，启动器会显示确认提示。pi-web 能够执行高权限 Agent 操作，因此请注意：

- 在局域网使用前修改默认密码 `123456`
- 仅在可信网络中绑定 `0.0.0.0`
- 不要直接通过公网 HTTP 暴露 pi-web
- HTTP Basic Auth 不会加密传输中的密码；远程使用时应通过可信 VPN 或 HTTPS 反向代理访问

绑定 `0.0.0.0` 时，启动器的“打开”按钮会使用本机地址：

```text
http://127.0.0.1:<port>
```

## 测试

运行全部测试：

```powershell
python -m unittest -v
```

执行 Python 编译检查：

```powershell
python -m py_compile .\pi_web_launcher.py .\test_pi_web_launcher.py
```
