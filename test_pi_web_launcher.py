import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pi_web_launcher as launcher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LauncherCoreTests(unittest.TestCase):
    def test_normalize_config_uses_defaults_for_missing_values(self):
        config = launcher.normalize_config({"port": 30141})
        self.assertEqual(config["hostname"], launcher.DEFAULT_HOSTNAME)
        self.assertEqual(config["port"], "30141")
        self.assertEqual(config["password"], launcher.DEFAULT_PASSWORD)
        self.assertEqual(config["model_mode"], "list")

    def test_save_and_load_config_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            source = launcher.default_config()
            source.update({"model_mode": "custom", "custom_image_model": "image-x", "image_models": ["image-a"]})
            launcher.save_launcher_config(path, source)
            self.assertEqual(launcher.load_launcher_config(path), source)

    def test_discover_hidden_remote_only_models_from_models_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cpa = root / "cliproxyapi.json"
            cache = root / "cliproxyapi-models.json"
            cpa.write_text(json.dumps({"baseUrl": "http://proxy", "apiKey": "secret"}), encoding="utf-8")
            cache.write_text(json.dumps({"models": [{"id": "chat-model"}]}), encoding="utf-8")
            payload = {"models": [
                {"slug": "chat-model", "visibility": "list"},
                {"slug": "image-a", "visibility": "hide"},
                {"slug": "image-b", "visibility": "hide"},
            ]}
            with patch.object(launcher.urllib.request, "Request") as request:
                request.return_value = object()
                result = launcher.discover_image_models(
                    cpa_config_path=cpa,
                    model_cache_path=cache,
                    urlopen=lambda *_args, **_kwargs: FakeResponse(payload),
                )
            self.assertEqual(result, ["image-a", "image-b"])
            self.assertNotIn("secret", json.dumps(result))

    def test_discover_falls_back_to_remote_difference_without_visibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cliproxyapi.json").write_text(json.dumps({"baseUrl": "http://proxy", "apiKey": "secret"}), encoding="utf-8")
            (root / "cliproxyapi-models.json").write_text(json.dumps({"models": [{"id": "chat-model"}]}), encoding="utf-8")
            payload = {"data": [{"id": "chat-model"}, {"id": "image-x"}]}
            with patch.object(launcher.urllib.request, "Request") as request:
                request.return_value = object()
                result = launcher.discover_image_models(
                    cpa_config_path=root / "cliproxyapi.json",
                    model_cache_path=root / "cliproxyapi-models.json",
                    urlopen=lambda *_args, **_kwargs: FakeResponse(payload),
                )
            self.assertEqual(result, ["image-x"])

    def test_model_list_preserves_custom_and_falls_back_stale_list(self):
        custom = launcher.default_config()
        custom.update({"model_mode": "custom", "custom_image_model": "future-image"})
        self.assertEqual(launcher.apply_model_list(custom, ["image-a"])["custom_image_model"], "future-image")

        stale = launcher.default_config()
        stale.update({"image_model": "old-image"})
        updated = launcher.apply_model_list(stale, ["image-a", "image-b"])
        self.assertEqual(updated["image_model"], "image-a")

    def test_validation_rejects_missing_model_and_bad_port(self):
        config = launcher.default_config()
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_config(config)
        config.update({"image_model": "image-a", "port": "bad"})
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_config(config)

    def test_process_start_passes_runtime_secrets_without_persisting_api_key(self):
        class FakeProcess:
            pid = 1234

            def poll(self):
                return None

        calls = []

        def fake_popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProcess()

        config = launcher.default_config()
        config.update({"image_model": "image-a", "password": "runtime-password", "port": "30141"})
        with patch.object(launcher, "port_is_open", return_value=False), patch.object(launcher, "wait_for_ready"):
            controller = launcher.PiWebProcess(popen=fake_popen)
            controller.start(config)
        command, kwargs = calls[0]
        self.assertIn("--no-open", command)
        self.assertEqual(kwargs["env"]["CLIPROXYAPI_IMAGE_MODEL"], "image-a")
        self.assertEqual(kwargs["env"]["PI_WEB_PASSWORD"], "runtime-password")
        self.assertNotIn("apiKey", kwargs["env"])

    def test_access_urls_map_wildcard_to_local_and_lan_addresses(self):
        with patch.object(launcher, "local_network_addresses", return_value=["192.168.1.8"]):
            self.assertEqual(
                launcher.access_urls("0.0.0.0", 30141),
                ["http://127.0.0.1:30141", "http://192.168.1.8:30141"],
            )

    def test_only_initial_wildcard_start_requires_confirmation(self):
        self.assertTrue(launcher.needs_lan_confirmation("start", "0.0.0.0"))
        self.assertFalse(launcher.needs_lan_confirmation("restart", "0.0.0.0"))
        self.assertFalse(launcher.needs_lan_confirmation("start", "127.0.0.1"))

    def test_control_states(self):
        self.assertEqual(launcher.control_states(launcher.STATE_STOPPED), {"start": "normal", "stop": "disabled", "restart": "disabled"})
        self.assertEqual(launcher.control_states(launcher.STATE_RUNNING), {"start": "disabled", "stop": "normal", "restart": "normal"})
        self.assertEqual(launcher.control_states(launcher.STATE_STARTING)["stop"], "disabled")


@unittest.skipIf(launcher.tk is None, "Tkinter is not installed")
class LauncherUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = launcher.tk.Tk()
        self.root.withdraw()
        self.app = launcher.LauncherApp(self.root, Path(self.temporary_directory.name))
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        self.temporary_directory.cleanup()

    def test_dark_theme_and_disabled_styles_are_configured(self):
        style = launcher.ttk.Style(self.root)
        self.assertEqual(style.theme_use(), "clam")
        self.assertEqual(self.root.cget("background"), launcher.DARK_COLORS["window"])
        self.assertEqual(style.lookup("TFrame", "background"), launcher.DARK_COLORS["window"])
        self.assertEqual(style.lookup("TEntry", "fieldbackground"), launcher.DARK_COLORS["field"])
        self.assertEqual(style.lookup("TButton", "foreground", ("disabled",)), launcher.DARK_COLORS["disabled"])
        self.assertEqual(style.lookup("Success.Status.TLabel", "foreground"), launcher.DARK_COLORS["success"])
        popdown = self.root.tk.call("ttk::combobox::PopdownWindow", str(self.app.model_combo))
        listbox = f"{popdown}.f.l"
        self.assertEqual(self.root.tk.call(listbox, "cget", "-background"), launcher.DARK_COLORS["field"])
        self.assertEqual(self.root.tk.call(listbox, "cget", "-foreground"), launcher.DARK_COLORS["text"])
        self.assertEqual(self.root.tk.call(listbox, "cget", "-selectbackground"), launcher.DARK_COLORS["accent"])

    def test_password_toggle_preserves_value(self):
        password = self.app.password.get()
        self.assertEqual(self.app.password_entry.cget("show"), "*")
        self.assertEqual(self.app.password_toggle.cget("text"), "显示")
        self.app._toggle_password()
        self.assertEqual(self.app.password_entry.cget("show"), "")
        self.assertEqual(self.app.password_toggle.cget("text"), "隐藏")
        self.assertEqual(self.app.password.get(), password)
        self.app._toggle_password()
        self.assertEqual(self.app.password_entry.cget("show"), "*")
        self.assertEqual(self.app.password.get(), password)

    def test_model_selector_and_refresh_share_a_row(self):
        self.assertIs(self.app.model_combo.master, self.app.refresh_button.master)
        self.assertEqual(int(self.app.model_combo.grid_info()["row"]), 0)
        self.assertEqual(int(self.app.refresh_button.grid_info()["row"]), 0)
        self.assertEqual(int(self.app.model_combo.grid_info()["column"]), 0)
        self.assertEqual(int(self.app.refresh_button.grid_info()["column"]), 1)

    def test_open_button_uses_running_snapshot_and_tracks_state(self):
        self.assertEqual(str(self.app.open_button.cget("state")), "disabled")
        self.app.state = launcher.STATE_RUNNING
        self.app.running_urls = ["http://127.0.0.1:30141"]
        self.app.hostname.set("0.0.0.0")
        self.app.port.set("49999")
        self.app._update_controls()
        self.assertEqual(str(self.app.open_button.cget("state")), "normal")
        with patch.object(launcher.webbrowser, "open") as open_browser:
            self.app.open_running_url()
        open_browser.assert_called_once_with("http://127.0.0.1:30141")
        self.app._stopped()
        self.assertEqual(self.app.running_urls, [])
        self.assertEqual(str(self.app.open_button.cget("state")), "disabled")

    def test_wildcard_running_snapshot_prefers_loopback(self):
        config = launcher.default_config()
        config.update({"image_model": "gpt-image-2", "hostname": "0.0.0.0", "port": "30141"})
        with patch.object(launcher, "local_network_addresses", return_value=["192.168.1.8"]), patch.object(launcher.webbrowser, "open"):
            self.app._started(config)
        self.assertEqual(self.app.running_urls[0], "http://127.0.0.1:30141")
        self.assertNotIn("http://0.0.0.0:30141", self.app.running_urls)


if __name__ == "__main__":
    unittest.main()
