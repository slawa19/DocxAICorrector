# Global Plan — Book Translation Pipeline

Date: 2026-06-16
Status: Active. Single forward reference for the pipeline.
Supersedes (for forward work): the planning docs now archived under
`docs/archive/specs/` (roadmap, MVP spec/backlog, reader-cleanup experiments,
PDF-import pivot, structure-recognition migration). Those remain as lineage only.

Active companions:
- `docs/RUNNING_THE_PIPELINE.md` — CANONICAL runbook for tests, config/model checks, and full-book
  pipeline runs. Read it BEFORE running anything; verified copy-paste commands + the pitfalls list
  (wrong model gpt-5-mini vs Gemini, env-override, WSL backgrounding, CRLF launchers).
- `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` — the first
  UI slice (how residual discrepancies reach the user).

## ═══ NAVIGATION / RESUME POINT (read this first) — updated 2026-06-22 ═══

**DONE this session (2026-06-22):** (1) Money main-text CLOSED via import fixes (sentence-breaks 89→1, 37
numbered headings promoted, footnotes 73→~21; accepted residue: ~10 body-font numbered sub-points, 3 "О"
caption-drops) — do NOT re-polish. (2) #2 structure-recognition feature FULLY REMOVED (f4cc963, −29.5K lines;
full suite 1855 pass; value moved to import). (3) BREADTH validated on lietaer + mazzucato — **import fixes
GENERALISE** (sentence-breaks ~200/245 → 25/63, footnotes → 0-1, no text loss, images intact); both fail
acceptance ONLY on pass-through (refs/captions/figure-labels/part-dividers) = confirms the gate needs work,
NOT the import.

**CURRENT STEP → Remaining-Work item 1 (gate stability / gate VISION).** 1‑A DONE & orchestrator-verified
(merged 062ef15: refs/bibliography/captions/part-divider exclusion generalised; on REAL breadth reports
lietaer SRC 47→8/TGT 17→2, mazzucato 26→2/12→3, all three unmapped checks now PASS, real body still counts,
Money fixture intact). De-hyphenation DONE too (merged afa506a: corpus-evidence-gated — the naive "remove
hyphen" would have corrupted 201 compounds; units unchanged, compounds safe). **NOW: 1‑B** (legacy-gate
audit, breadth = corpus: lietaer mixed_script_term=2 / list_fragment_regression=20 / raw_false_fragment=69 /
untranslated_body_review; mazzucato list_fragment_regressions_present — real defect vs stale heuristic?),
then 1‑C (severity-table extraction), 1‑D (decide body-integrity axis). Full scope in "### 1" below.
**1‑B DONE (merged 87c6c7d):** the only false hard-fail — mazzucato `list_fragment_regressions_present` —
fixed by partitioning residue (any non-numeric body fragment → hard-fail; pure standalone-numeric back-matter
→ review regardless of count; arbitrary cap=3 removed). Unit-verified; end-to-end confirms on a fresh mazzucato
run. 1‑B audit verdict: gate hygiene otherwise SOUND (raw counters already gated to 0; sleeping gates disabled).

**CRITICAL FINDING — full formatting re-verification (2026-06-22, director-requested, orchestrator-confirmed):**
Everything is OK EXCEPT **inline bold/italic is being LOST** (BINDING contract violation). Images (43/43,
55/55, 42/42), lists, headings/subheadings, target-styles (no zoo) — all OK. But emphasis: lietaer output
bold=13/italic=3 vs source .docx bold=143/italic=642 (italic almost entirely lost). Two import defects:
(6.2) font-name heuristic `"italic" in name` misses `-It`/`-BoldIt`/subset names (`text_layer_quality.py:262,383`)
→ kills lietaer italic; (6.1) emphasis is assigned per LINE (most-common font of a pdfminer line) not per
CHARACTER (`text_layer_quality.py:238-262` + `processing_runtime.py:576-611`) → a single italic word/book-title
mid-sentence is lost (money 876 / mazzucato 881 mixed lines). This is part of the MAIN GOAL (canonical
formatting). Secondary items noted: numbered-body promoted to Heading 3 (money 47/mazzucato 67 — verify
heading vs list), stray "%"/"***" headings.

TYPOGRAPHY SCOPE DECISION (director, 2026-06-22, orchestrator-verified) — **input-format-driven, no
overengineering.** The pipeline has TWO input paths with different ceilings (verified): PDF-text-layer loses
most typography (PdfTextSpan carries only per-LINE is_bold/is_italic); the **DOCX-input path already
preserves it natively** (verified on money.docx via `extract_document_content_from_docx`: bold 313,
underline 254, superscript 46, tables 3) and the render (Pandoc `markdown+raw_html+superscript+subscript`)
supports all of it. So the gap is ONLY in PDF import. DECISION:
- **DOCX input available → use it** (full typography for free). KEEP the DOCX path; code-review + robustness/
  correctness test it (director asked). Caveat: DOCX path is DIFFERENT import code — our recent PDF-import
  structure fixes (chapter/numbered headings, continuation-merge, footnotes) do NOT apply there → verify its
  structure quality on one run before relying on it.
- **PDF input → SIMPLE & RELIABLE, no overengineering.** Extract only what is cheaply/reliably extractable:
  **bold/italic** (font-name dictionary to catch `-It`/`-Bd`/subset abbreviations + CHARACTER-level runs
  instead of per-line most-common) — the big, reliable win (fixes lietaer italic 3→~600 + sub-line emphasis);
  **super/subscript** ONLY if cheap from size+baseline already in spans. **ACCEPT as the PDF ceiling — do NOT
  extract (require expensive/noisy geometric reconstruction, no direct attribute):** underline, tables,
  hyperlinks, list-nesting. Document them as accepted PDF-input losses; when fidelity matters, use DOCX input.
- **Also (director): code-review the PDF import** (`pdf_import/*`, `processing_runtime.py` PDF path) for dead
  code / duplication / dead-ends / obvious bugs / excess → fix & optimize alongside the typography fix.
Anti-infinite-polishing: the ACCEPT list above is explicit and binding — do not chase the PDF ceiling.

BIG FORMAT WORK DONE & orchestrator-verified (2026-06-22):
- **DOCX-path review** (merged 40995c6): fixed field-code/`delText` leakage (185 polluted paras → 0 in Value
  of Everything), toggle-off bug (`w:b w:val="0"` wrongly bold), + robustness tests. DOCX path confirmed
  robust; native typography (bold/italic/underline/sup/sub/tables) transfers. Remaining minor (documented,
  not fixed): in-table-cell emphasis, style-inherited emphasis.
- **PDF inline emphasis** (merged 57f93e4): font-name dictionary (`_font_style_flags` catches -It/-Bd/subset)
  + CHARACTER-level runs on PdfTextSpan + emission rework (`_append_pdf_text_paragraph_to_docx` now emits from
  paragraph.text via per-run bold/italic, fixing the multi-span bypass that made de-hyphenation + inline
  footnote-markers INERT in output). Independently verified: lietaer italic 3→831 runs, structure counts
  IDENTICAL (no regression), runs==text (no corruption), full suite 1885 pass. Dead code removed
  (`_font_ratio`/`_strong_heading_indent`/`_looks_like_standalone_heading_context`), duplicate predicate
  consolidated. super/sub/underline/tables/hyperlinks NOT done (accept-list, binding).
- PROCESS NOTE: first PDF-fix attempt was built on a STALE base (would have resurrected #2) — caught before
  merge, discarded, redone on current main. Lesson: verify code-agent branch base (`git merge-base` vs main).

NOW: fresh eyes-on runs on current code (all import fixes + typography) — creatingwealth (NEW book, PDF) +
lietaer (PDF, italic-recovery demo), run_ids `20260622T_creatingwealth_final` / `_lietaer_final`. Then
orchestrator re-verify (typography present, structure clean, defects low) → director eyes-on final documents.
Note: only creatingwealth is a genuinely new source PDF; the other sources have .docx variants (different path).

DIRECTOR EYES-ON #1 (2026-06-22): "overall looks very good." Flagged two heading defects on creatingwealth →
FIXED (merged ab71115, GENERAL rules, no per-book literals): (A) Part-dividers ("Part N")/section-markers
(Conclusion/Introduction/Appendix…) now promoted to headings (were bold body); (B) spurious chapter-heading
de-dup — adjacent same-number dups collapsed, back-matter chapter runs demoted, real "Chapter N — Title"
openers preserved. Verified on source + corrected creatingwealth run. RESIDUAL ACCEPTED (director: no
deterministic per-book tweaks — if no general rule, leave it): 2 part-boundary "ГЛАВА 1 + ГЛАВА N" spurious
pairs the general cluster rule didn't catch remain — NOT chasing a book-specific fix. Now: fresh Money run
(`20260622T_money_allfixes`) = cumulative result of ALL fixes for director eyes-on #2.

STANDING PRINCIPLE reaffirmed (director): NO deterministic per-book edits; only general rules. Reinforces
Working Rule #7 (no document-specific literals). A defect with no general rule is ACCEPTED, not patched.

DIRECTOR EYES-ON #2 (Money, 2026-06-22) + STRUCTURE FIXES. Money output looked good (italic 748 on titles,
acceptance passed, images 43/43, breaks 4). Director flagged structure defects; deep diagnosis + fixes:
- **DONE (merged da6789b, universal, no literals):**
  - **#1 Chapter headings destroyed into numbered page-footnotes** — ROOT: assembly-normalization bug in
    `output_validation.py::_normalize_final_entry_list_fragments` (a footnote block ending in a hanging "N."
    page-ref carried its number onto the NEXT entry and stripped its "#", turning "# Глава IV" into
    "24. Глава IV"; the carry branch's guard checked the current entry but not the follower — the intro
    branch already had the right guard). FIX: skip carry-over when the follower is a heading. Restores
    Глава IV/V/VI/VII + stops parasitic footnote numbers. **This was the highest-impact structure fix.**
  - **#2 Numbered section headings vs bare subheadings same level** — `_infer_heading_level` ranked only by
    font size (both body-font → L3). FIX: a leading section ordinal ("N." / "N.N") lifts a body-font heading
    one level (numbered→L2, bare→L3); large-font chapter tiers untouched. Role stays heading. 320 tests pass.
- **ACCEPTED (semantic / cross-role tail — no general deterministic rule; per standing principle):**
  - #5 body-like subheadings (14.4pt = body font in the source; the .docx itself styles them "Body text" —
    NO typographic/style signal; only SEMANTIC inference could recover them — that was #2/structure-recognition,
    removed). #4 box/sidebar sub-headings (same body-like class). #3 single line-break after a figure caption
    (cross-role toc_entry misclass; diminishing-returns tail). creatingwealth part-boundary "ГЛАВА 1+ГЛАВА N"
    duplicate residual (2-item non-strict clusters the general rule didn't catch).

WHAT REMAINS TO CLOSE (director asked): (a) gate is BLIND to body-structure damage — it passed Money with 4
chapter headings destroyed → a **body-integrity axis** (heading-demoted-to-list, sentence-breaks) belongs in
item 1‑D / item 3. (b) The five "Remaining Work Before UI" items 2–5 (reliability controlled-fallback,
acceptance meaning, harness↔prod parity, Mazzucato tail). (c) Then UI. Structure/formatting cleanliness — the
director's stated priority — is now in good shape (bold/italic transferred, chapter/part/section headings +
levels, images, clean prose); remaining structure gaps are the ACCEPTED semantic tail above.

**FORWARD SEQUENCE (the main line — do NOT lose it):**
1. → **item 1: gate stability/vision** (A→B→C→D) ← WE ARE HERE
2. items 2–5: reliability (controlled-fallback), acceptance meaning, harness↔prod parity, Mazzucato tail
3. **UI** (FORMATTING_DISCREPANCY_REPORTING spec).
Parked follow-ups: de-hyphenation (parallel); "О" reassembly caption-drop; footnote end-to-end confirm;
cross-role sentence-break tail (ACCEPTED, diminishing returns).

## Product Goal

Translate **full books** (PDF -> translated DOCX) preserving formatting, images,
structure, and reading quality, at book scale, on a stream of different books —
not one perfected excerpt. Gemini is the translation baseline; advanced models do
reader cleanup where judgement helps.

## Where We Are (2026-06-16)

Working and validated on two full, dissimilar books (Lietaer Rethinking Money,
Mazzucato The Value of Everything — PDF):

- **PDF text-layer import** is the chosen source path; images preserved (12/12,
  42/42, 55/55 across runs).
- **Translation** (Gemini) + **reader cleanup** (AI-first, PR-H0 readable-draft
  boundary) run at book scale.
- **Formatting preservation** is solved at the contract level: the acceptance
  gate is **role-aware coverage** (a heading/list/caption that loses its role
  counts; body legitimately reshaped by translation is credited with evidence),
  computed in shared code consumed by both production validation and the proof
  harness. The matcher **generalises**: Mazzucato maps 1075/1140 with
  `bad_pair_count=0` and role-aware basis on source and target.
- **Reliability**: a full book now completes end to end. Two abort causes are
  fixed — progress-write permission (atomic temp in the run dir) and
  `english_residual_output`/`empty_response` (controlled per-block fallback that
  surfaces the bad block and continues instead of crashing the run).
- **Stale gates**: three document-specific legacy heuristics were narrowed to
  unit-aware rules (`false_fragment_headings`, `list_fragment_regressions`,
  target-side topology masking) — classify-then-narrow, never blanket-zero.

Net: we moved from "formatting is lost" to "two full dissimilar books pass
through with a meaningful, audited gate."

## Update — 2026-06-18 (validation findings + refocus)

Eyes-on validation of the reader-cleanup post-pass (faithful replay, live model,
production prompt/config) over all three frozen books changed the picture. Record
these and refocus accordingly:

- **P0 fidelity blocker — reader-cleanup destroys image anchors.** The post-pass
  deletes/drops `[[DOCX_IMAGE_img_*]]` anchors: Creating Wealth 62→42 (20 via
  `delete_block reason=extraction_artifact`), Lietaer 55→18 (37 distinct IDs lost
  with **no** logged op — silent), Mazzucato 40→35. This is in the raw→cleaned
  **markdown** transform, not a harness artifact. So the "images preserved (34–62)"
  claim above holds only for the BASELINE path (reader-cleanup OFF). **Reader-cleanup
  must not be enabled in production until this is fixed** (protect image anchors from
  delete_block; preserve them through join/normalize/assembly with an audit trail;
  unit test = zero image-ID loss).
- **reclassify_role validated: correct & safe but marginal.** 3 accepted ops / 3
  books, all eyes-on-correct (1 epigraph-author demote, 2 part-subtitle promotes),
  zero body over-promotion. The motivating cases are **already solved by the importer**
  self-calibration work (2ab9a22/916dac3): "THE MERCANTILISTS"/"GDP" are already
  headings; the epigraph-author false-positives are gone. **The "19 vs 75" heading-gap
  premise in the PDF-heading section below is therefore STALE** — re-measure before
  treating it as open. A minor apply-guard recall gap remains (bold/letter-spaced
  lines rejected by exact-preview match); low ROI, defer.
- **Reliability harden landed (committed e6bcdf2):** reader-cleanup now fails loudly
  on auth/credential errors under any policy and on an all-chunks-failed ratio gate,
  instead of reporting a clean no-op. (Root cause it fixed: a 75/75-failed run that
  silently reported `stage_status=completed`.)
- **Evaluation discipline (re-confirmed):** cross-language heading P/R/F1 vs the
  English FineReader refs is invalid for Russian output (≈0.01, deltas in noise) —
  use FineReader as a recall guide + manual false-positive typing only, per the
  Generalization section's own rule. Clean metrics twice hid real defects (silent
  auth pass; image deletion); only opening the artifact caught them.

**Refocus (agreed 2026-06-18).** Reader-cleanup is an OFF-by-default enhancement, not
a UI-blocker, and is now image-blocked; stop polishing it (and stop re-running the same
three books). Return to the real path to UI: items 1–4 below — make the gate trustworthy
(item 1) and go for **breadth** (2–3 NEW, differently-formatted books, which is what
exposes the remaining stale gates). Reader-cleanup prod-enablement is parked behind the
P0 image fix.

## Update — 2026-06-19 (reader-cleanup structural-fix redesign: study & make it work)

Director steer (supersedes the 2026-06-18 "park/bias-away" lean): do NOT retire the AI
cleanup, and do NOT slide into per-book deterministic patches — that overfitting is the
flawed path. Structure judgment (headings/boundaries/lists) is a job the AI SHOULD do well;
it underperforms because of how it is WIRED, not the approach. Eyes-on the shipped baseline
DOCX (Money & Sustainability) showed obvious un-fixed defects: footnote markers glued to body
(25/43/44), subheadings fused mid-paragraph ("Экономические последствия концентрации
богатства", "Последствия для устойчивости"), broken lists/line-breaks. The shipped DOCX had
cleanup OFF (image-safe); and even when ON (replay), cleanup spent 11/19 ops deleting images
and caught only ~6 fusions. Two root causes, grounded and independent of model/prompt:
- it runs POST-translation (judges Russian text; original typography lost);
- its `block_metadata_by_index` hook (service.py:505) is fed only identity (late_phases passes
  `cleanup_identity_metadata`) — ZERO layout signals (font size, standalone-short-line, indent,
  superscript) that import already computed. It is structure-blind by construction.

Eight levers, three phases. Plan to be updated as results land. **Cross-cutting acceptance (all
phases):** no doc-specific literals (known defects are measurement targets, never hardcoded);
generalization = SPREAD across books, not average; eyes-on the produced DOCX; never credit
content-presence as format-presence; never silently lose content/anchors; full test files green;
cheap no-re-translation replay to iterate, full-book LLM only to confirm.

Phase 0 — safety + signal (cheap, low-risk, FIRST):
- L6 Content/anchor reconciliation. Remove the prompt instruction+example that tell the model to
  delete `[[DOCX_IMAGE_*]]` (service.py:449/453); hard-guard delete_block against image anchors
  in code; post-pass reconcile image IDs in==out, re-insert/flag any drop. **Done:** no book (the
  3 + Money & Sustainability) loses any image ID after cleanup; unit test; silent drops caught.
- L5 Deterministic footnote markers at import. Trailing superscript / short-digit refs separated
  generally (pdfminer superscript/size signal), not per-book. **Done:** markers like 25/43/44 no
  longer glued to body; no stripping of real page-refs/quantities; precision held on 3 books.
- L1 Enrich cleanup block metadata with layout signals (font size vs body mode, standalone-short-
  line, indent, centered, superscript). **Done:** signals present in the chunk payload
  (verifiable); no behaviour regression; enables Phase 1.

Phase 1 — re-architect the AI pass + MEASURE (the core):
- L3 Shift the AI from risky edit-ops (+exact-match guards that reject valid fixes) to role/
  boundary RE-ANNOTATION → deterministic apply → content-containment verification (model judges
  structure, code guarantees content safety).
- L4 Specialized focused passes (heading-boundary, list-reassembly) instead of one omnibus prompt.
- Measurement experiment (cheap replay over Money & Sustainability translated markdown, no
  re-translation): matrix {current edit-ops vs re-annotation} × {haiku/sonnet/opus} × {±layout
  signals}, scored against the KNOWN defect set (the fusions/list/footnotes above) + false
  positives + image safety + cost. **Done:** a measured config→(caught / false-pos / images-
  touched / cost) table; a chosen config catches the listed defects on this book with NO
  regression on the 3 tuning books (heading precision not down; zero image loss; no content change
  beyond structure/role).

Phase 2 — bigger moves, ONLY if Phase 1 leaves material defects (reserve):
- L2 Source-side pre-translation structural normalization (richest signal; fix once, before
  translation scrambles it) — bounded/local, NOT the killed global DocumentMap.
- L7 Verify-and-retry (LLM-judge) targeting the known defect classes (reader_verifier scaffold
  exists, disabled).
- L8 Vision (VLM over PDF page images) for the genuinely ambiguous tail only.
- **Done:** each gated by held-out measurement + no per-book literals; pursue only what Phase-1
  data justifies.

## Formatting Transfer Contract — BINDING (re-affirmed 2026-06-20)

The "what exactly do we transfer" requirement had drifted into archive. Canonical source:
`docs/archive/specs/TOC_TRANSLATION_AND_MINIMAL_FORMATTING_SPEC_2026-04-21.md` §8.3 (now lineage);
its minimal-formatting policy is PROMOTED here to ACTIVE and binding. This bounds all further
structure/formatting work — no feature may widen it without an explicit decision.

KEEP by default (structure + inline emphasis):
- headings + levels — rendered via TARGET reference-DOCX heading styles, NOT source geometry/size;
- body paragraphs — target defaults; lists (ordered/unordered + nesting); tables (baseline readable);
  images + captions;
- inline emphasis: bold, italic, underline, superscript, subscript, hyperlinks, line breaks.

DROP by default (the "source style zoo"):
- source paragraph style names; source fonts, COLORS, FONT SIZES; tab stops, indents, spacing,
  paragraph geometry; blind direct-alignment replay.

WHITELIST exceptions only: center for image placeholders; narrow test-backed centered short
non-heading paragraphs; baseline target table styling (Table Grid); list-numbering compat shims.

Measured current state vs contract (code audit 2026-06-20):
- Font COLOR: NOT applied to text by our code (`color` only in config/image modules; no
  `font.color`/`RGBColor` in document/generation). Red squiggles in screenshots = Word spell-check;
  heading colour = target template styles (compliant). No colour drift.
- Font SIZE: source `font_size_pt` replayed ONLY on TOC lines
  (`_restore_toc_run_formatting_for_mapped_pairs`, gated to toc_header/toc_entry), not body — one
  borderline item to review, not a general zoo.
- So real drift is small; the gap was that the contract was not ACTIVE or ENFORCED.

Binding actions:
1. This contract is the active reference; the archived spec stays as detailed lineage.
2. Add an ENFORCEMENT test: output DOCX body/headings carry NO source colour/font/size/indent/
   spacing; inline emphasis preserved; whitelist-only exceptions — so drift cannot silently return.
3. Review the TOC font-size exception against the contract (keep as narrow TOC-readability
   exception, or drop).

Implication for structure/heading work (bounds further development):
- Structure detection's job is to TAG role (heading/list/caption/footnote); RENDERING uses TARGET
  styles. NO typography replay, NO size/colour machinery.
- The 2026-06-19 post-pass experiments (0/4; target subheadings are typographically BODY-LIKE —
  real-layout signals at the targets read font≈body, bold=false, indent≈0) CONFIRM typography is the
  wrong lever: the residual is SEMANTIC role-tagging, not style transfer. This contract makes that
  explicit — stop chasing typography; get role tags right and let target styles render.

## Update — 2026-06-20b (shipped-DOCX defects classified: they are IMPORT-origin)

Director's eyes-on the shipped Money & Sustainability DOCX flagged four defect classes. Each was
checked against the PRE-translation imported markdown (`money_sustainability_imported.md`): all four
are present BEFORE translation → they originate at IMPORT, not the post-pass. (The AI post-pass was
never the right owner, and the 2026-06-19 experiments proved it dead for structure anyway.)

Defect ledger:
- A. Footnote markers glued to body (25/43/44). Pre-translation evidence: import lines 448/480/482/
  486 end "...times.2", "...Rome.5", "...States.6", "...change.8". Origin: IMPORT (superscript refs
  extracted as inline digits, not separated). Fix locus: import — deterministic footnote-marker
  separation (general; pdfminer superscript/size), not per-book.
- B. Subheadings fused / heading-role lost (e.g. "Short-Termism…", "Implications for sustainability").
  Evidence: import line 1410 "2. Short-Termism: Why the Future is Discounted" is a STANDALONE line
  but is NOT tagged as a heading (typography body-like) → renders as body. Origin: IMPORT heading-
  role tagging miss — the standalone-LINE signal exists, but detection keys on body-like font.
  Fix locus: import — tag standalone numbered/section lines as headings via line-structure +
  semantics, NOT typography.
- C. Body paragraphs fragmented mid-sentence. Origin: IMPORT paragraph segmentation on epub→pdf
  (same mechanism as D). Fix locus: import — rejoin via line-fill-ratio / continuation signal.
- D. Lists broken; items split / numbering lost. Evidence: import line 1376 item "1. …the upturns"
  continues on the next line. Origin: IMPORT list-item segmentation. Fix locus: import — list-item
  reassembly + ordered-intent preservation.

Consequences:
- The reader-cleanup structural-fix redesign (8-lever, 2026-06-19) is CLOSED for structure: the
  post-pass cannot recover structure from translated, typographically-body-like text (0/4 incl. real
  signals). KEPT: Phase 0 image safety (shipped, 43→43 on all 4 books). The structural levers
  re-home to IMPORT.
- Active direction for these defects: IMPORT-side segmentation + role-tagging, under the Formatting
  Transfer Contract (tag role → render with target styles; no typography replay). This is the
  existing "Generalization of structure detection" section, now with a concrete classified ledger.
- Bounds: profile-first / line-structure signals + semantics for the body-like tail; NO per-book
  literals; eyes-on the produced DOCX; measured held-out (spread across books).

## Update — 2026-06-20c (BINDING scope: main-content focus; B = test the existing pass first)

Director scope decision (BINDING): TOC and source/reference regions (bibliography, notes pages) are
PASS-THROUGH — detected and translated as-is, but EXCLUDED from structure/B work and from strict
acceptance (not held to heading standards, do not fail the run). **Main content + its formatting is
the focus.** This removes the hardest ambiguity (section-heading vs TOC-entry, which caused the
deterministic regressions) and makes the Class-2 extraction garble (front-matter/biblio) and most
unmapped-acceptance noise moot.

B recon findings (verified by orchestrator):
- The B candidate tail is FAR smaller than a naive "short standalone" count: e.g. Rethinking's 575
  short lines are mostly WRAPPED BODY TEXT + back-matter (656/1449 short lines in the last quarter),
  not subheadings. Real B candidates are narrow: ALL-CAPS-fused-with-body (CONCLUSION x4 Mazzucato),
  `N. Title` followed by prose (Systemic Crises, Money), attribution-like — in MAIN content only.
- A source-side, pre-translation, ROLE-ONLY structure-recognition pass ALREADY EXISTS
  (preparation.py:2730/2821 -> _run_structure_recognition -> build_structure_map -> apply_structure_map;
  roles heading/body/caption/attribution/toc_entry/...). It re-tags roles but CANNOT split a fused
  heading/body block (apply_structure_map only sets role/heading_level — verified recognition.py:687-751).
  This is NOT the killed structure-first tarpit (that was the global DocumentMap/topology); role-tagging
  is bounded.

Adjusted B plan (classify-before-BUILD):
1. The forensic imports were NO-LLM (typography only) — which is WHY B is unfixed there. **FIRST TEST**
   whether the existing AI structure_recognition pass, when ON, already tags the B cases correctly on
   the 4 books (CONCLUSION/Systemic Crises -> heading; TOC rows -> toc_entry; no false-promote of
   body/list), scoped to main content. This decides ENABLE-AND-EXTEND vs BUILD-NEW.
2. A bounded SPLIT-prefix patch (heading_substring/body_substring + containment, applied at
   import/source) is needed regardless for the fused cases (host can't split). Reuse the exact-substring
   / containment idea from normalize_heading_boundary.
3. Bounds: source-side, role-only, NO global DocumentMap/topology; candidate set is the NARROW tail
   (ALL-CAPS-fused / N.Title-before-prose / attribution in MAIN content), NOT "every short line";
   output role/split -> target styles; measured held-out + manual false-positive typing.

**DECISION 2026-06-21 — B DEFERRED (cosmetic tail).** Measuring the existing AI structure_recognition
on all 4 whole books surfaced the real signals: it DOES NOT SCALE (Rethinking classified only
505/2255 = 22% before window/fallback gave up) and is EXPENSIVE (8-19 min/book), while fixing only a
small subheading tail (8/14 standalone correct, 0/6 fused). Enabling that heavy pass is the wrong
instrument for a minor cosmetic gain. B (some main-content subheadings render as body / glued to body)
is hereby a KNOWN DEFERRED cosmetic tail — do NOT pour more in, do NOT enable the heavy non-scaling
pass. Revisit only if B becomes must-have, and only with a LIGHT approach. The real defects (footnotes,
paragraph/list breaks, images, formatting contract) are closed. Refocus: the items 1-4 path to UI.
(Orchestrator note: on every expensive whole-book run, lead the review with the BIG cross-book signals
— scale/reliability/cost — before any tail detail.)

## Update — 2026-06-21b (Pipeline code-review defect ledger: "success while silently failing")

A 4-subagent read-only review of the pipeline stages (import/prep; translation/block-exec;
structure/cleanup/assembly; validation/acceptance/formatting) found a consistent class: a stage
reports SUCCESS while silently failing, losing content, or not gating. This is the root of the
"running blindly" pattern. Verify each (classify-before-fix) before fixing; #1 verified by orchestrator.

TIER 1 — CRITICAL (production path; output actually wrong):
1. [VERIFIED] Untranslated English block ships as "success". Exhausted-retry fallback returns the
   source `target_text` (_generation.py:1050); `has_unexplained_english_residuals` returns False when
   there is no Cyrillic (output_validation.py:270) → a pure-English fallback block classifies as
   "valid" (block_execution.py:1117). Untranslated content in the Russian DOCX, green status, no signal.
2. Structure recognition silently accepts partial coverage. window-fail `continue` (recognition.py:896),
   split-cap returns [] (:1161), parser covers only returned indices (:1481); no coverage gate in
   preparation.py. = the observed Rethinking 505/2255.
3. Silent image loss. `_append_pdf_image_to_docx` (processing_runtime.py:607) swallows a render
   failure; the success log counts `image_count` including images that never rendered.
4. Quality gate is computed on the PRE-reader-cleanup markdown, but the shipped DOCX is the
   POST-cleanup artifact (late_phases.py:3707 vs 3798) — the green verdict is earned on a different
   artifact than what ships (worse when cleanup is ON).
5. Quality-gate authority fields swallowed by bare-except (late_phases.py:2943) → on import failure,
   fields default to absent/pass, downgrading a real structural defect to warn (scoped toc_body_concat/topology).

TIER 2 — HIGH:
6. origin-index collisions (logical_import.py:1507) — dense/two-column pages: wrong emphasis,
   arbitrary image/text order, no uniqueness check.
7. Assembly invariant checks COUNT not content (block_execution.py:1229) — controlled-fallback always
   appends one chunk, so count matches even for an empty/English fallback; no content-presence check.
8. Leakage fail-open (_generation.py:456) — last retry returns leaked neighbor text as valid.
9. Harness structural validation does not gate on quality_status (structural.py:2538) — harness
   `passed` can be green while the report says fail (harness↔prod divergence).

TIER 3 (feature-gated: reader-cleanup OFF by default; or TOC-related, now pass-through → lower):
reannotation path has no auth/ratio gate; `max_failed_chunk_ratio=1.0` tolerates 99% chunk failure;
image reconcile appends lost anchors at document end; positional TOC fallback applies source font-size
with no text evidence; TOC pPr uses a denylist not an allowlist.

Priority: TIER 1 (esp. #1/#2/#3 — production path, lose/corrupt real content). These explain the
"run blindly" pattern: a stage's green status was not trustworthy.

## Update — 2026-06-21c (fresh Money/Gemini run audited; gate-vision fix in flight; #2 confirmed live)

Fresh full-pipeline run on the CORRECT baseline (Gemini via OpenRouter), reader-cleanup OFF, image-safe:
run_id `20260621T_money_gemini`. Orchestrator audited the artifacts directly. Honest state:
- Output is HEALTHY for main content: DOCX openable, no placeholder leak, output_ratio=1.045,
  silent_text_loss=False. **Images 43/43 emitted** (signal #3 OK; no loss with cleanup OFF).
- **Signal #1 (source_text_fallback) = 0** — the TIER-1 #1 fix holds on a real run; no English-as-success.
- **Signal #2 CONFIRMED LIVE & now observable**: structure AI pass timed out on the big window, retry
  FAILED (structure_timeout_retry_failed=1), document fell back — primary_classified=203 vs
  split_fallback_classified=1405; readiness=blocked_unsafe_best_effort_only. The diagnostic snapshot
  now exposes what used to be silent. This is the same partial-coverage class as TIER-1 #2.
- acceptance=FAILED, but on unmapped_source(71)/unmapped_target(67)/formatting_diagnostics — and the
  unmapped items are EXACTLY the agreed pass-through categories: front-matter OCR garble
  (title/cover/attributions), bounded-TOC, and page-furniture digits ("1","2","5"…). NOT main-text loss.

ACTIVE NOW (orchestrator-issued dev task): **Acceptance gate "vision" fix** — exclude ONLY
front-matter / bounded-TOC / page-furniture from unmapped thresholds, by detection, with provenance,
WITHOUT suppressing genuine unmapped body prose (offline test on this run's artifacts + a synthetic
real-body counter-example). Rationale: without a trustworthy verdict we polish main text blind, AND a
clean gate then MEASURES whether #2's structure fallback actually damages main text (currently unproven).

NEXT (queued, after gate-vision): **Structure-recognition fallback hardening (TIER-1 #2)** — the
203-vs-1405 primary/fallback split + failed timeout-retry on Money. Do NOT start until the gate can
measure before/after on main text. Main goal UNCHANGED: ship-quality translated DOCX of the MAIN
CONTENT for one source, then breadth across books; TOC/front-matter/references stay pass-through.

## Update — 2026-06-22 (ROOT CAUSE of "nothing we fix sticks": defect is IMPORT-stage segmentation)

Director pushed: why does NOTHING we ship for assembly actually fix the body? Ran a NO-LLM import
diagnostic on Money (extract spans → `build_paragraph_units_from_text_spans`) and inspected the units
BEFORE any LLM. Decisive finding:
- Import produces **148 unmerged sentence/list continuations** (line ends with no terminal punct →
  next line starts lowercase) + **118 bare-digit footnote units (role=footnote)** ALREADY in the
  normalized DOCX, before structure recognition runs at all. English source, e.g. `…It makes clear`
  → `that awareness of`; `…between money` → `and sustainability…`.
- **Paragraph segmentation is FIXED AT IMPORT** (`processing_runtime.py:511,530` builds the normalized
  DOCX straight from importer units). Structure recognition only RE-ROLES; it NEVER merges paragraphs.
  So neither the full structure pass nor the timeout-fallback can fix these — it is not their job.
- Therefore EVERY measure we shipped (translation-fallback, image, structure-coverage, gate-vision,
  even the existing import "line-fill merge" at `logical_import.py:1114`) is ORTHOGONAL to the dominant
  body defect. The line-fill merge EXISTS but does NOT fire on this epub→pdf source (148 pass it).
- Cache RULED OUT (`preparation.cached=False`, logic version=2 in key). Fallback is NOT the main
  culprit. The gate is blind to this class by construction (these paragraphs map 1:1, so not "unmapped").
This is why we were circling: the "import-origin" diagnosis (2026-06-20b) was right, but we kept fixing
structure/gate/translation instead of the importer's continuation-merge itself.

DONE & orchestrator-verified (2026-06-22, merged to main d5970c7): **import continuation-merge fix**
in `build_paragraph_units_from_text_spans`. Independent no-LLM baseline↔fix comparison on 3 books:
unmerged body continuations Money **148→1**, lietaer 202→2, mazzucato 245→1; **NO over-merge — heading
& list unit counts IDENTICAL baseline↔fix on all three** (money 115/232, lietaer 176/286, mazzucato
132/480). Root cause was geometry/indent-based boundary detection missing soft-wraps (hanging-indent list
continuations, same-line split word-groups, page-break splits); fix adds a geometry-independent
`_is_soft_wrap_continuation_pair` signal. 5 new import tests + file 33 passed. FOOTNOTE re-attach
(118 bare-digit units) DEFERRED by dev as too risky to anchor — still open (see categorization below).
A confirming full Money LLM run on merged main is in flight (run_id `20260622T_money_merged`) to verify
the end-to-end OUTPUT body is now clean (segmentation is import-fixed; structure only re-roles) and to
give a fresh basis for categorizing the remaining main-text defects.

CONFIRMED on merged-main OUTPUT (run 20260622T_money_merged, eyes-on by orchestrator): the merge LANDED —
mid-sentence breaks **89→15**, ≤2-char headings 11→3, acceptance now **passed**. "numbered-as-body" went
20→46 but that is NOT a regression: the merge cleaned split numbered headings into single `N. Title`
paragraphs, REVEALING the true count (~40 real section headings styled Normal not Heading = Defect B).

RESIDUAL 15 sentence-breaks — root cause found (orchestrator, import-level breakdown 2026-06-22; they ARE
real, not analyzer error): the merge joins **same-role pairs only** and is **footnote-opaque**. The 15 are
(a) ~10 CROSS-ROLE continuations (lowercase soft-wrap whose two halves got different body/list/footnote
roles → neither merger fires) and (b) ~5 footnote-NUMBER-at-break ("…path for 50" → "evolution"). The prior
"148→1" acceptance metric was body-body-only and HID these. PROPOSED bulletproof fix (2 principled import
rules): (1) **footnote-marker transparency** — a footnote-role/trailing-number marker is transparent to the
merge (prose merges across it, marker kept inline); this also kills the 72 standalone digit-paragraphs at
one root, no anchor-guessing. (2) **cross-role continuation merge** — a lowercase soft-wrap merges as body
even across a role boundary (a real heading/list-start never begins lowercase mid-sentence). ACCEPTANCE
METRIC FIXED: count cross-role + number-aware (Money ~15→~0) with heading/list counts unchanged on
lietaer/mazzucato. ("Fix the gate" is NOT the lever — the gate does not measure sentence-breaks at all.)
Footnote standalone-digits (72) and "О" caption-drop (3) fold into rule (1) / stay low-priority.

DEFECT B diagnosed & orchestrator-verified (2026-06-22): the ~40 numbered section headings render as
Normal because the IMPORTER mis-tags `N. Title` lines as **unordered/bullet list** (`list_kind='unordered'`).
Evidence: of 47 `N. Title` source units, 46 are `role=list` (all 47 `list_kind='unordered'`), and **5 carry
`role_confidence='explicit'`** = role set by IMPORT with AI untouched (p0449/p1075/p1094/p1144/p1253) →
proves import-origin. A clean no-timeout structure run (even with tiny windows simulating fallback) returns
**heading, not list** → **#2 (structure timeout) is NOT the cause and does NOT fix B**. Worse, prod feeds the
import's bad `list_kind` into the descriptor, BIASING the AI to confirm `list` (42 ai-confirmed) — so the bad
import tag POISONS structure recognition too. FIX LOCUS = import: recognise standalone `N. Title` as a
numbered section heading, not a bullet item.

CONSEQUENCE (key for scope / no-overengineering): **main-text structural quality is now ENTIRELY an
import-layer problem.** Both remaining defects (sentence-breaks AND Defect B) are import-origin; #2
(structure-recognition fallback hardening) is **OFF the main-text critical path** — candidate to drop/defer
in the effectiveness review. Recommend ONE combined import fix: (rule 1) footnote-marker transparency,
(rule 2) cross-role continuation merge, (rule 3) numbered-heading promotion — all in logical_import.py
classification, verified by the no-LLM import diagnostic (cross-role/number-aware count → ~0; numbered
`N. Title` → heading; heading/list counts on lietaer/mazzucato sane), then ONE confirming full run.

DONE & orchestrator-verified (2026-06-22, merged to main c97b7fb): **combined import fix** (rules 1-3) on
branch `fix/import-footnote-crossrole-numbered-heading`. Independent baseline↔fix no-LLM diagnostic on 3
books: Money wide breaks **16→1**, numbered `N. Title` **37 promoted to heading** (list_kind never unordered),
footnote digit-paras 118→103; lietaer/mazzucato **0 over-promotion** (real numbered lists stay list 251/468,
list counts unchanged 286/480), breaks 6→2 / 19→5, mazzucato footnote digits 131→15. The heading-count drop
(lietaer 176→165, mazzucato 132→129, money lost 3) was independently diffed = ONLY spurious index/citation/
running-header fragments correctly demoted to body — NO real chapter/section heading lost. 39 import tests
pass. A confirming full Money run is in flight (run_id `20260622T_money_combined`) for end-to-end OUTPUT proof.
After it: declare Money main-text status, then the queued effectiveness/dead-stage review (#2 first to assess).

DONE & orchestrator-verified (2026-06-22, merged a4f9abb): **footnote boundary re-attach** — sentence-boundary
markers become trailing superscripts on the preceding paragraph. Money standalone footnote digit-units
**103→21**, 82 re-attached inline; **marker-conservation invariant proven (21+82=103, none lost/duplicated)**;
heads/lists unchanged (no over-merge); lietaer/mazzucato intact; 42 import tests pass. The 21 left standalone
are correct (epigraph attributions with no terminal punct, list/heading-preceded). Verified at import level
(rigorous); end-to-end output confirmation folds into the next full run.

=== MONEY MAIN-TEXT STATUS (2026-06-22) — dominant defects RESOLVED via import-stage fixes only ===
Journey on the OUTPUT DOCX: sentence breaks **89→1**, numbered section headings **37 promoted to Heading**,
footnote markers **73→~21** (re-attached as superscripts). Four import fixes (continuation-merge, footnote
transparency, cross-role merge, numbered-heading promotion, boundary re-attach), ZERO changes to structure
recognition or the gate. ACCEPTED remaining (worth-it verdict = not worth it / avoid infinite polishing):
~10 numbered sub-points at body-font (no heading typography → unsafe to promote), 3 "О" reassembly
caption-drops (Money-specific, low volume). KEY ARCHITECTURE FINDING: main-text structural quality was
ENTIRELY an import-layer problem; **structure recognition / #2 contributed nothing to it** → strong input to
the effectiveness review.

NOW ENTERING (director-ordered): **pipeline effectiveness / dead-stage review** — #2 first (does the
structure-recognition timeout/fallback machinery earn its keep, given main-text quality is import-driven?),
then sweep for other idle/over-engineered stages with no measurable output effect, then a worth-it verdict on
every residual. Goal: cut dead weight, no infinite polishing.

#2 CONTRIBUTION MEASURED & orchestrator-verified (2026-06-22, breadth-aware, on saved artifacts): #2 is NOT
pure dead weight but its useful core is TINY. On Money it makes exactly **7 AI heading promotions, all real
chapter headings the import missed** ("chapter i — why this report, now?", "chapter vi/vii/viii/ix", one
numbered subheading), **0 demotions, no harm**; the other ~8 role-changes are body→list (neutral under the
contract) and 62 structural roles (epigraph/attribution/toc) render as body/list anyway = neutral. On
mazzucato (current importer) #2 promotes ~0-1 headings; lietaer's big promotions exist only on the OLD
importer (post-fix import already yields 165≥129 headings). document_map patches 0 on the current Money run
(historical runs show up to ~20 patch-INTENT, gated by locked-override); topology disabled in prod. The
expensive machinery (timeout/retry/recursive split-fallback — retry FAILED, 1392/1499 via fallback, 266s) wraps
this tiny benefit. **The ONLY clean benefit is detecting "Chapter N" (roman) heading lines, which the import
fix does NOT catch (it catches "N. Title").**

DECISION (director, 2026-06-22) — **PATH 2: move "Chapter N" heading detection into IMPORT (deterministic),
then CUT the whole #2 cluster** (structure recognition + split-fallback + document_map + reconciliation +
topology). Rationale: consistent with "main-text structure = import problem", removes an LLM call + ~25% of
prep time, and DE-RISKS the cut (once import owns headings, cutting #2 needs no breadth measurement).
SEQUENCING (dependency: secure headings BEFORE cutting): **Task A** — import "Chapter N" promotion (no-LLM
verifiable: the 7 Money chapter headings now come from import; lietaer/mazzucato no over-promotion), verify+merge.
**Task B** — disable the #2 cluster on the prod path + confirm via one full run that chapter headings survive
(from import) and nothing breaks, then prune the now-dead code. A first.

TASK A DONE & verified (merged 35b21dc): deterministic "Chapter N" heading detect in import. Money body gets
exactly 9 chapter-opener headings (the 7 #2 used to promote, now from import); extra chapter lines promoted are
in front-matter/TOC (pass-through). lietaer +13 (numeric chapter rows), mazzucato 0 false promotes. 46 tests pass.

TASK B (B1) DONE & orchestrator-verified (merged 614ffd9): **#2 cluster DISABLED on prod via one reversible
switch** — `config.toml [structure_recognition].mode = "auto"→"off"`, which short-circuits the single
`should_run_ai` gate in `prepare_source` (preparation.py:2809), turning off structure recognition +
timeout/retry/split-fallback + document_map + reconciliation + topology together. Reversible (mode="auto"/"always").
Experimental profiles (`structural-ai-first-default`, `*topology-advisory`) set mode="always" explicitly →
UNAFFECTED. Verified: no-LLM prep proof = structure client 0 calls, prep completes, 169 import heading roles
flow through (incl. Chapter I–VII). Tests green (config 81, preparation 140, document_pipeline 160, structure_*
suites). NOTE: `test_structure_recognition.py` has 14 PRE-EXISTING failures (identical on base 35b21dc, NOT from
B; they live in the now-prod-dead split-fallback code → address in B2). Confirming full Money run with #2 OFF DONE
(run_id `20260622T_money_no2`), orchestrator-verified vs #2-ON (combined): **output PRESERVED and slightly
better** — acceptance PASSED, headings 122→131 (import headings flow through cleaner), chapter headings
present (21 "Глава", incl. real body openers I–IX), numbered-heading 37→36, sentence-breaks still 1,
output_ratio 1.045, images 43/43, no text loss. **HONEST SURPRISE: NOT faster — ~9% SLOWER** (1605 vs 1473s):
disabling #2 removed its semantic block grouping → translation ran with MORE, smaller blocks (335 vs 287) →
more API calls. So #2 was not purely dead — its blocking aided translation batching efficiency. NET verdict:
the #2 cut is justified on QUALITY + SIMPLICITY (output preserved, unstable LLM stage with timeout-failures
+ Defect-B poison risk removed) but gives NO speed win (slight loss). Possible future: a cheap deterministic
batching to recover efficiency (parked, not pursued — anti-infinite-polishing).

TASK B2 (deferred, director's call): prune the now-prod-dead #2 code — `structure/recognition.py`
(build_structure_map, split-fallback/timeout-retry, apply_structure_map), `structure/document_map.py`,
`structure/reconciliation.py`, `structure/topology.py`+`layout_signals.py`, and the preparation.py stage wrappers
(`_run_structure_recognition`, `_run_document_map_stage`, `_run_document_topology_projection_stage`). NOT a bare
delete — still used by the experimental #2 profiles; decide remove-with-exp-profiles vs keep-behind-flag. Do after
the excursion, low priority. The 14 pre-existing recognition test failures fold into this.

SECONDARY (after the main merge fix): "О"-heading amplification — ROOT CAUSE found & orchestrator-verified
2026-06-22. Only 2 short headings at import (OCR "%"/"o"), but **10× Cyrillic "О" in the output**. They
are a **REASSEMBLY bug**, not import/translation/structure: each "О" stands where a correctly-translated
figure caption was DROPPED. Proof on Money artifacts: per-block #58 = `[[DOCX_IMAGE_img_007]]` +
`Рисунок 2.2: …(подход ОЭСР).` (clean translation), but in `latest_markdown` that caption is GONE
(0 matches) and `# О` appears in its place. So reassembly drops the unmapped/translated caption paragraph
and substitutes a 1-char placeholder heading = CONTENT LOSS (10 captions) + spurious heading. Money-specific
volume (epub→pdf "fig ure" captions all fail to map); the class (dropped short paragraph → 1-char heading)
appears elsewhere only as rare digits. Candidate: `pipeline/reassembly.py` (exact line needs a reassembly
DEBUG run on those 2 blocks — read-only could not pinpoint it). Do AFTER import merge (which changes caption
units and may move this), then re-check whether it persists before fixing.

QUEUED — **Pipeline effectiveness & dead-stage review** (director-ordered, AFTER the current fix+verify
iteration, NOT before): (a) hunt for other unnoticed holes of this same shape (a stage we trust that
silently does nothing useful on real input); (b) identify OVER-ENGINEERED / idle stages — checks,
analyses, passes that run but produce no measurable effect on the output — and REMOVE them outright;
(c) categorize EVERY remaining known problem with an explicit **worth-it / not-worth-it verdict**.
Rationale (binding): we must NOT slide into infinite polishing — each residual defect earns a decision
to fix or to consciously accept, with a reason.

## Remaining Work Before Returning to UI

The UI surfaces results to users, so before UI work the pipeline must (a) reliably
finish **any** book, (b) produce a **stable, meaningful** verdict, (c) in
**production**, not just the harness. Five items, in priority order.

### 1. Gate stability / gate VISION — make the acceptance verdict trustworthy (highest leverage, CURRENT)

**This is where we are now (2026-06-22), after the #2 excursion + breadth.** Scope refined by the breadth
runs (Money PASS; lietaer + mazzucato acceptance=FAILED **purely on pass-through**, not body loss —
output_ratio 1.03–1.08, silent_text_loss=False, images intact). Four parts, do in order:

**A. Generalise the pass-through exclusion to ALL books (do FIRST — it unblocks a meaningful verdict).**
The Money gate-vision fix excludes front-matter / bounded-TOC / page-furniture from the unmapped thresholds.
But lietaer/mazzucato fail acceptance on pass-through it does NOT yet credit: **references/bibliography,
figure captions, part-dividers, diagram labels, author/attribution lines** (verified in the unmapped samples).
Extend the detection-based exclusion (in `validation/formatting_coverage.py` + the acceptance summary) to
these categories, across all profiles, with provenance. Guardrail (same as before): a real unmapped BODY
prose paragraph must still count. Done: on Money+lietaer+mazzucato the three unmapped/formatting checks fail
ONLY on genuine main-body loss, never on refs/captions/front-matter/furniture.

**B. Audit the legacy/heuristic gates — breadth is now the corpus.** The `legacy_markdown` + heuristic gates
(`false_fragment_heading`, `residual_bullet_glyph`, `bullet_heading`, `mixed_script_term`,
`list_fragment_regression`, `toc_body_concat`, `page_placeholder`, `scripture_reference_heading`,
`suspicious_heading_repetition`, `heading_body_concat`, `inline_page_furniture_leakage`,
`pdf_blank_page_marker_leakage`, …) — narrow each to unit-aware evidence or mark explicitly tolerant. Use the
NEW breadth signals that first-fired: lietaer `mixed_script_term=2`, `list_fragment_regression(raw)=20`,
`raw_false_fragment=69`, `untranslated_body/structural_text_review`; mazzucato `list_fragment_regressions_present`.
Decide for each: real defect vs stale heuristic.

**C. Extract the severity model into ONE table** (`_emit_hygiene_gate`). Six hand-copied hygiene-gate blocks
(+ a duplicate in `runtime/artifacts.py`) are the source of report ↔ `formatting_review.txt` drift. Collapse
to a table so B is a glance over data, not reverse-engineering five near-identical branches. (= Architecture
Hygiene Task A.)

**D. (decide; overlaps item 3) Gate VISION — body-integrity axis.** The gate measures unmapped paragraphs but
is BLIND to body-structure damage (sentence-breaks, footnote-as-paragraph): a book with 63 sentence-breaks can
still "pass" on the unmapped axis. Decide whether to ADD a measured body-integrity signal (e.g. sentence-break
count) so the verdict reflects readable quality, not just mapping. Likely lands with item 3 (acceptance meaning).

**Done for item 1:** on 4 books (Money + lietaer + mazzucato + one new) the acceptance verdict is TRUSTWORTHY —
clean main-text → pass; real body loss → fail with a short hand-checkable list; pass-through (refs/captions/
front-matter/furniture) → never a false fail; no new stale-gate first-fires on the 4th book.

Parked import polish (NOT part of item 1): **de-hyphenation** at import (mazzucato "про-\nцентов" → merge a
line ending in a mid-word hyphen). Small, generalizable; can run parallel. The remaining cross-role sentence-
break tail (lietaer 25 / mazzucato ~tens, down from ~200/245) is ACCEPTED — diminishing returns.

### 2. Reliability completeness — generalise the controlled-fallback contract

We fixed two specific block-abort causes. A robust stream needs the
controlled-fallback to be the **general contract**: any block that cannot be
cleanly produced after retries emits a visible fallback artifact and continues,
rather than aborting an expensive run. **Why before UI:** otherwise the next book
hits a new abort cause and never reaches a result to display. **Done:** a book
with several deliberately un-producible blocks finishes with a complete DOCX, and
every fallback is visible in artifacts (no silent loss).

Pre-implementation classification table:

| Block failure class | Decision | Contract |
| --- | --- | --- |
| `empty_response` / `empty_processed_block` after retry budget | `fallback_continue` | Emit a controlled-fallback block, event, and artifact; keep paragraph IDs/registry visible; final DOCX must still be produced. |
| `english_residual_output` after retry budget | `fallback_continue` | Emit a controlled-fallback block, event, and artifact; do not count it as lost formatting when the content is present, but surface it for translation review. |
| `heading_only_output`, `bullet_heading_output`, `toc_body_concat` after retry budget | `fallback_continue` | Treat as generated-output rejection only when the original block payload and paragraph IDs are intact; surface the fallback block for manual review. |
| Missing provider/client/configuration, including OpenAI image-client setup failures | `fail` | Infrastructure/configuration failure; no translation fallback may pretend the requested phase succeeded. |
| Missing source segment, missing translated segment, or `final_translated_book_incomplete` | `fail` | Assembly invariant failure; continuing would silently drop content. |
| Marker registry build failure or missing paragraph registry/anchors | `fail` | Fallback cannot be safely anchored or accounted for. |
| Invalid processing job, corrupted input block, source extraction/preparation failure | `fail` | The block substrate is not trustworthy enough to preserve. |
| User stop/cancel | `stopped` | Preserve explicit stopped state, not controlled fallback. |

Implementation rule: controlled fallback is allowed only when the original block
payload, paragraph IDs, and target/source accounting substrate are intact. Every
fallback path must emit a user-visible artifact and must be distinguishable from a
successful translation block in logs, diagnostics, and `formatting_review.txt`.

### 3. Acceptance tolerance and meaning

Exact-zero residual on a 1140-paragraph book's back matter (notes, bibliography,
controlled-fallback blocks) is neither achievable nor the right bar. **Do:**
define the product acceptance bar — a small, explicit tolerance for back-matter /
notes / fallback edge cases, and credit controlled-fallback blocks whose content
is present. **Why before UI:** otherwise acceptance is perpetually red on good
books and the UI cannot show a meaningful pass/fail. The verdict must be
format-aware **and** flagging-untranslated: a structural element whose formatting
survives but whose text remains in the source language (for example an English
heading in a Russian translation) must surface for review instead of silently
passing as role-aware coverage. Large body-text regions left in the source
language are a translation-completeness failure, not a formatting warning. Profiles
must also use finite acceptance thresholds; sentinel/vacuum thresholds are
provisional/fail and must not report `acceptance_passed=true`. **Done:** a clean
full book passes; a book with a real structural loss (e.g. a heading rendered as
body) fails with a short, hand-checkable list; untranslated structural
headings/captions produce a visible review item; large untranslated body residue
hard-fails.

### 4. Harness ↔ production parity

Some fixes landed in the validation harness (e.g. progress-write). The UI runs the
**production** pipeline. **Do:** verify production has the same reliability and
gate guarantees (progress/state robustness; role-aware/coverage already shared via
`validation/formatting_coverage.py`). **Why before UI:** the UI must inherit the
guarantees the proofs demonstrate, not a weaker path. **Done:** a production-path
run matches a harness proof on reliability and gate basis.

### 5. Finish the current Mazzucato tail (minor)

Confirm the `list_fragment` narrowing on the saved run offline (48 -> ~3 real
standalone continuations), and close `unmapped_target` +1 by crediting the
controlled-fallback bibliography block in target accounting. Small; part of items
2–3.

## Runs Alongside: Breadth Validation

Run 2–3 more full, dissimilar books to confirm reliability + matcher + gates hold
across types. This is validation, not a blocker; it is also what exposes the
remaining stale gates for item 1. Use small no-LLM replays for diagnostics; spend
a full-book LLM run only to confirm.

## Runs Alongside: Architecture Hygiene (secondary, opportunistic)

Secondary to the five items, but tracked so it is not lost. The constraint:
decompose **only inside an iteration that is already editing the code in
question** for a functional reason — never as a standalone "big refactor" that
displaces the main task (book reliability). Every change is behaviour-preserving:
full test files green before and after.

Findings (measured 2026-06-16):

- `src/docxaicorrector/pipeline/late_phases.py` is a **3871-line** module.
  `_build_translation_quality_report` alone is **474 lines** and is edited on
  nearly every gate iteration — it grows by accretion.
- The five legacy-hygiene gates inside it (`bullet_heading`, `false_fragment`,
  `residual_bullet`, `mixed_script`, and the near-identical `role_loss`) repeat
  one hand-copied block: classify via `_apply_manual_review_or_fail` → serialize
  samples → loop-append `_build_formatting_review_item` → set `count=0`/
  `aggregate_count` on the first item when samples are capped. The same
  capping/aggregate invariant is duplicated a sixth time in
  `runtime/artifacts.py`. This duplication is the **source of the report ↔
  `formatting_review.txt` divergence bugs** fixed across the last iterations: any
  rule change must be re-applied in six places or the totals drift.

Task A — **extract `_emit_hygiene_gate`** (do within item 1, while these blocks
are open). One helper encapsulates classify + status update + capped-sample
emission + `aggregate_count`. Each of the five gates collapses to a single call;
the severity model (`reason_review`, `reason_fail`, threshold per gate) becomes a
table — single-sourced, directly serving the item-1 audit. The capping invariant
lives in one place; `runtime/artifacts.py` stays a pure consumer of
`aggregate_count`, not a second implementation. **Done:** five blocks become five
calls; no behaviour change; the six duplicate count/aggregate sites become one.

Task B — **split the quality-report cluster** out of `late_phases.py` into
`pipeline/quality_report.py` (`_build_translation_quality_report`,
`_derive_translation_quality_authority_fields`, the severity table, review-item
rendering). Larger move; **deferred** — do it opportunistically when that cluster
is next open for a functional change, not for its own sake, and not while item 2
(controlled-fallback) is the active priority.

## PDF Source Conversion — heading-detection gap & converter alternatives

Findings (measured 2026-06-18, manual review of produced DOCX vs FineReader
references in `tests/sources/book/*.docx`; experiment artifacts under
`.run/layout_parser_experiment/` and `.run/current_conversion_check/`).

**Paragraph segmentation is solved; do not swap the importer.** The earlier
catastrophe (epub→pdf Creating Wealth produced 19,557-char concatenated blobs and
~12% untranslated body) was rooted in `build_paragraph_units_from_text_spans`,
not the DOCX writer. The first-line-indent fix brought all three books to near the
FineReader reference: % of text in oversized (>2000) blocks is 1.8% (Creating
Wealth) / 0.0% / 0.0%, with text fidelity 0.99–1.0 and images preserved (34–62).
A rigorous re-bench (`measure_v2.py`, severity-aware metric `pct_chars_in_gt2000`)
confirmed no tested OSS parser beats it: Docling 66.9% in giants + 0.76 fidelity
(its default OCR path mangles a digital PDF), PyMuPDF blocks 2.2% but no roles,
pymupdf4llm 39.7% + 237 spurious headings + 8% text loss, Marker timed out.

**Converter alternatives — brief verdict.** The 2025–2026 frontier (MinerU,
olmOCR, dots.mocr, Qwen-VL-class) is VLM-based, optimised for *scanned/complex*
documents (tables, formulas, multilingual) at GPU cost and with text-fidelity
risk. Our books are *clean digital PDFs* where the only hard part is structure, so
these are overkill and a fidelity downgrade now. Keep them in reserve: MinerU for
future complex tables; olmOCR/dots.mocr only if scanned books (no text layer)
appear. FineReader-class quality is real, but FineReader's own DOCX export drops
all images (0 vs our 34–62).

**Open defect — heading/subheading detection (metrics hid it).** Manual DOCX
comparison against the FineReader references shows `current` flattens section
*subheadings* into body: Mazzucato detects **19** headings vs FineReader's **75**;
Rethinking Money **62** vs **129** — roughly half to two-thirds of real
subheadings lost. Root cause: `_looks_like_heading_candidate` keys on font *size*,
so small-caps subheadings at body size (e.g. "THE MERCANTILISTS: TRADE AND
TREASURE", "GDP: A SOCIAL CONVENTION") slip through. The same root produces
Creating Wealth's 3 residual >2000 blocks: inline list subheadings
(`Employment / Education / Child Care`, `Paper and Coins / Electronic Media`) the
detector misses and therefore merges. No experiment metric caught this —
`heading_count` alone looked fine; only heading **recall vs the FineReader
ground-truth** exposes it. **Do:** strengthen heading detection in
`logical_import.py` with case/style cues (all-caps/small-caps, standalone short
line, indentation), not size alone; measure heading-recall against the three
FineReader references and confirm by hand that subheadings stop leaking into body
and the Creating Wealth lists split. **Why before UI:** lost section hierarchy is
a visible formatting-preservation failure in the very output the UI surfaces.

## Generalization of structure detection (self-calibration over heuristics)

Empirical trigger (2026-06-18): heading detection hit the heuristic ceiling. After
suppressing dash-attribution / FIGURE-caption / location-byline false positives,
Creating Wealth precision-vs-FineReader moved only 0.083→0.091. Manual review of the
220 predicted headings shows why: (a) most ARE real subheadings the coarse FineReader
Creating Wealth export (23 labels, vs 75/129 for Mazzucato/Rethinking) simply omitted
— so that precision number is mostly a weak-reference artifact, not over-detection;
(b) the genuine residual false positives are all-caps epigraph **author names**
("VIRGIL", "MARSHALL MCLUHAN", "BARTHOLD GEORG NIEBUHR") which are **typographically
identical** to real all-caps subheadings ("THE CORE ECONOMY") and separable only by
**meaning**. No typographic hand-rule can fix that tail; more rules just overfit our
three books. This is the rule against doc-specific literals (Working Rule #7) in
spirit: absolute thresholds tuned on a tiny corpus are doc-specific in disguise.

**Principle — replace accreting absolute thresholds with PER-DOCUMENT
self-calibration.** A PDF text layer has no semantic structure; inference is
unavoidable, so the question is "our general heuristics vs a learned model", and the
generalizing move is to measure each book's own typography first, then judge relative
to it:

- **Profile-first.** Measure the document's distributions (body font mode, body
  left-margin mode, body leading, line-length distribution, body case usage) before
  classifying; judge every line **relative** to that profile, never against absolute
  constants. `median_font_size` and repeated-furniture detection already do this in
  part — extend it to all features.
- **Heading levels by clustering** style-signatures (size, weight, case, isolation),
  not thresholds: largest/most-frequent cluster = body; higher clusters = heading
  levels; small/distinct = caption. Auto-discovers each book's hierarchy.
- **Paragraph boundaries:** auto-detect which convention the book uses (first-line
  indent / inter-paragraph spacing / neither) and add **line-fill ratio** (short last
  line + return to left margin) — the near-universal, indent-independent end-of-
  paragraph signal that was missing on the epub→pdf case.
- **Small, GENERAL negative-convention set only** (dash-attribution, FIGURE/TABLE,
  page furniture). Never per-book patches.
- **Intra-document consistency:** same style-signature → same role throughout; flag
  outliers.
- **Confidence-gated escalation for the ceiling.** Where a line is genuinely
  ambiguous (all-caps author-name vs all-caps subheading), do not force a typographic
  guess — decide conservatively or escalate the low-confidence minority to a
  semantic/LM check or review. ML is a fallback for the ambiguous tail, not a
  wholesale replacement; paragraph segmentation stays homegrown (faithful, cheap).

**Validation discipline (else "universal" is self-deception):**
- Tune ONE global score/clustering on a corpus; never per-book thresholds.
- Validate on **held-out** books not used for tuning (the FineReader DOCX set is a
  ground-truth corpus; keep some books validation-only).
- Success metric = the **spread** of recall/precision across books, not the average —
  stable on any book, not excellent on three.
- The FineReader references are themselves uneven (Creating Wealth 23 vs 75/129) — use
  them as a recall guide and corpus, but confirm precision by manual false-positive
  typing, not the raw score.
- **Tripwire:** the first new book needing a fresh typographic hand-rule is the signal
  the heuristic tail is exhausted and the ambiguous case belongs to the semantic/ML
  fallback.

This is a redesign of the importer's classification core; do it incrementally under
held-out validation, not as more patches.

## Then: UI

Once items 1–4 are solid, return to UI. The first UI slice is already specified:
`docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` — surface the
residual to the user via the existing result-notice / activity surfaces plus a
human-readable `formatting_review.txt` next to the output DOCX. It depends on a
stable, meaningful residual, which items 1–3 deliver.

## Working Rules (carry forward — earned the hard way)

1. **Classify before you fix.** A failing gate may be a stale heuristic, not a
   real defect. Forensic first (which stage, real vs measurement), then act.
2. **Measured results, not "confirmed".** Record actual numbers from a run.
3. **No-LLM replay for the inner loop.** Full-book LLM runs only to confirm
   finished, unit-tested changes — never to iterate.
4. **Run full test files, not focused selectors.**
5. **Production and harness share logic.** No gate/credit that lives only in the
   proof runner.
6. **Never credit content-presence as format-presence**, and never credit a pair
   without text evidence (target⊆source by containment; no position-only maps).
7. **No document-specific literals; no verifier as a gate.**
8. **Delivery loop (orchestrator↔director↔dev-agent).** Agree the approach with the
   director FIRST → orchestrator writes a self-contained dev-agent prompt → hands it to a
   subagent → orchestrator verifies the result independently (never rubber-stamp). This
   offloads the director: they decide direction/priority, not mechanics. Every dev prompt
   carries the `=== КАК ЗАПУСКАТЬ ===` block.
9. **Verify the run EXERCISED the fix, not just the output.** Before auditing output,
   confirm the artifact was produced by the fixed code on a real input — rule out stale
   cache, a degraded fallback path, and stage-orthogonality (a fix in stage X cannot fix a
   defect born in stage Y). Audit the stage that OWNS the defect (proven by a stage-isolated
   no-LLM diagnostic), not the convenient one.
10. **No infinite polishing.** Every remaining known defect must carry an explicit
    worth-it / not-worth-it verdict with a reason; "accept and move on" is a valid,
    documented outcome. Periodically prune over-engineered/idle stages that produce no
    measurable effect on the output.

## Non-Goals (defer; not blocking UI)

- Full-book cost/time optimisation (~20–35 min/run).
- Audiobook postprocess and other separate features.
- Aggressive dead-surface deletion beyond what is proven unused.

## Lineage (archived, for reference only)

- `docs/archive/specs/POST_FC_DEVELOPMENT_ROADMAP_2026-06-14.md` — WS-1..WS-5 /
  WS-MAP execution detail and forensic findings.
- `docs/archive/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md` —
  PR-H0/PR-I history.
- `docs/archive/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md` —
  role-aware gate / matcher consolidation (FC1–FC8).
- `docs/archive/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`,
  `READER_CLEANUP_MODEL_STRATEGY_EXPERIMENTS_2026-05-30.md`,
  `SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`,
  `STRUCTURE_RECOGNITION_TO_READER_FIRST_MIGRATION_PLAN_2026-05-29.md`.
