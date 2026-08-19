# Icon source artwork

These two ICO files are preserved user-provided source artwork:

- `pi-web-launcher.ico`: idle/application artwork and the base for generated resources.
- `pi-web-launcher-on.ico`: the original status-dot artwork, retained unchanged for reference.

`tools/generate_icons.py` does not modify either source file. It creates the standard multi-size runtime resources in `assets/icons/`: `idle.ico`, `running.ico`, `busy.ico`, and `error.ico`. The latter three add prominent green, yellow, and red status dots to the base artwork.
