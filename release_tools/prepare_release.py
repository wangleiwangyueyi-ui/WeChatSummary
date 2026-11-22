"""Build an allow-listed source tree and relocatable runtime; never copy app data.

Run with the verified Python environment that contains requirements.txt.
Large media dependencies are in a separate payload; the original runtime is read-only.
"""
import argparse
import hashlib
import importlib.metadata as md
import json
import shutil
import sys
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if (ROOT/'release_tools'/'extra').is_dir():
    sys.path.insert(0,str(ROOT/'release_tools'/'extra'))
from version import VERSION, RUNTIME_VERSION

PROGRAM = '''app_info.py app_paths.py credential_ui.py credentials.py db_reader.py group_search.py
help_content.py help_ui.py ime_font.py jobs.py macos_dialogs.py macos_theme.py macos_ui.py message_parser.py
model_catalog.py motion_ui.py quota_service.py report_format.py scheduler.py secure_store.py task_control.py task_manager_ui.py
ui_extras.py usage_tracker.py voice_reader.py wechat_gui.pyw update_service.py update_ui.py version.py
initialize_offline.pyw initialize_images.pyw clear_wechat_logs.ps1'''.split()
DOCUMENTS = ['LICENSE','THIRD_PARTY.txt','requirements.txt','README.md','软件使用说明.html','软件使用说明.txt','总结模板预览.html']
ASSETS = ['assets/wechat-summary.ico']
BOOTSTRAP = ['image_key_once.py','bootstrap/__init__.py','bootstrap/common.py','bootstrap/key.py','bootstrap/LICENSE','bootstrap/NOTICE.txt']
DEVELOPMENT = ['release_tools/prepare_release.py','release_tools/installer.iss','release_tools/build_release.ps1',
               'release_tools/make_manifest.py','release_tools/publish_release.py','test_distribution.py',
               'release_tools/MODEL_LICENSE','release_tools/fetch_model.py',
               '.gitignore','.github/workflows/validate.yml','UPGRADING.md','CHANGELOG.md','assets/wechat-summary.png']
CORE = ['pycryptodome','lz4','zstandard','pillow','google-genai','requests','pystray','tzdata','customtkinter']
MEDIA = ['rapidocr-onnxruntime','pilk-nogil','sherpa-onnx','av']


def copy_file(source, destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)


def copy_tree(source,destination,ignored=()):
    for path in source.rglob('*'):
        if path.is_file() and path.suffix.lower() not in ('.pdb','.lib','.exp','.pyc','.pyo') and not any(p in ignored for p in path.relative_to(source).parts):
            copy_file(path,destination/path.relative_to(source))


def dependencies(roots):
    selected={}
    def visit(name):
        name=canonicalize_name(name)
        if name in selected:return
        dist=md.distribution(name);selected[name]=dist
        for value in dist.requires or []:
            req=Requirement(value)
            if req.marker is None or req.marker.evaluate({'extra':''}):visit(req.name)
    for name in roots:visit(name)
    return selected


def copy_distributions(selected,site,destination):
    for dist in selected.values():
        dist_root=Path(dist.locate_file('')).resolve()
        for file in dist.files or []:
            source=Path(dist.locate_file(file)).resolve()
            if not source.is_relative_to(dist_root) or not source.is_file():continue
            rel=source.relative_to(dist_root)
            if '__pycache__' in rel.parts or source.suffix in ('.pyc','.pyo'):continue
            copy_file(source,destination/rel)


def prepare(output,runtime,models,conda_packages=None):
    output=output.resolve();runtime=runtime.resolve()
    # Refuse existing output rather than cleaning arbitrary user paths.
    if output.exists():raise ValueError('Choose a new empty output directory: '+str(output))
    output.mkdir(parents=True)
    source,core,media,update=[output/name for name in ('source','setup','media','update')]
    for name in PROGRAM+DOCUMENTS+ASSETS+BOOTSTRAP+DEVELOPMENT:
        if not (ROOT/name).is_file():raise FileNotFoundError(name)
        copy_file(ROOT/name,source/name)
    for name in PROGRAM+DOCUMENTS+ASSETS+BOOTSTRAP:
        copy_file(ROOT/name,core/name)
    # Routine updates do not reinstall memory-reading initialization helpers that
    # users deliberately removed after initialization.
    for name in PROGRAM+DOCUMENTS+ASSETS:
        copy_file(ROOT/name,update/name)
    marker=json.dumps({'layout':1,'version':VERSION,'runtime_version':RUNTIME_VERSION})
    for tree in (core,update):
        (tree/'installed-mode.json').write_text(marker,encoding='utf-8')
    core_runtime=core/'runtime';core_runtime.mkdir()
    for path in runtime.iterdir():
        if path.is_file() and (path.suffix.lower() in ('.dll','.exe') or path.name.startswith('LICENSE')):
            copy_file(path,core_runtime/path.name)
    copy_tree(runtime/'DLLs',core_runtime/'DLLs',('__pycache__',))
    copy_tree(runtime/'tcl',core_runtime/'tcl')
    copy_tree(runtime/'Lib',core_runtime/'Lib',('site-packages','__pycache__','test','tests','idlelib','ensurepip'))
    # Conda CPython/Tk locates Tcl, SSL and native support libraries here.
    for name in ('bin','lib','ssl'):
        copy_tree(runtime/'Library'/name,core_runtime/'Library'/name,('pkgconfig','__pycache__'))
    copy_tree(runtime/'info'/'licenses',core_runtime/'info'/'licenses')
    copy_tree(runtime/'Library'/'share'/'licenses',core_runtime/'Library'/'share'/'licenses')
    if conda_packages:
        for package in conda_packages.iterdir():
            licenses=package/'info'/'licenses'
            if licenses.is_dir():copy_tree(licenses,core_runtime/'licenses'/package.name)
    core_deps=dependencies(CORE);all_deps=dependencies(CORE+MEDIA)
    media_deps={k:v for k,v in all_deps.items() if k not in core_deps}
    site=(runtime/'Lib'/'site-packages').resolve()
    copy_distributions(core_deps,site,core_runtime/'Lib'/'site-packages')
    copy_distributions(media_deps,site,media/'runtime'/'Lib'/'site-packages')
    for name in ('model.int8.onnx','tokens.txt','README.md'):
        copy_file(models/name,media/'models'/'sensevoice'/name)
    # The model publisher supplies an Apache license upstream; include it when
    # preparing the package instead of copying this machine's download receipt.
    model_license=ROOT/'release_tools'/'MODEL_LICENSE'
    if not model_license.is_file():raise FileNotFoundError(model_license)
    copy_file(model_license,media/'models'/'sensevoice'/'LICENSE')
    (core/'runtime-version.txt').write_text(RUNTIME_VERSION,encoding='ascii')
    (media/'media-version.txt').parent.mkdir(parents=True,exist_ok=True)
    (media/'media-version.txt').write_text(RUNTIME_VERSION,encoding='ascii')
    metadata=[]
    for name,dist in sorted(all_deps.items()):
        metadata.append({'name':name,'version':dist.version,'group':'core' if name in core_deps else 'media',
                         'license':dist.metadata.get('License-Expression') or dist.metadata.get('License',''),
                         'homepage':dist.metadata.get('Home-page','')})
    for tree in (core,source):
        (tree/'DEPENDENCIES.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        (tree/'requirements-lock.txt').write_text('\n'.join(f'{n}=={d.version}' for n,d in sorted(all_deps.items()))+'\n',encoding='utf-8')
    report={}
    for name in ('setup','update','media','source'):
        files=[p for p in (output/name).rglob('*') if p.is_file()]
        report[name]={'files':len(files),'bytes':sum(p.stat().st_size for p in files)}
    (output/'build_inventory.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runtime',type=Path,default=Path(sys.prefix))
    p.add_argument('--models',type=Path,required=True)
    p.add_argument('--conda-packages',type=Path)
    args=p.parse_args();prepare(args.output,args.runtime,args.models,args.conda_packages)
