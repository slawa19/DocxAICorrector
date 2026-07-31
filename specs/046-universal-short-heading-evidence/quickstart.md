# Quickstart: Universal Short-Heading Evidence

## Focused canonical validation

```powershell
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh tests/test_document_extraction.py -vv
```

If a dedicated role test file exists after implementation, run it through the same entry point. Expected:

- no-signal one-to-four-word body controls remain body in both modes;
- explicit and form-backed short headings remain headings;
- matched no-form controls remain body;
- authoritative body/attribution protections remain green.
- instrumentation confirms zero additional external calls or preparation stages for the focused documents.

## Final proof

Use VS Code `Run Current Test File`, then `Run Full Pytest`; run `git diff --check`. Do not use a real-document failure report as proof unless it postdates the fix and satisfies the repository evidence contract.
