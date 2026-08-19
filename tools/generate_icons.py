"""Generate Windows tray icon states from preserved source artwork."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "source"
OUTPUT_DIR = ROOT / "assets" / "icons"
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
STATE_COLORS = {
    "running": (34, 197, 94),
    "busy": (234, 179, 8),
    "error": (239, 68, 68),
}
STATUS_DOT_DIAMETER_RATIO = 88 / 256
STATUS_DOT_MARGIN_RATIO = 7 / 256


def status_icon(idle: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Draw a prominent antialiased status dot without modifying source artwork."""
    result = idle.convert("RGBA").copy()
    diameter = round(min(result.size) * STATUS_DOT_DIAMETER_RATIO)
    margin = round(min(result.size) * STATUS_DOT_MARGIN_RATIO)
    box = (
        result.width - margin - diameter,
        result.height - margin - diameter,
        result.width - margin,
        result.height - margin,
    )
    ImageDraw.Draw(result).ellipse(box, fill=(*color, 255))
    return result


def write_icon(name: str, image: Image.Image) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_DIR / f"{name}.ico", format="ICO", sizes=SIZES)


def main() -> None:
    idle = Image.open(SOURCE_DIR / "pi-web-launcher.ico").convert("RGBA")
    write_icon("idle", idle)
    for name, color in STATE_COLORS.items():
        write_icon(name, status_icon(idle, color))


if __name__ == "__main__":
    main()
