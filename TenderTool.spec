# -*- mode: python ; coding: utf-8 -*-
# Build spec for the Tender dashboard. It launches Flask and opens the default
# browser (no bundled webview). Single-file output so it drops cleanly next to the
# shared data in one folder:
#   macOS   -> dist/TenderTool.app   (double-clickable bundle; quit from the Dock)
#   Windows -> dist/TenderTool.exe   (BUNDLE is a no-op on Windows; close the
#                                     console window to stop it)
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
    a.binaries,
    a.datas,
    [],
    name='TenderTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
app = BUNDLE(
    exe,
    name='TenderTool.app',
    icon=None,
    bundle_identifier='in.sensio.tendertool',
)
