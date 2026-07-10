---
description: Run the implementation-planning workflow to generate design artifacts (plan.md, research.md, data-model.md, contracts, quickstart) for the active feature (Spec Kit).
argument-hint: [tech / implementation notes]
---

Read `.agents/skills/speckit-plan/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

Before doing anything, read `.specify/memory/constitution.md`. It is BINDING for this repository. Pay particular attention to its **Spec Locations** and **Spec Format Contract** sections, and include the required Constitution Check in the plan.

Plan artifacts live alongside their spec under `specs/<NNN>-<slug>/` — never under `docs/specs/`.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's argument text (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
