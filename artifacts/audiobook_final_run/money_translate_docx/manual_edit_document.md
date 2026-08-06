# Что пришлось бы править руками в читаемом документе

База: доставленный `Money_Sustainability_pdf_full_heldout.docx`, 1344 абзацев, 540842 символов.
Классы — документные, не аудиокнижные: в документе формат и есть продукт.

| класс | штук | как считано |
|---|---:|---|
| потерянные заголовки | 21 | абзац с ролью `heading` в исходном реестре, чей ПЕРЕВЕДЁННЫЙ текст в доставленном `.docx` не стоит отдельным абзацем со стилем заголовка; всего заголовков в источнике 175, сохранено 154. Разбивка: {'kept_as_heading': 154, 'own_paragraph_but_body_style': 12, 'welded_into_another_paragraph': 7, 'no_translated_text': 2} |
| испорченные списки | 47 | абзац с `list_kind` в исходном реестре, чей переведённый текст в `.docx` не является элементом списка; всего элементов 227. Разбивка: {'kept_as_list': 180, 'own_paragraph_rendered_as_heading': 44, 'no_translated_text': 2, 'absent_from_document': 1} |
| непереведённые абзацы (≥40 букв) | 16 | доля кириллицы < 30 %; из них ≥60 букв — 15; доля символов 1.4816% |
| склеенные абзацы (по документу) | 41 из 47 | один абзац доставленного `.docx` целиком содержит текст двух и более переведённых абзацев; засчитаны только СОСЕДНИЕ исходные абзацы — далёкие друг от друга означают, что та же фраза стоит в книге дважды (строка оглавления и заголовок главы) |
| разорванные или пропавшие абзацы | 33 | перевод длиной ≥40 знаков не найден в документе ни отдельным абзацем, ни внутри другого |
| склеенные абзацы (вера пайплайна) | 0 | несколько исходных абзацев отображены в один целевой индекс |
| не отображённые исходные абзацы | 8 | `unmapped_source_ids` |
| целевые абзацы без источника | 4 | `unmapped_target_indexes` |
| утечки `[[DOCX_*]]` | 0 | поиск по тексту документа |
| мусор `(cid:N)` | 0 | поиск по тексту документа |
| надстрочные знаки сносок | 408 | поиск по тексту документа |
| картинок в документе | 43 | `inline_shapes` открытого `.docx`; подготовлено пайплайном 43 |

## Покрытие форматирования

- исходных абзацев: 1426
- целевых абзацев: 1342
- отображено: 1338 (93.83%)
- приёмка (`acceptance`): ПРОШЛА; провалено: []

## Роли исходных абзацев (реестр пайплайна)

| роль | абзацев |
|---|---:|
| `body` | 1023 |
| `list` | 183 |
| `heading` | 175 |
| `image` | 43 |
| `caption` | 2 |

## Потерянные заголовки — 21

- `p0056` (уровень 3, no_translated_text): «***»

- `p0064` (уровень 3, welded_into_another_paragraph, стиль в документе `Normal`): «ivo šlau s»

- `p0067` (уровень 3, welded_into_another_paragraph, стиль в документе `Body Text`): «messag e from the secretary general of the club of rome»

- `p0097` (уровень 2, own_paragraph_but_body_style, стиль в документе `Body Text`): «foreword by dennis meadows»

- `p0211` (уровень 1, own_paragraph_but_body_style, стиль в документе `Body Text`): «chapter i»

- `p0259` (уровень 1, own_paragraph_but_body_style, стиль в документе `Body Text`): «chapter ii»

- `p0323` (уровень 3, welded_into_another_paragraph, стиль в документе `Body Text`): «and so they should.”»

- `p0389` (уровень 1, own_paragraph_but_body_style, стиль в документе `Body Text`): «chapter iii»

- `p0505` (уровень 1, own_paragraph_but_body_style, стиль в документе `Body Text`): «chapter iv»

- `p0658` (уровень 1, own_paragraph_but_body_style, стиль в документе `Body Text`): «chapter v»

- `p0659` (уровень 2, own_paragraph_but_body_style, стиль в документе `Body Text`): «the effects of today’s money system on sustainability»

- `p0775` (уровень 3, no_translated_text): «***»

- `p0818` (уровень 2, own_paragraph_but_body_style, стиль в документе `Normal`): «the institutional framework of power»

- `p0962` (уровень 3, welded_into_another_paragraph, стиль в документе `Normal`): «civics at the city or regional level p.173»

- `p0964` (уровень 2, welded_into_another_paragraph, стиль в документе `Body Text`): «bus ine s s initiative s :»

- `p1345` (уровень 3, welded_into_another_paragraph, стиль в документе `Body Text`): «a: a primer about money»

- `p1352` (уровень 2, own_paragraph_but_body_style, стиль в документе `Normal`): «acknowledgements»

- `p1365` (уровень 2, own_paragraph_but_body_style, стиль в документе `Body Text`): «about the authors»

- `p1371` (уровень 2, own_paragraph_but_body_style, стиль в документе `Body Text`): «about the club of rome»

- `p1380` (уровень 2, own_paragraph_but_body_style, стиль в документе `Body Text`): «bibliography»

- `p1420` (уровень 3, welded_into_another_paragraph, стиль в документе `Body Text`): «thought leaders in design and systems thinking like russ ackoff and john seddon»

## Испорченные элементы списков — 47

- `p0220` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «identifying structural issues»

- `p0225` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «offering pragmatic solutions»

- `p0234` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the importance of timing»

- `p0270` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «dealing with the natural world»

- `p0345` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «dealing with the monetary system»

- `p0395` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the emergence of a ‘global casino’»

- `p0410` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «systemic crises: frequency, types and geographical spread»

- `p0452` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the sovereign debt squeeze»

- `p0465` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «a solution: the privatisation of everything?»

- `p0486` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «conclusion»

- `p0527` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the misclassification of economics»

- `p0537` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «complexity»

- `p0559` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the physics of complex flow networks»

- `p0578` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «lessons from nature»

- `p0590` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «application to monetary systems»

- `p0617` (unordered, absent_from_document): «• models from ecosystem research offer important and valid insights for understanding the resilience of the financial s…»

- `p0625` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «towards a structural solution?»

- `p0637` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «conclusion»

- `p0680` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «short-termism: why the future is discounted»

- `p0690` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «compulsory growth pressures: on debt and compound interest»

- `p0720` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «an unrelenting concentration of wealth: the poor vs. the super-rich»

- `p0783` (unordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «1. the input from game theory»

- `p0786` (unordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «2. evidence from neuro-imaging»

- `p0789` (unordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «3. evidence from clinical psychology»

- `p0797` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «money as an attractor»

- `p0805` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «conclusion»

- `p0825` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «semantic traps»

- `p0869` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the ‘chicago plan’»

- `p0895` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the official paradigm»

- `p0901` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the fiat currency paradigm»

- `p0920` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «comparing the two paradigms»

- `p0925` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «conclusion»

- `p0972` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «doraland: creating a ‘learning country’»

- `p0986` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «wellness tokens: overcoming market failures in the health care system»

- `p1017` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «natural savings»

- `p1046` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «c3: ‘commercial credit circuits’ for small and medium-sized enterprises»

- `p1078` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «the trc: an initiative for multinational businesses»

- `p1153` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «torekes: a city-initiated system to encourage volunteering»

- `p1208` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «civics: funding social, cultural or civic activities»

- `p1254` (ordered, own_paragraph_rendered_as_heading, стиль в документе `Heading 2`): «ecos: declaring war on climate change»

…и ещё 7. Полный список — в `mechanical_checks.json`.

## Непереведённые абзацы в документе (≥40 букв, кириллицы <30 %) — 16

- абзац 617 (`Normal`): «Time (1996). Определение и следствия взаимной причинности см. в книге Joanna Macy, The Dharma of Natural Systems: Mutual Causality in Buddhism and General Systems Theory (1991). 19 Рисунок взят из работы Goerner (1999). 20 См. Robert Ulanowicz and B. M. Hannon, ‘Life and the Production of Entropy’, »

- абзац 618 (`Body Text`): «Criticality in Non-Equilibrium Stationary States’, Journal of Physics A: Math. Gen. 36 #3 (2003), с. 631–641. 24 Eric Chaisson, ‘Non-equilibrium Thermodynamics in an Energy-Rich Universe’, в сб. A. Kleidon and R.D. Lorenz (eds), Non-»

- абзац 619 (`Body Text`): «Equilibrium Thermodynamics and the Production of Entropy: Life, Earth, and Beyond (2005), с. 21–33.»

- абзац 620 (`Body Text`): «25 См., например, Sally Goerner, Bernard Lietaer and Robert Ulanowicz, ‘Quantifying economic sustainability: Implications for free-enterprise theory, policy and practice’. Ecological Economics, 2009, Vol. 69(1), с. 76–81. 26 См., среди прочих, Robert Ulanowicz, A Third Window: Natural Foundations fo»

- абзац 622 (`Body Text`): «Jones (2010). 40 Andrew Haldane and Robert May, ‘Systemic Risk in Banking Ecosystems’, Nature, Vol. 469 (20 января 2011 г.), с. 351–355. 41 Этот рейтинг был рассчитан в 2010 году в Journal of Citation Reports Science Edition (Thomson Reuters, 2011). См. также:»

- абзац 768 (`Body Text`): «Reinhart et al. (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, Financial»

- абзац 1077 (`Body Text`): «Примечания: 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 О применении на уровне городов см., в частности, Gwendolyn Hallsmith and Bernard Lietaer, Creating Wealth: Growing Local»

- абзац 1078 (`Body Text`): «Economies with Local Currencies (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, Insurance»

- абзац 1224 (`Body Text`): «Примечания: 1 Все данные о Torekes взяты из внутреннего отчета о первом годе работы системы, подготовленного Ваутером Ван Тилло в ноябре 2011 года. См. также www.torekes.be. 2 См. Bernard Lietaer, «A World in Balance», Reflections (Journal of the Society for Organizational Learning – SoL), т. 4, № 4»

- абзац 1225 (`Body Text`): «Graham A. N. Wright, «A Critical Review of Savings Services in Africa and Elsewhere», рабочий документ (1999), 35 страниц.»

- абзац 1302 (`Normal`): «Edward Abbey: The Second Rape of the West (Chicago: Playboy Enterprises, 1975) Paul S. Adler and Seok -Woo Kwon, “Social Capital: Prospects for a New Concept”, Academy of Management Review, vol. 27 (2002), pp. 17-40 Dan Ariely, Predictably Irrational: The Hidden Forces That Shape Our Decisions (New »

- абзац 1303 (`Body Text`): «M áni Arnarson, Þorbjörn Kristjánsson, Atli Bjarnason, Harald Sverdrup and Kristín Vala Ragnarsdóttir, Icelandic Economic Collapse: A Systems Analysis Perspective on Financial, Social and World System Links (Reyk javik: Reyk javik U niversity, 2011) Christian Arnsperger, Full-Spectrum Economics: Tow»

- абзац 1304 (`Body Text`): «Anthony B. Atk inson and S. M orelli, “An Inequality Database For 25 Countries, 1911-2010”, Discussion Paper (Geneva: International Labor Office, 2010) J acques Attali, Tous ruinés dans dix ans? Dette publique: la dernière chance (Paris: Fayard, 2010).»

- абзац 1305 (`Body Text`): «Kenny Ausubel, Nature’s Operating Instructions (San Francisco: Sierra Club Book s, 2004) Sunny J . Auyang, Foundations of Complex-System Theories in Economics, Evolutionary Biology, and Statistical Physics (Cambridge: Cambridge U niversity Press, 1998) Robert Axelrod, The Evolution of Cooperation (N»

- абзац 1333 (`Heading 3`): «The Business Exchange, Шотландия ~ Community Connect Trade, США»

- абзац 1334 (`Normal`): «RES, Бельгия ~ puntoTRANSacciones, Сальвадор; Brixton Pound, Англия ~ Talente Tauschkreis Vorarlberg, Австрия; Equal Dollars, США ~ BerkShares, США; Chiemgauer, Германия ~ SOL Violette, Франция; Ithaca HOURS, США ~ Blaengarw Time Centre, Уэльс; Community Exchange System, ЮАР ~ Dane County Time Bank,»

## Утечки внутренних плейсхолдеров — 0

Ни одного.
