---
description: Create or update the project constitution and keep dependent Spec Kit templates in sync (Spec Kit).
argument-hint: [principles or amendment description]
---

Read `.agents/skills/speckit-constitution/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

The file you are editing is `.specify/memory/constitution.md`. Read it first: it is BINDING and already amended (currently v1.1.0). Preserve its existing principles, its **Spec Locations** and **Spec Format Contract** sections, and its Sync Impact Report / versioning discipline unless the user explicitly asks to change them.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's argument text (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
