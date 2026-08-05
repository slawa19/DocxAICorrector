# Счёт ручной правки после прогона — по классам

База: 1318 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Два класса
(`paragraph_emptied`, `year_lost`) видны только по парам «исходник → озвучка» и
считаются по 1318 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `bullet_marker_left_in` | 115 | 8.7% |
| `heading_without_terminal_punctuation_not_a_defect` | 78 | 5.9% |
| `not_translated` | 25 | 1.9% |
| `year_spelled_out_for_tts_not_a_defect` | 25 | 1.9% |
| `year_dropped_with_reference_apparatus` | 25 | 1.9% |
| `truncated_sentence` | 22 | 1.7% |
| `paragraph_emptied` | 8 | 0.6% |
| `year_lost` | 6 | 0.5% |
| `footnote_marker_left_in` | 5 | 0.4% |
| `stray_markup_or_ocr_garbage` | 4 | 0.3% |
| `url_left_in` | 3 | 0.2% |
| `malformed_or_disallowed_tag` | 2 | 0.2% |
| `absent_from_artifact` | 1 | 0.1% |

## Примеры по классам

### `bullet_marker_left_in` — 115

**`narration#58`, исходный абзац:**

> —

**в озвучке:**

> • В обычное время проциклическое усиление процесса создания денег обходится деловому миру крайне дорого. Компании постоянно сталкиваются либо с нехваткой, либо с избытком персонала и инвестиций, постоянно балансируя на этих качелях.

**`narration#59`, исходный абзац:**

> —

**в озвучке:**

> • Во время кризисов, когда банки совершают ошибки, они фактически берут в заложники весь бизнес-мир. Это повышает риски для всех компаний — от малых предприятий до гигантов с Уолл-стрит.

**`narration#60`, исходный абзац:**

> —

**в озвучке:**

> • Решения, представленные в седьмой главе, показывают, что именно бизнес может и должен предпринять самостоятельно, чтобы систематически избегать подобных проблем.

---

### `heading_without_terminal_punctuation_not_a_defect` — 78

**`narration#8`, исходный абзац:**

> —

**в озвучке:**

> [serious] Отчет Европейского отделения Римского клуба

**`narration#10`, исходный абзац:**

> —

**в озвучке:**

> [serious] Финансы, надзор и Всемирная бизнес-академия

**`narration#11`, исходный абзац:**

> —

**в озвучке:**

> Бернар Литар, Кристиан Амспергер, Салли Гёрнер и Стефан Бруннхубер

---

### `not_translated` — 25

**`narration#509`, исходный абзац:**

> —

**в озвучке:**

> “For plants and animals, information about the environment is stored in genes. Plants and animals have adapted to a specifi c environment. This adaptation takes place through natural selection. The plants and animals selected are those capable of most rapidly and effectively dissipating energy. By doing this, a living being changes its environment. As the environment changes, its genes are no longer adapted. This living being needs to evolve again. To remain in harmony with the environment which it is making evolve, a living being needs to adapt with greater speed. After atoms and molecules, living beings increase in complexity. Those most adept at dissipating energy are the ones that invariably win. “Geothermal energy dissipates not gradually but suddenly, in the form of earthquakes. The same is true with life. Plant and animal ecosystems develop quickly and collapse suddenly, to be rep

**`narration#717`, исходный абзац:**

> —

**в озвучке:**

> Once upon a time, in a small village in the Outback , people used barter for all their transactions. On every mark et day, people walk ed around with chick ens, eggs, hams, and breads, and engaged in prolonged negotiations among themselves to exchange what they needed. At k ey periods of the year, such as during harvests or when someone’s barn required big repairs after a storm, people recalled the tradition of helping each other out, brought from the old country. They k new that if they had a problem someday, others would help them in return. One mark et day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral the six chick ens he wanted to exchange for a big ham, he could not refrain from laughing. “Poor people”, he said, “so primitive”. The farmer’s wife overheard him a

**`narration#747`, исходный абзац:**

> —

**в озвучке:**

> Far from being the behaviourally neutral and purely facilitative exchange tool that the Traditional Economics paradigm assumes, the conventional monetary system acts as a large-scale, unconscious programming tool. It generates five processes that directly conflict with various dimensions of sustainability. Today’s monetary system combines a pro-cyclical money supply with deregulated capital flows, and uncontrolled speculative incentives. Furthermore, this money is created with built-in compound interest that makes growth obligatory and renders the concentration of wealth automatic. None of these features is a law of nature. They are all conventions that can be systemically counter-balanced by other systems to neutralise these effects.

---

### `year_spelled_out_for_tts_not_a_defect` — 25

**`p0184`, исходный абзац:**

> It is often assumed that the relationship between the banking system and governments has remained unchanged for centuries. A case study of France shows that this is not necessarily the case. Indeed, since 1973, the French government has been forced to borrow exclusively from the private sector and therefore pay interest on new debt. Without this change, French government debt would now be at 8.6% of GDP instead of the current 78%. Furthermore, the Maastricht and Lisbon Treaties have generalised this same process to all signatory countries.

**в озвучке:**

> Часто предполагают, что отношения между банковской системой и правительствами оставались неизменными на протяжении веков. Однако пример Франции показывает, что это не совсем так. С тысяча девятьсот семьдесят третьего года французское правительство вынуждено занимать средства исключительно в частном секторе и, следовательно, платить проценты по новому долгу. Без этого изменения государственный долг Франции составлял бы сейчас восемь целых и шесть десятых процента от валового внутреннего продукта, а не текущие семьдесят восемь процентов. Более того, Маастрихтский и Лиссабонский договоры распространили этот процесс на все страны-участницы.

**`p0186`, исходный абзац:**

> The ‘official story’ is that governments, just like any household, must raise the money needed to pay for their activities. This is done either through income (by taxation) or through debt (by issuing bonds). In this story, banks simply act as intermediaries collecting deposits and lending parts of that money to creditworthy individuals and institutions, including governments. However, since 1971, when fiat currency – that is, money created out of nothing – became universal, this story has been a complete fiction.

**в озвучке:**

> [thoughtful] Официальная версия гласит, что правительства, как и любая семья, должны изыскивать средства для оплаты своей деятельности. Это делается либо за счет доходов от налогов, либо через долг путем выпуска облигаций. Согласно этой версии, банки просто выступают посредниками, которые принимают депозиты и одалживают часть этих денег кредитоспособным лицам и организациям, включая правительства. Однако с тысяча девятьсот семьдесят первого года, когда фиатная валюта — то есть деньги, созданные из ничего, — стала повсеместной, эта история превратилась в полную фикцию.

**`p0218`, исходный абзац:**

> Our current monetary system – the specific manner in which money is created, circulated and managed in our society – is taken for granted by just about everyone. This includes not only the general public, the business community and nongovernmental organisations, but also policy makers and a majority of academics. Consequently, after the massive 2008 financial crisis – the biggest systemic financial failure in history so far **–** the only option considered was to bail out the banking system at whatever cost to taxpayers, in order to return as quickly as possible to business as usual.

**в озвучке:**

> Нынешнюю денежную систему — то есть конкретный способ создания, обращения и управления деньгами в нашем обществе — почти все воспринимают как нечто само собой разумеющееся. Это касается не только широкой общественности, бизнеса или некоммерческих организаций, но и политиков, и большинства ученых. В результате после масштабного финансового кризиса две тысячи восьмого года — крупнейшего системного провала в истории — единственным вариантом спасения стало выделение средств банковской системе любой ценой. Всё ради того, чтобы как можно быстрее вернуться к привычному укладу дел.

---

### `year_dropped_with_reference_apparatus` — 25

**`p0375`, исходный абзац:**

> He defines a scientific paradigm as an epistemological pattern, a mental framework that specifies a series of what’s and how-to’s: *what* is to be observed and scrutinised, and by implication what is to be overlooked; the kind of *questions* that are supposed to be asked or ignored; *how* these questions are to be structured; *how* the results of scientific investigations should be interpreted. A paradigm, according to Kuhn, adjusts over time to the everyday requirements of what he calls ‘normal science’, i.e., the business of tinkering with models and making them fit empirical data as well as possible, for as long as possible. The period of normal science is sometimes ended, more or less abruptly, by a ‘scientific revolution’. 2 Christian Arnsperger, *Full-Spectrum Economics: Towards an Inclusive and Emancipatory Social Science* (2010a), p.25. 3 In opposition to the Traditional Economic

**в озвучке:**

> [thoughtful] Томас Кун определяет научную парадигму как эпистемологическую модель, своего рода ментальную рамку. Она задает набор правил: что именно следует наблюдать и изучать, а что — игнорировать; какие вопросы стоит задавать, а какие — пропускать; как структурировать эти вопросы и как интерпретировать результаты исследований. По мнению Куна, парадигма со временем подстраивается под нужды так называемой «нормальной науки». Это повседневная работа по доработке моделей, чтобы они как можно дольше и точнее соответствовали эмпирическим данным. Период нормальной науки иногда завершается — более или менее внезапно — «научной революцией».

**`p0376`, исходный абзац:**

> Gowdy & Jon D. Erikson (2005). For a general but exhaustive treatment, see e.g. Molly Scott Cato (2009) and Herman Daly & Joshua Farley (2011). Ecological economics should not be confused with ‘environmental economics’, which was initially part of the Traditional Economics approach and has been a driving force behind the OECD approach shown in Figure 2.2. 9 In this statement, we extend ecological economics into what might be called ‘political ecology’, since traditionally ecological economists emphasise more the embeddedness of the economic within the environmental, and less its embeddedness within the social. However, political ecology and ecological economics are very closely linked, and most ecological economists will have no objection to our graph here.

**в озвучке:**

> [serious] Экологическую экономику не следует путать с «экономикой окружающей среды». Последняя изначально была частью традиционного экономического подхода и стала движущей силой стратегии ОЭСР. В этом тексте мы расширяем рамки экологической экономики до того, что можно назвать «политической экологией». Традиционно экологические экономисты делают упор на встроенность экономики в природную среду, уделяя меньше внимания её социальной составляющей. Однако политическая экология и экологическая экономика тесно связаны, и большинство специалистов в этой области согласятся с нашим подходом.

**`p0377`, исходный абзац:**

> 10 See, amongst others, Ken Wilber, *Sex, Ecology, Spirituality: The Spirit of Evolution* (1995). 11 An approach that has led mainstream economists to reason as if, with good enough economic and ‘human’ capital in the form of extremely high-grade technologies and an extremely well-trained workforce, the whole world’s production might be manufactured with virtually no natural capital, e.g., with just a few grains of matter… 12 This idea – and especially the notion of ‘ecological debt’ – is a major theme in the influential book of Tim Jackson, *Prosperity*

**в озвучке:**

> [curious] Существует подход, который заставил мейнстримных экономистов рассуждать так, будто при наличии достаточно качественного человеческого капитала, передовых технологий и квалифицированной рабочей силы мировое производство можно поддерживать практически без использования природного капитала — буквально из нескольких крупиц материи.

---

### `truncated_sentence` — 22

**`narration#280`, исходный абзац:**

> —

**в озвучке:**

> — Декларация 1700 ведущих ученых из 70 стран, включая 102 нобелевских лауреата в области науки, при поддержке научных академий США, Великобритании, Бразилии, Канады, Китая,

**`narration#455`, исходный абзац:**

> —

**в озвучке:**

> [serious] Мэни Арнарсон и соавторы, «Коллапс: системный анализ финансовых, социальных и мировых связей» (2011). См. также работу Эдриана Бакли «Финансовый кризис: причины, контекст и последствия» (2011), страницы с 74 по 88. Согласно определению Международного валютного фонда, системный банковский кризис — это ситуация, когда в корпоративном и финансовом секторах страны происходит большое количество дефолтов, а финансовые институты и корпорации сталкиваются с серьезными трудностями при выполнении своих обязательств в срок. В результате резко возрастает объем проблемных кредитов, а капитал банковской системы оказывается практически полностью исчерпан. Такая ситуация часто сопровождается падением цен на активы — например, на акции и недвижимость — после предшествовавшего им роста, а также резким повышением реальных процентных ставок и замедлением или оттоком капитала. В некоторых случаях к

**`narration#749`, исходный абзац:**

> —

**в озвучке:**

> Footnotes 1 Quoted in Naomi Klein, No Logo: Taking Aim at the Brand Bullies (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in The Economist January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see The Economist, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary P

---

### `paragraph_emptied` — 8

**`p0496`, исходный абзац:**

> 3 *The CIA Factbook 2012* estimates global GDP at purchasing power parity at US$78.98 trillion. 4 John Maynard Keynes, *The General Theory of Employment, Interest and Money* (1936), p.159. 5 Ludwig von Mises, *Human Action: A Treatise on Economics* (1949). 6 *The Financial Crisis Inquiry Report: Final Report of the National Commission of the Financial and Economic Crisis in the United*

**в озвучке:**

> 

**`p0497`, исходный абзац:**

> *States* (2011). 7 Andrew Ross Sorkin, *Too Big to Fail* (2010). 8 Anton R. Valukas, Lehman Brothers Inc. Chapter 11 Proceedings Examiner’s Report (2010), downloadable from *http://lehmanreport.jenner.com ~ bit.ly/TPlink18* (visited: 8 January 2012). 9 ‘Restoring Ireland’s Credit by Reducing Uncertainty’, Remarks by Mr Patrick Honohan, Governor of the Central Bank of Ireland, at the Institute of International and European Affairs, Dublin, 7 January 2011, downloadable from *www.bis.org* ~ *bit.ly/TPlink19* (visited: 8 January 2012). 10 Máni Arnarson, Þorbjörn Kristjánsson, Atli Bjarnason, Harald Sverdrup and Kristín Vala Ragnarsdóttir*, Icelandic Economic*

**в озвучке:**

> 

**`p0808`, исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, *No Logo: Taking Aim at the Brand Bullies* (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in *The Economist* January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see *The Economist*, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Mone

**в озвучке:**

> 

---

### `year_lost` — 6

**`p0383`, исходный абзац:**

> *Sustainable World* (2008). 26 The *World Scientists’ Warning to Humanity* was spearheaded by the late Henry Kendall, former chair of the Union of Concerned

**в озвучке:**

> Сенге описывает, как люди и организации могут объединять усилия для создания устойчивого мира. «Предупреждение ученых мира человечеству» было инициировано покойным Генри Кендаллом, бывшим председателем совета директоров Союза обеспокоенных ученых.

**`p0386`, исходный абзац:**

> *Globalization and Its Discontents* (2002). 34 See Friedrich Preisigke, *Girowesen im Griechischen Ägypten, enthaltend Korngiro, Geldgiro, Girobanknotariat mit Einschluß des*

**в озвучке:**

> Также стоит обратить внимание на историческое исследование Фридриха Прайзигке о банковском деле в эллинистическом Египте.

**`p0388`, исходный абзац:**

> *New Money for a New World* (2011), also available on *www.newmoneyforanewworld.com*. 36 ‘Nobel Descendant Slams Economics Prize’, *The Local*, 28 September, 2010 (*www.thelocal.se ~ bit.ly/TPlink16*).

**в озвучке:**

> Дополнительная информация доступна на сайте проекта «Новые деньги для нового мира». Также стоит упомянуть критику Нобелевской премии по экономике, прозвучавшую в 2010 году от потомков Альфреда Нобеля.

---

### `footnote_marker_left_in` — 5

**`narration#933`, исходный абзац:**

> —

**в озвучке:**

> The Wellness Token Alliance, which could be run by an NGO or by a group of insurance companies⁹, would issue Wellness Tokens for two types of activities:

**`narration#936`, исходный абзац:**

> —

**в озвучке:**

> The return on investment (ROI) of such preventive programmes is estimated to range from 300% to 1000% depending on the programme.¹¹ That such rates of return are available in preventive programmes provides hard evidence that the ‘sick and alive’ market failure is quite real. Wellness Tokens would encourage the adoption and maintenance of healthy habitual behaviours. The payment of individuals for maintaining specified healthy behaviours has already been documented through the use of conditional cash transfers, for example to remain HIV negative.¹² For example, a family with two obese children could participate in a weight reduction programme, monitored either through weight or, even more precisely, through the Body Mass Index (BMI). For every kilogram or BMI improvement, the family would receive 10 Wellness Tokens.

**`narration#939`, исходный абзац:**

> —

**в озвучке:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a personal-responsibility-building dimension to th

---

### `stray_markup_or_ocr_garbage` — 4

**`narration#25`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#718`, исходный абзац:**

> —

**в озвучке:**

> *

**`narration#1201`, исходный абзац:**

> —

**в озвучке:**

> * *

---

### `url_left_in` — 3

**`narration#221`, исходный абзац:**

> —

**в озвучке:**

> Веб-сайт money-sustainability.net является частью этого отчета. Там вы найдете выдержки из текста, обновления и все приложения. Также там есть способы связи для обсуждения этих идей. Выдержки и приложения доступны и по ссылке, указанной в тексте.

**`narration#831`, исходный абзац:**

> —

**в озвучке:**

> Четвертую причину можно назвать «политическим реализмом». Любая версия «Чикагского плана» встретит ожесточенное сопротивление банковской системы, поскольку она угрожает и её власти, и самой бизнес-модели. Даже после злоупотреблений, приведших к краху 2007–2008 годов, или в разгар Великой депрессии 1930-х годов, банковское лобби успешно блокировало любые значимые изменения. Вспомните: в 2010 году на каждого избранного чиновника в Вашингтоне приходилось по три высокопоставленных лоббиста, работающих на банковскую систему. Томас Фридман писал в «Нью-Йорк таймс»: «Сегодня наш Конгресс — это площадка для узаконенного взяточничества. Одна из групп по защите прав потребителей, используя данные сайта OpenSecrets.org, подсчитала, что индустрия финансовых услуг, включая сектор недвижимости, потратила на предвыборные кампании с 1990 по 2010 год два и три десятых миллиарда долларов. Это больше, чем 

**`narration#1292`, исходный абзац:**

> —

**в озвучке:**

> Джин Хьюстон, «Жизненная сила: психоисторическое восстановление самости» (1993), стр. 13. 5. Тойнби (1939). Краткую версию см. в работе Тойнби (1960). 6. Джаред Даймонд (2005). 7. Видео об атмосфере на саммите доступно по ссылке. Анализ интеллектуального содержания доступен на сайте Dandelion Salad. 8. Томас Фридман, «Слышали историю про банкиров?». 9. Эти два аспекта — рост населения и его старение — не обязательно исключают друг друга. Население планеты в целом все еще активно растет, в то время как в так называемом «развитом» мире «волна старения» уже близка и, по сути, уже началась. 10. См. Лиетар (2001), стр. 17–30. 11. Эдвард О. Уилсон, «Будущее жизни» (2002). 12. См. сайт Mises.org, стр. 133–134. 13. См. сайт Европейской комиссии. 14. Документация об аргументах в пользу стратегии регионального развития представлена в работах Кеннеди и Лиетара (2004), Лиетара и

---

### `malformed_or_disallowed_tag` — 2

**`narration#1055`, исходный абзац:**

> —

**в озвучке:**

> [[thoughtful]] Каждое из этих преимуществ заслуживает подробного разбора. Начнем с приведения финансовых интересов в соответствие с долгосрочными задачами. Функция демереджа в торговой эталонной валюте создает финансовый стимул, который переориентирует участников рынка на долгосрочную перспективу. Это прямо противоположно принципу дисконтирования денежных потоков в нынешних национальных валютах. Там положительные процентные ставки заставляют агентов фокусироваться на немедленной выгоде в ущерб будущему. В системе с демереджем происходит обратное: конфликт между краткосрочными интересами акционеров и долгосрочными приоритетами всего человечества значительно смягчается.

**`narration#1056`, исходный абзац:**

> —

**в озвучке:**

> [[serious]] Во-вторых, рассмотрим роль торговой эталонной валюты в стабилизации делового цикла. Она противодействует колебаниям рынка, повышая общую предсказуемость мировой экономики. Когда деловая активность падает, у корпораций обычно скапливаются излишки запасов и возникает потребность в кредитах. Если эти излишки представляют собой сырье, входящее в корзину торговой эталонной валюты, компании могут продать их Альянсу, который поместит товары на хранение. Взамен корпорации получат торговую валюту, что даст им доступ к средствам платежа, столь необходимым в периоды спада. Плата за демередж будет побуждать компании быстрее расплачиваться с поставщиками, а те, в свою очередь, будут стремиться передать валюту дальше. Распространение такой валюты, обладающей встроенным стимулом к обороту, поможет быстро оживить экономику в нужный момент.

---

### `absent_from_artifact` — 1

**`p0957`, исходный абзац:**

> ## **NGO Initiative s :**

**в озвучке:**

> None

---
