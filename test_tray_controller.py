import unittest
from pathlib import Path
from unittest.mock import patch

import tray_controller


class TrayControllerTests(unittest.TestCase):
    def make_controller(self, **overrides):
        callbacks = {name: lambda: None for name in (
            "on_single_click", "on_double_click", "on_show_window",
            "on_toggle_service", "on_open", "on_exit",
        )}
        callbacks.update(overrides)
        return tray_controller.TrayController(
            icon_paths={"idle": Path("idle.ico")},
            dispatch=lambda callback: callback(),
            status_provider=lambda: {"running": True, "busy": False, "has_url": True},
            **callbacks,
        )

    def test_single_click_is_deferred_and_double_click_cancels_it(self):
        single = []
        double = []
        controller = self.make_controller(
            on_single_click=lambda: single.append(True),
            on_double_click=lambda: double.append(True),
        )
        with patch.object(tray_controller.threading, "Timer") as timer_class:
            timer = timer_class.return_value
            controller._schedule_single_click()
            timer_class.assert_called_once_with(tray_controller.CLICK_DELAY_SECONDS, unittest.mock.ANY)
            controller._on_tray_message(None, None, None, tray_controller.win32con.WM_LBUTTONDBLCLK)
            timer.cancel.assert_called_once_with()
        self.assertEqual(single, [])
        self.assertEqual(double, [True])

    def test_double_click_consumes_following_button_up(self):
        controller = self.make_controller()
        controller._ignore_next_button_up = True
        with patch.object(controller, "_schedule_single_click") as schedule:
            controller._on_tray_message(None, None, None, tray_controller.win32con.WM_LBUTTONUP)
        schedule.assert_not_called()
        self.assertFalse(controller._ignore_next_button_up)

    def test_command_dispatches_menu_actions(self):
        actions = []
        controller = self.make_controller(
            on_show_window=lambda: actions.append("show"),
            on_toggle_service=lambda: actions.append("toggle"),
            on_open=lambda: actions.append("open"),
            on_exit=lambda: actions.append("exit"),
        )
        with patch.object(tray_controller.win32api, "LOWORD", side_effect=[1001, 1002, 1003, 1004]):
            for _ in range(4):
                controller._on_command(None, None, 0, None)
        self.assertEqual(actions, ["show", "toggle", "open", "exit"])

    def test_stop_is_idempotent_and_cancels_pending_click(self):
        controller = self.make_controller()
        pending = unittest.mock.Mock()
        controller._pending_click = pending
        controller._window = 100
        with patch.object(tray_controller.win32gui, "PostMessage") as post:
            controller.stop()
            controller.stop()
        pending.cancel.assert_called_once_with()
        self.assertEqual(post.call_count, 1)

    def test_menu_state_disables_busy_actions(self):
        controller = self.make_controller()
        controller._window = 100
        with patch.object(tray_controller.win32gui, "CreatePopupMenu", return_value=1), \
             patch.object(tray_controller.win32gui, "AppendMenu") as append, \
             patch.object(tray_controller.win32gui, "SetForegroundWindow"), \
             patch.object(tray_controller.win32gui, "GetCursorPos", return_value=(1, 2)), \
             patch.object(tray_controller.win32gui, "TrackPopupMenu"), \
             patch.object(tray_controller.win32gui, "DestroyMenu"), \
             patch.object(controller, "status_provider", return_value={"running": True, "busy": True, "has_url": False}):
            controller._show_menu()
        calls = [call.args for call in append.call_args_list]
        self.assertTrue(any("停止 Pi Web" in args for args in calls))
        self.assertTrue(any("打开 Pi Web" in args for args in calls))


if __name__ == "__main__":
    unittest.main()
