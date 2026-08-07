# Счёт ручной правки после прогона — по классам (value_of_everything)

База: 1247 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1247 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 44 | 3.5% |
| `year_spelled_out_for_tts_not_a_defect` | 33 | 2.6% |
| `truncated_sentence` | 21 | 1.7% |
| `year_dropped_with_reference_apparatus` | 19 | 1.5% |
| `year_lost` | 15 | 1.2% |
| `malformed_or_disallowed_tag` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 44

**`narration#2`, исходный абзац:**

> —

**в озвучке:**

> [serious] Создание и присвоение ценности в мировой экономике

**`narration#5`, исходный абзац:**

> —

**в озвучке:**

> [serious] Ценность в глазах смотрящего: расцвет маржинализма

**`narration#9`, исходный абзац:**

> —

**в озвучке:**

> [serious] Одной лишь корректировки национальных счетов недостаточно

---

### `year_spelled_out_for_tts_not_a_defect` — 33

**`p0005`, исходный абзац:**

> 2018

**в озвучке:**

> [serious] Две тысячи восемнадцатый год.

**`p0075`, исходный абзац:**

> Similar questions are still being asked today. In 2016 the British high-street retailer BHS collapsed. It had been founded in 1928 and in 2004 was bought by Sir Philip Green, a well-known retail entrepreneur, for £200 million. In 2015 Sir Philip sold the business for £1 to a group of investors headed by the British businessman Dominic Chappell. While it was under his control, Sir Philip and his family extracted from BHS an estimated £580 million in dividends, rental payments and interest on loans they had made to the company. The collapse of BHS threw 11,000 people out of work and left its pension fund with a £571 million deficit, even though the fund had been in surplus when Sir Philip acquired it.² A report on the BHS disaster by the House of Commons Work and Pensions Select Committee accused Sir Philip, Mr Chappell and their ‘hangers-on’ of ‘systematic plunder’. For BHS workers and pe

**в озвучке:**

> [serious] Подобные вопросы задают и сегодня. В две тысячи шестнадцатом году обанкротилась британская розничная сеть BHS. Компания была основана в тысяча девятьсот двадцать восьмом году, а в две тысячи четвертом ее приобрел известный предприниматель сэр Филип Грин за двести миллионов фунтов стерлингов. В две тысячи пятнадцатом году сэр Филип продал бизнес всего за один фунт группе инвесторов во главе с британским бизнесменом Домиником Чэппеллом. За время своего контроля над компанией сэр Филип и его семья вывели из нее около пятисот восьмидесяти миллионов фунтов в виде дивидендов, арендных платежей и процентов по кредитам, которые они сами же выдали компании. Банкротство BHS привело к увольнению одиннадцати тысяч человек и оставило пенсионный фонд компании с дефицитом в пятьсот семьдесят один миллион фунтов, хотя на момент покупки фонда сэром Филипом он был профицитным. Специальный комите

**`p0076`, исходный абзац:**

> While Sir Philip’s activities could be viewed as an aberration, the excesses of an individual, his way of thinking is hardly unusual: today, many giant corporations are also guilty of confusing value creation with value extraction. In August 2016, for instance, the European Commission, the European Union’s (EU) executive arm, sparked an international row between the EU and the US when it ordered Apple to pay €13 billion in 3 back taxes to Ireland.

**в озвучке:**

> [thoughtful] Хотя деятельность сэра Филипа можно было бы счесть исключением, проявлением жадности одного человека, такой образ мыслей едва ли уникален. Сегодня многие гигантские корпорации также грешат тем, что путают создание ценности с ее извлечением. Например, в августе две тысячи шестнадцатого года Европейская комиссия — исполнительный орган Европейского союза — спровоцировала международный скандал, потребовав от компании Apple выплатить Ирландии тринадцать миллиардов евро в качестве налоговых недоимок.

---

### `truncated_sentence` — 21

**`narration#141`, исходный абзац:**

> —

**в озвучке:**

> Чтобы построить более справедливую экономику, где процветание распределяется шире и потому является более устойчивым, нам нужно возобновить серьезный разговор о природе и происхождении ценности. Мы должны переосмыслить истории, которые мы рассказываем о том, кто такие «создатели ценности» и как мы определяем, является ли деятельность экономически продуктивной. Мы не можем ограничивать прогрессивную политику одним лишь налогообложением богатства. Нам нужно новое понимание процесса создания богатства, чтобы этот вопрос стал предметом открытой и острой борьбы. Слова имеют значение: нам нужен новый словарь для формирования политики. Политика — это не просто «вмешательство». Это формирование будущего: совместное создание рынков и ценности, а не просто их «исправление» или перераспределение. Речь идет о принятии рисков, а не только о

**`narration#223`, исходный абзац:**

> —

**в озвучке:**

> [serious] В 1810-х годах еще одна выдающаяся фигура английской классической экономической школы использовала трудовую теорию стоимости и понятие производительности, чтобы объяснить, как общество поддерживает условия для своего воспроизводства. Дэвид Рикардо происходил из семьи сефардских евреев, которая перебралась из Португалии в Голландию, а затем обосновалась в Англии. Рикардо пошел по стопам отца и стал лондонским биржевым маклером, хотя позже порвал с семьей, приняв унитарианство. Он сказочно разбогател на спекуляциях, самым известным из которых стал его заработок на недостоверной информации о битве при Ватерлоо в

**`narration#264`, исходный абзац:**

> —

**в озвучке:**

> Раньше экономисты рассматривали «капитал» как нечто сугубо материальное — например, станки или здания, — а прибавочный продукт считали исключительно позитивным явлением, помогающим экономике воспроизводиться и расти. Маркс же придал капиталу социальное измерение, а прибавочному продукту — негативный оттенок. Труд создает прибавочную стоимость, которая питает накопление капитала и экономический рост. Однако накопление капитала происходит не только благодаря производительному труду. Оно глубоко социально. Поскольку рабочие не владеют средствами производства, они оказываются

---

### `year_dropped_with_reference_apparatus` — 19

**`p0172`, исходный абзац:**

> Seventeenth-century Britain saw two groundbreaking attempts to quantify national income. One was by Sir William Petty (1623–87), an adventurer, anatomist, physician and Member of Parliament, who was a tax administrator in Ireland under Oliver Cromwell’s Commonwealth government.⁵ The other was by the herald Gregory King (1648–1712), a genealogist, engraver and statistician whose work on enacting a new tax on marriages, births and burials provoked his interest in national accounting.

**в озвучке:**

> В Британии семнадцатого века было предпринято две новаторские попытки количественно оценить национальный доход. Одну из них предпринял сэр Уильям Петти — авантюрист, анатом, врач и член парламента, который служил налоговым администратором в Ирландии при правительстве Оливера Кромвеля. Другую — герольд Грегори Кинг, генеалог, гравер и статистик, чей интерес к национальному учету возник во время работы над введением нового налога на браки, рождения и смерти.

**`p0189`, исходный абзац:**

> The first efforts to find a formal theory of value came in the mid-eighteenth century from the court of Louis XV of France, in the twilight – so it turned out – of that country’s absolute monarchy. There, François Quesnay (1694–1774), often described as the ‘father of economics’, was the king’s physician and adviser. He used his medical training to understand the economy as a ‘metabolic’ system. Crucially, in metabolism, everything must come from somewhere and go somewhere – and that, for Quesnay, included wealth. Quesnay’s approach led him to formulate the first systematic theory of value that classified who is and is not productive in an economy, and to model how the entire economy could reproduce itself from the value generated by a small group of its members. In his seminal work *Tableau Économique*, published in 1758, he constructed an ‘economic table’ which showed how new value was

**в озвучке:**

> [thoughtful] Первые попытки создать формальную теорию стоимости появились в середине восемнадцатого века при дворе французского короля Людовика XV, на закате эпохи абсолютной монархии. Франсуа Кенэ, которого часто называют «отцом экономики», был придворным врачом и советником короля. Он использовал свои медицинские знания, чтобы представить экономику как своего рода «метаболический» процесс. Кенэ считал, что в обмене веществ всё должно откуда-то приходить и куда-то уходить — это касалось и богатства. Его подход позволил сформулировать первую систематическую теорию стоимости. Она классифицировала виды деятельности на продуктивные и непродуктивные и показывала, как экономика может воспроизводить себя за счёт ценности, создаваемой лишь малой группой людей. В своей знаменитой работе «Экономическая таблица», опубликованной в 1758 году, он построил схему, демонстрирующую создание и движение це

**`p0313`, исходный абзац:**

> Socialist critiques of value theory were multiplying even before Marx wrote *Capital*. A group called the ‘Ricardian socialists’ used Ricardo’s labour theory of value to demand that workers get better wages. They included the Irishman William Thompson (1775–1833), Thomas Hodgskin (1787–1869) and John Gray (1799–1883), both British, and John Bray (1809–97), who was born in the US but worked for part of his life in Britain. Together, they made the obvious argument that if the value of commodities derives from labour, the revenue from their sale should go to workers. This idea underlay the co-operativism of the textile manufacturer Robert Owen (1771–1858), for whom the solution was that workers should also participate in ownership, of both factories and publicly created infrastructure. Marx and Engels were friendly with some of these groups, but very unfriendly towards others whom they thou

**в озвучке:**

> [serious] Социалистическая критика теории стоимости звучала еще до того, как Карл Маркс написал «Капитал». Группа мыслителей, известных как «рикардианские социалисты», опиралась на трудовую теорию стоимости Давида Рикардо, требуя повышения зарплат для рабочих. В эту группу входили ирландец Уильям Томпсон, британцы Томас Ходжскин и Джон Грей, а также Джон Брей, родившийся в Соединенных Штатах, но часть жизни проработавший в Британии. Все они приводили простой довод: если стоимость товаров создается трудом, то и выручка от их продажи должна принадлежать рабочим. Эта идея легла в основу кооперативного движения текстильного фабриканта Роберта Оуэна. Он считал, что рабочие должны участвовать в управлении собственностью — как на фабриках, так и в отношении общественной инфраструктуры. Маркс и Энгельс поддерживали дружеские отношения с одними из этих групп, но крайне враждебно относились к друг

---

### `year_lost` — 15

**`p0169`, исходный абзац:**

> Scholars and politicians of the time who argued that accumulating precious metals was the route to national power and prosperity are called mercantilists (from *mercator*, the Latin word for merchant), because they espoused protectionist trade policies and positive trade balances to stimulate the inflow, and prevent the outflow, of gold and silver. The best-known English advocate of mercantilism was a merchant and director of the East India Company called Sir Thomas Mun (1571–1641). In his influential book *England’s Treasure by Forraign Trade*, Mun summed up the mercantilist doctrine: we must, he said, ‘sell more to strangers yearly 4 than wee consume of theirs in value’.

**в озвучке:**

> Ученых и политиков того времени, которые доказывали, что накопление драгоценных металлов — это путь к государственной мощи и процветанию, называют меркантилистами. Само слово происходит от латинского «mercator», что значит «купец». Они поддерживали протекционистскую торговую политику и положительный торговый баланс, чтобы стимулировать приток золота и серебра и предотвратить их отток. Самым известным английским идеологом меркантилизма был купец и директор Ост-Индской компании сэр Томас Ман. В своей влиятельной книге «Богатство Англии во внешней торговле» Ман подвел итог меркантилистской доктрине: мы должны, писал он, ежегодно продавать иностранцам товаров на большую сумму, чем покупаем у них.

**`p0244`, исходный абзац:**

> Ricardo inherited this ‘dismal theory’ of wages from his contemporary Thomas Malthus (1766–1834), another English writer on political economy, who proposed that whenever real wages are above subsistence level, the population will grow until it is so large that the demand for food 35 will push up food prices enough to bring wages back to subsistence level.

**в озвучке:**

> Рикардо унаследовал эту «мрачную теорию» заработной платы от своего современника Томаса Мальтуса. Этот английский экономист полагал, что всякий раз, когда реальная зарплата превышает прожиточный минимум, население растет до тех пор, пока спрос на продовольствие не поднимет цены настолько, что зарплаты снова вернутся к уровню выживания.

**`p0303`, исходный абзац:**

> All these issues have come to the fore again since the 2008 financial crisis. At their heart is how finance has been self-serving, and not actually serving what the American economist Hyman Minsky (1919–96) called the ‘capital development of the economy’.⁶¹ In other words, instead of facilitating industrial production, finance has simply degenerated into a casino, aiming to appropriate as much of the existing surplus as possible for itself.⁶² But whether that casino is seen as a mere imperfection or as a stable source of unearned income (whereby activities that are not creating value are somehow allowed to be presented a such) makes all the difference in policies that aim to reform the system.

**в озвучке:**

> [serious] Все эти вопросы вновь вышли на первый план после финансового кризиса 2008 года. В их основе лежит проблема того, что финансовый сектор стал работать на самого себя, а не на то, что американский экономист Хайман Мински называл «капитальным развитием экономики». Иными словами, вместо того чтобы способствовать промышленному производству, финансы превратились в своего рода казино. Их главная цель — присвоить как можно большую часть уже созданного прибавочного продукта. Однако то, как мы воспринимаем это «казино» — как простое несовершенство рынка или как устойчивый источник нетрудовых доходов, — имеет решающее значение для политики реформирования системы. Ведь в последнем случае деятельность, которая не создает никакой ценности, каким-то образом получает статус созидательной.

---

### `malformed_or_disallowed_tag` — 1

**`narration#215`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Смит выделял три вида дохода: заработная плата за труд на капиталистических предприятиях, прибыль капиталистов, владеющих средствами производства, и рента от владения землей. Когда эти три источника дохода выплачиваются на конкурентном уровне, вместе они определяют то, что он называл «конкурентной ценой». Поскольку земля необходима, рента с нее была «естественной» частью экономики. Но это не означало, что рента продуктивна. Смит писал: «землевладельцы, как и все другие люди, любят пожинать там, где они не сеяли, и требуют ренту [с земли] даже за ее естественные плоды». Более того, Смит утверждал, что принцип земельной ренты можно распространить и на другие монополии, например, на право импортировать определенный товар или право выступать в суде. Смит прекрасно понимал, какой вред могут нанести монополии. В семнадцатом веке правительство, отчаянно нуждавшееся в доходах, разда

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

- граница: блок `236` — `## Notes`
- блоков аппарата: 477, из них исключено из озвучки: 476
- **абзацев аппарата, попавших в озвучку: 12**
- **символов: 4284**

Примеры (цитаты из артефакта):

**`p2281`:**

> ## Благодарности

**`p2282`:**

> [thoughtful] В 2013 году я написала книгу «Предпринимательское государство». В ней я развенчала мифы об одиноких предпринимателях и стартапах, которые захватили теорию и практику инноваций. Эти мифы игнорируют одного из ключевых игроков — государство, которое часто выступает инвестором первой очеред

**`p2283`:**

> Книга, которую вы держите в руках, стала прямым следствием этих размышлений. Мы не сможем понять экономический рост, если не вернемся к истокам: что такое богатство и откуда берется стоимость? Уверены ли мы, что многое из того, что выдается за создание стоимости, не является лишь ее присвоением под 
