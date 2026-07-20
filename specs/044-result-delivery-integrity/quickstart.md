# Quickstart: Result Delivery Integrity

## Prerequisites

From a Windows terminal confirm WSL readiness, then use the canonical entry point only:

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

## Focused validation

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_generation.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_late_phases_finalize_gate_persistence.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_processing_runtime.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_ui.py -vv
```

Expected: all marker-mode fallback classes are marker-free; accepted/warn results keep normal UI; blocked results never show success or emit accepted artifact signals.

## Final proof

Use existing VS Code tasks `Run Current Test File` for focused files and `Run Full Pytest` after focused selectors pass. Verify `git diff --check` and confirm no blocked result created a `.run/ui_results/*.result.*` group.
