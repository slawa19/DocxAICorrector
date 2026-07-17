"""Spec 025 / A2 — the built wheel is importable outside a checkout.

Opt-in (needs a build toolchain + venv). Builds the wheel, installs it --no-deps
into a fresh venv, and imports the package from a directory OUTSIDE the repo so
the packaged resources (prompts + default config) must come from the wheel, not
from a repo checkout on the path. Guards against regressing the A2 install
contract (e.g. dropping package-data or reintroducing resolve_repo_root at
import time for resources).
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.system_deps]

REPO_ROOT = Path(__file__).resolve().parents[1]

# Importing only docxaicorrector.core.constants needs stdlib alone, so --no-deps
# keeps this offline and fast while still proving resources ship in the wheel.
_IMPORT_PROBE = (
    "from docxaicorrector.core import constants as c; "
    "assert c.CONFIG_PATH.exists(), c.CONFIG_PATH; "
    "assert c.SYSTEM_PROMPT_PATH.exists(), c.SYSTEM_PROMPT_PATH; "
    "assert c.PROMPTS_DIR.is_dir(), c.PROMPTS_DIR; "
    "print('OK', c.CONFIG_PATH)"
)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="wheel requires Python >=3.12")
def test_wheel_imports_and_resources_resolve_outside_checkout(tmp_path):
    try:
        import build  # noqa: F401
    except ImportError:
        pytest.skip("`build` not installed; wheel smoke test is opt-in")

    wheel_dir = tmp_path / "wheel"
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir), str(REPO_ROOT)],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        pytest.skip(f"wheel build unavailable in this environment:\n{build.stderr[-800:]}")

    wheels = list(wheel_dir.glob("*.whl"))
    assert wheels, "no wheel produced"

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    venv_python = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python"
    )

    install = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", "-q", str(wheels[0])],
        capture_output=True, text=True,
    )
    assert install.returncode == 0, f"install failed:\n{install.stderr[-800:]}"

    # Run from tmp_path (outside the repo) so resources cannot come from a checkout.
    probe = subprocess.run(
        [str(venv_python), "-c", _IMPORT_PROBE],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert probe.returncode == 0, f"import from installed wheel failed:\n{probe.stderr[-800:]}"
    assert "OK" in probe.stdout
