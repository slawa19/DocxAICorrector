from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PACKAGE_ROOT = REPO_ROOT / "src" / "docxaicorrector"
PACKAGE_MANIFEST_PATH = SRC_PACKAGE_ROOT / "real_image" / "manifest.py"


def _run_without_pythonpath(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_repo_root_import_bootstraps_src_package_without_pythonpath() -> None:
    result = _run_without_pythonpath(
        "-c",
        (
            "import json; "
            "from pathlib import Path; "
            "import docxaicorrector; "
            "import docxaicorrector.real_image.manifest as manifest; "
            "print(json.dumps({"
            "'package_path': docxaicorrector.__path__[0], "
            "'manifest_file': str(Path(manifest.__file__).resolve())"
            "}))"
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)

    assert Path(payload["package_path"]).resolve() == SRC_PACKAGE_ROOT
    assert Path(payload["manifest_file"]).resolve() == PACKAGE_MANIFEST_PATH


def test_repo_root_module_execution_bootstraps_src_package_without_pythonpath() -> None:
    result = _run_without_pythonpath("-m", "docxaicorrector.real_image.manifest", "--help")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()
