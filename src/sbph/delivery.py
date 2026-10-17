"""Resolve artifact roles without film names or implicit self-comparisons."""
from pathlib import Path


def delivery_path(p, override=None):
    name=override or p.data.get('delivery') or p.data.get('master')
    return (p.root/Path(name)).resolve() if name else (p.output/'assembly.mp4').resolve()


def reference_path(p, override=None):
    name=override or p.data.get('reference') or p.data.get('master')
    if not name:
        raise ValueError('Conform requires an explicit reference movie: set reference or use --reference')
    reference=(p.root/Path(name)).resolve()
    assembly=(p.output/'assembly.mp4').resolve()
    if reference==assembly or (reference.is_file() and assembly.is_file() and reference.samefile(assembly)):
        raise ValueError('Conform reference must be a separate movie from the assembly')
    if not reference.is_file():raise ValueError('Conform reference is missing: '+str(reference))
    return reference
