<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles: none redefined
Added principles: VII. Universal Rules Over Document-Specific Literals;
VIII. Evidence Must Be Fresher Than The Fix
Added sections: Spec Format Contract; Spec Locations
Removed sections: none
Rationale: the project's most-cited standing rule ("Working Rule #7", no per-book
literals) was defined only in an ARCHIVED doc
(docs/archive/specs/POST_FC_DEVELOPMENT_ROADMAP_2026-06-14.md), and mis-numbered:
the no-literals rule is item 8 there, item 7 is content-presence != format-presence.
Both are now stated here, in an active source of truth. Principle VIII records the
2026-07-09 failure where a spec asserted a live defect from a fixture older than the
commit that fixed it, stalling a branch for a week.
Templates requiring updates: .specify/templates/spec-template.md (Non-goals +
Anti-regression sections) -- applied.
Follow-up TODOs: none
-->

# DocxAICorrector Constitution

## Core Principles

### I. WSL Runtime Is The Source Of Truth

All runtime verification, dependency checks, diagnostic imports, real-document
validation, and canonical test results MUST run in the project WSL runtime unless
the task is explicitly documented as a debug-only Windows-side check. Agents MUST
detect the current shell and the actual `.venv` layout before concluding that the
environment is broken.

Rationale: this project has shell-bound validation scripts, LibreOffice/PDF
dependencies, and WSL-specific capture behavior. Treating another runtime as
equivalent produces false results.

### II. Canonical Entry Points Over Direct Runners

Tests and validation MUST use repository entry points such as
`bash scripts/test.sh ...`, `scripts/run-real-document-validation.sh`,
`scripts/run-real-document-quality-gate.sh`, existing VS Code tasks, or the
documented WSL transport command. Direct `pytest`, ad-hoc `python -c`, or Windows
Python invocations are allowed only when explicitly marked as debug-only and
MUST NOT be presented as canonical proof.

Rationale: repository scripts encode environment, dependency, and output
contracts that direct runners do not preserve.

### III. Spec Before Code For Non-Trivial Work

Feature work that changes user-visible behavior, pipeline architecture,
document-structure recognition, validation gates, artifact contracts, or
cross-module workflows MUST go through the Spec Kit sequence:

```text
Spec -> Plan -> Tasks -> Implement
```

Agents MAY skip Spec Kit for narrow bug fixes, direct diagnostic/test requests,
format-only edits, and isolated test expectation updates where expected behavior
is already unambiguous.

Rationale: this codebase has many interlocking contracts. Written specs make
assumptions, success criteria, verification commands, and scope boundaries
auditable before implementation begins.

### IV. Real-Document Evidence Before Hypotheses

For real-document validation failures, agents MUST read the latest run report,
quote `failed_checks` with `actual`, `threshold`, and overage ratio, compare the
result with the live failure inventory, and update stale inventory data before
proposing hypotheses or implementation plans.

Rationale: failure modes change between runs. Planning from memory causes work on
obsolete or non-blocking assumptions.

### V. Observable Artifacts And Logging Contracts

Features that produce UI outputs, diagnostics, validation reports, audiobook
artifacts, or benchmark artifacts MUST define expected artifact paths, log
events, retention behavior, and validation commands in the plan or quickstart.
New logging events MUST follow the project logging and artifact-retention
contract.

Rationale: this project is operated through persisted artifacts and structured
logs. A feature is incomplete if its result cannot be found, diagnosed, and
verified.

### VI. Minimal, Bounded Changes

Implementation tasks MUST be scoped to the selected spec and task. Agents MUST
avoid unrelated refactors, metadata churn, and broad rewrites unless the plan
explicitly justifies them. Existing user changes in the worktree MUST be
preserved.

Rationale: the repository is large enough that unrelated cleanup increases risk
and makes validation results harder to interpret.

### VII. Universal Rules Over Document-Specific Literals

Two standing rules, quoted verbatim from the original Working Rules list
(`docs/archive/specs/POST_FC_DEVELOPMENT_ROADMAP_2026-06-14.md`, items 7 and 8),
restated here because that document is archived and specs across the repository
cite them as binding:

7. **Content-presence != format-presence.** Never credit a source as covered
   because its text survived if its structural role was lost.
8. **No document-specific literals, no new broad substring/containment matcher
   heuristics, no verifier as a gate.**

Note on citation drift: specs across this repo say "Working Rule #7" when they
mean the no-literals rule, which is item **8** above. Both are binding; cite them
as "Constitution VII" from now on.

Detection MUST be keyed on document region, structural role, or form — never on a
word list, a signal count, or a string taken from one book. A defect for which no
general rule exists is **ACCEPTED, not patched**: rare quality tails are a
conscious outcome, not a backlog. TOC and footnotes are deliberately out of scope.

Any credit rule that subtracts from a loss/defect count MUST carry an anti-vacuum
counter-proof test showing that real body content is still counted.

Rationale: per-book tuning does not transfer to the next document, inflates the
code, and hides real losses behind plausible-looking exceptions.

### VIII. Evidence Must Be Fresher Than The Fix

A claim that a defect is LIVE MUST be supported by a fresh run or by a
deterministic test executed against current code. Saved fixtures and stored run
reports prove only what was true when they were captured. Before asserting a live
defect from a stored artifact, agents MUST compare the artifact's date against the
history of the code it describes.

A spec's acceptance criteria MUST be re-verified when the code they describe
changes. A criterion that can no longer be satisfied is a defect in the spec, not
a gap in the implementation.

Rationale: on 2026-07-09 an active spec required a detector to surface four demoted
chapters that a prior commit had already fixed. The criterion was written from
fixtures predating that commit. Work stalled for a week while agents tried to make
correct code satisfy an impossible criterion.

## Runtime Boundaries

The canonical project runtime is WSL/Debian at:

```text
/mnt/d/www/projects/2025/DocxAICorrector
```

From Windows/PowerShell agent terminals, use `wsl.exe -d Debian --cd
"D:\www\Projects\2025\DocxAICorrector" -- ...` for canonical commands. Do not
nest `wsl.exe` inside an already-WSL shell.

PDF import readiness requires LibreOffice availability inside WSL
(`soffice`/`libreoffice`) and the Writer PDF import filter.

## Spec Kit Routing

Use Spec Kit when the user asks for:

- a new feature or user-facing workflow;
- a change with unclear requirements;
- architecture, data-contract, validation-pipeline, real-document, artifact, or
  UI-workflow changes;
- a multi-step implementation where design decisions should be reviewable.

Do not use Spec Kit for:

- direct requests to run tests or diagnostics;
- tiny bug fixes with obvious expected behavior;
- formatting-only changes;
- isolated test expectation updates;
- real-document failure analysis before the required report-reading contract has
  been completed.

When using Spec Kit:

1. Start with `$speckit-specify` when no current spec exists.
2. Use `$speckit-clarify` when requirements have material ambiguity.
3. Use `$speckit-plan` to create `plan.md`, `research.md`, `data-model.md`,
   `contracts/` when applicable, and `quickstart.md`.
4. Use `$speckit-tasks` to create small, ordered, independently verifiable tasks.
5. Use `$speckit-implement` for selected tasks only, not for open-ended rewrites.

Generated specs under `specs/` are project documentation and SHOULD be committed
when they describe accepted or in-progress product behavior.

## Spec Locations

The repository has two spec homes. They are not interchangeable:

- **`specs/<NNN>-<slug>/`** — one unit of work: `spec.md`, `plan.md`, `tasks.md`
  and their Spec Kit companions. Created by `$speckit-specify`. This is where ALL
  new specs go.
- **`docs/specs/`** — long-lived documents that do not fit the one-feature-one-folder
  model: `GLOBAL_PLAN_2026-06-16.md` (the living roadmap and dated update log) and
  forward specs written before Spec Kit existed. No NEW spec is created here.

`GLOBAL_PLAN` remains the roadmap and SHOULD link to the `specs/<NNN>-…/` folders
that discharge its Remaining-Work items. `docs/ARCHIVE_INDEX.md` governs retirement
for both locations.

## Spec Format Contract

Spec Kit's stock `spec-template.md` is written for greenfield feature delivery. Most
work in this repository is refactoring and defect-driven quality engineering on a
live pipeline. Every `spec.md` in this repo MUST therefore also carry:

- **`## Non-goals`** — what this work deliberately will NOT do, with the reason.
  Without it, scope creeps into the "endless polishing" this project forbids.
- **`## Anti-regression`** — the invariants that must survive, and the counter-proof
  test for each credit/subtraction rule (Constitution VII).
- A header block: `Date`, `Status`, `Companion`/`Supersedes` cross-links, and a
  `Changelog` appended whenever a finding or criterion is corrected.
- Evidence citations as `path/file.py:line` for every claim about current behavior,
  with the date the claim was verified (Constitution VIII).

## Documentation Sources

Spec Kit artifacts MUST align with these project documents:

- `AGENTS.md`
- `README.md`
- `CONTRIBUTING.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/STARTUP_PERFORMANCE_CONTRACT.md`
- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`
- `.github/copilot-instructions.md`

If these sources conflict, `AGENTS.md` is the front-door routing contract for
agents. More specific docs govern their own domains, such as startup performance
or logging/artifact retention.

## Governance

This constitution governs Spec Kit plans, tasks, and implementation work in this
repository. Any feature plan MUST include a Constitution Check that explains how
the work preserves runtime, verification, evidence, observability, and scope
contracts.

Amendments require:

- updating this file;
- updating affected Spec Kit templates when the change impacts generated specs,
  plans, tasks, or quickstarts;
- documenting the version change in the Sync Impact Report.

Versioning follows semantic versioning:

- MAJOR for removing or redefining a principle;
- MINOR for adding principles or material governance sections;
- PATCH for wording clarifications.

**Version**: 1.1.0 | **Ratified**: 2026-07-09 | **Last Amended**: 2026-07-10
