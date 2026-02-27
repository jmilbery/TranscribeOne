# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Find tkinterdnd2 tkdnd data files
tkdnd_datas = []
try:
    import tkinterdnd2
    tkdnd_path = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
    if os.path.isdir(tkdnd_path):
        tkdnd_datas.append((tkdnd_path, "tkinterdnd2/tkdnd"))
except ImportError:
    pass

a = Analysis(
    ["transcribeone_gui.py"],
    pathex=[],
    binaries=[],
    datas=tkdnd_datas,
    hiddenimports=[
        "assemblyai",
        "assemblyai.types",
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        "httpcore",
        "h11",
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        "certifi",
        "sniffio",
        "idna",
        "tkinterdnd2",
        "tkinterdnd2.TkinterDnD",
        "pygame",
        "pygame.mixer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "test_transcribeone",
        "_pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TranscribeOne",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TranscribeOne",
)

app = BUNDLE(
    coll,
    name="TranscribeOne.app",
    icon=None,
    bundle_identifier="com.transcribeone.app",
    info_plist={
        "CFBundleName": "TranscribeOne",
        "CFBundleDisplayName": "TranscribeOne",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Audio File",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": [
                    "public.mp3",
                    "public.wav-audio",
                    "org.xiph.flac",
                    "com.apple.m4a-audio",
                    "public.aac-audio",
                    "org.xiph.ogg",
                ],
            }
        ],
    },
)
