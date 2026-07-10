# Spec Kit Workflow For DocxAICorrector

This repository uses Spec Kit for non-trivial feature design and implementation.
Spec Kit is not required for every small fix. Use it when a change needs durable
requirements, design decisions, validation commands, or cross-module planning.

## What Is Committed

Commit these files:

- `.specify/`
- `.agents/skills/speckit-*`
- `specs/<NNN-feature>/` for accepted or in-progress feature work

Do not commit unrelated future `.agents/` state unless it is reviewed for
secrets and useful to the team.

## Agent Entry Points

Use these prompts with Codex:

```text
$speckit-specify
<feature request>
```

```text
$speckit-plan
Use AGENTS.md, README.md, CONTRIBUTING.md, and the docs/ contracts as project
context. Preserve canonical WSL verification commands.
```

```text
$speckit-tasks
Create small independently verifiable tasks. Include exact file paths and
canonical validation commands.
```

```text
$speckit-implement
Implement only the next selected task. Do not refactor unrelated files.
```

Optional quality steps:

```text
$speckit-clarify
```

Use before planning when the feature has meaningful ambiguity.

```text
$speckit-analyze
```

Use after tasks are generated to check consistency between spec, plan, and tasks.

```text
$speckit-converge
```

Use after partial implementation to append remaining work back into `tasks.md`.

## Recommended Feature Flow

1. Create a feature spec.
2. Resolve clarifications before planning.
3. Generate the implementation plan and quickstart validation.
4. Generate tasks.
5. Implement one task or one story-sized batch.
6. Verify with canonical commands.
7. Update task checkboxes and summarize changed files.

## Existing Context To Reuse

Before generating a plan, agents should read only the relevant context:

- `AGENTS.md` for routing, runtime, and verification rules.
- `README.md` for product behavior and repository shape.
- `CONTRIBUTING.md` for development and PR workflow.
- `docs/AI_AGENT_DEVELOPMENT_RULES.md` for protected engineering practices.
- `docs/WORKFLOW_AND_IMAGE_MODES.md` for workflow and image-mode behavior.
- `docs/STARTUP_PERFORMANCE_CONTRACT.md` when startup or app initialization is affected.
- `docs/LOGGING_AND_ARTIFACT_RETENTION.md` when logs or artifacts are affected.
- Existing specs under `docs/specs/` and `specs/` when the feature touches the same domain.

Do not load every document by default. Pick the smallest set that covers the
feature, then cite the chosen files in `plan.md`.

## When To Skip Spec Kit

Skip Spec Kit and work directly when the task is:

- a direct test or diagnostic run;
- a one-line or narrow bug fix with clear expected behavior;
- formatting-only cleanup;
- a small documentation wording edit;
- a real-document failure investigation that has not yet completed the mandatory
  latest-report analysis from `AGENTS.md`.

## Verification Standard

Plans and tasks must include canonical proof commands, for example:

```bash
bash scripts/test.sh tests/test_file.py::test_name -vv -x
```

For structural diagnostics:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <document_profile_id> --run-profile-id <run_profile_id>
```

For final proof in VS Code, prefer existing user-visible tasks when a matching
task exists.

Always run or request `git diff --check` after text or whitespace-sensitive
changes.
