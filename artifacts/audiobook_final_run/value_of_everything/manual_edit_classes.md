# Счёт ручной правки после прогона — по классам (value_of_everything)

База: 1242 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1277 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 47 | 3.8% |
| `year_spelled_out_for_tts_not_a_defect` | 26 | 2.1% |
| `year_dropped_with_reference_apparatus` | 19 | 1.5% |
| `truncated_sentence` | 13 | 1.0% |
| `year_lost` | 12 | 1.0% |
| `absent_from_artifact` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 47

**`narration#2`, исходный абзац:**

> —

**в озвучке:**

> Создание и присвоение в мировой экономике

**`narration#5`, исходный абзац:**

> —

**в озвучке:**

> [serious] Ценность в глазах смотрящего: расцвет маржинализма

**`narration#9`, исходный абзац:**

> —

**в озвучке:**

> [serious] Недостаточно просто подлатать национальные счета

---

### `year_spelled_out_for_tts_not_a_defect` — 26

**`p0005`, исходный абзац:**

> 2018

**в озвучке:**

> [serious] Две тысячи восемнадцатый год.

**`p0114`, исходный абзац:**

> A variation of this debate about where to draw the production boundary continues today with the financial sector. After the 2008 financial crisis, there were calls from many quarters for a revival of industrial policy to boost the ‘makers’ in industry, who were seen to be pitted against the ‘takers’ in finance. It was argued that rebalancing was needed to shrink the size of the financial sector (falling into the dark grey circle of unproductive activities above) by taxation, for example a tax on financial transactions such as foreign exchange dealing or securities trading, and by industrial policies to nurture growth in industries that actually made things instead of just exchanging them (falling into the light grey circle of productive activities above).

**в озвучке:**

> [thoughtful] Споры о том, где именно проводить границу производства, продолжаются и сегодня, особенно в отношении финансового сектора. После кризиса две тысячи восьмого года многие призывали возродить промышленную политику, чтобы поддержать «созидателей» в реальном секторе экономики. Их противопоставляли «извлекателям» из финансовой сферы. Звучали аргументы, что нужно сбалансировать экономику и ограничить размеры финансового сектора — который в нашей схеме попадает в зону непроизводительной деятельности. Предлагались разные меры: от налогов на финансовые операции, например, на валютные или биржевые сделки, до промышленной политики, направленной на рост отраслей, где действительно создаются товары, а не просто перераспределяются активы.

**`p0208`, исходный абзац:**

> As industry developed rapidly through the eighteenth and nineteenth centuries, so too did the ideas of a succession of outstanding thinkers like Adam Smith (1723–90), David Ricardo (1772–1823) and Karl Marx (1818–83), a German who did much of his greatest work in England.

**в озвучке:**

> [serious] По мере того как в восемнадцатом и девятнадцатом веках промышленность стремительно развивалась, менялись и взгляды выдающихся мыслителей того времени. Среди них были Адам Смит, живший с тысяча семьсот двадцать третьего по тысяча семьсот девяностый год, Давид Рикардо, живший с тысяча семьсот семьдесят второго по тысяча восемьсот двадцать третий, и Карл Маркс, немецкий мыслитель, который создал свои главные труды в Англии.

---

### `year_dropped_with_reference_apparatus` — 19

**`p0172`, исходный абзац:**

> Seventeenth-century Britain saw two groundbreaking attempts to quantify national income. One was by Sir William Petty (1623–87), an adventurer, anatomist, physician and Member of Parliament, who was a tax administrator in Ireland under Oliver Cromwell’s Commonwealth government.⁵ The other was by the herald Gregory King (1648–1712), a genealogist, engraver and statistician whose work on enacting a new tax on marriages, births and burials provoked his interest in national accounting.

**в озвучке:**

> В Британии семнадцатого века были предприняты две новаторские попытки количественно оценить национальный доход. Одну из них совершил сэр Уильям Петти — авантюрист, анатом, врач и член парламента, работавший налоговым администратором в Ирландии при правительстве Оливера Кромвеля. Другую — герольд Грегори Кинг, генеалог, гравер и статистик, чей интерес к национальному учету возник во время работы над введением нового налога на браки, рождения и погребения.

**`p0189`, исходный абзац:**

> The first efforts to find a formal theory of value came in the mid-eighteenth century from the court of Louis XV of France, in the twilight – so it turned out – of that country’s absolute monarchy. There, François Quesnay (1694–1774), often described as the ‘father of economics’, was the king’s physician and adviser. He used his medical training to understand the economy as a ‘metabolic’ system. Crucially, in metabolism, everything must come from somewhere and go somewhere – and that, for Quesnay, included wealth. Quesnay’s approach led him to formulate the first systematic theory of value that classified who is and is not productive in an economy, and to model how the entire economy could reproduce itself from the value generated by a small group of its members. In his seminal work *Tableau Économique*, published in 1758, he constructed an ‘economic table’ which showed how new value was

**в озвучке:**

> [thoughtful] Первые попытки создать формальную теорию стоимости были предприняты в середине восемнадцатого века при дворе французского короля Людовика Пятнадцатого, в период заката абсолютной монархии. Франсуа Кенэ, которого часто называют «отцом экономики», служил там придворным врачом и советником. Он использовал свои медицинские знания, чтобы представить экономику как «метаболическую» систему. В обмене веществ всё должно откуда-то приходить и куда-то уходить — и для Кенэ это было верно и в отношении богатства. Его подход позволил сформулировать первую систематическую теорию стоимости, которая разделяла участников экономики на продуктивных и непродуктивных. Он также смоделировал, как вся экономика может воспроизводить себя за счёт ценности, создаваемой небольшой группой людей. В своей фундаментальной работе «Экономическая таблица», опубликованной в 1758 году, он построил схему, показыв

**`p0313`, исходный абзац:**

> Socialist critiques of value theory were multiplying even before Marx wrote *Capital*. A group called the ‘Ricardian socialists’ used Ricardo’s labour theory of value to demand that workers get better wages. They included the Irishman William Thompson (1775–1833), Thomas Hodgskin (1787–1869) and John Gray (1799–1883), both British, and John Bray (1809–97), who was born in the US but worked for part of his life in Britain. Together, they made the obvious argument that if the value of commodities derives from labour, the revenue from their sale should go to workers. This idea underlay the co-operativism of the textile manufacturer Robert Owen (1771–1858), for whom the solution was that workers should also participate in ownership, of both factories and publicly created infrastructure. Marx and Engels were friendly with some of these groups, but very unfriendly towards others whom they thou

**в озвучке:**

> [thoughtful] Социалистическая критика теории стоимости набирала обороты еще до того, как Карл Маркс написал «Капитал». Группа мыслителей, известных как «рикардианские социалисты», опиралась на трудовую теорию стоимости Давида Рикардо, требуя повышения заработной платы для рабочих. В эту группу входили ирландец Уильям Томпсон, британцы Томас Ходжскин и Джон Грей, а также Джон Брей, который родился в Соединенных Штатах, но часть жизни провел в Британии. Все они приводили простой аргумент: если стоимость товаров создается трудом, то и доход от их продажи должен принадлежать рабочим. Эта идея легла в основу кооперативного движения текстильного фабриканта Роберта Оуэна. Он считал, что рабочие должны участвовать в управлении собственностью — как на заводах, так и в объектах общественной инфраструктуры. Маркс и Энгельс поддерживали дружеские отношения с некоторыми из этих групп, но резко критик

---

### `truncated_sentence` — 13

**`narration#222`, исходный абзац:**

> —

**в озвучке:**

> [serious] В 1810-х годах еще одна выдающаяся фигура английской классической экономической школы использовала трудовую теорию стоимости и понятие производительности, чтобы объяснить, как общество поддерживает условия для собственного воспроизводства. Дэвид Рикардо происходил из семьи сефардских евреев, которая перебралась из Португалии в Голландию, а затем обосновалась в Англии. Рикардо пошел по стопам отца, став лондонским биржевым маклером, хотя позже порвал с семьей, приняв унитарианство. Он сказочно разбогател на спекуляциях, в частности, на использовании инсайдерской информации о битве при Ватерлоо в

**`narration#263`, исходный абзац:**

> —

**в озвучке:**

> Раньше экономисты рассматривали капитал как нечто сугубо материальное — например, станки или здания, — а прибавочный продукт считали исключительно позитивным явлением, помогающим экономике воспроизводиться и расти. Маркс же придает капиталу социальное измерение, а прибавочному продукту — негативный оттенок. Труд создает прибавочную стоимость, которая питает накопление капитала и экономический рост. Однако накопление капитала обусловлено не только производительным трудом. Оно глубоко социально. Поскольку рабочие не владеют средствами производства, они оказываются

**`narration#316`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Маршалл настолько стремился подчеркнуть уравновешивающие и эволюционные силы в экономике с их плавными кривыми, поддающимися математическому описанию, что эпиграфом к его работе 1890 года

---

### `year_lost` — 12

**`p0169`, исходный абзац:**

> Scholars and politicians of the time who argued that accumulating precious metals was the route to national power and prosperity are called mercantilists (from *mercator*, the Latin word for merchant), because they espoused protectionist trade policies and positive trade balances to stimulate the inflow, and prevent the outflow, of gold and silver. The best-known English advocate of mercantilism was a merchant and director of the East India Company called Sir Thomas Mun (1571–1641). In his influential book *England’s Treasure by Forraign Trade*, Mun summed up the mercantilist doctrine: we must, he said, ‘sell more to strangers yearly 4 than wee consume of theirs in value’.

**в озвучке:**

> Ученых и политиков того времени, утверждавших, что накопление драгоценных металлов — это путь к национальной мощи и процветанию, называют меркантилистами. Само слово происходит от латинского «mercator», что значит «купец». Они выступали за протекционистскую торговую политику и положительное сальдо торгового баланса, чтобы стимулировать приток золота и серебра и предотвратить их отток. Самым известным английским сторонником меркантилизма был купец и директор Ост-Индской компании сэр Томас Ман. В своей влиятельной книге «Богатство Англии во внешней торговле» Ман подытожил доктрину меркантилизма: мы должны, писал он, ежегодно продавать иностранцам товаров больше, чем мы потребляем их товаров по стоимости.

**`p0244`, исходный абзац:**

> Ricardo inherited this ‘dismal theory’ of wages from his contemporary Thomas Malthus (1766–1834), another English writer on political economy, who proposed that whenever real wages are above subsistence level, the population will grow until it is so large that the demand for food 35 will push up food prices enough to bring wages back to subsistence level.

**в озвучке:**

> Эту «мрачную теорию» заработной платы Рикардо унаследовал от своего современника Томаса Мальтуса. Тот полагал, что всякий раз, когда реальная зарплата превышает прожиточный минимум, население растет до тех пор, пока спрос на еду не поднимет цены настолько, что зарплаты снова вернутся к уровню выживания.

**`p0303`, исходный абзац:**

> All these issues have come to the fore again since the 2008 financial crisis. At their heart is how finance has been self-serving, and not actually serving what the American economist Hyman Minsky (1919–96) called the ‘capital development of the economy’.⁶¹ In other words, instead of facilitating industrial production, finance has simply degenerated into a casino, aiming to appropriate as much of the existing surplus as possible for itself.⁶² But whether that casino is seen as a mere imperfection or as a stable source of unearned income (whereby activities that are not creating value are somehow allowed to be presented a such) makes all the difference in policies that aim to reform the system.

**в озвучке:**

> [serious] Все эти вопросы вновь вышли на первый план после финансового кризиса 2008 года. В их основе лежит проблема того, что финансовый сектор стал работать на самого себя, а не на то, что американский экономист Хайман Мински называл «капитальным развитием экономики». Иными словами, вместо того чтобы способствовать промышленному производству, финансы превратились в своего рода казино. Их главная цель — присвоить как можно большую часть уже созданного прибавочного продукта. Однако то, как мы воспринимаем это «казино» — как досадную помеху или как устойчивый источник нетрудовых доходов, — принципиально меняет подход к реформированию всей системы.

---

### `absent_from_artifact` — 1

**`p0989`, исходный абзац:**

> ### NETWORK EFFECTS AND FIRST-MOVER ADVANTAGES

**в озвучке:**

> None

---
