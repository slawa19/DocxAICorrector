# Model Role And Configuration Spec

Date: 2026-04-18

## Goal

Document the canonical role-to-model policy for the centralized model registry.

This specification defines:

1. which runtime roles exist in the project model registry
2. which models are currently assigned to those roles
3. which roles are user-facing versus service-level
4. how model policy should be updated without reintroducing configuration drift

This document is policy and documentation only. The architectural ownership and migration rules for config loading are governed by the centralized model-registry refactor specification and by the current implementation in `config.py`.

## Canonical Configuration Contract

The project now uses one canonical registry shape for model assignment.

Canonical baseline in `config.toml`:

```toml
[models.text]
default = "gpt-5.4-mini"
options = [
  "gpt-5.4",
  "gpt-5.4-mini",
  "gpt-5-mini",
]

[models.structure_recognition]
default = "gpt-5-mini"

[models.image_analysis]
default = "gpt-5.4-mini"

[models.image_validation]
default = "gpt-5.4-mini"

[models.image_reconstruction]
default = "gpt-5.4-mini"

[models.image_generation]
default = "gpt-image-1.5"

[models.image_edit]
default = "gpt-image-1.5"

[models.image_generation_vision]
default = "gpt-5.4-mini"
```

Canonical env override naming:

```env
DOCX_AI_MODELS_TEXT_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_TEXT_OPTIONS=gpt-5.4,gpt-5.4-mini,gpt-5-mini
DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT=gpt-5-mini
DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT=gpt-5.4-mini
```

Important rules:

1. `models.*` is the only canonical configuration surface for model names.
2. Runtime modules must not define their own production model defaults.
3. Legacy keys such as `default_model`, `model_options`, `validation_model`, `reconstruction_model`, and `[structure_recognition].model` are migration-only inputs handled inside `config.py`.
4. `constants.py` is no longer part of the model configuration contract.

## Role Matrix

### User-facing text roles

These are the models exposed in the sidebar through `models.text.options`.

| Role | Model | Status | Notes |
| --- | --- | --- | --- |
| Main premium text transform | `gpt-5.4` | `recommended_high_quality` | Premium option for users who prioritize output quality over cost. |
| Main default text transform | `gpt-5.4-mini` | `recommended_default` | Current canonical default in `models.text.default`. |
| Budget text fallback | `gpt-5-mini` | `supported_fallback` | Lower-cost fallback that remains supported. |
| Budget text fallback | `gpt-5-mini` | `supported_fallback` | Lower-cost fallback that remains in the canonical sidebar shortlist. |

### Service-level roles

These roles are resolved from the centralized registry and are not selected directly by end users in the sidebar.

| Role | Model | Status | Notes |
| --- | --- | --- | --- |
| Structure recognition | `gpt-5-mini` | `balanced_cost_quality` | Optional stage during preparation; moved to a cheaper modern GPT-5 tier. |
| Pipeline image analysis | `gpt-5.4-mini` | `balanced_cost_quality` | Explicit role `models.image_analysis.default`; balanced multimodal default for routing and vision analysis. |
| Image validation | `gpt-5.4-mini` | `balanced_cost_quality` | Explicit role `models.image_validation.default`; keeps validator quality without full flagship pricing. |
| Image reconstruction | `gpt-5.4-mini` | `balanced_cost_quality` | Explicit role `models.image_reconstruction.default`; balanced choice for text-sensitive scene-graph extraction. |
| Image generation | `gpt-image-1.5` | `balanced_cost_quality` | Explicit role for `Images.generate`; refreshed image-native baseline. |
| Image editing | `gpt-image-1.5` | `balanced_cost_quality` | Explicit role for `Images.edit`; aligned with generation baseline. |
| Generation-time image vision | `gpt-5.4-mini` | `balanced_cost_quality` | Explicit role for vision calls inside generation/edit orchestration. |

## Design Principles

The role matrix must follow these rules:

1. Distinguish UI-facing text model choice from service-level pipeline model assignment.
2. Keep role identity explicit even when multiple roles currently use the same model string.
3. Treat `recommended_default`, `supported_fallback`, and `stable_keep_for_now` as policy labels, not as separate configuration layers.
4. Keep the canonical docs synchronized with `config.toml`, `.env.example`, `README.md`, and `config.py`.
5. Do not document runtime-owned fallbacks as if they were part of the supported contract.

## Balanced Refresh Policy

The current balanced refresh intentionally moves the canonical baseline away from GPT-4-family defaults for active production roles.

That means:

1. `gpt-5.4-mini` is the default balanced multimodal tier for text-sensitive service roles
2. `gpt-5-mini` is the lower-cost balanced choice for structure recognition
3. `gpt-image-1.5` is the refreshed image-native baseline for generation and edit
4. older GPT-4-family models may remain migration-compatible inputs, but they are no longer the recommended canonical defaults

## Experimental Model Handling

Experimental models are intentionally not part of the canonical repository baseline unless they are promoted into the centralized registry.

Operational rules:

1. experimental models do not appear in canonical `config.toml` defaults unless the project explicitly adopts them
2. experimental models must not silently replace stable defaults in docs or examples
3. if an experiment proves useful, the next step is to add or update an explicit role in the centralized registry rather than a runtime-only override

For the current project shape, this means `gpt-image-1-mini` may be discussed as a future experiment, but the balanced canonical baseline remains `gpt-image-1.5`.

## Sync Rules

Any future model refresh must update all relevant layers together.

At minimum, a model-role change must review:

1. `config.toml`
2. `.env.example`
3. `README.md`
4. `config.py`
5. UI code that renders `models.text.options` and `models.text.default`
6. tests asserting exact role assignments or available text options

Anti-drift rules:

1. canonical production model literals must stay confined to approved config-loading and documentation surfaces
2. runtime modules must continue consuming resolved role values rather than hardcoded model names
3. legacy aliases may remain only as migration-compatible config-loader inputs, never as a second canonical contract

## Acceptance Criteria

This specification is considered implemented when:

1. the repository documents one centralized role-based registry shape
2. `README.md` reflects that registry shape
3. `.env.example` reflects the canonical env naming scheme
4. the docs distinguish user-facing text options from service-level model roles
5. the docs explicitly describe the balanced GPT-5 and GPT Image 1.5 baseline per role
6. no canonical docs present legacy mixed-shape keys as the active repository baseline

## Summary

The repository now has an explicit role-based model policy built on the centralized registry.

The current recommendation is:

1. keep `gpt-5.4-mini` as the default text model
2. keep `gpt-5.4` as the premium text option
3. keep `gpt-5-mini` as the lower-cost text fallback and structure-recognition model
4. use `gpt-5.4-mini` across image analysis, validation, reconstruction, and generation-time vision
5. use `gpt-image-1.5` for image generation and edit

This keeps model refreshes auditable and prevents the project from drifting back to mixed configuration ownership.
