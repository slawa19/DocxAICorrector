# Centralized Model Registry Refactor Spec

Date: 2026-04-18
Status: Implemented on 2026-04-18; archived historical design record

Archive note:

1. The centralized role-based registry is implemented in `config.py`, `config.toml`, `.env.example`, runtime consumers, and targeted regression coverage.
2. The maintained source of truth now lives in the active configuration contract: `config.toml`, `config.py`, `README.md`, and `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md`.
3. This document is preserved as the historical implementation record and should not be treated as an active work target.

## Goal

Refactor model configuration so the project has one architectural source of truth for all OpenAI model assignments by runtime role.

This specification defines a practical migration from the current mixed configuration shape to a centralized role-based model registry that:

1. keeps user-facing text model selection explicit
2. keeps service-level model roles explicit
3. removes hardcoded model literals from runtime modules
4. makes model refreshes safe, auditable, and low-drift
5. preserves a staged migration path without forcing a single breaking rewrite

This is an architecture and configuration refactor. It does not, by itself, require changing the currently chosen models for any role.

## Problem Statement

The repository currently stores model decisions across too many layers:

1. `config.toml`
2. `.env.example`
3. `.env`
4. `README.md`
5. `constants.py`
6. `config.py`
7. module-level constants in image modules
8. inline fallback literals in runtime request builders

This means the project does not have a single canonical runtime authority for model names.

Today the same conceptual decision can appear in multiple forms:

1. canonical config baseline in `config.toml`
2. fallback baseline in `constants.py`
3. parsing defaults in `config.py`
4. local service defaults in `image_generation.py` or `image_reconstruction.py`
5. last-mile inline fallbacks such as `model or "gpt-4.1"`

This creates several concrete problems:

1. model drift when one layer changes but another is forgotten
2. hidden coupling when one config key implicitly drives multiple roles
3. difficult migrations because updates require editing many files by hand
4. unclear ownership because runtime modules partially define configuration policy themselves
5. false resilience because silent fallbacks can preserve stale model literals long after the canonical config changes

Concrete current-repository example:

1. `config.toml` currently uses `default_model = "gpt-5.4-mini"`
2. `constants.py` still exposes `DEFAULT_MODEL = "gpt-5-mini"`
3. `.env.example` still documents `DOCX_AI_DEFAULT_MODEL=gpt-5-mini`

This is exactly the kind of real drift the refactor must eliminate rather than merely describe.

The current arrangement worked while the project was smaller, but it is no longer architecturally sound for a multi-stage DOCX pipeline with separate text, structure, validation, reconstruction, vision, and image-generation responsibilities.

## Desired Outcome

After this specification is implemented:

1. all model names used by runtime logic originate from one centralized registry in config loading
2. runtime modules do not define their own default model names
3. runtime modules do not contain inline model fallback literals
4. model roles are explicit even when two roles temporarily use the same model value
5. env overrides preserve the same role-based structure as the canonical config
6. docs and tests reference one configuration contract rather than scattered implementation details

The result should make model refreshes routine, predictable, and reviewable.

## Non-Goals

This specification does not require:

1. immediate migration of all `gpt-4.*` service roles to the `gpt-5.*` family
2. automatic model discovery from the OpenAI API
3. dynamic model routing based on cost, latency, or benchmarks
4. support for non-OpenAI providers
5. changing prompt contracts or pipeline semantics unrelated to configuration ownership
6. collapsing image generation models and text or vision models into one shared abstraction

## Current State

### Current configuration shape

Current model-related configuration is split across at least four distinct patterns:

1. top-level text model settings:
   - `default_model`
   - `model_options`
2. nested structure-recognition setting:
   - `[structure_recognition].model`
3. top-level service keys:
   - `validation_model`
   - `reconstruction_model`
4. code-only image constants:
   - `IMAGE_GENERATE_MODEL`
   - `IMAGE_EDIT_MODEL`
   - `IMAGE_STRUCTURE_VISION_MODEL`

### Current code-level fallback sources

The repository currently contains model-name defaults outside canonical config:

1. `constants.py`
   - `DEFAULT_MODEL`
   - `DEFAULT_MODEL_OPTIONS`
2. `config.py`
   - `structure_recognition_model` default literal
   - `validation_model` default literal
   - `reconstruction_model` default literal
3. `image_generation.py`
   - `IMAGE_EDIT_MODEL`
   - `IMAGE_GENERATE_MODEL`
   - `IMAGE_STRUCTURE_VISION_MODEL`
   - inline fallback `reconstruction_model or "gpt-4.1"`
4. `image_reconstruction.py`
   - `DEFAULT_RECONSTRUCTION_MODEL`
5. `image_analysis.py`
   - inline fallback `model or "gpt-4.1"`
6. `image_validation.py`
   - inline fallback `model or "gpt-4.1"`
7. `image_pipeline.py`
   - `_config_str(self.config, "validation_model", "gpt-4.1")` in the validation path

### Current role-coupling issue

The repository currently has at least one model-role coupling that is real runtime behavior but not cleanly represented in configuration:

1. `image_pipeline.py` currently uses `validation_model` for both:
   - pipeline image analysis
   - image validation

This means the repository does not yet fully distinguish:

1. model identity
2. role identity
3. config-key identity

That is the core architectural smell this refactor is intended to fix.

## Architectural Principles

The refactor must follow these rules:

1. Configuration ownership belongs in `config.toml`, `.env`, and `config.py`, not in service modules.
2. Runtime roles must remain explicit even if two roles currently share one model value.
3. A module may consume a model value, but must not define the canonical default for that value.
4. Silent hardcoded fallback literals in runtime request payloads are forbidden after migration.
5. Backward compatibility may exist during migration, but only inside the config-loading layer.
6. The centralized registry must describe both user-facing and service-level roles.
7. Image generation models remain a separate role family from text or vision models.

## Proposed Configuration Design

### Canonical model registry in `config.toml`

Introduce one explicit section for model roles.

Recommended canonical shape:

```toml
[models.text]
default = "gpt-5.4-mini"
options = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini"]

[models.structure_recognition]
default = "gpt-4o-mini"

[models.image_analysis]
default = "gpt-4.1"

[models.image_validation]
default = "gpt-4.1"

[models.image_reconstruction]
default = "gpt-4.1"

[models.image_generation]
default = "gpt-image-1"

[models.image_edit]
default = "gpt-image-1"

[models.image_generation_vision]
default = "gpt-4.1"
```

Design notes:

1. `text.default` and `text.options` replace the current top-level `default_model` and `model_options` as the long-term canonical location.
2. `structure_recognition.default` replaces `[structure_recognition].model` as the long-term canonical source for the model name only.
3. `image_analysis.default` and `image_validation.default` are separate roles even if they temporarily share one value.
4. `image_generation_vision.default` makes the current `IMAGE_STRUCTURE_VISION_MODEL` role explicit in config.
5. `gpt-image-1` remains its own image-model family and is not normalized into a text-model role.
6. The resulting split between `[structure_recognition]` feature settings and `[models.structure_recognition]` model resolution is intentional, not accidental duplication.
7. After migration, `[structure_recognition]` must keep only feature-level controls such as mode, timeout, cache, and confidence policy; it must not remain a second source of truth for the model name.
8. `[models.structure_recognition]` must contain only model-resolution state and must not absorb feature-level operational settings.

### Related feature flags that stay outside the registry

Some config keys are tightly related to model usage but are not themselves model assignments.

Current examples include:

1. `enable_vision_image_analysis`
2. `enable_vision_image_validation`

These flags must remain outside `models.*`.

This specification refactors model ownership only. It does not move feature toggles, enablement flags, or other non-model policy knobs into the model registry.

### Why role identity must remain explicit

The registry must not compress multiple roles into a single key just because they currently use the same string.

For example, this is architecturally wrong:

```toml
[models.image_service]
default = "gpt-4.1"
```

because it hides distinct responsibilities:

1. image analysis
2. image validation
3. image reconstruction
4. generation-time vision inspection

Those roles may diverge later, and the config shape should not block that separation.

## Proposed Python Configuration Design

### Current `AppConfig` constraint

The current repository already treats `AppConfig` as a `Mapping`-like object with dict-style access in production code and tests.

Examples of current usage include:

1. `app_config["default_model"]` in config tests
2. `app_config["validation_model"]` in config tests and consumers
3. `_config_str(self.config, "validation_model", ...)` in `image_pipeline.py`

Therefore this specification does not require a broad conversion of the whole config surface away from mapping-style access.

The migration must preserve the effective `Mapping[str, Any]` contract for `AppConfig` while introducing a centralized internal model registry.

### Mapping-preserving target shape

The preferred migration shape is:

1. `AppConfig` continues to behave as a mapping for compatibility
2. `models` is added as a nested resolved structure, available via `config["models"]` and attribute access if the implementation already supports it
3. legacy fields may remain available as derived aliases during migration
4. converting `AppConfig` to a strictly typed non-mapping object is out of scope unless specified by a separate refactor

### New typed registry structure

Add a dedicated typed model registry to `config.py`.

Recommended shape:

```python
@dataclass(frozen=True)
class TextModelConfig:
    default: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class ModelRegistry:
    text: TextModelConfig
    structure_recognition: str
    image_analysis: str
    image_validation: str
    image_reconstruction: str
    image_generation: str
    image_edit: str
    image_generation_vision: str
```

`AppConfig` should then expose the registry as a single field while preserving the current mapping contract:

```python
@dataclass(frozen=True)
class AppConfig:
    models: ModelRegistry
    ...
```

This snippet is illustrative of the nested registry shape, not a requirement to remove `Mapping` behavior from `AppConfig`.

### Compatibility access during migration

During migration, `AppConfig` may temporarily keep legacy convenience properties such as:

1. `default_model`
2. `model_options`
3. `structure_recognition_model`
4. `validation_model`
5. `reconstruction_model`

but these must become derived aliases from `models`, not independent sources of truth.

Example principle:

1. `AppConfig.models.image_validation` is canonical
2. `AppConfig.validation_model` is compatibility sugar only

The project must not continue treating both as independently configured values.

## Runtime Consumption Rules

### Mandatory rule

No runtime module may define a default model name for a production role after the refactor lands.

That means:

1. no `IMAGE_*_MODEL = "..."` production defaults in service modules
2. no `DEFAULT_RECONSTRUCTION_MODEL = "..."`
3. no payload expressions such as `model or "gpt-4.1"`

### Allowed runtime behavior

Runtime modules may do one of two things only:

1. receive an explicit model argument from orchestrating code
2. read a resolved model from the typed config object passed into the orchestration layer

If a required model is missing at runtime, the code must fail with a configuration error rather than silently falling back to a stale literal.

Example preferred behavior:

```python
if not model:
    raise RuntimeError("Image validation model is not configured.")
```

### Module impact

The following modules must stop owning model defaults:

1. `image_generation.py`
2. `image_reconstruction.py`
3. `image_analysis.py`
4. `image_validation.py`

The following modules may continue to own configuration parsing only:

1. `config.py`
2. potentially a new helper such as `model_registry.py` if the parsing logic becomes too large

## Env Override Design

### Long-term env contract

The env override surface should mirror role-based config structure rather than use an inconsistent mix of legacy names.

Recommended long-term env naming:

```env
DOCX_AI_MODELS_TEXT_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_TEXT_OPTIONS=gpt-5.4,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini
DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT=gpt-4o-mini
DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT=gpt-4.1
DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT=gpt-4.1
DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT=gpt-4.1
DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT=gpt-image-1
DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT=gpt-image-1
DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT=gpt-4.1
```

### Migration compatibility

The project may temporarily support legacy env names during migration, including:

1. `DOCX_AI_DEFAULT_MODEL`
2. `DOCX_AI_MODEL_OPTIONS`
3. `DOCX_AI_STRUCTURE_RECOGNITION_MODEL`
4. `DOCX_AI_VALIDATION_MODEL`
5. `DOCX_AI_RECONSTRUCTION_MODEL`

Compatibility rules:

1. new env names win if both new and legacy names are present
2. legacy env names are translated into the new registry inside `config.py`
3. runtime modules do not know whether a value came from legacy or canonical env keys

### Full source precedence during migration

The migration must define one explicit precedence order for every role:

1. canonical new env override
2. canonical new TOML registry value
3. legacy env override
4. legacy TOML value
5. migration-only default inside config-loading code

Rules:

1. precedence must be implemented uniformly per role, not ad hoc per field
2. legacy env must not override canonical new TOML if a canonical new value is present
3. runtime modules must receive only the resolved final value and must not implement their own fallback ordering
4. the same precedence policy must define what happens when a default model is absent from an explicit options list

## Backward-Compatible Migration Plan

This refactor should land in phases rather than as a single breaking rewrite.

### Phase 1: Introduce the centralized registry

Add `models.*` sections to `config.toml` and parsing support in `config.py`.

Requirements:

1. the new registry exists as the canonical internal representation
2. legacy keys remain readable during migration
3. `AppConfig` can still expose old convenience fields derived from the new registry
4. no behavior change is required yet for model values themselves

### Phase 2: Move runtime consumers to the registry

Update orchestration and service-call paths so model values come from resolved config rather than module constants.

Expected consumers include:

1. UI text model selection
2. structure-recognition runtime wiring
3. image analysis
4. image validation
5. image reconstruction
6. image generation
7. image edit
8. generation-time image vision calls

This phase must explicitly fix the current analysis or validation coupling in `image_pipeline.py`:

1. `ImagePipelineContext.analyze_image` must stop sourcing its model from `validation_model`
2. the analyze path must read the resolved `image_analysis` role instead
3. the validate path must read the resolved `image_validation` role instead

Even if both roles temporarily resolve to the same model string, they must be wired independently.

### Phase 3: Remove runtime-owned model defaults

Delete model-name literals from runtime modules.

This phase must remove:

1. `DEFAULT_MODEL` and `DEFAULT_MODEL_OPTIONS` from `constants.py`
2. production model constants from image modules
3. inline request-payload fallbacks for model names
4. reconstruction fallbacks such as `reconstruction_model or "gpt-4.1"` in `image_generation.py`

After this point, only config-loading code and documentation may contain canonical production model names.

### Phase 4: Deprecate legacy config surface

Once all consumers read from the registry and documentation is updated:

1. deprecate top-level `default_model`
2. deprecate top-level `model_options`
3. deprecate top-level `validation_model`
4. deprecate top-level `reconstruction_model`
5. deprecate `[structure_recognition].model` as the canonical source of the model name

This phase may preserve read-compatibility for one migration window, but new docs and examples must use the registry only.

## Detailed Responsibilities By Layer

### `config.toml`

Must become the canonical declarative source for all role-to-model mappings.

### `config.py`

Must become the only runtime authority that:

1. reads the model registry
2. applies env overrides
3. validates required role values
4. exposes typed resolved model assignments to the rest of the app
5. translates legacy keys during migration
6. emits enough resolved-state observability to make per-role model selection auditable in logs or diagnostics
7. applies one explicit policy for reconciling text default vs text options during migration

### `constants.py`

Should contain path and neutral scalar constants only.

It must stop acting as a hidden fallback model registry.

### Runtime service modules

Modules such as `image_generation.py`, `image_analysis.py`, `image_validation.py`, and `image_reconstruction.py` must consume resolved model values only.

They must not contain config policy.

### Documentation

`README.md`, `.env.example`, and model-role docs must reflect the centralized registry rather than a mixed legacy shape once the migration is complete.

## Validation Rules

The config loader must validate at least the following:

1. all configured model role values are non-empty strings
2. `models.text.options` is non-empty
3. `models.text.default` is present in `models.text.options`
4. required service-level roles are populated
5. no runtime path can proceed with an absent required model role
6. `models.text.options` contains no duplicate values

Migration-specific rule for text models:

1. the implementation must explicitly choose and document one behavior when the resolved text default is missing from the resolved text options
2. allowed behaviors are:
   - fail with a configuration error
   - auto-insert the resolved default into the resolved options list in a deterministic position
3. the project must not leave this behavior implicit or field-specific
4. if compatibility with the current loader behavior is desired, the spec recommends deterministic auto-insert with the resolved default placed first

Recommended additional validation:

1. emit a clear error if only some of a migration pair is configured inconsistently
2. optionally warn when legacy keys are used instead of canonical registry keys

## Observability Contract

Because the goal includes `auditable` configuration behavior, the implementation must expose resolved model assignments in an inspectable way.

At minimum, the application should make it possible to observe the resolved model per role at startup or config-load time.

Acceptable implementations include:

1. one structured log event with all resolved model roles
2. one config-diagnostics dump or debug artifact showing the final resolved registry
3. both of the above

Minimum contract for that observability:

1. the output must use stable role keys, for example `text.default`, `image_analysis`, `image_validation`, `image_reconstruction`, `image_generation`, `image_edit`, and `image_generation_vision`
2. the output must be emitted at a deterministic time, preferably during config resolution or application startup, not only deep inside a request path
3. when a resolved value comes from legacy env or legacy TOML translation, the observability output should indicate that source class
4. the output must omit secrets and credentials, but model names and source provenance must remain visible enough for diagnostics and CI verification

The implementation does not need to log sensitive credentials, but it must make role-to-model resolution visible enough to detect drift quickly.

## Sweep Test Contract

The repository should include one anti-regression sweep that verifies model literals do not reappear in runtime modules after the refactor.

Minimum requirements:

1. the sweep must operate on an explicit allow-list or deny-list, not an informal grep convention
2. approved locations for production model literals should be limited to canonical config-loading and documentation surfaces
3. runtime modules such as `image_generation.py`, `image_analysis.py`, `image_validation.py`, `image_reconstruction.py`, and `image_pipeline.py` must fail the sweep if they contain new canonical model string literals after the migration
4. the sweep must distinguish executable code from documentation, comments, or intentionally archived specs
5. the sweep must define whether test files are excluded or checked under a separate rule set

Recommended implementation options:

1. AST-based inspection for Python runtime modules
2. a pytest helper that scans only a defined set of production files
3. a hybrid of AST for Python and path-based filtering for non-Python files

## Documentation Contract

After the migration completes, project docs must reflect:

1. one canonical model registry shape in `config.toml`
2. one canonical env override naming scheme
3. an explicit distinction between role identity and current model equality
4. the rule that runtime modules do not own model defaults

The existing model-role document remains useful for policy and rationale, while this refactor specification governs architecture and configuration ownership.

## Risks And Tradeoffs

### 1. Migration complexity

Risk:

The project has several consumers and compatibility surfaces, so a full cutover may touch many files.

Mitigation:

Use a staged migration with compatibility only in `config.py`.

### 2. Over-designing for future roles

Risk:

The registry could become too abstract or attempt to predict every future model role.

Mitigation:

Model only currently real runtime roles plus the already-known generation-time vision role.

### 3. Hidden remaining literals

Risk:

One or two inline fallback strings survive the migration and reintroduce drift.

Mitigation:

Add targeted tests and a repository sweep that verifies `gpt-` literals do not remain in runtime modules outside approved config-loading locations.

### 4. Backward-compatibility drag

Risk:

Legacy fields remain indefinitely and the project never fully converges on the registry.

Mitigation:

Document legacy fields as migration-only and define an explicit deprecation phase.

## Verification Criteria

This specification is considered implemented when all of the following are true:

1. `config.toml` contains one canonical role-based model registry
2. `config.py` resolves all production model assignments from that registry
3. legacy keys, if still supported, are translated only inside the config-loading layer
4. runtime service modules no longer define production default model names
5. runtime request payloads no longer contain inline fallback literals such as `model or "gpt-4.1"`
6. `constants.py` no longer acts as a fallback source for model names
7. `README.md` and `.env.example` document the centralized registry rather than the old mixed shape
8. image analysis and image validation are represented as separate config roles even if they still share one model value
9. changing a model for any role requires editing only canonical config and documentation, not runtime module constants
10. resolved model assignments are observable in logs, diagnostics, or equivalent startup output

## Suggested Implementation Order

1. Add the `ModelRegistry` typed structure and parsing logic to `config.py`.
2. Add canonical `models.*` sections to `config.toml` while preserving migration compatibility.
3. Update `AppConfig` to expose registry-backed compatibility aliases.
4. Route all model-consuming runtime code through resolved config values.
5. Remove hardcoded model constants and inline fallback literals from runtime modules.
6. Fix `image_pipeline.py` so analysis and validation consume separate resolved roles.
7. Preserve non-model feature toggles such as `enable_vision_*` outside the registry.
8. Update `.env.example`, `README.md`, and tests to the canonical registry shape.
9. Add targeted tests that fail if model literals reappear outside approved locations.

## Implementation Checklist

### Priority 0: Lock the architectural contract

- [x] Confirm the centralized registry is the only long-term source of truth for model names.
- [x] Confirm backward compatibility is allowed only in `config.py`.
- [x] Confirm runtime modules must not contain production model defaults.
- [x] Confirm role identity remains explicit even when values match.

### Priority 1: Introduce the typed registry

- [x] Add `TextModelConfig` and `ModelRegistry` to `config.py`.
- [x] Add `models` field to `AppConfig`.
- [x] Parse canonical `models.*` sections from `config.toml`.
- [x] Validate required role values and text options.

### Priority 2: Add migration compatibility

- [x] Read legacy `default_model` and `model_options` only as migration inputs.
- [x] Read legacy `validation_model` and `reconstruction_model` only as migration inputs.
- [x] Read legacy `[structure_recognition].model` only as a migration input.
- [x] Translate legacy env names into registry values inside `config.py`.
- [x] Implement one explicit precedence order: new env > new TOML > legacy env > legacy TOML > config-loader default.

### Priority 3: Migrate runtime consumers

- [x] Update UI text model consumption to read from `config.models.text`.
- [x] Update `app.py` sidebar-setting consumers such as `_resolve_sidebar_settings` and related startup wiring to consume registry-backed text defaults.
- [x] Update structure-recognition wiring to read from `config.models.structure_recognition`.
- [x] Update image analysis to read from `config.models.image_analysis`.
- [x] Update image validation to read from `config.models.image_validation`.
- [x] Update reconstruction to read from `config.models.image_reconstruction`.
- [x] Update image generation/edit to read from `config.models.image_generation` and `config.models.image_edit`.
- [x] Update generation-time vision calls to read from `config.models.image_generation_vision`.
- [x] In `image_pipeline.py.analyze_image`, stop sourcing analysis from `validation_model` and switch to the explicit `image_analysis` role.
- [x] In `image_pipeline.py.validate_redraw_result`, keep validation wired to the explicit `image_validation` role only.

### Priority 4: Remove code-owned defaults

- [x] Remove `DEFAULT_MODEL` and `DEFAULT_MODEL_OPTIONS` from `constants.py`.
- [x] Remove module-level production model constants from image modules.
- [x] Remove inline fallback expressions for model names in request payloads.
- [x] Remove reconstruction fallback expressions such as `reconstruction_model or "gpt-4.1"` in `image_generation.py`.
- [x] Remove validation-path fallbacks such as `_config_str(self.config, "validation_model", "gpt-4.1")` in `image_pipeline.py`.
- [x] Replace silent fallbacks with explicit configuration errors where needed.

### Priority 5: Update docs and tests

- [x] Update `.env.example` to the registry-based env contract.
- [x] Update `README.md` configuration examples to the registry shape.
- [x] Update tests asserting config defaults and env overrides.
- [x] Update tests that currently assert against public module-level constants such as `image_generation.IMAGE_STRUCTURE_VISION_MODEL` to assert against resolved config or injected values instead.
- [x] Add tests that confirm no runtime module owns a production model default.
- [x] Add a repository sweep test or equivalent verification that rejects `gpt-` literals in runtime modules outside approved config-loading files.
- [ ] Introduce a centralized pytest fixture or helper for resolved model-role values so tests stop duplicating model names in scattered tuples and stubs.

### Priority 6: Finish deprecation

- [x] Mark legacy config fields as deprecated in docs.
- [ ] Remove legacy examples from canonical docs.
- [ ] Decide the removal point for migration-only aliases after the registry is stable.

## Implementation Review Snapshot

Review date: 2026-04-18

This review compared the current repository state against this specification across `config.py`, `config.toml`, runtime image modules, `README.md`, `.env.example`, and the current regression tests.

### Summary

The main refactor is largely implemented:

1. the typed centralized registry exists in `config.py`
2. canonical `models.*` sections exist in `config.toml`
3. runtime consumers read explicit roles instead of legacy shared keys
4. legacy compatibility is isolated to config loading
5. docs and tests were substantially updated to the new registry shape

The remaining work is mostly cleanup and anti-drift hardening rather than core architecture.

## Review Findings

### Finding 1: Canonical documentation is still internally inconsistent

Severity: medium

The repository still contains a canonical-looking document that describes the pre-refactor mixed model shape and even states that `constants.py` remains part of the configuration contract.

Concrete conflicts found during review:

1. `README.md:256` still points readers to `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md` as the canonical role-based model spec
2. `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md:95-111` still documents legacy service-level keys and image constants as the active specialized defaults
3. `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md:218-250` still presents `default_model`, `model_options`, `validation_model`, `reconstruction_model`, and `structure_recognition.model` as the repository baseline and says `constants.py` must stay synchronized

Why this matters:

1. it breaks the spec goal of one configuration contract
2. it reintroduces documentation drift even though runtime ownership is already centralized
3. it makes future model refreshes less auditable because two documents describe different sources of truth

### Finding 2: Runtime anti-drift sweep is weakened by an explicit literal allow-list and one remaining runtime model literal

Severity: medium

The sweep test exists, but it currently permits a canonical production model literal to remain in a runtime module.

Concrete locations:

1. `image_analysis.py:466-474` still contains the literal `"gpt-image-1"` in runtime branching logic
2. `tests/test_model_registry_sweep.py:22-24` explicitly allow-lists that literal for `image_analysis.py`

Why this matters:

1. the spec explicitly aims to keep canonical production model names out of runtime modules
2. the current allow-list makes the anti-regression sweep less strict than the architectural contract
3. future model refreshes still require remembering a runtime code path instead of only config and docs

### Finding 3: Test centralization is only partially complete

Severity: low

The repository now has a shared registry fixture, but model-role values are still duplicated across tests instead of consistently using one helper surface.

Concrete locations:

1. `tests/conftest.py:40-49` introduces `resolved_test_model_registry`
2. `tests/test_config.py:9-22`, `tests/test_config.py:54-105`, and multiple later assertions still duplicate concrete model names inline
3. several image tests still use direct `validation_model=` or `reconstruction_model=` arguments in stubs rather than a shared resolved registry fixture

Why this matters:

1. it leaves part of the old drift problem alive inside the test suite
2. bulk model refreshes still require touching many scattered tests
3. the checklist goal for centralized model-role test helpers is not yet fully achieved

## Review Follow-Up Checklist

### Documentation follow-up

- [x] Align `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md` with the centralized `models.*` registry architecture.
- [x] Update `README.md` so it points to the correct canonical configuration spec after the documentation set is reconciled.
- [x] Remove or archive canonical-looking legacy examples that still present `default_model`, `model_options`, `validation_model`, `reconstruction_model`, or `structure_recognition.model` as the active repository baseline.

### Runtime literal and sweep follow-up

- [x] Remove the `"gpt-image-1"` runtime literal from `image_analysis.py` and replace it with model-agnostic routing semantics.
- [x] Tighten `tests/test_model_registry_sweep.py` so runtime model literals are not allow-listed in production modules unless there is an explicitly documented exception in this spec.
- [x] Re-run the sweep after cleanup to ensure runtime modules remain free of canonical production model literals.

### Test-suite follow-up

- [x] Expand the shared model-role fixture approach so config and image tests stop hardcoding the same production model strings in multiple places.
- [ ] Add targeted regression coverage for model-registry observability output such as `model_registry_resolved` and legacy-source warning events.
- [ ] Decide whether compatibility alias fields on `AppConfig` should continue to be asserted directly in tests or be progressively replaced by registry-first assertions.
