# -*- mode: python ; coding: utf-8 -*-
# Build spec for the Tender dashboard. It launches Flask and opens the default
# browser (no bundled webview). One-DIR build for fast startup (a one-file build
# re-extracts on every launch and takes ~20s+ before the server is ready):
#   macOS   -> dist/TenderTool.app   (single double-clickable icon; the folder
#                                      payload is hidden inside the bundle)
#   Windows -> dist/TenderTool/       (folder with TenderTool.exe + _internal;
#                                      BUNDLE is a no-op on Windows)
# Data (all_tenders_pipeline.xlsx + saved_<name>.xlsx) lives NEXT TO the app on
# macOS, or inside the TenderTool folder on Windows — point that at Google Drive.
# Build with:  pyinstaller TenderTool.spec --noconfirm
import sys

datas = [('Website_frontend', 'Website_frontend')]
hiddenimports = ['openpyxl']

# The dashboard only reads/writes Excel via pandas — it never touches the ML /
# scraper stack, which gets pulled in transitively and would balloon the build.
# Also drop pywebview: we open the system browser instead of a native window.
excludes = [
    'torch', 'torchvision', 'torchaudio',
    'transformers', 'sentence_transformers', 'tokenizers',
    'sklearn', 'scipy', 'sympy', 'numba',
    'redis', 'playwright', 'playwright_stealth',
    'matplotlib', 'IPython', 'notebook', 'PIL',
    'webview',
]

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Keep a console window on Windows so closing it stops the background server.
# The macOS .app is windowless and is quit from the Dock.
_console = sys.platform.startswith('win')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TenderTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TenderTool',
)
app = BUNDLE(
    coll,
    name='TenderTool.app',
    icon=None,
    bundle_identifier='in.sensio.tendertool',
)
