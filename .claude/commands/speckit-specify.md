---
description: Create or update a feature specification from a natural-language feature description (Spec Kit).
argument-hint: <feature description>
---

Read `.agents/skills/speckit-specify/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

Before doing anything, read `.specify/memory/constitution.md`. It is BINDING for this repository. Pay particular attention to its **Spec Locations** and **Spec Format Contract** sections — every `spec.md` here must also carry `## Non-goals` and `## Anti-regression` plus the required header block and evidence citations.

New specs are created under `specs/<NNN>-<slug>/` — never under `docs/specs/`.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's feature description (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
