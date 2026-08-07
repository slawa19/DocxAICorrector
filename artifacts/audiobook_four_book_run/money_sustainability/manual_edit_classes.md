# Счёт ручной правки после прогона — по классам (money_sustainability)

База: 1300 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1318 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 75 | 5.8% |
| `year_spelled_out_for_tts_not_a_defect` | 28 | 2.2% |
| `year_dropped_with_reference_apparatus` | 20 | 1.5% |
| `truncated_sentence` | 12 | 0.9% |
| `paragraph_emptied` | 11 | 0.8% |
| `stray_markup_or_ocr_garbage` | 4 | 0.3% |
| `url_left_in` | 3 | 0.2% |
| `bullet_marker_left_in` | 2 | 0.2% |
| `malformed_or_disallowed_tag` | 1 | 0.1% |
| `absent_from_artifact` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 75

**`narration#8`, исходный абзац:**

> —

**в озвучке:**

> [serious] Отчет Римского клуба — Европейское отделение

**`narration#10`, исходный абзац:**

> —

**в озвучке:**

> [serious] Финансовый надзор и Всемирная бизнес-академия

**`narration#11`, исходный абзац:**

> —

**в озвучке:**

> Бернар Литар, Кристиан Амспергер, Салли Гёрнер, Стефан Бруннхубер

---

### `year_spelled_out_for_tts_not_a_defect` — 28

**`p0184`, исходный абзац:**

> It is often assumed that the relationship between the banking system and governments has remained unchanged for centuries. A case study of France shows that this is not necessarily the case. Indeed, since 1973, the French government has been forced to borrow exclusively from the private sector and therefore pay interest on new debt. Without this change, French government debt would now be at 8.6% of GDP instead of the current 78%. Furthermore, the Maastricht and Lisbon Treaties have generalised this same process to all signatory countries.

**в озвучке:**

> Часто предполагают, что отношения между банковской системой и правительствами оставались неизменными на протяжении столетий. Однако пример Франции показывает, что это не так. С тысяча девятьсот семьдесят третьего года французское правительство было вынуждено занимать средства исключительно в частном секторе и, следовательно, платить проценты по новому долгу. Без этого изменения государственный долг Франции составлял бы сейчас восемь целых и шесть десятых процента от валового внутреннего продукта, а не текущие семьдесят восемь процентов. Более того, Маастрихтский и Лиссабонский договоры распространили этот процесс на все страны-участницы.

**`p0186`, исходный абзац:**

> The ‘official story’ is that governments, just like any household, must raise the money needed to pay for their activities. This is done either through income (by taxation) or through debt (by issuing bonds). In this story, banks simply act as intermediaries collecting deposits and lending parts of that money to creditworthy individuals and institutions, including governments. However, since 1971, when fiat currency – that is, money created out of nothing – became universal, this story has been a complete fiction.

**в озвучке:**

> «Официальная версия» гласит, что правительства, как и любые домохозяйства, должны изыскивать средства для оплаты своей деятельности. Это делается либо через доходы от налогов, либо через долг путем выпуска облигаций. В этой версии банки просто выступают посредниками: они собирают депозиты и одалживают часть этих денег кредитоспособным лицам и организациям, включая правительства. Однако с тысяча девятьсот семьдесят первого года, когда фиатная валюта — то есть деньги, созданные из ничего, — стала повсеместной, эта история превратилась в полную фикцию.

**`p0199`, исходный абзац:**

> • *Torekes*: a city-based initiative to encourage volunteering while promoting green behaviour and social cohesion in a poor neighbourhood. It has been running since 2010 in the city of Ghent, Belgium.

**в озвучке:**

> • Торекес: городская инициатива, поощряющая волонтерство, экологичное поведение и социальную сплоченность в неблагополучных районах. Она работает с две тысячи десятого года в бельгийском городе Гент.

---

### `year_dropped_with_reference_apparatus` — 20

**`p0375`, исходный абзац:**

> He defines a scientific paradigm as an epistemological pattern, a mental framework that specifies a series of what’s and how-to’s: *what* is to be observed and scrutinised, and by implication what is to be overlooked; the kind of *questions* that are supposed to be asked or ignored; *how* these questions are to be structured; *how* the results of scientific investigations should be interpreted. A paradigm, according to Kuhn, adjusts over time to the everyday requirements of what he calls ‘normal science’, i.e., the business of tinkering with models and making them fit empirical data as well as possible, for as long as possible. The period of normal science is sometimes ended, more or less abruptly, by a ‘scientific revolution’. 2 Christian Arnsperger, *Full-Spectrum Economics: Towards an Inclusive and Emancipatory Social Science* (2010a), p.25. 3 In opposition to the Traditional Economic

**в озвучке:**

> [thoughtful] Он определяет научную парадигму как эпистемологическую модель, своего рода ментальную рамку. Она задает набор правил: что именно подлежит наблюдению и изучению, а что, по умолчанию, следует игнорировать; какие вопросы стоит задавать, а какие — пропускать; как эти вопросы должны быть структурированы и как следует интерпретировать результаты научных исследований. По мнению Куна, парадигма со временем приспосабливается к повседневным нуждам того, что он называет «нормальной наукой». Это процесс постоянной доработки моделей, чтобы они как можно дольше и как можно точнее соответствовали эмпирическим данным. Период нормальной науки иногда завершается, более или менее внезапно, «научной революцией».

**`p0376`, исходный абзац:**

> Gowdy & Jon D. Erikson (2005). For a general but exhaustive treatment, see e.g. Molly Scott Cato (2009) and Herman Daly & Joshua Farley (2011). Ecological economics should not be confused with ‘environmental economics’, which was initially part of the Traditional Economics approach and has been a driving force behind the OECD approach shown in Figure 2.2. 9 In this statement, we extend ecological economics into what might be called ‘political ecology’, since traditionally ecological economists emphasise more the embeddedness of the economic within the environmental, and less its embeddedness within the social. However, political ecology and ecological economics are very closely linked, and most ecological economists will have no objection to our graph here.

**в озвучке:**

> Гоуди и Эриксон в 2005 году. Для более общего, но исчерпывающего обзора можно обратиться к работам Молли Скотт Като, а также Германа Дейли и Джошуа Фарли. Экологическую экономику не стоит путать с «экономикой окружающей среды». Последняя изначально была частью традиционного экономического подхода и послужила движущей силой для стратегии ОЭСР, представленной на схеме. В этом изложении мы расширяем рамки экологической экономики до того, что можно назвать «политической экологией». Традиционно экологические экономисты делают упор на включенность экономики в окружающую среду, меньше внимания уделяя ее связи с обществом. Тем не менее политическая экология и экологическая экономика тесно взаимосвязаны, и большинство специалистов в этой области согласятся с нашей схемой.

**`p0377`, исходный абзац:**

> 10 See, amongst others, Ken Wilber, *Sex, Ecology, Spirituality: The Spirit of Evolution* (1995). 11 An approach that has led mainstream economists to reason as if, with good enough economic and ‘human’ capital in the form of extremely high-grade technologies and an extremely well-trained workforce, the whole world’s production might be manufactured with virtually no natural capital, e.g., with just a few grains of matter… 12 This idea – and especially the notion of ‘ecological debt’ – is a major theme in the influential book of Tim Jackson, *Prosperity*

**в озвучке:**

> [curious] Это подход, который заставил мейнстримных экономистов рассуждать так, будто при наличии достаточного капитала — как экономического, так и «человеческого» в виде высококлассных технологий и отлично обученных кадров — мировое производство можно поддерживать практически без использования природного капитала. Будто достаточно лишь нескольких крупиц материи. Эта идея, и особенно понятие «экологического долга», является одной из центральных тем в влиятельной книге Тима Джексона.

---

### `truncated_sentence` — 12

**`narration#280`, исходный абзац:**

> —

**в озвучке:**

> — Декларация 1700 ведущих ученых из 70 стран, включая 102 нобелевских лауреата в области науки, при поддержке научных академий США, Великобритании, Бразилии, Канады, Китая,

**`narration#339`, исходный абзац:**

> —

**в озвучке:**

> Ее название — «Процветание без роста: экономика для конечной планеты», вышедшая в 2009 году. Николас Джорджеску-Реген, годы жизни с 1906 по 1994, родился в Румынии, но основную часть своей академической карьеры провел в Университете Вандербильта в

**`narration#760`, исходный абзац:**

> —

**в озвучке:**

> Большинство учебников экономики определяют деньги через три функции: мера стоимости, средство обращения и средство накопления. Но это лишь описание того, что деньги делают, а не того, чем они являются на самом деле. Из-за такой популярности функционального подхода природа денег почти не исследуется. Мы же предлагаем свое рабочее определение: деньги — это соглашение внутри сообщества об использовании некоего стандартизированного объекта в качестве средства обмена. В отличие от традиционного подхода, если соглашение перестает работать, его можно изменить. Можно представить, что разные инструменты способны выполнять лишь некоторые из этих функций, а не все три сразу. Существуют и другие языковые ловушки. Когда кредит берет частное лицо или бизнес, мы используем слово «кредит». Но когда речь заходит о государстве, всегда говорят «долг». Хотя по сути это одни и те же процессы. Слово «кредит» 

---

### `paragraph_emptied` — 11

**`p0495`, исходный абзац:**

> Footnotes 1 Source:Speech made in New York 25 October 2010 See:*www.qfinance.com ~ bit.ly/TPlink17* 2 ‘The Global Currency Game is Exploding’, *The Wall Street Journal*, 26 September 2007, pp.C1 and C3.

**в озвучке:**

> 

**`p0496`, исходный абзац:**

> 3 *The CIA Factbook 2012* estimates global GDP at purchasing power parity at US$78.98 trillion. 4 John Maynard Keynes, *The General Theory of Employment, Interest and Money* (1936), p.159. 5 Ludwig von Mises, *Human Action: A Treatise on Economics* (1949). 6 *The Financial Crisis Inquiry Report: Final Report of the National Commission of the Financial and Economic Crisis in the United*

**в озвучке:**

> 

**`p0497`, исходный абзац:**

> *States* (2011). 7 Andrew Ross Sorkin, *Too Big to Fail* (2010). 8 Anton R. Valukas, Lehman Brothers Inc. Chapter 11 Proceedings Examiner’s Report (2010), downloadable from *http://lehmanreport.jenner.com ~ bit.ly/TPlink18* (visited: 8 January 2012). 9 ‘Restoring Ireland’s Credit by Reducing Uncertainty’, Remarks by Mr Patrick Honohan, Governor of the Central Bank of Ireland, at the Institute of International and European Affairs, Dublin, 7 January 2011, downloadable from *www.bis.org* ~ *bit.ly/TPlink19* (visited: 8 January 2012). 10 Máni Arnarson, Þorbjörn Kristjánsson, Atli Bjarnason, Harald Sverdrup and Kristín Vala Ragnarsdóttir*, Icelandic Economic*

**в озвучке:**

> 

---

### `stray_markup_or_ocr_garbage` — 4

**`narration#25`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#710`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#1183`, исходный абзац:**

> —

**в озвучке:**

> * *

---

### `url_left_in` — 3

**`narration#819`, исходный абзац:**

> —

**в озвучке:**

> Четвертую причину можно назвать «политическим реализмом». Любая версия «Чикагского плана» встретит яростное сопротивление банковской системы, так как она угрожает и ее власти, и ее бизнес-модели. Даже после краха 2007–2008 годов, вызванного чрезмерными аппетитами банков, или в разгар Великой депрессии 1930-х годов, банковское лобби успешно блокировало любые значимые изменения. Вспомните: в 2010 году на каждого избранного чиновника в Вашингтоне приходилось по три высокопоставленных лоббиста, работающих на банковскую систему. Томас Фридман писал в «Нью-Йорк таймс»: «Сегодня наш Конгресс — это площадка для узаконенного взяточничества. Одна из групп по защите прав потребителей, используя данные портала Opensecrets.org, подсчитала, что индустрия финансовых услуг, включая сектор недвижимости, потратила на предвыборные кампании федерального уровня 2,3 миллиарда долларов в период с 1990 по 2010 

**`narration#1245`, исходный абзац:**

> —

**в озвучке:**

> На сайте «money-sustainability.net», который является частью этого отчета, мы приглашаем всех желающих высказаться по затронутым вопросам. Количество тем, заслуживающих внимания и обсуждения, бесконечно. Они так же богаты, как сама жизнь. Вот лишь четыре примера тем, достойных внимания:

**`narration#1274`, исходный абзац:**

> —

**в озвучке:**

> Джин Хьюстон, «Жизненная сила: Психоисторическое восстановление самости» (1993), стр. 13. 5. Тойнби (1939). Сокращенную версию см. в работе Тойнби (1960). 6. Джаред Даймонд (2005). 7. Видео о саммите доступно по ссылке. Анализ интеллектуального содержания доступен на сайте Dandelion Salad. 8. Томас Фридман, «Слышали историю про банкиров?». 9. Эти два аспекта — рост населения и его старение — не обязательно исключают друг друга. Население планеты в целом все еще активно растет, в то время как в так называемом развитом мире «волна старения» уже близка или даже началась. 10. См. Лиетар (2001), стр. 17–30. 11. Эдвард О. Уилсон, «Будущее жизни» (2002). 12. См. сайт Mises.org, стр. 133–134. 13. См. сайт Европейской комиссии. 14. Документация по аргументам в пользу стратегии регионального развития представлена в работах Кеннеди и Лиетара (2004), Лиетара и

---

### `bullet_marker_left_in` — 2

**`narration#1183`, исходный абзац:**

> —

**в озвучке:**

> * *

**`narration#1199`, исходный абзац:**

> —

**в озвучке:**

> * *

---

### `malformed_or_disallowed_tag` — 1

**`narration#424`, исходный абзац:**

> —

**в озвучке:**

> «Существует идеальный механизм [для правительств] по привлечению средств: монетизация существующих активов. Эти активы чрезвычайно ценны. В 2008 году общая стоимость основных средств правительства США на федеральном, штатном и местном уровнях составляла 9,3 триллиона долларов. Из них 1,9 триллиона принадлежат федеральному правительству, а 7,4 триллиона находятся на уровне штатов. Если предположить, что федеральное правительство не будет продавать военно-морской флот, а муниципалитеты — свои школы, остается еще огромное количество активов, которые можно реализовать. Например, стоимость всех шоссе и дорог, принадлежащих штатам и муниципалитетам, составляет 2,4 триллиона долларов. На местном уровне и уровне штатов есть активы канализационных систем на 550 миллиардов долларов и водоснабжения еще на 400 миллиардов. В секторе недвижимости федеральное правительство, власти штатов и муниципалите

---

### `absent_from_artifact` — 1

**`p0957`, исходный абзац:**

> ## **NGO Initiative s :**

**в озвучке:**

> None

---

## Новый класс, которого не было в таксономии 2026-08-04: `back_matter_narrated`

На Money & Sustainability этот дефект увидеть было нельзя — там аппарат книги
выбрасывался целиком, поэтому в классах первого прогона его нет. На корпусе из четырёх
книг он виден, поэтому считается здесь.

**Как считается.** По списку блоков продакшена (`blocks.json`) ищется ПЕРВЫЙ блок,
чей заголовок называет аппарат книги (`Notes` / `Index` / `Bibliography` / `References` /
`Endnotes`). Всё от этого блока и до конца документа считается аппаратом. Затем по парам
«исходник → озвучка» считается, сколько из этих абзацев ДОШЛО до артефакта озвучки.
`Acknowledgements` и «Об авторе» аппаратом НЕ считаются: это авторская проза, её могут
хотеть услышать.

- граница: блок `323` — `## Bibliography`
- блоков аппарата: 15, из них исключено из озвучки: 12
- **абзацев аппарата, попавших в озвучку: 8**
- **символов: 854**

Примеры (цитаты из артефакта):

**`p1416`:**

> [serious] ## Об издательстве Triarchy Press

**`p1417`:**

> ### Хорошие книги и яркие идеи об организациях и обществе

**`p1418`:**

> [thoughtful] Triarchy Press — это небольшое независимое издательство. Мы публикуем лучшие новые идеи об устройстве организаций и общества, а также рассказываем о том, как применять эти знания на практике.
