# Post-FC Development Roadmap

Date: 2026-06-14
Status: Active roadmap for the implementing agent
Owner surface: whole pipeline (import -> translate -> cleanup -> rebuild ->
restore -> validate), proof harness, corpus
Reviewer: plan author reviews each work-stream result and returns findings.
Related (read before starting):
`docs/archive/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md`,
`docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`,
`docs/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`,
`docs/specs/READER_CLEANUP_MODEL_STRATEGY_EXPERIMENTS_2026-05-30.md`

## Product Goal (the thing all work serves)

Translate **full books** (PDF -> translated DOCX) preserving formatting, images,
structure, and reading quality, at book scale. Gemini stays the translation
baseline; advanced models do reader cleanup where judgement helps. Everything
below is judged by whether it moves the product toward full-book output, not by
how perfect one chapter excerpt looks.

## Where We Are (entry state, 2026-06-14)

- Translation, reader cleanup (PR-H0 readable-draft boundary), PDF text-layer
  import, image preservation (12/12), and id-first lineage all work.
- The long-standing formatting blocker (PR-I2) is **closed for the
  chapter-region proof**. The matcher handles role-compatible body/list fuzzy
  mapping, image-heading DOCX reconstruction is fixed upstream, and clean
  restore now emits an auditable role-aware `formatting_diagnostics` payload.
- A no-LLM restore replay exists (`validation/formatting_replay.py`) — use it.
- Superseded proof `20260614T_wsmap_bounded_mapping_proof` passed acceptance but
  reviewer spot-check found it was a hollow pass: six chapter/title headings
  were credited while rendered as `Body Text`, and `p0072` was falsely reported
  as role-loss despite being present in `Heading 1`.
- Fresh proof `20260614T_wsmap_auditable_role_aware_proof_v4` passed acceptance
  with DOCX openable, images `12/12`, `formatting_diagnostics` length `1`,
  `final_generated_paragraph_registry=123`,
  `unmapped_source_count_basis=role_aware_formatting_coverage`, raw/effective
  source residual `0/0`, raw target residual `0`, and no-LLM replay residual
  `0/0`.
- **Not done:** the role-aware reframe is validated on **one** document
  (Lietaer chapter-region) only.

## Working Rules (non-negotiable — these are the lessons of the last iteration)

1. **Large chunks, not micro-slices.** Each work-stream below is one substantial
   unit. Do not split a work-stream into a dozen "hypothesis confirmed" proofs.
2. **Deterministic results, recorded as measured numbers — never "confirmed".**
   A chunk is done only when its verifiable result is in the doc with the actual
   numbers from a run, not intentions.
3. **Use the no-LLM replay for the inner loop.** Reserve full LLM proof runs for
   genuine behaviour validation. Do not burn a translation run to read
   deterministic diagnostics.
4. **Always run the FULL relevant test file(s), never only focused selectors.**
   The 54-test regression slipped through because only new tests were run.
5. **Production and harness share logic.** No gate/credit that lives only in the
   proof runner. If the product should enforce it, it lives in `src/`.
6. **Named result types over positional tuples** for any multi-field return.
7. **Content-presence != format-presence.** Never credit a source as covered
   because its text survived if its structural role was lost.
8. **No document-specific literals, no new broad substring/containment matcher
   heuristics, no verifier as a gate.**

## How This Will Be Reviewed

After each work-stream the agent reports: what changed (files), the measured
verifiable result, the full-file test results, and any deviation from scope with
its justification. The reviewer checks the result against the "Verifiable result"
and "Done" lines below and returns findings before the next work-stream starts.

---

# WS-1. Close & Archive the FC Iteration

**Goal:** discharge the one remaining FC gate and archive the spec.

**Scope:**
- Install optional `pdfminer.six` in the environment.
- Run one chapter-region live proof with current code.
- Confirm: role-aware basis appears in the gate, the run produces an artifact
  containing `final_generated_paragraph_registry`, images stay 12/12, output DOCX
  opens, exactly one restore pass (single build).
- Move `FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md` to an archive
  location/status once the proof passes.

**Verifiable result:**
- A fresh run dir whose report has `unmapped_source_count_basis =
  role_aware_formatting_coverage`, a non-empty
  `/runtime/state/final_generated_paragraph_registry`, `formatting_diagnostics`
  length `1`, images 12/12.
- The role-aware effective unmapped number recorded, with the residual either
  empty or a hand-checkable list of real heading/list/caption role losses.

**Guardrails / non-goals:** no code changes beyond what the proof needs; if the
proof reveals a real bug, stop and report rather than patching blind.

**Done:** proof artifact recorded with the numbers above; FC spec archived.

**Superseded 2026-06-14:** `20260614T_wsmap_bounded_mapping_proof`
(`tests/artifacts/real_document_pipeline/runs/20260614T_wsmap_bounded_mapping_proof/lietaer_pdf_chapter_region_report.json`)
passed acceptance with `failed_checks=[]`. The report has
`unmapped_source_count_basis=role_aware_formatting_coverage`,
`formatting_diagnostics` length `1`, DOCX openable, images `12/12`,
`final_generated_paragraph_registry=123`, raw source/target residual `1/0`,
and the sole effective residual is `p0072`
(`content_survived_but_format_role_lost`). Reviewer spot-check rejected this
artifact because `p0026`, `p0076`, `p0077`, `p0092`, `p0093`, and `p0094` were
actually rendered as `Body Text` in the DOCX. The FC spec was already archived
to `docs/archive/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md`,
but WS-1 remains open until a fresh artifact satisfies the role-aware proof
requirements without false heading credit.

**Completed 2026-06-14:** `20260614T_wsmap_auditable_role_aware_proof_v4`
(`tests/artifacts/real_document_pipeline/runs/20260614T_wsmap_auditable_role_aware_proof_v4/lietaer_pdf_chapter_region_report.json`)
passed acceptance with `failed_checks=[]`. The report has
`formatting_diagnostics` length `1`, `formatting_diagnostics_paths` length `1`,
`unmapped_source_count_basis=role_aware_formatting_coverage`,
`role_aware_effective_unmapped_source_count=0`,
`raw_unmapped_source_paragraph_count=0`,
`raw_unmapped_target_paragraph_count=0`, DOCX openable, images `12/12`, and
`final_generated_paragraph_registry=123`. No-LLM replay on the same report
returns `source_reconstruction_basis=final_generated_paragraph_registry`,
`unmapped_source_count=0`, `unmapped_target_count=0`. The archived FC spec
remains at
`docs/archive/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md`.

# WS-MAP. Fix the Real Loss Stage: Restore/Mapping (highest priority)

**Forensic finding (2026-06-14, run `20260614T_ws1_fc_close_live_proof`):** the
WS-1 proof failed the gate with 26 unmapped source / 32 unmapped target. A
no-LLM stage trace of all 26 was run (translated text of each residual searched
in the final DOCX by exact + fuzzy + token-overlap, and in the cleaned MD):

| Stage | Lost |
| --- | ---: |
| Import (no id) | 0 |
| Translation (no output) | 0 |
| Cleanup (gone from MD) | 0 |
| Conversion MD->DOCX (gone from DOCX) | 0 |
| **Restore/Mapping (text present in final DOCX, not matched)** | **26** |

**All 26 survive into the final DOCX.** Nothing is lost at translation, cleanup,
or conversion. The failure is entirely the formatting-restore matcher being too
strict: it maps source<->target by exact text equality, so it misses targets
whose text is present but slightly merged/reworded (body/lists, fuzz 0.92-1.0)
or where a heading's text is a substring blended into a larger target (headings,
exact-substring present). The role-aware credit returned 0 because it measured
the wrong relationship ("body dissolved into a *mapped neighbor*") while the real
situation is "text present in its *own unmapped/blended* target".

**Goal:** make the matcher connect source paragraphs to the targets that already
contain their text, and refocus the gate on real role loss.

**Scope:**
- **MAP-1 (closes ~18/26): bounded fuzzy/containment mapping pass.** After the
  existing exact strategies, add a pass that maps a still-unmapped source to a
  still-free target when similarity is high (SequenceMatcher ratio >= ~0.92 OR
  token-overlap >= ~0.85) AND exactly one such candidate exists, within a bounded
  index window. This is a justified measurement->mapping step *because the text is
  provably the same* — unlike past "guess by a fragment" heuristics.
- **MAP-2 (closes headings, ~8): heading-containment recovery.** When a heading
  source's text is an exact substring of a larger target, recognise it as a
  blended heading: map it and transfer heading style, or record it as a genuine
  role loss (split candidate). This is exactly the role loss the gate should
  catch.
- **MAP-3 (gate refocus): count role loss, not all unmapped.** After MAP-1/MAP-2
  the remaining unmapped should be only real heading/list/caption role losses.
  Refocus the gate on "is the structural role preserved" (the role-aware intent)
  on the correct relationship (present-but-unmapped / blended), not
  dissolved-in-neighbor.

**Verifiable result (via no-LLM replay on the saved WS-1 artifact, then a fresh
run):**
- Stage trace re-run shows the Restore/Mapping count drop from `26` toward the
  small set of genuine role losses; record the new number.
- **Zero false pairs:** every new fuzzy/containment map is spot-checked to be the
  correct target (role-compatible, same content); `rebuild_key_mapping_quality` /
  a mapping-quality check reports no role/style mismatch among new maps.
- Body/list residuals (the fuzz 0.96-1.0 set: p0042, p0059, p0060, p0119,
  p0120-p0126, ...) become mapped; headings (p0026, p0072, p0094, ...) are either
  mapped-with-heading-style or reported as explicit role loss.
- `unmapped_target` falls correspondingly; final DOCX still openable, images
  12/12, single restore pass.

**Guardrails / non-goals:** do not touch translation/cleanup/conversion (proven
loss-free). The fuzzy pass MUST require uniqueness + high threshold + spot-check;
it must not become a broad guess-by-fragment matcher. Do not resurrect the
embedded id-marker (FC5) — fuzzy mapping closes more (~18) than the marker (7)
and is simpler.

**Done:** Restore/Mapping residual reduced to a small, hand-checked set of real
role losses, with zero false pairs; gate refocused on role loss; full relevant
test files green.

**Progress 2026-06-14:** MAP-1 is valid. Bounded registry fuzzy mapping covers
the reviewed body/list set (`p0042`, `p0059`, `p0060`, `p0119`,
`p0120-p0126`, etc.) with role-compatible targets and no false pairs in the
spot-check. MAP-2/MAP-3 false heading credit was fixed after reviewer feedback:
heading credit now requires heading-format targets, and body-style text presence
is counted as role loss instead of coverage.

**Fresh proof 2026-06-14:** `20260614T_wsmap_heading_role_repair_proof_v3`
(`tests/artifacts/real_document_pipeline/runs/20260614T_wsmap_heading_role_repair_proof_v3/lietaer_pdf_chapter_region_report.json`)
passed acceptance with DOCX openable, images `12/12`, translation quality
`pass`, and `final_generated_paragraph_registry=123`. Manual DOCX spot-check:
`p0026 "Глава восьмая" -> Heading 2`, `p0050 "Глава девятая" -> Heading 2`,
`p0076 "Глава десятая" -> Heading 2`, `p0077 "ИСТИНА И ПОСЛЕДСТВИЯ" ->
Heading 1`, `p0092 "Глава одиннадцатая" -> Heading 2`, `p0093 "УПРАВЛЕНИЕ И
МЫ, ГРАЖДАНЕ" -> Heading 1`, `p0094 "Будущее из глубины веков?" -> Heading 1`,
and `p0072 "ЧАСТЬ ТРЕТЬЯ ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ" -> Heading 1`.

**Audit repair 2026-06-14:** clean restore now persists a reviewable restore
diagnostics artifact; replay can also reconstruct diagnostics from
`runtime.state.final_generated_paragraph_registry` and the saved final DOCX when
saved formatting diagnostics are absent or source-language-only. Fresh proof
`20260614T_wsmap_auditable_role_aware_proof_v4` records raw/effective source
residual `0/0`, raw target residual `0`, and no-LLM replay residual `0/0`.

Full-file tests after the repair: `tests/test_document_pipeline.py`
`142 passed`, `tests/test_format_restoration.py` `80 passed`,
`tests/test_validation_formatting_replay.py` `7 passed`, and
`tests/test_real_document_pipeline_validation.py` `90 passed`.

**Ready for review before WS-2.** WS-2 and WS-3 still start only after reviewer
accepts this auditable WS-MAP/WS-1 closure.

# WS-2. Generalize the Role-Aware Gate Beyond One Document

**Goal:** prove the role-aware reframe holds on more than the single excerpt
before trusting it as the product gate.

**Scope:**
- Run the role-aware gate on at least 2-3 other corpus profiles (e.g.
  first-20-pages, full-benchmark), using the no-LLM replay where a saved final
  DOCX exists and fresh runs only where needed.
- For each: record raw vs role-aware effective unmapped, the credited
  (body-dissolved) set, and the real-loss (heading/list/caption -> body) set.
- **Manually spot-check** a sample of credited items: is each genuinely covered,
  or is the fuzzy evidence over-crediting? Tune the evidence threshold
  (measurement-only) if false credit is found.

**Verifiable result:**
- A cross-document table: per document, raw `unmapped_*`, role-aware effective,
  credited count, real-loss count, false-credit count from the spot-check.
- A written conclusion: does role-aware generalize, and what evidence threshold
  is safe across documents (not tuned to one).

**Guardrails / non-goals:** measurement-only changes to evidence; do not relax
the gate by asserting coverage without spot-check proof; do not tune to a single
document.

**Done:** role-aware gate validated (or corrected) on >=3 documents with a
documented safe threshold and zero unexplained false credits.

**Progress 2026-06-14:** WS-2 found and fixed a cross-document authority bug.
On `lietaer-pdf-full-benchmark`, the restore diagnostic already had a
role-aware residual classification, but the translation-quality authority still
preferred `topology_unit` for source coverage. That masked a large source-side
role-aware residual (`102 raw / 100 effective` in the first full probe) behind a
small topology-unit count. The source-side authority now uses
`role_aware_formatting_coverage` whenever a role-aware formatting diagnostic is
available; topology-unit authority remains available for target-side counts and
structural diagnostics.

Fresh WS-2 proof runs after this correction:

| Profile | Run | Acceptance | Failed checks | Source | Mapped | Target | Raw source | Effective source | Credit | Raw target | Source basis | Images |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `lietaer-pdf-chapter-region-core` | `20260614T_ws2_chapter_region_role_aware_probe_v5` | pass | `[]` | 135 | 134 | 134 | 0 | 0 | 0 | 0 | `role_aware_formatting_coverage` | 12/12 |
| `lietaer-pdf-first-20-benchmark` | `20260614T_ws2_first20_role_aware_probe_v3` | fail | `false_fragment_headings_present` | 48 | 43 | 43 | 0 | 0 | 0 | 0 | `role_aware_formatting_coverage` | 1/1 |
| `lietaer-core` | `20260614T_ws2_lietaer_core_role_aware_probe_v2` | fail | `centered_short_paragraphs_preserved` | 62 | 58 | 58 | 0 | 0 | 0 | 0 | `role_aware_formatting_coverage` | 7/7 |
| `lietaer-pdf-full-benchmark` | `20260614T_ws2_full_benchmark_role_aware_probe_v2` | fail | `formatting_diagnostics_threshold`, `unmapped_source_threshold`, `false_fragment_headings_present` | 1215 | 794 | 874 | 88 | 85 | 3 | 80 | `role_aware_formatting_coverage` | 55/55 |

Full-benchmark residual classes in the fresh role-aware artifact:
`content_survived_but_format_role_lost=35`,
`unproven_or_marker_closable=36`, `true_aggregate_relation_gap=14`,
`format_neutral_body_dissolved_creditable=3`.

Spot-check result:
- Heading mappings: `bad_heading_mappings=0` across all four fresh reports.
- Format-neutral credits: only full-benchmark has credits (`3`), all body
  year-fragment credits into `Normal` targets (`p0646`, `p0659`, `p0764`); no
  heading/list/caption credit found.
- List mappings: chapter-region `19/19`, `lietaer-core 3/3`, and full-benchmark
  `237/237` have list restoration decisions (`kept_existing_target_numbering`
  or `restored`). Direct DOCX index spot-checks were cross-checked against
  nearby raw paragraphs because target registry indexes omit some empty
  paragraphs.
- No unexplained false credit was found in the checked set.

No-LLM replay was run as secondary evidence. It reports
`source_reconstruction_basis=final_generated_paragraph_registry` for
chapter-region (`0/0`) and saved source registry replay for first-20/core/full.
Replay is useful as a current-code cross-check, but the authoritative WS-2
counts above are the in-pipeline diagnostics.

Full-file tests after the WS-2 authority correction:
`tests/test_document_pipeline.py` `142 passed`,
`tests/test_real_document_pipeline_validation.py` `90 passed`,
`tests/test_format_restoration.py` `80 passed`, and
`tests/test_validation_formatting_replay.py` `7 passed`.

**WS-2 review conclusion:** the role-aware gate is now generalized beyond the
chapter-region proof and is not tuned to one document. It passes the short
documents and fails the full benchmark honestly, with measured residuals instead
of a topology-unit masked pass.

**Reviewer correction / WS-MAP2 trigger:** independent forensic on the full-book
`88` raw source residuals shows this is **not** an 85-defect product catalogue:
`80/88` are present in the final DOCX and are matcher misses; only `8/88` are
absent or heavily reworded, mostly small note fragments such as `ibid`/numbered
notes. Therefore the full-book failure is a matcher-generalization gap, not a
content-loss baseline. WS-3 must not start from "85 defects"; WS-MAP2 must first
scale the present-but-unmapped matcher to book size.

# WS-MAP2. Scale the Matcher to Full-Book Density

**Goal:** reduce full-book present-but-unmapped residuals before treating the
book-scale run as the WS-3 baseline.

**Forensic finding (2026-06-14, run
`20260614T_ws2_full_benchmark_role_aware_probe_v2`):**

| Full-book residual class | Count |
| --- | ---: |
| Text present in final DOCX, matcher missed it | 80 |
| Absent / heavily reworded, mostly note fragments | 8 |

This is the same broad class as the chapter-region `26` Restore/Mapping misses,
but the small-excerpt MAP-1 strategy does not scale: full books contain many
near-duplicates (repeated list patterns, notes, `ibid`, page/index fragments),
so strict candidate uniqueness rejects many otherwise safe mappings.

**Scope:**
- Generalize fuzzy/containment mapping for book density without adding
  document-specific literals.
- Prefer local uniqueness and local neighbourhood evidence over global
  uniqueness where the final DOCX proves the text is present.
- Add explicit mapping branches for the observed full-book classes:
  `target_exists_text_align_missed` and `target_occupied_by_mapped_neighbor`,
  preserving the role-by-target-style rule.
- Keep role-sensitive safety: heading source maps only to heading-format target;
  list source must have final target numbering/marker evidence; body-only
  dissolved credits remain body-only.
- Treat `ibid`/note numbering fragments as a separate note-handling bucket, not
  broad content loss.

**Verifiable result:**
- No-LLM replay or fresh full-book proof shows raw/effective source residual
  dropping from `88/85` toward the small note-fragment set.
- A stage trace records present-but-unmapped -> mapped reduction and remaining
  absent/note fragments.
- Spot-checks on the new maps show zero false pairs across high-risk duplicate
  areas (lists, notes, repeated headings, index-like entries).
- Short-document proofs (`chapter-region`, `first-20`, `lietaer-core`) do not
  regress.

**Guardrails / non-goals:** no broad substring guessing, no full-book literals,
no verifier-as-gate, no credit based only on text presence when role is lost.
Do not proceed to WS-3 until the full-book residual is measured as mostly real
or note-specific rather than matcher-missed.

**Done:** full-book matcher residual is reduced to a small, hand-checked set of
real absence/note fragments; the safe threshold is documented and full relevant
test files are green.

**2026-06-15 projected-pass guardrail correction:** reviewer forensic flagged
that the projected matcher can only use local position as a search window, not
as proof of identity. The implementation now requires an explicit text floor for
`projected_registry_fuzzy`: exact/contained text evidence, or token Jaccard
`>=0.50`, or high token overlap with matching target coverage and sequence
ratio. A regression test covers the previous unsafe shape: two good positional
anchors around a near-looking sequence-only target with no shared tokens must
remain unmapped. Current offline replay audit against
`20260614T_ws_map2_full_benchmark_projected_probe` reports
`projected_registry_fuzzy=33` and `projected_bad_by_current_generated_text_floor=0`,
but WS-MAP2 remains open until the same zero-false-pair rule is confirmed on a
fresh in-pipeline full-book proof and the remaining residual bucket is classified
with the reviewer-facing false-pair checker.

**2026-06-15 canonical false-pair checker:** reviewer and agent agreed that
false-pair audits must use matcher indexing:
`formatting_diagnostics.target_registry[mapped_target_index]`, never raw
`doc.paragraphs[mapped_target_index]`. The offline classifier now emits
`mapping_text_quality` for every reviewable diagnostic, including clean
diagnostics without residual rows. It compares `final_generated_paragraph_registry`
text against the target registry preview and reports checked/bad pairs for all
text-verified strategies. The same pass exposed one historical
`paragraph_id_registry_similarity` year-fragment false pair (`2011 г.` ->
`2012 г.`) in the saved full-book report, so that fallback now uses the same
registry evidence/text-floor and skips heading sources. Current-code replay of
`20260614T_ws_map2_full_benchmark_projected_probe` reports
`mapping_text_quality.checked_count=65`, `bad_pair_count=0`, and
`projected_registry_fuzzy=37`.

**2026-06-15 fresh embedded-quality proof:** run
`20260615T_ws_map2_full_benchmark_embedded_quality` proves the false-pair audit
is now in the in-pipeline artifact, not only in offline replay:
`source_count=1215`, `mapped_count=869`, `target_count=888`,
`raw_unmapped_source=23`, `effective_unmapped_source=20`,
`unmapped_target_actual=0`, `mapping_text_quality.checked_count=66`,
`bad_pair_count=0`, `bad_strategy_counts={}`. Strategy counts:
`bounded_registry_fuzzy=48`, `bounded_registry_heading_containment=6`,
`paragraph_id_registry_similarity=4`, `projected_registry_fuzzy=8`,
`image_anchor=54`, `image_anchor_contained=1`. Acceptance still fails on
`formatting_diagnostics_threshold`, `unmapped_source_threshold`, and
`false_fragment_headings_present`, so WS-MAP2 remains open. The remaining
role-aware bucket is now small and explicit: `23` raw source residuals, `3`
format-neutral body dissolved credits, `20` effective residuals split across
notes/year fragments and a few heading/title fragments.

**2026-06-15 final full-book proof / WS-MAP2 closed:** a single canonical
full-book run on commit `e4c850c` completed without another inner-loop series:
`20260615T091759Z_1013_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne`.
The in-pipeline report passes acceptance with `failed_checks=[]` and records
`basis=role_aware_formatting_coverage`, `source_count=1215`,
`mapped_count=884`, `target_count=889`, `mapping_text_quality.checked_count=71`,
and `mapping_text_quality.bad_pair_count=0`. Source-side formatting coverage is
measured as `raw_unmapped_source=12`, `format_neutral_creditable_count=2`, and
`role_aware_effective_unmapped_source_count=10` (`<=12`). Target-side residuals
are reduced to five short note/year markers only:
`unmapped_target_residual_diagnostics.counts={"short_note_or_marker": 5}`;
the role-aware diagnostic target residual is therefore `5` (`<=6`), while the
acceptance gate also reports `unmapped_target_threshold actual=0` on
`topology_unit` authority. The translation-quality gate is `pass`,
`false_fragment_heading_count=0`, the DOCX is openable/zip-valid, and the output
contains `55` inline shapes. WS-MAP2 is closed: the full-book matcher residual
is now a small, auditable note-fragment set with zero text-quality bad pairs.

# WS-3. Full-Book End-to-End Run

**Goal:** move from excerpt to a full book — the actual product target.

**Scope:**
- Take one full book through the complete pipeline (import -> translate ->
  cleanup -> single rebuild/restore -> validate) with verifier off.
- Exercise book scale: chunking, progress/artifact capture per stage, retries,
  and record wall-clock + cost.
- Catalogue every failure mode that appears at scale (translation aborts,
  empty_response, memory, time, malformed chunks) — do not fix them inline;
  record them for WS-4.

**Verifiable result:**
- A completed full-book run that produces an openable final DOCX, images
  preserved, and a role-aware gate result recorded for the whole book.
- A failure-mode catalogue with frequency and stage for each issue.
- Runtime and approximate cost recorded.

**Guardrails / non-goals:** do not regress the chapter-region result; do not
introduce per-document hacks to force a book through; if a stage cannot complete,
record the controlled failure, do not silently truncate output.

**Done:** one full book produces a complete artifact set with the gate result and
a failure-mode catalogue.

# WS-4. Reliability Hardening At Book Scale (driven by WS-3)

**Goal:** make a full-book run survive its own failure modes.

**Scope:** address the WS-3 catalogue in priority order. Likely: persistent
`empty_response` recovery at scale (is PR-R0 enough across hundreds of blocks?),
bounded retries, controlled per-block fallback artifacts instead of whole-run
aborts, and progress that lets a long run be observed/resumed.

**Verifiable result:**
- A full-book run with **zero uncontrolled pipeline aborts**; any block that
  cannot be translated produces an explicit fallback artifact/event, and the run
  still finishes with a complete document.
- Before/after the hardening: failure count from WS-3 -> after.

**Guardrails / non-goals:** do not change the translation model/prompt or reader
cleanup behaviour; reliability only. No silent data loss — every fallback is
visible in artifacts.

**Done:** a full book completes end-to-end with no uncontrolled abort and all
failures surfaced as artifacts.

# WS-5. Tooling & Process Hardening (cross-cutting, ongoing)

**Goal:** keep the cheap, honest feedback loop that the last iteration painfully
earned.

**Scope:**
- Extend the no-LLM replay so the full role-aware/coverage diagnostic set can be
  recomputed offline from any saved run (close the stale-artifact fidelity gap
  where it matters).
- A dev/CI contract that runs full relevant test files, not focused selectors.
- Audit remaining multi-field positional returns in the pipeline and convert the
  fragile ones to named results.

**Verifiable result:**
- Replay reproduces the role-aware effective number for a saved run within a
  stated tolerance, no model call.
- Test contract documented/enforced; positional-return audit list with
  conversions done for the fragile ones.

**Guardrails / non-goals:** tooling only; no behavioural change to the product
pipeline.

**Done:** offline replay covers the role-aware metric; full-file test discipline
enforced; fragile returns converted.

---

# Sequencing

1. **WS-1** first (close the open iteration; small). NOTE: the WS-1 proof already
   ran and exposed the mapping issue below — WS-1 stays open until WS-MAP makes
   the gate meaningful and the final proof passes.
2. **WS-MAP** next and highest priority (fix the real loss stage: restore/mapping).
   The forensic trace proved the 26 residual are present-but-unmapped, not lost in
   translation/cleanup/conversion. Nothing downstream is trustworthy until the
   matcher stops dropping them.
3. **WS-2** (trust the gate beyond one document before scaling on it) — only after
   WS-MAP, so it generalises a matcher that actually works.
4. **WS-3** (the product goal: full book) — the largest chunk.
5. **WS-4** falls out of WS-3 and is driven by its catalogue.
6. **WS-5** runs alongside, prioritised whenever the inner loop gets expensive or
   a regression slips through.

Do not start WS-2/WS-3 before WS-MAP: a book-scale run measured by a matcher that
drops present-but-unmapped text would mislead. WS-1.5 ("lost vs reworded") is
discharged by the WS-MAP forensic finding — nothing is lost, all 26 are
present-but-unmapped.
