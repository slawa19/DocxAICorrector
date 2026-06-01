from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docxaicorrector.pdf_import.text_layer_quality import (
    build_text_layer_quality_report,
    extract_pdf_text_spans_with_pdfminer,
    load_spans_json,
    unsupported_quality_report,
    write_quality_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic PR-PDF0 text-layer quality report."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-pdf", type=Path)
    source.add_argument("--input-spans-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.input_spans_json:
        report = build_text_layer_quality_report(load_spans_json(args.input_spans_json))
    else:
        try:
            spans = extract_pdf_text_spans_with_pdfminer(args.input_pdf)
        except RuntimeError as exc:
            report = unsupported_quality_report(str(exc))
        else:
            report = build_text_layer_quality_report(spans)

    if args.output:
        write_quality_report(args.output, report)
    else:
        json.dump(report.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
