"""
sub-egress version declaration.
Reads version dynamically from pyproject.toml as the Single Source of Truth (SSOT).
"""
import tomllib
from importlib.metadata import version
from pathlib import Path


def _load_version() -> str:
    # Search parent directories for pyproject.toml
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            with candidate.open("rb") as project_file:
                project = tomllib.load(project_file).get("project", {})
            if project.get("name") == "sub-egress":
                return project["version"]
    return version("sub-egress")

VERSION = _load_version()
