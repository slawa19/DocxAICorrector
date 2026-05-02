from pathlib import Path
from importlib import import_module
import sys as _sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

_TARGET = "docxaicorrector.ui._app"


def _load_target_module():
    module = import_module(_TARGET)
    _sys.modules.setdefault("app", module)
    return module

if __name__ == "__main__":
    _load_target_module().main()
else:
    _target = _load_target_module()
    _sys.modules[__name__] = _target
