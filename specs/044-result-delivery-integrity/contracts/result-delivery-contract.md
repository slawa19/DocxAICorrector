# Contract: Result Delivery and Controlled Fallback

## Controlled fallback

- Marker mode: every eligible fallback returns the canonical marker-free source substrate.
- Non-marker mode: existing source text is returned unchanged.
- Retry classification, eligibility and event identity do not change.

## Result bundle

- MUST carry one authoritative delivery disposition.
- A blocked disposition MUST include an explanation.
- Advisory/degradation notices MAY coexist and MUST NOT override disposition.

## UI

- `accepted`: normal success and normal downloads.
- `accepted_with_advisory`: normal delivery plus advisory review data.
- `blocked` with bytes: no success; prominent blocked explanation; every download explicitly diagnostic.
- `blocked` without bytes: no success and no invented download.

## Artifacts and logs

- Only accepted outcomes write `.run/ui_results/<stem>.result.*` and emit `ui_result_artifacts_saved`.
- Blocked diagnostic bytes are not accepted artifacts.
- Existing fallback events remain; returned-length metadata describes sanitized output.
