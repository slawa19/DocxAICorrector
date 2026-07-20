# Quickstart: Stable Source and Preparation Identity

## Prerequisites

Confirm WSL/Debian and the actual Linux venv, plus LibreOffice before any real PDF/DOC exercise.

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash -lc "uname; pwd; test -f .venv/bin/activate; command -v soffice || command -v libreoffice; echo READY"
```

## Focused validation

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_processing_runtime.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_restart_store.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_application_flow.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_app_restartable_state.py -vv
```

Expected: PDF/DOC persist/restore retains original token, verifies normalized bytes, performs zero reconversions; corrupted/legacy records are unavailable; a fresh upload recovers in the same application process; language-pair changes produce new UI preparation markers.

## Final proof

Use VS Code `Run Current Test File` for focused proof, then `Run Full Pytest`. Run `git diff --check`. For a manual PDF smoke, verify LibreOffice availability and that `.run/completed_*` is treated only as cached source.
