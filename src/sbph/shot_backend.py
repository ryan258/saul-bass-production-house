"""Explicit shot renderer selection; existing SVG configurations keep their contract."""
from .project import sha
from .fingerprint import digest


def backend(p):
    name=p.data.get('renderer','svg')
    if not isinstance(name,str) or name not in {'svg','motion-canvas'}:raise ValueError('renderer must be svg or motion-canvas')
    return name


def motion_projects(p):
    mapping=p.data.get('motion_shots')
    if not isinstance(mapping,dict) or set(mapping)!={s['id'] for s in p.edit['scenes']}:
        raise ValueError('motion_shots must map every shot ID to a project.ts or explicit project window')
    result={}
    for key,value in mapping.items():
        if isinstance(value,dict):
            if set(value)!={'project','startFrame'} or type(value['startFrame']) is not int or value['startFrame']<0:
                raise ValueError('Motion window requires project and nonnegative integer startFrame')
            value=value['project']
        if not isinstance(value,str):raise ValueError('Motion shot project must be a path')
        file=(p.root/value).resolve()
        if not file.is_file() or file.name!='project.ts':raise ValueError('Missing Motion Canvas project.ts: '+str(file))
        if file.parent==p.root or p.output.is_relative_to(file.parent) or file.is_relative_to(p.output):
            raise ValueError('Keep isolated Motion shot sources in a separate folder outside production output')
        result[key]=file
    for key,file in result.items():
        if sum(other==file for other in result.values())>1 and not isinstance(mapping[key],dict):
            raise ValueError('Shared Motion projects require explicit startFrame windows for every shot')
    return result


def motion_start(p,identifier):
    value=p.data['motion_shots'][identifier]
    return value['startFrame'] if isinstance(value,dict) else 0


def renderer_record(p):
    if backend(p)=='svg':return {'sourceDriverSha256':sha(p.driver)}
    return {'renderer':'motion-canvas','sourceRendererSha256':digest({key:sha(file) for key,file in motion_projects(p).items()})}
