# Data Model: Result Delivery Integrity

## DeliveryDisposition

- `status`: `accepted | accepted_with_advisory | blocked`
- `explanation`: localized-message identity plus safe context; required for blocked
- `source_token`: identity of the result source

Validation: blocked cannot be inferred from bytes; accepted-with-advisory remains deliverable.

## ResultBundle

- Existing source name/token, DOCX bytes, Markdown, narration and quality-warning fields
- `delivery_disposition`: authoritative delivery state
- `result_notices`: zero or more typed facts (blocked explanation, cleanup/narration degradation, review advisory)

Relationship: one bundle has one disposition and may have multiple notices. A blocked disposition dominates presentation but does not delete other facts.

## ControlledFallbackPayload

- `source_text`: original source substrate
- `marker_mode`: whether structural markers were used
- `returned_text`: source text with only structural paragraph markers removed when marker mode is active
- `fallback_reason`: existing reason classification

Invariant: returned text is non-empty when fallback is eligible and never contains a valid internal paragraph marker.

## State transitions

`gate pass/warn → accepted disposition → normal result UI/persistence`

`gate fail + bytes → blocked disposition → blocked notice + session diagnostic download → failed outcome`

`gate fail + no bytes → blocked/failure notice → no download → failed outcome`
