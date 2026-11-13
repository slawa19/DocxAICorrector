# Specification Quality Checklist: составная иллюстрация PDF приходит одной картинкой

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — оговорка: спека этого репозитория по Spec Format
  Contract обязана цитировать `file:line` текущего поведения, а правило сформулировано через величины импортёра; выбор
  библиотеки отрисовки — решение D-3, записанное как решение, а не как требование к пользователю
- [x] Focused on user value and business needs — читатель переведённой книги и слушатель аудиокниги
- [x] Written for non-technical stakeholders — разделы «Дефект», User Stories, Success Criteria
- [x] All mandatory sections completed, плюс `## Non-goals`, `## Anti-regression`, `## Changelog` (Конституция)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — три инженерных вопроса вынесены в «Открытые вопросы» с выбранным
  умолчанием, они не блокируют US1
- [x] Requirements are testable and unambiguous — каждое FR-001…FR-014 имеет тест в `tasks.md`
- [x] Success criteria are measurable — SC-001…SC-008 с числами корпуса
- [x] Success criteria are technology-agnostic — кроме SC-006 (размер в EMU) и SC-008 (имена событий): это контракты
  артефактов, которых требует Конституция V
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified — обложка, сноски под картинкой, подпись у схемы, две схемы, схема во всю страницу,
  таблица, поворот, `CropBox`, строка на краю, обломок-битмап, страница без текста
- [x] Scope is clearly bounded — Non-goals (перевод подписей, обтравка, `SMask`, Ghostscript, роль заголовка схемы…)
- [x] Dependencies and assumptions identified — `pypdfium2==5.15.2`; кэш замеров; приближение озвучиваемости

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows — US1 (P1), US2 (P2, отрезаемо)
- [x] Feature meets measurable outcomes defined in Success Criteria — симуляция производственными функциями
  (`research.md` R17)
- [x] No implementation details leak into specification — в пределах оговорки выше

## Notes

- Статус `DRAFT` требует строки о спеке 082 в разделе «Что открыто» `docs/WHERE_WE_ARE.md`; этот файл правит
  оркестратор (до этого `tests/test_spec_status_consistency.py::test_specs_with_open_work_are_listed_in_where_we_are`
  красный).
