# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller --onedir Windows build specification for T-Notes."""

from pathlib import Path
from PIL import Image
import PySide6
from PySide6.QtCore import QLibraryInfo
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve()
BUILD_DIR = PROJECT_ROOT / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

# Generate multi-resolution Windows .ico from bundled app_icon.png
PNG_ICON = PROJECT_ROOT / "assets" / "icons" / "app_icon.png"
ICO_ICON = BUILD_DIR / "app_icon.ico"
if PNG_ICON.is_file():
    with Image.open(PNG_ICON) as img:
        img.convert("RGBA").save(
            ICO_ICON,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )

# Synchronize assets/m365_synthetic with assets/m365 before bundling so runtime needs zero writes
synth_src_dir = PROJECT_ROOT / "assets" / "m365"
synth_dst_dir = PROJECT_ROOT / "assets" / "m365_synthetic"
synth_dst_dir.mkdir(parents=True, exist_ok=True)
for src_name, dst_name in (
    ("categories.json", "categories.json"),
    ("contract-review-pins.json", "contract-review-pins.json"),
    ("synthetic-catalog.json", "catalog.json"),
):
    src_file = synth_src_dir / src_name
    dst_file = synth_dst_dir / dst_name
    if src_file.is_file() and (not dst_file.exists() or dst_file.read_bytes() != src_file.read_bytes()):
        dst_file.write_bytes(src_file.read_bytes())

datas = [
    (str(PROJECT_ROOT / "src" / "database" / "schema.sql"), "src/database"),
    (str(PROJECT_ROOT / "assets" / "styles" / "dark_theme.qss"), "assets/styles"),
    (str(PROJECT_ROOT / "assets" / "icons" / "app_icon.png"), "assets/icons"),
    (str(PROJECT_ROOT / "assets" / "m365"), "assets/m365"),
    (str(PROJECT_ROOT / "assets" / "m365_synthetic"), "assets/m365_synthetic"),
    (str(PROJECT_ROOT / "docs" / "contracts" / "m365" / "schemas"), "docs/contracts/m365/schemas"),
    (str(PROJECT_ROOT / "prototypes" / "m365_official_engine" / "protocol.ps1"), "prototypes/m365_official_engine"),
]

# Recursively include scripts/m365 (host helpers, all 25 operation .ps1 scripts, manifests, fixtures)
scripts_root = PROJECT_ROOT / "scripts" / "m365"
for item in scripts_root.rglob("*"):
    if not item.is_file():
        continue
    rel = item.relative_to(scripts_root)
    if "__pycache__" in rel.parts or rel.parts[0] == "tooling" or item.suffix.lower() in {".pyc", ".log"}:
        continue
    dest_dir = (Path("scripts/m365") / rel.parent).as_posix()
    datas.append((str(item), dest_dir))

# Collect Draft 2020-12 metaschema JSON resources shipped inside jsonschema_specifications
datas += collect_data_files("jsonschema_specifications")

# Explicitly bundle PySide6 Qt plugins required for inline JPEG/PNG/ICO/SVG images and Windows styling
qt_plugins_root = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath))
if not qt_plugins_root.is_dir():
    qt_plugins_root = Path(PySide6.__file__).resolve().parent / "plugins"

binaries = []
for plugin_subdir in ("imageformats", "platforms", "styles", "iconengines"):
    src_subdir = qt_plugins_root / plugin_subdir
    if src_subdir.is_dir():
        for dll in src_subdir.glob("*.dll"):
            binaries.append((str(dll), f"PySide6/plugins/{plugin_subdir}"))

hiddenimports = (
    collect_submodules("src")
    + [
        "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin",
        "PIL.BmpImagePlugin",
        "PIL.GifImagePlugin",
        "PIL.WebPImagePlugin",
        "PIL.IcoImagePlugin",
        "PIL.TiffImagePlugin",
        "jsonschema",
        "jsonschema_specifications",
        "referencing",
        "sqlite3",
        "winreg",
        "ctypes.wintypes",
        "PySide6.QtSvg",
    ]
)

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "tkinter", "matplotlib", "numpy", "scipy"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="T-Notes",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICO_ICON) if ICO_ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="T-Notes",
)
