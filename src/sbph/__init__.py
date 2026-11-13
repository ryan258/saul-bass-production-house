"""Saul Bass Production House: local media assembly and editable timeline interchange."""
from pathlib import Path
import tomllib

__version__=tomllib.loads((Path(__file__).resolve().parents[2]/'pyproject.toml').read_text())['project']['version']
