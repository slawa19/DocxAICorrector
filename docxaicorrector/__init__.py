"""Repository bootstrap package for src/docxaicorrector.

This keeps plain `python -m docxaicorrector...` working from the repository
root during the staged migration without relying on editable install or an
externally exported `PYTHONPATH`.
"""

from pathlib import Path


_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "docxaicorrector"
if not _SRC_PACKAGE.is_dir():
    raise ImportError(f"Missing src package directory: {_SRC_PACKAGE}")

__path__ = [str(_SRC_PACKAGE)]
__all__ = []
