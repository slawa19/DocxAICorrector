# Image model comparison — 2026-11-07 (spec 062, SC-002 / FR-005 input)

**Durable outputs (not in git):** `D:\Temp\docxai-runs\image-compare-2026-11-07\` (WSL `/mnt/d/Temp/docxai-runs/image-compare-2026-11-07/`)

- `index.html`: every original and output side by side, with captions (vision / draw / mode, judge scores, validator scores, calls, cost)
- `comparison.md`: this text plus the same tables
- `<image>/<mode>/<vision>__<draw>[__forced].png|.json`: the kept output, every attempt (`__aN.png`), the raw Images API rasters (`raw/`), and the full cell record
- `analysis/analysis_<model>.json`: the 9 standalone analysis calls; `book_analysis_gpt-5.4-mini.json`: the 43-image analysis
- `spend_ledger.jsonl`: one line per model call (stage, role, model, tokens, raw usage, estimated $)
- `scripts/`: the harness (`run_cells.py`, `run_analysis.py`, `cmp_lib.py`, `replay_restore.py`, `build_report.py`)

Judge scores 1–5: **L** label fidelity, **C** Cyrillic / glyph rendering, **S** structural fidelity, **V** visual quality. "missing / altered" counts text nodes against the original; "validator" is the pipeline's own score of the kept attempt (semantic / text / structure match).

## How this was run

- Worktree `062/image-compare` at `9e3ff9f` (spec 062 P0 selectors, capability table, P1 prompt fixes). Per-role pins in `.env` commented out, so the two selectors drove all six image roles (each cell JSON records `role_models`).
- Every redraw went through the production entry `ProcessingService.process_document_images` with the shipped `config.toml` (advisory validation, two attempts max, nine calls per image max). The selection was applied with `apply_image_model_selection(load_app_config(), vision_model=…, draw_model=…)`, the same way the UI does it. One cell is one image × one mode × one draw model with the vision model fixed, and each cell ran in its own `run_model_accounting_scope`.
- The harness only observed. It patched in three places to read, never to change behaviour: a per-call usage record on the ledger, the raw vision JSON, and the raw Images API raster before the product's restore step. That last capture started after the first 12 cells (all the mini cells); the cells after it have `raw/` files.
- **Forced cells (non-production).** With terra or sol as the vision model, the analysis routed the infographic and the chart to `safe_mode`, so production made no redraw at all (12 of the 28 planned cells; see finding 5). To compare the draw models with those vision models anyway, those 12 cells were rerun with `--force`. In that rerun only the analysis of the ORIGINAL image is overridden to `semantic_redraw_allowed=True`; brief, generation, candidate analysis and validation are untouched. Forced cells are marked "forced" everywhere.
- Image selection from Money & Sustainability: the 43 images were extracted through the product's own PDF import (`_convert_pdf_to_docx_with_optional_text_layer` → `extract_document_content_from_docx`; the DOCX in `tests/sources/book/` has no media), and `gpt-5.4-mini` analysed all of them. The diagram is `img_023`: three images tied as `diagram` with 11 text nodes, and this one had the longest extracted text and two curves plus two arrows. The chart is `img_027`: `chart` with the most nodes (30), four series, and 56 real text nodes counted by hand.

## Cost and calls (ledger)

The ledger recorded **268 calls, all of them with `usage`**. `cost_usd_reported_by_provider` is 0.0 and `cost_accounting_complete` is False on every cell, because OpenAI does not return a price. All dollar figures below are therefore estimates: tokens × the rate table in `scripts/cmp_lib.py`. The rates are deliberately upper-bound:

| Model | Rate used (per 1M tokens) | Source |
|---|---|---|
| `gpt-5.4-mini` | $0.75 in / $4.50 out | spec 062 R9 |
| `gpt-6.1-sol` | $2 / $10 | spec 062 variant-2 table |
| `gpt-6.1-terra` | $2 / $10 (upper bound) | not published in the repo; the spec 062 FR-006 row implies ≈ $1 / $5 |
| `gpt-image-2.5-flare`, `-sunburst` | text in $5, image in $10, out $40 (upper bound) | not published; the spec 062 FR-006 rows imply ≈ $8 in / ≈ $30 out |

| Phase | Calls | ≈ $ (upper bound) |
|---|---|---|
| 43-image analysis, mini | 43 | 0.063 |
| 9 analysis calls (3 images × 3 vision models) | 9 | 0.076 |
| 28 production cells | 127 | 2.424 |
| 12 forced cells | 89 | 2.438 |
| **Total** | **268** | **5.00** (cap $10, stop line $9 never reached) |

| Role / model | Calls | Prompt tokens | Completion tokens | ≈ $ |
|---|---|---|---|---|
| image_analysis / mini | 81 | 112 504 | 23 843 | 0.19 |
| image_analysis / sol | 18 | 57 524 | 13 316 | 0.25 |
| image_analysis / terra | 43 | 95 699 | 35 951 | 0.55 |
| image_edit / flare | 11 | 21 406 | 15 092 | 0.77 |
| image_edit / sunburst | 13 | 24 900 | 17 836 | 0.91 |
| image_generation / flare | 12 | 21 024 | 16 464 | 0.76 |
| image_generation / sunburst | 14 | 24 471 | 19 208 | 0.89 |
| image_generation_vision / mini, sol, terra | 12 / 3 / 11 | 15 256 / 9 803 / 15 488 | 14 118 / 3 512 / 11 314 | 0.08 / 0.06 / 0.14 |
| image_validation / mini, sol, terra | 23 / 7 / 20 | 86 448 / 45 565 / 77 003 | 1 560 / 1 109 / 6 909 | 0.07 / 0.10 / 0.22 |

Measured, not estimated: **every one of the 50 Images API calls returned exactly 1 372 output image tokens**, on both models and on both edit and generate. So flare and sunburst cost the same per call unless their per-token prices differ. That makes one image call ≈ $0.067 at the upper-bound rate and ≈ $0.05 at the spec-implied rate, against the spec's forecast of $0.175. A production cell cost $0.07–0.18 with mini as the vision model and $0.09–0.24 with terra or sol; the second attempt is what drives the upper end.

## Verdicts

**Complex image (Cyrillic infographic, FR-005 gate material).**
- Best regardless of price: **structured × flare with terra or sol as the vision model**. Both reproduced every text block verbatim, including `використовуються` and `Оціночні`, with a faithful layout (5/5/5/5). Both were forced, though: in production terra and sol route this image to `safe_mode` and make no redraw.
- Best in production: **mini × flare, structured** (4/5/5/5, ≈ $0.17). It carries two text alterations. One of them, `Оцінювальні`, is mini's own misreading copied into the picture (finding 4).
- Best creative (direct) result: **terra × sunburst** or **sol × flare/sunburst** (forced). All text is exact, with a full redesign. Direct with flare garbled Cyrillic twice (`маніпу?ція`, `оціночі`, `бюся`).
- FR-005: on this image, Cyrillic rendering itself is **not** the blocker. In structured mode both draw models render Ukrainian cleanly (C = 5 in all 6 structured outputs). The errors that occur are copied-in misreadings or single substituted letters.

**Diagram (img_023).**
- Best regardless of price and best value at once: **terra × sunburst, structured**. It is pixel-faithful, every label is exact (including `Efficiency (Λ)`, which mini and flare turned into `(A)`), it needed one attempt, and it cost ≈ $0.09.
- Cheapest good result: **mini × flare, structured** (4/5/5/5, ≈ $0.07, one attempt; Λ→A).
- Direct mode rearranges the diagram: windows, chevrons and dots move (S = 2–3). mini × sunburst direct lost 7 of 11 labels to the restore defect (finding 1) and was delivered anyway.

**Chart (img_027, 56 text nodes).**
- Only structured mode is usable. The best result is **mini × sunburst, structured** (4/5/5/5: one duplicated x tick; title style closest to the original). Close behind are **mini × flare** and **terra × flare (forced)**, with 3 wrong x ticks each.
- Direct mode failed on 3 of 4 outputs. The title, the axis label and all 13 y ticks were erased by the restore step, and the series proportions were redrawn arbitrarily.
- In production, terra and sol do not redraw this chart at all (route `safe_mode`).

**Overall.**
- **Mode matters far more than the model.** Structured (the `images.edit` path) scored S = 4–5 everywhere. Direct (vision brief → `images.generate`) is a redesign (S = 2–3), and it is also the path hit by finding 1.
- **flare vs sunburst: no consistent winner, and the cost is the same** (identical token counts). sunburst won on the diagram (kept Λ) and on the chart with mini (one wrong tick against three). flare won on the chart with terra (3 wrong against 12) and on the infographic with sol (0 against 1).
- **Best for value: `gpt-5.4-mini` + `gpt-image-2.5-flare`, structured (spec 062 "variant 1").** It is the only vision model that lets production redraw the dense infographic and the dense chart. The analysis costs ~$0.001–0.005 per call.
- **Best regardless of price: `gpt-6.1-terra` + either draw model, structured.** It has the most accurate and the most stable reading, and the validator gets a stable reference. That holds only if terra's `safe_mode` routing on dense images is not taken as final (finding 5). As shipped, terra turns redraw off for 2 of the 3 test images.

## terra vs mini vs sol on analysis

Of the 9 standalone calls, the chart and the infographic were counted against a hand-made ground truth (chart: 56 nodes; infographic: 19 text blocks plus 3 logo captions). The diagram reference is the 11 labels.

| Image | mini | sol | terra |
|---|---|---|---|
| Infographic: text | all blocks; **1 wrong word** (`Оціночні`→`Оцінювальні`) | all verbatim (`labels` capped at 12) | all verbatim, plus one spurious `unreadable` token |
| Infographic: route / nodes | `semantic_redraw_direct`, 18 → advisory `dense_text_bypass` → **redraws** | **`safe_mode`**, 22 → no redraw | **`safe_mode`**, 21 → no redraw |
| Diagram: labels | 11/11, Λ→A | 11/11, Λ→A | 11/11, Λ→A here (Λ kept in 3 of 4 in-pipeline calls); **type `chart`** (every call) |
| Chart: text | **missed all 13 y-axis ticks**; 37/37 years | **missed all 37 x-axis years** ("unreadable") | **56/56** |
| Chart: route / nodes | structured, 38 → advisory bypass → redraws | `safe_mode`, 56 | `safe_mode`, 56 |
| Reasoning tokens (infographic / diagram / chart) | 0 / 0 / 0 | 317 / 271 / 379 | 190 / 693 / 398 |
| ≈ $ per call | 0.0014–0.005 | 0.007–0.016 | 0.010–0.014 |
| Node count across all calls on the same image | chart **6, 23, 29, 30, 35, 38**; diagram **5, 9, 11, 11, 11**; infographic 12–19 | infographic 22–25 | chart **56 ×9**; diagram **11 ×5**; infographic **21 ×9** |

**Verdict: terra beats both.** It is the only model that read the chart completely, it ties sol on the Cyrillic text, and it is by far the most stable: identical node counts on every call. mini is the cheapest and the only model that keeps dense images on a redraw route. It drops whole label classes, though (all y ticks), and its run-to-run variance is large enough to swing the validator (finding 3). sol sits between them on accuracy, below terra on the chart, and costs about the same as terra.

## What the pipeline did unexpectedly

1. **Defect: the creative path erases dark text.** `generation.py:470` asks for `background="transparent"`, which the 2.5 rows of the capability table accept. `:484-489` then runs `_restore_generated_output(..., prefer_light_background=True)`. That calls `_normalize_generated_document_background` (`:1585`), whose mask (`_build_connected_background_mask`, `:1599`) works on `image.convert("RGB")` (`:1605`) and ignores alpha. The fully transparent pixels of a 2.5 answer carry a dark RGB value (the corner pixel measured `(1, 11, 41, 0)`; 90 % of the canvas is alpha 0). So any dark text within distance 48 (`:1618`) of that colour is flood-filled to white.
   - Evidence: compare the raw model output in `raw/*__on_white.png` with the delivered file. The model drew the title, the axis labels and all the ticks; the delivered file has white ghosts in their place.
   - Replaying the product function offline on the raw file reproduces the erased result exactly (`replay/…__restored.png`, `scripts/replay_restore.py`).
   - Seen in 6 direct outputs: diagram mini × sunburst (both attempts), diagram terra × sunburst attempt 1 (9 labels gone), chart mini × flare, chart mini × sunburst, chart terra × sunburst (forced). The mini cells predate the raw capture but show the same signature.
   - Coloured (red, blue) text survives. The structured `images.edit` path was not affected in any cell. `:621` (structured generate) sends the same parameter, but that path was not exercised here.
2. **The validator never stops a redraw.** All 28 cells that produced a candidate delivered it: 2 `accept`, 26 `accept_soft`. 48 of 50 validations logged `image_validation_advisory_accept`. That includes text_match 0.20–0.22 with 7–15 labels missing. The cause is `semantic_validation_policy = "advisory"` (`config.toml:42`) together with `should_deliver_redrawn_candidate` (`pipeline_policy.py:45`), which delivers anything short of a hard failure. Validator scores are informational only.
3. **The validator's reference is the noisy part.** The validator compares the candidate against the analysis of the original made in the same cell. mini's analysis of the same image varied from 5 to 11 nodes on the diagram and from 6 to 38 on the chart. As a result, a pixel-faithful redraw (diagram mini × sunburst, structured) scored sem 0.54 with "added_entities: 100, diversity…" and triggered a paid second attempt. terra produced the same count every time, and its validator text_match tracked real quality (0.88 for 3 wrong ticks, 0.30 for 12, 0.20 for an erased chart).
4. **Vision misreadings are copied into the picture.** mini's `Оцінювальні` appears in the mini × flare structured redraw, and `Λ→A` appears in every cell whose analysis misread it. The draw model reproduces the extracted text it is given. Whenever the reading came out right (terra, sol), the redraw got it right.
5. **terra and sol turn redraw off for dense images.** The analysis system prompt says that dense infographics and charts, "especially in Cyrillic", should prefer `safe_mode` (`analysis.py:524`). terra and sol follow it; mini does not. A `safe_mode` route forces `semantic_redraw_allowed=False` (`analysis.py:749`) with a free-text `fallback_reason`, which is not one of the advisory `dense_*` prefixes (`pipeline_policy.py:6-9`). So the semantic modes fall back to `safe_only` with no redraw. All 12 such production cells (terra × chart, terra × infographic, sol × infographic) cost one analysis call each and delivered the safe image. Choosing terra or sol in the UI therefore silently disables redraw for exactly the images FR-005 is about.
6. Minor:
   - terra types the sustainability diagram as `chart` on every call (no visible effect).
   - mini returned `image_type: "logo"` for 2 of the 43 book images. That value is outside `ANALYSIS_IMAGE_TYPES` and passes through unchecked.
   - On 7 of the 43 images, the heuristic `fallback_reason: photo_safe_only` survives on images classified as diagrams or charts.
   - There were **no** parameter errors, no retries, no exceptions, no `image_model_role_override_active` and no WARNING/ERROR events in any cell. The capability table produced valid requests for both 2.5 models on edit and on generate.

## Per-image tables

### Complex image — Cyrillic infographic «ФАКТИ VS МАНІПУЛЯЦІЇ» (tests/журналистика факты манипуляции.png)

| vision × draw | mode | run | L | C | S | V | missing / altered labels | validator (kept: sem / txt / str) | outcome | calls | ≈ $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mini × flare | structured | prod | 4 | 5 | 5 | 5 | 0 / 2 | 0.89 / 0.87 / 0.69 | delivered (accept_soft) | 7 | 0.174 |
| mini × sunburst | structured | prod | 4 | 5 | 4 | 5 | 0 / 1 | 0.72 / 0.35 / 0.68 | delivered (accept_soft) | 7 | 0.173 |
| terra × flare | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.014 |
| terra × sunburst | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| sol × flare | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| sol × sunburst | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| terra × flare | structured | forced | 5 | 5 | 5 | 5 | 0 / 0 | 0.89 / 1.00 / 0.66 | delivered (accept_soft) | 4 | 0.118 |
| terra × sunburst | structured | forced | 5 | 5 | 4 | 5 | 0 / 0 | 0.73 / 0.55 / 0.69 | delivered (accept_soft) | 7 | 0.220 |
| sol × flare | structured | forced | 5 | 5 | 5 | 5 | 0 / 0 | 0.74 / 0.55 / 0.73 | delivered (accept_soft) | 7 | 0.220 |
| sol × sunburst | structured | forced | 4 | 5 | 5 | 5 | 0 / 1 | 0.74 / 0.55 / 0.71 | delivered (accept_soft) | 7 | 0.221 |
| mini × flare | direct | prod | 3 | 3 | 2 | 4 | 0 / 3 | 0.72 / 0.45 / 0.66 | delivered (accept_soft) | 9 | 0.174 |
| mini × sunburst | direct | prod | 4 | 5 | 2 | 4 | 0 / 1 | 0.69 / 0.55 / 0.57 | delivered (accept_soft) | 9 | 0.175 |
| terra × flare | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| terra × sunburst | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| sol × flare | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.015 |
| sol × sunburst | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.016 |
| terra × flare | direct | forced | 3 | 3 | 2 | 4 | 0 / 4 | 0.70 / 0.50 / 0.60 | delivered (accept_soft) | 9 | 0.229 |
| terra × sunburst | direct | forced | 5 | 5 | 2 | 5 | 0 / 0 | 0.90 / 1.00 / 0.69 | delivered (accept_soft) | 9 | 0.231 |
| sol × flare | direct | forced | 5 | 5 | 2 | 5 | 0 / 0 | 0.90 / 0.99 / 0.71 | delivered (accept) | 5 | 0.127 |
| sol × sunburst | direct | forced | 5 | 5 | 2 | 5 | 0 / 0 | 0.88 / 1.00 / 0.64 | delivered (accept_soft) | 9 | 0.236 |

### Diagram — Money & Sustainability img_023 (sustainability curve, 11 text nodes)

| vision × draw | mode | run | L | C | S | V | missing / altered labels | validator (kept: sem / txt / str) | outcome | calls | ≈ $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mini × flare | structured | prod | 4 | 5 | 5 | 5 | 0 / 1 | 0.94 / 1.00 / 0.82 | delivered (accept) | 4 | 0.071 |
| mini × sunburst | structured | prod | 4 | 5 | 5 | 5 | 0 / 1 | 0.54 / 0.99 / 0.64 | delivered (accept_soft) | 7 | 0.139 |
| terra × flare | structured | prod | 4 | 5 | 5 | 5 | 0 / 1 | 0.90 / 1.00 / 0.68 | delivered (accept_soft) | 4 | 0.090 |
| terra × sunburst | structured | prod | 5 | 5 | 5 | 5 | 0 / 0 | 0.88 / 1.00 / 0.65 | delivered (accept_soft) | 4 | 0.088 |
| mini × flare | direct | prod | 3 | 5 | 3 | 4 | 0 / 1 | 0.69 / 1.00 / 0.59 | delivered (accept_soft) | 9 | 0.148 |
| mini × sunburst | direct | prod | 1 | 2 | 2 | 3 | 7 / 0 | 0.84 / 0.22 / 0.54 | delivered (accept_soft) | 9 | 0.150 |
| terra × flare | direct | prod | 5 | 5 | 3 | 4 | 0 / 0 | 0.83 / 1.00 / 0.59 | delivered (accept_soft) | 5 | 0.096 |
| terra × sunburst | direct | prod | 5 | 5 | 3 | 4 | 0 / 0 | 0.81 / 1.00 / 0.59 | delivered (accept_soft) | 9 | 0.181 |

### Chart — Money & Sustainability img_027 (stacked area, 4 series, 56 text nodes)

| vision × draw | mode | run | L | C | S | V | missing / altered labels | validator (kept: sem / txt / str) | outcome | calls | ≈ $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mini × flare | structured | prod | 4 | 5 | 5 | 5 | 0 / 3 | 0.74 / 0.30 / 0.74 | delivered (accept_soft) | 7 | 0.151 |
| mini × sunburst | structured | prod | 4 | 5 | 5 | 5 | 0 / 1 | 0.77 / 0.50 / 0.81 | delivered (accept_soft) | 7 | 0.151 |
| terra × flare | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.010 |
| terra × sunburst | structured | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.011 |
| terra × flare | structured | forced | 4 | 5 | 5 | 5 | 0 / 3 | 0.67 / 0.88 / 0.70 | delivered (accept_soft) | 7 | 0.201 |
| terra × sunburst | structured | forced | 3 | 4 | 5 | 5 | 0 / 12 | 0.81 / 0.30 / 0.71 | delivered (accept_soft) | 7 | 0.199 |
| mini × flare | direct | prod | 1 | 1 | 2 | 3 | 15 / 37 | 0.67 / 0.40 / 0.54 | delivered (accept_soft) | 9 | 0.150 |
| mini × sunburst | direct | prod | 1 | 1 | 3 | 3 | 15 / 37 | 0.72 / 0.30 / 0.68 | delivered (accept_soft) | 9 | 0.151 |
| terra × flare | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.010 |
| terra × sunburst | direct | prod | — | — | — | — | — | — | no redraw: analysis route safe_mode, safe image delivered | 1 | 0.011 |
| terra × flare | direct | forced | 3 | 5 | 3 | 4 | 0 / 4 | 0.53 / 0.82 / 0.68 | delivered (accept_soft) | 9 | 0.225 |
| terra × sunburst | direct | forced | 1 | 1 | 3 | 3 | 15 / 37 | 0.46 / 0.20 / 0.53 | delivered (accept_soft) | 9 | 0.211 |

## Money & Sustainability: analysis of all 43 images (gpt-5.4-mini, product analyze_image)

The images were extracted through the product PDF import (the DOCX in `tests/sources/book/` carries no media). 43 calls, 26 811 / 9 511 tokens, ≈ $0.063. Types: diagram 15, chart 12, infographic 7, mixed_or_ambiguous 3, logo 2, table 2, screenshot 1, photo 1. Raw routes: semantic_redraw_structured 23, semantic_redraw_direct 13, safe_mode 7.

| image | px | image_type | text_node_count | recommended_route (raw) | pipeline render_strategy | redraw allowed | fallback_reason |
|---|---|---|---|---|---|---|---|
| img_001 | 973x1389 | screenshot | 9 | safe_mode | safe_mode | no | Cover page with text and logo; not suitable for semantic ... |
| img_002 | 91x76 | logo | 2 | safe_mode | safe_mode | no | Simple logo/emblem with text; not a diagram/table/chart s... |
| img_003 | 70x69 | mixed_or_ambiguous | 2 | safe_mode | safe_mode | no | Logo/emblem with curved text; not suitable for faithful s... |
| img_004 | 568x73 | logo | 2 | safe_mode | safe_mode | no | Not one of the allowed image_type values; treated conserv... |
| img_005 | 371x750 | chart | 12 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_006 | 152x233 | diagram | 2 | semantic_redraw_direct | semantic_redraw_direct | yes | photo_safe_only |
| img_007 | 210x187 | diagram | 3 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_008 | 282x282 | diagram | 3 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_009 | 577x253 | table | 8 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_010 | 483x175 | diagram | 8 | semantic_redraw_structured | semantic_redraw_structured | yes | photo_safe_only |
| img_011 | 411x256 | chart | 13 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_012 | 390x234 | chart | 11 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_013 | 398x373 | chart | 17 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_014 | 479x228 | table | 18 | semantic_redraw_structured | deterministic_reconstruction | no | dense_text_bypass:18_nodes |
| img_015 | 495x341 | infographic | 11 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_016 | 324x279 | diagram | 4 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_017 | 449x392 | chart | 13 | semantic_redraw_structured | deterministic_reconstruction | no | dense_non_latin_text_bypass:13_nodes |
| img_018 | 418x264 | chart | 8 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_019 | 400x252 | diagram | 10 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_020 | 361x226 | diagram | 10 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_021 | 473x260 | diagram | 11 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_022 | 453x286 | diagram | 11 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_023 | 413x259 | diagram | 11 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_024 | 454x319 | infographic | 17 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_025 | 390x294 | chart | 5 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_026 | 333x294 | chart | 22 | semantic_redraw_structured | deterministic_reconstruction | no | dense_text_bypass:22_nodes |
| img_027 | 474x362 | chart | 30 | semantic_redraw_structured | deterministic_reconstruction | no | dense_text_bypass:30_nodes |
| img_028 | 520x333 | chart | 13 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_029 | 389x260 | diagram | 6 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_030 | 362x255 | mixed_or_ambiguous | 1 | safe_mode | safe_mode | no | Hand-drawn cartoon/illustration with only a tiny illegibl... |
| img_031 | 256x295 | diagram | 7 | semantic_redraw_direct | deterministic_reconstruction | yes |  |
| img_032 | 444x333 | chart | 16 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_033 | 539x240 | diagram | 8 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_034 | 455x267 | diagram | 6 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_035 | 467x254 | chart | 13 | semantic_redraw_structured | semantic_redraw_structured | yes | photo_safe_only |
| img_036 | 576x732 | infographic | 29 | semantic_redraw_structured | deterministic_reconstruction | no | dense_text_bypass:29_nodes |
| img_037 | 459x344 | photo | 0 | safe_mode | safe_mode | no | Photographic scene with no readable text and no diagramma... |
| img_038 | 542x293 | infographic | 3 | semantic_redraw_structured | semantic_redraw_structured | yes | photo_safe_only |
| img_039 | 550x295 | infographic | 10 | semantic_redraw_structured | semantic_redraw_structured | yes | photo_safe_only |
| img_040 | 531x309 | infographic | 11 | semantic_redraw_structured | semantic_redraw_structured | yes | photo_safe_only |
| img_041 | 502x386 | diagram | 5 | semantic_redraw_structured | deterministic_reconstruction | yes |  |
| img_042 | 55x68 | mixed_or_ambiguous | 1 | safe_mode | safe_mode | no | Small stylized logo/monogram; not enough structured conte... |
| img_043 | 561x800 | infographic | 12 | semantic_redraw_direct | semantic_redraw_direct | yes | photo_safe_only |
