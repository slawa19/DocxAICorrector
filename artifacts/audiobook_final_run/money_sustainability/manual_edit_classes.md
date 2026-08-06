# Счёт ручной правки после прогона — по классам (money_sustainability)

База: 1299 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1318 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 76 | 5.9% |
| `year_dropped_with_reference_apparatus` | 24 | 1.8% |
| `year_spelled_out_for_tts_not_a_defect` | 23 | 1.8% |
| `truncated_sentence` | 11 | 0.8% |
| `year_lost` | 7 | 0.5% |
| `paragraph_emptied` | 6 | 0.5% |
| `url_left_in` | 5 | 0.4% |
| `stray_markup_or_ocr_garbage` | 4 | 0.3% |
| `bullet_marker_left_in` | 2 | 0.2% |
| `absent_from_artifact` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 76

**`narration#3`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Деньги и устойчивое развитие

**`narration#8`, исходный абзац:**

> —

**в озвучке:**

> [serious] Доклад Римского клуба: Европейское отделение

**`narration#10`, исходный абзац:**

> —

**в озвучке:**

> Финансовый надзор и Всемирная бизнес-академия

---

### `year_dropped_with_reference_apparatus` — 24

**`p0375`, исходный абзац:**

> He defines a scientific paradigm as an epistemological pattern, a mental framework that specifies a series of what’s and how-to’s: *what* is to be observed and scrutinised, and by implication what is to be overlooked; the kind of *questions* that are supposed to be asked or ignored; *how* these questions are to be structured; *how* the results of scientific investigations should be interpreted. A paradigm, according to Kuhn, adjusts over time to the everyday requirements of what he calls ‘normal science’, i.e., the business of tinkering with models and making them fit empirical data as well as possible, for as long as possible. The period of normal science is sometimes ended, more or less abruptly, by a ‘scientific revolution’. 2 Christian Arnsperger, *Full-Spectrum Economics: Towards an Inclusive and Emancipatory Social Science* (2010a), p.25. 3 In opposition to the Traditional Economic

**в озвучке:**

> [thoughtful] Он определяет научную парадигму как эпистемологическую модель, своего рода ментальную рамку. Она задает набор правил: что именно нужно наблюдать и изучать, а что, соответственно, можно упустить из виду; какие вопросы следует задавать, а какие — игнорировать; как эти вопросы должны быть структурированы и как следует интерпретировать результаты научных исследований. По мнению Куна, парадигма со временем подстраивается под повседневные нужды того, что он называет «нормальной наукой». Это процесс доработки моделей, чтобы они как можно дольше и точнее соответствовали эмпирическим данным. Период нормальной науки иногда завершается — более или менее внезапно — «научной революцией».

**`p0376`, исходный абзац:**

> Gowdy & Jon D. Erikson (2005). For a general but exhaustive treatment, see e.g. Molly Scott Cato (2009) and Herman Daly & Joshua Farley (2011). Ecological economics should not be confused with ‘environmental economics’, which was initially part of the Traditional Economics approach and has been a driving force behind the OECD approach shown in Figure 2.2. 9 In this statement, we extend ecological economics into what might be called ‘political ecology’, since traditionally ecological economists emphasise more the embeddedness of the economic within the environmental, and less its embeddedness within the social. However, political ecology and ecological economics are very closely linked, and most ecological economists will have no objection to our graph here.

**в озвучке:**

> Работы Гоуди и Эриксона — хороший тому пример. Для более общего, но исчерпывающего обзора можно обратиться к трудам Молли Скотт Кейто, а также Германа Дейли и Джошуа Фарли. Экологическую экономику не стоит путать с «экономикой окружающей среды». Последняя изначально была частью традиционного экономического подхода и стала движущей силой стратегии ОЭСР, представленной на схеме. В этом изложении мы расширяем рамки экологической экономики до того, что можно назвать «политической экологией». Традиционно экологические экономисты делают акцент на встроенности экономики в природную среду, а не в социальную систему. Однако политическая экология и экологическая экономика тесно связаны, и у большинства специалистов в этой области наше графическое представление не вызовет возражений.

**`p0377`, исходный абзац:**

> 10 See, amongst others, Ken Wilber, *Sex, Ecology, Spirituality: The Spirit of Evolution* (1995). 11 An approach that has led mainstream economists to reason as if, with good enough economic and ‘human’ capital in the form of extremely high-grade technologies and an extremely well-trained workforce, the whole world’s production might be manufactured with virtually no natural capital, e.g., with just a few grains of matter… 12 This idea – and especially the notion of ‘ecological debt’ – is a major theme in the influential book of Tim Jackson, *Prosperity*

**в озвучке:**

> [curious] Подход, который заставил мейнстримных экономистов рассуждать так, будто при наличии достаточного капитала — как экономического, так и «человеческого» в виде высокотехнологичных инструментов и квалифицированных кадров — мировое производство можно поддерживать практически без использования природного капитала, обходясь лишь крупицами материи. Эта идея, особенно концепция «экологического долга», является одной из центральных тем в влиятельной книге Тима Джексона «Процветание без роста: экономика для конечной планеты».

---

### `year_spelled_out_for_tts_not_a_defect` — 23

**`p0184`, исходный абзац:**

> It is often assumed that the relationship between the banking system and governments has remained unchanged for centuries. A case study of France shows that this is not necessarily the case. Indeed, since 1973, the French government has been forced to borrow exclusively from the private sector and therefore pay interest on new debt. Without this change, French government debt would now be at 8.6% of GDP instead of the current 78%. Furthermore, the Maastricht and Lisbon Treaties have generalised this same process to all signatory countries.

**в озвучке:**

> Часто предполагают, что отношения между банковской системой и правительствами оставались неизменными на протяжении веков. Однако пример Франции показывает, что это не всегда так. С тысяча девятьсот семьдесят третьего года французское правительство было вынуждено занимать средства исключительно в частном секторе и, следовательно, выплачивать проценты по новому долгу. Без этого изменения государственный долг Франции сейчас составлял бы восемь целых и шесть десятых процента от валового внутреннего продукта, а не текущие семьдесят восемь процентов. Кроме того, Маастрихтский и Лиссабонский договоры распространили этот процесс на все страны-участницы.

**`p0186`, исходный абзац:**

> The ‘official story’ is that governments, just like any household, must raise the money needed to pay for their activities. This is done either through income (by taxation) or through debt (by issuing bonds). In this story, banks simply act as intermediaries collecting deposits and lending parts of that money to creditworthy individuals and institutions, including governments. However, since 1971, when fiat currency – that is, money created out of nothing – became universal, this story has been a complete fiction.

**в озвучке:**

> «Официальная версия» гласит, что правительства, как и любые домохозяйства, должны изыскивать средства для оплаты своей деятельности. Это делается либо через доходы от налогов, либо через долги, то есть выпуск облигаций. В этой версии банки просто выступают посредниками: они собирают депозиты и одалживают часть этих денег кредитоспособным лицам и организациям, включая правительства. Однако с тысяча девятьсот семьдесят первого года, когда фиатные деньги — то есть деньги, созданные буквально из ничего — стали повсеместными, эта история превратилась в полную фикцию.

**`p0218`, исходный абзац:**

> Our current monetary system – the specific manner in which money is created, circulated and managed in our society – is taken for granted by just about everyone. This includes not only the general public, the business community and nongovernmental organisations, but also policy makers and a majority of academics. Consequently, after the massive 2008 financial crisis – the biggest systemic financial failure in history so far **–** the only option considered was to bail out the banking system at whatever cost to taxpayers, in order to return as quickly as possible to business as usual.

**в озвучке:**

> Нынешнюю денежную систему — то есть конкретный способ создания, обращения и управления деньгами в нашем обществе — почти все воспринимают как нечто само собой разумеющееся. Это касается не только широкой общественности, бизнеса или общественных организаций, но и политиков, и большинства ученых. В результате после масштабного финансового кризиса две тысячи восьмого года — крупнейшего системного провала в истории на сегодняшний день — единственным вариантом спасения стало выделение средств банковской системе за счет налогоплательщиков. Цель была одна: как можно быстрее вернуться к привычному положению дел.

---

### `truncated_sentence` — 11

**`narration#223`, исходный абзац:**

> —

**в озвучке:**

> Популярное руководство, объясняющее этот процесс простым языком, находится в приложении А (онлайн). Там обсуждаются роли центральных банков, Международного валютного фонда и других «пожарных» финансовой системы. 4. Ссылка на сайт и сокращенная ссылка bit.ly/TPlink14. (Как и здесь, все ссылки на онлайн-источники сначала указывают основной адрес, а затем прямую ссылку. В некоторых браузерах может потребоваться сначала ввести 5. Донелла Медоуз, Деннис Медоуз, Йорген Рандерс и Уильям Беренс III, «Пределы роста» (1972). Обоснованность многих прогнозов, сделанных в том докладе, была подтверждена в работе Донеллы Медоуз и соавторов «Пределы роста: 30 лет спустя» (2004). 6. Стивен Чеккетти, Мадхусудан Моханти и Фабрицио Замполли, «Будущее государственного долга: перспективы и последствия», BIS

**`narration#280`, исходный абзац:**

> —

**в озвучке:**

> — Декларация 1700 ведущих ученых из 70 стран, включая 102 нобелевских лауреата в области науки, при поддержке академий наук США, Великобритании, Бразилии, Канады, Китая,

**`narration#455`, исходный абзац:**

> —

**в озвучке:**

> См., например, Эдриан Бакли, «Финансовый кризис: причины, контекст и последствия» (2011). 12. Определение МВФ: «При системном банковском кризисе корпоративный и финансовый секторы страны сталкиваются с массовыми дефолтами, а финансовые институты и корпорации испытывают огромные трудности с выполнением обязательств. В результате резко возрастает объем проблемных кредитов, а капитал банковской системы истощается. Эта ситуация может сопровождаться падением цен на активы, резким ростом реальных процентных ставок и замедлением или разворотом потоков капитала». 13. Определение МВФ: «Мы идентифицируем эпизоды суверенного дефолта и реструктуризации долга, опираясь на данные Всемирного банка и отчеты сотрудников МВФ. Мы выявили 63 эпизода суверенных дефолтов и реструктуризаций с 1970 года». Подробности можно найти в работе Федерико Штурценеггера и Джеромина Зеттельмейера «Дефолты по долгам и урок

---

### `year_lost` — 7

**`p0159`, исходный абзац:**

> The consequences in terms of unemployment, lost economic output, societal disruption and widespread human suffering are dramatic. The full financial costs of the 2007-2008 crisis are unprecedented. In the United States for instance, the $700 billion Troubled Asset Relief Program (TARP) is often talked about, although it is only the first slice of the rescue operation. Mention of this programme is usually followed by the comment: “most of that money has by now been reimbursed”.

**в озвучке:**

> Последствия в виде безработицы, потери экономического продукта, разрушения общественных связей и масштабных человеческих страданий драматичны. Полные финансовые издержки кризиса двух тысяч седьмого — восьмого годов беспрецедентны. Например, в Соединенных Штатах часто говорят о программе выкупа проблемных активов на семьсот миллиардов долларов, хотя это лишь первая часть спасательной операции. Упоминание этой программы обычно сопровождается комментарием, что большая часть этих денег к настоящему моменту уже была возвращена.

**`p0383`, исходный абзац:**

> *Sustainable World* (2008). 26 The *World Scientists’ Warning to Humanity* was spearheaded by the late Henry Kendall, former chair of the Union of Concerned

**в озвучке:**

> Сенге в своей книге «Необходимая революция» описывает, как люди и компании могут работать вместе ради устойчивого будущего. Важное обращение ученых всего мира к человечеству было инициировано покойным Генри Кендаллом, бывшим председателем совета директоров Союза обеспокоенных ученых.

**`p0386`, исходный абзац:**

> *Globalization and Its Discontents* (2002). 34 See Friedrich Preisigke, *Girowesen im Griechischen Ägypten, enthaltend Korngiro, Geldgiro, Girobanknotariat mit Einschluß des*

**в озвучке:**

> Его книга «Глобализация и ее недовольство» стала классикой в этой области. Также стоит обратить внимание на исследование Фридриха Прайзигке о банковских операциях в эллинистическом Египте.

---

### `paragraph_emptied` — 6

**`p0808`, исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, *No Logo: Taking Aim at the Brand Bullies* (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in *The Economist* January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see *The Economist*, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Mone

**в озвучке:**

> 

**`p0809`, исходный абзац:**

> Reinhart *et al.* (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, *Financial*

**в озвучке:**

> 

**`p1140`, исходный абзац:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, *Creating Wealth: Growing Local*

**в озвучке:**

> 

---

### `url_left_in` — 5

**`narration#221`, исходный абзац:**

> —

**в озвучке:**

> Сайт money-sustainability.net является частью этого доклада. Там вы найдете фрагменты текста, обновления и все приложения. Также на сайте есть возможность обсудить изложенные идеи. Фрагменты и приложения также доступны по короткой ссылке bit.ly/TPmissinglink.

**`narration#821`, исходный абзац:**

> —

**в озвучке:**

> Четвертая причина — это, говоря прямо, политический реализм. Банковская система будет бороться с любой версией «Чикагского плана» до последнего, так как он угрожает и её власти, и самой бизнес-модели. Даже после краха 2007–2008 годов или в разгар Великой депрессии 1930-х годов банковское лобби успешно блокировало любые значимые изменения. Вспомните: в 2010 году на каждого избранного чиновника в Вашингтоне приходилось по три высокопоставленных лоббиста, работавших на банковскую систему. Томас Фридман писал в «Нью-Йорк таймс»: «Наш Конгресс сегодня — это площадка для узаконенного взяточничества». Одна из групп по защите прав потребителей, используя данные сайта Opensecrets.org, подсчитала, что индустрия финансовых услуг, включая сектор недвижимости, потратила 2,3 миллиарда долларов на взносы в федеральные избирательные кампании с 1990 по 2010 год. Это больше, чем расходы индустрий здравоох

**`narration#1274`, исходный абзац:**

> —

**в озвучке:**

> 4 Джин Хьюстон, «Жизненная сила: Психоисторическое восстановление личности» (1993), стр. 13. 5 Тойнби (1939). Сокращенную версию см. в работе Тойнби (1960). 6 Джаред Даймонд (2005). 7 Видео о саммите доступно по ссылке. Анализ интеллектуального содержания доступен на сайте dandelionsalad.wordpress.com. 8 Томас Фридман, «Слышали историю про банкиров?». 9 Эти два аспекта — рост населения и его старение — не обязательно исключают друг друга. Население планеты в целом все еще быстро растет, тогда как в так называемом «развитом» мире «демографическая волна» уже близка, а по сути, уже начинается. 10 См. Лиетар (2001), стр. 17–30. 11 Эдвард О. Уилсон, «Будущее жизни» (2002). 12 См. сайт mises.org, стр. 133–134. 13 См. сайт ec.europa.eu. 14 Документация по аргументам в пользу стратегии регионального развития представлена в работах Кеннеди и Лиетара (2004), Лиетара и

---

### `stray_markup_or_ocr_garbage` — 4

**`narration#25`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#716`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#1183`, исходный абзац:**

> —

**в озвучке:**

> * *

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

### `absent_from_artifact` — 1

**`p0957`, исходный абзац:**

> ## **NGO Initiative s :**

**в озвучке:**

> None

---
