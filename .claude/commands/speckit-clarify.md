---
description: Surface underspecified areas in the active feature spec by asking up to five targeted questions and recording the answers back into the spec (Spec Kit).
---

Read `.agents/skills/speckit-clarify/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

Before doing anything, read `.specify/memory/constitution.md`. It is BINDING for this repository. Pay particular attention to its **Spec Locations** and **Spec Format Contract** sections.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's argument text (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
