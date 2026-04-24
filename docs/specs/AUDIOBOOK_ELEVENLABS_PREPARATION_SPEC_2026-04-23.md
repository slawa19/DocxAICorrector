# Audiobook ElevenLabs Preparation Spec

Date: 2026-04-23
Status: Implemented; final polish tracked in-place
Scope type: new processing operation + composable post-pass + new user-visible artifact

## Implementation Status Snapshot (2026-04-24)

Closed in code and covered by tests:

1. stale narration state clearing on failure paths;
2. completed-view mode drift via persisted result-bundle metadata;
3. audiobook prompt and deterministic stripper contract hardening;
4. standalone audiobook guard against translation second pass;
5. bibliography-tail false exclusion for mixed final narrative blocks;
6. stronger §10.4 real-document sanity coverage with normalized paragraph-signature comparison and per-section tag assertions;
7. grouped `.result.md` / `.result.docx` / optional `.result.tts.txt` retention and dedicated narration artifact logging.

Remaining non-blocking polish after this update:

1. no architectural gaps remain for this spec;
2. log payload consistency is aligned to the shared `filename` / `artifact_paths` envelope while preserving the existing narration-specific fields.

Primary inputs:

- current processing-operation extension points in `config.py:68` (`PROCESSING_OPERATION_VALUES`), `config.py:131` (`_PROMPT_OPERATION_PATHS`), `config.py:141` (`_PROMPT_EXAMPLE_PATHS`), `config.py:917` (`load_system_prompt`).
- current translation second-pass precedent in `config.py:161-162` (`translation_second_pass_default`, `translation_second_pass_model`) and its UI/runtime wiring.
- current preparation cache and request-marker contract in `preparation.py:447` (`build_prepared_source_key`), `processing_runtime.py:482` (`build_preparation_request_marker`), `application_flow.py:468` (`prepare_run_context_for_background`), and `preparation.py:626` (`jobs are built during preparation`).
- current semantic-block plan builder in `document_semantic_blocks.py:18` (`build_semantic_blocks`) and `document_semantic_blocks.py:172` (`build_editing_jobs`).
- current pipeline orchestrator in `document_pipeline.py:846` (`run_document_processing`) and its late-phase finalization in `document_pipeline_late_phases.py:478` (`finalize_processing_success`).
- current output artifact contract in `runtime_artifacts.py:46` (`write_ui_result_artifacts`) and `constants.py:9` (`UI_RESULT_ARTIFACTS_DIR`).
- current runtime result/state plumbing in `processing_runtime.py:58` (`_ALLOWED_SET_STATE_EVENT_KEYS`), `processing_runtime.py:504` (`build_result_bundle`), `processing_runtime.py:517` (`get_current_result_bundle`), `state.py:494` (`init_session_state`), `state.py:540` (`reset_run_state`), and `app.py:823` (completed-result detection).
- current UI sidebar and result-rendering surface in `ui.py:43` (`TEXT_OPERATION_LABELS`), `ui.py:480` (`render_sidebar`), and `ui.py` result-rendering helpers (`render_result`, `render_result_bundle`).
- paragraph structural roles in `models.py:148` (`structural_role`: `body`, `toc_header`, `toc_entry`, `epigraph`, `attribution`, `image`, ...).
- prior extension-pattern precedent in `docs/archive/specs/TRANSLATION_QUALITY_AND_SECOND_PASS_SPEC_2026-04-20.md` and `docs/archive/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md`.
- ElevenLabs v3 audio-tag conventions (`[thoughtful]`, `[curious]`, `[serious]`, `[sad]`, `[excited]`, `[annoyed]`, `[sarcastic]`, `[whispers]`, `[short pause]`, `[long pause]`, `[sighs]`, `[laughs]`, `[chuckles]`, `[exhales]`).

## 1. Purpose

Add a first-class capability to produce an ElevenLabs-ready narration text from any document processed by this app, with no manual post-editing required. The capability must be available in two complementary shapes:

1. as a **standalone processing operation** `audiobook`, parallel to the existing `edit` and `translate`, for documents the user uploads directly with the intent to produce narration text;
2. as an **optional post-pass** (`audiobook_postprocess`) that can be composed with `edit` or `translate`, so that a single run produces both the edited/translated DOCX and the narration text from the same input.

When the post-pass is enabled, the UI must expose **two distinct download affordances**: one for the edited or translated document, one for the narration text.

## 2. Problem Statement

Today the app produces only an edited or translated DOCX/Markdown pair. To feed the result into ElevenLabs Audiobooks, the user must manually:

1. strip footnote reference markers (superscripts, inline `».1`, `[12]`);
2. strip non-narratable artefacts (page numbers, inline bibliographic references, URLs, duplicated captions, TOC entries, index pages);
3. expand typographic abbreviations that TTS reads as nonsense (`т. е.`, `т. н.`, `стр.`, `см.`, `г.`, `в.`, `напр.`);
4. normalize or remove non-pronounceable glyphs (`§`, `†`, `‡`, `©`, `®`, `™` when used as reference marks);
5. re-flow the text so each paragraph carries emotional/prosodic hints understood by ElevenLabs v3 (`[thoughtful]`, `[short pause]`, `[sighs]`, etc.).

Doing this by hand is slow, error-prone, and destroys the value of the upstream AI polishing. The product must deliver narration-ready text as a first-class output.

## 3. Goals

This work must achieve the following:

1. add a new `processing_operation` value `audiobook`, routed through the same pipeline as `edit` and `translate`, with its own system-prompt assets;
2. add an orthogonal toggle `audiobook_postprocess_enabled`, composable with `edit` and `translate`, that adds a narration-preparation second pass on the final post-edit markdown;
3. produce a narration-ready artifact `<stem>.tts.txt` in `.run/ui_results/`, containing ElevenLabs v3 audio tags and no Markdown markup, no footnote references, no non-narratable residue;
4. when `audiobook_postprocess_enabled` is active, expose in the UI **two separate download buttons**: one for the edited/translated DOCX or Markdown, one for the narration text;
5. when `processing_operation = "audiobook"`, force effective `image_mode = no_change` and emit only the narration artifact as the primary result, while still producing the standard `.result.md` and `.result.docx` for inspection;
6. keep TOC, bibliography, and image-only blocks out of the narration artifact without destroying them in the standard artifacts;
7. add regression coverage that proves the narration artifact is footnote-free, tag-enriched, stable across reruns, and that enabling the post-pass does not semantically mutate the base DOCX branch;
8. log a dedicated event `ui_audiobook_artifact_saved` following the existing `ui_result_artifacts_saved` contract (`docs/LOGGING_AND_ARTIFACT_RETENTION.md`).

### 3.1 Binding implementation decisions

The following decisions are fixed by this specification and must not be left to local implementation guesswork:

1. `audiobook` is a third `processing_operation` alongside `edit` and `translate`; it is not a new pipeline, not a new `ImageMode` axis, not a new `prompt_variant`.
2. `audiobook_postprocess_enabled` is a boolean config flag, defaulting to `False`, exposed as a sidebar checkbox, only meaningful when `processing_operation ∈ {"edit", "translate"}`.
3. When `processing_operation = "audiobook"`, the `audiobook_postprocess_enabled` checkbox is hidden and its effective value is `False`.
4. The narration artifact is always a plain UTF-8 text file with suffix `.tts.txt`, written next to `.result.md` / `.result.docx` in `.run/ui_results/`, sharing the same timestamped stem.
5. The narration artifact must not contain: Markdown headings/markers (`#`, `*`, `_`, `>`, backticks), raw URLs, footnote numbers, bibliographic citations, internal placeholders (`[[DOCX_PARA_*]]`, `[[DOCX_IMAGE_*]]`).
6. The narration artifact must contain at least one ElevenLabs audio tag per logical section and zero or more per paragraph elsewhere, with a density ceiling defined in §8.
7. Audiobook model resolution uses a single `AppConfig.audiobook_model` field. It resolves from `config.toml [models.audiobook].default` and falls back to `text.default`. This spec does **not** add a parallel `ModelRegistry.audiobook` field.
8. `narration_include` is preparation metadata computed deterministically from semantic blocks regardless of whether the post-pass checkbox is currently enabled. Toggling `audiobook_postprocess_enabled` must not require a different preparation cache key.
9. `processing_operation = "audiobook"` must coerce effective `image_mode = no_change` in runtime or pipeline setup, not only in the sidebar widget state.
10. The runtime result bundle grows an optional `narration_text` field, and all completed-view plumbing must carry it through background events, session state, reruns, and idle completed rendering.
11. Chapter-level JSON indexing and SSML emission are explicitly out of scope for this spec and deferred to a follow-up.

## 4. Non-Goals

This spec does not authorize the following:

1. integration with any TTS API directly (no audio generation, no ElevenLabs HTTP calls from this app);
2. SSML emission or any XML-based narration format;
3. chapter-level JSON indexing of narration text (deferred);
4. voice-casting hints, multi-voice dialogue tagging, or per-character prosody;
5. changes to the image pipeline, OOXML formatter, or DOCX assembly beyond runtime coercion of `image_mode = no_change` for `audiobook`;
6. a CLI entry point for this feature (Streamlit remains the only user surface);
7. a standalone "strip footnotes only" operation without LLM (the LLM is the correct tool to disambiguate reference marks from meaningful digits).

## 5. Terminology

- **Base operation** — the user-chosen `processing_operation`: `edit`, `translate`, or `audiobook`.
- **Post-pass** — an optional second LLM pass, applied after the base operation completes. Current precedent: `translation_second_pass`. New: `audiobook_postprocess`.
- **Narration artifact** — a plain-text file tailored for ElevenLabs Audiobooks, suffix `.tts.txt`.
- **Standard artifacts** — the existing `.result.md` + `.result.docx` pair produced by the pipeline today.
- **Narratable block** — a semantic block whose processed text may appear in the narration artifact; determined by paragraph `structural_role` and per-block heuristics.
- **Narration chunks** — processed block outputs collected in base-operation order for jobs where `narration_include=True`; this is the canonical intermediate input to narration artifact building and to the audiobook post-pass.
- **Semantic equivalence of DOCX outputs** — equality of normalized document content, not raw file-byte identity. The minimal guaranteed comparator is paragraph text order; a stronger comparator may also include selected stable OOXML parts.

## 6. Architecture Overview

The feature composes four additive surfaces around the existing pipeline:

### 6.1 New base operation `audiobook`

`audiobook` reuses the existing job pipeline. It differs only in:

1. `processing_operation` value and routing in `config.py:68`;
2. dedicated prompt files `prompts/operation_audiobook.txt` and `prompts/example_audiobook.txt`;
3. per-operation passthrough rules in `document_semantic_blocks.py` and preparation metadata `narration_include`;
4. runtime coercion `effective_image_mode = no_change`;
5. late-phase finalization emits the narration artifact in addition to the standard inspection artifacts.

### 6.2 Composable post-pass `audiobook_postprocess`

When `processing_operation ∈ {"edit", "translate"}` and the checkbox is checked, after base-operation block calls have completed, the pipeline runs a sibling narration branch over the processed outputs of narratable jobs only. The post-pass produces a separate narration-ready text stream and does not mutate the base-operation markdown.

Outputs:

- base-operation markdown -> `.result.md` + `.result.docx`;
- post-pass output -> `.tts.txt`.

### 6.3 Narration intermediate data contract

Late phases must not attempt to recover narratable content by re-parsing one monolithic `final_markdown` string. Instead, the runtime carries a dedicated narration-oriented intermediate structure through processing.

The minimal required contract is:

```python
state.processed_chunks: list[str]                 # existing full markdown chunks
state.narration_chunks: list[str]                 # processed chunks for narration_include=True jobs only
state.excluded_narration_block_count: int         # count of narration_include=False jobs
```

Equivalent richer structures are allowed, but the pipeline must preserve block order and narratability explicitly.

### 6.4 Narration artifact writer and result bundle

`runtime_artifacts.write_ui_result_artifacts` grows an optional `narration_text: str | None` parameter and, when present, writes `<stem>.tts.txt` alongside the existing pair.

The generic runtime result bundle and session-state contract also grow an optional `narration_text` field so the artifact remains visible after rerun and in the completed idle view.

Retention policy is extended to prune timestamped result stems atomically: `.result.md`, `.result.docx`, and optional `.tts.txt` from the same run are retained or removed as one group.

## 7. Detailed Design

### 7.1 Configuration and prompts

`config.py:68` becomes:

```python
PROCESSING_OPERATION_VALUES = ("edit", "translate", "audiobook")
```

`config.py:131` adds:

```python
_PROMPT_OPERATION_PATHS["audiobook"] = PROMPTS_DIR / "operation_audiobook.txt"
```

`config.py:141` adds:

```python
_PROMPT_EXAMPLE_PATHS["audiobook"] = PROMPTS_DIR / "example_audiobook.txt"
```

`AppConfig` gains two new fields, wired through the existing layered loader (`config_loader_layers.py`, `config_runtime_sections.py`):

```python
audiobook_postprocess_default: bool      # .env: DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT, default False
audiobook_model: str                     # config.toml [models.audiobook].default, fallback text.default
```

`config.toml` gains an optional new section:

```toml
[models.audiobook]
default = "gpt-5.4-mini"
```

Resolution rule:

1. if `[models.audiobook].default` is configured, use it;
2. otherwise use `models.text.default`.

Usage rule:

1. standalone `processing_operation="audiobook"` uses the user-selected sidebar model for the base operation, consistent with existing `edit` / `translate` behavior;
2. `AppConfig.audiobook_model` is the default model for the audiobook post-pass and for non-UI callers that need an explicit audiobook-specific model choice;
3. if a future internal caller explicitly overrides the audiobook-pass model, that override wins over `AppConfig.audiobook_model`.

This preserves the existing UI model-selection contract while giving the post-pass a stable config-backed default.

New prompt assets:

- `prompts/operation_audiobook.txt` — master instruction (§8).
- `prompts/example_audiobook.txt` — two worked source/target pairs demonstrating footnote stripping, abbreviation expansion, tag insertion, and tag-density discipline.

### 7.2 Preparation, cache invariants, and narratable classification

Preparation cache and request markers must remain stable when only `audiobook_postprocess_enabled` changes. Therefore the preparation phase always computes narratability metadata, even when the checkbox is off.

`build_prepared_source_key(...)` and `build_preparation_request_marker(...)` do not gain `audiobook_postprocess_enabled`.

`build_editing_jobs` is extended to emit `narration_include: bool` on each job. Updated signature:

```python
def build_editing_jobs(
    blocks,
    *,
    max_chars: int,
    processing_operation: str = "edit",
) -> list[dict[str, object]]:
```

`audiobook_postprocess_enabled` is intentionally **not** passed into `build_editing_jobs`; it is consumed later when selecting whether to launch the sibling narration branch.

`narration_include` rules:

1. blocks whose paragraphs are all `structural_role ∈ {"toc_header", "toc_entry"}` -> `narration_include=False`;
2. blocks whose paragraphs are all `structural_role == "image"` or whose text is empty after stripping placeholders -> `narration_include=False`;
3. blocks identified as bibliography tails -> `narration_include=False`;
4. all other blocks -> `narration_include=True`.

Bibliography-tail heuristic:

1. candidate blocks must be contiguous terminal blocks;
2. at least 70% of non-empty lines in the candidate region must match bibliography-like patterns such as `^\s*[\[\d]`, DOI / ISBN / URL tokens, or citation-heavy lead-ins;
3. the region must occur after the last narrative heading.

For this spec, a **narrative heading** means the last heading-like block before the terminal bibliography region whose paragraphs are not all `toc_header` / `toc_entry` and whose normalized text is not itself bibliography-like by the same DOI / ISBN / URL heuristic.

Operation-specific job-plan behavior:

1. for standalone `audiobook`, `narration_include=False` blocks are forced to passthrough behavior in the processing plan so they remain present in inspection artifacts but do not consume audiobook LLM calls;
2. for `edit` / `translate`, base-operation job kinds remain unchanged from current behavior, even when `narration_include=False`;
3. the audiobook post-pass branch consumes only the processed outputs of jobs with `narration_include=True`.

### 7.3 Late phases, narration chunks, and artifacts

`document_pipeline_block_execution.py` or equivalent block-execution plumbing must maintain a narration-specific collection during the base pass.

Required minimal state extension:

```python
state.narration_chunks: list[str]
state.excluded_narration_block_count: int
```

Population rules:

1. when a job finishes base processing and `job.narration_include=True`, append its processed chunk to `state.narration_chunks` in base-operation order;
2. when `job.narration_include=False`, do not append it to `state.narration_chunks` and increment `state.excluded_narration_block_count`;
3. standalone `audiobook` and `edit` / `translate` both populate `state.narration_chunks`; the difference is only whether the late narration branch is executed.

`runtime_artifacts.write_ui_result_artifacts(...)` gains:

```python
def write_ui_result_artifacts(
    *,
    source_name: str,
    markdown_text: str,
    docx_bytes: bytes,
    narration_text: str | None = None,
    output_dir: Path = UI_RESULT_ARTIFACTS_DIR,
    created_at: float | None = None,
) -> dict[str, str]:
```

Important compatibility notes:

1. the parameter name remains `source_name`; `source_stem` is not introduced;
2. the return type remains `dict[str, str]` for backward compatibility with existing callers that immediately cast the result with `dict(...)`;
3. when `narration_text is not None`, the returned mapping additionally contains `tts_text_path`.

Late-phase behavior:

1. if `processing_operation == "audiobook"`, the final markdown already contains audiobook-style text for narratable chunks. The narration artifact is built from `state.narration_chunks` passed through the deterministic markdown stripper.
2. if `audiobook_postprocess_enabled`, the late phase runs a separate audiobook LLM sweep over `state.narration_chunks` only. The post-pass output is then passed through the same deterministic markdown stripper.
3. if neither condition holds, no narration artifact is produced.

Post-pass rechunking rule:

1. do **not** rebuild semantic blocks from the assembled final markdown;
2. reuse base-operation narratable chunk boundaries as the primary unit;
3. if multiple adjacent narratable chunks need to be grouped to stay near `chunk_size`, group them in order while preserving narratable-only neighbors for `context_before` / `context_after`;
4. `context_before` / `context_after` for the post-pass are derived from adjacent narratable chunks, not from excluded TOC / bibliography / image-only blocks.

The log event `ui_audiobook_artifact_saved` is emitted with payload conceptually shaped as:

```json
{
  "event": "ui_audiobook_artifact_saved",
  "filename": "...",
  "source_name": "...",
  "artifact_paths": {
    "markdown_path": ".../.run/ui_results/...result.md",
    "docx_path": ".../.run/ui_results/...result.docx",
    "tts_text_path": ".../.run/ui_results/...tts.txt"
  },
  "tts_text_path": ".../.run/ui_results/...tts.txt",
  "char_count": 12345,
  "tag_count": 42,
  "excluded_blocks": 7,
  "mode": "standalone"
}
```

or the same payload with `"mode": "postprocess"`. The `mode` field is a string enum, not TypeScript union syntax.

For log-schema consistency with `ui_result_artifacts_saved`, the event also carries `filename` and the full `artifact_paths` mapping. `source_name` may remain as a compatibility alias while existing consumers converge.

### 7.4 Runtime result-bundle and session-state contract

The runtime result contract becomes:

```python
{
    "source_name": str,
    "source_token": str,
    "docx_bytes": bytes | None,
    "markdown_text": str,
    "narration_text": str | None,
}
```

Required plumbing updates:

1. `processing_runtime.py:_ALLOWED_SET_STATE_EVENT_KEYS` adds `latest_narration_text`;
2. `processing_runtime.py:build_result_bundle(...)` gains `narration_text: str | None`;
3. `processing_runtime.py:get_current_result_bundle()` must no longer be hard-gated only by `latest_docx_bytes`; it must support the completed result when `narration_text` exists, while still carrying inspection DOCX / Markdown for audiobook mode;
4. `state.py:init_session_state()` adds `latest_narration_text = None`;
5. `state.py:reset_run_state()` clears `latest_narration_text`;
6. `state.py` adds `get_latest_narration_text() -> str | None` and, if helpers are used elsewhere, a matching setter pattern;
7. all success and failure `emit_state(...)` call sites that currently clear or set `latest_docx_bytes` / `latest_markdown` must be audited to also clear or set `latest_narration_text` appropriately;
8. `app.py` completed-result detection and idle completed rendering must carry narration text through reruns and background completion, not only immediate in-run rendering.

### 7.5 UI changes

`ui.py:43` `TEXT_OPERATION_LABELS` gains:

```python
"audiobook": "Подготовка аудиокниги (ElevenLabs)"
```

Current `render_sidebar(...)` return tuple is, in order:

```python
(
    model,
    chunk_size,
    max_retries,
    image_mode,
    keep_all_image_variants,
    processing_operation,
    source_language,
    target_language,
    translation_second_pass_enabled,
)
```

It becomes:

```python
(
    model,
    chunk_size,
    max_retries,
    image_mode,
    keep_all_image_variants,
    processing_operation,
    source_language,
    target_language,
    translation_second_pass_enabled,
    audiobook_postprocess_enabled,
)
```

`render_sidebar(...)` changes:

1. renders a new checkbox `Подготовить для ElevenLabs аудиокниги` below the text-operation selector when `processing_operation ∈ {"edit", "translate"}`;
2. hides the checkbox when `processing_operation == "audiobook"`;
3. when `processing_operation == "audiobook"`, disables the image-mode widget and shows effective `no_change`;
4. keeps `source_language` and `target_language` widgets visible;
5. when `processing_operation == "audiobook"`, the UI must also force effective `translation_second_pass_enabled = False` because translation second pass is meaningless for the standalone audiobook operation.

Result-rendering helpers in `ui.py` (`render_result`, `render_result_bundle`) are extended to show download buttons based on the effective mode:

| Effective mode | Download buttons shown |
|---|---|
| `edit` | `Отредактированный DOCX`, `Отредактированный Markdown` |
| `translate` | `Переведённый DOCX`, `Переведённый Markdown` |
| `edit` + `audiobook_postprocess` | `Отредактированный DOCX`, `Отредактированный Markdown`, `Текст для ElevenLabs (.txt)` |
| `translate` + `audiobook_postprocess` | `Переведённый DOCX`, `Переведённый Markdown`, `Текст для ElevenLabs (.txt)` |
| `audiobook` | `Текст для ElevenLabs (.txt)`, `Markdown (для инспекции)`, `DOCX (для инспекции)` |

The completed idle view must render these same affordances from the result bundle, not only from immediate session-local variables.

### 7.6 Runtime enforcement of `image_mode = no_change`

The sidebar widget state alone is not sufficient. The effective runtime contract is:

1. if `processing_operation != "audiobook"`, keep existing image-mode behavior;
2. if `processing_operation == "audiobook"`, runtime or pipeline setup must coerce the effective image mode to `ImageMode.NO_CHANGE.value` before image processing is entered;
3. tests and non-UI callers that pass another image mode under `audiobook` must still observe `no_change` behavior;
4. optional warning logging on coercion is allowed but not required.

### 7.7 LLM pass semantics

Both the standalone base operation and the post-pass share the same system prompt (`operation_audiobook.txt`), loaded via the existing `load_system_prompt(operation="audiobook", source_language=..., target_language=..., editorial_intensity=...)`.

Chunking rules:

1. standalone `audiobook` uses the same semantic-block builder and base job chunking as other operations;
2. the audiobook post-pass uses `state.narration_chunks` as its source and preserves narratable-only neighborhood context when regrouping around `chunk_size`;
3. the post-pass does not re-run document extraction or semantic-block detection on the assembled markdown.

Model rules:

1. standalone `audiobook` base pass uses the user-selected runtime model, consistent with current `edit` / `translate` behavior;
2. audiobook post-pass defaults to `AppConfig.audiobook_model`;
3. if `AppConfig.audiobook_model` resolves empty for any reason, fall back to the current base model.

### 7.8 Follow-up-ready speech-clarity adaptation point

The current architecture should preserve a narrow extension point for future spoken-clarity rewriting without introducing a new pipeline axis.

1. Any future "make it easier to listen to" behavior must remain a narration-only concern inside the audiobook prompt contract and/or narration-only post-pass semantics; it must not become a fourth `processing_operation` and must not mutate the base `.result.md` / `.result.docx` branch.
2. The recommended shape is a narration-only profile such as `narration_adaptation_profile`, with `narration_adapted` as the effective default for both standalone `audiobook` and `audiobook_postprocess`.
3. The first rollout should be prompt-level, not pipeline-level: implement it by tightening `prompts/operation_audiobook.txt`, `prompts/example_audiobook.txt`, and narration-specific tests rather than by changing preparation, semantic-block planning, cache keys, or result-bundle structure.
4. If the profile remains implicit in v1, encode `narration_adapted` directly in the audiobook prompt assets. If it later becomes user-configurable, that setting must affect only the narration branch and must stay out of preparation cache keys and base-operation planning invariants.
5. `narration_adapted` means: split overly long or nested sentences, allow light paraphrase for oral clarity, preserve factual meaning, argument direction, polarity, named entities, quantities, and materially relevant qualifiers; no summarization, no omission of load-bearing clauses, no author-position softening.

This keeps the current spec additive: the audiobook pipeline can land first, and spoken-clarity adaptation can be strengthened later without reopening core runtime contracts.

## 8. Narration Transformation Rules (Prompt Contract)

These rules are the normative behavior of `prompts/operation_audiobook.txt` and must be explicitly encoded there. Tests in §10 verify them.

### 8.1 Artefact removal

The model must remove:

1. footnote reference markers: trailing superscripts (Unicode `\u00B9`, `\u00B2`, `\u00B3`, `\u2070-\u2079`), trailing digits glued to punctuation (for example `».1`, `"text".12`), inline bracketed reference markers (`[12]`, `[*]`, `[†]`, `[‡]`);
2. inline bibliographic citations: `(Smith, 2009)`, `[Smith, 2009, p.12]`, `(Ibid., 45)`, `(там же, с. 12)`;
3. raw URLs, DOIs, ISBNs, arXiv IDs;
4. non-pronounceable reference glyphs when used as reference marks (`§`, `†`, `‡`, `*`, `©`, `®`, `™` in reference position); keep them when they carry meaning, for example `§ 42 of the law`;
5. boilerplate figure/table cross-references that cannot be narrated (`см. рис. 3`, `см. табл. 2 выше`, `as shown in Figure 4`) — either rephrase neutrally or remove if load-bearing context is absent;
6. residual typographic artefacts: lone page numbers surrounded by em-dashes (`— 42 —`), running-header duplicates, soft-hyphen remnants, duplicate whitespace.

The model must **not** remove:

1. years, dates, monetary amounts, quantitative claims, proper nouns with digits (`Goldman Sachs`, `1930-х`, `125 миллиардов`);
2. genuine inline numbers that are part of the narrative.

Disambiguation rule: a trailing digit glued to a closing quote or punctuation with no grammatical role in the sentence is a footnote reference; a digit that reads as a year, count, or identifier stays.

### 8.2 Abbreviation expansion

The model must expand the following, matched on word boundaries:

| Source | Target |
|---|---|
| `т. е.`, `т.е.` | `то есть` |
| `т. н.`, `т.н.` | `так называемый` with correct gender / number |
| `г.` after year, `гг.` | `года`, `годов` |
| `в.` after century | `века` |
| `стр.` | `страница` with correct case |
| `см.` | `смотрите` |
| `напр.` | `например` |
| `и т. д.` | `и так далее` |
| `и т. п.` | `и тому подобное` |
| `e.g.` | `for example` |
| `i.e.` | `that is` |
| `cf.` | `compare` |
| `etc.` | `and so on` |
| Roman numerals in chapter references | spelled out, for example `гл. IV` -> `глава четвёртая` |

The model may leave an abbreviation unchanged if expansion would produce ungrammatical output.

### 8.3 Typography normalization

1. Quotes already normalized upstream must remain as-is; the audiobook pass must not fight upstream typography.
2. Em-dashes and en-dashes are preserved.
3. Ellipses `...` and `…` may remain according to upstream text; no special stripping is required.
4. Multiple consecutive spaces collapse to one; line-internal tabs are removed.

### 8.4 ElevenLabs tag insertion

Allowed tag vocabulary, closed set for v1:

```text
[thoughtful] [curious] [serious] [sad] [excited] [annoyed] [sarcastic] [whispers]
[short pause] [long pause] [sighs] [laughs] [chuckles] [exhales]
```

Placement rules:

1. **Section openers:** the first paragraph of every heading-delimited section must begin with exactly one mood tag derived from the section's emotional register.
2. **Paragraph openers inside a section:** a mood tag at the start of a paragraph is allowed but not required. Insert one when the tone clearly shifts from the previous paragraph.
3. **Inline pauses and non-verbal tags:** allowed between sentences, not inside a sentence. At most one inline tag per paragraph outside the opener.
4. **Tag-density ceiling:** average `<= 1.5` tags per 100 words across the document; no paragraph may carry more than 3 tags total.
5. **No repetition:** do not emit two identical tags adjacent to each other or within 40 words of the same tag.
6. **No contradiction with text:** do not insert `[laughs]` next to solemn content, `[whispers]` next to shouted dialogue, and so on.
7. **No Markdown markup around tags:** tags are plain bracketed tokens, never wrapped in `*` or `_`.

### 8.5 Markdown stripping, deterministic writer pass

When the narration artifact is written, a deterministic post-processor strips residual Markdown:

1. headings `#...` -> their text content followed by a blank line;
2. bold / italic markers `*`, `_`, `**`, `__` removed while preserving wrapped text;
3. inline-code backticks removed while preserving content;
4. bullet markers `-`, `*`, `1.` at line start removed while preserving content on its own line;
5. link syntax `[text](url)` -> `text` only;
6. blockquote `>` removed;
7. internal placeholders (`[[DOCX_*]]`) removed entirely;
8. consecutive blank lines collapsed to exactly one.

This deterministic stripping is a safety net so that even if the LLM leaks Markdown syntax, the narration artifact stays clean.

## 9. Data Flow Summary

```text
                 upload DOCX
                      |
                      v
        preparation + semantic blocks
                      |
                      v
   build_editing_jobs(processing_operation)
     -> each job gets narration_include flag
                      |
                      v
        base operation block execution
      -> processed_chunks for all jobs
      -> narration_chunks for narratable jobs
                      |
          +-----------+------------+
          |                        |
          v                        v
  final markdown / DOCX     audiobook sibling branch
  inspection artifacts      only if audiobook mode or
                            audiobook_postprocess_enabled
                                     |
                                     v
                   standalone audiobook: strip narration_chunks
                   post-pass: audiobook LLM sweep over narration_chunks,
                   then strip markdown
                                     |
                                     v
                               narration text
                                     |
                                     v
      write_ui_result_artifacts(
          source_name=...,
          markdown_text=final_markdown,
          docx_bytes=final_docx,
          narration_text=narration_text_or_none,
      )
                                     |
                                     v
             .result.md + .result.docx + optional .tts.txt
```

## 10. Test Plan

All tests run through `bash scripts/test.sh` in the canonical WSL runtime per `AGENTS.md`.

### 10.1 Unit

1. `tests/test_config_processing_operation.py`: `PROCESSING_OPERATION_VALUES` contains `"audiobook"`; `load_system_prompt("audiobook", ...)` composes without error and returns non-empty.
2. `tests/test_config_audiobook_model.py`: `AppConfig.audiobook_model` defaults to `text.default` when `[models.audiobook]` is absent; honors override when present.
3. `tests/test_semantic_blocks_narration_include.py`: fixture with TOC, body, image-only, bibliography blocks -> correct `narration_include` flags.
4. `tests/test_preparation_cache_audiobook_invariants.py`: toggling `audiobook_postprocess_enabled` does not change preparation cache key or request marker for the same file and chunk size.
5. `tests/test_runtime_artifacts_narration.py`: `write_ui_result_artifacts(..., narration_text="...")` creates `.tts.txt` next to the pair and returns `tts_text_path` in the mapping.
6. `tests/test_narration_markdown_stripping.py`: deterministic stripper removes `#`, `*`, `[[DOCX_*]]`, link syntax, blockquotes; preserves ElevenLabs `[tag]` tokens.
7. `tests/test_result_bundle_narration.py`: runtime result bundle and session-state helpers carry `narration_text` through completed-view accessors.

### 10.2 Integration

8. `tests/test_audiobook_standalone_pipeline.py`: mini-DOCX with a paragraph carrying a superscript footnote number -> pipeline run with `processing_operation="audiobook"` -> `.tts.txt` exists, contains no superscripts, no Markdown `#` or `*`, and at least one `[...]` tag.
9. `tests/test_audiobook_postprocess_pipeline.py`: same mini-DOCX with `processing_operation="translate"` and `audiobook_postprocess_enabled=True` -> both `.result.docx` and `.tts.txt` exist; the translated DOCX is semantically equivalent to a baseline run without post-pass by normalized paragraph-text comparison.
10. `tests/test_audiobook_excluded_blocks.py`: fixture with TOC + bibliography tail -> narration artifact contains neither; `.result.md` contains both.
11. `tests/test_audiobook_log_event.py`: a run emits exactly one `ui_audiobook_artifact_saved` event with the payload described in §7.3.
12. `tests/test_audiobook_runtime_image_mode_coercion.py`: standalone audiobook run coerces effective `image_mode` to `no_change` even if a non-UI caller passes another value.

### 10.3 Regression guard

13. `tests/test_ui_sidebar_audiobook.py`: sidebar exposes the checkbox only when base operation is `edit` or `translate`; hides it and forces effective `image_mode=no_change` when base is `audiobook`.
14. `tests/test_ui_result_buttons.py`: result panel and completed idle view expose the documented button set for each mode combination in §7.5.
15. `tests/test_translation_second_pass_is_ignored_for_audiobook.py`: standalone audiobook run does not execute translation second pass even if stale config or session state says it is enabled.

### 10.4 Real-document sanity

16. Run the existing Mazzucato fixture used in `docs/archive/specs/TOC_TRANSLATION_AND_MINIMAL_FORMATTING_SPEC_2026-04-21.md` with `translate + audiobook_postprocess` and verify:
    - `.result.docx` is semantically unchanged vs. baseline translate run by paragraph-text hash compare on the first `N` paragraphs or an equivalent normalized-content comparator;
    - `.tts.txt` has `tag_count >= 1` per detected section, zero lines matching `^\s*#`, zero URLs, zero superscripts `\u00B9-\u00B3\u2070-\u2079`.

## 11. Logging and Observability

Per `docs/LOGGING_AND_ARTIFACT_RETENTION.md`:

1. new event `ui_audiobook_artifact_saved` with payload described in §7.3;
2. existing `ui_result_artifacts_saved` continues to be emitted for the standard pair, independent of audiobook activity;
3. post-pass LLM calls are tagged with `operation="audiobook"` and `pass="postprocess"` in the existing structured-log call-site shape;
4. optional runtime coercion of `image_mode` under standalone audiobook may emit a warning or info event, but this is observational only and not part of the functional contract.

## 12. Migration and Backward Compatibility

1. Absence of `[models.audiobook]` in `config.toml` is a valid state; `AppConfig.audiobook_model` inherits `text.default`.
2. Absence of `DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT` in `.env` keeps the checkbox unchecked by default.
3. Existing runs with `processing_operation ∈ {"edit", "translate"}` and no checkbox produce semantically equivalent base artifacts to pre-feature builds. Regression test 10.2#9 guards this.
4. `runtime_artifacts.write_ui_result_artifacts` adds `narration_text: str | None = None` as a keyword-only, defaulted argument and preserves the existing `source_name` parameter name and mapping return type.
5. `render_sidebar` return tuple grows from 9 to 10 values; all call sites must be updated in the same commit that introduces the change.
6. The completed-result and result-bundle contract is extended, not replaced: code that only reads `docx_bytes` / `markdown_text` continues to work, but all user-visible result surfaces must be updated to understand optional `narration_text`.

## 13. Documentation Updates

Same commit or immediately following must update:

1. `docs/WORKFLOW_AND_IMAGE_MODES.md` — new section `Audiobook mode and post-pass`: base operation, checkbox, artifact contract, excluded blocks, runtime image-mode coercion, tag policy.
2. `README.md` — user-facing description of the new mode and the additional download button.
3. `docs/LOGGING_AND_ARTIFACT_RETENTION.md` — register `ui_audiobook_artifact_saved` and stem-group retention behavior for `.tts.txt` alongside the standard pair.
4. `AGENTS.md` `UI result artifacts` section — mention `.tts.txt` as an additional narration artifact alongside `.result.md` and `.result.docx`.

## 14. Implementation Plan (Commit Sequence)

Each step is independently reviewable and must pass `bash scripts/test.sh tests/ -q`. Do not merge steps together.

1. **Prompts and operation wiring.** Add `operation_audiobook.txt`, `example_audiobook.txt`. Extend `PROCESSING_OPERATION_VALUES`, `_PROMPT_OPERATION_PATHS`, `_PROMPT_EXAMPLE_PATHS`. Land the deterministic narration markdown stripper here. Tests 10.1#1, 10.1#6.
2. **AppConfig audiobook model fields.** Add `audiobook_postprocess_default` and `audiobook_model`. Wire `[models.audiobook].default` loader resolution with fallback to `text.default`. Tests 10.1#2.
3. **Preparation invariants and `narration_include`.** Extend `build_editing_jobs`; keep narratability independent from checkbox state; preserve preparation cache and request-marker invariants. Tests 10.1#3, 10.1#4.
4. **Narration artifact writer and grouped retention.** Extend `write_ui_result_artifacts` and retention behavior while preserving mapping compatibility. Tests 10.1#5.
5. **Pipeline narration chunks.** Add `state.narration_chunks` / equivalent runtime structure and populate it during base block execution. Tests covering standalone audiobook and excluded blocks.
6. **Standalone audiobook late-phase branch.** Wire `processing_operation="audiobook"` through runtime image-mode coercion and narration artifact finalization. Tests 10.2#8, 10.2#10, 10.2#12.
7. **Post-pass branch.** Implement audiobook post-pass over narration chunks, using `AppConfig.audiobook_model` default resolution and preserving base DOCX semantic equivalence. Tests 10.2#9.
8. **Runtime result bundle and UI wiring.** Extend result bundle, session state, completed idle view, `render_sidebar`, and result-render helpers. Tests 10.1#7, 10.3#13, 10.3#14, 10.3#15.
9. **Docs.** Per §13.
10. **Real-document sanity.** Run the Mazzucato fixture scenario in §10.4 and attach results to the PR.

### 14.1 Review Follow-Up Checklist

The following review findings were discovered during implementation verification and are now part of the must-close checklist for this spec. A step is not considered complete while any item that applies to that step remains open.

1. [closed] Failure paths that terminate processing after a previous successful audiobook-capable run explicitly clear `latest_narration_text` together with `latest_docx_bytes` / `latest_markdown`.
2. [closed] Completed-result rendering derives labels and button sets from persisted result-bundle metadata for that run, not from mutable session-local mode flags.
3. [closed] The normative audiobook prompt contract in §8 is encoded explicitly in `prompts/operation_audiobook.txt`.
4. [closed] The deterministic narration writer pass removes raw URLs and normalizes tabs / repeated internal whitespace in addition to Markdown cleanup.
5. [closed] Post-pass structured logs use the spec-defined field `pass="postprocess"`.
6. [closed] The real-document sanity path in §10.4 compares `translate + audiobook_postprocess` against a baseline `translate` run using a normalized semantic comparator for DOCX content.
7. [closed] The real-document sanity path in §10.4 verifies a stronger per-section tag condition, not just a single global tag hit.
8. [closed] The bibliography-tail heuristic keeps mixed final narrative blocks out of the excluded terminal bibliography region.
9. [closed] Standalone `audiobook` UI presents image mode as effectively fixed to `no_change`.
10. [closed] Regression coverage explicitly guards that standalone `processing_operation="audiobook"` never executes translation second pass even under stale config/session state.

Post-implementation polish note:

1. [closed] `ui_audiobook_artifact_saved` now follows the same `filename` / `artifact_paths` envelope style as `ui_result_artifacts_saved`, while retaining narration-specific counters and mode metadata.

## 15. Open Questions Deferred to Follow-Ups

1. chapter-level JSON indexing (`.tts.chapters.json`) for ElevenLabs chapter navigation;
2. voice-casting hints for dialogue-heavy texts;
3. SSML alternative output for TTS engines other than ElevenLabs;
4. per-language tag vocabularies beyond the language-agnostic v1 set defined in §8.4;
5. a preview pane in the UI that plays the first paragraph via the ElevenLabs API.
6. a narration-only spoken-clarity profile with `narration_adapted` as the default for both standalone `audiobook` and `audiobook_postprocess`; see §15.1.

### 15.1 Planned Follow-Up: `narration_adapted`

Recommended implementation shape:

1. Keep this as a narration-only prompt behavior, not a new processing operation, pipeline branch, image-mode axis, or document-level rewrite mode.
2. Treat `narration_adapted` as the default behavior for both standalone `audiobook` and `audiobook_postprocess`, but scope its output strictly to `.tts.txt`.
3. Land the first version by refining `prompts/operation_audiobook.txt` and `prompts/example_audiobook.txt`, then add narration-only regression coverage for sentence splitting and light paraphrase that preserves meaning.
4. Limit the transformation to splitting long, nested, or parenthetical sentences and lightly rephrasing bookish or over-compressed constructions for oral clarity.
5. Preserve factual claims, causal links, polarity, dates, quantities, names, and author stance; forbid summarization, deletion of materially relevant qualifiers, or weakening of the original claim.
6. Keep base-operation invariants unchanged: enabling or refining `narration_adapted` must not affect preparation cache keys, semantic-block detection, base DOCX semantic equivalence, or the standard artifact contract.
7. Recommended landing point: immediately after §14 step 7. By then the standalone audiobook path, narration chunks, and audiobook post-pass branch already exist, so the change stays localized to prompt contract, prompt examples, and narration-specific tests instead of reopening core pipeline work.

Prompt-contract requirements for this follow-up:

1. `prompts/operation_audiobook.txt` must explicitly state that the default narration style is `narration_adapted`: narration should sound easier to follow by ear than the source, while preserving meaning.
2. The prompt must allow sentence splitting when a sentence is long, multi-clausal, parenthetical, or difficult to parse on first hearing.
3. The prompt must allow only light paraphrase for spoken clarity: replacing bookish, compressed, or overly abstract constructions with simpler spoken equivalents is allowed when the meaning stays materially identical.
4. The prompt must explicitly forbid summarization, omission of load-bearing clauses, deletion of important qualifiers, softening or strengthening the author's claim, and insertion of new interpretation.
5. The prompt must explicitly require preservation of: named entities, dates, numbers, quantitative claims, causal links, polarity, attribution, and overall argument direction.
6. The prompt should instruct the model to keep terminology when it is semantically important, and simplify surrounding syntax before simplifying domain terms.
7. The prompt should instruct the model not to simplify sentences that are already clear enough for oral delivery; adaptation is selective, not mandatory on every paragraph.
8. The prompt should instruct the model to prefer two or three shorter spoken sentences over one overloaded sentence, but not to fragment prose into choppy one-clause lines when the original already flows naturally.
9. The prompt should instruct the model to keep paragraph order and local rhetorical progression intact; no reordering of claims across sentences or paragraphs.
10. The prompt must make tag placement compatible with sentence splitting: tags may appear at paragraph openings or between resulting sentences per §8.4, but adaptation must not increase tag density beyond the existing ceiling.
11. `prompts/example_audiobook.txt` should include at least two worked examples where a long academic or analytical sentence is split into shorter spoken sentences while preserving all factual content and argumentative force.
12. At least one example pair should be negative-by-contrast: show that an over-aggressive simplification would be wrong because it drops a qualifier, causal step, or evaluative nuance.

Recommended regression coverage for this follow-up:

1. Add a prompt-contract regression that checks a dense, nested sentence produces a narration output with more sentence boundaries than the source while preserving required entities and quantities.
2. Add a meaning-preservation regression that fails if a materially relevant qualifier or causal link disappears from the narration output.
3. Add a selective-adaptation regression that a short, already clear sentence is not unnecessarily paraphrased into a looser or more colloquial formulation.
4. Add a post-pass regression proving `translate + audiobook_postprocess` may simplify narration wording in `.tts.txt` while the translated `.result.docx` remains semantically equivalent to the baseline translate run.
