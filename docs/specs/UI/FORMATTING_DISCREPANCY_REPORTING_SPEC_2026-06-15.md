# Formatting Discrepancy Reporting Spec (UI + human-readable log)

Date: 2026-06-15
Status: Forward spec, not yet implemented
Owner surface: pipeline result notice + activity feed, per-job output artifacts
Scope: how residual formatting discrepancies are surfaced so a user can review
and fix them by hand. Small, additive, tied to the current UI surfaces.

## Purpose

After a translation, the role-aware formatting gate may leave a small residual
(real role losses, unmapped paragraphs, note fragments). Today these live only
in `report.json` for engineers. This spec makes them **user-visible and
actionable**: a short UI notice + a human-readable log file next to the output
DOCX, so a non-technical user can open the DOCX and fix the few remaining spots
by hand.

This is presentation only. All discrepancy data is **already computed** (no new
analysis): `formatting_diagnostics[*].unmapped_source_residual_diagnostics`
(category + closability + samples), `mapping_text_quality` (false pairs), and the
role-aware effective counts in `translation_quality_report`.

## Plugs into existing surfaces (do not invent new ones)

- UI notice: existing `latest_result_notice = {"level", "message"}` (emit_state).
- UI feed: existing `emit_activity(runtime, message)`.
- Existing wiring to reuse/extend:
  `build_formatting_diagnostics_user_feedback()` already returns
  `(severity, activity_message, user_summary)` from diagnostics artifacts —
  extend it to also point at the log file and carry counts.
- Per-job output dir: the same dir as the user's output DOCX (`.run/job_results/<job>/`).
- Per-run human summary precedent: `*_summary.txt` (key=value). The new log is a
  separate, prose, reader-facing file (not key=value).

## What counts as a discrepancy (reuse existing classes)

| Class | Source field | User meaning |
| --- | --- | --- |
| `role_loss` (heading/list/caption -> body) | residual closability `content_survived_but_format_role_lost` + role-by-target-style | A heading/list became plain text — **needs manual fix** |
| `unmapped_source_present` | closability `target_exists_text_align_missed` / `target_occupied_*` | Text is in the DOCX but its original formatting may not have transferred — **review** |
| `unmapped_target` | `unmapped_target_indexes` classified split vs spurious | An output paragraph with no clear origin — **review** |
| `note_fragment` | residual `ABSENT` short/`ibid` bucket | Footnote/endnote fragment — usually cosmetic |
| `false_pair` | `mapping_text_quality.bad_pair_count > 0` | **Hard alarm**: wrong formatting may have been applied to a paragraph — must not ship silently |

## Severity model -> UI level

- **OK** (`level=info`): zero `role_loss`, zero `false_pair`. Notice:
  «Оформление перенесено полностью.» No log file needed (or empty log).
- **Review recommended** (`level=warn`): only `unmapped_*` / `note_fragment`,
  no `role_loss`, no `false_pair`. Notice names the count and the log path.
- **Manual fix needed** (`level=warn`, prominent): any `role_loss`.
- **Defect** (`level=error`): any `false_pair > 0`. This is the only one that
  signals possible wrong formatting applied; surface loudly, never silent.

The DOCX is always produced regardless — reporting never blocks output.

## UI notification (concise)

`latest_result_notice.message` — one line, Russian, e.g.:
- OK: `Готово. Оформление перенесено полностью (0 расхождений).`
- Review: `Готово. 16 абзацев требуют проверки оформления. Подробности: formatting_review.txt`
- Fix: `Готово, но 3 заголовка стали обычным текстом — нужна ручная правка. См. formatting_review.txt`
- Defect: `Внимание: 2 абзаца получили оформление от чужого фрагмента. См. formatting_review.txt`

Activity feed (`emit_activity`) gets the same headline plus the per-class counts.
The notice MUST name the log file by name so the user knows where to look.

## Human-readable log file

- Name: `formatting_review.txt` (or `<output_basename>.formatting_review.txt`),
  written into the **same folder as the output DOCX**.
- Always written when severity != OK; on OK, write a one-line "no issues" file so
  its presence is predictable.
- Plain prose, Russian, no internal ids/jargon in the body. Ordered by document
  position so the user can walk the DOCX top to bottom.

### Format

```
Проверка оформления — <имя книги>
Дата: <ISO>
Итог: <0 критичных / 3 на правку / 16 на проверку>
Что значат пометки: [ПРАВКА] — нужно поправить вручную; [ПРОВЕРКА] — желательно
глянуть; [КРИТ] — возможно применено чужое оформление.

----------------------------------------------------------------------
[ПРАВКА] Заголовок стал обычным текстом
  Где (примерно): после абзаца «…the local activities are run by a comm…»
  Оригинал:  «Глава десятая»  (должен быть заголовок главы)
  В выводе:  обычный абзац стиля Body Text
  Как поправить: выделить строку и применить стиль «Заголовок 2».

[ПРОВЕРКА] Абзац без явного соответствия оригиналу
  В выводе (стиль Normal): «BerkShares — это местная валюта региона…»
  Похоже на: разрыв/перенос при переводе. Текст на месте, проверьте стиль.

[КРИТ] Возможно чужое оформление
  Абзац: «…www imf org/external/pubs…»
  Применён стиль от другого фрагмента — проверьте вручную.
----------------------------------------------------------------------
Всего: ПРАВКА 3 · ПРОВЕРКА 16 · КРИТ 0
```

Each entry carries: the **class label**, an **anchor** the user can locate in the
DOCX (preceding text snippet or the paragraph text itself — never an internal
paragraph id), the **original vs output** description, and a **concrete manual
action** (which Word style to apply / what to check). Snippets are truncated to a
readable length.

## Data source & writer placement

- A single writer turns `report.json` residual diagnostics into both the notice
  string and `formatting_review.txt`. It runs at finalize, after the role-aware
  gate result is known, before/with the user-facing result emission.
- It reuses the role-by-target-style check (the same logic that distinguishes
  real role loss from credited body dissolution) so the log never flags a
  credited/legitimate case as a defect.
- Anchors come from the residual `samples` (source text preview + neighbor
  context) already captured in diagnostics.

## Non-goals

- No new discrepancy analysis — presentation of existing diagnostics only.
- No blocking of DOCX output on discrepancies.
- No internal ids, strategy names, or basis labels in the user-facing body
  (they may stay in `report.json` for engineers).
- No auto-fixing — the user fixes by hand; the log only guides.

## Future hooks

- When the role-aware gate passes clean, the OK file makes "nothing to fix"
  explicit (avoids the "is it green because empty?" doubt we hit earlier).
- The same `formatting_review.txt` generalises to every book unchanged: it reads
  the same diagnostics that any run produces, so no per-document work is needed.
- A later UI iteration can render `formatting_review.txt` inline (clickable
  anchors) without changing the writer.
