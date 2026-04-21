# Universal Real Document Validation Spec

**Date:** 2026-03-21  
**Status:** implemented in current branch, with one known tolerant legacy-DOC structural profile remaining  
**Trigger:** UI runs still surface model-output and formatting-transfer failures that routine automated validation either does not exercise or does not preserve in a reusable, document-agnostic form.

## Archive Status

Archived on 2026-04-16.

Reason for archive:

1. the registry-driven extraction/structural/full validation architecture is materially present in code and tests;
2. the document remained useful as historical design context, but it was no longer the right active source of truth for day-to-day maintenance;
3. maintained operational guidance now lives primarily in `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`, `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`, and the current code/tests.

---

## 0a. Implementation Status Snapshot

Implemented in the current branch:

1. generic registry-driven document and run profiles via `corpus_registry.toml`;
2. deterministic corpus-backed `extraction` tier;
3. deterministic corpus-backed `structural` passthrough tier;
4. explicit runtime-resolution and override reporting for full-tier runs;
5. repeat/soak execution with aggregated intermittent-failure reporting;
6. second corpus document proving real multi-document architecture;
7. regression coverage for `heading_only_output` in both pipeline and real-document failure-classification paths;
8. project-level legacy `.doc` auto-detection and auto-conversion so corpus and UI share the same normalized input contract.

Still intentionally not fully closed:

1. `religion-wealth-core` remains `tolerant` in deterministic structural mode because one page-separator-like artifact still produces a bounded formatting diagnostic;
2. corpus promotion remains an ongoing workflow, not a one-time completed milestone.

## 0b. Review-Validated Status And Follow-Ups

Code review of the implemented branch confirms that the architecture is materially in place, but also confirms several important boundaries where the implementation is only partially generalized.

Confirmed as implemented:

1. normalization of `.docx` and legacy `.doc` now happens through a shared runtime boundary before downstream preparation and validation;
2. document profiles and run profiles are registry-driven rather than hard-coded to one source file;
3. deterministic `extraction` and `structural` corpus tiers exist and consume profile thresholds declaratively;
4. full-tier validation emits run-scoped artifacts, runtime resolution, and repeat or soak aggregation;
5. `heading_only_output` now has both pipeline-level and real-document report-level regression coverage;
6. the legacy `.doc` conversion path now has bounded subprocess execution, preferred-backend fallback, and stricter format detection than the first implementation pass;
7. repeat-parent reports now expose explicit failing-run and representative-success artifact references;
8. the registry now enforces the currently supported strict-only `expected_acceptance_policy` contract instead of silently accepting broader undeployed policy values.

Confirmed as only partially closed:

1. full-tier orchestration is profile-driven, but full-tier acceptance is still effectively strict and largely hard-coded rather than fully derived from the generalized profile surface;
2. repeat or soak parent reports aggregate child runs correctly and now expose explicit child-run references, but the legacy latest markdown and DOCX aliases still remain compatibility-oriented rather than being a fully redesigned aggregate-artifact contract;
3. legacy conversion provenance is discovered at normalization time, but not yet persisted into the manifest or report contract;
4. legacy `.doc` unit coverage is materially stronger than before, but converter-unavailable and corrupt-input failure paths still deserve broader dedicated tests;
5. full single-run, repeat-parent, and structural reports are closer than before, but report schemas still are not fully normalized to one canonical shape across all tiers.

These are not reasons to roll back the current architecture. They are the main follow-up points needed to make the implementation match the full ambition of this specification.

---

## 0. Document Placement Rule

This specification is intentionally placed in `docs/`, not in `docs/archive/`.

Repository policy for specs going forward:

1. new and active specifications live in `docs/`;
2. `docs/archive/` is only for historical, superseded, or already-realized materials kept for context;
3. archive placement must not be used as the default location for new plans or active design work.

---

## 1. Problem

The current real-document validation path is useful, but too narrow to serve as the main pre-UI quality barrier.

Current gaps:

1. the canonical validator is tied to one document, `tests/sources/Лиетар глава1.docx`;
2. the validator is framed as an exceptional quality gate rather than a general reusable harness;
3. a single stochastic run is not enough to detect intermittent failures such as `heading_only_output`, `empty_response`, or block-collapse behavior;
4. UI runs and validator runs can diverge by runtime knobs such as model, chunk size, retries, image mode, and paragraph-marker configuration;
5. failures found manually in the UI are not automatically promoted into a reusable regression corpus;
6. current reporting is run-centric, but not yet structured around a generic corpus, profile, and replay contract;
7. the ordinary pytest suite does not have a cheap structural tier that exercises Pandoc plus formatting transfer without calling the model API.

Result:

The project can have a green routine regression suite and even a successful single real-document validation run while still missing user-visible failures that appear later during manual UI testing.

---

## 2. Goal

Turn the current Lietaer-specific validator into a universal real-document validation architecture that:

1. reuses the same preparation and processing paths as the UI as much as practical;
2. can run against any registered real document, not only one canonical sample;
3. captures enough run configuration and artifacts to make failures reproducible;
4. supports both deterministic targeted checks and stochastic repeat validation;
5. makes promotion of UI-discovered failures into the regression corpus a normal workflow;
6. improves error discovery before user-facing manual testing without forcing the full default pytest suite to become slow or flaky;
7. adds a zero-API structural tier that can run on every commit across the registered corpus.

---

## 3. Non-Goals

This work does not aim to:

1. make the default full pytest suite run the full real-document corpus on every execution;
2. eliminate all model nondeterminism;
3. replace focused unit tests for block classification, formatting transfer, or pipeline invariants;
4. require every real-document run to succeed under every model and every runtime combination;
5. redesign the main UI workflow;
6. force the structural tier to simulate all semantic rewriting behavior of the model.

---

## 4. Current State

### 4.1. What exists today

The repository already has a strong base:

1. real-document processing uses the real document pipeline, not a toy stub;
2. run artifacts, manifests, progress snapshots, and acceptance reports already exist;
3. runtime event logs already expose block rejection signals such as `heading_only_output`;
4. the quality gate already validates a real DOCX end to end;
5. unit tests already protect many local failure contracts.

### 4.2. What is missing

The missing layer is an architecture that separates:

1. a generic runner contract;
2. a document corpus registry;
3. reproducible run profiles;
4. repeat and soak execution modes;
5. a workflow for promoting real failures into reusable automation;
6. a cheap deterministic structural tier that validates DOCX extraction and formatting restoration without LLM calls.

---

## 5. Proposed Architecture

### 5.1. Split the current validator into generic platform plus document profiles

Replace the idea of a single hard-coded Lietaer validator with two layers.

Layer A: generic replay validation runner

Responsibilities:

1. load a document profile;
2. resolve input document and expected runtime configuration;
3. invoke the same preparation and processing flow used by the app pipeline;
4. persist run manifest, progress, runtime events, and output artifacts;
5. compute standardized validation signals and acceptance outcomes.

Layer B: document corpus profiles

Responsibilities:

1. define which real source document to run;
2. declare profile-specific expectations and tolerances;
3. record known risk areas, such as images, tables, headings, or list-heavy structure;
4. define whether the profile is deterministic smoke, regression, or soak-oriented.

### 5.2. Introduce a real-document corpus registry

Add a registry that treats each real document as a named validation asset rather than a one-off script constant.

Preferred storage: `corpus_registry.toml`.

Each corpus entry should contain concrete structural expectations as well as runtime metadata.

Minimum fields:

1. stable profile id;
2. source document path;
3. minimum extractability expectations such as `min_paragraphs`;
4. structural feature expectations such as `has_headings`, `has_numbered_lists`, `has_images`, `has_tables`;
5. optional prompt or mode overrides;
6. default run profile linkage or runtime defaults;
7. expected acceptance policy;
8. optional tags such as `headings`, `tables`, `images`, `formatting`, `stress`, `manual-regression`;
9. provenance metadata describing why the document exists in the corpus.

These fields serve different tiers:

1. extraction tier uses minimum extractability and structure expectations;
2. structural tier uses the same corpus metadata plus formatting expectations;
3. full tier uses the acceptance policy and run-profile bindings.

Suggested examples:

1. `lietaer-core` for the current canonical historical sample;
2. `ui-heading-only-regression-001` for a document added because the UI exposed a heading-collapse failure;
3. `formatting-split-paragraph-regression-001` for a source that previously created restore mismatches.

Illustrative shape:

```toml
[[documents]]
id = "lietaer-core"
source_path = "tests/sources/Лиетар глава1.docx"
min_paragraphs = 120
has_headings = true
has_numbered_lists = true
has_images = true
has_tables = false
default_run_profile = "ui-parity-default"
tags = ["headings", "formatting", "manual-regression"]
expected_acceptance_policy = "strict"
provenance = "Canonical real document regression sample"
```

### 5.3. Introduce run profiles separate from document profiles

A document profile and a run profile must be independent.

Document profile answers:

1. what document is under test;
2. what risks the document represents.

Run profile answers:

1. which model;
2. which chunk size;
3. max retries;
4. image mode;
5. paragraph marker setting;
6. repeat count;
7. whether this is smoke, strict regression, or soak validation.

This separation is necessary because the same document may need:

1. one stable deterministic smoke profile;
2. one UI-parity profile;
3. one repeat profile for intermittent model failures.

### 5.4. Preserve a UI-parity execution mode

The universal validator must support a run mode whose explicit purpose is to mirror the UI path as closely as practical.

Requirements:

1. use the same preparation and processing entry points as the app flow;
2. capture all runtime knobs that materially affect output;
3. avoid hidden hard-coded overrides unless they are declared in the run profile and written into the manifest;
4. report any divergence from UI-default behavior in the run manifest.

Important consequence:

The current behavior where the validator silently forces `enable_paragraph_markers=True` should become explicit profile configuration, not implicit validator behavior.

### 5.5. Introduce three validation tiers

The architecture should explicitly distinguish three tiers.

#### Tier 1. Extraction tier

Purpose:

1. verify that document parsing and semantic extraction succeed for every registered corpus document;
2. verify coarse structural expectations from the corpus registry;
3. stay deterministic and cheap enough for ordinary pytest execution.

Examples of assertions:

1. extracted paragraph count is at least `min_paragraphs`;
2. heading presence matches `has_headings` when declared;
3. numbered-list detection matches `has_numbered_lists` when declared.

#### Tier 2. Structural tier

Purpose:

1. validate the formatting pipeline without calling the model API;
2. catch regressions in Pandoc conversion and formatting transfer on every commit;
3. target the exact class of deterministic formatting failures that often surface later in the UI.

Mechanism:

1. extract the source document into the intermediate markdown or markdown-equivalent representation;
2. use mock markdown passthrough instead of LLM output;
3. feed that passthrough content through Pandoc and `formatting_transfer`;
4. validate the reconstructed DOCX and its diagnostics.

This tier is intentionally not semantic editing validation. It is a deterministic check of extraction plus reconstruction plus formatting restoration.

Examples of assertions:

1. no unexpected formatting diagnostics;
2. heading hierarchy survives when declared by the corpus profile;
3. numbered lists remain lists when declared by the corpus profile;
4. alignment-sensitive or paragraph-count-sensitive documents remain within allowed thresholds.

#### Tier 3. Full tier

Purpose:

1. run the real model-backed pipeline;
2. validate UI-parity and stochastic behavior;
3. support smoke, regression, repeat, soak, and quality-gate modes.

This is the only tier that requires LLM execution.

### 5.6. Define a structural assertion contract

The structural tier must not rely on vague outcomes such as "structure mostly survived" or "formatting looks acceptable". It needs a declared pass/fail contract.

Structural assertions should be split into three categories.

#### Category A. Extraction completeness

These assertions confirm that the document was parsed into a plausible intermediate representation.

Recommended fields:

1. `min_paragraphs`;
2. `min_headings` when `has_headings = true`;
3. `min_numbered_items` when `has_numbered_lists = true`;
4. `min_images` when `has_images = true`;
5. `min_tables` when `has_tables = true`.

#### Category B. Structural preservation

These assertions confirm that the deterministic passthrough pipeline did not destroy the document's intended paragraph and style structure.

Recommended fields:

1. `max_formatting_diagnostics`;
2. `max_unmapped_source_paragraphs`;
3. `max_unmapped_target_paragraphs`;
4. `max_alignment_mismatches`;
5. `max_heading_level_drift`;
6. `require_numbered_lists_preserved`.

#### Category C. Text preservation in passthrough mode

Because the structural tier does not perform semantic rewriting, text preservation should be much stricter than in the full model-backed tier.

Recommended fields:

1. `min_text_similarity` for normalized source vs normalized output text;
2. `require_nonempty_output = true` by default;
3. `forbid_heading_only_collapse = true` when the source block clearly contains body text.

### 5.7. Recommended default thresholds

The spec should provide default values so implementation does not invent its own pass/fail rules ad hoc.

Recommended baseline defaults for structural tier:

1. `min_text_similarity = 0.98`;
2. `max_formatting_diagnostics = 0`;
3. `max_unmapped_source_paragraphs = 0`;
4. `max_unmapped_target_paragraphs = 0`;
5. `max_alignment_mismatches = 0` for alignment-sensitive profiles, otherwise unset;
6. `max_heading_level_drift = 1`;
7. `require_numbered_lists_preserved = true` when `has_numbered_lists = true`;
8. `require_nonempty_output = true`.

Recommended paragraph-count defaults:

1. for strict formatting profiles: `abs(output_paragraph_count - source_paragraph_count) <= 3`;
2. for tolerant profiles: `output_paragraph_count >= source_paragraph_count * 0.90`.

These defaults are intentionally conservative. A profile may override them only when a known document-specific behavior justifies it.

### 5.8. Support strict and tolerant structural profiles

Not all real documents need the same threshold strictness.

Recommended modes:

#### `strict`

Use for documents that serve as formatting regressions or acceptance-critical layout samples.

Expected behavior:

1. `max_formatting_diagnostics = 0`;
2. `max_unmapped_source_paragraphs = 0`;
3. `max_unmapped_target_paragraphs = 0`;
4. `min_text_similarity >= 0.99` when normalization is stable enough;
5. paragraph-count drift limited to a very small absolute threshold.

#### `tolerant`

Use for documents where the pipeline may legitimately create small deterministic paragraph shifts, but must still preserve user-visible structure.

Expected behavior:

1. paragraph-count comparison may use a percentage threshold;
2. one explicitly whitelisted diagnostic family may be allowed;
3. heading, list, and caption survival still remain mandatory when declared by the profile.

Tolerance must remain explicit and narrow. A tolerant profile must list why it is tolerant.

### 5.9. Declare thresholds in `corpus_registry.toml`

Thresholds should live next to the document profile rather than being hard-coded in test logic.

Illustrative shape:

```toml
[[documents]]
id = "lietaer-core"
source_path = "tests/sources/Лиетар глава1.docx"
structural_mode = "strict"
min_paragraphs = 120
has_headings = true
min_headings = 8
has_numbered_lists = true
min_numbered_items = 12
has_images = true
min_images = 1
max_formatting_diagnostics = 0
max_unmapped_source_paragraphs = 0
max_unmapped_target_paragraphs = 0
max_alignment_mismatches = 0
max_heading_level_drift = 1
min_text_similarity = 0.98
require_numbered_lists_preserved = true
require_nonempty_output = true
forbid_heading_only_collapse = true
default_run_profile = "ui-parity-default"
tags = ["headings", "formatting", "manual-regression"]
expected_acceptance_policy = "strict"
provenance = "Canonical real document regression sample"
```

The testing code should read these fields declaratively rather than re-encoding special cases in Python conditionals.

### 5.10. Add repeat and soak execution modes

A single run is insufficient for intermittent model failures.

The architecture should support:

1. smoke mode: one fast run for a selected document/profile;
2. regression mode: one or a few runs with stricter acceptance checks for known regressions;
3. soak mode: repeated runs of the same document/profile to measure intermittent failure rates;
4. matrix mode: selected document set across selected runtime profiles.

This is the mechanism for catching rare `heading_only_output` or `collapsed_output` incidents earlier.

### 5.11. Standardize run outputs and acceptance signals

Every universal validation run should emit a consistent manifest schema.

Implementation note from review:

1. the current branch already emits aggregate repeat metadata and per-run artifacts;
2. however, the top-level repeat or soak artifact policy is still implicit because latest markdown and DOCX aliases track the last repeat artifact rather than an explicitly designated failing or representative child run;
3. the intended end state for this section is: parent manifest is the canonical aggregate truth, while child-run links are explicit for the first failing repeat and, when useful, a representative successful repeat.

Minimum top-level fields:

1. `run_id`;
2. `document_profile_id`;
3. `run_profile_id`;
4. `source_document_path`;
5. `status`;
6. `result`;
7. `acceptance_passed`;
8. resolved runtime configuration;
9. artifact paths;
10. summarized validator signals.

Minimum summarized validator signals:

1. block rejection counts by classification;
2. whether `heading_only_output` occurred;
3. whether retries were exhausted;
4. formatting diagnostics count and summary;
5. image pipeline warnings or failures;
6. placeholder integrity result;
7. marker integrity result;
8. document-level acceptance outcome;
9. tier name, so extraction, structural, and full results are comparable in one reporting model.

Additional manifest fields now justified by review:

1. normalization provenance for mixed-format inputs: original filename, normalized filename, detected source format, whether conversion occurred, and conversion backend;
2. explicit aggregate-artifact links for repeat or soak runs so intermittent failures do not get masked by the final repeat artifact;
3. explicit declaration when a parsed policy field such as `expected_acceptance_policy` is deferred and not yet active beyond schema validation;
4. schema consistency between deterministic and full-tier reports for runtime-configuration fields and optional artifact keys, so downstream consumers do not need tier-specific key translation for the same conceptual data.

Current implementation note:

1. item 2 is now partially implemented via explicit failing-run and representative-success links in repeat-parent reports;
2. item 3 is now enforced as strict-only schema contract rather than remaining silently open-ended;
3. items 1 and 4 remain the main manifest-level follow-ups.

### 5.12. Add a promotion workflow from UI failure to reusable corpus case

When manual testing exposes a failure, the workflow should be:

1. preserve the triggering source document or a minimal redacted reproduction;
2. record the UI runtime settings that produced the failure;
3. create a new document profile and, if needed, a dedicated run profile;
4. add profile-specific acceptance checks if the failure is structurally unique;
5. make the failure reproducible through the universal validator.

This is the main mechanism by which manual testing shrinks over time.

---

## 6. Module Boundaries And Dependency Direction

### 6.1. New or expanded responsibilities

#### validation runner module

Purpose:

1. generic orchestration of a real-document validation run;
2. loading profiles;
3. invoking shared pipeline entry points;
4. writing manifests and reports.

#### validation profile module

Purpose:

1. schema for document profiles;
2. schema for run profiles;
3. corpus registry loading and validation;
4. support for concrete structural expectations loaded from `corpus_registry.toml`.

#### validation reporting module

Purpose:

1. standardize manifest generation;
2. summarize runtime events;
3. compute acceptance results from standardized signals.

#### structural validation module

Purpose:

1. implement mock-markdown passthrough validation;
2. run Pandoc plus formatting transfer without API calls;
3. expose reusable helpers for deterministic corpus-wide pytest coverage.

### 6.2. Existing modules that remain central

1. `application_flow.py` remains the high-level runtime orchestration source;
2. `document_pipeline.py` remains the block-processing engine and failure classifier source;
3. formatting-transfer and image pipeline modules remain domain owners for their own diagnostics;
4. config loading remains in the existing config layer.

### 6.3. Dependency direction

Required direction:

1. validation runner depends on profiles, application flow, document pipeline, and reporting helpers;
2. structural validation helpers depend on extraction, generation, formatting-transfer, and reporting helpers;
3. reporting helpers may depend on runtime event schemas and artifact metadata;
4. core runtime modules must not depend on validator-only modules;
5. UI code must not depend on corpus-specific validation code.

This keeps the validator as a consumer of runtime behavior, not a new owner of runtime logic.

---

## 7. Proposed Implementation Plan

### Phase 1. Generalize the current Lietaer runner

1. extract reusable runner logic from the current Lietaer-specific implementation;
2. keep Lietaer as the first registered document profile;
3. replace hard-coded document assumptions with profile-driven configuration;
4. preserve current manifests and latest aliases where practical.

### Phase 2. Add corpus and run-profile schemas

1. define the profile schema and registry location;
2. support at least one document profile and multiple run profiles;
3. use `corpus_registry.toml` for document metadata and structural expectations;
4. capture resolved config into the run manifest.

### Phase 3. Add extraction and structural pytest tiers

1. add corpus-loading helpers usable from ordinary pytest;
2. implement parametrized extraction tests across the registered corpus;
3. implement parametrized structural passthrough tests across the registered corpus;
4. keep these tests deterministic and API-free.

### Phase 4. Add UI-parity mode and explicit override reporting

1. eliminate silent validator-only runtime overrides;
2. record all effective overrides in the manifest;
3. provide a run mode intended to mirror UI defaults.

### Phase 5. Add repeat and soak execution

1. support repeated execution counts;
2. aggregate intermittent failure metrics;
3. expose per-repeat outcomes in the final report.

### Phase 6. Add promotion workflow and targeted regression onboarding

1. document how UI failures become corpus entries;
2. add one or more corpus cases derived from already observed failures;
3. define which profiles belong in smoke, regression, and exceptional quality-gate paths.

---

## 8. Test Strategy

The architecture needs tests at several levels.

### 8.1. Ordinary pytest corpus coverage

The ordinary suite should run corpus-based tests without API access.

Recommended shape:

```python
@pytest.mark.parametrize("doc", load_corpus())
def test_corpus_extraction(doc):
	...


@pytest.mark.parametrize("doc", load_corpus())
def test_corpus_structural_passthrough(doc):
	...
```

This gives the repository a cheap deterministic barrier on every commit for all registered real documents.

### 8.2. Fast deterministic tests

Add unit coverage for:

1. profile schema validation;
2. manifest generation;
3. event summarization;
4. acceptance computation from synthetic validator signals;
5. explicit detection of runtime override drift;
6. structural-tier helper behavior for passthrough markdown and diagnostics interpretation;
7. malformed and unsupported legacy-input detection, including non-Word OLE2 containers and converter-unavailable paths;
8. conversion-runner hardening paths, including subprocess timeout handling and `soffice` to `antiword` fallback behavior when the preferred backend is present but unusable;
9. repeat override parsing and error handling for malformed environment values.

### 8.3. Corpus-backed deterministic integration tests

Add deterministic corpus tests for:

1. extraction tier against every registered document;
2. structural tier passthrough against every registered document;
3. corpus expectation enforcement from `corpus_registry.toml`.

These tests should be regular pytest tests, not exceptional gates.

### 8.4. Focused integration tests

Add integration coverage for:

1. generic runner can execute a registered profile;
2. Lietaer compatibility path still works after generalization;
3. run profile configuration is written into the manifest;
4. repeat mode aggregates results correctly;
5. parent repeat reports expose explicit failing-run and representative-success links instead of relying on implicit last-run artifact selection when intermittent failures occur;
6. legacy `.doc` normalization failures surface as structured user-facing failures rather than raw conversion exceptions.

### 8.5. Migration map for current tests

The new extraction and structural tiers do not replace the current focused tests one for one. They change the role of parts of the existing suite.

#### Keep as focused unit or narrow integration tests

These tests still provide faster root-cause localization than corpus-wide tiers and should remain.

Current examples from `tests/test_document.py`:

1. extraction heuristics for headings, captions, tables, and inline markup;
2. semantic block construction and image-only passthrough behavior;
3. formatting-transfer mapping rules, list restoration, and similarity-based matching;
4. image reinsertion behavior for placeholders, tables, headers, footers, and textboxes.

Rationale:

1. corpus tiers answer whether the pipeline outcome regressed;
2. focused tests answer which local rule regressed and why.

#### Move user-visible outcome coverage into corpus extraction and structural tiers

Some current tests protect user-visible end-to-end formatting behavior using small synthetic fixtures. Those remain useful initially, but after corpus tiers land, they should no longer be the primary place where document-level behavior is validated.

Current examples from `tests/test_document.py`:

1. caption survival through extraction plus normalization;
2. mismatch diagnostics and artifact creation on synthetic paragraph-count drift;
3. list restoration outcome checks that are better expressed as document-profile structural expectations.

Migration rule:

1. keep one targeted local test per tricky rule;
2. move broad user-visible outcome coverage to corpus-based extraction and structural tests;
3. avoid keeping multiple synthetic tests that all prove the same document-level contract.

#### Consolidate after corpus tiers are stable

The following class of tests becomes a consolidation target, not an immediate deletion target:

1. synthetic extraction-plus-normalization tests that duplicate corpus structural coverage;
2. multiple tests asserting the same formatting-diagnostic family at both local and pseudo-end-to-end levels;
3. multiple small fixtures verifying list, caption, or heading survival when the same contract is already enforced by corpus thresholds.

Consolidation rule:

1. remove a synthetic test only after an equivalent or stronger corpus-based assertion exists;
2. preserve the most local, fastest, and most diagnostic test when two tests cover the same failure class.

#### Remove or repair immediately when discovered

Dead or duplicate tests should not wait for the new architecture.

Known current example:

1. `test_preserve_source_paragraph_properties_logs_mismatch_warning` is defined twice in `tests/test_document.py`; the later definition overrides the earlier one at import time.

Required action:

1. merge, rename, or delete duplicated definitions before treating the suite as authoritative;
2. do not carry hidden duplicate tests into the tiered corpus architecture.

#### Practical ownership after migration

After the new architecture lands, the suite should read as follows.

1. unit tests: extraction heuristics, mapping rules, local formatting rules, image reinsertion internals;
2. extraction tier: corpus-wide extraction expectations from `corpus_registry.toml`;
3. structural tier: corpus-wide deterministic passthrough and formatting preservation assertions;
4. full tier: UI-parity, stochastic behavior, retries, and exceptional real-document quality gates.

Decision rule:

An existing test is considered obsolete only when both conditions are true:

1. a corpus-based extraction or structural assertion now protects the same user-visible contract;
2. the old test no longer provides faster or more precise root-cause localization.

### 8.6. Exceptional real-document verification

Keep real-document quality gates explicit and user-visible.

The default full suite should remain fast. Real-document corpus execution should remain an intentional path via dedicated tasks and documented commands.

---

## 9. Documentation Changes Required

This architecture requires documentation updates together with code.

Required updates:

1. document that new active specs belong in `docs/`, not `docs/archive/`;
2. reframe the current Lietaer workflow as one document profile within a broader validation architecture;
3. document the three-tier model: extraction, structural, full;
4. document how to add a new real-document profile to `corpus_registry.toml`;
5. document how the structural passthrough tier works and what it does not prove;
6. document how to promote a UI-found failure into the corpus;
7. document smoke vs regression vs soak modes.

---

## 10. Risks

1. if the validator grows without profile boundaries, it will become another hard-coded script with multiple special cases;
2. if UI-parity mode is underspecified, the new harness will still miss real user failures;
3. if the corpus grows without tags and provenance, it will become unmaintainable;
4. if the structural tier is underspecified, it will become too weak to catch formatting regressions despite being cheap;
5. if repeat mode is treated as mandatory for every run, validation cost will become unacceptable;
6. if acceptance signals are not standardized, reports will remain hard to compare across runs.

Additional risks confirmed by review of the implemented branch:

1. if full-tier acceptance remains only partially profile-driven, the registry schema can look more generalized than the actual behavior of the main validator;
2. if repeat-parent latest artifacts keep tracking the last repeat implicitly for compatibility, intermittent failures will still be harder to triage than a fully aggregate-first artifact policy would allow;
3. if normalization provenance is not persisted, mixed-format regressions will be harder to explain across environments and reruns;
4. if already-normalized frozen payloads continue to be normalized again defensively in downstream preparation, the contract boundary stays harder to reason about and easier to drift later;
5. if normalization provenance is not persisted, mixed-format runs will still be less explainable than the runtime now allows them to be;
6. if report schemas continue to diverge between structural, single-run full-tier, and repeat-parent outputs, report consumers will remain more fragile than the architecture intends.

---

## 11. What Does Not Change

1. focused unit tests remain the first line of defense for deterministic contracts;
2. the ordinary pytest suite gains extraction and structural corpus coverage, but full model-backed validation remains separate from exceptional real-document gates;
3. the runtime pipeline remains owned by existing application modules;
4. the current Lietaer sample remains useful, but as one registered corpus document rather than the whole validation concept.

---

## 12. Acceptance Criteria

This spec is considered implemented when:

1. the repository has a generic real-document validation runner that is not hard-coded to one document;
2. Lietaer runs through that generic runner as a document profile;
3. at least one additional document profile can be added without cloning the runner logic;
4. the repository contains `corpus_registry.toml` or an equivalent canonical corpus registry with concrete fields such as `min_paragraphs`, `has_headings`, and `has_numbered_lists`;
5. ordinary pytest runs parametrized extraction-tier tests across the registered corpus;
6. ordinary pytest runs parametrized structural-tier passthrough tests across the registered corpus without API calls;
7. the manifest records document profile, run profile, effective runtime configuration, and validation tier;
8. the validator can run in a UI-parity mode without hidden implicit overrides;
9. the validator supports repeated execution for intermittent failure detection;
10. repository docs explain the profile workflow, three-tier model, and state clearly that new active specs live in `docs/`, while `docs/archive/` is only for historical materials.

## 12a. Current Branch Assessment

Based on review of the current branch, the acceptance criteria above are best understood as follows.

Implemented:

1. criteria 1 through 10 are materially implemented in the repository and are sufficient to treat this specification as implemented in its main architectural direction;
2. the strongest implemented pieces are the shared normalization boundary, registry-driven corpus shape, deterministic extraction and structural tiers, explicit runtime-resolution reporting, and repeat or soak aggregation.

Still requiring follow-up for architectural completeness:

1. criterion 7 is implemented at the manifest-shape level, but should be extended with normalization provenance for mixed-format runs;
2. criteria 7 through 9 are implemented operationally, and repeat-parent reports now expose explicit child-run references, but the top-level alias policy still should move further from implicit last-repeat semantics;
3. criteria 2, 3, and 8 are implemented at the runner and configuration level, but the full-tier acceptance layer should still be brought into tighter alignment with the generalized profile contract;
4. the parsed field `expected_acceptance_policy` is now constrained to the supported strict-only mode, but still should either become active runtime behavior or remain explicitly documented as strict-only deferred surface until broader policy variants are introduced;
5. deterministic and full-tier report schemas should converge further so runtime configuration and artifact keys are easier to consume uniformly across tiers;
6. the current test strategy should still be extended with explicit coverage for converter-unavailable paths, corrupt legacy inputs, and broader multi-block or partial `heading_only_output` scenarios.
