"""Explicit active-run selection; ordinary status commands remain read-only."""
from pathlib import Path
import json,re,sys
from .project import dump


def resolve(base,run=None):
    base=Path(base).resolve();saved=base/'.local/unit9-active-run.json'
    if run is None and saved.exists():
        try:
            data=json.loads(saved.read_text())
            if not isinstance(data,dict) or data.get('schemaVersion')!=1:raise ValueError('Unsupported active run record')
            run=data['run']
        except (OSError,ValueError,TypeError,KeyError) as error:raise ValueError('Unreadable active run; use motion-use default or select an existing run') from error
    if run is None or run=='default':return base/'examples/unit-9-motion.json'
    if not isinstance(run,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',run):raise ValueError('Use a run name containing only letters, numbers, - or _')
    runs=base/'output/unit-9-motion-handled';folder=runs/run;config=folder/'production.json'
    if folder.resolve().parent!=runs.resolve() or config.resolve().parent!=folder.resolve():raise ValueError('Named run must remain inside output/unit-9-motion-handled')
    if not config.is_file():raise ValueError('No production.json for run '+run)
    data=json.loads(config.read_text())
    if not isinstance(data,dict):raise ValueError('Named run configuration must be an object')
    root=(config.parent/data.get('root','.')).resolve();output=(root/data.get('output','production')).resolve()
    if data.get('renderer')!='motion-canvas' or root!=(base/'examples/unit-9-motion').resolve() or output!=folder.resolve():
        raise ValueError('Named run must be a native Unit 9 configuration whose output is its run folder')
    return config.resolve()


def select(base,run):
    config=resolve(base,run)
    dump(Path(base)/'.local/unit9-active-run.json',{'schemaVersion':1,'run':None if run=='default' else run})
    return config


if __name__=='__main__':
    try:
        mode,base,*rest=sys.argv[1:]
        if mode=='use':
            if len(rest)!=1:raise ValueError('Choose motion-use RUN or motion-use default')
            print(select(base,rest[0]))
        elif mode=='config':print(resolve(base,rest[0] if rest else None))
        else:raise ValueError('Choose use or config')
    except (ValueError,OSError,TypeError,KeyError) as error:raise SystemExit('unit9: '+' '.join(str(error).split()))
