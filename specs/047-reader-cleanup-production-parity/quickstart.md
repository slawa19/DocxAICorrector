# Quickstart: Reader Cleanup Production Parity

## Dependency gate

Do not implement or validate this feature until focused tests for specs 044 and 048 pass. In particular, final diagnostics must already be run/source-owned; no mtime compatibility path is accepted.

## Focused canonical validation

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_config.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_app_preparation.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_document_pipeline.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_late_phases_finalize_gate_persistence.py -vv
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_reader_cleanup_mvp.py -vv
```

Expected: default/non-translation runs skip cleanup; enabled UI translation runs execute it; final verdict uses owned final evidence; stop prevents subsequent late work; cleanup/narration advisories persist; translation narration matches final accepted text.

## Standalone audiobook counter-proof

Run the existing standalone audiobook selectors in their current test files through `scripts/test.sh`. They must show unchanged narration source, no cleanup projection, and no new omission/warning behavior.

## Final proof

Use VS Code `Run Current Test File` for focused files, then `Run Full Pytest`. Run `git diff --check`; inspect accepted `.run/ui_results/` artifacts and structured logs only from a fresh post-fix run.
