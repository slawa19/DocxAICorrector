"""Compatibility wrapper for the migrated CLI-capable module."""

from importlib import import_module
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_TARGET = "docxaicorrector.validation.structural"

if __name__ == "__main__":
    from docxaicorrector.validation.structural import main

    raise SystemExit(main())

_target = import_module(_TARGET)
sys.modules[__name__] = _target
