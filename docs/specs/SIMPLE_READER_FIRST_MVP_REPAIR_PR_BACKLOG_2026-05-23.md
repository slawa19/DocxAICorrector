# Simple Reader-First MVP Repair PR Backlog

Date: 2026-05-23
Status: Active implementation backlog; code-readiness audit updated 2026-05-30

Source specs and evidence:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/archive/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md` (archived dead-end context)
- Latest completed comparison-only run used for this audit:
   `tests/artifacts/real_document_pipeline/runs/20260530T071434Z_968_Rethinking-money-chapter-region-pages-10-11-and-156-217/`
- Latest completed cleanup report used for this audit:
   `.run/ui_results/20260530_102025_Rethinking-money-chapter-region-pages-10-11-and-156-217.reader_cleanup_report.json`
- Active model/strategy experiment log:
   `docs/specs/READER_CLEANUP_MODEL_STRATEGY_EXPERIMENTS_2026-05-30.md`
- Latest manifest caveat:
   `tests/artifacts/real_document_pipeline/lietaer_pdf_chapter_region_latest.json` currently points at `20260530T074105Z_1139_...` with `status=in_progress`; do not use that run as success/failure proof until it completes.

## Purpose

Convert the latest Simple Reader-First MVP findings into a small, ordered PR
backlog that preserves the agreed AI-first cleanup architecture.

The current MVP run proved that the pipeline can produce reviewable raw and
cleaned artifacts, and that cleanup improves readability. The next bottleneck is
stable product-visible cleanup proof: failed cleanup chunks must be eliminated
before per-category changes are trusted, and the remaining reader-visible
defects must be reduced without turning the backlog into polish-to-zero work.

This backlog is not a request to make the comparison-only run green by adding
document-specific deterministic fixes. It is a request to improve bounded AI
cleanup operations on the remaining reader-visible defects while preserving the
code-owned safety and verifier evidence contracts.

AI-first priority is the controlling rule for all remaining work. When a real
run gets worse, first inspect whether the AI proposed valid bounded operations
that code rejected too narrowly, or whether the prompt/model produced non-exact
operations. Do not respond by adding regex-repair that independently finds and
rewrites document text. Regex may support safety acceptance for AI-p roposed exact
substrings, pre-audit evidence, or reporting; it must not become a hidden second
cleanup engine.

## User-Facing Summary

The MVP works as a draft-quality comparison tool: it creates output and makes
the text more readable. It is not yet final-quality because many page headers,
page numbers, fused headings, and paragraph breaks remain.

The target status for this loop is a truthful readable draft, not a perfect
book. `readable_draft_not_acceptance_ready` is an acceptable MVP result when the
run completes, cleanup/verifier evidence is stable, no-harm invariants hold, and
remaining issues are visible in the report.

The main reason is now product-quality, not validator architecture: cleanup
successfully runs, but the remaining reader-visible defects are still too common
for final output. Earlier backlog slices targeted PR-H directly; the current
next move is to test whether cleaner source input makes PR-H stable instead of
adding more post-translation runtime guards.

## 2026-05-30 Code Readiness Audit

Current code is no longer at the original May 24 backlog baseline. The reader
cleanup MVP has runtime support for the main PR-H safety and operation-contract
slices, but the latest completed proof does not reach MVP exit.

Code-ready / implemented enough to validate:

- Runtime reader cleanup is integrated in `late_phases` and writes raw, cleaned,
   DOCX, and reader cleanup report artifacts under `.run/ui_results/`.
- `reader_cleanup_mvp` has schema repair, exact-field recovery for
   `normalize_heading_boundary`, standalone numeric delete page-context safety,
   page-furniture/caption anchor repair, same-block sequencing diagnostics, and a
   narrow adjacent/split heading application path.
- Unit coverage exists for numeric delete safety, protected heading/first/last
   blocks, page-caption anchor repair, ignored operation reasons, heading
   boundary diagnostics, and Anthropic SDK request routing.
- Provider/model configuration includes an Anthropic provider, timeout support,
   and model selector normalization for `anthropic:claude-sonnet-4.6` / working
   direct Anthropic id `claude-sonnet-4-6`.
- Source-cleanup evidence is available through the existing layout artifact
   cleanup/reporting path and validation profiles can select
   `layout_artifact_cleanup_mode=remove`; this is the current implementation
   route for the source-cleanup experiment, not a new broad source rewrite
   subsystem.

Not ready / still blocking MVP exit:

- Latest completed proof run `20260530T071434Z_968_...` succeeded as a pipeline
   run and kept no-harm gates green, but verifier proof failed with
   `reader_verifier_status=failed`, `reader_verifier_reason=execution_failed`,
   and `reader_verifier_remaining_issue_missing_required_text`.
- Deterministic pre-audit still reports `heading_fused_with_body=5` and
   `fragmented_paragraph=6`; top reader-visible blockers are not closed.
- The new adjacent/split heading path did not get exercised in the latest
   completed proof (`heading_boundary_normalized_across_adjacent_block` count was
   `0`), so it is code-ready but not proven useful on the real document.
- Cleanup application diagnostics still show local operation-shape problems:
   `prior_same_block_operation_not_applied=2`,
   `heading_boundary_substrings_not_found=2`,
   `heading_boundary_unaccounted_text=1`, and
   `remove_inline_noise_not_exact_noise_pattern=2`.
- A fresh completed source-cleanup-remove comparison run is still required
   before promoting source cleanup as the next production path. Older runs show
   the profile exists, but the latest completed audit run did not provide the
   needed fresh proof.

Readiness conclusion: the code is ready for the next evidence-producing PR, not
for MVP exit. The next slice should be proof/diagnostic driven: repair verifier
preconditions first, then rerun the source-cleanup-remove comparison path and
only after that decide whether remaining PR-H work belongs to prompt selection,
operation contract, or source cleanup.

May 26 replay experiments changed the preferred next move. Frozen cleanup replay
showed that runtime safety is not the dominant remaining problem: valid exact
cleanup operations are accepted, broad heading-eating `remove_inline_noise`
proposals are rejected, and prompt variants only partially improve stability.
The bigger instability comes from the translated raw Markdown changing shape
between runs. Therefore the next useful iteration should test a two-stage
cleanup strategy: remove only obvious source-side page furniture before
translation, then keep the existing post-translation AI reader cleanup as the
reader polish pass.

## Non-Negotiable Architecture Rules

- Keep cleanup AI-first.
- Do not add Lietaer-specific regexes, phrase lists, heading literals, or page
  header strings as cleanup logic.
- Do not expand the shared page-furniture phrase library for this document.
- Do not use deterministic Markdown rewrites to split headings, merge
  paragraphs, or remove document-specific running headers.
- Do not turn source cleanup into a broad pre-translation rewrite pass. It may
   remove only obvious non-semantic source artifacts with reliable page-boundary,
   repetition, or extraction evidence, and it must report every removal.
- Do not implement verifier-suggested `deterministic_last_resort` as regex
   repair unless the backlog is updated with cross-document evidence that
   prompt/model/operation-contract/safety-application paths cannot solve the
   defect without violating exact-match cleanup.
- Do not tune Stage 1, Stage 2, topology, or structure-recognition windows for
  these reader-cleanup defects.
- Do not tighten or relax acceptance thresholds to make the comparison-only run
  look better.
- Do not treat absolute remaining-issue counts as polish targets. Use them as
   comparison signals on the same document/profile, and prefer relative movement
   in top blocker categories plus qualitative review over numeric perfection.
- Treat `reader_cleanup_failed_chunk_count = 0` as a hard proof gate for this
   backlog. A run with failed cleanup chunks may still be useful runtime evidence,
   but it must not be used to conclude that a PR improved or regressed a defect
   category.
- Validation must remain observational: it may run profiles, read artifacts,
   score results, build evidence, and report findings, but it must not implement
   production repair behavior or mutate final Markdown/DOCX artifacts.
- Keep code responsible for IDs, hashes, schema validation, exact-match
  application, protected-block rules, safety budgets, and reporting.
- Keep AI responsible for document-specific judgement: what is page furniture,
  what heading boundary is intended, and whether adjacent blocks are one broken
  paragraph.

## Ownership Map

Use this map to decide where a defect belongs before writing code:

| Defect | Owning layer | Allowed mechanism | Not allowed |
| --- | --- | --- | --- |
| Old page numbers, running headers, footers | `reader_cleanup_mvp` | AI-selected bounded operations: `delete_block` for standalone furniture, `remove_inline_noise` for exact inline furniture | Global number deletion, document-specific phrases, regexes for this book |
| Obvious source-side page furniture before translation | extraction/preparation or a dedicated audited source-cleanup step | Remove only standalone page numbers, blank-page markers, technical placeholders, or repeated page-boundary headers with reliable source evidence and a removal report | Source prose rewriting, unique heading deletion, document-specific phrase lists, source-level AI rewriting, or anything difficult to audit |
| Heading fused with body text | `reader_cleanup_mvp` | `normalize_heading_boundary`, `split_block`, or composed exact operations after removing page furniture | Deterministic heading detection, invented heading/body text, unaccounted source text |
| TOC page numbers / generated TOC fidelity | not a target for this reader-first repair backlog | Filter/ignore TOC-only defects in verifier evidence when the profile marks TOC out of scope; remove stale TOC page numbers only through an explicit reader cleanup policy after translation | Broad pre-translation TOC deletion, rebuilding a correct translated TOC, preserving original page numbers, or treating TOC reconstruction as acceptance-critical |
| Footnote markers/footnote blocks | `reader_cleanup_mvp` only after explicit MVP policy | `delete_block` or `remove_inline_noise` with exact evidence and a `drop_footnotes`/equivalent policy | Silent deletion of semantic numbers, numbered lists, citations needed by the selected mode |
| Bold, italic, emphasis, heading/subheading styles, list styles | formatting transfer / intermediate model / DOCX writer | Preserve source run-level formatting and structural style evidence through final DOCX | Guessing styles from plain cleanup text alone or mixing this into reader-cleanup deletion work |
| Images from PDF-derived documents | PDF import / image extraction / main pipeline asset handoff / DOCX reinsertion | Locate where image assets disappear in the main pipeline; restore asset placeholders/reinsertion in a dedicated image PR | Restoring images through reader-cleanup prompts, replacing images with descriptions, or hiding image loss inside formatting work |
| Verifier blind spots | verifier/reporting layer | Add checks only after the output behavior is fixed or as a small supporting change | Treating verifier prompt tuning as the primary fix for bad output |
| Validation applying cleanup or rewriting DOCX | runtime pipeline / reader cleanup orchestration | Move repair execution into the main pipeline and let validation consume produced artifacts | Validation scripts applying AI cleanup, overwriting cleaned Markdown, or rebuilding DOCX |

## Current Visual MVP Roadmap

The post-PR-F/PR-G visual review changed the next priorities. Correct TOC
reconstruction is explicitly not a goal for this backlog. In translated output,
source page numbers become stale and do not need to be preserved; TOC page
numbers may be ignored by verifier evidence or removed by explicit
post-translation reader policy when they harm reading. Do not broaden source
cleanup into pre-translation TOC deletion.

The visible failures to address are old page furniture, running headers/footers,
page numbers glued into prose, heading/body fusion, fragmented paragraphs,
basic list readability, source formatting preservation (bold, italic, emphasis,
heading/subheading styles, list styles), and missing images.

Work must be split by owner:

- **PR-G: Validator Boundary Refactor**
   - Scope: validation architecture and reader-cleanup runtime orchestration.
   - Remove validation-owned anchor repair execution and artifact mutation.
   - Ensure any second cleanup/anchor repair pass runs inside the main pipeline
      or is not run at all; validation may only record verifier anchors as
      evidence.
   - Must happen before PR-H/PR-I/PR-J proof work, because visual/formatting
      evidence is unreliable while validation can rewrite DOCX through a
      simplified path.
- **PR-H: Reader Cleanup Visual Blockers**
   - Scope: `reader_cleanup_mvp` only.
   - Fix old page numbers, running headers/footers, page-furniture glued into
      prose, heading/body fusion, fragmented paragraphs, and reader-visible list
      marker cleanup.
   - Completed sub-slice: targeted page-furniture plus image-caption plus
      continuation repair. This was code-owned orchestration inside
      `reader_cleanup_mvp`, not a validation-side repair and not a prompt-only
      contract.
   - Current active sub-slice: PR-H2 Heading Boundary Application Diagnostics.
      This is a reader-cleanup diagnostic/classification slice first; it must
      not broaden into heading repair implementation until the current fused
      heading anchors are classified by owner and risk.
   - Current May 26 evidence suggests no further runtime safety expansion should
      be made before testing source-side cleanup. Keep PR-H runtime stable while
      the next iteration measures whether pre-translation source cleanup reduces
      the raw translated noise that PR-H currently has to repair.
   - TOC reconstruction is out of scope. Verifier evidence may ignore TOC-only
      defects when TOC is out of scope; stale TOC page numbers may be removed
      only through explicit reader policy, not broad source cleanup.
   - Do not touch image reinsertion, bold/italic/style preservation, or verifier
      tuning except as small supporting evidence.
- **PR-I: Formatting Preservation**
   - Scope: formatting transfer / intermediate representation / DOCX writer.
   - Preserve bold, italic, emphasis/highlight where source evidence exists.
   - Preserve heading and subheading style levels, plus list styling/numbering
      when source evidence and translated structure can be mapped safely.
   - Do not infer formatting purely from plain cleanup text, and do not treat
      stale TOC page numbers as formatting to preserve.
- **PR-J: Image Handoff/Reinsertion**
   - Scope: PDF import, image extraction, artifact handoff, DOCX reinsertion.
   - If images are expected to flow through the main pipeline, dedicate this PR
      to finding why PDF-origin images disappear during conversion/handoff.
   - Find where `image_count`, image placeholders, processed image assets, or
      output inline shapes becomes zero and fix that layer or document the
      upstream blocker.
   - Do not attempt image recovery in reader cleanup.

Future implementation slices must name exactly one of these scopes unless this
backlog is updated first. If a slice discovers a defect belongs to a different
owner, it must record the evidence and stop instead of broadening the PR.

### Remaining PRs In Plain Words

- **Fix verifier proof before declaring MVP status.** The latest completed run
   preserved artifacts and no-harm evidence, but verifier proof failed before a
   reliable cleaned-vs-raw conclusion. Repair the verifier required-text/runtime
   failure, then rerun the same comparison-only profile before using issue
   counts as promotion evidence.
- **Run the source-cleanup-remove experiment fresh.** Use the existing audited
   layout cleanup/reporting path with the source-cleanup-remove profile, then
   compare raw translated Markdown, cleaned Markdown, source cleanup evidence,
   reader cleanup report, and verifier output against the latest completed
   no-source-cleanup baseline.
- **Classify the remaining PR-H blockers from fresh evidence.** If source
   cleanup reduces page furniture and keeps safety green, keep PR-H as
   post-translation polish. If it does not, split the remaining work into one
   heading operation-contract slice and one fragmented-paragraph/caption slice;
   do not merge them into one broad cleanup PR.

- **Stabilize input before widening PR-H.** Continue PR-H only where AI-proposed
   bounded cleanup operations are valid but rejected too narrowly. The next
   planned iteration should instead test whether obvious source-side page
   furniture can be removed before translation so the post-translation cleanup
   receives less noisy raw Markdown. Do not keep adding runtime guards to chase
   translated forms that should not have reached translation.
- **Finish PR-H after source cleanup evidence.** If pre-translation cleanup does
   not reduce reader-visible noise, return to prompt/model discipline for PR-H.
   If it helps, keep PR-H as the post-translation polish layer and avoid turning
   it into a source-noise recovery engine.
- **Start PR-I after PR-H is stable.** PR-I begins when comparison-only runs
   consistently produce readable text with no false deletions/readability
   regressions, and the main remaining pain is book-like formatting: bold,
   italic, emphasis, heading/subheading styles, list styling, and DOCX style
   preservation.
- **Start PR-J independently when image loss matters.** PR-J begins when the
   desired output must preserve PDF-origin images and evidence shows images,
   placeholders, or inline shapes disappear in import/handoff/reinsertion. Do not
   wait for PR-I if images are a release blocker, but do not solve images through
   reader cleanup.
- **Do not reopen PR-G unless validation mutates artifacts again.** Validator
   work is only supporting evidence now: it may report, filter out-of-scope TOC
   findings, and explain ignored cleanup reasons, but it must not repair output.

### PR-H2: Heading Boundary Application Diagnostics

#### Scope

PR-H2 is limited to `reader_cleanup_mvp` diagnostics and backlog classification.
Validation remains observer-only: it may report verifier anchors, review/status,
and evidence, but it must not call cleanup as a repair executor, mutate cleaned
Markdown/DOCX, or rebuild cleaned DOCX. This slice must not add Lietaer-specific
heading literals, phrase lists, or deterministic regex repair. It also must not
touch the larger reader-first migration/decommission plan without separate
approval.

The first deliverable is a classification table for the current heading anchors,
not a broad heading repair. Fragmented paragraphs remain the next separate
slice; do not fix duplicate/orphan fragments by unsafe deletion.

#### Evidence Baseline

Baseline run:
`tests/artifacts/real_document_pipeline/runs/20260529T083946Z_1243_Rethinking-money-chapter-region-pages-10-11-and-156-217/`

Key baseline facts:

- `reader_verifier_overall_verdict=cleaned_better`
- `reader_cleanup_failed_chunk_count=0`
- `reader_verifier_remaining_issue_count=15`
- blocker group: `heading_fused_with_body=9|fragmented_paragraph=6`
- cleanup application diagnostics:
   `prior_same_block_operation_not_applied=2`,
   `heading_boundary_unaccounted_text=2`,
   `heading_boundary_substrings_not_found=1`,
   `remove_inline_noise_not_exact_noise_pattern=7`
- accepted operation counts included `normalize_heading_boundary=13`

Important evidence nuance: the blocker group says `heading_fused_with_body=9`,
but the run artifacts contain seven unique cleaned-Markdown heading locations
plus two lower-severity verifier-summary duplicates for lines 249 and 277. The
filtered TOC pre-audit issue at `cleaned_markdown:1` is out of scope for TOC
reconstruction and is not counted as a PR-H2 repair target.

#### Current Heading Classification

| Line ref / snippet | Issue kind | Likely owner | Suggested next action | Risk notes |
| --- | --- | --- | --- | --- |
| `249`: `ПЯТЬ МИЛЛИАРДОВ... Вдохновленный примером...` | genuine heading+body | prompt selection | prompt tweak | Exact prefix/body split looks safe if the model copies the full body tail; duplicated as both verifier and pre-audit issue. |
| `277`: `ВАЛЮТА ДЛЯ ЧРЕЗВЫЧАЙНЫХ СИТУАЦИЙ Ураган...` | genuine heading+body | prompt selection | prompt tweak | Exact prefix/body split looks safe; keep disaster-event prose intact; duplicated as both verifier and pre-audit issue. |
| `cleaned_markdown:249`: same snippet as line 249 | genuine heading+body duplicate | verifier taxonomy | verifier dedup/filtering | Do not treat as a second repair target; use as evidence that review/pre-audit dedup needs clearer reporting. |
| `cleaned_markdown:277`: same snippet as line 277 | genuine heading+body duplicate | verifier taxonomy | verifier dedup/filtering | Do not double-count implementation impact if one block-level operation fixes it. |
| `cleaned_markdown:303`: `ИСТИНА И ПОСЛЕДСТВИЯ: извлеченные уроки` | title+subtitle / heading-only verifier false positive | verifier taxonomy | verifier filtering | Looks like a heading plus subtitle, not running prose; avoid `normalize_heading_boundary` unless source evidence proves a body sentence starts here. |
| `cleaned_markdown:351`: `ВОСХОЖДЕНИЕ НАЦИСТСКОЙ ПАРТИИ Подавление...` | genuine heading+body with missing exact substrings | operation contract / prompt selection | prompt tweak first; inspect mixed-language exactness before contract tweak | Ignored cleanup operation used `with` inside Russian body substring, producing `heading_boundary_substrings_not_found`; do not relax exact matching. |
| `cleaned_markdown:359`: `СОЕДИНЕННЫЕ ШТАТЫ Во время...` | genuine heading+body | prompt selection | prompt tweak | Long body tail; next prompt should emphasize full body remainder, not teaser body substring. |
| `cleaned_markdown:411`: `УПРАВЛЕНИЕ И МЫ, ГРАЖДАНЕ Древнее будущее?` | title+subtitle / heading-only verifier false positive | verifier taxonomy | verifier filtering | Second segment is a subtitle/question, not narrative prose; leave as known limitation unless verifier taxonomy is updated. |
| `cleaned_markdown:521`: `ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ... СПРАВЕДЛИВОСТЬ. Авиабизнес...` | genuine heading+body after same-block conflict | safety application / operation contract | operation-contract diagnostic, then prompt tweak | Cleanup proposed only trailing `И СПРАВЕДЛИВОСТЬ.` after another operation had already affected the block; next implementation should preserve full semantic heading or classify as same-block conflict, not split a trailing tail. |

#### Ignored Operation Mapping

Current machine-readable detail is enough to classify the rejected heading
operations, but not enough to directly map every ignored operation to a verifier
anchor without manual snippet matching.

- `heading_boundary_substrings_not_found=1` maps to
   `cleaned_markdown:351`: the proposed body substring contained a non-exact
   mixed-language token (`with`) and was correctly rejected.
- `heading_boundary_unaccounted_text=2` maps to non-prefix heading proposals:
   one around `ЧАСТЬ ТРЕТЬЯ. ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ` after preceding quote text,
   and one around `21 РОТТЕРДАМ.` after preceding quote/page-residue text. These
   are operation-shape problems: `normalize_heading_boundary` is prefix-only,
   so pre-heading prose requires `split_block` or a different bounded contract.
- `prior_same_block_operation_not_applied=2` currently maps to
   `join_fragmented_paragraph`, not to `normalize_heading_boundary`; keep it as
   fragmented-paragraph evidence for the next slice.
- `block_already_removed` for a proposed trailing heading split around
   `И СПРАВЕДЛИВОСТЬ.` is a same-block sequencing/targeting symptom, but it is
   not counted in the summarized heading-boundary reasons. It should be kept as
   PR-H2 evidence because the remaining verifier issue at `cleaned_markdown:521`
   still names the full semantic heading.

If this diagnostic needs to become more machine-readable, extend
`heading_boundary_application_diagnostics` with accepted/ignored examples and
anchor/block IDs from report payloads; do not add repair behavior in validation.

#### Acceptance Criteria

- Backlog records the current run ID, issue counts, ignored heading reasons, and
   the classification table above.
- PR-H2 classifies each current heading issue as one of: genuine heading+body,
   heading-only verifier false positive, page/header residue, title+subtitle,
   same-block operation conflict, missing exact substrings, or unaccounted
   prefix/prose.
- Each class has an owner: prompt selection, operation contract, safety
   application, verifier taxonomy, or known draft limitation.
- The next implementation micro-slice is chosen explicitly before code changes:
   start with prompt tweaks for genuine prefix heading+body cases, keep exact
   substring safety strict, and handle verifier taxonomy/filtering for
   title+subtitle false positives separately.
- No document-specific heading strings, regex repair, TOC reconstruction, or
   fragmented-paragraph deletion is introduced by this slice.

#### PR-H2a / PR-H2b Continuation Note

PR-H2a prompt guidance for genuine prefix heading+body is unit-ok, but the first
real comparison-only proof is not acceptable as success proof. Run
`20260529T105829Z_1195_Rethinking-money-chapter-region-pages-10-11-and-156-217`
reduced `heading_fused_with_body` from `9` to `8`, kept
`fragmented_paragraph=6`, kept `page_furniture_inline=0`, and had
`reader_cleanup_failed_chunk_count=0`, but it reported a possible false
deletion after accepting `delete_block` for standalone numeric block `b_000119`
with `reason=page_number` and `raw_text_preview="8"`.

The next micro-slice is PR-H2b: Numeric Delete Safety / Footnote vs Semantic
Numbering. A standalone numeric `delete_block` must not be considered
proof-safe by model reason alone. It should be accepted only when tied to
document-agnostic page-boundary, repeated header/footer, or explicit
page-furniture evidence. If that evidence is absent, keep the numeric block and
report a clear ignored reason instead of risking deletion of footnote, citation,
principle/list numbering, or other semantic numeric markers.

PR-H2b closed the safety blocker in real comparison-only run
`20260529T173533Z_1197_Rethinking-money-chapter-region-pages-10-11-and-156-217`:
`reader_cleanup_accepted_delete_block_count=0`, `b_000119` is ignored with
`standalone_number_delete_requires_page_context`, `false deletions=0`,
`readability regressions=0`, `reader_cleanup_failed_chunk_count=0`, and
`page_furniture_inline=0`. This is a safety proof, not a PR-H2 heading proof:
the status still reports `heading_fused_with_body=13`,
`fragmented_paragraph=2`, and `duplicate_fragment=1`.

The next micro-slice is PR-H2c: Heading Evidence Classification / Unique Site
Accounting. Before further prompt hardening, classify the current heading
signals by unique cleaned Markdown site and by source. The latest report has
`pre_audit_issue_counts.heading_fused_with_body=9`, while the aggregated
reader-visible status reports `heading_fused_with_body=13` because several
lines are surfaced both as verifier/model issues and pre-audit issues. PR-H2c
should distinguish true remaining heading sites from duplicated evidence and
then choose the next implementation slice from the remaining unique sites. Keep
validation observer-only: it may normalize, count, and classify evidence, but it
must not repair or rewrite Markdown/DOCX artifacts.

#### PR-H2c Unique Heading Evidence Snapshot

Run
`20260529T173533Z_1197_Rethinking-money-chapter-region-pages-10-11-and-156-217`
has 9 unique pre-audit `heading_fused_with_body` sites, not 13 unique heading
failures. The aggregated count of 13 comes from 9 pre-audit sites plus 4
verifier/model duplicate signals for the same cleaned Markdown line numbers
(`93`, `221`, `229`, `251`). Treat the status-level `heading_fused_with_body=13`
as evidence volume, not unique-site count.

| Unique site | Source signals | Classification | Likely owner | Suggested next action | Risk notes |
|---|---:|---|---|---|---|
| `cleaned_markdown:93` `КАК ЭТО РАБОТАЕТ: Местные органы власти...` | pre-audit + verifier duplicate | genuine prefix heading+body | prompt selection / operation coverage | runtime cleanup candidate; inspect why accepted heading ops did not cover this site | Safe only with exact full heading prefix and full body remainder. |
| `cleaned_markdown:221` `ГРАЖДАНСКИЕ ИНИЦИАТИВЫ... Через призму...` | pre-audit + verifier duplicate | genuine prefix heading+body | prompt selection / operation coverage | runtime cleanup candidate | Needs full uppercase heading prefix; no document-specific literal rules. |
| `cleaned_markdown:229` `БЕСПЛАТНЫЕ КЛИНИКИ... Здравоохранение...` | pre-audit + verifier duplicate | genuine prefix heading+body | prompt selection / operation coverage | runtime cleanup candidate | Exact substring safety should remain strict. |
| `cleaned_markdown:251` `ПЯТЬ МИЛЛИАРДОВ... Вдохновившись...` | pre-audit + verifier duplicate | genuine prefix heading+body | prompt selection / operation coverage | runtime cleanup candidate | PR-H2a target still remains in this run; diagnose operation proposal/acceptance gap before more prompt hardening. |
| `cleaned_markdown:281` `ВАЛЮТА ДЛЯ ЧРЕЗВЫЧАЙНЫХ СИТУАЦИЙ Ураган...` | pre-audit only | genuine prefix heading+body | prompt selection / operation coverage | runtime cleanup candidate | No duplicate verifier signal; still a unique remaining reader-visible site. |
| `cleaned_markdown:313` `ПРАВДА И ПОСЛЕДСТВИЯ: извлеченные уроки` | pre-audit only | title+subtitle / heading-only taxonomy | verifier taxonomy / known draft limitation | verifier filtering or known limitation | Do not split as body; no running prose remainder is present. |
| `cleaned_markdown:361` `ВОСХОЖДЕНИЕ НАЦИСТСКОЙ ПАРТИИ Подавление...` | pre-audit only | genuine prefix heading+body with ignored exact-substring proposal | operation contract / safety application | inspect `heading_boundary_substrings_not_found` before prompt changes | Rejection is correct if substrings are not exact; do not loosen safety. |
| `cleaned_markdown:425` `УПРАВЛЕНИЕ И МЫ, ГРАЖДАНЕ Древнее будущее?` | pre-audit only | title+subtitle / heading-only taxonomy | verifier taxonomy / known draft limitation | verifier filtering or known limitation | Subtitle/question, not body prose; runtime cleanup should not invent a body split. |
| `cleaned_markdown:533` `ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ... Авиабизнес...` | pre-audit only | genuine prefix heading+body / possible same-block sequencing residue | operation contract / sequencing diagnostics | inspect accepted/ignored operations around this block | Prior diagnostics showed same-block targeting symptoms; avoid broad prompt hardening until block-level evidence is clear. |

PR-H2c acceptance for the diagnostic slice:

- report both raw evidence volume and unique cleaned Markdown site count;
- mark duplicate verifier/model signals separately from pre-audit unique sites;
- classify each unique site as genuine prefix heading+body, title+subtitle,
   heading-only taxonomy, operation-contract miss, or sequencing/safety
   diagnostic;
- choose the next runtime slice only from genuine prefix heading+body sites;
- keep validation observer-only and do not add document-specific heading
   literals, regex repair, or Markdown/DOCX rewriting in validation.

#### PR-H-final Attempt Note

PR-H-final added a runtime-only exact-field recovery for
`normalize_heading_boundary` proposals whose `expected_after_preview` contains
an exact heading plus a teaser body prefix. Code may recover the full
`body_substring` only from the current block text, after verifying the exact
heading, optional safe page-furniture prefix, and exact body-prefix match.
Strict substring safety remains in place: non-exact body text, translated words,
and title/subtitle rows still fail closed.

Focused unit coverage passed, but the real comparison-only evidence does not
close the MVP exit threshold. Run
`20260529T180231Z_1206_Rethinking-money-chapter-region-pages-10-11-and-156-217`
passed the must-hold safety gates (`failed_chunk_count=0`,
`false_deletions=0`, `readability_regressions=0`, `page_furniture_inline=0`),
removed the duplicate-fragment blocker, and reduced unique pre-audit heading
sites to 7. That is still above the desired `<=2` genuine heading+body blocker
threshold. A follow-up experimental adjacent-heading tweak was not retained:
its proof run did not use the new path and reported
`readability_regressions=1` plus `page_furniture_inline=1`, so it is not a
valid PR-H-final proof.

Next step should not be broader prompt hardening. Use the current exact-field
recovery as the safe base, then decide between a narrow runtime operation
contract for adjacent split-heading blocks or a separate caption/fragment
repair slice, with a fresh proof run. Do not weaken delete safety or move repair
into validation.

#### PR-H-exit Adjacent/Split Heading Operation Contract

PR-H-exit is the last runtime micro-slice before the MVP ship/no-ship decision.
It targets only remaining genuine heading+body sites from run
`20260529T180231Z_1206_Rethinking-money-chapter-region-pages-10-11-and-156-217`.
The retained runtime contract is intentionally narrow:

- `normalize_heading_boundary` may apply across the adjacent next block only
   when the current block is the exact prefix of `heading_substring`;
- `body_substring` must be an exact substring of the adjacent block;
- split headings are allowed only when the adjacent block begins with the exact
   remaining heading tail before the exact body text;
- prose-before-heading, non-exact substrings, title/subtitle rows, and ambiguous
   body starts still fail closed;
- validation remains observer-only and no document-specific heading literals or
   regex repair are introduced.

Stop rule for the proof run: if must-hold safety remains green and unique
genuine heading blockers are `<=2`, MVP exit is locally reached. If more than
two remain but they are all classified as exact-substring/safety limitations,
the readable-draft MVP may still be accepted by product decision. If more than
two unclassified runtime-fixable headings remain, heading cleanup needs a
separate operation-contract design decision rather than another prompt tweak.

Outcome note from comparison-only run
`20260530T071434Z_968_Rethinking-money-chapter-region-pages-10-11-and-156-217`:
the pipeline succeeded and safety stayed green (`failed_chunk_count=0`,
`accepted_delete_block_count=0`, false deletions/readability regressions empty,
`page_furniture_inline=0`, standalone numeric guard still active), but the
reader verifier failed with `execution_failed`, so this is not a valid MVP exit
proof. Deterministic pre-audit still reported `heading_fused_with_body=5` and
`fragmented_paragraph=6`. The new adjacent/split heading runtime path was not
used in accepted operations (`heading_boundary_normalized_across_adjacent_block`
count `0`), leaving the remaining heading issue as an operation-selection /
contract design decision rather than a prompt wording slice.

## Latest Evidence To Preserve

### May 26 Cleanup Replay Evidence

Use these numbers as the comparison baseline for the next iteration:

- best full comparison-only baseline remains `20260525T140558Z_1207` with
   `reader_verifier_remaining_issue_count=16` and no false deletion/readability
   regression reports;
- later full repeats after PR-H safety work were worse but safe:
   `20260525T154237Z_1231` had 25 remaining issues and
   `20260525T154728Z_1745` had 22 remaining issues, both with false deletion and
   readability regression statuses `none_reported`;
- frozen cleanup replay on `20260525_185154...raw.result.md` showed current
   prompt values `29/32/32`, mean `31.0`, and repeated the same broad unsafe
   `remove_inline_noise` proposal in all 3 repeats;
- `decomposition_first` replay values were `26/33/26`, mean `28.333`, with
   broad unsafe `remove_inline_noise` count `0/0/0`; it is promising but not
   stable enough for production;
- `anchor_focused` replay values were `26/32/32`, mean `30.0`, with heading
   issues `10/10/11`, but mixed-language leaks and broad unsafe proposals still
   appeared;
- current replay controls on different frozen translated inputs were
   `164842 -> 34` and `184704 -> 28`, which indicates that translated raw input
   shape is a major driver of output quality.

Interpretation: do not ship a prompt-only production switch yet, and do not add
more runtime safety relaxations. The next evidence-producing slice should test
whether removing obvious source-side page furniture before translation makes the
translated raw Markdown more consistent and easier for the existing reader
cleanup pass to polish.

### Next Iteration: Audited Source Cleanup Before Translation

Goal: reduce translated layout noise before it becomes unstable Russian text,
without broad source rewriting and without weakening post-translation cleanup
safety.

Required experiment shape:

1. Add or use a diagnostic path that runs the selected chapter-region profile
    with an audited source-cleanup step before translation.
2. Source cleanup may remove only high-confidence non-semantic artifacts:
    standalone page numbers, blank-page markers, extraction placeholders, and
    repeated running headers/footers when reliable source page-boundary or
    repetition evidence exists.
3. Source cleanup must write a report with removed items and kept-uncertain
    items. Examples like `2. 19` must be kept unless the source evidence makes
    them clearly non-semantic.
4. Run the normal translation path and the existing post-translation AI reader
    cleanup after that source cleanup.
5. Compare the new artifacts with the preserved baselines above. Do not judge by
    one metric only; inspect raw translated Markdown, cleaned Markdown, cleanup
    reports, and verifier summaries.

Success criteria for this iteration:

- no false deletions and no readability regressions;
- no failed reader-cleanup chunks in the run used as source-cleanup proof;
- source cleanup report is reviewable and contains no unique heading/prose
   deletion;
- translated raw Markdown has fewer page headers/page numbers embedded in prose
   than the `154237` and `154728` runs;
- final cleaned output is at least competitive with the best comparable
   verifier-backed baseline: top blocker categories should not grow for the same
   document/profile unless the run is explicitly non-comparable, and any growth
   must be explained before promoting the approach;
- `mixed_language_leak=0` or clearly reduced versus the fresh repeats;
- `page_furniture_inline` and `heading_fused_with_body` do not regress versus a
   comparable completed run without a diagnostic explanation;
- post-translation cleanup still rejects broad heading-eating
   `remove_inline_noise` proposals.

Stop and do not promote the approach if source cleanup deletes unique semantic
text, requires document-specific phrase lists, hides cleanup inside validation,
or only improves numbers by making verifier evidence less complete.

MVP exit criterion for this backlog: stop reader-cleanup polish once repeatable
comparison-only evidence on the selected proof document, and at least one
additional representative real document when available, shows `cleaned_better`
or better, no failed cleanup chunks, no false deletions, no readability
regressions, and no document-specific cleanup logic or acceptance-threshold
tuning. Remaining reader-visible issues may be carried forward as known draft
limitations instead of being polished to zero.

Latest comparison-only run:

- `run_id`: `20260524T085558Z_976_Rethinking-money-chapter-region-pages-10-11-and-156-217`
- `validation_run_type`: `comparison_only`
- `acceptance_contract_active`: `False`
- pipeline result: succeeded; the previous post-processing/finalization hang did
   not reproduce
- cleanup stage: completed
- cleanup changed output: true
- cleanup chunks: 4
- failed cleanup chunks: 0
- proposed cleanup operations: 67
- accepted cleanup operations: 36
- ignored cleanup operations: 31
- accepted delete blocks: 3
- deleted non-whitespace chars: 71 (`deleted_char_ratio=0.000713`)
- verifier verdict: `cleaned_better`
- cleaned audit verdict: `improved_but_has_remaining_issues`
- raw score: 3.0
- cleaned score: 5.0
- remaining reader-visible issues: 26
- high severity issues: 22
- output DOCX openable: true
- formatting diagnostics: failed diagnostic threshold; `mapped_count=282`,
   `unmapped_source_count=30`, `unmapped_target_count=31`

Main remaining issue categories:

- `heading_fused_with_body`: 14
- `page_furniture_inline`: 7
- `fragmented_paragraph`: 5

Current primary product blockers:

- page numbers / running headers glued into normal prose;
- paragraphs still fused to headings or subheadings;
- remaining fragmented paragraphs around page/caption/list boundaries;
- formatting preservation is not solved yet: bold, italic, emphasis/highlight,
   heading/subheading styles, and list styles need a later formatting PR;
- images are not solved here and need a dedicated image handoff/reinsertion PR.

## Current PR-H Sub-Slices

### PR-H0a: Inline Marker + Duplicate Heading Runtime Proof

Status: completed locally on 2026-05-30. This is not a clean-checkout CI proof
because the worktree is dirty with PR-H0/PR-H0a changes.

Proof artifact:
`.run/reader_cleanup_replay_experiments/20260530T133307Z_anthropic-small-overlap-pr-h0a-inline-marker-duplicate-boundary-proof/`

Completed:

- `remove_inline_noise` can recover a missing `noise_substring` from a full
   exact `expected_after_preview`, but only for safe inline numeric/endnote
   markers and adjacent duplicate phrases.
- Inline marker removal preserves word-boundary spacing; `... годах 5 эта ...`
   becomes `... годах эта ...`, not `... годахэта ...`.
- `duplicate_fragment` is accepted for `remove_inline_noise` only for exact
   adjacent repeated semantic phrases of 2-8 words.
- Validation/verifier remains observer-only; no repair behavior moved into
   verifier code.

Proof result:

- selector: `anthropic:claude-sonnet-4-6`;
- shape: `chunk_size=8000`, `3/3` overlap, `global_plan_enabled=false`;
- cleanup chunks: `15`, failed chunks: `0`;
- accepted operations: `49`, including `22` `remove_inline_noise`;
- verifier: `cleaned_better`, high confidence, raw `4.0` -> cleaned `6.0`;
- remaining issues: `17`;
- `noise_substring_not_found=0`, broad unsafe remove_inline_noise proposals `0`.

Closed:

- inline endnote/page markers in the proof run.

Implemented but not selected by the real replay:

- duplicate semantic heading text such as `национальные валюты Национальные
   валюты`; unit tests cover the runtime contract, but the model did not propose
   the operation for the real proof site.

Superseded by PR-H0b/PR-H0c targeting slices:

- no verifier-side repair;
- keep `failed_chunk_count=0`, no false deletions, and no broad unsafe
   `remove_inline_noise` proposals.

### PR-H0b: Operation Selection Targets Runtime Proof

Status: completed locally on 2026-05-30. This is not a clean-checkout CI proof
because the worktree is dirty with PR-H0/PR-H0a/PR-H0b changes.

Proof artifact:
`.run/reader_cleanup_replay_experiments/20260530T155633Z_anthropic-small-overlap-pr-h0b-targeting-proof/`

Completed:

- Added advisory `operation_selection_targets` to the cleanup request payload.
- Duplicate semantic heading candidates provide `operation_hint=remove_inline_noise`,
   `reason_hint=duplicate_fragment`, exact `noise_substring`, and full
   `expected_after_preview`.
- Side-heading island candidates are surfaced as classification targets without
   making `remove_inline_noise` the default.

Proof result:

- selector: `anthropic:claude-sonnet-4-6`;
- shape: `chunk_size=8000`, `3/3` overlap, `global_plan_enabled=false`;
- cleanup chunks: `15`, failed chunks: `0`;
- accepted operations: `52`, including `23` `remove_inline_noise`;
- verifier: `cleaned_better`, high confidence, raw `4.0` -> cleaned `6.0`;
- remaining issues: `19`;
- `noise_substring_not_found=0`, broad unsafe remove_inline_noise proposals `0`.

Closed:

- duplicate semantic heading operation selection for the proof site:
   `национальные валюты Национальные валюты` no longer remains, and the accepted
   operation uses `remove_inline_noise` with reason `duplicate_fragment`.

Still open:

- side-heading islands were still proposed as unsafe `remove_inline_noise` and
   rejected by runtime as `remove_inline_noise_not_exact_noise_pattern`.

### PR-H0c: Side-Heading Operation Choice Salience

Status: completed locally on 2026-05-30. This is not a clean-checkout CI proof
because the worktree is dirty with PR-H0/PR-H0a/PR-H0b/PR-H0c changes.

Proof artifact:
`.run/reader_cleanup_replay_experiments/20260530T165518Z_anthropic-small-overlap-pr-h0c-side-heading-salience-proof/`

Completed:

- Side-heading `operation_selection_targets` now declare preferred operation
   order: first `split_block`, second `normalize_heading_boundary`; the
   forbidden/default-rejected operation is `remove_inline_noise`.
- The chunk prompt explicitly says semantic heading islands are not noise, must
   not be deleted, and should be handled only with exact `split_block` or
   `normalize_heading_boundary`; if exact preservation is impossible, skip.
- Runtime still rejects semantic side-heading deletion as
   `remove_inline_noise_not_exact_noise_pattern`.

Proof result:

- selector: `anthropic:claude-sonnet-4-6`;
- shape: `chunk_size=8000`, `3/3` overlap, `global_plan_enabled=false`;
- cleanup chunks: `15`, failed chunks: `0`;
- accepted operations: `55`, including `11` `split_block`, `13`
   `normalize_heading_boundary`, and `24` `remove_inline_noise`;
- verifier: `cleaned_better`, high confidence, raw `4.0` -> cleaned `6.0`;
- remaining issues: `20`;
- `noise_substring_not_found=0`, broad unsafe remove_inline_noise proposals `0`;
- `remove_inline_noise_not_exact_noise_pattern` decreased from `8` in PR-H0b to
   `3` in PR-H0c.

Closed:

- side-heading operation choice salience for the proof examples: `Три
   мультинациональные валюты`, `Авиационные бонусные программы`, and `Частные
   международные расчетные единицы` moved to accepted `split_block` operations
   that preserve semantic text instead of rejected `remove_inline_noise`.

Still open:

- the accepted side-heading splits can leave sentence stubs and continuation
   fragments around the isolated heading. This is now a separate
   stub/continuation contract problem, not a deletion-safety problem.
- `Потребность в глобальной валюте, Глобальная эталонная валюта...` still needs
   a bounded decision: runtime correctly rejected a partial
   `normalize_heading_boundary` as `heading_boundary_unaccounted_text`.

Next active PR-H slice:

- define a bounded side-heading stub/continuation contract: when a semantic
   side-heading island interrupts a sentence, preserve the heading while joining
   or retaining the pre-heading stub and post-heading continuation without
   creating orphan fragments;
- keep duplicate-heading PR-H0b behavior intact;
- leading-dash continuation artifacts remain a separate classification decision.

### PR-H1: Targeted Page-Furniture + Caption + Continuation Repair

Historical slice. Do not treat this as the active PR-H slice after PR-H0a; use
the PR-H0a next-slice notes above unless a fresh proof reopens this exact
page-furniture/caption continuation class.

Last updated: 2026-05-29 from comparison-only run
`20260528T151827Z_1227_Rethinking-money-chapter-region-pages-10-11-and-156-217`.

#### Goal

Close the current single `page_furniture_inline` anchor without widening PR-H to
the whole document. The active defect is the fused sequence around
`166 ПРОЦВЕТАНИЕ ... Фото: A Human Right. развивающейся стране`, where a page
number, running header, and image caption sit between two parts of one sentence.

#### Ownership Boundary

- `remove_inline_noise` remains a bounded AI cleanup operation in
   `reader_cleanup_mvp`.
- `join_fragmented_paragraph` may be used only as a follow-up after exact
   page-furniture/caption removal exposes a continuation that should be joined
   to the previous adjacent block.
- Sequenced repair is code-owned orchestration in
   `src/docxaicorrector/reader_cleanup_mvp/service.py`: the model may propose
   both operations, but code guarantees ordering, adjacency, IDs/hashes,
   exact substrings, and whether the follow-up join is allowed.
- Validation remains observer-only. It may report the anchor, status, and
   evidence, but it must not execute cleanup, mutate Markdown/DOCX, or rebuild
   artifacts.

#### Required Work

1. Add or finish a targeted diagnostic path for the one page-furniture anchor,
   using verifier-recommended current anchors rather than stale applied anchors.
2. For the anchored block, compute a preflight preview before applying the
   operation:
   - `before`: current exact block text;
   - `noise`: proposed exact page-number/running-header/caption span;
   - `after`: remaining text after the noise span is removed.
3. Accept `remove_inline_noise` only when the proposed noise span is exact,
   bounded, non-semantic page furniture/caption residue and does not consume the
   semantic continuation.
4. Permit a follow-up `join_fragmented_paragraph` only when all are true:
   - the same anchor block had an accepted exact `remove_inline_noise` operation;
   - the join is from the previous adjacent payload block to the cleaned anchor
      block;
   - the operation uses current request `id`/`text_hash` values, not stale
      artifact IDs;
   - the previous block ends with a continuation signal, such as non-final
      punctuation, an opening quote, ellipsis, or a grammar-dependent trailing
      token, and the cleaned anchor remainder starts like sentence continuation;
   - the join preserves every semantic character from both sides.
5. Keep `delete_block` disallowed for this case. `duplicate_fragment` safety is
   unchanged and must not be loosened.
6. Do not introduce document-specific regexes or literals such as
   `Фото: A Human Right` or `ПРОЦВЕТАНИЕ` into production code.

#### Acceptance Criteria

- The specific `166 ПРОЦВЕТАНИЕ ... Фото ... развивающейся стране` anchor no
   longer appears as `page_furniture_inline` in the verifier output.
- `reader_mvp_status_readability_regression_status=none_reported`.
- `reader_cleanup_failed_chunk_count=0` and anchor-repair failed chunks remain
   `0`.
- No `delete_block` operation is accepted for this case; `remove_inline_noise`
   is the page-furniture/caption cleanup operation.
- Manual review confirms the Time quote reads as one sentence after cleanup:
   `... что вы находитесь в развивающейся стране, — это мусор под ногами ...`.
- `fragmented_paragraph` and `heading_fused_with_body` do not grow versus the
   comparable completed baseline unless the run records a clear diagnostic
   explanation.
- No false deletions are reported, and no acceptance threshold or verifier
   taxonomy is changed to make the run look better.

#### Stop Conditions

Stop and update this backlog before coding wider PR-H changes if any of these
become true:

- the repair needs a new cleanup operation type;
- the repair requires document-specific caption/header regexes;
- the model can only close the case by deleting semantic continuation text;
- validation has to execute or apply cleanup to make the proof pass;
- the page-only proof reports false deletions or readability regressions.

## Historical PR Order (PR-A Through PR-G)

PR-A through PR-G are historical context for how the backlog reached the current
state. Do not start a new implementation from these completed/superseded slices.
The next active implementation slice is PR-H from the Current Visual MVP Roadmap.

### PR-A: Cleanup Schema Repair Retry

#### Goal

Make cleanup chunks recover from simple AI schema mistakes instead of becoming
no-op for a large part of the document.

#### Why First

The latest run cleaned only one of four chunks. Until invalid AI cleanup JSON can
be repaired, prompt and operation improvements will affect only part of the
document.

#### Required Work

1. Harden the cleanup system prompt so every operation must include all required
   fields:
   - `operation`
   - `id`
   - `text_hash`
   - `reason`
   - `confidence`
   - `evidence_before`
   - `expected_after_preview`
   - `safety_note`
2. Add a single schema-repair retry for cleanup chunk responses that are valid
   JSON but fail operation schema validation.
3. The repair prompt must ask the model to return only corrected JSON
   `cleanup_operations` and `warnings`.
4. The repair prompt must not allow rewritten Markdown or new operation types.
5. Advisory mode behavior:
   - original invalid response -> one repair retry;
   - valid repaired response -> continue normal validation/application;
   - invalid repaired response -> keep chunk unchanged and report warning.
6. Strict mode behavior:
   - preserve the existing fail-closed semantics; if repair still fails, fail
     cleanup while preserving base artifacts according to existing policy.
7. Add report fields or warnings that distinguish:
   - original schema failure;
   - repair attempted;
   - repair succeeded;
   - repair failed.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- invalid operation missing `evidence_before` triggers exactly one repair retry;
- repaired valid operation is accepted and applied;
- repaired invalid operation leaves chunk unchanged in advisory mode;
- repair prompt forbids full rewritten Markdown;
- report includes repair attempt/success/failure evidence;
- existing ambiguous inline-noise safety tests still pass.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

After focused tests, rerun the same comparison-only profile only if the unit
slice passes:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected improvement: fewer failed cleanup chunks. Do not require acceptance to
pass.

### PR-B: Heading Boundary Operation Reliability

#### Goal

Improve AI cleanup's ability to split fused headings from body text without
adding deterministic heading rewrites.

#### Why Second

The largest remaining category is `heading_fused_with_body`. The latest report
also shows ignored `normalize_heading_boundary` operations because the model did
not provide exact enough parts.

#### Required Work

1. Add document-agnostic examples to the cleanup prompt for fused heading/body
   cases:
   - uppercase heading followed by prose;
   - chapter heading followed by epigraph;
   - section heading followed by first sentence;
   - part title followed by introductory paragraph.
2. Require the model to provide exact `heading_substring` and exact
   `body_substring` from the original block.
3. Tell the model that `body_substring` must cover the full semantic body portion
   it expects to remain after the heading, not just the first few words.
4. If prompt-only still produces `heading_boundary_unaccounted_text`, consider a
   bounded operation-contract refinement:
   - allow `normalize_heading_boundary` with a unique exact heading prefix;
   - code preserves the entire remaining text as body;
   - no words may be changed, dropped, or reordered.
5. This refinement is allowed only if it is implemented as exact-match
   application of an AI-selected boundary, not as deterministic heading
   detection.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- fused uppercase heading/body is normalized when exact substrings are provided;
- operation is rejected when heading substring is ambiguous;
- operation is rejected when body text would be lost;
- optional prefix mode preserves the full remainder exactly;
- no operation creates new heading text that was not already present.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

Expected improvement: fewer `heading_fused_with_body` issues after rerun.

### PR-C: Inline Page Furniture Application Hardening

#### Goal

Improve safe application of AI-proposed `remove_inline_noise` operations for
page furniture glued inside or at the start of paragraphs.

#### Why Third

The model already identified page furniture patterns, and some operations were
accepted. Remaining problems are mostly exactness/safety/application issues.

Before implementing PR-C, do one diagnostic pass on the latest completed run:
list the current `page_furniture_inline` anchors and determine whether the
increase came from a failed cleanup chunk or from completed cleanup producing new
inline furniture. If the growth is explained by a failed chunk, fix chunk
stability first and rerun before changing page-furniture application logic.

#### Required Work

1. Keep document-specific running headers inside the AI global cleanup plan and
   cleanup report only.
2. Do not promote run-specific phrases into shared deterministic code.
3. Accept `remove_inline_noise` only when:
   - the block ID and hash match;
   - the noise substring is exact and unique in that block;
   - the remaining block keeps semantic text;
   - deletion does not produce malformed spacing or empty semantic content;
   - the operation reason and evidence are consistent with page furniture,
     page-number island, blank-page marker, or running header residue.
4. Improve the model prompt to provide the full exact noise substring including
   surrounding spaces when needed.
5. Improve ignored-operation reporting so a developer can distinguish:
   - non-exact substring;
   - ambiguous repeated substring;
   - semantic deletion risk;
   - reason/kind mismatch.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- prefix page furniture removal preserves prose;
- middle-of-paragraph page furniture removal preserves prose;
- ambiguous repeated substring is rejected;
- semantic phrase that merely resembles a header is rejected;
- report records ignored reason precisely.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

Expected improvement: fewer `page_furniture_inline` issues after rerun.

Promotion rule: do not move from the diagnostic/stability step into PR-C code
changes until the run used for comparison has
`reader_cleanup_failed_chunk_count = 0`. A failed chunk can make aggregate
`cleaned_better` true while hiding local cleanup gaps, so it is not acceptable
proof for page-furniture regressions.

### PR-D: Verifier-Guided Anchor Repair Pass

#### Goal

Use verifier/pre-audit findings to drive a second bounded AI cleanup pass over
only the remaining problem anchors.

#### Why Fourth

After basic cleanup is reliable, a second pass should focus on the exact places
still reported as reader-visible defects instead of reprocessing the whole book.

#### Required Work

1. After the first cleanup pass and verifier/pre-audit, collect top remaining
   anchors by category:
   - `heading_fused_with_body`
   - `page_furniture_inline`
   - `fragmented_paragraph`
2. Build small anchor windows around affected blocks.
3. Ask the cleanup model for the same bounded operations only.
4. Preserve all existing ID/hash/exact-match safety checks.
5. Keep the pass optional and advisory for MVP.
6. Report first-pass vs anchor-repair-pass operation counts separately.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` only if
  verifier artifacts need additional machine-readable anchor grouping
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`

#### Tests Required

- anchor pass receives only selected windows, not the full document;
- anchor pass cannot edit blocks outside its editable ID set;
- invalid anchor-pass response is no-op in advisory mode;
- report separates first-pass and anchor-pass stats;
- verifier/pre-audit anchors with equal category counts are preserved by
  identity, not category count alone.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

Expected improvement: lower remaining issue count with no false deletions.

### PR-E: User-Facing MVP Status Report

#### Goal

Make the comparison-only result understandable to a non-developer user.

#### Why Fifth

The current artifacts contain useful data, but the user-facing interpretation is
too easy to misread as either a failure or a final acceptance result.

#### Required Work

1. Add or improve summary fields that clearly separate:
   - pipeline success;
   - cleanup improvement;
   - acceptance diagnostic status;
   - remaining reader-visible risk.
2. Include positive safety signals:
   - no verifier-reported false deletions;
   - no verifier-reported readability regressions.
3. Include blocker grouping:
   - schema/operation contract failures;
   - remaining reader-visible cleanup defects;
   - mapping/quality-gate diagnostics.
4. Prefer concise Russian user summaries for this workflow when the source run
   profile is used by Russian-speaking operators.

#### Suggested Files

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `tests/test_real_document_pipeline_validation.py`

#### Tests Required

- comparison-only summary states that acceptance failure is diagnostic;
- summary includes cleanup score delta;
- summary includes remaining issue counts and top categories;
- summary includes false-deletion/regression status;
- summary distinguishes cleanup defects from unmapped source/target diagnostics.

#### Validation

```bash
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

Expected improvement: users can understand whether the artifact is a readable
draft, acceptance-ready output, or a failed pipeline.

## Post-PR-E Real-Run Evidence

PR-A through PR-E have now been implemented and validated on the same
comparison-only chapter-region profile. The latest real-document evidence is:

- `run_id`: `20260523T134507Z_967_Rethinking-money-chapter-region-pages-10-11-and-156-217`
- `validation_run_type`: `comparison_only`
- pipeline result: `succeeded`
- acceptance result: `failed`, diagnostic-only for this profile
- verifier verdict: `cleaned_better`
- cleaned audit verdict: `improved_but_has_remaining_issues`
- raw score: 3.0
- cleaned score: 5.0
- remaining reader-visible issues: 10
- high severity issues: 6
- MVP status artifact:
   `tests/artifacts/real_document_pipeline/runs/20260523T134507Z_967_Rethinking-money-chapter-region-pages-10-11-and-156-217/lietaer_pdf_chapter_region_reader_mvp_status.md`
- cleaned Markdown artifact:
   `.run/ui_results/20260523_164936_Rethinking-money-chapter-region-pages-10-11-and-156-217.result.md`
- cleanup report:
   `.run/ui_results/20260523_164936_Rethinking-money-chapter-region-pages-10-11-and-156-217.reader_cleanup_report.json`

The current reader-facing quality is readable draft, not final quality. The
document is materially easier to read than the raw output, and the verifier did
not report false deletions or readability regressions. Remaining defects are
visible but localized.

Current blocker groups from the PR-E status report:

- cleanup contract: `cleanup_chunk_failures=2`
- reader-visible cleanup defects:
   - `heading_fused_with_body=5`
   - `page_furniture_inline=3`
   - `fragmented_paragraph=2`
- mapping/quality-gate diagnostics:
   - `translation_quality_status=warn`
   - `translation_quality_gate_reasons=unmapped_source_paragraphs_above_advisory_threshold`
   - `acceptance_diagnostic_checks=formatting_diagnostics_threshold,unmapped_source_threshold,unmapped_target_threshold`

Reader-visible examples from the latest cleaned Markdown:

- fused TOC heading:
   `СОДЕРЖАНИЕ Предисловие ix Введение: от дефицита к процветанию за одно поколение 1`
- fragmented paragraph after an image caption:
   `деньги по-другому и при этом быть уверенными, что их дети ходят в школу», — вспоминает Лернер. Множество инициатив...`
- inline page furniture before a heading:
   `11 ФУРЕАЙ КИППУ`
- fused heading/body:
   `ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ. Авиационный бизнес...`
- page number plus running header fused into body:
   `200 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ Наконец-то признана необходимость...`

## Historical PR-F Repair Slice (Completed/Superseded)

This section is retained as implementation history. It is not the current next
slice. The current next slice is PR-H: Reader Cleanup Visual Blockers.

### PR-F: Anchor Repair Reliability and Remaining Reader Defects

#### Goal

Reduce the remaining reader-visible defects without violating the AI-first
cleanup contract. The first target is to eliminate anchor-repair schema/chunk
failures; the second target is to improve the same anchor pass on the three
remaining defect families: fused headings, inline page furniture, and fragmented
paragraphs.

#### Why This Can Be One Iteration

These improvements touch the same bounded cleanup surface:

- anchor-repair prompt and schema-repair prompt;
- cleanup operation contract guidance;
- verifier/pre-audit anchor payload shaping;
- tests around `run_reader_cleanup_anchor_repair` and comparison-only verifier
   integration.

Combining them is optimal if the implementation remains limited to prompt,
schema-repair, anchor payload, exact-match validation, and tests. It is not
optimal if it requires a new cleanup operation type, document-specific detection,
or live app runtime wiring. In that case, split the work and update this backlog
before coding further.

#### Required Work

1. Fix anchor-repair schema reliability:
    - harden the anchor-repair request instructions so every proposed operation
       includes all required audit fields;
    - harden schema-repair instructions so the model only adds or corrects
       missing operation fields and does not rewrite Markdown;
    - preserve advisory behavior: failed anchor chunks are reported and leave
       selected text unchanged;
    - preserve strict validation and exact-match application.
2. Improve fused heading repair guidance:
    - add document-agnostic examples for uppercase heading + body prose;
    - include examples with leading page number/running header plus heading/body;
    - prefer composed AI operations where needed, for example
       `remove_inline_noise` followed by `normalize_heading_boundary` on the same
       block when both are justified by exact evidence;
    - do not add deterministic heading detection or heading literals.
3. Improve inline page-furniture guidance:
    - clarify that a leading page/footnote number before a heading can be a
       candidate only when the model provides exact evidence and safe preview;
    - keep code-owned safety strict: exact unique substring, semantic remainder,
       ID/hash match, and no broad numeric-prefix rule.
4. Improve fragmented paragraph guidance:
    - pass enough neighboring context in anchor windows for the model to decide
       whether a fragment is a page/caption split;
    - use existing bounded operations such as `join_fragmented_paragraph` when
       the required exact evidence is present;
    - do not add a duplicate-removal operation in this PR unless the existing
       operation contract already supports it safely. If a new operation type is
       required, write a separate contract update first.
5. Improve developer-facing diagnostics:
    - make anchor chunk failure warnings easy to distinguish from first-pass
       cleanup failures;
    - include accepted/ignored operation counts for the anchor pass;
    - keep the PR-E user status report unchanged except for naturally improved
       numbers from the same fields.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`

Do not change `src/docxaicorrector/pipeline/late_phases.py` for this PR unless
the task is explicitly expanded to live app runtime wiring. The next repair
target is the comparison-only validation path.

#### Tests Required

- anchor response missing `evidence_before` is repaired and applied when the
   corrected operation is valid;
- anchor response missing `expected_after_preview` is repaired and applied when
   safe;
- unrepaired invalid anchor response leaves the selected text unchanged in
   advisory mode and reports the failure;
- composed page-furniture plus heading-boundary repair on one block preserves
   all semantic body text exactly;
- numeric prefix that is semantic content is rejected, not deleted;
- fragmented paragraph anchor receives enough neighbor context and applies only
   through an existing safe operation;
- comparison-only verifier loop still reruns after anchor repair and refreshes
   reader MVP status fields.

#### Validation

Run focused tests first:

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

If the focused tests pass, rerun the same real-document comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected improvement:

- `cleanup_chunk_failures` decreases, ideally to 0;
- remaining reader-visible issue count decreases below 10;
- high severity count decreases below 6;
- no false deletions or readability regressions appear;
- status remains readable draft unless the verifier reports the cleaned artifact
   is actually clean;
- comparison-only acceptance may still be diagnostic failed because mapping and
   quality-gate diagnostics are separate from reader cleanup.

#### Stop Conditions

Stop and update this backlog instead of widening the PR if any of these become
true:

- fixing the fragmented paragraph requires a new cleanup operation type;
- the proposed fix needs Lietaer-specific literals or regexes;
- the proposed fix changes acceptance thresholds or structure-recognition
   behavior;
- the proposed fix changes live app runtime behavior in `late_phases.py`;
- real-document evidence reports possible false deletions or readability
   regressions.

## Architecture Review Findings Before Remaining Visual Work

The post-PR-F architecture review found that the comparison-only validator has
drifted beyond validation responsibility. It currently runs verifier review, then
uses verifier issues to execute `run_reader_cleanup_anchor_repair`, overwrites
the cleaned Markdown artifact, and rebuilds the cleaned DOCX through a simplified
Markdown-to-DOCX path. That makes validation a second repair pipeline instead of
an observer.

This must be fixed before PR-H/PR-I/PR-J, because remaining visual proof depends
on knowing whether the final DOCX came from the real runtime pipeline or from a
validation-only rewrite path.

Current concrete findings:

- validation-owned mutation: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
   applies anchor repair and rewrites cleaned Markdown/DOCX instead of only
   reporting verifier anchors;
- DOCX parity risk: validation rebuilds post-anchor DOCX with
   `convert_markdown_to_docx_bytes(...)`, while live runtime cleanup uses the
   full rebuild path with source paragraph property preservation and image
   reinsertion hooks;
- composed-operation mismatch: cleanup prompts allow page-furniture removal plus
   heading/body normalization on the same block, but the parser currently ignores
   a second non-join operation for the same block;
- audit-contract drift: legacy `delete_blocks` responses can still bypass the
   full `cleanup_operations` audit fields required by the MVP contract;
- numeric-prefix safety gap: the inline-noise safety layer still accepts a broad
   number-plus-uppercase substring class, which is too close to the forbidden
   "delete any number before an uppercase phrase" shortcut;
- verifier taxonomy drift: `recommended_next_changes.change_type` accepts
   `cleanup_core` / `ai_operation_contract`, while the spec names
   `model_selection`, `operation_contract`, `safety_application`, and
   `deterministic_last_resort` as the stable categories;
- latest evidence caveat: the latest comparison-only evidence still says
   `cleaned_better`, but reports readability regressions, so it must not be used
   as success proof for PR-H until the boundary and contract issues are fixed.

### PR-G: Validator Boundary Refactor And Cleanup Contract Preflight

#### Goal

Restore the architecture boundary: validation evaluates and reports only; all
reader cleanup and anchor repair execution must happen in the main runtime
pipeline or not happen at all. While touching that boundary, fix the small
cleanup-contract mismatches that would otherwise make PR-H visual repair evidence
ambiguous.

#### Why Before PR-H / PR-I / PR-J

PR-H needs visual evidence from the actual pipeline output. PR-I and PR-J are
about formatting and image preservation. If validation can still rewrite cleaned
Markdown and rebuild DOCX by a simplified path, visual regressions can be caused
by the validator rather than by the production pipeline. That would make the next
formatting/image work chase the wrong layer.

#### Required Work

1. Remove validation-owned repair execution:
   - delete or disable the call from `_write_reader_verifier_artifacts(...)` to
      `_run_reader_cleanup_anchor_repair_validation_pass(...)`;
   - validation may still build and persist anchor targets as diagnostic evidence;
   - validation must not call cleanup models to mutate output artifacts;
   - validation must not overwrite cleaned Markdown, cleaned DOCX, or cleanup
      reports except to add validation/report metadata in run-scoped reports.
2. Decide the runtime home for anchor repair:
   - either move anchor repair orchestration into the main pipeline where the full
      DOCX rebuild path is available;
   - or leave anchor repair disabled as a future runtime feature and expose
      verifier anchors as backlog evidence only;
   - do not keep a validation-only repair path as an MVP shortcut.
3. Preserve verifier value without mutation:
   - write verifier evidence, review JSON/Markdown, and reader MVP status as
      before;
   - include `recommended_anchor_targets` or equivalent diagnostic fields in
      verifier/summary artifacts;
   - if anchor repair is not runtime-enabled yet, clearly report
      `anchor_repair_status=diagnostic_only_not_applied`.
4. Align cleanup operation parsing with the AI-first contract:
   - allow compatible composed operations on the same block when exact evidence
      supports them, especially `remove_inline_noise` followed by
      `normalize_heading_boundary`;
   - reject incompatible duplicate edits explicitly instead of silently ignoring
      them;
   - keep operation order deterministic and report accepted/ignored composed
      operations clearly.
5. Tighten audit and safety contracts before visual repair:
   - require full audit fields for new cleanup operations;
   - either deprecate legacy `delete_blocks` or convert it into fully audited
      `cleanup_operations` before application;
   - narrow the number-plus-uppercase inline-noise acceptance path so semantic
      numeric headings or numbered prose are rejected unless AI evidence is exact
      and the operation fits a document-agnostic safety rule.
6. Align verifier recommendation taxonomy with the spec:
   - support `prompt`, `model_selection`, `operation_contract`,
      `safety_application`, and `deterministic_last_resort`;
   - keep legacy values only as normalized compatibility input, not as the
      preferred output contract.

#### Suggested Files

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `src/docxaicorrector/pipeline/late_phases.py` only if anchor repair execution
   is moved into runtime in this PR
- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`
- `docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md` only if
   the runtime-anchor decision needs a follow-up slice

#### Tests Required

- verifier run no longer mutates cleaned Markdown or cleaned DOCX artifacts;
- verifier artifacts still contain remaining issues, evidence anchors, and
   recommended anchor targets;
- comparison-only status distinguishes diagnostic anchor targets from applied
   cleanup;
- if runtime anchor repair is implemented, it uses the same DOCX rebuild path as
   normal reader cleanup and validation only observes its artifacts;
- composed same-block page-furniture removal plus heading-boundary normalization
   is accepted when exact and safe;
- incompatible duplicate operations on one block are rejected with an explicit
   ignored reason;
- legacy `delete_blocks` cannot bypass the required audit contract for new
   cleanup behavior;
- semantic numeric uppercase text is preserved when AI proposes it as inline
   noise;
- verifier recommendation change types match the spec taxonomy.

#### Validation

Run focused tests first:

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

If the focused tests pass, rerun the same comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected result:

- comparison-only run still completes and writes raw/cleaned/verifier/status
   artifacts;
- validation no longer applies anchor repair or rewrites primary output
   artifacts;
- verifier anchors are preserved as diagnostic evidence;
- if no runtime anchor repair is implemented yet, remaining issue counts may not
   improve, and that is acceptable for this PR;
- no false deletions or readability regressions are introduced by cleanup
   contract changes;
- downstream PR-H/PR-I/PR-J can trust that visual artifacts came from the real
   pipeline path.

#### Stop Conditions

Stop and update this backlog instead of widening the PR if any of these become
true:

- moving anchor repair into runtime requires a broad pipeline refactor beyond
   `late_phases.py` and `reader_cleanup_mvp`;
- preserving verifier anchors requires changing the verifier review JSON schema
   incompatibly with existing artifacts;
- fixing duplicate fragments requires a new cleanup operation type;
- the change needs document-specific literals, regexes, or page-header strings;
- comparison-only artifacts stop being produced.

#### PR-G Completion Report For Orchestrator

Result

- Completed: restored the validator boundary so validation is observational
   only; validator-owned anchor repair execution was removed; verifier output now
   records diagnostic-only anchor metadata and surfaces
   `anchor_repair_status=diagnostic_only_not_applied`; cleanup contract preflight
   was tightened for same-block composed operations, explicit duplicate rejection,
   legacy `delete_blocks` now requiring schema repair/full audit instead of
   code-generated audit fields, numeric-uppercase inline-noise safety, and
   verifier recommendation taxonomy normalization.
- Changed files:
   `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`,
   `src/docxaicorrector/reader_cleanup_mvp/service.py`,
   `tests/test_real_document_pipeline_validation.py`,
   `tests/test_reader_cleanup_mvp.py`.
- Checks:
   `git status --porcelain` confirmed a dirty worktree before final verification;
   `bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q` passed
   (`49 passed`);
   `bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'`
   passed (`19 passed`, `48 deselected`);
   touched files had no editor/type errors.
- Iterations: two implementation slices plus one real-document comparison-only
   rerun attempt.
- Risks: the requested comparison-only real-document rerun for
   `lietaer-pdf-chapter-region-core` with
   `ui-parity-translate-simple-reader-cleanup-comparison-only` did not finish;
   processing reached `phase=process`, `stage=DONE`, but the run never finalized
   report/summary artifacts and root latest still stayed `status=in_progress`, so
   runtime proof is incomplete and the exact finalization failure location is not
   yet isolated.

Continuation

PR-G is complete for the validator-boundary goal. The later comparison-only run
`20260524T085558Z_976_Rethinking-money-chapter-region-pages-10-11-and-156-217`
completed and produced report/summary/UI artifacts, so the old stalled-run
triage is no longer the next work item. Do not reopen validator-boundary edits
unless a new run reproduces a validation-owned mutation or finalization failure.
Proceed to PR-H: Reader Cleanup Visual Blockers.

## Final Validation Strategy

For each PR, run focused tests first. Before any final verification, check the
dirty worktree:

```bash
git status --porcelain
```

For real-document evidence, use the same comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

The proof target is not `acceptance_passed=True`. The proof target is:

- validation does not mutate cleaned Markdown/DOCX after pipeline artifact
   production;
- cleanup chunk failures decrease;
- accepted bounded operations increase for valid cases;
- ignored operations remain explainable;
- reader quality score improves or stays improved;
- remaining reader-visible issues decrease;
- no false deletions or readability regressions appear;
- raw and cleaned artifacts remain reviewable.

## Stop Conditions

Stop and update this backlog instead of coding further if any of these become
true:

- PR-A requires changing the cleanup operation contract beyond schema repair;
- a proposed fix needs document-specific deterministic cleanup logic;
- a proposed fix uses regex-repair as the main cleanup mechanism instead of
   AI-proposed bounded operations plus code-owned safety/application;
- a change would modify structure-recognition authority boundaries;
- real-document evidence shows false deletions or readability regressions;
- comparison-only artifacts stop being produced.
