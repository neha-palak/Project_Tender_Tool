# -*- mode: python ; coding: utf-8 -*-
# Cross-platform build spec for the Tender dashboard desktop app.
#   macOS   -> dist/TenderTool.app  (via BUNDLE)  + dist/TenderTool/
#   Windows -> dist/TenderTool/     (folder with TenderTool.exe; BUNDLE is a no-op)
# Build with:  pyinstaller TenderTool.spec  --noconfirm
from PyInstaller.utils.hooks import collect_all

datas = [('Website_frontend', 'Website_frontend')]
binaries = []
hiddenimports = []

# pywebview ships platform backends + JS assets that must be pulled in explicitly.
for pkg in ('webview',):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# openpyxl is imported lazily by pandas' Excel engine, so pin it as a hidden import.
hiddenimports += ['openpyxl']

# The dashboard only reads/writes Excel via pandas — it never touches the ML /
# scraper stack. Those get dragged in transitively (transformers -> torch, etc.)
# and balloon the build to ~560MB, so exclude them explicitly. Verified safe:
# `import Website_frontend.server` pulls none of these.
excludes = [
    'torch', 'torchvision', 'torchaudio',
    'transformers', 'sentence_transformers', 'tokenizers',
    'sklearn', 'scipy', 'sympy', 'numba',
    'redis', 'playwright', 'playwright_stealth',
    'matplotlib', 'IPython', 'notebook', 'PIL',
]


a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=binaries,
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
    console=False,
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
