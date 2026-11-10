# Контракт: группа результата, состояние, bundle, экран (спека 073, FR-008)

Всё — продолжение контрактов 072 (`specs/072-narration-docx-pdf/contracts/result-group.md`, `state-bundle.md`): новых
ключей состояния нет, новых событий доставки нет, новый член группы один.

## 1. Файл на диске (`.run/ui_results/`)

| Файл | Ключ результата писателя | Условие | Содержимое |
|---|---|---|---|
| `<основа>.tts.minimax.txt` (основа уже кончается на `.result`, `runtime/artifacts.py:163-169`) | `tts_minimax_path` | `narration_minimax_text` непуст | текст `.tts.txt` с метками `<#x#>` (FR-007), UTF-8, LF |

- Писатель: `write_ui_result_artifacts(..., narration_minimax_text: str | None = None)` (`runtime/artifacts.py:366-382`);
  протокол `ResultArtifactWriter` (`pipeline/contracts.py:151-166`) — тот же аргумент последним, `None` по умолчанию.
- Член того же `_atomic_write_group` (`runtime/artifacts.py:440`): сбой записи откатывает всю группу.
- Перевод и редактура аргумент не передают — группа побайтно прежняя.
- Хранение: `_UI_RESULT_GROUP_SUFFIXES` (`runtime/artifact_retention.py:90-99`) += `.result.tts.minimax.txt`.

## 2. Состояние и bundle

| Ключ | Изменение |
|---|---|
| `latest_narration_exports` (`processing/processing_runtime.py:182`) | словарь получает пятый ключ `minimax_text: str \| None` (`data-model.md` §8); пишется в том же `emit_state`, что 072 (`pipeline/late_phases.py:1399-1419`) |
| `narration_exports` в bundle (`build_result_bundle`, `:1603-1654`; `_normalize_narration_exports`, `:1657-1675`) | нормализация пропускает `minimax_text` (не-`str` и `""` → `None`); прочие ключи как в 072 |

Правило пары bundle (`:1759-1765`), сброс (`runtime/state.py:611`, `:739`; `processing/processing_service.py:380`), Stop до
публикации, старый bundle — без изменений: тот же ключ.

## 3. Экран аудиокниги (`ui/_ui.py:_render_audiobook_downloads`, `:1111-1196`)

Строка «Текст для озвучки» — в порядке: DOCX (основная), PDF, TXT, **MiniMax**; строка «Для проверки» — без изменений.

| Кнопка | Имя файла | MIME | Метка (ru / en) | Тип |
|---|---|---|---|---|
| MiniMax | `<основа исходника>.tts.minimax.txt` (`_build_narration_minimax_filename`, рядом с `:92-101`) | `text/plain` | `result.narration_minimax` — «TXT для MiniMax» / «TXT for MiniMax»; заблокированная выдача — `result.blocked_download_narration_minimax` | `secondary` |

- `minimax_text is None` (не собран, старый bundle) → кнопки нет, строки причины нет (причина — в событии
  `audiobook_narration_minimax_failed`).
- Все кнопки — `width="stretch"`, `on_click="ignore"`, как в 072; `st.columns(len(narration_buttons))` (`:1163-1164`).
- Перевод и редактура — экран побайтно прежний (характеристика пакета).
- Ключи локали — в `ui/locales/ru.json` и `en.json` одновременно.
