---
description: Generate a dependency-ordered tasks.md for the active feature from its available design artifacts (Spec Kit).
---

Read `.agents/skills/speckit-tasks/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

Before doing anything, read `.specify/memory/constitution.md`. It is BINDING for this repository. Pay particular attention to its **Spec Locations** and **Spec Format Contract** sections.

The `tasks.md` lives alongside its spec under `specs/<NNN>-<slug>/` — never under `docs/specs/`.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's argument text (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
