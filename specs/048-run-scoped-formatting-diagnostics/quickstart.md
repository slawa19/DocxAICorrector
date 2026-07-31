# Quickstart: Run-Scoped Formatting Diagnostics

## Focused canonical validation

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_format_restoration.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_late_phases_finalize_gate_persistence.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_processing_runtime.py::test_processing_admission_gate_caps_concurrency -vv -x
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_structural_validation_characterization.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_pipeline_validation.py -vv
```

Expected: overlapping run A/B collect only owned paths; live marker diagnostics carry ownership; a clean run stays empty; same-source reruns isolate; repeated same-stage writes do not overwrite; retention remains family-wide; structural/real-document validation uses explicit offline paths and never mtime ownership.

## Artifact inspection

Inspect `.run/formatting_diagnostics/` only after tests that create isolated temp roots or explicitly documented manual runs. Verify every surfaced path exists and its ownership envelope matches the event/report run and source. Legacy unscoped files must be replayable only by explicit selection.

## Final proof

Use VS Code `Run Current Test File`, then `Run Full Pytest`; run `git diff --check`. Do not begin spec 047 implementation until this focused ownership contract passes.
