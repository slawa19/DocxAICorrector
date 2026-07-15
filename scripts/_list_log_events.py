"""Utility: enumerate log_event/log_exception event names by scanning source."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "src/docxaicorrector/ui/_app.py",
    "src/docxaicorrector/core/config.py",
    "src/docxaicorrector/core/logger.py",
    "src/docxaicorrector/document/layout_cleanup.py",
    "src/docxaicorrector/generation/_generation.py",
    "src/docxaicorrector/generation/formatting_restoration.py",
    "src/docxaicorrector/generation/formatting_transfer.py",
    "src/docxaicorrector/image/analysis.py",
    "src/docxaicorrector/image/generation.py",
    "src/docxaicorrector/image/pipeline.py",
    "src/docxaicorrector/image/reconstruction.py",
    "src/docxaicorrector/image/reinsertion.py",
    "src/docxaicorrector/image/validation.py",
    "src/docxaicorrector/pipeline/_pipeline.py",
    "src/docxaicorrector/pipeline/block_execution.py",
    "src/docxaicorrector/pipeline/block_failures.py",
    "src/docxaicorrector/pipeline/late_phases.py",
    "src/docxaicorrector/pipeline/narration_postprocess.py",
    "src/docxaicorrector/pipeline/reader_cleanup_postprocess.py",
    "src/docxaicorrector/pipeline/reader_cleanup_rebuild.py",
    "src/docxaicorrector/pipeline/setup.py",
    "src/docxaicorrector/pipeline/terminal_results.py",
    "src/docxaicorrector/processing/preparation.py",
    "src/docxaicorrector/processing/processing_runtime.py",
    "src/docxaicorrector/processing/processing_service.py",
    "src/docxaicorrector/runtime/artifact_retention.py",
    "src/docxaicorrector/runtime/state.py",
    "src/docxaicorrector/ui/application_flow.py",
    "src/docxaicorrector/validation/structural.py",
]

EVENT_RE = re.compile(r'log_event\s*\(\s*(?:[^,]+),\s*"([a-zA-Z0-9_]+)"')
EXC_RE = re.compile(r'log_exception\s*\(\s*"([a-zA-Z0-9_]+)"')
FAIL_RE = re.compile(r'fail_critical\s*\(\s*"([a-zA-Z0-9_]+)"')
PRESENT_RE = re.compile(r'present_error\s*\(\s*"([a-zA-Z0-9_]+)"')

found: dict[str, set[str]] = {}
for relative_path in TARGETS:
    file_path = ROOT / relative_path
    if not file_path.exists():
        continue
    text = file_path.read_text(encoding="utf-8")
    for regex in (EVENT_RE, EXC_RE, FAIL_RE, PRESENT_RE):
        for match in regex.finditer(text):
            found.setdefault(match.group(1), set()).add(relative_path)

for event in sorted(found):
    print(f"{event}\t{','.join(sorted(found[event]))}")
