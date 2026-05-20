# Index Region Authority Spec

Date: 2026-05-20
Status: Narrow validator contract implemented; milestone-confirmed for the original C example set
Package: Mini-plan C only
Primary continuation source: [STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md](./STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md#L250)
Related out-of-scope parent: [TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md](./TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md#L17)

## 1. Purpose

This spec defines only the problem framing, evidence contract, and future acceptance boundary for Mini-plan C: index-region / page-range / back-matter heading-like authority.

The adopted implementation remained limited to the narrow validator/acceptance contract described here. This document still does not authorize broader upstream recognition redesign, and it does not reopen Mini-plan A, Mini-plan B, or Stage 1 prompt/schema/cache work.

## 2. Baseline Restored on 2026-05-20

The restored source of truth for this package is:

1. [AGENTS.md](../../AGENTS.md)
2. [STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md](./STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md#L139)
3. [TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md](./TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md#L1)
4. [lietaer_pdf_full_benchmark_latest.json](../../tests/artifacts/real_document_pipeline/lietaer_pdf_full_benchmark_latest.json)
5. [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L133922)
6. [baseline old run report](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136131)

Baseline assumptions confirmed from those artifacts:

- The latest manifest now points to completed run `20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne` with `status: "failed"`, `result: "succeeded"`, and `acceptance_passed: false`.
- The latest completed full-book report now leaves only Mini-plan B in `failed_checks`; Mini-plan A and Mini-plan C are no longer active live failures in the refreshed continuation-plan inventory.
- Mini-plan C is no longer blocked on spec creation: the dedicated spec path is opened, the narrow validator contract is implemented, and the latest full-book milestone confirms the old C example set at the validator/acceptance layer only.

## 3. Why Existing Specs Do Not Already Cover Mini-plan C

The current continuation plan explicitly says this is a separate authority class and requires a separate spec: [STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md](./STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md#L150), [STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md](./STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md#L156), [STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md](./STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md#L290).

The topology-first remediation spec also explicitly excludes index / page-range heading authority from its scope: [TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md](./TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md#L17).

At spec-open time there was no already-approved spec in the repository that covered Mini-plan C well enough to authorize implementation. This document is now that dedicated spec path for the adopted narrow validator contract. It still does not authorize a broader upstream recognition redesign.

## 4. Evidence Contract From the Baseline and Latest Completed Reports

Mini-plan C now uses a baseline-to-latest comparison as its evidence contract anchor: the old failing baseline that motivated the package and the latest completed full-book milestone that confirms the adopted narrow validator contract.

The exact old `failed_checks` list in baseline run `20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne` is recorded at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136131):

- `formatting_diagnostics_threshold`
- `unmapped_source_threshold`
- `unmapped_target_threshold`
- `residual_bullet_glyphs_present`
- `key_headings_preserved`

For Mini-plan C, the exact old `key_headings_preserved.missing` set is fixed by [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136272):

- `11,12` at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136275)
- `179– 180` at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136276)
- `182, 192–1 93` at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136277)

The latest completed milestone run `20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne` now records `failed_checks = ["formatting_diagnostics_threshold", "unmapped_source_threshold", "unmapped_target_threshold"]` at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L133922), and `key_headings_preserved` passes with `missing = []` and `source_heading_count = 0` at [lietaer_pdf_full_benchmark_report.json](../../tests/artifacts/real_document_pipeline/runs/20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L134061).

For this package, the old serialized strings remain authoritative as the motivating baseline examples, and the latest run remains authoritative for the milestone-confirmed pass state.

## 5. Current Mini-plan C Evidence Classification

| Example | Report anchor | Output/report-adjacent anchor | Current classification | Why this is the narrowest supported reading |
|---|---|---|---|---|
| `11,12` | [report](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136275) | [Rethinking_money_full_benchmark.md](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/Rethinking_money_full_benchmark.md#L777) | body marker / source heading inventory anomaly | The rendered output shows a standalone numeric marker between body text and a real heading, which supports treating it as a source-heading-inventory anomaly rather than a chapter-heading authority gap. |
| `179– 180` | [report](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136276) | [Rethinking_money_full_benchmark.md](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/Rethinking_money_full_benchmark.md#L3689) | index-style page-range entry | The same token is rendered as a late-book page-range marker in the index/back-matter region, not as a chapter or narrative heading. |
| `182, 192–1 93` | [report](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/lietaer_pdf_full_benchmark_report.json#L136277) | [Rethinking_money_full_benchmark.md](../../tests/artifacts/real_document_pipeline/runs/20260519T082926Z_963_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne/Rethinking_money_full_benchmark.md#L3599) | index-style page-range entry | The report serializes the token with spacing artifacts, while the rendered output shows the corresponding comma-plus-range page marker inside index-style content. |

No broader classification claim is authorized here. In particular, this package does not reopen any Chapter 9 or late-book chapter-authority narrative.

### 5.1 Milestone Follow-up on 2026-05-20

The implemented Mini-plan C change remained narrow: it updated the validator/acceptance contract so standalone numeric/body-marker anomalies and pure page-range index-style tokens are not automatically treated as enforceable key headings.

The latest completed full-book milestone confirms that narrow contract for the original C example set:

- `key_headings_preserved` is no longer in `failed_checks`.
- `missing = []`.
- `source_heading_count = 0`.

Reviewer-safe boundary: this milestone confirms the adopted validator/acceptance slice only. It does not prove that Stage 1, topology projection, or `StructuralUnit` now carry a broad dedicated index / back-matter authority class.

## 6. Exact Scope

This package covers only the recognition and validation contract for index-region / page-range / back-matter heading-like authority.

In scope:

- defining how heading-like strings in index/back-matter regions differ from actual chapter/body heading authority;
- defining how `key_headings_preserved` should treat page-range markers and related back-matter heading-like tokens;
- defining the evidence required before implementation starts on this package;
- defining the focused acceptance boundary for future Mini-plan C work;
- preserving explicit separation from Mini-plan A residual bullets and Mini-plan B unmapped-alignment work.

Mini-plan C is separate from A and B because the current evidence still points to a different root-cause class: `new_authority_class` in the continuation plan's live inventory, not markdown hygiene and not unmapped alignment.

## 7. Explicit Non-Scope

This package does not cover:

- residual bullet cleanup or any Mini-plan A residual-bullet inventory work;
- unmapped source/target alignment, unmapped back-matter tracing, or any Mini-plan B breakage pattern work;
- TOC/body concat or protected TOC boundary behavior;
- Chapter 9 or any late-book chapter authority narrative;
- generic markdown hygiene or markdown normalizer retirement;
- broad Stage 1 redesign, including prompt/schema/cache changes;
- full appendix/bibliography rewrite or general back-matter rewrite;
- broad authorization to treat the current milestone as upstream recognition completion or to expand beyond the adopted narrow validator contract without a separate approved package.

## 8. Evidence Required Before Any Future Expansion Starts

Before any future expansion sprint beyond the adopted narrow validator contract for Mini-plan C, all of the following must exist:

1. The expansion scope is explicitly approved as separate from the already-landed narrow validator contract.
2. A focused discovery note maps each current missing example to a concrete authority expectation and fixture plan.
3. Dedicated focused fixtures exist for at least:
   - the standalone numeric/body-marker anomaly represented by `11,12`;
   - a single page-range index token represented by `179–180`;
   - a comma-plus-page-range token represented by `182, 192–193`;
   - a back-matter region boundary case proving the validator is using the intended authority contract.
4. Focused tests define whether these tokens should be preserved as headings, reclassified as non-heading authority, or excluded from the heading-preservation contract; that decision must be explicit and test-visible.
5. A no-regression check exists for Mini-plan A and Mini-plan B surfaces using their own focused fixtures/contracts.

No expansion package may claim Mini-plan C completion from a full-book rerun alone.

## 9. Future Acceptance Criteria for Mini-plan C Only

Any future expansion beyond the current narrow validator contract is accepted only when all of the following are true:

1. Dedicated focused fixtures and tests for index-region / page-range / back-matter authority exist and pass before any future full-book milestone is cited.
2. The current `key_headings_preserved` examples from this C set are each explained by the adopted authority contract and covered by focused assertions.
3. The validator and recognition contract agree on how index-style page-range tokens are treated; no ambiguous silent reclassification is allowed.
4. There is no regression on Mini-plan A or Mini-plan B surfaces.
5. Any later full-book milestone is used only as outer confirmation after the focused C package is already green; it is not an inner-loop tuning mechanism for this package.

## 10. Reviewer-Relevant Boundary

Reviewer-safe conclusion for this document:

- The current evidence supports a narrow index-region / page-range / back-matter authority package only, and that narrow validator contract is now milestone-confirmed for the original C example set.
- This spec does not reopen Mini-plan A, Mini-plan B, Chapter 9 narratives, or Stage 1 redesign.
