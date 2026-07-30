# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import pydicom
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

pydicom_dir = os.path.dirname(pydicom.__file__)
site_packages_dir = os.path.dirname(pydicom_dir)

pydicom_subs = collect_submodules('pydicom')
pydicom_datas = collect_data_files('pydicom')

fastapi_subs = collect_submodules('fastapi')
fastapi_datas = collect_data_files('fastapi')

uvicorn_subs = collect_submodules('uvicorn')
uvicorn_datas = collect_data_files('uvicorn')

starlette_subs = collect_submodules('starlette')
starlette_datas = collect_data_files('starlette')

pydantic_subs = collect_submodules('pydantic')
pydantic_datas = collect_data_files('pydantic')

webview_subs = collect_submodules('webview')
webview_datas = collect_data_files('webview')

added_files = [
    ('static', 'static'),
    ('sample_data', 'sample_data'),
    ('Test Images', 'Test Images'),
    (pydicom_dir, 'pydicom')
] + pydicom_datas + fastapi_datas + uvicorn_datas + starlette_datas + pydantic_datas + webview_datas

all_hiddenimports = list(set([
    'pydicom',
    'pydicom.encoders',
    'pydicom.pixel_data_handlers',
    'pydicom.pixel_data_handlers.numpy_handler',
    'pydicom.pixel_data_handlers.pillow_handler',
    'pydicom.pixel_data_handlers.rle_handler',
    'pydicom.datadict',
    'pydicom.dataset',
    'pydicom.sequence',
    'pydicom.tag',
    'pydicom.uid',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'scipy.spatial.transform._rotation_groups',
    'scipy.special.cython_special',
    'scipy.ndimage',
    'PIL.Image',
    'tkinter',
    'tkinter.filedialog',
    'webview',
    'app',
    'app.main',
    'app.dicom_loader',
    'app.dicom_parser',
    'app.analysis_engine',
    'app.comparator',
    'app.simulator',
    'app.qc_report',
    'app.gravity_engine'
] + pydicom_subs + fastapi_subs + uvicorn_subs + starlette_subs + pydantic_subs + webview_subs))

a = Analysis(
    ['run.py'],
    pathex=['.', site_packages_dir],
    binaries=[],
    datas=added_files,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pillow_avif', 'PIL._avif', 'pillow_avif._avif'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InspectMLC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='InspectMLC'
)
