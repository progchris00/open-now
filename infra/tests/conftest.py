from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative_path: str) -> ModuleType:
    """Load a standalone script from the repository as a module."""
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"{relative_path} has not been written yet"

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_file(relative_path: str) -> str:
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"{relative_path} has not been written yet"
    return path.read_text()
