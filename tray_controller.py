"""Windows system tray controller isolated from the Tkinter event loop."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

try:
    import win32api
    import win32con
    import win32gui
    import win32gui_struct
except ImportError:  # pragma: no cover - exercised by packaging/runtime checks
    win32api = None
    win32con = None
    win32gui = None
    win32gui_struct = None

TRAY_CALLBACK_MESSAGE = 0x0400 + 20
TRAY_ICON_ID = 1
CLICK_DELAY_SECONDS = 0.25


class TrayController:
    """Owns the Win32 notification icon and dispatches actions to Tkinter."""

    def __init__(
        self,
        *,
        icon_paths: dict[str, Path],
        dispatch: Callable[[Callable[[], None]], None],
        status_provider: Callable[[], dict[str, Any]],
        on_single_click: Callable[[], None],
        on_double_click: Callable[[], None],
        on_show_window: Callable[[], None],
        on_toggle_service: Callable[[], None],
        on_open: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self.icon_paths = icon_paths
        self.dispatch = dispatch
        self.status_provider = status_provider
        self.on_single_click = on_single_click
        self.on_double_click = on_double_click
        self.on_show_window = on_show_window
        self.on_toggle_service = on_toggle_service
        self.on_open = on_open
        self.on_exit = on_exit
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._window: int | None = None
        self._class_atom: int | None = None
        self._pending_click: threading.Timer | None = None
        self._ignore_next_button_up = False
        self._state = "idle"
        self._tooltip = "Pi Web Launcher"
        self._icons: dict[str, int] = {}
        self._icon_added = False
        self._stop_requested = False

    @property
    def available(self) -> bool:
        return all((win32api, win32con, win32gui, win32gui_struct))

    def start(self) -> bool:
        if not self.available:
            return False
        with self._lock:
            if self._thread is not None:
                return True
            self._thread = threading.Thread(target=self._run, name="pi-web-tray", daemon=True)
            self._thread.start()
        return self._ready.wait(timeout=5)

    def update(self, state: str, tooltip: str) -> None:
        with self._lock:
            self._state = state
            self._tooltip = tooltip[:127]
            window = self._window
        if window is not None:
            win32gui.PostMessage(window, win32con.WM_APP + 1, 0, 0)

    def stop(self) -> None:
        with self._lock:
            if self._stop_requested:
                return
            self._stop_requested = True
            window = self._window
            pending = self._pending_click
            self._pending_click = None
        if pending is not None:
            pending.cancel()
        if window is not None:
            win32gui.PostMessage(window, win32con.WM_CLOSE, 0, 0)
        self._stopped.wait(timeout=3)

    def _dispatch(self, callback: Callable[[], None]) -> None:
        self.dispatch(callback)

    def _run(self) -> None:
        class_name = f"PiWebLauncherTray{threading.get_ident()}"
        message_map = {
            TRAY_CALLBACK_MESSAGE: self._on_tray_message,
            win32con.WM_COMMAND: self._on_command,
            win32con.WM_APP + 1: self._on_update,
            win32con.WM_CLOSE: self._on_close,
            win32con.WM_DESTROY: self._on_destroy,
        }
        window_class = win32gui.WNDCLASS()
        window_class.hInstance = win32api.GetModuleHandle(None)
        window_class.lpszClassName = class_name
        window_class.lpfnWndProc = message_map
        try:
            self._class_atom = win32gui.RegisterClass(window_class)
            self._window = win32gui.CreateWindow(
                self._class_atom,
                class_name,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                window_class.hInstance,
                None,
            )
            self._load_icons()
            self._add_icon()
            self._ready.set()
            win32gui.PumpMessages()
        finally:
            self._ready.set()
            self._stopped.set()

    def _load_icons(self) -> None:
        for state, path in self.icon_paths.items():
            if path.exists():
                self._icons[state] = win32gui.LoadImage(
                    0,
                    str(path),
                    win32con.IMAGE_ICON,
                    0,
                    0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
        if not self._icons:
            self._icons["idle"] = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _current_icon(self) -> int:
        return self._icons.get(self._state) or self._icons.get("idle") or next(iter(self._icons.values()))

    def _add_icon(self) -> None:
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        data = (self._window, TRAY_ICON_ID, flags, TRAY_CALLBACK_MESSAGE, self._current_icon(), self._tooltip)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, data)
        self._icon_added = True

    def _on_update(self, _window: int, _message: int, _wparam: int, _lparam: int) -> int:
        if self._icon_added:
            flags = win32gui.NIF_ICON | win32gui.NIF_TIP
            data = (self._window, TRAY_ICON_ID, flags, 0, self._current_icon(), self._tooltip)
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, data)
        return 0

    def _on_tray_message(self, _window: int, _message: int, _wparam: int, event: int) -> int:
        if event == win32con.WM_LBUTTONUP:
            if self._ignore_next_button_up:
                self._ignore_next_button_up = False
            else:
                self._schedule_single_click()
        elif event == win32con.WM_LBUTTONDBLCLK:
            self._cancel_single_click()
            self._ignore_next_button_up = True
            self._dispatch(self.on_double_click)
        elif event == win32con.WM_RBUTTONUP:
            self._cancel_single_click()
            self._show_menu()
        return 0

    def _schedule_single_click(self) -> None:
        self._cancel_single_click()
        timer = threading.Timer(CLICK_DELAY_SECONDS, self._fire_single_click)
        timer.daemon = True
        with self._lock:
            self._pending_click = timer
        timer.start()

    def _fire_single_click(self) -> None:
        with self._lock:
            self._pending_click = None
        self._dispatch(self.on_single_click)

    def _cancel_single_click(self) -> None:
        with self._lock:
            timer = self._pending_click
            self._pending_click = None
        if timer is not None:
            timer.cancel()

    def _show_menu(self) -> None:
        status = self.status_provider()
        running = bool(status.get("running"))
        has_url = bool(status.get("has_url"))
        menu = win32gui.CreatePopupMenu()
        try:
            self._append_menu(menu, 1001, "显示窗口")
            self._append_menu(menu, 1002, "停止 Pi Web" if running else "启动 Pi Web", enabled=not status.get("busy", False))
            self._append_menu(menu, 1003, "打开 Pi Web", enabled=has_url)
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
            self._append_menu(menu, 1004, "退出", enabled=not status.get("busy", False))
            win32gui.SetForegroundWindow(self._window)
            position = win32gui.GetCursorPos()
            win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON, position[0], position[1], 0, self._window, None)
        finally:
            win32gui.DestroyMenu(menu)

    @staticmethod
    def _append_menu(menu: int, command: int, text: str, *, enabled: bool = True) -> None:
        flags = win32con.MF_STRING | (0 if enabled else win32con.MF_GRAYED)
        win32gui.AppendMenu(menu, flags, command, text)

    def _on_command(self, _window: int, _message: int, wparam: int, _lparam: int) -> int:
        command = win32api.LOWORD(wparam)
        callbacks = {
            1001: self.on_show_window,
            1002: self.on_toggle_service,
            1003: self.on_open,
            1004: self.on_exit,
        }
        callback = callbacks.get(command)
        if callback is not None:
            self._dispatch(callback)
        return 0

    def _on_close(self, _window: int, _message: int, _wparam: int, _lparam: int) -> int:
        self._cancel_single_click()
        if self._icon_added:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self._window, TRAY_ICON_ID))
            self._icon_added = False
        win32gui.DestroyWindow(self._window)
        return 0

    def _on_destroy(self, _window: int, _message: int, _wparam: int, _lparam: int) -> int:
        win32gui.PostQuitMessage(0)
        return 0
