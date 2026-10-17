"""Versioned identity of configured sources, render settings, and local tools.

Project drivers may execute arbitrary code. Files outside the default source
trees must be declared with source_files/source_globs; no import guesser can
discover every dynamic file read. Dependency locks and installed versions are
recorded, rather than claiming to attest every byte of a runtime installation.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys

from .project import FRAMEWORK, binary, sha

BUILD_SCHEMA = 2
DEFAULT_GLOBS = ['src/**/*', 'assets/**/*', 'data/**/*']
IGNORED = {'node_modules', '__pycache__', '.vite', '.git', '.venv', '.sbph'}
NON_RENDER_SETTINGS = {'root','edit','audio','driver','output','deliver_root',
    'delivery','master','reference','timeline_file','proof_start','proof_duration','verification'}


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def tool_identity(name):
    path=Path(binary(name)).resolve();stat=path.stat()
    # Flag selection depends on the tool, not the executable's filename (which
    # may be an override or a versioned FFmpeg binary).
    return _named_tool_identity(name,str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


@lru_cache(maxsize=32)
def _named_tool_identity(name,path,size,mtime,ctime):
    flag='-version' if name in {'ffmpeg','ffprobe'} else '--version'
    version=subprocess.check_output([path,flag],stderr=subprocess.STDOUT,text=True).splitlines()[0]
    return {'path':path,'sha256':sha(path),'version':version}


@lru_cache(maxsize=8)
def _sharp_identity(node, node_hash, runtime_hash, module_path, package_hash):
    script="const r=require('./render/runtime.cjs');console.log(JSON.stringify(r.sharp.versions));"
    return json.loads(subprocess.check_output([node,'-e',script],cwd=FRAMEWORK,text=True))


def runtime_identity():
    tools={name:tool_identity(name) for name in ['node','ffmpeg','ffprobe']}
    names=[line.split('==')[0] for line in (FRAMEWORK/'requirements.lock').read_text().splitlines() if '==' in line]
    versions={}
    for name in names:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    packages={}
    lock=json.loads((FRAMEWORK/'package-lock.json').read_text())
    for relative in sorted(lock.get('packages',{})):
        if not relative:continue
        file=FRAMEWORK/relative/'package.json'
        packages[relative]=sha(file) if file.is_file() else None
    return {
        'tools':tools,'python':{'executable':str(Path(sys.executable).resolve()),'version':sys.version,'packages':versions},
        'nodePackages':packages,
        'sharp':_sharp_identity(tools['node']['path'],tools['node']['sha256'],sha(FRAMEWORK/'render/runtime.cjs'),os.environ.get('SBPH_NODE_MODULES'),digest(packages)),
        'environment':{key:os.environ.get(key) for key in ['SBPH_NODE_MODULES','UNIT9_NODE_MODULES','NODE_PATH','NODE_OPTIONS']},
    }


@lru_cache(maxsize=8)
def _browser_file(path,size,mtime,ctime):
    return {'path':path,'sha256':sha(path)}


def browser_identity():
    """Locate the launcher's browser and hash it without starting a browser."""
    candidate=os.environ.get('SBPH_CHROMIUM')
    if not candidate:
        script="console.log(require('playwright-core').chromium.executablePath())"
        candidate=subprocess.check_output([binary('node'),'-e',script],cwd=FRAMEWORK,text=True).strip()
        if not Path(candidate).is_file():candidate='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    file=Path(candidate).resolve()
    if not file.is_file():raise ValueError('No Chromium found; set SBPH_CHROMIUM. No browser was launched.')
    stat=file.stat()
    return _browser_file(str(file),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


def build_inventory(p):
    from .shot_backend import backend, motion_projects
    renderer=backend(p)
    paths={p.audio,(p.root/p.data.get('edit','data/edit.json')).resolve()}
    if renderer=='svg':paths.add(p.driver)
    else:
        for project in motion_projects(p).values():
            paths.update(f.resolve() for f in project.parent.rglob('*') if f.is_file()
                and not IGNORED.intersection(f.relative_to(project.parent).parts)
                and not f.resolve().is_relative_to(p.output))
    for pattern in p.data.get('source_globs',DEFAULT_GLOBS):
        paths.update(f.resolve() for f in p.root.glob(pattern) if f.is_file() and not IGNORED.intersection(f.relative_to(p.root).parts))
    for name in p.data.get('source_files',[]):
        file=(p.root/name).resolve()
        if not file.is_file():raise ValueError('Declared source is missing: '+str(file))
        paths.add(file)
    def label(file):
        try:return file.relative_to(p.root).as_posix()
        except ValueError:return 'external:'+str(file)
    inventory=[{'file':label(f),'sha256':sha(f)} for f in sorted(paths)]
    framework_files=list((FRAMEWORK/'src/sbph').glob('*.py'))+list((FRAMEWORK/'render').glob('*.cjs'))
    framework_files += [FRAMEWORK/name for name in ['package.json','package-lock.json','pyproject.toml','requirements.lock']]
    if renderer=='motion-canvas':framework_files += list((FRAMEWORK/'motion-canvas').glob('*.*'))
    inventory += [{'file':'framework:'+f.relative_to(FRAMEWORK).as_posix(),'sha256':sha(f)} for f in sorted(framework_files)]
    spec={
        'schema':BUILD_SCHEMA,'backend':renderer+'-shots',
        'settings':{key:value for key,value in p.data.items() if key not in NON_RENDER_SETTINGS},
        'driver':label(p.driver) if renderer=='svg' else None,'edit':label((p.root/p.data.get('edit','data/edit.json')).resolve()),'audio':label(p.audio),
        'fps':p.fps,'width':p.width,'height':p.height,'frames':p.frames,'handles':p.handles,
        'runtime':runtime_identity(),
    }
    if renderer=='motion-canvas':spec['browser']=browser_identity()
    inventory.append({'file':'build:specification','sha256':digest(spec),'specification':spec})
    return digest(inventory),inventory
