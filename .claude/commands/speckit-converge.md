---
description: Assess the codebase against the feature's spec, plan, and tasks, then append any remaining unbuilt work to tasks.md so implement can finish it (Spec Kit).
---

Read `.agents/skills/speckit-converge/SKILL.md` and follow it exactly. This command is a thin wrapper: the skill file is the single source of truth. Do not improvise a different workflow.

Before doing anything, read `.specify/memory/constitution.md`. It is BINDING for this repository. Pay particular attention to its **Spec Locations** and **Spec Format Contract** sections, and to Principle VIII (evidence must be fresher than the fix) when judging what is still unbuilt.

Ignore any `.specify/extensions.yml` hook boilerplate the skill mentions: that file does not exist in this repo, so skip hook checks silently.

The user's argument text (pass through to the skill as its `$ARGUMENTS`):

$ARGUMENTS
