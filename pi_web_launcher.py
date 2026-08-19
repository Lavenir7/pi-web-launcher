"""Windows Tkinter launcher for the locally installed pi-web command."""

from __future__ import annotations

import http.client
import json
import os
import queue
import secrets
import string
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from tray_controller import TrayController
except ImportError:  # pragma: no cover - tray remains optional for source-only environments
    TrayController = None

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover - useful error for headless Python installs
    tk = None
    messagebox = None
    ttk = None

DEFAULT_HOSTNAME = "127.0.0.1"
DEFAULT_PORT = "30141"
DEFAULT_PASSWORD = "123456"
CUSTOM_MODEL = "自定义…"
CONFIG_FILENAME = "pi-web-launcher.json"
APP_CONFIG_DIRNAME = "Pi Web Launcher"
HOSTNAME_CHOICES = ("127.0.0.1", "0.0.0.0")
LEGACY_CONFIG_KEYS = frozenset({
    "model_mode", "image_model", "custom_image_model", "hostname", "port",
    "password", "password_enabled", "image_models",
})
TRAY_STATE_IDLE = "idle"
TRAY_STATE_RUNNING = "running"
TRAY_STATE_BUSY = "busy"
TRAY_STATE_ERROR = "error"
PI_WEB_READY_TIMEOUT = 45.0
MODEL_REQUEST_TIMEOUT = 15.0

STATE_STOPPED = "stopped"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_STOPPING = "stopping"

DARK_COLORS = {
    "window": "#111318",
    "surface": "#191d26",
    "field": "#0f1218",
    "border": "#303846",
    "text": "#f1f5f9",
    "muted": "#94a3b8",
    "disabled": "#64748b",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "success": "#22c55e",
    "error": "#ef4444",
}


class LauncherError(Exception):
    """An expected, user-displayable launcher error."""


def project_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / relative_path
    return project_dir() / relative_path


def installed_config_path(local_app_data: Path | None = None) -> Path:
    root = local_app_data or Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / APP_CONFIG_DIRNAME / CONFIG_FILENAME


def launcher_config_path(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir / CONFIG_FILENAME
    if getattr(sys, "frozen", False):
        return installed_config_path()
    return project_dir() / CONFIG_FILENAME


def migrate_legacy_config(destination: Path, legacy_path: Path) -> bool:
    if destination.exists() or not legacy_path.is_file() or destination == legacy_path:
        return False
    try:
        raw = json.loads(legacy_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not LEGACY_CONFIG_KEYS.intersection(raw):
            return False
        save_launcher_config(destination, normalize_config(raw))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return True


def agent_dir() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".pi" / "agent"


PASSWORD_ALPHABET = string.ascii_letters + string.digits
PASSWORD_LENGTH = 16


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def default_config() -> dict[str, Any]:
    return {
        "model_mode": "list",
        "image_model": "",
        "custom_image_model": "",
        "hostname": DEFAULT_HOSTNAME,
        "port": DEFAULT_PORT,
        "password": DEFAULT_PASSWORD,
        "password_enabled": True,
        "image_models": [],
    }


def _string(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def normalize_config(raw: Any) -> dict[str, Any]:
    config = default_config()
    if not isinstance(raw, dict):
        return config

    mode = raw.get("model_mode")
    if mode in ("list", "custom"):
        config["model_mode"] = mode
    config["image_model"] = _string(raw.get("image_model"), "").strip()
    config["custom_image_model"] = _string(raw.get("custom_image_model"), "").strip()
    config["hostname"] = _string(raw.get("hostname"), DEFAULT_HOSTNAME).strip() or DEFAULT_HOSTNAME
    raw_port = raw.get("port")
    config["port"] = str(raw_port).strip() if isinstance(raw_port, (str, int)) else DEFAULT_PORT
    config["password"] = _string(raw.get("password"), DEFAULT_PASSWORD)
    password_enabled = raw.get("password_enabled")
    config["password_enabled"] = password_enabled if isinstance(password_enabled, bool) else True
    models = raw.get("image_models")
    if isinstance(models, list):
        config["image_models"] = [item.strip() for item in models if isinstance(item, str) and item.strip()]
    return config


def load_launcher_config(path: Path) -> dict[str, Any]:
    try:
        return normalize_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default_config()


def save_launcher_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_config(config)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def load_clipproxy_config(path: Path | None = None) -> tuple[str, str]:
    source = path or agent_dir() / "cliproxyapi.json"
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LauncherError("无法读取 CLIProxyAPI 配置，请检查 ~/.pi/agent/cliproxyapi.json。") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("baseUrl"), str) or not raw["baseUrl"].strip():
        raise LauncherError("CLIProxyAPI 配置缺少有效的 baseUrl。")
    api_key = raw.get("apiKey")
    if not isinstance(api_key, str) or not api_key.strip():
        raise LauncherError("CLIProxyAPI 配置缺少 API Key。")
    return raw["baseUrl"].strip().rstrip("/"), api_key


def _model_id(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    value = entry.get("id") or entry.get("slug")
    return value.strip() if isinstance(value, str) else ""


def catalog_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise LauncherError("CLIProxyAPI 模型接口返回格式无效。")
    entries = payload.get("models")
    if not isinstance(entries, list):
        entries = payload.get("data")
    if not isinstance(entries, list):
        raise LauncherError("CLIProxyAPI 模型接口缺少模型列表。")
    return [entry for entry in entries if isinstance(entry, dict) and _model_id(entry)]


def _read_json(path: Path, error_message: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LauncherError(error_message) from exc


def discover_image_models(
    *,
    cpa_config_path: Path | None = None,
    model_cache_path: Path | None = None,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> list[str]:
    base_url, api_key = load_clipproxy_config(cpa_config_path)
    cache_path = model_cache_path or agent_dir() / "cliproxyapi-models.json"
    cache_payload = _read_json(cache_path, "无法读取 CLIProxyAPI 本地模型缓存。")
    if not isinstance(cache_payload, dict) or not isinstance(cache_payload.get("models"), list):
        raise LauncherError("CLIProxyAPI 本地模型缓存格式无效。")
    cached_ids = {_model_id(entry) for entry in cache_payload["models"] if _model_id(entry)}

    endpoint = f"{base_url}/v1/models?client_version=pi"
    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=MODEL_REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise LauncherError("无法获取 CLIProxyAPI 模型列表，请检查网络或稍后重试。") from exc

    entries = catalog_entries(payload)
    remote_only = [entry for entry in entries if _model_id(entry) not in cached_ids]
    has_visibility = any("visibility" in entry for entry in remote_only)
    if has_visibility:
        selected = [
            _model_id(entry)
            for entry in remote_only
            if str(entry.get("visibility", "")).strip().lower() == "hide"
        ]
    else:
        selected = [_model_id(entry) for entry in remote_only]
    return list(dict.fromkeys(selected))


def apply_model_list(config: dict[str, Any], models: Iterable[str]) -> dict[str, Any]:
    updated = normalize_config(config)
    discovered = list(dict.fromkeys(model for model in models if isinstance(model, str) and model.strip()))
    updated["image_models"] = discovered
    if updated["model_mode"] == "list" and updated["image_model"] not in discovered:
        updated["image_model"] = discovered[0] if discovered else ""
    return updated


def effective_model(config: dict[str, Any]) -> str:
    if config.get("model_mode") == "custom":
        return str(config.get("custom_image_model", "")).strip()
    return str(config.get("image_model", "")).strip()


def endpoint_config(config: dict[str, Any]) -> tuple[str, int]:
    hostname = str(config.get("hostname", "")).strip() or DEFAULT_HOSTNAME
    raw_port = str(config.get("port", "")).strip()
    if not raw_port.isdigit():
        raise LauncherError("Port 必须是 1 到 65535 之间的整数。")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise LauncherError("Port 必须是 1 到 65535 之间的整数。")
    return hostname, port


def validate_config(config: dict[str, Any]) -> tuple[str, int, str]:
    hostname, port = endpoint_config(config)
    password = str(config.get("password", ""))
    if bool(config.get("password_enabled", True)) and not password:
        raise LauncherError("启用密码保护时，Pi Web 密码不能为空。")
    model = effective_model(config)
    if not model:
        raise LauncherError("请选择生图模型或填写自定义模型名称。")
    return hostname, port, model


def local_network_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = result[4][0]
            if address and not address.startswith("127.") and address != "0.0.0.0":
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def access_urls(hostname: str, port: int) -> list[str]:
    if hostname in ("0.0.0.0", "::", "[::]"):
        urls = [f"http://127.0.0.1:{port}"]
        urls.extend(f"http://{address}:{port}" for address in local_network_addresses())
        return urls
    return [f"http://{hostname}:{port}"]


def readiness_host(hostname: str) -> str:
    return "127.0.0.1" if hostname in ("0.0.0.0", "::", "[::]") else hostname


def needs_lan_confirmation(action: str, hostname: str) -> bool:
    return action == "start" and hostname.strip() == "0.0.0.0"


def protection_status(config: dict[str, Any]) -> str:
    return "密码保护已开启" if bool(config.get("password_enabled", True)) else "密码保护已关闭"


def tray_state_for(state: str, error: bool = False) -> str:
    if error:
        return TRAY_STATE_ERROR
    if state in (STATE_STARTING, STATE_STOPPING):
        return TRAY_STATE_BUSY
    if state == STATE_RUNNING:
        return TRAY_STATE_RUNNING
    return TRAY_STATE_IDLE


def tray_tooltip(state: str, config: dict[str, Any], urls: list[str], *, error: bool = False) -> str:
    labels = {
        STATE_STOPPED: "未启动",
        STATE_STARTING: "启动中",
        STATE_RUNNING: "运行中",
        STATE_STOPPING: "处理中",
    }
    status = "异常" if error else labels.get(state, state)
    try:
        hostname, port = endpoint_config(config)
        fallback_url = access_urls(hostname, port)[0]
    except LauncherError:
        fallback_url = "未配置"
    address = urls[0] if urls else fallback_url
    model = effective_model(config) or "未选择"
    if len(model) > 32:
        model = model[:29] + "..."
    protection = "已开启" if bool(config.get("password_enabled", True)) else "已关闭"
    return f"Pi Web Launcher\n状态：{status}\n地址：{address}\n模型：{model}\n密码保护：{protection}"[:127]


def control_states(state: str) -> dict[str, str]:
    return {
        "start": "normal" if state == STATE_STOPPED else "disabled",
        "stop": "normal" if state == STATE_RUNNING else "disabled",
        "restart": "normal" if state == STATE_RUNNING else "disabled",
    }


def port_is_open(hostname: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((readiness_host(hostname), port), timeout=timeout):
            return True
    except OSError:
        return False


def strict_service_check(hostname: str, port: int, timeout: float = 0.75) -> bool:
    target = readiness_host(hostname)
    connection = http.client.HTTPConnection(target, port, timeout=timeout)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read(1)
        # Basic Auth may return 401/403 even though pi-web is healthy and reachable.
        return 100 <= response.status < 600
    except OSError:
        return False
    finally:
        connection.close()


def listening_pid(port: int) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP":
            continue
        if fields[-2].upper() != "LISTENING":
            continue
        local_endpoint = fields[1].rsplit(":", 1)
        if len(local_endpoint) != 2 or local_endpoint[1] != str(port):
            continue
        try:
            return int(fields[-1])
        except ValueError:
            continue
    return None


def process_id_is_running(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return False
    return any(len(fields) >= 2 and fields[1] == str(pid) for fields in (line.split() for line in result.stdout.splitlines()))


def wait_for_ready(hostname: str, port: int, process: subprocess.Popen[Any], timeout: float = PI_WEB_READY_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    target = readiness_host(hostname)
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError("pi-web 启动失败，请检查端口和 Node.js 环境。")
        connection = http.client.HTTPConnection(target, port, timeout=0.75)
        try:
            connection.request("GET", "/")
            connection.getresponse().read(1)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
        finally:
            connection.close()
    detail = "HTTP 服务未在规定时间内就绪。"
    if last_error:
        detail = f"HTTP 服务未在规定时间内就绪：{last_error.strerror or '连接失败'}。"
    raise LauncherError(detail)


def wait_for_port_closed(hostname: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    target = readiness_host(hostname)
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((target, port), timeout=0.25):
                time.sleep(0.2)
        except OSError:
            return
    raise LauncherError("pi-web 已停止，但端口仍处于占用状态。")


class PiWebProcess:
    def __init__(self, cwd: Path | None = None, popen: Callable[..., Any] = subprocess.Popen) -> None:
        self.cwd = cwd or project_dir()
        self._popen = popen
        self.process: subprocess.Popen[Any] | None = None
        self.external_pid: int | None = None
        self.external_endpoint: tuple[str, int] | None = None
        self.running_config: dict[str, Any] | None = None

    @staticmethod
    def command(hostname: str, port: int) -> list[str]:
        executable = shutil.which("pi-web.cmd") or shutil.which("pi-web") or "pi-web.cmd"
        args = [executable, "--hostname", hostname, "--port", str(port), "--no-open"]
        if sys.platform == "win32" and Path(executable).suffix.lower() == ".cmd":
            return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *args]
        return args

    def adopt(self, config: dict[str, Any]) -> None:
        hostname, port = endpoint_config(config)
        self.process = None
        self.external_pid = listening_pid(port)
        self.external_endpoint = (hostname, port)
        self.running_config = normalize_config(config)

    def start(self, config: dict[str, Any]) -> None:
        hostname, port, model = validate_config(config)
        if self.is_running():
            raise LauncherError("pi-web 已经在运行。")
        if port_is_open(hostname, port):
            raise LauncherError(f"端口 {port} 已被占用，请更换端口或停止占用它的程序。")
        environment = os.environ.copy()
        environment["CLIPROXYAPI_IMAGE_MODEL"] = model
        if bool(config.get("password_enabled", True)):
            environment["PI_WEB_PASSWORD"] = str(config["password"])
        else:
            environment.pop("PI_WEB_PASSWORD", None)
        command = self.command(hostname, port)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if sys.platform == "win32":
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = self._popen(
                command,
                cwd=str(self.cwd),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise LauncherError("找不到 pi-web.cmd，请确认 pi-web 已安装并在 PATH 中。") from exc
        self.process = process
        self.external_pid = None
        self.external_endpoint = None
        try:
            wait_for_ready(hostname, port, process)
        except BaseException:
            self.stop(config, wait_for_port=False)
            raise
        self.running_config = normalize_config(config)

    def stop(self, config: dict[str, Any] | None = None, wait_for_port: bool = True) -> None:
        process = self.process
        pid = getattr(process, "pid", None) if process is not None else self.external_pid
        if process is None and pid is None and config is not None:
            _, port = endpoint_config(config)
            pid = listening_pid(port)
        if process is None and pid is None:
            self.running_config = None
            self.external_endpoint = None
            return
        try:
            process_running = process is not None and process.poll() is None
            external_running = process is None and pid is not None and process_id_is_running(pid)
            if process_running or external_running:
                if sys.platform == "win32" and pid:
                    result = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    if result.returncode != 0:
                        if process is not None and process.poll() is None:
                            process.kill()
                        elif external_running:
                            raise LauncherError("无法停止检测到的 pi-web 进程，请尝试以管理员身份运行启动器。")
                elif process is not None:
                    process.terminate()
                if process is not None:
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            if wait_for_port and config is not None:
                hostname, port = endpoint_config(config)
                wait_for_port_closed(hostname, port)
        finally:
            self.process = None
            self.external_pid = None
            self.external_endpoint = None
            self.running_config = None

    def is_running(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        if self.external_endpoint is not None:
            return strict_service_check(*self.external_endpoint)
        return False


class IconButton(tk.Canvas if tk is not None else object):
    """Small theme-aware icon button with a native Tk tooltip."""

    SIZE = 26

    def __init__(
        self,
        parent: Any,
        *,
        icon: str,
        command: Callable[[], None],
        tooltip: str,
        background: str | None = None,
        size: int = SIZE,
    ) -> None:
        if tk is None:
            raise LauncherError("当前 Python 未安装 Tkinter。")
        self._icon = icon
        self._command = command
        self._tooltip_text = tooltip
        self._background = background or DARK_COLORS["field"]
        self._state = "normal"
        self._hovered = False
        self._tooltip_after: str | None = None
        self._tooltip_window: Any = None
        super().__init__(
            parent,
            width=size,
            height=size,
            highlightthickness=0,
            borderwidth=0,
            background=self._background,
            cursor="hand2",
            takefocus=True,
        )
        self.bind("<Button-1>", self._activate)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", lambda _event: self._set_hovered(True))
        self.bind("<FocusOut>", lambda _event: self._set_hovered(False))
        self._draw()

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        state = kwargs.pop("state", None)
        result = super().configure(cnf, **kwargs) if cnf is not None else super().configure(**kwargs)
        if state is not None:
            self._state = str(state)
            self.configure(cursor="hand2" if self._state != "disabled" else "arrow")
            self._draw()
        return result

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return self._state
        return super().cget(key)

    def set_icon(self, icon: str, tooltip: str | None = None) -> None:
        self._icon = icon
        if tooltip is not None:
            self._tooltip_text = tooltip
        self._draw()

    def _activate(self, _event: Any = None) -> None:
        if self._state != "disabled":
            self._command()

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        self._draw()

    def _on_enter(self, _event: Any) -> None:
        self._set_hovered(True)
        self._tooltip_after = self.after(450, self._show_tooltip)

    def _on_leave(self, _event: Any) -> None:
        self._set_hovered(False)
        if self._tooltip_after is not None:
            self.after_cancel(self._tooltip_after)
            self._tooltip_after = None
        self._hide_tooltip()

    def _show_tooltip(self) -> None:
        self._tooltip_after = None
        if self._tooltip_window is not None or not self._tooltip_text:
            return
        window = tk.Toplevel(self)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 5}")
        label = tk.Label(
            window,
            text=self._tooltip_text,
            background=DARK_COLORS["surface"],
            foreground=DARK_COLORS["text"],
            borderwidth=1,
            relief="solid",
            padx=6,
            pady=3,
        )
        label.pack()
        self._tooltip_window = window

    def _hide_tooltip(self) -> None:
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
            self._tooltip_window = None

    def _draw(self) -> None:
        self.delete("icon")
        self.configure(background=DARK_COLORS["surface"] if self._hovered else self._background)
        color = DARK_COLORS["disabled"] if self._state == "disabled" else DARK_COLORS["muted"]
        if self._hovered and self._state != "disabled":
            color = DARK_COLORS["text"]
        if self._icon == "copy":
            self.create_rectangle(7, 8, 17, 19, outline=color, width=1.4, tags="icon")
            self.create_rectangle(11, 5, 21, 16, outline=color, width=1.4, tags="icon")
        elif self._icon in ("eye", "eye-off"):
            self.create_arc(4, 7, 22, 20, start=20, extent=140, style="arc", outline=color, width=1.4, tags="icon")
            self.create_arc(4, 7, 22, 20, start=200, extent=140, style="arc", outline=color, width=1.4, tags="icon")
            self.create_oval(11, 11, 15, 15, outline=color, width=1.2, tags="icon")
            if self._icon == "eye-off":
                self.create_line(5, 21, 21, 5, fill=color, width=1.6, tags="icon")
        elif self._icon == "refresh":
            self.create_text(
                int(self.cget("width")) / 2,
                int(self.cget("height")) / 2 - 1,
                text="↻",
                fill=color,
                font=("Segoe UI Symbol", 15),
                tags="icon",
            )
        elif self._icon == "check":
            self.create_line(6, 13, 11, 18, 21, 7, fill=DARK_COLORS["success"], width=2.0, tags="icon")


class LinkAction(tk.Label if tk is not None else object):
    """Borderless link-like command used for low-emphasis actions."""

    def __init__(self, parent: Any, *, text: str, command: Callable[[], None]) -> None:
        if tk is None:
            raise LauncherError("当前 Python 未安装 Tkinter。")
        self._command = command
        self._state = "normal"
        self._hovered = False
        self._label_text = text
        super().__init__(
            parent,
            text=f"🔗 {text}",
            background=DARK_COLORS["window"],
            foreground="#60a5fa",
            cursor="hand2",
            borderwidth=0,
            padx=0,
            pady=3,
            takefocus=True,
        )
        self.bind("<Button-1>", self._activate)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Enter>", lambda _event: self._set_hovered(True))
        self.bind("<Leave>", lambda _event: self._set_hovered(False))
        self.bind("<FocusIn>", lambda _event: self._set_hovered(True))
        self.bind("<FocusOut>", lambda _event: self._set_hovered(False))

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        state = kwargs.pop("state", None)
        result = super().configure(cnf, **kwargs) if cnf is not None else super().configure(**kwargs)
        if state is not None:
            self._state = str(state)
            self._redraw()
        return result

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return self._state
        return super().cget(key)

    def _activate(self, _event: Any = None) -> None:
        if self._state != "disabled":
            self._command()

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        self._redraw()

    def _redraw(self) -> None:
        disabled = self._state == "disabled"
        foreground = DARK_COLORS["disabled"] if disabled else ("#93c5fd" if self._hovered else "#60a5fa")
        self.configure(
            foreground=foreground,
            cursor="arrow" if disabled else "hand2",
            font=("Segoe UI", 9, "underline" if self._hovered and not disabled else "normal"),
        )


class PasswordProtectionSwitch(tk.Canvas if tk is not None else object):
    """Compact canvas switch matching a restrained desktop settings control."""

    WIDTH = 36
    HEIGHT = 20
    PADDING = 2

    def __init__(self, parent: Any, command: Callable[[], None]) -> None:
        if tk is None:
            raise LauncherError("当前 Python 未安装 Tkinter。")
        super().__init__(
            parent,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightthickness=0,
            borderwidth=0,
            background=DARK_COLORS["window"],
            cursor="hand2",
            takefocus=True,
        )
        self._command = command
        self._enabled = True
        self.bind("<Button-1>", self._on_activate)
        self.bind("<Return>", self._on_activate)
        self.bind("<space>", self._on_activate)
        self.bind("<Enter>", lambda _event: self._draw(True))
        self.bind("<Leave>", lambda _event: self._draw(False))
        self.bind("<FocusIn>", lambda _event: self._draw(True))
        self.bind("<FocusOut>", lambda _event: self._draw(False))
        self._draw(False)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._draw(False)

    def _on_activate(self, _event: Any = None) -> None:
        self._command()

    def _draw(self, highlighted: bool) -> None:
        self.delete("switch")
        enabled = self._enabled
        track = "#3e6f94" if enabled else "#2a303a"
        if highlighted:
            track = "#4b7da4" if enabled else "#3a424e"
        outline = "#5a8bb0" if highlighted and enabled else DARK_COLORS["border"]
        x0 = self.PADDING
        y0 = self.PADDING
        x1 = self.WIDTH - self.PADDING
        y1 = self.HEIGHT - self.PADDING
        self.create_oval(x0, y0, x0 + (y1 - y0), y1, fill=track, outline=outline, tags="switch")
        self.create_rectangle(x0 + (y1 - y0) / 2, y0, x1 - (y1 - y0) / 2, y1, fill=track, outline=track, tags="switch")
        self.create_oval(x1 - (y1 - y0), y0, x1, y1, fill=track, outline=outline, tags="switch")
        knob_size = y1 - y0 - 4
        knob_x = x1 - knob_size - 2 if enabled else x0 + 2
        knob_y = y0 + 2
        self.create_oval(
            knob_x,
            knob_y,
            knob_x + knob_size,
            knob_y + knob_size,
            fill="#f1f5f9" if enabled else "#a3adb9",
            outline="",
            tags="switch",
        )


class LauncherApp:
    def __init__(self, root: Any, base_dir: Path | None = None, *, enable_tray: bool = False) -> None:
        if tk is None or ttk is None:
            raise LauncherError("当前 Python 未安装 Tkinter。")
        self.root = root
        self.base_dir = base_dir or project_dir()
        self.config_path = launcher_config_path(base_dir)
        if base_dir is None and getattr(sys, "frozen", False):
            migrate_legacy_config(self.config_path, project_dir() / CONFIG_FILENAME)
        self.config = load_launcher_config(self.config_path)
        self.config = apply_model_list(self.config, self.config.get("image_models", []))
        self.controller = PiWebProcess(self.base_dir)
        self.state = STATE_STOPPED
        self._refreshing = False
        self._status_checking = False
        self.running_urls: list[str] = []
        self.service_detected = False
        self.service_endpoint: tuple[str, int] | None = None
        self.password_visible = False
        self.password_enabled = tk.BooleanVar(value=self.config["password_enabled"])
        self.tray = None
        self._tray_error = False
        self._tray_snapshot: dict[str, Any] = {"running": False, "busy": False, "has_url": False}
        self._tray_actions: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._exiting = False

        self.root.title("Pi Web Launcher")
        icon_path = resource_path("assets/icons/idle.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.model_mode = tk.StringVar(value=self.config["model_mode"])
        self.model_value = tk.StringVar(value=effective_model(self.config))
        self.custom_model = tk.StringVar(value=self.config.get("custom_image_model", ""))
        self.copy_feedback = tk.StringVar(value="")
        self._copy_feedback_after: str | None = None
        self.hostname = tk.StringVar(value=self.config["hostname"])
        self.port = tk.StringVar(value=self.config["port"])
        self.password = tk.StringVar(value=self.config["password"])
        self.status = tk.StringVar(value="未启动")
        self.address = tk.StringVar(value="访问地址：未启动")

        self._configure_theme()
        self._build_ui()
        self._set_model_values(self.config.get("image_models", []))
        self._apply_mode()
        self._apply_password_protection()
        self._update_controls()
        if enable_tray:
            self._initialize_tray()
        self.root.after(50, self._drain_tray_actions)
        self.root.after(100, self.refresh_models)
        self.root.after(300, self.refresh_status)

    def _configure_theme(self) -> None:
        colors = DARK_COLORS
        self.root.configure(background=colors["window"])
        self.root.option_add("*TCombobox*Listbox.background", colors["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", colors["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", colors["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", colors["text"])

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=colors["window"])
        style.configure("Surface.TFrame", background=colors["surface"])
        style.configure("TLabel", background=colors["window"], foreground=colors["text"])
        style.configure("Muted.TLabel", background=colors["window"], foreground=colors["muted"])
        style.configure("Muted.Status.TLabel", background=colors["window"], foreground=colors["muted"])
        style.configure("Success.Status.TLabel", background=colors["window"], foreground=colors["success"])
        style.configure("Error.Status.TLabel", background=colors["window"], foreground=colors["error"])
        style.configure("Address.TLabel", background=colors["window"], foreground=colors["muted"])
        style.configure("TSeparator", background=colors["border"])
        style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["text"],
            insertcolor=colors["text"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            padding=6,
        )
        style.configure("Password.TEntry", padding=(6, 6, 60, 6))
        style.map(
            "TEntry",
            fieldbackground=[("disabled", colors["surface"])],
            foreground=[("disabled", colors["disabled"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["field"],
            foreground=colors["text"],
            insertcolor=colors["text"],
            selectbackground=colors["accent"],
            selectforeground=colors["text"],
            arrowcolor=colors["muted"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            focuscolor=colors["accent"],
            relief="solid",
            borderwidth=1,
            arrowsize=12,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("focus", colors["field"]), ("readonly", colors["field"]), ("disabled", colors["surface"])],
            background=[("focus", colors["field"]), ("readonly", colors["field"]), ("active", colors["field"]), ("pressed", colors["field"]), ("disabled", colors["surface"])],
            foreground=[("focus", colors["text"]), ("readonly", colors["text"]), ("disabled", colors["disabled"])],
            bordercolor=[("focus", colors["accent"]), ("active", colors["accent_hover"]), ("disabled", colors["border"])],
            lightcolor=[("focus", colors["accent"]), ("active", colors["accent_hover"])],
            darkcolor=[("focus", colors["accent"]), ("active", colors["accent_hover"])],
            arrowcolor=[("focus", colors["text"]), ("active", colors["text"]), ("disabled", colors["disabled"])],
            selectbackground=[("readonly", colors["accent"])],
            selectforeground=[("readonly", colors["text"])],
        )
        style.configure(
            "TButton",
            background=colors["surface"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            focuscolor=colors["accent"],
            padding=(0, 7),
        )
        style.map(
            "TButton",
            background=[
                ("active", colors["accent_hover"]),
                ("pressed", colors["accent"]),
                ("disabled", colors["surface"]),
            ],
            foreground=[("disabled", colors["disabled"])],
            bordercolor=[("focus", colors["accent"]), ("active", colors["accent_hover"])],
        )
        style.configure(
            "Accent.TButton",
            background=colors["accent"],
            foreground=colors["text"],
            bordercolor=colors["accent"],
            padding=(0, 7),
        )
        style.map("Accent.TButton", background=[("active", colors["accent_hover"]), ("pressed", colors["accent"])])

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="生图模型").grid(row=0, column=0, sticky="w")
        model_row = ttk.Frame(frame)
        model_row.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        model_row.columnconfigure(0, weight=1)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_value, width=30)
        self.model_combo.grid(row=0, column=0, sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        self.model_combo.bind("<FocusOut>", self._on_model_edited)
        self.refresh_button = IconButton(
            model_row,
            icon="refresh",
            command=self.refresh_models,
            tooltip="更新模型列表",
            background=DARK_COLORS["window"],
            size=28,
        )
        self.refresh_button.grid(row=0, column=1, padx=(5, 0))

        network = ttk.Frame(frame)
        network.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        network.columnconfigure(0, weight=1)
        network.columnconfigure(1, weight=0)
        network.columnconfigure(2, weight=0)
        ttk.Label(network, text="Hostname").grid(row=0, column=0, sticky="w")
        ttk.Label(network, text="Port").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.hostname_combo = ttk.Combobox(network, textvariable=self.hostname, values=HOSTNAME_CHOICES, width=22)
        self.hostname_combo.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Entry(network, textvariable=self.port, width=8).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(4, 0))

        password_title = ttk.Frame(frame)
        self.password_title_row = password_title
        password_title.grid(row=3, column=0, sticky="ew")
        password_title.columnconfigure(2, weight=1)
        ttk.Label(password_title, text="Pi Web 密码").grid(row=0, column=0, sticky="w")
        self.password_switch = PasswordProtectionSwitch(
            password_title,
            command=self._toggle_password_protection,
        )
        self.password_switch.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.copy_feedback_label = ttk.Label(
            password_title, textvariable=self.copy_feedback, style="Success.Status.TLabel"
        )
        self.copy_feedback_label.grid(row=0, column=2, sticky="e", padx=(8, 10))
        self.username_hint = ttk.Label(password_title, text="Pi Web 用户名: pi", style="Muted.TLabel")
        self.username_hint.grid(row=0, column=3, sticky="e")
        password_row = ttk.Frame(frame)
        password_row.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        password_row.columnconfigure(0, weight=1)
        password_field = ttk.Frame(password_row)
        password_field.grid(row=0, column=0, sticky="ew")
        password_field.columnconfigure(0, weight=1)
        self.password_entry = ttk.Entry(
            password_field,
            textvariable=self.password,
            show="*",
            width=25,
            style="Password.TEntry",
        )
        self.password_entry.grid(row=0, column=0, sticky="ew")
        self.password_toggle = IconButton(
            password_field,
            icon="eye",
            command=self._toggle_password,
            tooltip="显示密码",
        )
        self.password_toggle.place(relx=1.0, rely=0.5, x=-3, anchor="e")
        self.password_copy = IconButton(
            password_field,
            icon="copy",
            command=self._copy_password,
            tooltip="复制密码",
        )
        self.password_copy.place(relx=1.0, rely=0.5, x=-31, anchor="e")
        self.password_generate = ttk.Button(password_row, text="生成", width=6, command=self._generate_password)
        self.password_generate.grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(frame).grid(row=5, column=0, sticky="ew", pady=(10, 10))
        self.status_label = ttk.Label(frame, textvariable=self.status, style="Muted.Status.TLabel")
        self.status_label.grid(row=6, column=0, sticky="w")
        address_row = ttk.Frame(frame)
        address_row.grid(row=7, column=0, sticky="ew", pady=(4, 12))
        address_row.columnconfigure(0, weight=1)
        ttk.Label(address_row, textvariable=self.address, justify="left", style="Address.TLabel").grid(row=0, column=0, sticky="w")
        self.open_button = ttk.Button(address_row, text="打开", width=9, command=self.open_running_url)
        self.open_button.grid(row=0, column=1, sticky="n", padx=(12, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        self.refresh_status_button = LinkAction(buttons, text="检测连接", command=self.refresh_status)
        self.refresh_status_button.grid(row=0, column=0, sticky="w")
        actions = ttk.Frame(buttons)
        actions.grid(row=0, column=1, sticky="e")
        self.stop_button = ttk.Button(actions, text="停止", width=9, command=self.stop)
        self.stop_button.grid(row=0, column=0, padx=(0, 6))
        self.restart_button = ttk.Button(actions, text="重启", width=9, command=self.restart)
        self.restart_button.grid(row=0, column=1, padx=(0, 6))
        self.start_button = ttk.Button(actions, text="启动", width=9, style="Accent.TButton", command=self.start)
        self.start_button.grid(row=0, column=2)

    def _initialize_tray(self) -> None:
        if TrayController is None:
            return
        icons = {
            TRAY_STATE_IDLE: resource_path("assets/icons/idle.ico"),
            TRAY_STATE_RUNNING: resource_path("assets/icons/running.ico"),
            TRAY_STATE_BUSY: resource_path("assets/icons/busy.ico"),
            TRAY_STATE_ERROR: resource_path("assets/icons/error.ico"),
        }
        tray = TrayController(
            icon_paths=icons,
            dispatch=self._enqueue_tray_action,
            status_provider=self._tray_status,
            on_single_click=self._on_tray_single_click,
            on_double_click=self.show_window,
            on_show_window=self.show_window,
            on_toggle_service=self._on_tray_toggle_service,
            on_open=self.open_running_url,
            on_exit=self.exit_application,
        )
        if tray.start():
            self.tray = tray
            self._update_tray()

    def _enqueue_tray_action(self, callback: Callable[[], None]) -> None:
        self._tray_actions.put(callback)

    def _drain_tray_actions(self) -> None:
        while True:
            try:
                callback = self._tray_actions.get_nowait()
            except queue.Empty:
                break
            callback()
        if not self._exiting:
            self.root.after(50, self._drain_tray_actions)

    def _tray_status(self) -> dict[str, Any]:
        return dict(self._tray_snapshot)

    def _update_tray(self, *, error: bool | None = None) -> None:
        if error is not None:
            self._tray_error = error
        self._tray_snapshot = {
            "running": self.state == STATE_RUNNING,
            "busy": self.state in (STATE_STARTING, STATE_STOPPING),
            "has_url": bool(self.running_urls),
        }
        if self.tray is not None:
            if self.state in (STATE_STARTING, STATE_RUNNING, STATE_STOPPING):
                tooltip_config = self.controller.running_config or self.config
            else:
                tooltip_config = self._form_config()
            self.tray.update(
                tray_state_for(self.state, self._tray_error),
                tray_tooltip(self.state, tooltip_config, self.running_urls, error=self._tray_error),
            )

    def _set_status(self, message: str, tone: str = "muted") -> None:
        self.status.set(message)
        self.status_label.configure(style=f"{tone.capitalize()}.Status.TLabel")
        self._update_tray(error=tone == "error")

    def _set_model_values(self, models: Iterable[str]) -> None:
        values = [model for model in models if isinstance(model, str) and model.strip()]
        self.model_combo.configure(values=list(dict.fromkeys(values)))

    def _toggle_password(self) -> None:
        self.password_visible = not self.password_visible
        self.password_entry.configure(show="" if self.password_visible else "*")
        self.password_toggle.set_icon(
            "eye-off" if self.password_visible else "eye",
            "隐藏密码" if self.password_visible else "显示密码",
        )

    def _toggle_password_protection(self) -> None:
        self.password_enabled.set(not self.password_enabled.get())
        self._apply_password_protection()
        self.config = self._form_config()
        try:
            save_launcher_config(self.config_path, self.config)
        except OSError:
            self._set_status("密码保护状态已改变，但无法保存配置", "error")
        self._update_tray()

    def _apply_password_protection(self) -> None:
        enabled = bool(self.password_enabled.get())
        self.password_switch.set_enabled(enabled)
        state = "normal" if enabled else "disabled"
        self.password_entry.configure(state=state)
        self.password_toggle.configure(state=state)
        self.password_generate.configure(state=state)
        self.password_copy.configure(state=state)

    def _generate_password(self) -> None:
        self.password.set(generate_password())

    def _copy_password(self) -> None:
        password = self.password.get()
        if not password:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(password)
        self.root.update()
        self.password_copy.set_icon("check", "已复制")
        self.copy_feedback.set("已复制")
        if self._copy_feedback_after is not None:
            self.root.after_cancel(self._copy_feedback_after)
        self._copy_feedback_after = self.root.after(1600, self._clear_copy_feedback)

    def _clear_copy_feedback(self) -> None:
        self._copy_feedback_after = None
        self.copy_feedback.set("")
        self.password_copy.set_icon("copy", "复制密码")

    def _sync_model_mode(self) -> None:
        value = self.model_value.get().strip()
        models = set(self.config.get("image_models", []))
        if value and value not in models:
            self.model_mode.set("custom")
            self.custom_model.set(value)
        else:
            self.model_mode.set("list")
            self.config["image_model"] = value

    def _on_model_selected(self, _event: Any = None) -> None:
        self._sync_model_mode()

    def _on_model_edited(self, _event: Any = None) -> None:
        self.model_value.set(self.model_value.get().strip())
        self._sync_model_mode()

    def _apply_mode(self) -> None:
        self.model_value.set(effective_model(self.config))
        self._sync_model_mode()

    def _update_controls(self) -> None:
        states = control_states(self.state)
        try:
            current_endpoint = endpoint_config(self._form_config())
        except LauncherError:
            current_endpoint = None
        if self.state == STATE_STOPPED and self.service_detected and current_endpoint == self.service_endpoint:
            states["start"] = "disabled"
        self.start_button.configure(state=states["start"])
        self.stop_button.configure(state=states["stop"])
        self.restart_button.configure(state=states["restart"])
        self.refresh_button.configure(state="disabled" if self._refreshing else "normal")
        self.refresh_status_button.configure(state="disabled" if self._status_checking else "normal")
        service_matches_form = self.service_detected and current_endpoint == self.service_endpoint
        self.open_button.configure(
            state="normal" if self.running_urls and (self.state == STATE_RUNNING or service_matches_form) else "disabled"
        )

    def _form_config(self) -> dict[str, Any]:
        self._sync_model_mode()
        config = normalize_config(self.config)
        selected_model = self.model_value.get().strip()
        config.update(
            {
                "model_mode": self.model_mode.get(),
                "image_model": selected_model if self.model_mode.get() == "list" else config.get("image_model", ""),
                "custom_image_model": selected_model if self.model_mode.get() == "custom" else self.custom_model.get().strip(),
                "hostname": self.hostname.get().strip() or DEFAULT_HOSTNAME,
                "port": self.port.get().strip(),
                "password": self.password.get(),
                "password_enabled": bool(self.password_enabled.get()),
            }
        )
        return config

    def _validate_form(self) -> dict[str, Any]:
        config = self._form_config()
        validate_config(config)
        return config

    def refresh_status(self) -> None:
        if self._status_checking:
            return
        try:
            hostname, port = endpoint_config(self._form_config())
        except LauncherError as exc:
            self._set_status(f"状态检查失败：{exc}", "error")
            return
        self._status_checking = True
        self._set_status("正在检查 pi-web 状态…")
        self._update_controls()

        def worker() -> None:
            try:
                available = strict_service_check(hostname, port)
            except (OSError, http.client.HTTPException):
                available = False
            self.root.after(0, lambda: self._status_checked(hostname, port, available))

        threading.Thread(target=worker, daemon=True).start()

    def _status_checked(self, hostname: str, port: int, available: bool) -> None:
        self._status_checking = False
        if available:
            self.service_detected = True
            self.service_endpoint = (hostname, port)
            self.running_urls = access_urls(hostname, port)
            if self.state == STATE_STOPPED:
                self.controller.adopt(self._form_config())
                self.state = STATE_RUNNING
                self._set_status("检测到 pi-web 正在运行，已接管控制", "success")
                self.root.after(1000, self._monitor_process)
            else:
                self._set_status("pi-web 运行中", "success")
            self.address.set("绑定地址：http://%s:%s\n访问地址：%s" % (hostname, port, "\n".join(self.running_urls)))
        else:
            self.service_detected = False
            self.service_endpoint = None
            if self.state == STATE_STOPPED or (self.state == STATE_RUNNING and self.controller.process is None):
                self.controller.external_pid = None
                self.controller.external_endpoint = None
                self.controller.running_config = None
                self.state = STATE_STOPPED
                self.running_urls = []
                self._set_status("未检测到正在运行的 pi-web", "muted")
                self.address.set("访问地址：未启动")
            elif self.state == STATE_RUNNING:
                self._set_status("进程仍在运行，但 HTTP 服务无响应", "error")
        self._update_controls()

    def refresh_models(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self._set_status("正在刷新模型列表…")
        self._update_controls()

        def worker() -> None:
            try:
                models = discover_image_models()
            except LauncherError as exc:
                self.root.after(0, lambda: self._refresh_failed(str(exc)))
                return
            self.root.after(0, lambda: self._refresh_succeeded(models))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_succeeded(self, models: list[str]) -> None:
        self._refreshing = False
        current = self._form_config()
        self.config = apply_model_list(current, models)
        self._set_model_values(models)
        self.model_mode.set(self.config["model_mode"])
        self.model_value.set(effective_model(self.config))
        self.custom_model.set(self.config.get("custom_image_model", ""))
        self._sync_model_mode()
        try:
            save_launcher_config(self.config_path, self.config)
        except OSError:
            self._set_status("模型列表已刷新，但无法保存配置", "error")
        else:
            self._set_status(f"已发现 {len(models)} 个生图模型", "success")
        self._update_controls()

    def _refresh_failed(self, message: str) -> None:
        self._refreshing = False
        self._set_status(f"模型刷新失败：{message}", "error")
        self._update_controls()

    def _confirm_lan_config(self, config: dict[str, Any]) -> bool:
        hostname = str(config.get("hostname", "")).strip() or DEFAULT_HOSTNAME
        if not needs_lan_confirmation("start", hostname):
            return True
        protected = bool(config.get("password_enabled", True))
        protection_message = (
            "当前已开启 HTTP Basic Auth。"
            if protected
            else "当前未开启密码保护，其他网络设备无需认证即可访问高权限服务！"
        )
        return bool(
            messagebox.askyesno(
                "确认局域网访问",
                "Hostname 为 0.0.0.0，其他网络设备可能访问 pi-web。\n"
                f"{protection_message}\n\n"
                "是否继续启动？",
                parent=self.root,
            )
        )

    def _confirm_lan_start(self) -> bool:
        return self._confirm_lan_config(self._form_config())

    def start(self) -> None:
        if self.state != STATE_STOPPED:
            return
        try:
            config = self._validate_form()
        except LauncherError as exc:
            messagebox.showerror("配置无效", str(exc), parent=self.root)
            return
        if not self._confirm_lan_start():
            return
        self._begin_start(config)

    def _on_tray_single_click(self) -> None:
        if self.state == STATE_STOPPED:
            self.start_saved_config()
        elif self.state == STATE_RUNNING:
            self.open_running_url()

    def _on_tray_toggle_service(self) -> None:
        if self.state == STATE_STOPPED:
            self.start_saved_config()
        elif self.state == STATE_RUNNING:
            self.stop()

    def start_saved_config(self) -> None:
        if self.state != STATE_STOPPED:
            return
        saved = load_launcher_config(self.config_path)
        config = apply_model_list(saved, saved.get("image_models", []))
        try:
            validate_config(config)
        except LauncherError as exc:
            self.show_window()
            self._operation_failed(f"保存的配置无效：{exc}")
            return
        if not self._confirm_lan_config(config):
            return
        self._begin_start(config)

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _begin_start(self, config: dict[str, Any]) -> None:
        self.service_detected = False
        self.service_endpoint = None
        self.config = config
        try:
            save_launcher_config(self.config_path, config)
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法保存启动器配置：{exc}", parent=self.root)
            return
        self.state = STATE_STARTING
        self._set_status(f"正在启动 pi-web（{protection_status(config)}）…")
        self.address.set("访问地址：等待服务就绪")
        self._update_controls()

        def worker() -> None:
            try:
                self.controller.start(config)
            except LauncherError as exc:
                self.root.after(0, lambda: self._operation_failed(str(exc)))
                return
            self.root.after(0, lambda: self._started(config))

        threading.Thread(target=worker, daemon=True).start()

    def _started(self, config: dict[str, Any]) -> None:
        self.service_detected = True
        self.service_endpoint = endpoint_config(config)
        self.state = STATE_RUNNING
        hostname, port, _ = validate_config(config)
        urls = access_urls(hostname, port)
        self.running_urls = urls
        self._set_status(f"已运行：{effective_model(config)}（{protection_status(config)}）", "success")
        self.address.set("绑定地址：http://%s:%s\n访问地址：%s" % (hostname, port, "\n".join(urls)))
        self._update_controls()
        if urls:
            webbrowser.open(urls[0])
        self.root.after(1000, self._monitor_process)

    def _monitor_process(self) -> None:
        if self.state != STATE_RUNNING:
            return
        if not self.controller.is_running():
            self.controller.process = None
            self.controller.external_pid = None
            self.controller.external_endpoint = None
            self.controller.running_config = None
            self.running_urls = []
            self.service_detected = False
            self.service_endpoint = None
            self.state = STATE_STOPPED
            self._set_status("pi-web 已意外退出", "error")
            self.address.set("访问地址：未启动")
            self._update_controls()
            return
        self.root.after(1000, self._monitor_process)

    def _operation_failed(self, message: str) -> None:
        self.service_detected = False
        self.service_endpoint = None
        self.running_urls = []
        self.state = STATE_STOPPED
        self._set_status(f"操作失败：{message}", "error")
        self.address.set("访问地址：未启动")
        self._update_controls()
        messagebox.showerror("pi-web 启动失败", message, parent=self.root)

    def stop(self) -> None:
        if self.state != STATE_RUNNING:
            return
        config = self.controller.running_config or self._form_config()
        self.state = STATE_STOPPING
        self._set_status("正在停止 pi-web…")
        self._update_controls()

        def worker() -> None:
            try:
                self.controller.stop(config)
            except LauncherError as exc:
                self.root.after(0, lambda: self._operation_failed(str(exc)))
                return
            self.root.after(0, self._stopped)

        threading.Thread(target=worker, daemon=True).start()

    def _stopped(self) -> None:
        self.service_detected = False
        self.service_endpoint = None
        self.running_urls = []
        self.state = STATE_STOPPED
        self._set_status("未启动")
        self.address.set("访问地址：未启动")
        self._update_controls()

    def open_running_url(self) -> None:
        if self.running_urls and (self.state == STATE_RUNNING or self.service_detected):
            webbrowser.open(self.running_urls[0])

    def restart(self) -> None:
        if self.state != STATE_RUNNING:
            return
        try:
            config = self._validate_form()
        except LauncherError as exc:
            messagebox.showerror("配置无效", str(exc), parent=self.root)
            return
        try:
            save_launcher_config(self.config_path, config)
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法保存启动器配置：{exc}", parent=self.root)
            return
        self.config = config
        self.state = STATE_STOPPING
        self._set_status(f"正在重启 pi-web（{protection_status(config)}）…")
        self._update_controls()

        def worker() -> None:
            try:
                self.controller.stop(self.controller.running_config or config)
                self.controller.start(config)
            except LauncherError as exc:
                self.root.after(0, lambda: self._operation_failed(str(exc)))
                return
            self.root.after(0, lambda: self._started(config))

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self) -> None:
        if self.tray is not None and not self._exiting:
            self.root.withdraw()
            return
        self.exit_application()

    def exit_application(self) -> None:
        if self._exiting:
            return
        if self.state in (STATE_STARTING, STATE_STOPPING):
            self.show_window()
            messagebox.showwarning("请稍候", "pi-web 正在处理操作，请稍候再退出。", parent=self.root)
            return
        if self.state == STATE_RUNNING:
            self.show_window()
            if not messagebox.askyesno("退出", "pi-web 正在运行，是否停止服务并退出？", parent=self.root):
                return
            try:
                self.controller.stop(self.controller.running_config or self._form_config())
            except LauncherError:
                pass
        self._exiting = True
        try:
            save_launcher_config(self.config_path, self._form_config())
        except OSError:
            pass
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        self.root.destroy()


def main() -> None:
    if tk is None:
        raise SystemExit("Python Tkinter is required to run this launcher.")
    root = tk.Tk()
    LauncherApp(root, enable_tray=sys.platform == "win32")
    root.mainloop()


if __name__ == "__main__":
    main()
