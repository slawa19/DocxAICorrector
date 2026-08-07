# Аудиокнига, прогон четырёх книг 2026-08-06 — value_of_everything, материал для просмотра глазами

Книга: Mariana Mazzucato, *The Value of Everything* (`tests/sources/book/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_ab4_value_of_everything`. Seed выборки: `20260804` (тот же, что 2026-08-04).

Пары «исходный абзац → что попало в озвучку» взяты из перехваченного трафика к модели:
в запросе каждый абзац помечен маркером `[[DOCX_PARA_...]]`, в ответе — тем же маркером,
поэтому сопоставление точное, а не восстановленное по тексту.

В файл попадают только те абзацы, чей озвученный текст **дословно присутствует в итоговом
narration-артефакте** (`.tts.txt`) после того же `strip_markdown_for_narration`, который
применяет пайплайн.

**Про метрику.** Озвучка — это перевод с английского на русский, поэтому посимвольный
diff «до/после» равен ~100 % у всех абзацев и ничего не ранжирует. Крайние случаи отобраны по
`длина озвучки / длина оригинала`: сильное сжатие — там, где содержание могло потеряться.
«Самые нетронутые» — по посимвольному совпадению с оригиналом.

## Что в файле

1. **Случайная выборка, 49 абзацев прозы** — до 20 из первой, средней и последней трети книги,
   `random.Random(20260804)`, без отбора «по красоте».
2. **20 абзацев с максимальным сжатием** — низ списка по отношению длин.
3. **10 абзацев с максимальным раздуванием** — верх того же списка.
4. **10 самых буквальных абзацев** — максимальное совпадение символов с оригиналом.
5. **0 абзацев, оставшихся в озвучке на английском** (порог ≥ 60 букв, кириллицы < 30 %).
6. **Пустые и почти пустые абзацы — все 7**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1247; вернулось: 1247;
дошло до narration-артефакта: 1247.
Пул прозы, из которого делалась выборка: 813 абзацев.
Медианное отношение длин по прозе: 1.0306.

---
## Случайная выборка (49 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0055` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> If there are so many wealth creators in industry, the inevitable conclusion is that at the opposite side of the spectrum featuring fleet-footed bankers, science-based pharmaceuticals and entrepreneurial geeks are the inert, value-extracting civil servants and bureaucrats in government. In this view, if private enterprise is the fast cheetah bringing innovation to the world, government is a plodding tortoise impeding progress – or, to invoke a different metaphor, a Kafkaesque bureaucrat, buried under papers, cumbersome and inefficient. Government is depicted as a drain on society, funded by obligatory taxes on long-suffering citizens. In this story, there is always only one conclusion: that we need more market and less state. The slimmer, trimmer and more efficient the state machine the better.

**В озвучку попало:**

> [serious] Если в промышленности так много «создателей богатства», то напрашивается вывод: на другом полюсе, в противовес шустрым банкирам, ученым-фармацевтам и предприимчивым гикам, находятся инертные, извлекающие выгоду государственные служащие и бюрократы. В этой картине мира частный бизнес — это быстрый гепард, несущий миру инновации, а правительство — медлительная черепаха, тормозящая прогресс. Или, если использовать другую метафору, кафкианский бюрократ, заваленный бумагами, неповоротливый и неэффективный. Государство изображается как обуза для общества, существующая за счет обязательных налогов с многострадальных граждан. В этой истории вывод всегда один: нам нужно больше рынка и меньше государства. Чем стройнее и эффективнее государственный аппарат, тем лучше.

---

### 2. `p0081` — длина озвучки / длина оригинала: 1.16; классы правки: —

**Исходный абзац:**

> It is clear that Apple’s highly complex tax arrangements were principally designed to extract the maximum value from its business by avoiding paying substantial taxes which would have benefited the societies in which the company operated. Apple certainly creates value, of that there is no doubt: but to ignore the support taxpayers have given it, and then to pit states and countries against each other, is surely not the way to build an innovative economy or achieve growth that is inclusive, that benefits a wide section of the population, not only those best able to ‘game’ the system.

**В озвучку попало:**

> [serious] Очевидно, что сложнейшие налоговые схемы Apple были разработаны прежде всего для извлечения максимальной выгоды. Компания стремилась избежать уплаты значительных налогов, которые могли бы принести пользу обществам, где она вела свою деятельность. Безусловно, Apple создает ценность, в этом нет никаких сомнений. Однако игнорировать поддержку, которую ей оказали налогоплательщики, и при этом стравливать между собой штаты и целые страны — это явно не тот путь, который ведет к созданию инновационной экономики. Такой подход не способствует инклюзивному росту, который приносил бы пользу широким слоям населения, а не только тем, кто лучше всех умеет «обыгрывать» систему.

---

### 3. `p0098` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> For a long time the idea of value was at the heart of debates about the economy, production and the distribution of the resulting income, and there were healthy disagreements over what value actually resided in. For some economic schools of thought, the price of products resulted from supply and demand, but the value of those products derived from the amount of work that was needed to produce things, the ways in which technological and organizational changes were affecting work, and the relations between capital and labour. Later, this emphasis on ‘objective’ conditions of production, technology and power relationships was replaced by concepts of scarcity and the ‘preferences’ of economic actors: the amount of work supplied is determined by workers’ preference for leisure over earning a higher amount of money. Value, in other words, became *subjective*.

**В озвучку попало:**

> Долгое время вопрос о том, что такое ценность, был центральным в дискуссиях об экономике, производстве и распределении доходов. Вокруг него велись серьезные споры. Некоторые экономические школы полагали, что цена товара определяется спросом и предложением, но сама ценность продукта зависит от объема труда, затраченного на его создание, от влияния технологических и организационных изменений на этот труд, а также от отношений между капиталом и наемными работниками. Позже этот акцент на «объективных» условиях производства, технологиях и отношениях власти сменился концепциями дефицита и «предпочтений» экономических субъектов. Согласно им, объем предлагаемого труда определяется тем, что работники предпочитают отдых заработку больших денег. Иными словами, ценность стала субъективной.

---

### 4. `p0118` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Indeed, the recurring debate about the optimal size of government and the supposed perils of high public debt boils down to whether government spending helps the economy to grow – because government can be productive and add value – or whether it holds back the economy because it is unproductive or even destroys value*.* The issue is politically loaded and deeply colours current debates, ranging from whether the UK can afford Trident nuclear weapons to whether there is a ‘magic number’ for the size of government, defined as government spending as a proportion of national output, beyond which an economy will inevitably do less well than it might have done if government spending had been lower. As we will explore in Chapter 8, this question is more tainted by political views and ideological positions than informed by deep scientific proofs. Indeed, it is important to remember that economics is at heart a social science, and the ‘natural’ size of government will depend on one’s theory of (or simply ‘position’ on) the purpose of government. If it is seen as useless, or at best a fixer of occasional problems, its optimum size will inevitably be notionally smaller than if it is viewed as a key engine of growth needed to steer and invest in the value creation process.

**В озвучку попало:**

> [serious] Постоянные дебаты об оптимальном размере государства и опасностях высокого государственного долга сводятся к одному. Помогают ли государственные расходы экономическому росту, поскольку государство может быть производительным и добавлять стоимость? Или же они сдерживают экономику, будучи непроизводительными или даже разрушительными? Этот вопрос политизирован и глубоко влияет на современные дискуссии. Спектр мнений широк: от того, может ли Великобритания позволить себе ядерное оружие «Трайдент», до поиска «магического числа» размера государства. Многие считают, что если доля госрасходов в национальном продукте превысит некий предел, экономика неизбежно начнет отставать. Как мы увидим в восьмой главе, этот вопрос больше пропитан политическими взглядами и идеологией, чем подкреплен строгими научными доказательствами. Важно помнить, что экономика — это прежде всего социальная наука. «Естественный» размер государства зависит от того, какой теории вы придерживаетесь и какова, по вашему мнению, цель государства. Если вы считаете его бесполезным или лишь «пожарным», исправляющим случайные проблемы, то его оптимальный размер в ваших глазах будет меньше. Если же вы видите в государстве ключевой двигатель роста, необходимый для инвестиций и управления процессом создания стоимости, то взгляд на его роль будет иным.

---

### 5. `p0124` — длина озвучки / длина оригинала: 0.85; классы правки: —

**Исходный абзац:**

> Second, the lack of analysis of value has massive implications for one particular area: the distribution of income between different members of society. When value is determined by price (rather than vice versa), the level and distribution of income seem justified as long as there is a market for the goods and services which, when bought and sold, generate that income. All income, according to this logic, is earned income: gone is any analysis of activities in terms of whether they are productive or unproductive.

**В озвучку попало:**

> Во-вторых, отсутствие анализа стоимости имеет серьезные последствия для распределения доходов между членами общества. Когда стоимость определяется ценой, а не наоборот, уровень и распределение доходов кажутся оправданными до тех пор, пока существует рынок для товаров и услуг, приносящих этот доход. Согласно такой логике, любой доход считается заработанным. Исчезает само понятие разделения деятельности на продуктивную и непроизводительную.

---

### 6. `p0130` — длина озвучки / длина оригинала: 1.18; классы правки: —

**Исходный абзац:**

> Once impediments to competition are removed, the outcome should benefit everyone. How different notions of value might affect the distribution of revenues between workers, public agencies, managers and shareholders at, say, Google, General Electric or BAE Systems, goes unquestioned.

**В озвучку попало:**

> Предполагается, что как только препятствия для конкуренции будут устранены, результат принесет пользу всем. Вопрос о том, как разные представления о стоимости влияют на распределение доходов между работниками, госорганами, менеджерами и акционерами в компаниях вроде «Гугл», «Дженерал Электрик» или «БАЕ Системс», остается без ответа.

---

### 7. `p0151` — длина озвучки / длина оригинала: 1.05; классы правки: truncated_sentence

**Исходный абзац:**

> To create a fairer economy, one where prosperity is more broadly shared and is therefore more sustainable, we need to reinvigorate a serious discussion about the nature and origin of value. We must reconsider the stories we are telling about who the value creators are, and what that says to us about how we define activities as economically productive and unproductive. We cannot limit progressive politics to taxing wealth, but require a new understanding of and debate about wealth creation so that it is more fiercely and openly contested. Words matter: we need a new vocabulary for policymaking. Policy is not just about ‘intervening’. It is about shaping a different future: co-creating markets and value, not just ‘fixing’ markets or redistributing value. It’s about taking risks, not only

**В озвучку попало:**

> Чтобы построить более справедливую экономику, где процветание распределяется шире и потому является более устойчивым, нам нужно возобновить серьезный разговор о природе и происхождении ценности. Мы должны переосмыслить истории, которые мы рассказываем о том, кто такие «создатели ценности» и как мы определяем, является ли деятельность экономически продуктивной. Мы не можем ограничивать прогрессивную политику одним лишь налогообложением богатства. Нам нужно новое понимание процесса создания богатства, чтобы этот вопрос стал предметом открытой и острой борьбы. Слова имеют значение: нам нужен новый словарь для формирования политики. Политика — это не просто «вмешательство». Это формирование будущего: совместное создание рынков и ценности, а не просто их «исправление» или перераспределение. Речь идет о принятии рисков, а не только о

---

### 8. `p0153` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> This idea that we can shape markets has important consequences. We can create a better economy by understanding that markets are outcomes of decisions that are made – in business, in public organizations and in civil society. The eight-hour working day has formed markets – and that was the result of a fight held in labour organizations. And perhaps the reason there is so much despair across the globe – despair now leading to populist politics – is that the economy is presented to us simply as ‘made’ by trade rules, technocrats and neoliberal forces. Indeed, as the book will show, ‘value’ theory itself is presented as a sort of objective force determined by supply and demand, rather than deeply embedded in particular ways of seeing the world. The economy can indeed be made and shaped – but it can be done either in fear or in hope.

**В озвучку попало:**

> [thoughtful] Идея о том, что мы способны формировать рынки, имеет важные последствия. Мы можем создать более совершенную экономику, если осознаем, что рынки — это результат принимаемых решений: в бизнесе, в государственных организациях и в гражданском обществе. Например, восьмичасовой рабочий день сформировал определенные рыночные условия, и это стало итогом борьбы профсоюзов. Возможно, причина повсеместного отчаяния, которое сегодня подпитывает популизм, кроется в том, что нам преподносят экономику как нечто неизбежное, созданное лишь торговыми правилами, технократами и неолиберальными силами. На самом деле, как показано в этой книге, сама теория ценности подается как объективная сила, определяемая спросом и предложением, хотя на деле она глубоко укоренена в конкретных взглядах на мир. Экономику действительно можно создавать и менять, но делать это можно либо из страха, либо с надеждой.

---

### 9. `p0232` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> Smith’s penetrating analysis of how advanced capitalist economies functioned won him many followers. Equally, his staunch advocacy of free trade, in an era in which mercantilist policies were beginning to be seen as old-fashioned (Smith, indeed, believed that merchants were unproductive because they only provided the ephemeral service of moving goods around, rather than producing anything of value), made his book a hit among the ‘free traders’ who eventually overturned England’s Corn Laws, which imposed heavy tariffs on imported corn to protect domestic landowners, and other protectionist measures. Armed with Smith’s ideas, free traders showed that nations could get richer even if there was no trade surplus and no gold accumulation. Amassing gold was unnecessary and insufficient for growth. Huge amounts of gold flowed to Spain from its colonies, but the kingdom did not become more productive.

**В озвучку попало:**

> Проницательный анализ того, как функционируют развитые капиталистические экономики, принес Смиту множество последователей. В эпоху, когда меркантилистская политика начала казаться устаревшей, его решительная поддержка свободной торговли сделала книгу хитом среди сторонников фритрейдерства. Именно они в итоге добились отмены «хлебных законов» Англии, которые вводили высокие пошлины на импортное зерно для защиты местных землевладельцев, и других протекционистских мер. Вооружившись идеями Смита, сторонники свободной торговли доказали, что нации могут богатеть, даже если у них нет торгового профицита и накоплений золота. Накопление золота было излишним и недостаточным условием для роста. Огромное количество золота текло в Испанию из ее колоний, но само королевство не стало от этого более производительным.

---

### 10. `p0294` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Marx then identified ‘interest-bearing’ capital – capitalists such as banks who earned interest on loans that production capitalists took out to expand production. The generation of interest is possible because, in capitalism, money represents not just purchasing power – buying commodities for consumption – but also the potential to generate more profit in the future through investment as capital.⁵⁷ The interest is deducted from the production capitalist’s profit rate. Interest-bearing capital, unlike commercial capital, does not lower the general rate of profit; it just subdivides it between recipients of interest and earners of profit.

**В озвучку попало:**

> [thoughtful] Маркс также выделил «ссудный» капитал. Это капиталисты, например банки, которые получают доход в виде процентов по займам, выданным производственным предприятиям для расширения их деятельности. Получение процентов возможно потому, что в условиях капитализма деньги — это не просто покупательная способность для приобретения товаров, но и потенциал для извлечения будущей прибыли через инвестиции. Проценты вычитаются из прибыли производственного капиталиста. В отличие от торгового капитала, ссудный капитал не снижает общую норму прибыли, а лишь распределяет её между теми, кто получает проценты, и теми, кто зарабатывает прибыль.

---

### 11. `p0323` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> The marginal utility theory of value states that all income is reward for a productive undertaking. Given the large investments being made in factories and the edifices of the Industrial Revolution, it suited the changing circumstances of the second half of the nineteenth century. But it did not come out of nowhere; indeed, it has a long history. In medieval times, thinkers argued that ‘just prices’ were those that reflected an object’s utility. In his *Summa Theologica*, the thirteenth century philosopher-theologian Thomas Aquinas discussed the concept of the just price in a section of the book called ‘Of Cheating, Which Is Committed in Buying and Selling’. Just price was a normative concept, against what was seen as the wrong price resulting from morally evil greed. The medieval Church inveighed against the sin of greed and avarice, which broadly meant profiteering by middlemen and moneylenders. In Dante’s *Inferno*, usurers are consigned to the hottest part of hell (circle 7) because they are making money not from the productive sources, which for Dante were Nature or Art, but from speculative changes in interest rates. Indeed, he is so disgusted by usury that he puts usurers just below the circle of hell housing the sodomites.

**В озвучку попало:**

> Теория предельной полезности утверждает, что любой доход — это вознаграждение за продуктивную деятельность. Учитывая огромные инвестиции в заводы и инфраструктуру промышленной революции, такая концепция хорошо вписалась в меняющиеся реалии второй половины девятнадцатого века. Однако она не возникла на пустом месте; у неё долгая история. В Средние века мыслители доказывали, что «справедливые цены» — это те, что отражают полезность объекта. В своей «Сумме теологии» философ и теолог тринадцатого века Фома Аквинский обсуждал понятие справедливой цены в разделе «Об обмане, совершаемом при купле и продаже». Справедливая цена тогда была нормативным понятием, противопоставленным «неправильной» цене, продиктованной греховной жадностью. Средневековая церковь выступала против греха алчности, под которым в широком смысле понималась нажива посредников и ростовщиков. В «Аде» Данте ростовщики попадают в самую жаркую часть ада — седьмой круг, — потому что они извлекают прибыль не из продуктивных источников, которыми для Данте были природа или искусство, а из спекулятивных изменений процентных ставок. Данте настолько презирал ростовщичество, что поместил ростовщиков даже ниже круга, где мучились содомиты.

---

### 12. `p0329` — длина озвучки / длина оригинала: 1.14; классы правки: truncated_sentence

**Исходный абзац:**

> At some point the utility gained from eating them will decrease.⁷ In this way, the utility of the last bar is less, possibly much less, than that of earlier bars. This is ‘marginal utility’ – in the case of a Mars Bar, worth less to you than the previous one, ‘decreasing marginal utility’. By the same token, the scarcer a thing is, the more utility it gives you –

**В озвучку попало:**

> В какой-то момент полезность от поедания батончиков начнет снижаться. Таким образом, полезность последнего съеденного батончика меньше, а возможно, и гораздо меньше, чем у предыдущих. Это и есть «предельная полезность». В случае с батончиком «Марс» для вас он стоит меньше, чем предыдущий — это называется «убывающей предельной полезностью». По той же логике, чем дефицитнее вещь, тем больше полезности она вам дает —

---

### 13. `p0473` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> As with the absurdity of neighbours paying each other to do their housework, it is as if the statisticians are saying that a nation of owner-occupiers could artificially amplify GDP by swapping homes with their neighbours and paying rent to one another. Statisticians have fiercely defended their treatment of income from property. But when real-estate prices appreciate rapidly, as in the US and the UK before 2007 and in hot-spots such as London even after the financial crisis, there are alarming implications for measuring. Rising house prices mean rising implicit rentals, and hence rising incomes when the implicit rental is included. The paradoxical result is that a house price bubble, perhaps caused by low interest rates or relaxed lending conditions, will show up as an acceleration of GDP growth. Why? Because households’ services to themselves – as their own landlords, charging themselves implicit rentals – are suddenly rising in value, and that is counted as income which adds to GDP. By the same token, if you strip out those imputed rentals, GDP can be shown to have risen more slowly in the years before the financial crash than after 33 2009.

**В озвучку попало:**

> Ситуация напоминает абсурдную картину, когда соседи платят друг другу за уборку в доме. Статистики как будто намекают: нация домовладельцев могла бы искусственно раздуть ВВП, просто обмениваясь жильем и выплачивая друг другу аренду. Специалисты яростно защищают такой подход к доходам от недвижимости. Однако, когда цены на жилье стремительно растут — как это было в США и Великобритании до 2007 года или в Лондоне даже после финансового кризиса, — возникают тревожные последствия для расчетов. Рост цен на дома означает рост «условной аренды», а значит, и рост доходов, если учитывать эту условную величину. В итоге возникает парадокс: «пузырь» на рынке жилья, вызванный низкими процентными ставками или мягкими условиями кредитования, выглядит как ускорение роста ВВП. Почему? Потому что услуги, которые домохозяйства оказывают сами себе, выступая в роли собственных арендодателей, внезапно растут в цене. Это засчитывается как доход, увеличивающий ВВП. Если исключить такую условную аренду из расчетов, окажется, что в годы перед финансовым крахом ВВП рос гораздо медленнее, чем после 2009 года.

---

### 14. `p0477` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> National accountants present this question of whether something is ‘analytically useful’ or not as a vague argument, without reference to value. To be fair, they also rightly caution that it would be extremely difficult comprehensively to cost such externalities – negative or positive ‘side effects’ of production – which are not priced. All of which just highlights the difficulties of being consistent and drawing a clear production boundary.

**В озвучку попало:**

> Национальные бухгалтеры представляют вопрос о том, что является «аналитически полезным», как нечто расплывчатое, не опираясь на понятие ценности. Справедливости ради, они также резонно предостерегают, что крайне сложно всесторонне оценить такие внешние эффекты — негативные или позитивные «побочные продукты» производства, — у которых нет рыночной цены. Все это лишь подчеркивает трудности в соблюдении последовательности и проведении четкой границы производства.

---

### 15. `p0478` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> So while Marshall claimed that Nature does not make jumps (recall the discussion of *natura non facit saltus* in Chapter 2), national income, it appears, can do so! If self-employment (referred to as own-account production for small farming or sex workers, for example) grows in importance, or if a way can be found to cost externalities, national income will jump when the statisticians decide to include it.

**В озвучку попало:**

> [short pause] Альфред Маршалл утверждал, что природа не делает скачков. Но, как мы видим, национальный доход на них способен! Если самозанятость — например, в мелком фермерстве или секс-индустрии — станет играть более заметную роль, или если будет найден способ оценивать внешние эффекты, национальный доход совершит скачок, как только статистики решат включить эти данные в отчетность.

---

### 16. `p0543` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> Governments viewed regulation as essential, because a long international history of bank crashes and failed or fraudulent investment schemes showed how, left to themselves, financial firms could easily lose depositors’ money and, in so doing, disrupt real economic activity and even cause social unrest. When banks competed, they tended to offer ever more improbably high returns to savers by funding ever more risky investment projects, until disaster (and bankruptcy) struck. But while such competitive instability was averted by restricting entry, and giving banks some monopoly power, they still inflicted damage on the rest of the economy in other ways – by artificially inflating the price of loans, and co-ordinating their buying and selling to cause artificial boom and bust in the prices of key commodities. Small banks were especially vulnerable because their (and clients’) activities were insufficiently spread across different industries and geographical regions. But big banks quickly became ‘too big to fail’, assured of expensive government rescue when overextended because their collapse would do too much economic damage. Such assurances only led them to behave even more recklessly.

**В озвучку попало:**

> [serious] Правительства считали регулирование необходимым. Многолетняя история международных банковских кризисов, а также провальных или мошеннических инвестиционных схем показывала: если оставить финансовые фирмы без присмотра, они легко могут потерять деньги вкладчиков. Это подрывает реальную экономику и даже ведет к социальным потрясениям. Когда банки конкурировали между собой, они стремились предложить вкладчикам нереалистично высокую прибыль. Для этого они финансировали всё более рискованные проекты, пока не наступала катастрофа и банкротство. Но даже когда конкурентную нестабильность удавалось сдержать, ограничивая вход на рынок и предоставляя банкам некоторую монопольную власть, они всё равно вредили экономике. Они искусственно завышали стоимость кредитов и координировали свои действия при купле-продаже, чтобы создавать искусственные взлеты и падения цен на ключевые товары. Небольшие банки были особенно уязвимы, так как их деятельность и деятельность их клиентов была недостаточно диверсифицирована по отраслям и регионам. Однако крупные банки быстро становились «слишком большими, чтобы обанкротиться». Они были уверены, что в случае проблем получат дорогостоящую государственную помощь, ведь их крах нанес бы слишком большой ущерб экономике. Такие гарантии лишь подталкивали их к еще более безрассудному поведению.

---

### 17. `p0546` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> During this time, banks never ceased to lobby against the regulations that deprived them of significant markets, and others (like the Glass– Steagall Act) which restricted their scope to combine operations in different markets. As well as pushing for an end to regulations, banks proved adept at persuading politicians that restrictive regulations were unworkable, by finding ways to work around them. Bans on speculative derivatives trading, enacted in the US in the 1930s because of its role in magnifying the 1929 Crash and Great Depression, were effectively sidestepped by the growth of unregulated over-the-counter derivatives trading, which grew explosively in the 1980s and defied subsequent efforts at re-regulation.¹³ Banks’ invention of ‘offshore’ currencies, to sidestep cross-border capital controls, was especially effective. In 1944, the Bretton Woods system had pegged the value of the dollar to gold. But when the post-war boom, based on manufacturing, tailed off around 1970, ‘light-touch’ financial regulation increasingly appealed to policymakers on both sides of the Atlantic. The financial sector reacted to this interest by developing a new currency, the Eurodollar.

**В озвучку попало:**

> В это время банки не прекращали лоббировать отмену правил, которые лишали их значительных рынков, или ограничивали возможность объединять операции в разных сферах, как это делал закон Гласса — Стиголла. Помимо давления за отмену регулирования, банки мастерски убеждали политиков в неработоспособности ограничительных мер, находя способы их обходить. Запреты на торговлю спекулятивными деривативами, введенные в США в тридцатых годах из-за их роли в усилении краха 1929 года и Великой депрессии, были фактически обойдены за счет роста нерегулируемой внебиржевой торговли деривативами. Она бурно развивалась в восьмидесятые годы и игнорировала последующие попытки повторного регулирования. Изобретение банками офшорных валют для обхода трансграничного контроля над капиталом оказалось особенно эффективным. В 1944 году Бреттон-Вудская система привязала стоимость доллара к золоту. Но когда послевоенный бум, основанный на производстве, пошел на спад около 1970 года, «мягкое» финансовое регулирование стало всё больше привлекать политиков по обе стороны Атлантики. Финансовый сектор отреагировал на этот интерес развитием новой валюты — евродоллара.

---

### 18. `p0557` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Their reasoning was as follows. To maintain their high profits, the big commercial and investment banks still needed regulators who would keep potential competitors out of the market. Existing big players are therefore helped if banking licences are restricted. Ironically, the disastrous big bank behaviour that triggered the 2008 crash forced regulators (especially in Europe) into further lengthening and complicating an already arduous process for obtaining a new licence, frustrating their plans to unleash a hungry horde of ‘challenger banks’. In issuing licences sparingly, governments and central banks were quietly admitting something they were still reluctant to announce publicly: the extraordinary power of private-sector bank lending to affect the pace of money creation, and therefore economic growth.

**В озвучку попало:**

> Их логика была проста. Чтобы поддерживать высокую прибыль, крупным коммерческим и инвестиционным банкам по-прежнему нужны были регуляторы, которые не пускали бы на рынок потенциальных конкурентов. Поэтому существующим игрокам выгодно, чтобы получение банковских лицензий было ограничено. Ирония в том, что катастрофическое поведение крупных банков, приведшее к кризису 2008 года, вынудило регуляторов — особенно в Европе — еще больше усложнить и затянуть процесс получения новой лицензии. Это фактически сорвало планы по привлечению на рынок множества новых «банков-претендентов». Выдавая лицензии крайне скупо, правительства и центральные банки молчаливо признавали то, о чем не хотели говорить публично: частные банки обладают колоссальной властью. Они влияют на темпы создания денег, а значит, и на экономический рост.

---

### 19. `p0580` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Lord Adair Turner, who took over as Chair of the UK financial regulator (then called the Financial Services Authority) in 2008, just as the system was crashing around it, reflected when the dust settled that: ‘financial services (particularly wholesale trading activities) include a large share of highly remunerated activities that are purely distributive in their indirect effects … the ability of national income accounts to distinguish between activities that are meaningfully value-creative and activities that are 30 essentially distributive rent extraction is far from perfect’.

**В озвучку попало:**

> [serious] Лорд Адер Тёрнер возглавил британский финансовый регулятор, тогда известный как Управление по финансовым услугам, в 2008 году, прямо в разгар краха системы. Когда ситуация стабилизировалась, он заметил: «Финансовые услуги, особенно оптовая торговля, включают в себя огромную долю высокооплачиваемой деятельности, которая по своим косвенным эффектам является чисто распределительной. Способность счетов национального дохода различать деятельность, которая действительно создает ценность, и деятельность, которая по сути является распределительным извлечением ренты, далека от совершенства».

---

### 20. `p0635` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> In the intervening years, there has, unsurprisingly, been a regulatory reversal – or at least a partial one. Under political pressure, and recognizing that they may have gone too far in allowing commercial and investment banks to share the same roof, regulators in the US and Europe have since 2008 sought to distance one from the other. Reforms such as the US Dodd–Frank Act of 2010 attempt to prevent investment banks from using the deposits of their commercial-bank parents (which are ultimately backed by government under deposit insurance schemes) to finance their riskier income-generating activities. New rules have tried, at least partly, to steer investment banks back to their original function of using borrowed money raised in wholesale markets to finance risky transactions – which even mainstream economists sometimes liken to a casino.

**В озвучку попало:**

> [serious] В последующие годы, что неудивительно, произошел откат в регулировании — или, по крайней мере, частичный. Под политическим давлением и осознавая, что они, возможно, зашли слишком далеко, разрешив коммерческим и инвестиционным банкам находиться под одной крышей, регуляторы в США и Европе после 2008 года попытались разделить их. Реформы, такие как американский закон Додда — Фрэнка 2010 года, направлены на то, чтобы инвестиционные банки не использовали депозиты своих материнских коммерческих банков — которые в конечном счете защищены государством через систему страхования вкладов — для финансирования своих рискованных операций. Новые правила попытались, хотя бы частично, вернуть инвестиционные банки к их изначальной функции: использованию заемных средств, привлеченных на оптовых рынках, для финансирования рискованных сделок, которые даже мейнстримные экономисты иногда сравнивают с казино.

---

### 21. `p0771` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Jensen, now a professor at the University of Rochester, wrote a paper with the Dean of Rochester’s business school, William Meckling (who, like Jensen, was a student of Friedman at Chicago), on how to implement Friedman’s idea. It was called ‘Theory of the firm: Managerial behavior, agency costs, and ownership structure’. The key argument was that managers (the agents) were not being disciplined by competitive financial markets or product markets, since they could misallocate resources or run up unnecessary expenses without incurring losses or endangering their jobs, and so it was hard for investors (the principals) to keep them accountable. The only way to do so was through strengthening the ‘market’, which was neutral and objective enough to make sure the company thrived. The result was a body of theory that argued that the only way for companies to be well run was if they maximized their ‘shareholder value’. In this way, investors would indirectly keep company managers accountable.

**В озвучку попало:**

> Дженсен, ставший к тому времени профессором Рочестерского университета, написал статью совместно с деканом бизнес-школы того же университета Уильямом Меклингом — который, как и Дженсен, был учеником Фридмана в Чикаго. В работе под названием «Теория фирмы: управленческое поведение, агентские издержки и структура собственности» они предложили способ реализации идей Фридмана. Ключевой аргумент заключался в том, что менеджеры, как агенты, не контролируются конкурентными финансовыми или товарными рынками. Они могут неэффективно распределять ресурсы или нести ненужные расходы, не неся при этом убытков и не рискуя своим местом, поэтому инвесторам-принципалам сложно привлечь их к ответственности. Единственный способ сделать это — укрепить «рынок», который достаточно нейтрален и объективен, чтобы обеспечить процветание компании. В результате появилась теория, утверждающая, что единственный путь к эффективному управлению — это максимизация акционерной стоимости. Так инвесторы могли бы косвенно контролировать менеджеров компаний.

---

### 22. `p0795` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Diversification was more appropriately left to the shareholders, with the bosses of each company ‘sticking to the knitting’ and not venturing beyond their narrow zone of expertise. Conglomerates’ inefficiency could be practically demonstrated if their constituent parts, broken up and floated separately, could command a higher total share price than the coagulated whole. Whether right or wrong, the assumption about managers’ professionalism did not address the problem that they might not always act in the best interests of shareholders. When the US and other Western economies slowed down in the 1970s, Friedman and other agency theorists argued that because principals and agents are motivated by self-interest, the inevitable conflicts could best be resolved by giving the ultimate owner, the shareholder, the overriding interest. Conventional wisdom was turned on its head and conglomerates were broken up, a step also justified by seeing corporations as nothing more than a collection of cash flows.

**В озвучку попало:**

> Диверсификацию лучше оставить самим акционерам, а руководителям компаний — сосредоточиться на своем основном деле и не выходить за рамки узкой специализации. Неэффективность конгломератов можно было легко доказать: если разбить их на части и продать отдельно, общая стоимость акций могла оказаться выше, чем у конгломерата в целом. Независимо от того, были ли они правы, само предположение о профессионализме менеджеров не решало проблему того, что они не всегда действуют в интересах акционеров. Когда в семидесятых годах экономика США и других западных стран замедлилась, Милтон Фридман и другие теоретики агентских отношений заявили, что, поскольку и принципалы, и агенты движимы личным интересом, конфликты лучше всего разрешать, отдавая приоритет конечному владельцу — акционеру. Привычные представления перевернулись с ног на голову, и конгломераты начали распадаться. Этот шаг также оправдывался тем, что корпорации рассматривались лишь как совокупность денежных потоков.

---

### 23. `p0831` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> Sales growth and improved profit margins, the two components of earnings growth, are positively influenced by investment, whether in plant and equipment (capital expenditure) or R&D. Investment is the story corporate managers like to tell. But there is another, quicker and more predictable way to improve margins, about which managers are less forthcoming: cutting costs. It’s a process that companies have embraced – to the detriment of investment.

**В озвучку попало:**

> Рост продаж и увеличение маржи прибыли — два компонента роста доходов — положительно зависят от инвестиций, будь то в оборудование и производственные мощности или в исследования и разработки. Инвестиции — это та история, которую любят рассказывать корпоративные менеджеры. Но есть и другой, более быстрый и предсказуемый способ улучшить маржу, о котором менеджеры говорят менее охотно: сокращение расходов. Компании активно взяли этот процесс на вооружение, что происходит в ущерб инвестициям.

---

### 24. `p0862` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Inequality reveals what we think of millions of our fellow humans. The economic issue with value extraction is not normative, however. As we have seen, in a capitalist economy some rent is necessary: there is an unavoidable price tag to maintaining the circulation of capital in the economic system. But the scale of the financial sector and of financialization generally has increased value extraction to the point where two critical questions must be answered: where is value created, extracted and even destroyed? And how can we steer the economy away from excessive financialization towards true value creation? Proposals such as taxing away very high incomes and accumulations of wealth may treat some of the symptoms of excessive finance. They do not, however, treat the causes, which lie deep in a system of value extraction which has grown up over the last forty years or so.

**В озвучку попало:**

> Неравенство обнажает наше истинное отношение к миллионам других людей. Однако экономическая проблема извлечения стоимости не является чисто этической. Как мы видели, в капиталистической экономике некоторая доля ренты неизбежна: поддержание обращения капитала в системе имеет свою цену. Но масштабы финансового сектора и финансовизации в целом увеличили извлечение стоимости до такой степени, что необходимо ответить на два критических вопроса. Где именно стоимость создается, извлекается или даже уничтожается? И как нам направить экономику от чрезмерной финансовизации к реальному созиданию стоимости? Предложения вроде налогообложения сверхвысоких доходов и накоплений могут помочь в борьбе с симптомами, но они не устраняют причины. А причины кроются глубоко в системе извлечения стоимости, которая формировалась последние сорок лет.

---

### 25. `p0928` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> IPOs are, first, a way for early investors to get their money out. The very possibility of an IPO encourages investment – although it has to be said that investors with one eye on the exit door and the other on the clock might not be ideal for nurturing a company to its potential. Second, IPOs can raise new capital for business expansion, which can be valuable in some sectors but less significant in others (like software), where the most important capital is human. Third, founders can realize the value of their ingenuity and sweat equity that has remained latent in the company.

**В озвучку попало:**

> Во-первых, IPO — это способ для ранних инвесторов вернуть свои деньги. Сама возможность выхода на биржу поощряет инвестиции, хотя стоит признать: инвесторы, которые одним глазом следят за выходом, а другим — за часами, вряд ли подходят для того, чтобы помогать компании полностью раскрыть свой потенциал. Во-вторых, IPO позволяет привлечь новый капитал для расширения бизнеса. В некоторых секторах это ценно, но в других, например в программном обеспечении, это менее значимо, ведь там самый важный капитал — человеческий. В-третьих, основатели могут реализовать стоимость своей изобретательности и вложенного труда, которая до этого момента оставалась скрытой.

---

### 26. `p0934` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> The classical economists would have had little time for the way in which the VC industry has extracted value by shifting money around rather than creating value: for them the point was to nurture the production of value rather than its simple circulation.

**В озвучку попало:**

> [thoughtful] Классические экономисты вряд ли одобрили бы то, как индустрия венчурного капитала извлекает прибыль. Они предпочитали просто перекладывать деньги из кармана в карман, а не создавать реальную ценность. Для классиков же главным было развивать производство, а не просто обеспечивать циркуляцию капитала.

---

### 27. `p0939` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> Patents are protections granted to inventions that are novel, inventive (non-obvious) and suitable for industrial application. In theory they protect the innovator from having his or her idea copied. In practice, however, most innovations are not patented, which in itself shows that patents are not really necessary, as there are other ways to protect innovations, including lead-times and trade secrecy. One study found that between 1977 and 2004, only 10 per cent of ‘important’ innovations were patented.²² Patents tend to be granted for two reasons, which must be held in constant tension for the system to function effectively. The first is to reward and incentivize inventors for developing new ideas by granting them a time-limited monopoly entitlement over their inventions,23 or what is known as the *appropriability function* of patents. In exchange for this monopoly entitlement, the inventor must reveal detailed information about his or her invention. Which brings us to the second reason: once the patent has expired, the invention can diffuse rapidly through the economy in a process known as the *disclosure function* of patents. If the system works well, the appropriability function is properly balanced against the disclosure function and the public gains from the rapid diffusion of this 24 new knowledge through the economy.

**В озвучку попало:**

> Патенты — это защита, предоставляемая изобретениям, которые являются новыми, оригинальными и пригодными для промышленного применения. В теории они оберегают новатора от копирования его идей. На практике же большинство инноваций не патентуется. Это само по себе доказывает, что патенты не всегда необходимы, ведь существуют и другие способы защиты, например, опережение конкурентов или коммерческая тайна. Согласно одному исследованию, в период с 1977 по 2004 год было запатентовано лишь 10 процентов «важных» инноваций. Патенты обычно выдаются по двум причинам, которые должны находиться в постоянном равновесии для эффективной работы системы. Первая — это вознаграждение изобретателей за разработку новых идей путем предоставления им временной монополии. Это называется функцией присвоения. В обмен на такую монополию изобретатель обязан раскрыть подробную информацию о своем открытии. Это подводит нас ко второй причине: после истечения срока действия патента изобретение может быстро распространиться в экономике. Это называется функцией раскрытия. Если система работает исправно, функция присвоения должным образом сбалансирована с функцией раскрытия, и общество выигрывает от быстрого распространения новых знаний.

---

### 28. `p1017` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> The first major consequence is monopoly. Historically, industries naturally prone to being monopolies, for example railways and water, have been either taken into public ownership (e.g. in Europe) or heavily regulated (e.g. in the US) to protect the public against abuses of corporate power. But monopolistic online platforms remain privately owned and largely unregulated despite all the issues they raise: privacy, control of information and their sheer commercial power in the market, to name a few. In the absence of strong, transnational, countervailing regulatory forces, firms that first establish market control can reap extraordinary rewards. The low rates of tax that technology companies are typically paying on these rewards are also paradoxical, given that their success was built on technologies funded and developed by high-risk public investments.⁷⁴ If anything, companies owing their fortunes to taxpayer investment should be repaying the taxpayer, not seeking tax breaks.

**В озвучку попало:**

> Первое серьезное последствие — это монополия. Исторически сложилось так, что отрасли, склонные к монополизации, например, железные дороги или водоснабжение, либо переходили в государственную собственность, как в Европе, либо подвергались жесткому регулированию, как в США. Это делалось для защиты общества от злоупотреблений корпоративной властью. Однако монопольные онлайн-платформы остаются частными и практически не регулируются, несмотря на все проблемы, которые они создают: от контроля над информацией и нарушения приватности до колоссального коммерческого влияния. В отсутствие сильных международных регуляторных механизмов компании, первыми захватившие рынок, получают сверхприбыли. Парадоксально и то, что технологические гиганты платят с этих доходов низкие налоги, хотя их успех был построен на технологиях, которые финансировались и развивались за счет рискованных государственных инвестиций. Более того, компании, обязанные своим состоянием деньгам налогоплательщиков, должны были бы возвращать средства обществу, а не искать налоговые льготы.

---

### 29. `p1026` — длина озвучки / длина оригинала: 0.74; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Current stories about value, wealth creation and risk-taking that privilege the contribution of individual inventors and capitalists lead to ways of thinking whereby it is acceptable to divide up the fruits of innovation between them – the concept of ‘just deserts’. The term comes from the English philosopher John Locke (1632–1704). His concept of individual entitlement – ‘just deserts’ – to the product of work was based on a production system where individual labour was more important, and was easier to identify, than it is today when collective contributions have been central to technology-driven growth. This point was made by Herbert Simon (1916–2001), who made his name in the study of organizational decision-making, and who won the Nobel Prize in Economics in 1978. ‘If we are generous with ourselves,’ Simon considered, ‘I suppose that we might claim that we “earned” as much as one-fifth of our income. The rest of the patrimony [is] associated with being a member of an enormously productive social system, which has accumulated a vast store of physical capital, and an even larger store of intellectual capital – including knowledge, skills, and organizational know-how held by all of us.’78 Ignoring this collectively produced social system, certain individuals feel justified in earning a much higher proportion of a nation’s income than their own contribution warrants. But, more specifically, it has affected policies on taxes, patents and prices, thus fuelling the dynamics of inequality.

**В озвучку попало:**

> Современные представления о богатстве и успехе ставят во главу угла индивидуальных изобретателей и капиталистов. Это порождает концепцию «заслуженного вознаграждения», которая восходит к английскому философу Джону Локку. Его идея о том, что человек имеет право на продукт своего труда, была оправдана в эпоху, когда индивидуальный вклад был очевиден. Сегодня же, когда в основе технологического роста лежат коллективные усилия, этот подход устарел. Герберт Саймон, лауреат Нобелевской премии по экономике, однажды заметил: «Если мы будем очень щедры к себе, то сможем заявить, что заработали одну пятую часть своего дохода. Остальное — это результат того, что мы являемся частью невероятно продуктивной социальной системы». Эта система накопила колоссальные запасы физического и интеллектуального капитала — знаний, навыков и организационного опыта, которые принадлежат всем нам. Игнорируя этот факт, некоторые люди присваивают себе гораздо большую долю национального дохода, чем того заслуживает их личный вклад. Это напрямую влияет на налоговую политику, систему патентов и ценообразование, подпитывая неравенство.

---

### 30. `p1107` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> The immensely influential Alfred Marshall was quite nuanced in his discussion of economic life in his *Principles*, but still recommended that economics should avoid ‘as far as possible’ the discussion of matters associated with government.²⁴ He believed that government interference in, or regulation of, the market would often happen in response to attempts by vested interests to rig the market in their favour (i.e. government would be ‘captured’ by such interests) – thus only hurting a particular competitor 25 rather than benefiting society as a whole.

**В озвучку попало:**

> Влиятельный экономист Альфред Маршалл в своих «Принципах» рассуждал об экономической жизни довольно тонко. Тем не менее он рекомендовал экономистам «по возможности» избегать обсуждения вопросов, связанных с государством. Он полагал, что вмешательство власти в рынок или его регулирование часто происходит в ответ на попытки групп интересов подстроить рынок под себя. В итоге государство оказывается «захваченным» этими группами, что лишь вредит отдельным конкурентам, не принося пользы обществу в целом.

---

### 31. `p1109` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> To the humble citizen, however, it might not be so obvious that government does not create value. We have already seen three ways in which it does so: bailing out the banks; investing in infrastructure, education and basic science; and funding radical, innovative technologies which are transforming our lives.

**В озвучку попало:**

> [thoughtful] Обычному человеку может быть не так уж очевидно, что государство не создает ценности. Мы уже видели три способа, которыми оно это делает: спасение банков, инвестиции в инфраструктуру, образование и фундаментальную науку, а также финансирование прорывных инновационных технологий, которые меняют нашу жизнь.

---

### 32. `p1151` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> The 1980s backlash against government was in part driven by the notion that economies should worry more about ‘government failure’ than ‘market failure’. Government failure emerged as a concept from Public Choice theory, a set of ideas closely associated with economists like the American James Buchanan and the University of Chicago, where Buchanan studied. In 1986 he was awarded the Nobel Prize in Economics.

**В озвучку попало:**

> Волна критики в адрес правительства в восьмидесятые годы была отчасти вызвана идеей о том, что экономике следует больше опасаться «провалов государства», чем «провалов рынка». Понятие провала государства возникло в рамках теории общественного выбора. Эти идеи тесно связаны с именами таких экономистов, как американец Джеймс Бьюкенен и представители Чикагского университета, где он учился. В 1986 году Бьюкенен был удостоен Нобелевской премии по экономике.

---

### 33. `p1161` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> The solution to the problem of natural monopolies was regulation. In the UK a series of regulatory agencies sprang up, each intended to stand between the public and industry. Regulatory capitalism replaced state capitalism. It was not what pure Public Choice theorists intended; indeed, regulatory capitalism resulted in exactly the kind of government cronyism and corruption that they had warned about.

**В озвучку попало:**

> Решением проблемы естественных монополий стало регулирование. В Великобритании возник целый ряд регулирующих органов, каждый из которых должен был выступать посредником между обществом и промышленностью. На смену государственному капитализму пришел капитализм регулируемый. Это было совсем не то, к чему стремились сторонники теории общественного выбора. Напротив, регулируемый капитализм привел именно к тем формам государственного кумовства и коррупции, о которых они предупреждали.

---

### 34. `p1162` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> Another consequence of Public Choice theory has been the rise of intermediary mechanisms to fund public activity. This has mainly taken two forms. One is private finance initiatives (PFIs), for example to build hospitals. The other, mentioned earlier, is outsourcing to private providers to run a wide range of services. In both cases, public activity is financed privately. Turning to PFIs in this way has been called ‘pseudo-privatization’, because the private firms receive their income not from clients in the ‘market’ but from government through a guaranteed profit margin. An outsourcing contract is in effect a type of monopoly which locks the government in as the sole customer. In the UK, moreover, the degree of competition between providers of outsourcing services is questionable: only a handful, dominated by Capita, G4S and Serco, 44 account for most the contracts.

**В озвучку попало:**

> Еще одним следствием теории общественного выбора стало появление посреднических механизмов для финансирования государственных нужд. В основном это приняло две формы. Первая — частные финансовые инициативы, например, для строительства больниц. Вторая — аутсорсинг, то есть передача широкого спектра услуг частным поставщикам. В обоих случаях государственная деятельность финансируется за счет частных средств. Такой подход к частным финансовым инициативам называют «псевдоприватизацией», поскольку частные фирмы получают доход не от клиентов на открытом рынке, а от государства в виде гарантированной прибыли. Контракт на аутсорсинг фактически является разновидностью монополии, которая делает государство единственным заказчиком. Более того, в Великобритании уровень конкуренции между поставщиками аутсорсинговых услуг вызывает сомнения: лишь несколько компаний, среди которых доминируют «Капита», «Джи-фор-эс» и «Серко», выполняют большую часть контрактов.

---

### 35. `p1165` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> In 1948, when the UK was still undergoing a long and difficult post-war reconstruction (public debt was well above 200 per cent over GDP in that year), British citizens received a leaflet on which was stated: ‘Your new National Health Service begins on 5th July. What is it? How do you get it?

**В озвучку попало:**

> В 1948 году, когда Великобритания еще переживала долгий и трудный период послевоенного восстановления, а государственный долг значительно превышал двести процентов от валового внутреннего продукта, британцы получили листовку. В ней говорилось: «Ваша новая Национальная служба здравоохранения начинает работу 5 июля. Что это такое? Как ею воспользоваться?»

---

### 36. `p1225` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> A bold view of the role of public policy also requires a change in the metrics used for evaluation of those policies. Today’s typical static cost-benefit analysis is inadequate for decisions which will inevitably have many indirect consequences. A much more dynamic analysis, one which can capture more of the market-shaping process, is urgently required. For example, any measure of the success of a government project to organize a charging infrastructure for electric cars must try to take into account the opportunities offered for further technical development, the reduction of pollution and the political and ecological gains of lessening reliance on non-renewable oil from countries with objectionable governments.

**В озвучку попало:**

> [thoughtful] Смелый взгляд на роль государственной политики требует и изменения критериев, по которым эта политика оценивается. Сегодняшний стандартный анализ «затраты-выгоды» статичен. Он не подходит для решений, которые неизбежно влекут за собой множество косвенных последствий. Нам срочно нужен гораздо более динамичный подход, способный учитывать процессы формирования рынка. Например, оценивая успех государственного проекта по созданию инфраструктуры для зарядки электромобилей, необходимо учитывать не только прямые показатели. Нужно принимать во внимание возможности для дальнейшего технического прогресса, снижение уровня загрязнения среды, а также политические и экологические выгоды от уменьшения зависимости от нефти, поставляемой странами с сомнительными режимами.

---

### 37. `p1242` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> In this book, I have argued that such critiques are important but will remain powerless – in their ability to bring about real reform of the economic system – until they become firmly grounded in a discussion about the processes by which economic value is created. It is not enough to argue for less value extraction and more value creation. First, ‘value’, a term that once lay at the heart of economic thinking, must be revived and better understood.

**В озвучку попало:**

> В этой книге я утверждаю, что подобная критика важна, но она останется бессильной. Чтобы добиться реальных перемен в экономической системе, нужно прочно обосновать дискуссию на процессах создания экономической ценности. Недостаточно просто призывать к сокращению извлечения ценности и увеличению её создания. Прежде всего, необходимо возродить и лучше понять само понятие «ценности», которое когда-то лежало в основе экономической мысли.

---

### 38. `p1249` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Internet.³ It is also not enough to tax wealth. While such measures are important in themselves, they do not address the greatest challenge: defining and measuring the collective contribution to wealth creation, so that value extraction is less able to pass for value creation. As we have seen, the idea that price determines value and that markets are best at determining prices has all sorts of nefarious consequences. To sum up, four stand out.

**В озвучку попало:**

> Интернет. Также недостаточно просто облагать налогами богатство. Хотя такие меры важны сами по себе, они не решают главную проблему: определение и измерение коллективного вклада в создание богатства, чтобы извлечение ценности не могло выдаваться за её создание. Как мы уже видели, идея о том, что цена определяет ценность, а рынки лучше всего справляются с установлением цен, имеет множество пагубных последствий. Подводя итог, можно выделить четыре основных.

---

### 39. `p1268` — длина озвучки / длина оригинала: 1.29; классы правки: —

**Исходный абзац:**

> With this in mind, we can move beyond the idea of public goods as ‘corrections’, that is being limited to areas that need fixing (due to positive externalities that they generate), to being ‘objectives’. This requires a new understanding of policy as actively ‘shaping’ and ‘creating’ markets that achieve public value, benefitting society more widely.

**В озвучку попало:**

> [thoughtful] С учетом этого мы можем выйти за рамки представления об общественных благах как о «корректировках» — то есть как о чем-то, что нужно лишь для исправления рыночных провалов из-за создаваемых ими положительных внешних эффектов. Вместо этого общественные блага должны стать «целями». Это требует нового понимания политики: она должна активно формировать и создавать рынки, которые приносят общественную пользу и работают на благо всего общества.

---

### 40. `p1275` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Indeed, a key way to tackle some of society’s most pressing problems today is to learn lessons from historical periods in which bold ambitions were set to tackle difficult technological problems. Consider two lessons from the man on moon mission. First, the agencies involved, from NASA to DARPA, built up their own capacity and competences. They did not outsource their tasks, or the resulting knowledge, to the private sector. This practice should be borne in mind when considering the currently fashionable public–private partnership arrangements. They will only succeed as dynamic knowledge-intensive collaborations, with both sides equally committed to investing in in-house competencies and capabilities.

**В озвучку попало:**

> [serious] На самом деле, один из лучших способов решения самых острых социальных проблем сегодня — это извлечь уроки из периодов истории, когда ставились смелые цели для преодоления сложных технологических барьеров. Вспомним два урока программы высадки человека на Луну. Во-первых, все задействованные агентства, от НАСА до DARPA, наращивали собственные компетенции и возможности. Они не передавали свои задачи или полученные знания на аутсорсинг частному сектору. Об этом стоит помнить, рассматривая популярные сегодня модели государственно-частного партнерства. Они будут успешны только как динамичные, наукоемкие коллаборации, где обе стороны в равной степени инвестируют в развитие внутренних навыков и возможностей.

---

### 41. `p2282` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> In 2013 I wrote a book called *The Entrepreneurial State*. In it I debunked how myths about lone entrepreneurs and start-ups have captured the theory and practice of innovation, ignoring one of the key actors that has been an investor of first resort: the state. Innovation is a collective process, with different types of public institutions playing a pivotal role. That role is ignored, so our theory of value creation is flawed. And this is a major reason for wealth often being distributed in dysfunctional ways.

**В озвучку попало:**

> [thoughtful] В 2013 году я написала книгу «Предпринимательское государство». В ней я развенчала мифы об одиноких предпринимателях и стартапах, которые захватили теорию и практику инноваций. Эти мифы игнорируют одного из ключевых игроков — государство, которое часто выступает инвестором первой очереди. Инновации — это коллективный процесс, где важную роль играют различные государственные институты. Поскольку эта роль игнорируется, наша теория создания стоимости оказывается ошибочной. И это одна из главных причин, почему богатство так часто распределяется неэффективно.

---

### 42. `p2283` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> The book you have in your hand is a direct consequence of this early reasoning. We cannot understand economic growth if we do not go back to the beginning: what is wealth and where does value come from? Are we sure that much of what is passing for value creation is not just value extraction in disguise?

**В озвучку попало:**

> Книга, которую вы держите в руках, стала прямым следствием этих размышлений. Мы не сможем понять экономический рост, если не вернемся к истокам: что такое богатство и откуда берется стоимость? Уверены ли мы, что многое из того, что выдается за создание стоимости, не является лишь ее присвоением под другой личиной?

---

### 43. `p2284` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> To write the book I needed to delve into the last 300 years of thinking about value. No easy task, and made no easier by also having to grapple with the application of these ideas to contemporary capitalism as a whole – for example, financialization – and to particular sectors, from finance to big pharma and IT.

**В озвучку попало:**

> Чтобы написать эту книгу, мне пришлось погрузиться в историю экономической мысли за последние триста лет. Это была непростая задача. Ее усложняла необходимость применить эти идеи к современному капитализму в целом — например, к финансовизации — и к конкретным секторам, от финансов до фармацевтики и информационных технологий.

---

### 44. `p2286` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> I would like to thank Gregor Semeniuk, who like me received a PhD from the Graduate Faculty of the New School in New York – a rare place that still teaches alternative theories of economic thought. He generously shared his extraordinary knowledge about value theory, from the physiocrats to the classicals. Gregor was a tremendous support in helping me document, in a ‘user-friendly’ way, the debates between the Physiocrats, Smith and Ricardo – and the strange fact that even Marx had no real theory of the way in which the state can contribute to value.

**В озвучку попало:**

> [serious] Я хочу поблагодарить Грегора Семенюка, который, как и я, получил докторскую степень в Новой школе в Нью-Йорке. Это редкое место, где до сих пор преподают альтернативные экономические теории. Он щедро поделился своими выдающимися знаниями о теории стоимости, начиная от физиократов и заканчивая классиками. Грегор оказал мне огромную поддержку, помогая доступно изложить дебаты между физиократами, Смитом и Рикардо. А также обсудить странный факт: даже у Маркса не было реальной теории того, как государство может способствовать созданию стоимости.

---

### 45. `p2288` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> He cheerfully cycled to our meetings on even the hottest days of the year and was not just a friendly editor but also a great companion, bringing calm to what often felt like hectic months trying to finish a book while I was raising a large family and starting up a new department at UCL. Our weekly meetings in the Lord Stanley pub in Camden to pore over the material often trailed off into a stream of consciousness dwelling on the ills of modern capitalism – and were nothing but pure joy. With the occasional pint (or two) to keep us going.

**В озвучку попало:**

> Он бодро приезжал на наши встречи на велосипеде даже в самые жаркие дни. Майкл был не просто дружелюбным редактором, но и отличным собеседником. Он привносил спокойствие в те месяцы, когда я пыталась закончить книгу, воспитывая большую семью и открывая новый факультет в Университетском колледже Лондона. Наши еженедельные встречи в пабе «Лорд Стэнли» в Камдене, где мы корпели над текстом, часто перетекали в поток сознания о пороках современного капитализма. Это было чистое удовольствие, иногда подкрепленное пинтой-другой пива для бодрости.

---

### 46. `p2289` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> I would like to thank the following people for looking at particular chapters in the book and double checking it for errors in its final stages, selflessly offering their wisdom and care: (in alphabetical order) Matteo Deleidi, Lukas Fuchs Tommaso Gabellini, Simone Gasperin, Edward Hadas, Andrea Laplane, Alain Rizk, and Josh Ryan Collins.

**В озвучку попало:**

> Я хочу поблагодарить следующих людей за то, что они изучили отдельные главы книги и проверили их на наличие ошибок на финальных этапах, бескорыстно предлагая свою мудрость и внимание: Маттео Делейди, Лукаса Фукса, Томмазо Габеллини, Симоне Гасперини, Эдварда Хадаса, Андреа Лаплан, Алена Ризка и Джоша Райана Коллинза.

---

### 47. `p2290` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> My editor Tom Penn at Penguin was a great sounding board during our endless coffee-filled meetings at the British Library – having the rare qualities of a meticulous proofreader while also retaining a deep engagement with the content, both economic and philosophical.

**В озвучку попало:**

> Мой редактор Том Пенн из издательства «Пингвин» стал отличным собеседником во время наших бесконечных встреч за кофе в Британской библиотеке. Он обладает редким сочетанием качеств: он дотошный корректор, который при этом глубоко погружен в содержание — как экономическое, так и философское.

---

### 48. `p2291` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> I also want to thank the excellent administrative assistance I have had over the last four years, first at SPRU in the University of Sussex and now in a new institute that I have founded at UCL, the Institute for Innovation and Public Purpose IIPP). Gemma Smith in particular has helped me always try to get messages across – whether on the 10 o’clock news or in a policy brief – that could be understood by the general public. With the new team at IIPP, I hope the book’s message about the need for revived debate about key questions around value can be linked with the IIPP’s ambition to redefine ways of conceptualizing public value in particular: how to create it, nurture it and evaluate it.

**В озвучку попало:**

> Я также хочу поблагодарить всех, кто оказывал мне административную поддержку в последние четыре года — сначала в отделе исследований научной политики в Университете Сассекса, а теперь и в новом институте, который я основала в Университетском колледже Лондона: Институте инноваций и общественного назначения. Особенно Джемму Смит, которая помогала мне доносить мысли до широкой публики — будь то в новостях или в аналитических записках. Надеюсь, что с новой командой института мы сможем связать идеи этой книги о необходимости дискуссий вокруг стоимости с нашей амбицией по-новому взглянуть на общественную ценность: как ее создавать, развивать и оценивать.

---

### 49. `p2292` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> Lastly, I want to thank Carlo, Leon, Micol, Luce and Sofia for putting up with the many long nights and weekends that the book entailed – letting me climb up the stairs and plop myself down to the most happy and conversive dinner table a wife and mother can ask for – putting life back at the centre, where it should be.

**В озвучку попало:**

> [exhales] Наконец, я хочу поблагодарить Карло, Леона, Миколь, Люче и Софию за то, что они терпели долгие ночи и выходные, которые отнимала эта книга. Спасибо, что позволяли мне спуститься по лестнице и сесть за самый счастливый и оживленный обеденный стол, о котором только может мечтать жена и мать. Вы вернули жизнь в центр всего, где ей и положено быть.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0849` — длина озвучки / длина оригинала: 0.67; классы правки: —

**Исходный абзац:**

> Friedman summarized the classic view of entrepreneurial firms as eternally struggling to stay afloat in a turbulent market (while hinting at the temptation to escape by subverting that market) by defining the purpose of a business as being to ‘use its resources and engage in activities designed to increase profits so long as it stays within the rules of the game, which is to say, engages in open and free competition, without deception 35 or fraud’.

**В озвучку попало:**

> Милтон Фридман описывал предпринимательские фирмы как структуры, которые вечно борются за выживание на турбулентном рынке. Он считал, что цель бизнеса — использовать свои ресурсы для увеличения прибыли, пока компания соблюдает «правила игры», то есть ведет честную конкуренцию без обмана и мошенничества.

---

### 2. `p1026` — длина озвучки / длина оригинала: 0.74; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Current stories about value, wealth creation and risk-taking that privilege the contribution of individual inventors and capitalists lead to ways of thinking whereby it is acceptable to divide up the fruits of innovation between them – the concept of ‘just deserts’. The term comes from the English philosopher John Locke (1632–1704). His concept of individual entitlement – ‘just deserts’ – to the product of work was based on a production system where individual labour was more important, and was easier to identify, than it is today when collective contributions have been central to technology-driven growth. This point was made by Herbert Simon (1916–2001), who made his name in the study of organizational decision-making, and who won the Nobel Prize in Economics in 1978. ‘If we are generous with ourselves,’ Simon considered, ‘I suppose that we might claim that we “earned” as much as one-fifth of our income. The rest of the patrimony [is] associated with being a member of an enormously productive social system, which has accumulated a vast store of physical capital, and an even larger store of intellectual capital – including knowledge, skills, and organizational know-how held by all of us.’78 Ignoring this collectively produced social system, certain individuals feel justified in earning a much higher proportion of a nation’s income than their own contribution warrants. But, more specifically, it has affected policies on taxes, patents and prices, thus fuelling the dynamics of inequality.

**В озвучку попало:**

> Современные представления о богатстве и успехе ставят во главу угла индивидуальных изобретателей и капиталистов. Это порождает концепцию «заслуженного вознаграждения», которая восходит к английскому философу Джону Локку. Его идея о том, что человек имеет право на продукт своего труда, была оправдана в эпоху, когда индивидуальный вклад был очевиден. Сегодня же, когда в основе технологического роста лежат коллективные усилия, этот подход устарел. Герберт Саймон, лауреат Нобелевской премии по экономике, однажды заметил: «Если мы будем очень щедры к себе, то сможем заявить, что заработали одну пятую часть своего дохода. Остальное — это результат того, что мы являемся частью невероятно продуктивной социальной системы». Эта система накопила колоссальные запасы физического и интеллектуального капитала — знаний, навыков и организационного опыта, которые принадлежат всем нам. Игнорируя этот факт, некоторые люди присваивают себе гораздо большую долю национального дохода, чем того заслуживает их личный вклад. Это напрямую влияет на налоговую политику, систему патентов и ценообразование, подпитывая неравенство.

---

### 3. `p1061` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> This historical and institutional view of markets’ relationship with government contrasts sharply with the current prevailing orthodoxy and is not to be found in mainstream economics. Here – to get technical for a moment – you only find government as a player in the macroeconomic models that look at the effect of regulation or the effect of a stimulus programme on GDP (through the multiplier which we discuss later in the chapter). But government is totally missing from what in microeconomics is known as the ‘production function’: the relationship between the quantity of outputs of a good and the quantity of inputs needed to make it, or, to put it simply, the analysis of how firms behave. And thus it is assumed that it is only in firms that value is created. Government is left outside the production boundary.

**В озвучку попало:**

> [serious] Такой исторический и институциональный взгляд на отношения рынка и государства резко контрастирует с господствующей сегодня ортодоксией и отсутствует в мейнстримной экономике. Если говорить технически, в макроэкономических моделях государство выступает лишь как игрок, влияющий на ВВП через регулирование или программы стимулирования. Но в микроэкономике, в так называемой «производственной функции» — анализе того, как фирмы превращают ресурсы в товары, — государства просто нет. Считается, что ценность создается только внутри фирм. Государство остается за пределами производственного процесса.

---

### 4. `p1256` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> Third, this market story confuses policymakers. By and large, policymakers of all stripes want to help their communities and their country, and they think the way to do so is to put more trust in market mechanisms, with policy just a matter of tinkering at the edges. The crucial thing is to be seen as progressive while also ‘business-friendly’. But with a very limited understanding of where value comes from, politicians and all too many government employees are like putty in the hands of those who claim to be value creators. Regulators end up being lobbied by businesses and induced to endorse policies which make incumbents even richer – increasing profits but with little effect on investment. Examples include ways in which governments across much of the Western world have been persuaded to reduce capital gains tax, even though there is no reason to do so if the aim is to promote long-term investments rather than short-term ones. And lobbyists with their innovation stories have pushed through the Patent Box policy, which reduces tax on the profits generated from 20-year patent-based monopolies – even though the policy’s main impact has been merely to reduce government revenue, rather than increasing the types of investments that led to the patents in the first place.⁵ All of which serves only to subtract value from the economy and make for a less attractive future for almost everyone. Not having a clear view of the collective value creation process, the public sector is thus ‘captured’ – entranced by stories about wealth creation which have led to regressive tax policies that increase inequality.

**В озвучку попало:**

> В-третьих, эта рыночная идеология сбивает с толку политиков. В большинстве своем они хотят помочь своей стране и думают, что лучший способ — довериться рыночным механизмам, ограничиваясь лишь косметическими мерами. Важно выглядеть прогрессивным и при этом «дружелюбным к бизнесу». Но из-за ограниченного понимания того, откуда берется ценность, политики и многие чиновники становятся пластилином в руках тех, кто называет себя создателями богатства. Регуляторы поддаются лоббированию и одобряют политику, которая делает владельцев бизнеса еще богаче, увеличивая прибыль, но почти не влияя на реальные инвестиции. Примеры включают снижение налога на прирост капитала, хотя это не способствует долгосрочным вложениям. Лоббисты также протащили политику «патентных ящиков», снижающую налоги на прибыль от двадцатилетних монополий. Главным результатом стало лишь сокращение государственных доходов, а не рост инвестиций в инновации. Это лишь изымает ценность из экономики и делает будущее менее привлекательным для всех. Не имея ясного представления о процессе коллективного создания ценности, госсектор оказывается в ловушке историй о создании богатства, которые ведут к регрессивной налоговой политике и росту неравенства.

---

### 5. `p0447` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Indeed, following this logic, government is also a producer of intermediate inputs for businesses. Surely education, roads, or the police, or courts of law can be seen as necessary inputs into the production of a variety of goods? But herein lies is a twist. If government spending were to increase, this would mean that government was producing more intermediate goods. Businesses would buy at least some of those goods (e.g. some public services cost money) with a fee; but because they were spending more on them (than if government was not producing anything, and therefore not buying supplies from businesses), their operating surplus and value added would inevitably fall. Government’s share of GDP would rise, but the absolute size of GDP would stay the same. This does, of course, run counter to Keynesian attempts to show how increases in government demand could lift GDP.

**В озвучку попало:**

> Следуя этой логике, государство выступает производителем промежуточных товаров для бизнеса. Разве образование, дороги, полиция или суды — это не необходимые ресурсы для производства самых разных товаров? Но здесь есть подвох. Если бы государственные расходы выросли, это означало бы, что государство производит больше промежуточных товаров. Бизнес покупал бы часть этих услуг за плату, но из-за роста этих издержек их собственная операционная прибыль и добавленная стоимость неизбежно снизились бы. Доля государства в ВВП выросла бы, а общий размер ВВП остался бы прежним. Это, конечно, противоречит кейнсианским попыткам доказать, что рост государственных расходов стимулирует ВВП.

---

### 6. `p0110` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> For centuries, economists and policymakers – people who set a plan for an organization such as government or a business – have divided activities according to whether they produce value or not; that is, whether they are productive or unproductive. This has essentially created a boundary – the fence in Figure 1 below – thereby establishing a conceptual boundary – sometimes referred to as a ‘production boundary’ – between these activities.¹⁶ Inside the boundary are the wealth creators. Outside are the beneficiaries of that wealth, who benefit either because they can extract it through rent-seeking activities, as in the case of a monopoly, or because wealth created in the productive area is redistributed to them, for example through modern welfare policies. Rents, as understood by the classical economists, were *unearned* income and fell squarely outside the production boundary. Profits were instead the returns earned for productive activity inside the boundary.

**В озвучку попало:**

> На протяжении столетий экономисты и политики — те, кто определяет стратегию развития государства или бизнеса, — разделяли все виды деятельности на производительные и непроизводительные. По сути, это создало своего рода концептуальный барьер, который часто называют «границей производства». Внутри этой границы находятся создатели богатства. Снаружи — те, кто лишь пользуется этим богатством. Они получают его либо через ренту, как в случае с монополиями, либо через перераспределение, например, с помощью современной социальной политики. Классические экономисты считали ренту нетрудовым доходом, поэтому она всегда оставалась за пределами границы производства. Прибыль же, напротив, считалась вознаграждением за производительный труд внутри этой границы.

---

### 7. `p0806` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The ‘short-termism’ which Keynes anticipated is encapsulated in index fund pioneer John Bogle’s concept that institutional investors rent the shares of the companies they invest in rather than take ownership for the long term. Consider the increased turnover of domestic shares: according to the World Federation of Exchanges, which represents the world’s publicly regulated stock exchanges, in the US turnover of domestic shares was around 20 per cent a year in the 1970s, rising steeply to consistently over 100 per cent a year in the 2000s. Turnover measures how often a share changes hands and is calculated by dividing the number of shares traded in a given period by the number of shares outstanding in the same period. Increasing turnover is a sign that institutional investors’ sights were trained on the short-term movement of stock prices rather the intrinsic, long-term value of the corporation. High turnover can be more profitable for institutional investors than passive, long-term holding of shares. It should also be said that the short-termist behaviour of institutional investors reflects mounting pressure over the last four decades from clients who, expecting quick results and with a dislike of surprises, quickly withdraw their funds when disappointed. The result has been a corporate fixation on quarterly performance, which encourages consistent earnings growth to generate acceptable share price performance.

**В озвучку попало:**

> [serious] «Краткосрочность», которую предвидел Кейнс, хорошо описывает концепция Джона Богла, пионера индексных фондов. Он считал, что институциональные инвесторы не владеют компаниями в долгосрочной перспективе, а лишь арендуют их акции. Посмотрите на рост оборота акций: по данным Всемирной федерации бирж, в семидесятые годы в США оборот составлял около двадцати процентов в год, а в двухтысячных он стабильно превышал сто процентов. Оборот показывает, как часто акции переходят из рук в руки. Рост этого показателя — верный признак того, что институциональные инвесторы сфокусированы на сиюминутных колебаниях цен, а не на внутренней долгосрочной стоимости корпорации. Высокий оборот может быть выгоднее для инвесторов, чем пассивное долгосрочное владение. Стоит также сказать, что такое поведение инвесторов — это реакция на давление со стороны клиентов. Ожидая быстрых результатов и не любя сюрпризов, клиенты быстро забирают свои деньги при первых признаках разочарования. В результате компании зацикливаются на квартальных отчетах, стараясь обеспечить стабильный рост прибыли ради красивых графиков цены акций.

---

### 8. `p0516` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> The current chapter looks at the expansion of banking, and the way in which political decisions to recognize its value in national accounts (although based on economically contentious assumptions) helped to drive a deregulation which fuelled its ultimately over-reaching growth. In the next two chapters I explore the relationship between this growth and the financialization of the rest of the economy.

**В озвучку попало:**

> В этой главе рассматривается расширение банковской деятельности и то, как политические решения признать её ценность в национальных счетах помогли стимулировать дерегулирование, которое подпитывало этот чрезмерный рост. В следующих двух главах я исследую связь между этим ростом и финансиализацией остальной экономики.

---

### 9. `p0414` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Second, competition in economies is generally imperfect – a reality that has proven distinctively uncomfortable for national accountants trained in the neoclassical ideas of perfect competition and ‘equilibria’. By simply adding up market prices they ignored the fact that those prices would not always produce an equilibrium and be compatible with ‘perfect competition’; prices could therefore be higher or lower than if equilibrium prevailed, thereby giving a distorted impression of value creation. In short, during the war years practice became significantly detached from the prevailing theory – or, seen another way, the utility theory of value did not solve the urgent war-related problems of the time.

**В озвучку попало:**

> Во-вторых, конкуренция в экономике обычно несовершенна. Этот факт всегда был неудобен для специалистов, обученных неоклассическим идеям о совершенной конкуренции и равновесии. Просто складывая рыночные цены, они игнорировали то, что эти цены не всегда отражают равновесие. В реальности цены могли быть выше или ниже равновесных, что искажало представление о создании ценности. Короче говоря, в военные годы практика значительно отошла от господствовавшей теории, либо, если взглянуть иначе, теория полезности просто не решала насущных проблем военного времени.

---

### 10. `p0468` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> How might this work? Let’s contrast two countries. In one, there are only renters paying owners such as real-estate companies (in Switzerland in 2014 more people lived in rented homes than in owner-occupied homes). In the other, all houses are owned (in the US and UK a larger percentage of people own than rent). Since real estate adds value and income (rent) from the actual rent charged (as opposed to the ‘imputed rent’ calculated), the first country would have an unfairly high GDP compared to the other, at least in terms of the percentage of GDP deriving from property.

**В озвучку попало:**

> Как это работает на практике? Давайте сравним две страны. В первой живут только арендаторы, снимающие жилье у компаний, как, например, в Швейцарии в 2014 году. Во второй стране почти все дома находятся в собственности владельцев, как в США или Великобритании. Поскольку недвижимость приносит доход в виде реальной арендной платы, первая страна имела бы неоправданно высокий ВВП по сравнению со второй — по крайней мере, в части доли недвижимости в экономике.

---

### 11. `p0215` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> With Britain well on the path to industrial capitalism, Smith’s *The* *Wealth of Nations* highlighted the role of the division of labour in manufacturing. His account of pin-manufacturing continues to be cited today as one of the first examples of organizational and technological change at the centre of the economic growth process. Explaining the immense increase in productivity that occurred when one worker was no longer responsible for producing an entire pin, but only for a small part of it, Smith related how the division of labour allowed an increase in specialization and hence productivity: I have seen a small manufactory of this kind where ten men only were employed, and where some of them consequently performed two or three distinct operations. But though they were very poor, and therefore but indifferently accommodated with the necessary machinery, they could, when they exerted themselves, make among them about twelve pounds of pins in a day. There are in a pound upwards of four thousand pins of a middling size. Those ten persons, therefore, could make among them upwards of forty-eight thousand pins in a day. Each person, therefore, making a tenth part of forty-eight thousand pins, might be considered as making four thousand eight hundred pins in a day. But if they had all wrought separately and independently, and without any of them having been educated to this peculiar business, they certainly could not each of them have made twenty, perhaps not one pin in a day; that is, certainly, not the two hundred and fortieth, perhaps not the four thousand eight hundredth part of what they are at present capable of performing, in consequence of a proper division and combination of their different operations.²⁰

**В озвучку попало:**

> Поскольку Британия уверенно шла по пути промышленного капитализма, в своей книге «Богатство народов» Смит подчеркнул роль разделения труда в производстве. Его описание изготовления булавок до сих пор приводят как один из первых примеров организационных и технологических изменений, лежащих в основе экономического роста. Объясняя колоссальный рост производительности, который возникал, когда один рабочий переставал отвечать за создание булавки целиком, а занимался лишь малой частью процесса, Смит писал: «Я видел небольшую мануфактуру такого рода, где было занято всего десять человек. Некоторые из них выполняли две или три отдельные операции. Несмотря на бедность и отсутствие необходимого оборудования, при должном усердии они могли изготовить около двенадцати фунтов булавок в день. В одном фунте содержится более четырех тысяч булавок среднего размера. Таким образом, эти десять человек могли сделать более сорока восьми тысяч булавок в день. Получается, что каждый из них, выполняя десятую часть работы, создавал по четыре тысячи восемьсот булавок в день. Но если бы они работали порознь, не будучи обученными этому ремеслу, каждый из них, безусловно, не смог бы сделать и двадцати, а возможно, и одной булавки в день. Это составило бы лишь малую долю — едва ли не четырехтысячную часть того, чего они способны достичь благодаря правильному разделению и сочетанию своих операций».

---

### 12. `p0252` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> By highlighting the different types of incomes earned, such as rent, profits and wages, Ricardo drew attention to an important question. When goods are sold, how are the proceeds of that sale divided? Does everyone involved get their ‘just share’ for the amount of effort they put into production? Ricardo’s answer was an emphatic ‘No’.

**В озвучку попало:**

> Выделяя различные виды доходов — ренту, прибыль и заработную плату, — Рикардо привлек внимание к важному вопросу. Как распределяется выручка от продажи товаров? Получает ли каждый участник свою «справедливую долю» за вложенные усилия? Ответ Рикардо был категоричным: «Нет».

---

### 13. `p0568` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> By this yardstick, Keynes commented, Wall Street could not ‘be claimed as one of the outstanding triumphs of *laissez-faire* capitalism – which is not surprising, if I am right in thinking that the best brains of Wall Street 22 have been in fact directed towards a different object’.

**В озвучку попало:**

> По этому критерию, отмечал Кейнс, Уолл-стрит «нельзя назвать одним из величайших триумфов капитализма свободной конкуренции. И это неудивительно, если я прав, полагая, что лучшие умы Уолл-стрит на самом деле заняты совсем другим».

---

### 14. `p0438` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> It is important to stress, however, that the difference between value added and final expenditure is not the government’s budget deficit. Rather, the deficit is government revenue (mainly taxes) minus expenses, including transfers of funds from the government to households, such as pensions and unemployment benefit – which, since households spend the money from pensions and benefits, are defined in national accounting as household, rather than government, spending (it’s the final expenditure that matters, remember). It is that household spending that counts towards final demand for the whole economy. So, what is going on?

**В озвучку попало:**

> Важно подчеркнуть, что разница между добавленной стоимостью и конечными расходами — это не бюджетный дефицит. Дефицит — это доходы государства, в основном налоги, минус расходы, включая трансферты домохозяйствам, такие как пенсии или пособия по безработице. Поскольку домохозяйства тратят эти деньги, в национальном учете они считаются расходами домохозяйств, а не государства. Помните: важны именно конечные расходы. Именно траты домохозяйств учитываются в конечном спросе всей экономики. Так что же здесь происходит?

---

### 15. `p0445` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> National accountants have therefore long adopted the so-called ‘inputs = outputs’ approach. Once the output is defined, value added can be computed because the costs of intermediate inputs, such as the computers that employees use, are known. But since government’s output is basically intermediate inputs plus labour costs, its value added is simply equal to its employees’ salaries. One significant consequence of this is that the estimate of government value added – unlike that of businesses – assumes no ‘profit’ or operating surplus on top of wages. (In Figure 8 above, the dark-grey line shows the value added of government; it is equal – with slight adjustments – to the share of government employment income in GDP.) In a capitalist system in which earning a profit is deemed the outcome of being productive, this is important because it makes government, whose activities tend to be non-profit, seem unproductive.

**В озвучку попало:**

> Поэтому специалисты по национальным счетам давно приняли подход «затраты равны результатам». Как только мы определяем объем выпуска, добавленную стоимость можно вычислить, так как затраты на промежуточные товары — например, компьютеры для сотрудников — нам известны. Но поскольку выпуск государства — это, по сути, промежуточные затраты плюс расходы на оплату труда, его добавленная стоимость равна просто сумме зарплат госслужащих. Важное следствие этого подхода: в оценке государственного сектора, в отличие от частного, не учитывается никакой «прибыль» или операционный излишек сверх зарплат. В капиталистической системе, где получение прибыли считается признаком продуктивности, это создает ложное впечатление, будто государство — сектор непроизводительный.

---

### 16. `p0949` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> The aim of the Bayh–Dole Act was to strengthen university–industry interactions and incentivize commercialization. Yet granting an exclusive licence on a university-owned patent deters follow-on innovations. Firms must now negotiate – and pay for – a licence before entering a market to access proprietary information that would previously have been available in publications.²⁷ Instead of encouraging better technology transfer – for example, of human stem cell patents held by the University of Wisconsin – 28 the system has delayed technology diffusion.

**В озвучку попало:**

> Целью закона было укрепление связей между университетами и промышленностью, а также стимулирование коммерциализации. Однако выдача исключительных лицензий на университетские патенты мешает дальнейшим инновациям. Теперь компаниям приходится вести переговоры и платить за лицензию, чтобы получить доступ к информации, которая раньше была доступна в научных публикациях. Вместо того чтобы способствовать передаче технологий, система замедлила их распространение.

---

### 17. `p0850` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> A truth more complex than the primacy of the shareholders, however, is that wealth creation is a collective process. After all, important as shareholders are, it is hard to imagine a company being successful without the involvement of many groups, including employees, suppliers, distributors, the broader community in which the company’s plants and headquarters are located, and even local and central government.

**В озвучку попало:**

> Однако реальность сложнее, чем просто приоритет интересов акционеров. Создание богатства — это коллективный процесс. Как бы важны ни были акционеры, трудно представить успех компании без участия многих групп: сотрудников, поставщиков, дистрибьюторов, местного сообщества, где расположены заводы и штаб-квартира, и даже государственных органов.

---

### 18. `p1253` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Price-equals-value thinking encourages companies to put financial markets and shareholders first, and to offer as little as possible to other stakeholders. This ignores the reality of value creation – as a collective process. In truth, everything concerning a company’s business – especially the underlying innovation and technological development – is intimately interwoven with decisions made by elected governments, investments made by schools, universities, public agencies and even movements by not-for-profit institutions. Corporate leaders are not telling the whole truth when they say that shareholders are the only real risk takers and hence deserve the lion’s share of the gains from doing business.

**В озвучку попало:**

> Убеждение, что цена равна ценности, заставляет компании ставить интересы финансовых рынков и акционеров превыше всего, предлагая остальным участникам процесса минимум. Это игнорирует тот факт, что создание ценности — процесс коллективный. На самом деле всё, что касается бизнеса компании, особенно фундаментальные инновации и технологическое развитие, тесно переплетено с решениями правительства, инвестициями в образование, науку и общественные институты. Корпоративные лидеры лукавят, когда говорят, что акционеры — единственные, кто рискует, и поэтому заслуживают львиную долю прибыли.

---

### 19. `p0443` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Given these lower prices, the usual way of calculating value added for a business doesn’t work with government activities. Let’s recall that value added is normally the value of output minus costs of intermediate inputs used in production. The value added by a business is basically workers’ wages plus the business’s operating surplus, the latter broadly similar to *gross operating profit* in business accounting terms. So adding up the non-market prices of government activities is likely to show less value added, because they are set with a different, non-commercial objective: to provide a service to the public. If the non-market prices of the output are lower than the total costs of intermediate inputs, value added would even show up as negative – indeed, government activities would ‘subtract’ value.

**В озвучку попало:**

> Из-за таких низких цен привычный метод расчета добавленной стоимости для бизнеса здесь не работает. Напомним: добавленная стоимость — это стоимость выпуска за вычетом затрат на промежуточные товары и услуги. Для бизнеса она складывается из зарплат сотрудников и операционной прибыли. Если мы будем суммировать нерыночные цены государственных услуг, мы получим заниженную добавленную стоимость, ведь цель государства — не извлечение прибыли, а общественное благо. Если нерыночная цена услуги ниже стоимости затрат на её производство, добавленная стоимость может даже оказаться отрицательной. Получается, что государственная деятельность как бы «вычитает» ценность из экономики.

---

### 20. `p0389` — длина озвучки / длина оригинала: 0.84; классы правки: —

**Исходный абзац:**

> According to marginalists, because value derives from price, somebody earning a very high salary is indicative of their productivity and worth. At the same time, anybody holding down a job at all is supposed to reflect their preference for work: the utility of work against that of leisure. GDP can be measured as the total amount of products produced, the total amount demanded, or the total income earned (with adjustments reviewed below). But if income is not necessarily a sign of productivity but of something else – for example the classicals’ notion of rent as ‘unearned income’ – what are the implications for GDP as a reliable measure of an economy’s productiveness?

**В озвучку попало:**

> Согласно маржиналистам, раз ценность определяется ценой, то высокий заработок человека — это показатель его продуктивности и значимости. В то же время считается, что любая работа отражает предпочтения человека: его выбор в пользу труда, а не отдыха. ВВП можно измерить как общую стоимость произведенных товаров, как совокупный спрос или как общую сумму доходов. Но если доход не всегда является признаком продуктивности, а, скажем, отражает классическое понятие ренты как «незаработанного дохода», то можно ли считать ВВП надежным мерилом продуктивности экономики?

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0690` — длина озвучки / длина оригинала: 1.60; классы правки: —

**Исходный абзац:**

> How does finance extract value? There are broadly three related answers: by inserting a wedge, in the form of transaction costs, between providers and receivers of finance; through monopoly power, especially in the case of banks; and with high charges relative to risks run, notably in fund management.

**В озвучку попало:**

> [thoughtful] Как именно финансовая система извлекает прибыль? Можно выделить три основных, взаимосвязанных способа. Во-первых, это создание своего рода «клиньев» в виде транзакционных издержек между теми, кто предоставляет капитал, и теми, кто его получает. Во-вторых, использование монопольной власти, что особенно характерно для банков. И в-третьих, установление высоких комиссий, которые зачастую не соответствуют реальным рискам, что особенно заметно в сфере управления фондами.

---

### 2. `p1137` — длина озвучки / длина оригинала: 1.50; классы правки: —

**Исходный абзац:**

> Fourth, governments often own productive businesses such as railways, postal services or energy providers. But, by accounting convention, state-owned enterprises that sell products at market prices are counted as private enterprises in the value added of the relevant sector: public railways are part of the transport sector, not the government sector. Even though state-owned corporations earn profits (and in the stats, higher profits means higher value added), their profits are accounted for in the industrial sector they work for, not the ‘government’ sector. So if the state-owned railway makes huge sales and profits (high value added), it boosts the transport sector value added, even if that sector is perhaps only successful because of state ownership. Only government-owned entities that don’t sell at market prices are by definition included in the government sector. In short, from the perspective of national accounting, you don’t count as government if you are doing market production. So, in the case of free public education, while increasing the number of teachers might add to

**В озвучку попало:**

> В-четвертых, государства часто владеют производственными предприятиями, такими как железные дороги, почтовые службы или энергетические компании. Но по правилам бухгалтерского учета государственные предприятия, продающие товары по рыночным ценам, учитываются как частные компании в составе соответствующего сектора. Например, государственные железные дороги относятся к транспортному сектору, а не к государственному. Даже если такие корпорации получают прибыль, а в статистике высокая прибыль означает высокую добавленную стоимость, она учитывается в той отрасли, где работает компания, а не в секторе «государство». Поэтому, если государственная железная дорога показывает огромные продажи и прибыль, это увеличивает добавленную стоимость транспортного сектора, даже если успех этого сектора обусловлен именно государственной собственностью. По определению, в государственный сектор включаются только те структуры, которые не продают свои услуги по рыночным ценам. Короче говоря, с точки зрения национального учета, если вы занимаетесь рыночным производством, вы не считаетесь государством. Так, в случае с бесплатным государственным образованием: увеличение числа учителей может добавить что-то к ВВП, поскольку им платят зарплату, но реальная ценность, которую они создают, в ВВП не отражается. Все это означает, что государство может увеличить свою добавленную стоимость только через нерыночное производство. Это скрывает истинную значимость государства в экономике: ценность, которую *действительно* создают государственные предприятия, не видна в официальной статистике, как и ценность, которую генерируют образование или здравоохранение.

---

### 3. `p0691` — длина озвучки / длина оригинала: 1.34; классы правки: —

**Исходный абзац:**

> In certain areas of the economy, such transaction costs are regarded as reducing efficiency and destroying value, not creating it. Governments are accused of inefficiency whenever they impose an income tax – which puts a wedge between what people receive for work and the value they place on leisure – or when they try to finance social security through a payroll tax, which disconnects wage costs from total labour costs. When they secure a pay rise for their members, trade unions are accused of increasing workers’ pay while their contribution to production remains the same.

**В озвучку попало:**

> В некоторых секторах экономики такие транзакционные издержки принято считать фактором, который снижает эффективность и разрушает стоимость, а не создает её. Правительства часто обвиняют в неэффективности, когда они вводят подоходный налог, ведь он создает разрыв между тем, что человек получает за свой труд, и ценностью, которую он придает отдыху. То же самое происходит, когда государство пытается финансировать социальное обеспечение через налоги на фонд оплаты труда, что разрывает связь между затратами на зарплату и общими расходами на рабочую силу. Профсоюзы также нередко подвергаются критике: когда они добиваются повышения зарплат для своих членов, их обвиняют в том, что они увеличивают доходы работников, хотя вклад этих работников в производство остается прежним.

---

### 4. `p1065` — длина озвучки / длина оригинала: 1.34; классы правки: —

**Исходный абзац:**

> After the 2008 financial crash – a crisis chiefly brought about by private, not public, debt – governments saved the capitalist system from breakdown. Not only did they pump money into the financial system: they took over private assets. A few months after Lehman Brothers collapsed, the US government was in charge of General Motors and Chrysler, the British government was running high street banks and, across the OECD, governments had committed the equivalent of 2.5 per cent of GDP to rescuing the system.

**В озвучку попало:**

> [serious] После финансового краха 2008 года — кризиса, вызванного прежде всего частными, а не государственными долгами, — правительства спасли капиталистическую систему от развала. Они не просто вливали деньги в финансовый сектор, они брали под контроль частные активы. Через несколько месяцев после банкротства банка «Леман Бразерс» правительство США взяло под управление компании «Дженерал Моторс» и «Крайслер», британское правительство начало управлять крупными коммерческими банками, а страны Организации экономического сотрудничества и развития в совокупности выделили на спасение системы сумму, эквивалентную двум с половиной процентам мирового валового внутреннего продукта.

---

### 5. `p0741` — длина озвучки / длина оригинала: 1.31; классы правки: —

**Исходный абзац:**

> Reform is not impossible. Financial regulation can be used to reward long-termism and also help to direct finance towards the real economy, as opposed to feeding on itself. Indeed, the point of the financial transaction tax – which has yet to be implemented – is precisely to reward long-term investments over quick millisecond trades.

**В озвучку попало:**

> Реформы возможны. Финансовое регулирование можно использовать для поощрения долгосрочного подхода и перенаправления капитала в реальную экономику, вместо того чтобы позволять финансовому сектору подпитываться самим собой. Собственно, смысл налога на финансовые транзакции, который до сих пор не внедрен, как раз и заключается в том, чтобы сделать долгосрочные инвестиции более выгодными по сравнению с молниеносными спекулятивными сделками.

---

### 6. `p1268` — длина озвучки / длина оригинала: 1.29; классы правки: —

**Исходный абзац:**

> With this in mind, we can move beyond the idea of public goods as ‘corrections’, that is being limited to areas that need fixing (due to positive externalities that they generate), to being ‘objectives’. This requires a new understanding of policy as actively ‘shaping’ and ‘creating’ markets that achieve public value, benefitting society more widely.

**В озвучку попало:**

> [thoughtful] С учетом этого мы можем выйти за рамки представления об общественных благах как о «корректировках» — то есть как о чем-то, что нужно лишь для исправления рыночных провалов из-за создаваемых ими положительных внешних эффектов. Вместо этого общественные блага должны стать «целями». Это требует нового понимания политики: она должна активно формировать и создавать рынки, которые приносят общественную пользу и работают на благо всего общества.

---

### 7. `p0878` — длина озвучки / длина оригинала: 1.29; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> The success of some of the companies has been extraordinary. Google’s share of the global desktop search engine market is more than 80 per cent,1 while just five US companies (Google, Microsoft, Amazon, Facebook and IBM) own most of the world’s data, with China’s Baidu being the only foreign company coming close. This market share also results in immense wealth: Apple’s cash pile was over $250 billion in 2017.

**В озвучку попало:**

> Успех некоторых компаний был просто невероятным. Доля Google на мировом рынке поисковых систем для компьютеров превышает восемьдесят процентов. При этом всего пять американских компаний — Google, Microsoft, Amazon, Facebook и IBM — владеют большей частью мировых данных. Единственная иностранная компания, которая приближается к ним, — это китайский Baidu. Такая доля рынка приносит колоссальное богатство: например, в две тысячи семнадцатом году объем денежных средств на счетах Apple превышал двести пятьдесят миллиардов долларов.

---

### 8. `p0638` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> It has led less regulated ‘non-bank financial institutions’ or ‘shadow banks’ to expand where banks were forced to contract. What we must now look at is the wider web of different financial intermediaries that have cropped up, with their desire to make a quick, high return and their effect on company organization and the evolution of industry.

**В озвучку попало:**

> [curious] Это привело к тому, что менее регулируемые «небанковские финансовые организации» или «теневые банки» стали расширяться там, где банки были вынуждены сокращать деятельность. Теперь нам необходимо рассмотреть более широкую сеть различных финансовых посредников, которые появились в последнее время. Важно понять их стремление к быстрой и высокой прибыли, а также то, как они влияют на организацию компаний и развитие промышленности.

---

### 9. `p0077` — длина озвучки / длина оригинала: 1.27; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Apple is the world’s biggest company by stock market value. In 2015 it 4 held a mountain of cash and securities outside the US worth $187 billion – about the same size as the Czech Republic’s economy that year⁵ – to avoid paying the US taxes that would be due on the profits if they were repatriated. Under a deal with Ireland dating back to 1991, two Irish subsidiaries of Apple received very generous tax treatment. The subsidiaries were Apple Sales International (ASI), which recorded all the profits earned on sales of iPhones and other Apple devices in Europe, the Middle East, Africa and India; and Apple Operations Europe, which made computers. Apple transferred development rights of its products to ASI for a nominal amount, thereby depriving the US taxpayer of revenues from technologies, embodied in Apple products, whose early development the taxpayer had funded. The European Commission alleged that the maximum rate payable on those profits booked through Ireland which were liable for tax was 1 per cent, but that in 2014 Apple paid tax at 0.005 per cent. The usual rate of corporation tax in Ireland is 12.5 per cent.

**В озвучку попало:**

> [serious] Apple — крупнейшая в мире компания по рыночной стоимости акций. В две тысячи пятнадцатом году она хранила за пределами США горы наличности и ценных бумаг на сумму сто восемьдесят семь миллиардов долларов — это примерно равно объему экономики Чехии за тот же год. Так компания избегала уплаты американских налогов, которые пришлось бы отдать с этой прибыли при ее возвращении в страну. Согласно соглашению с Ирландией, заключенному еще в тысяча девятьсот девяносто первом году, две ирландские дочерние компании Apple пользовались крайне выгодным налоговым режимом. Одной из них была Apple Sales International, которая фиксировала всю прибыль от продаж айфонов и других устройств Apple в Европе, на Ближнем Востоке, в Африке и Индии. Другой была Apple Operations Europe, занимавшаяся производством компьютеров. Apple передала права на разработку своих продуктов компании Apple Sales International за номинальную сумму. Тем самым она лишила американских налогоплательщиков доходов от технологий, заложенных в продукты Apple, ранние этапы разработки которых эти самые налогоплательщики и финансировали. Европейская комиссия заявила, что максимальная ставка налога на прибыль, зафиксированную через Ирландию, составляла один процент, но в две тысячи четырнадцатом году Apple заплатила налог по ставке ноль целых пять тысячных процента. При этом обычная ставка корпоративного налога в Ирландии составляет двенадцать с половиной процентов.

---

### 10. `p1131` — длина озвучки / длина оригинала: 1.27; классы правки: —

**Исходный абзац:**

> The national accounts fail to capture the full amount of this government value added and have several major flawed assumptions. First of all, national accounts regard most of government value added only as costs, mainly pay to government employees; government activity lacks an operating surplus, which would increase its value added. Let’s compare it with the private sector. The share of pay in private-sector value added is rarely above 70 per cent. On that basis, you could say that government value added is on average only 70 per cent of what it should be.

**В озвучку попало:**

> Национальные счета не способны отразить весь объем добавленной стоимости, создаваемой государством, и опираются на ряд ошибочных допущений. Во-первых, они рассматривают большую часть государственной добавленной стоимости исключительно как издержки, в основном — зарплаты бюджетников. Государственная деятельность в такой системе лишена операционной прибыли, которая могла бы увеличить показатель добавленной стоимости. Давайте сравним это с частным сектором. Доля зарплат в добавленной стоимости частных компаний редко превышает семьдесят процентов. Исходя из этого, можно сказать, что государственная добавленная стоимость в среднем составляет лишь семьдесят процентов от того, чем она могла бы быть на самом деле.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1009` — совпадение символов с оригиналом: 29%; классы правки: —

**Исходный абзац:**

> Six firms (Facebook, Google, Yahoo, AOL, Twitter and Amazon) account for around 53 per cent of the digital advertising market (with just Google and Facebook making up 39 per cent).⁷¹ Such dominance implies that online giants can impose their conditions on users and customer firms.

**В озвучку попало:**

> Шесть компаний — Facebook, Google, Yahoo, AOL, Twitter и Amazon — занимают около 53 процентов рынка цифровой рекламы, причем на долю Google и Facebook приходится 39 процентов. Такое доминирование означает, что интернет-гиганты могут диктовать свои условия пользователям и компаниям-клиентам.

---

### 2. `p0916` — совпадение символов с оригиналом: 24%; классы правки: year_lost

**Исходный абзац:**

> Much of the work to commercialize military technology was done in the research labs of established ICT companies like General Electric, Texas Instruments, AT&T, Xerox and IBM. Employees of these companies left to found their own start-ups. The Small Business Investment Company, set up in 1958 by the government’s Small Business Administration, itself founded in 1953, helped many of the start-ups to raise capital.

**В озвучку попало:**

> Большая часть работы по коммерциализации военных технологий проводилась в лабораториях таких признанных компаний, как General Electric, Texas Instruments, AT&T, Xerox и IBM. Сотрудники этих корпораций уходили, чтобы основывать собственные стартапы. А государственное Управление по делам малого бизнеса, созданное в 1953 году, через свои инвестиционные компании помогало многим новичкам привлекать капитал.

---

### 3. `p0878` — совпадение символов с оригиналом: 23%; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> The success of some of the companies has been extraordinary. Google’s share of the global desktop search engine market is more than 80 per cent,1 while just five US companies (Google, Microsoft, Amazon, Facebook and IBM) own most of the world’s data, with China’s Baidu being the only foreign company coming close. This market share also results in immense wealth: Apple’s cash pile was over $250 billion in 2017.

**В озвучку попало:**

> Успех некоторых компаний был просто невероятным. Доля Google на мировом рынке поисковых систем для компьютеров превышает восемьдесят процентов. При этом всего пять американских компаний — Google, Microsoft, Amazon, Facebook и IBM — владеют большей частью мировых данных. Единственная иностранная компания, которая приближается к ним, — это китайский Baidu. Такая доля рынка приносит колоссальное богатство: например, в две тысячи семнадцатом году объем денежных средств на счетах Apple превышал двести пятьдесят миллиардов долларов.

---

### 4. `p0990` — совпадение символов с оригиналом: 21%; классы правки: —

**Исходный абзац:**

> In just a few years, firms such as Google, Facebook, Twitter, Amazon and eBay have come from nowhere to being almost indispensable in the lives of billions of people around the world. These companies increasingly dominate how we find information, connect and communicate, maintain our friendships, document our lives, shop and share our thoughts with anyone who cares to listen. The new technologies behind these companies have revealed – or created – in us new wants and needs. Any number of firms, each with broadly similar technologies, might have met these needs.

**В озвучку попало:**

> Всего за несколько лет такие компании, как Google, Facebook, Twitter, Amazon и eBay, прошли путь из ниоткуда до статуса практически незаменимых сервисов для миллиардов людей по всему миру. Эти корпорации всё больше определяют то, как мы ищем информацию, общаемся, поддерживаем дружбу, фиксируем события нашей жизни, совершаем покупки и делимся мыслями со всеми, кто готов нас слушать. Новые технологии, лежащие в основе этих компаний, выявили — или создали — в нас новые желания и потребности. И ведь многие другие фирмы, обладая схожими технологиями, могли бы удовлетворить эти запросы.

---

### 5. `p1008` — совпадение символов с оригиналом: 21%; классы правки: —

**Исходный абзац:**

> Google alone accounts for 70 per cent of online searches in the US, and 90 per cent in Europe. Facebook has more than 1.5 billion users, a quarter of the planet’s population and streets ahead of its competitors. Amazon now accounts for around half of the US books market, not to mention e-books.

**В озвучку попало:**

> На долю одного только Google приходится 70 процентов поисковых запросов в США и 90 процентов в Европе. У Facebook более полутора миллиардов пользователей — это четверть населения планеты, что намного опережает любых конкурентов. Amazon сегодня контролирует около половины книжного рынка США, не говоря уже об электронных книгах.

---

### 6. `p0046` — совпадение символов с оригиналом: 20%; классы правки: —

**Исходный абзац:**

> These stories of value creation are not limited to finance. In 2014 the pharmaceutical giant Gilead priced its new treatment for the life-threatening hepatitis C virus, Harvoni, at $94,500 for a three-month course. Gilead justified charging this price by insisting that it represented ‘value’ to health systems. John LaMattina, former President of R&D at the drugs company Pfizer, argued that the high price of speciality drugs is justified by how beneficial they are for patients and for society in general.

**В озвучку попало:**

> [serious] Эти истории о создании ценности не ограничиваются финансами. В 2014 году фармацевтический гигант Gilead установил цену на свой новый препарат для лечения опасного для жизни гепатита C — Харвони — в размере 94 500 долларов за трехмесячный курс. Gilead оправдывала такую стоимость, настаивая на том, что она отражает «ценность» для систем здравоохранения. Джон ЛаМаттина, бывший президент по исследованиям и разработкам фармацевтической компании Pfizer, утверждал, что высокая цена специализированных лекарств оправдана тем, насколько они полезны для пациентов и общества в целом.

---

### 7. `p1006` — совпадение символов с оригиналом: 20%; классы правки: —

**Исходный абзац:**

> Uber, like Google, Facebook and Amazon, seems to have no limit to its size. The network effects that pervade online markets add an important peculiarity: once a firm establishes leadership in a market its dominance increases and becomes self-perpetuating almost automatically. If everyone is on Facebook, no one wants to join a different social network. As most people search on Google, the gap between Google and its competitors grows wider because it can elaborate on more data. And as its market share rises, so does its capacity to attract users, which in turn increases its 70 market dominance.

**В озвучку попало:**

> Uber, как и Google, Facebook или Amazon, кажется, не имеет пределов роста. Сетевые эффекты, пронизывающие онлайн-рынки, добавляют важную особенность: как только фирма занимает лидирующие позиции, ее доминирование усиливается и становится почти автоматическим. Если все пользуются Facebook, никто не хочет переходить в другую социальную сеть. Поскольку большинство людей ищут информацию через Google, разрыв между ним и конкурентами увеличивается, ведь система постоянно совершенствуется на основе накопленных данных. По мере роста доли рынка растет и способность привлекать новых пользователей, что, в свою очередь, еще больше укрепляет доминирующее положение.

---

### 8. `p0997` — совпадение символов с оригиналом: 20%; классы правки: —

**Исходный абзац:**

> All this sounds fine until you ask yourself what it might mean for the size of companies. A strong source of increasing returns to scale necessarily expands companies. Google’s size is a direct result of the network effects typical of Internet-based services. Google is not just a search engine. It is also an email address (Gmail), a conference call maker (Google Hangout), a document creator and editor – all designed to maximize the advantages of sticking to Google: you cannot use Google Hangout without a Gmail address.

**В озвучку попало:**

> [serious] Всё это звучит логично, пока вы не задумаетесь, что это означает для масштабов компаний. Мощный источник возрастающей отдачи от масштаба неизбежно ведет к их росту. Огромные размеры Google — прямой результат сетевых эффектов, характерных для интернет-сервисов. Google — это не просто поисковик. Это и электронная почта, и инструмент для видеоконференций, и платформа для создания документов. Все эти продукты разработаны так, чтобы вы оставались внутри экосистемы Google: например, вы не сможете воспользоваться сервисом для звонков без учетной записи Gmail.

---

### 9. `p0667` — совпадение символов с оригиналом: 20%; классы правки: —

**Исходный абзац:**

> So when the global financial crisis arrived in 2007 it blew apart the ideology that had promoted financialization above all else. Yet the crisis did not fundamentally change how the sector is valued: two years later the head of Goldman Sachs could still keep a straight face when arguing that his bankers were the most productive in the world. And the fact that ex- Goldman Sachs employees were abundant in both the Obama and Trump administrations shows the power of the ‘story’ of the value created by Goldman Sachs across political parties.

**В озвучку попало:**

> Поэтому, когда в 2007 году разразился мировой финансовый кризис, он разрушил идеологию, ставившую финансовизацию превыше всего. Тем не менее кризис не изменил фундаментально подход к оценке сектора. Два года спустя глава Goldman Sachs мог с невозмутимым лицом утверждать, что его банкиры — самые продуктивные в мире. А тот факт, что бывшие сотрудники Goldman Sachs занимали множество постов в администрациях Обамы и Трампа, лишь подтверждает силу истории о ценности, создаваемой этим банком, в обеих политических партиях.

---

### 10. `p0079` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Ireland, the Commission alleged, had offered Apple ultra-low taxes in return for the creation of jobs in other Apple businesses there. Apple and Ireland rejected the Commission’s demand – and of course Apple is not the only major corporation to have constructed exotic tax structures.

**В озвучку попало:**

> [thoughtful] Комиссия утверждала, что Ирландия предложила Apple сверхнизкие налоги в обмен на создание рабочих мест в других подразделениях компании в стране. Apple и Ирландия отвергли требование Комиссии. И, конечно, Apple — не единственная крупная корпорация, выстроившая подобные экзотические налоговые схемы.

---
## Абзацы, оставшиеся в озвучке на английском (0)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.
## Пустые и почти пустые абзацы (7)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0084` — длина озвучки / длина оригинала: 0.95; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### COMMON CRITIQUES OF VALUE EXTRACTION

**В озвучку попало:**

> ### ОБЩАЯ КРИТИКА ИЗВЛЕЧЕНИЯ СТОИМОСТИ

---

### 2. `p0165` — длина озвучки / длина оригинала: 0.95; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### THE MERCANTILISTS: TRADE AND TREASURE

**В озвучку попало:**

> ### Меркантилисты: торговля и сокровища

---

### 3. `p0188` — длина озвучки / длина оригинала: 0.73; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### THE PHYSIOCRATS: THE ANSWER LIES IN THE SOIL

**В озвучку попало:**

> ### ФИЗИОКРАТЫ: ОТВЕТ СКРЫТ В ЗЕМЛЕ

---

### 4. `p0398` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### A Brief History of National Accounts

**В озвучку попало:**

> ### Краткая история национальных счетов

---

### 5. `p0419` — длина озвучки / длина оригинала: 0.75; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### THE SYSTEM OF NATIONAL ACCOUNTS COMES INTO BEING

**В озвучку попало:**

> ### СИСТЕМА НАЦИОНАЛЬНЫХ СЧЕТОВ: ИСТОКИ

---

### 6. `p0541` — длина озвучки / длина оригинала: 0.79; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### DEREGULATION AND THE SEEDS OF THE CRASH

**В озвучку попало:**

> ### Дерегулирование и истоки краха

---

### 7. `p0745` — длина озвучки / длина оригинала: 0.95; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 6 Financialization of the Real Economy

**В озвучку попало:**

> ## 6 Финансиализация реальной экономики

---
