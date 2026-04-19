"""Utility: enumerate log_event/log_exception event names by scanning source."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "app.py",
    "preparation.py",
    "document_pipeline.py",
    "image_generation.py",
    "image_validation.py",
    "image_reconstruction.py",
    "image_reinsertion.py",
    "image_analysis.py",
    "image_pipeline.py",
    "generation.py",
    "config.py",
    "formatting_transfer.py",
    "processing_runtime.py",
    "processing_service.py",
    "state.py",
    "application_flow.py",
    "logger.py",
]

EVENT_RE = re.compile(r'log_event\s*\(\s*(?:[^,]+),\s*"([a-zA-Z0-9_]+)"')
EXC_RE = re.compile(r'log_exception\s*\(\s*"([a-zA-Z0-9_]+)"')
FAIL_RE = re.compile(r'fail_critical\s*\(\s*"([a-zA-Z0-9_]+)"')
PRESENT_RE = re.compile(r'present_error\s*\(\s*"([a-zA-Z0-9_]+)"')

found: dict[str, set[str]] = {}
for name in TARGETS:
    file_path = ROOT / name
    if not file_path.exists():
        continue
    text = file_path.read_text(encoding="utf-8")
    for regex in (EVENT_RE, EXC_RE, FAIL_RE, PRESENT_RE):
        for match in regex.finditer(text):
            found.setdefault(match.group(1), set()).add(name)

for event in sorted(found):
    print(f"{event}\t{','.join(sorted(found[event]))}")
