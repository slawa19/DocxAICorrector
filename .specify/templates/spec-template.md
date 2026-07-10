# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft <!-- one of: Draft | ACTIVE forward spec | Implemented | Superseded -->

**Input**: User description: "$ARGUMENTS"

<!--
  REPO HEADER BLOCK (Spec Format Contract, Constitution VIII).
  Refactor/defect specs in this repo carry these fields in ADDITION to the Spec Kit fields above.
  Keep them as plain prose lines, NOT a table. Omit Companion/Supersedes when there is no cross-link.
-->

**Date**: [DATE this spec was last verified or touched]

**Owner surface**: [the production surface this work steers, e.g. "quality gate + acceptance verdict + formatting_review.txt writer"]

**Companion**: [cross-link to a related living spec, e.g. `docs/specs/GLOBAL_PLAN_2026-06-16.md`, and the items it discharges]

**Supersedes**: [cross-link to the spec this one replaces]

**Changelog**:

- [DATE] — [record here every correction to a finding or criterion, with the date it was made]

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Verified findings

<!--
  Required for refactoring / defect-driven specs. Evidence for every claim about CURRENT behaviour.
  This is where refactor specs in this repo live or die.
-->

Every claim about CURRENT behaviour MUST cite `path/file.py:line` and the date it was verified.
A claim that a defect is LIVE MUST come from a fresh run or a deterministic test against the current
code — never from a stored fixture or run report older than the code it describes (Constitution VIII).
Saved fixtures prove only what was true when they were captured; compare their date against the
history of the code before trusting them.

- **[Finding title]** — [what the current code actually does], `path/file.py:line` (verified [DATE]).
- **[Live defect]** — [observed wrong behaviour], reproduced by [fresh run / deterministic test] on [DATE].

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

> **Binding rule for detection/classification (Constitution VII, item 8)**: any rule that detects,
> classifies, credits, or excludes content MUST key on document region, structural role, or form —
> never on a word list, a signal count, or a literal taken from one book. Per-book literals do not
> transfer to the next document and are rejected in review.

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Non-goals

<!--
  What this work deliberately will NOT do, and why. Without it, scope creeps into "endless polishing".
-->

- [Capability or fix deliberately excluded from this work] — [why it is out of scope].
- A defect for which no GENERAL rule exists is ACCEPTED, not patched: rare quality tails are a
  conscious outcome, not a backlog item (Constitution VII). List any such accepted defects here.

## Anti-regression

<!--
  Invariants that MUST survive this change. Refactor/defect specs in this repo require this section.
-->

- [Existing behaviour or passing state that must still hold after the change, e.g. a named fixture
  or acceptance threshold that must not regress].
- Any rule that SUBTRACTS from a loss/defect count MUST ship an anti-vacuum COUNTER-PROOF test
  proving that real body content is still counted (Constitution VII). Name that test here.

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the feature description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]
