"""Compatibility alias for the migrated implementation module."""

from importlib import import_module
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_target = import_module("docxaicorrector.image.validation")
sys.modules[__name__] = _target
