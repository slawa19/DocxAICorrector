# Контракт: оценка цены текстовых стадий

Владельцы: WP-7 (`pipeline/cost_estimate.py`, `pipeline/price_list.py`, `resources/cost_estimate_coefficients.json`),
WP-8 (UI, bundle, событие), WP-9 (отчёт раннера). Происхождение чисел — research R3.

## 1. Таблица коэффициентов `resources/cost_estimate_coefficients.json` (v1)

```json
{
  "version": "069-v1",
  "frozen_at": "2026-11-09",
  "scope": "text stages only: glossary_extraction, text_generation, literary_polish; images excluded",
  "anchor": {
    "model": "google/gemini-3.1-flash-lite-preview",
    "stage": "text_generation",
    "language_pair": "en->ru",
    "input_tokens": {"per_llm_job": 3111, "per_source_char": 1.329},
    "output_tokens": {"per_paragraph": 48.3, "per_source_char": 0.160},
    "provenance": "fit over rm_ch3 A, money_ch3 A (2026-11-08 bake-off) + RM sixth / Money fifth full runs (2026-11-08); in-sample books +-1 %, leave-one-book-out -25.9 % (Money) / +27.7 % (RM) (069-plan/cost_form_fit_jobs.out; J = LLM jobs of the prepared document)"
  },
  "glossary": {
    "model": "google/gemini-3.1-flash-lite-preview",
    "per_book": {"input_tokens": 31625, "output_tokens": 6745},
    "range": {"input_tokens": [30801, 32448], "output_tokens": [4291, 9198]},
    "provenance": "RM sixth 4 calls 32448/9198; Money fifth 3 calls 30801/4291 (2026-11-08)"
  },
  "ratios": [
    {"model": "anthropic/claude-haiku-5.5", "stage": "literary_polish", "language_pair": "ru->ru over en->ru",
     "input_vs_anchor": 1.306, "output_vs_anchor": 3.055,
     "spread": {"input": [1.248, 1.363], "output": [2.818, 3.291]},
     "provenance": "variant C / variant A text stage, rm_ch3 + money_ch3, 2026-11-08 (harness ran as edit: no document context, no glossary)"},
    {"model": "google/gemini-3.7-flash", "stage": "text_generation", "language_pair": "en->ru", "reasoning_effort": "low",
     "editorial_intensity": "conservative",
     "input_vs_anchor": 0.995, "output_vs_anchor": 1.013,
     "spread": {"input": [0.989, 1.000], "output": [1.009, 1.016]},
     "provenance": "G-low-cons / A, rm_ch3 + money_ch3, 2026-11-09"},
    {"model": "google/gemini-3.7-flash", "stage": "glossary_extraction", "language_pair": "en->ru", "reasoning_effort": "low",
     "input_vs_anchor": 0.976, "output_vs_anchor": 0.984,
     "spread": {"input": [0.952, 0.999], "output": [0.966, 1.002]},
     "provenance": "G-low-cons / A glossary stage, 2026-11-09"}
  ],
  "discount_scenarios": [
    {"model": "google/gemini-3.1-flash-lite-preview", "lower_bound_factor": [0.762, 0.790],
     "label": "empirical provider discount on full books, cause unverified (no cache fields recorded)",
     "provenance": "provider / list: RM sixth 0.790, Money fifth 0.762; chapters 0.974-0.984"}
  ]
}
```

Модели и стадии без строки `ratios` — оценка не строится (`price_unknown_models`/`coefficients_missing`), а не
подменяется якорем. Пара языков без строки — оценка строится по ближайшей строке модели и стадии с флагом
`extrapolated: true` и подписью «приблизительно».

## 2. Формулы

```
J = число LLM-заданий подготовленного документа, P = число абзацев, C = символы источника (без рисунков)
anchor_in  = 3111·J + 1.329·C
anchor_out = 48.3·P + 0.160·C
stage tokens (model m, stage s):
  text_generation / literary_polish: in = anchor_in · ratio_in(m, s);  out = anchor_out · ratio_out(m, s)
                                      (для якорной модели ratio = 1)
  glossary_extraction:                in = gl_in · ratio_in(m, glossary); out = gl_out · ratio_out(m, glossary)
upper_usd(s)  = in · price_in(m) / 1e6 + out · price_out(m) / 1e6        (прайс OpenRouter с датой)
lower_usd(s)  = upper_usd(s) · min(lower_bound_factor(m))  если у m есть сценарий скидки, иначе = upper_usd(s)
режим = сумма своих стадий; «Стандарт» = глоссарий(первый проход) + перевод(первый) + шлифовка(второй);
«Качество» = глоссарий + перевод (модель режима); single = как «Качество» с моделью single.
```

Проверка арифметики (тест WP-7, прайс 2026-11-09: flash-lite 0,25/1,50, haiku-5.5 0,10/0,50, gemini-3.7-flash
0,75/3,75, вход/выход за 1 млн): по фактическим J/P/C полных книг — «Стандарт» RM ≈ 1,22 $ верх, Money ≈ 1,05 $;
«Качество» RM ≈ 1,88 $, Money ≈ 1,81 $ (research R3; отклонение от этих чисел > 3 % — тест падает).

## 3. Прайс `pipeline/price_list.py`

- Кеш: `.run/price_list/openrouter_models.json` = `{"fetched_at": "<ISO-8601 UTC>", "source_url":
  "https://openrouter.ai/api/v1/models", "prices": {"<model_id>": {"input_per_1m": f, "output_per_1m": f}}}`. Семья —
  один файл, перезапись атомарно (`tmp` + `replace`), срока нет (последний известный прайс ценен без сети).
- Свежесть 24 ч → без сети. Иначе GET с тайм-аутом 5 с; успех → перезапись кеша; ошибка → последний кеш (дата в
  оценке) и WARNING `price_list_fetch_failed`; нет кеша → `None`.
- Цены OpenRouter — за токен строками (`pricing.prompt`, `pricing.completion`); переводятся в «за 1 млн» без
  округления. Модели не из OpenRouter (`anthropic:…`, `openai:…`) → цена неизвестна.

## 4. Сравнение с фактом

`cost_estimate_vs_actual` (см. `events.md`): `estimate_upper_usd`, `estimate_lower_usd`, `actual_usd` (сумма
`cost_usd_reported_by_provider` тех же стадий из снимка учёта), `relative_error_vs_upper = (actual − upper) / actual`,
`within_range = lower ≤ actual ≤ upper`, `run_complete`, `cost_accounting_complete`. Если `run_complete` или
`cost_accounting_complete` ложны — ошибка не считается (`null`), чтобы частичные прогоны не попадали в будущую
калибровку (Non-goals спеки: самокалибровки нет).
