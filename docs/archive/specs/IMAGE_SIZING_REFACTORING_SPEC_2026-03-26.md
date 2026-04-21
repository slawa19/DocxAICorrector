# Image Sizing & Crop Fidelity Refactoring Specification

**Date:** 2026-03-26
**Status:** Implemented — phases 1 through 6 completed for the sizing/crop fidelity track

## Implementation Status

- Done: phase 1 forensic guardrails were implemented in the real-document harness for extracted and processed image assets.
- Done: phase 3 config externalization started with a centralized image-output policy and runtime wiring for generation/restore paths.
- Done: per-image source forensic metadata now includes drawing container type, `a:srcRect` presence/value, drawing doc properties, and source hashes in validation reports.
- Done: phase 4 trim hardening.
- Done: phase 6 size-selection moved from rigid 3-way logic toward policy-driven nearest-size selection with configurable candidate lists.
- Done: phase 5 OOXML crop reapplication during reinsertion now restores `a:srcRect` and preserved `docPr` metadata on output drawings.
- Done: phase 2 untouched-image delivery fidelity now restores preserved drawing geometry for untouched images, including `a:srcRect`, source `docPr`, and source `wp:anchor` container XML when available.

---

## 1. Problem Statement

Images from the Lietaer document (`tests/sources/Лиетар глава1.docx`) are visually cropped in the output DOCX. The attached screenshot shows a table where the left column is cut off: "onnectednesss" instead of "Connectedness", "esthetic Enjoymemt" instead of "Aesthetic Enjoyment", etc.

Important diagnostic correction: the **latest validated Lietaer run** used the `ui-parity-default` profile, which does **not** override `image_mode`, so it inherits `image_mode_default = "no_change"` from `config.toml`. That means the primary defect visible in the latest run cannot come from semantic redraw trimming or generated-image restore logic, because those paths were not executed for that run.

Additional forensic correction after inspecting both the source DOCX and the validated DOCX from run `20260324T165421Z_33817_1`:

- the large table image payload is **byte-identical** in source and output,
- its visible `wp:extent` is identical in source and output,
- neither the source nor the output drawing contains `a:srcRect`,
- the extracted source raster is visually intact.

Therefore, the previous explanation that the latest Lietaer screenshot is caused by `a:srcRect` loss is **not supported for this specific artifact**.

Important scope note: if the clipped screenshot came from a **manual run with `semantic_redraw_structured` enabled**, then it belongs to a different branch than the inspected latest validation artifact. In that branch, the relevant path is the structured image reconstruction flow (`diagram_semantic_redraw` → `deterministic_reconstruction`), not the `no_change` passthrough lane.

Accordingly, the problems below must be separated into:

1. **Confirmed fidelity gaps** — real source/output differences found in the current pipeline.
2. **Unconfirmed screenshot cause** — the attached clipping screenshot is not yet reproduced by an OOXML/media delta in the inspected latest artifact.
3. **Adjacent hardening risks** — real issues in semantic redraw / generated-image paths, but not the cause of the latest `ui-parity-default` regression.

### Confirmed Fidelity Gap F1: Lossy passthrough architecture for untouched images

For `image_mode = "no_change"`, the pipeline preserves the original image bytes, but it does **not** preserve the original Word drawing contract. Instead, extraction keeps only the embedded bytes plus visible `wp:extent` dimensions, and reinsertion recreates the picture through `python-docx` `add_picture()`.

That is a lossy reconstruction of the original OOXML drawing because the original drawing may carry additional semantics beyond width and height, including anchor/inline settings, crop metadata, and other picture-level geometry.

This gap is confirmed by the inspected Lietaer run: at least one source image changed drawing container type from `wp:anchor` in the source to `wp:inline` in the output. That is a real no-change fidelity regression even though it does not explain the specific large table screenshot.

### Unconfirmed Screenshot Cause U1: Missing drawing semantics beyond bytes and extents

The current evidence does **not** prove that the screenshot defect comes from changed image bytes, changed extents, or missing `a:srcRect` on the large table image. The screenshot may instead come from a different renderer, a different artifact than the inspected run, or another drawing-level property not yet compared.

The correct engineering response is to add forensic checks and reproduction hooks before claiming a single root cause for that screenshot.

### Conditional Fidelity Gap F2: Missing OOXML `a:srcRect` crop preservation

When Word displays an image with cropping, it stores `a:srcRect` metadata (left/top/right/bottom percentages) alongside `wp:extent` (visible display dimensions). The current extraction reads `wp:extent` correctly but **ignores** `a:srcRect`. During reinsertion, `python-docx`'s `add_picture()` receives the **full uncropped image bytes** with the **post-crop display dimensions**, causing the image to be squeezed/distorted rather than properly cropped.

**Location:** [document.py#L499-L500](document.py#L499-L500) — explicit comment: *"Word-native crop metadata such as a:srcRect is not extracted/reapplied yet."*

This remains a legitimate fidelity gap for source documents that do use Word crop metadata, but it is **not confirmed in the inspected Lietaer source artifact**.

### Adjacent Hardening Risk H1: Aggressive outer-padding trimming

`_trim_generated_outer_padding()` in `image_generation.py` uses a hardcoded pixel-difference threshold of **12** and re-adds only **1% padding** (min 2px). For images with light-colored content near the edges (common in tables/diagrams), the threshold is too aggressive — it detects table cell borders or light text as "background" and trims them away.

**Location:** [image_generation.py#L1230-L1255](image_generation.py#L1230-L1255)

This is a valid hardening target for semantic redraw and generated-image restore paths, but it is **not** the primary explanation for the latest `no_change` run.

### Adjacent Hardening Risk H2: API generation at fixed sizes with lossy aspect-ratio mapping

`_select_generate_size()` maps any source image to one of three fixed API sizes: `1024x1024`, `1536x1024`, or `1024x1536`. The aspect-ratio thresholds (1.2 and 1/1.2) are coarse. A table image that is 1400×900 (ratio 1.55) gets generated at 1536×1024 — close enough — but a 1200×900 (ratio 1.33) also maps to 1536×1024, causing a bigger aspect mismatch. The subsequent restore flow then fits the API output back into the original dimensions, potentially losing edge content.

**Location:** [image_generation.py#L1158-L1167](image_generation.py#L1158-L1167)

There is already targeted test coverage for preserving edge content in the structured generated path, so this area is better described as ongoing hardening than as the primary defect behind the latest run artifact.

### Adjacent Hardening Risk H3: Deterministic reconstruction can clip content when scene-graph geometry is too tight

For diagram/table images classified as `diagram_semantic_redraw`, the preferred structured path is `deterministic_reconstruction`. In that flow, a VLM first emits a scene graph with explicit canvas size, element coordinates, and table-cell text; then `image_reconstruction.py` renders that scene graph onto a fixed canvas.

If the extracted geometry for the leftmost column is even slightly too far left, or if cell widths are underestimated, the renderer has no final overflow-correction pass that expands the canvas or shifts elements back into view. That makes left-edge clipping of first characters a plausible failure mode for structured redraw screenshots like the one provided by the user.

### Cross-Cutting Improvement C1: Hardcoded size constants scattered across modules

Image sizing parameters (API size selection, trim thresholds, padding ratios, reconstruction canvas limits, background detection thresholds) are hardcoded as magic numbers in `image_generation.py` and `image_reconstruction.py`. This makes tuning impossible without code changes and prevents per-document or per-image-type adjustments.

### Preserved Structured-Redraw Analysis

The earlier four-point analysis must remain part of the specification, but it should be scoped to the **structured redraw / generated-image hardening track**, not to the confirmed `no_change` diagnosis.

For the structured redraw family of paths, the following remain valid engineering concerns:

1. **Aggressive trim in `_trim_generated_outer_padding()`**
    - pixel-difference threshold = `12`,
    - restored safety padding = `1%` with a minimum of `2px`,
    - light table borders and near-edge content can be misread as background.
2. **Missing OOXML crop metadata support (`a:srcRect`)**
    - extraction currently preserves bytes + `wp:extent`,
    - `a:srcRect` is ignored,
    - for documents that do rely on Word crop metadata, reinsertion can become visually inaccurate.
3. **Rigid API generation sizes**
    - `_select_generate_size()` still maps to `1024x1024`, `1536x1024`, or `1024x1536`,
    - aspect-ratio mismatch can still force lossy restoration decisions in generated-image paths.
4. **Hardcoded image parameters**
    - trim thresholds, padding ratios, API size lists, and related limits remain hardcoded,
    - tuning still requires code changes instead of config changes.

In other words: the original A/B/C/D analysis was **not wrong as a hardening plan**. What changed is only the attribution: it is no longer presented as the proven explanation for the inspected latest `no_change` run.

---

## 2. Current State of Affected Code

### 2.1 Hardcoded constants in `image_generation.py`

| Constant | Value | Purpose |
|----------|-------|---------|
| Trim pixel threshold | `12` | Background detection sensitivity |
| Trim padding ratio | `0.01` (1%) | Re-added padding after trim |
| Trim padding minimum | `2` px | Minimum padding floor |
| Corner patch size | `min(w,h) // 16` | Background color sampling |
| Aspect ratio thresholds | `1.2` / `1/1.2` | Landscape/portrait API size selection |
| Dark background ceiling | `40.0` | Mean RGB for "dark" background detection |
| Background distance threshold | `48` | Connected-background mask tolerance |

### 2.2 Hardcoded constants in `image_reconstruction.py`

These are already partially configurable via `config.toml` and `render_config` dict:

| Constant | Default | config.toml key |
|----------|---------|-----------------|
| `min_canvas_short_side_px` | 900 | `reconstruction_min_canvas_short_side_px` |
| `target_min_font_px` | 18 | `reconstruction_target_min_font_px` |
| `max_upscale_factor` | 3.0 | `reconstruction_max_upscale_factor` |
| `background_sample_ratio` | 0.04 | `reconstruction_background_sample_ratio` |
| `background_color_distance_threshold` | 48.0 | `reconstruction_background_color_distance_threshold` |
| `background_uniformity_threshold` | 10.0 | `reconstruction_background_uniformity_threshold` |

### 2.3 API size selection in `image_generation.py`

- `_select_generate_size()` — hardcoded 3-way switch
- `_extract_supported_size_fallback()` — hardcoded candidate list for edit API
- `_extract_supported_generate_size_fallback()` — hardcoded candidate list for generate API

### 2.4 Image reinsertion in `image_reinsertion.py`

- `_build_picture_size_kwargs()` applies original EMU extents to the inserted image
- Images are re-created through `Run.add_picture(...)`, not passed through as original drawing XML
- No crop metadata is applied to the OOXML output
- The inspected Lietaer run shows a real geometry drift: one image changed from `anchor` to `inline`

### 2.5 Image extraction in `document.py`

- `_extract_run_element_images()` reads blip bytes + `wp:extent` EMU dimensions
- `_resolve_drawing_extent_emu()` reads only `cx` and `cy`
- `a:srcRect` is explicitly not extracted

### 2.6 Existing test coverage that changes the diagnosis

- `tests/test_image_generation.py` already contains regression coverage for preserving edge content in the structured generated path.
- There is currently no equivalent no-change / OOXML crop-fidelity regression proving that source drawing crop semantics survive extraction and reinsertion.
- There is also no no-change forensic assertion for media hash, extent, or container-type drift.
- Therefore the most important missing protection is in the passthrough / forensic lane, not in the generated-image lane.

---

## 3. Proposed Changes

### Phase 1: Add forensic guardrails and reproduce the screenshot path

This phase is mandatory before any large refactor because the currently attached screenshot is not yet explained by the inspected latest artifact.

**Implementation goals:**

1. Extend the real-document validation harness to record per-image forensic data for `no_change` runs:
    - embedded media hash,
    - visible `wp:extent`,
    - drawing container type (`inline` vs `anchor`),
    - presence/absence of `a:srcRect`,
    - picture description.
2. Add a regression assertion that `no_change` preserves media bytes for accepted-original images.
3. Add a regression assertion that container-type drift is either prevented or explicitly reported.
4. If the screenshot is produced through a specific renderer or preview path, capture that path in the validation artifact set so the defect becomes reproducible rather than anecdotal.

This phase does not replace the refactor. It prevents solving the wrong problem.

### Phase 2: Preserve source drawing fidelity for untouched images

This phase addresses the confirmed no-change fidelity gap: untouched images currently do not preserve the original drawing contract.

**Preferred architecture:** for `no_change` and any final decision that resolves to the untouched original image, preserve the original drawing contract as first-class data instead of reconstructing it from bytes plus width/height.

**Recommended implementation direction:**

1. Extend extraction to capture source drawing placement metadata as a dedicated structure, for example `ImagePlacement` or `SourceDrawingGeometry`.
2. Store at minimum:
    - visible extent (`wp:extent`),
    - crop rect (`a:srcRect`),
    - whether the source drawing was inline vs anchor,
    - any picture description already present on the source drawing.
3. Prefer reinserting untouched images by recreating the drawing from preserved geometry metadata rather than relying on `python-docx add_picture()` defaults.
4. If full source-drawing passthrough proves too brittle, the minimum acceptable implementation is explicit `a:srcRect` round-tripping plus extent preservation.

Status update: implemented. Reinsertion restores preserved `a:srcRect`, source `docPr` metadata, and source `anchor` container geometry for untouched images.

This keeps the repository aligned with the architectural rule: fix the durable contract, not just the local symptom.

### Phase 3: Externalize image sizing parameters to `config.toml`

**New `[image_output]` section in `config.toml`:**

```toml
[image_output]
# --- Outer padding trim ---
trim_pixel_threshold = 12          # 0–255; lower = more aggressive trim
trim_padding_ratio = 0.02          # ratio of image dimension added back as safety padding
trim_padding_min_px = 4            # absolute minimum padding in pixels

# --- API generation size ---
# Preferred output sizes for the OpenAI images API.
# The pipeline selects the closest match by aspect ratio.
api_generate_sizes = ["1536x1024", "1024x1536", "1024x1024"]
api_edit_sizes = ["1536x1024", "1024x1536", "1024x1024", "512x512", "256x256"]
aspect_ratio_landscape_threshold = 1.2    # ratio >= this → landscape
aspect_ratio_portrait_threshold = 0.833   # ratio <= this → portrait (1/1.2)

# --- Background detection ---
background_dark_ceiling = 40.0     # mean RGB ≤ this → "dark" background
background_distance_threshold = 48 # color distance for connected mask
corner_patch_divisor = 16          # patch = min(w,h) // this
```

**Implementation:** Add new `AppConfig` fields, wire them through the parsing layer, pass to `image_generation.py` functions.

**Module boundary change:** Functions that currently use hardcoded constants (`_trim_generated_outer_padding`, `_select_generate_size`, `_restore_semantic_output`, `_restore_generated_output`, `_pick_generated_background_color`) will accept an `image_output_config` parameter (a dataclass or typed dict) instead of using module-level constants.

### Phase 4: Fix aggressive trim threshold (Hardening Risk H1)

Status: implemented in the current slice.

1. **Raise default `trim_pixel_threshold`** from `12` to `20` — reduces false-positive edge trimming for light table borders.
2. **Raise default `trim_padding_ratio`** from `0.01` (1%) to `0.02` (2%) — provides more safety margin.
3. **Raise default `trim_padding_min_px`** from `2` to `4`.
4. Add a **content-aware guard**: if the trimmed bounding box removes more than 15% of any single dimension, skip the trim entirely and return the original image. This prevents catastrophic edge cropping for content-heavy images like tables.

**Location:** `_trim_generated_outer_padding()` in `image_generation.py`.

### Phase 5: Preserve `a:srcRect` crop metadata as the minimum geometry contract

1. **Extraction** (`document.py`): Read `a:srcRect` (attributes: `l`, `t`, `r`, `b` — percentages as integers 0–100000 representing thousandths-of-a-percent) from the `<pic:blipFill>/<a:srcRect>` element.
2. **Carry** (`models.py`): Carry source drawing crop/doc metadata with the image asset so untouched delivery can restore Word geometry semantics.
3. **Reapply** (`image_reinsertion.py`): After `add_picture()`, inject the `a:srcRect` element into the picture's `<pic:blipFill>` XML node and restore preserved `docPr` metadata. This restores the original Word cropping behavior without modifying the image bytes.

**Architectural note:** this is the minimum acceptable fix if full source-drawing passthrough is not implemented in Phase 2.

Status update: implemented.

**Not recommended as the primary design:** pre-cropping image bytes during extraction to match the crop rect. That would simplify reinsertion but would silently redefine the source asset contract and make future variants operate on an already-cropped raster.

### Phase 6: Improve API size selection (Hardening Risk H2)

1. Add a `preferred_output_long_side` config parameter (default: `1536`) that controls the target long dimension for API-generated images.
2. Instead of a rigid 3-way switch, select the API size that is closest to the source aspect ratio from the `api_generate_sizes` list.
3. Preserve the existing `_extract_supported_size_fallback` mechanism as a runtime constraint from the API.

---

## 4. Module Boundaries & Dependency Direction

```
config.toml
    ↓ (parsed by)
config.py  →  AppConfig (with new image_output fields)
    ↓ (consumed by)
image_pipeline.py  →  passes image_output_config to:
    ├── image_generation.py  (trim, restore, size selection)
    ├── image_reconstruction.py  (render_config — already wired)
    └── image_reinsertion.py  (source geometry / crop reapplication)

document.py  →  extracts source geometry metadata into ImageAsset
models.py  →  ImageAsset gains crop_rect and source-geometry metadata
```

No new modules are required. Existing public APIs can remain backward-compatible by adding optional metadata fields and helper parameters.

---

## 5. Consumer Update Plan

### 5.1 `config.toml`
- Add `[image_output]` section with documented defaults.

### 5.2 `config.py`
- Add fields to `AppConfig` for the new `[image_output]` parameters.
- Add corresponding parse functions in `load_config()`.

### 5.3 `image_generation.py`
- Replace hardcoded constants with config-driven values.
- Refactor `_trim_generated_outer_padding()` to accept config and add content-aware guard.
- Refactor `_select_generate_size()` to use config-driven size list and thresholds.
- Refactor `_restore_semantic_output()` / `_restore_generated_output()` to accept config.
- Refactor `_pick_generated_background_color()` to accept config.

### 5.4 `document.py`
- Add a helper to extract source drawing geometry metadata for passthrough fidelity.
- Add `_extract_crop_rect()` helper to read `a:srcRect` from drawing XML.
- Pass result to `ImageAsset` constructor.

### 5.5 `models.py`
- Add `crop_rect: tuple[int, int, int, int] | None = None` to `ImageAsset`.
- Add a source-geometry field suitable for no-change reinsertion fidelity.

### 5.6 `image_reinsertion.py`
- Prefer source-geometry-aware reinsertion for untouched images.
- After `add_picture()`, inject `a:srcRect` into the OOXML if `asset.crop_rect` is not None.

### 5.7 `image_pipeline.py`
- Thread the new `image_output_config` through the pipeline entry points.

---

## 6. What Does NOT Change

- The `image_reconstruction.py` render config mechanism (already properly wired to `config.toml`).
- The high-level semantic meaning of `no_change` remains the same: untouched images should still be delivered without model-side transformation.
- The image analysis/validation pipeline (`image_analysis.py`, `image_validation.py`).
- The image prompt system (`image_prompts.py`, registry).
- The Streamlit UI layer.
- The document processing pipeline (`document_pipeline.py`) beyond threading config.
- The startup performance contract.
- The test workflow contract.

---

## 7. Verification Criteria

1. **Unit tests** for no-change forensic extraction: source/output drawing metadata comparison must detect media hash drift, extent drift, and container-type drift.
2. **Unit tests** for no-change extraction/reinsertion round-trip: untouched images must preserve the intended drawing contract for the supported metadata subset.
3. **Unit tests** for `a:srcRect` extraction and reinsertion round-trip.
4. **Unit tests** for `_trim_generated_outer_padding` with table-like images (light borders on white background) — verify no content loss beyond configurable threshold.
5. **Unit tests** for `_select_generate_size` with the full range of aspect ratios — verify correct size selection against configurable size list.
6. **Integration test**: process `tests/sources/Лиетар глава1.docx` under the default `ui-parity-default` path and assert the recorded forensic metadata for all images.
7. **Integration test**: process `tests/sources/Лиетар глава1.docx` with `image_mode=semantic_redraw_structured`, verify that table images remain free of unintended edge cropping in the redraw path.
8. **Existing test suite passes:** `bash scripts/test.sh tests/ -q`.
9. **Config defaults produce identical behavior to current hardcoded values** for semantic redraw tuning paths before defaults are intentionally changed.

---

## 8. Recommended Phase Order

| Phase | Scope | Risk | Effort |
|-------|-------|------|--------|
| **1** | Forensic guardrails for `no_change` | Low — additive diagnostics and tests | Low-Medium |
| **2** | Source drawing fidelity for `no_change` | Medium — metadata plumbing / OOXML handling | Medium-High |
| **3** | Config externalization | Low — additive, backward-compatible | Medium |
| **4** | Trim threshold fix | Low — default change + guard | Low |
| **5** | `a:srcRect` preservation minimum fix | Medium — OOXML manipulation | Medium |
| **6** | Smarter API size selection | Low — algorithm change | Low |

**Recommended:** start with Phase 1 immediately to turn the screenshot complaint into a reproducible, testable artifact. Then do Phase 2 to address the confirmed no-change fidelity gap. Phases 3-6 remain valid hardening work, but they should not be presented as the proven fix for the latest Lietaer screenshot until the reproduction path is closed.

## 9. Completion Note

Post-implementation verification confirms that this focused sizing/crop-fidelity track is closed in the current codebase:

- forensic extraction/reporting for source drawing metadata is covered;
- untouched-image reinsertion restores preserved source geometry semantics including `a:srcRect` and source anchor metadata where available;
- image-output policy is centralized and wired through generation/restore paths;
- trim hardening and policy-driven size selection are covered by the current test suite;
- the latest visible full-suite verification passed.
