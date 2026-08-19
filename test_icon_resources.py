import unittest
from pathlib import Path

from PIL import Image


class IconResourceTests(unittest.TestCase):
    def test_all_generated_icons_are_transparent_multi_size_ico(self):
        icon_directory = Path(__file__).resolve().parent / "assets" / "icons"
        required_sizes = {(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (256, 256)}
        for state in ("idle", "running", "busy", "error"):
            path = icon_directory / f"{state}.ico"
            with self.subTest(state=state):
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertTrue(required_sizes.issubset(image.info.get("sizes", set())))
                    largest = image.ico.getimage((256, 256)).convert("RGBA")
                    self.assertEqual(largest.getchannel("A").getextrema()[0], 0)

    @unittest.skipUnless(__import__("sys").platform == "win32", "Windows icon API is required")
    def test_generated_icons_load_with_windows_api(self):
        import win32con
        import win32gui

        icon_directory = Path(__file__).resolve().parent / "assets" / "icons"
        for state in ("idle", "running", "busy", "error"):
            path = (icon_directory / f"{state}.ico").resolve()
            with self.subTest(state=state):
                handle = win32gui.LoadImage(
                    0,
                    str(path),
                    win32con.IMAGE_ICON,
                    0,
                    0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
                self.assertTrue(handle)
                win32gui.DestroyIcon(handle)

    def test_status_dots_are_prominent_at_tray_and_large_sizes(self):
        icon_directory = Path(__file__).resolve().parent / "assets" / "icons"
        colors = {
            "running": (34, 197, 94),
            "busy": (234, 179, 8),
            "error": (239, 68, 68),
        }
        for state, expected in colors.items():
            with self.subTest(state=state), Image.open(icon_directory / f"{state}.ico") as image:
                for size, minimum_span in (((256, 256), 86), ((16, 16), 5)):
                    layer = image.ico.getimage(size).convert("RGBA")
                    points = []
                    for y in range(layer.height // 2, layer.height):
                        for x in range(layer.width // 2, layer.width):
                            red, green, blue, alpha = layer.getpixel((x, y))
                            distance = sum(abs(actual - target) for actual, target in zip((red, green, blue), expected))
                            if alpha > 128 and distance < 90:
                                points.append((x, y))
                    self.assertTrue(points)
                    span = max(x for x, _y in points) - min(x for x, _y in points) + 1
                    self.assertGreaterEqual(span, minimum_span)

    def test_source_artwork_and_generated_resources_are_separate(self):
        root = Path(__file__).resolve().parent / "assets"
        self.assertTrue((root / "source" / "pi-web-launcher.ico").is_file())
        self.assertTrue((root / "source" / "pi-web-launcher-on.ico").is_file())
        self.assertNotEqual(
            (root / "source" / "pi-web-launcher-on.ico").resolve(),
            (root / "icons" / "running.ico").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
