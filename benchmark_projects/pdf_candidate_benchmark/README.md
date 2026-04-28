# PDF Candidate Benchmark

Isolated benchmark project for comparing PDF normalization and structural extraction candidates on `end-times-pdf-core` without changing the production app path.

## Scope

- Reuses the repository's existing structural preparation path for DOCX-producing candidates.
- Keeps structural-extractor candidates benchmark-only.
- Writes run-scoped artifacts under `benchmark_projects/pdf_candidate_benchmark/artifacts/runs/<run_id>/`.

## Entry Point

Run from WSL project root:

```bash
bash benchmark_projects/pdf_candidate_benchmark/run.sh
```

Optional arguments are forwarded to the Python CLI, for example:

```bash
bash benchmark_projects/pdf_candidate_benchmark/run.sh --source-profile-id end-times-pdf-core
```