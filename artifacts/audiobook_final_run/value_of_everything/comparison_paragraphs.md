# Аудиокнига, финальный подтверждающий прогон 2026-08-06 — value_of_everything, материал для просмотра глазами

Книга: Mariana Mazzucato, *The Value of Everything* (`tests/sources/book/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_fin2_value_of_everything`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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

Всего абзацев отдано модели: 1277; вернулось: 1276;
дошло до narration-артефакта: 1242.
Пул прозы, из которого делалась выборка: 811 абзацев.
Медианное отношение длин по прозе: 1.0299.

---
## Случайная выборка (49 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0055` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> If there are so many wealth creators in industry, the inevitable conclusion is that at the opposite side of the spectrum featuring fleet-footed bankers, science-based pharmaceuticals and entrepreneurial geeks are the inert, value-extracting civil servants and bureaucrats in government. In this view, if private enterprise is the fast cheetah bringing innovation to the world, government is a plodding tortoise impeding progress – or, to invoke a different metaphor, a Kafkaesque bureaucrat, buried under papers, cumbersome and inefficient. Government is depicted as a drain on society, funded by obligatory taxes on long-suffering citizens. In this story, there is always only one conclusion: that we need more market and less state. The slimmer, trimmer and more efficient the state machine the better.

**В озвучку попало:**

> Если в промышленности так много создателей богатства, то неизбежный вывод таков: на другом полюсе, в противовес шустрым банкирам, наукоемким фармацевтам и предприимчивым гикам, находятся инертные, извлекающие ценность госслужащие и бюрократы. В этой картине мира частный бизнес — это быстрый гепард, приносящий миру инновации, а правительство — медлительная черепаха, тормозящая прогресс. Или, если использовать другую метафору, это кафкианский чиновник, заваленный бумагами, неповоротливый и неэффективный. Государство изображается как обуза для общества, существующая за счет принудительных налогов с многострадальных граждан. В этой истории всегда один вывод: нам нужно больше рынка и меньше государства. Чем стройнее и эффективнее государственная машина, тем лучше.

---

### 2. `p0081` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> It is clear that Apple’s highly complex tax arrangements were principally designed to extract the maximum value from its business by avoiding paying substantial taxes which would have benefited the societies in which the company operated. Apple certainly creates value, of that there is no doubt: but to ignore the support taxpayers have given it, and then to pit states and countries against each other, is surely not the way to build an innovative economy or achieve growth that is inclusive, that benefits a wide section of the population, not only those best able to ‘game’ the system.

**В озвучку попало:**

> [serious] Очевидно, что сложнейшие налоговые схемы Apple были разработаны прежде всего для извлечения максимальной выгоды. Компания стремилась избежать уплаты значительных налогов, которые могли бы принести пользу обществам, где она вела свою деятельность. Безусловно, Apple создает ценность, в этом нет никаких сомнений. Однако игнорировать поддержку, которую ей оказывали налогоплательщики, и при этом стравливать между собой штаты и целые страны — это явно не тот путь, который ведет к созданию инновационной экономики. Такой подход не способствует инклюзивному росту, который приносил бы пользу широким слоям населения, а не только тем, кто лучше всех умеет играть по правилам системы.

---

### 3. `p0098` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> For a long time the idea of value was at the heart of debates about the economy, production and the distribution of the resulting income, and there were healthy disagreements over what value actually resided in. For some economic schools of thought, the price of products resulted from supply and demand, but the value of those products derived from the amount of work that was needed to produce things, the ways in which technological and organizational changes were affecting work, and the relations between capital and labour. Later, this emphasis on ‘objective’ conditions of production, technology and power relationships was replaced by concepts of scarcity and the ‘preferences’ of economic actors: the amount of work supplied is determined by workers’ preference for leisure over earning a higher amount of money. Value, in other words, became *subjective*.

**В озвучку попало:**

> Долгое время понятие ценности находилось в центре дискуссий об экономике, производстве и распределении доходов. Вокруг того, в чем именно заключается ценность, велись серьезные споры. Для одних экономических школ цена продукта определялась спросом и предложением, но сама ценность товара зависела от количества труда, затраченного на его создание, от влияния технологических и организационных изменений на этот труд, а также от отношений между капиталом и наемными работниками. Позже этот акцент на объективных условиях производства, технологиях и отношениях власти сменился концепциями дефицита и «предпочтений» экономических субъектов. Теперь количество затраченного труда стало определяться тем, что работники предпочитают отдых заработку больших денег. Иными словами, ценность стала субъективной.

---

### 4. `p0118` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Indeed, the recurring debate about the optimal size of government and the supposed perils of high public debt boils down to whether government spending helps the economy to grow – because government can be productive and add value – or whether it holds back the economy because it is unproductive or even destroys value*.* The issue is politically loaded and deeply colours current debates, ranging from whether the UK can afford Trident nuclear weapons to whether there is a ‘magic number’ for the size of government, defined as government spending as a proportion of national output, beyond which an economy will inevitably do less well than it might have done if government spending had been lower. As we will explore in Chapter 8, this question is more tainted by political views and ideological positions than informed by deep scientific proofs. Indeed, it is important to remember that economics is at heart a social science, and the ‘natural’ size of government will depend on one’s theory of (or simply ‘position’ on) the purpose of government. If it is seen as useless, or at best a fixer of occasional problems, its optimum size will inevitably be notionally smaller than if it is viewed as a key engine of growth needed to steer and invest in the value creation process.

**В озвучку попало:**

> [serious] Постоянные дебаты об оптимальном размере государства и опасностях высокого госдолга сводятся к одному вопросу. Помогают ли государственные расходы экономике расти, потому что государство может быть продуктивным и создавать ценность? Или же они сдерживают экономику, будучи непроизводительными или даже разрушительными? Этот вопрос политически ангажирован и глубоко влияет на современные дискуссии. От того, может ли Великобритания позволить себе ядерное оружие, до поиска «магического числа» — оптимальной доли госрасходов в национальном продукте, после которой экономика якобы неизбежно начинает стагнировать. Как мы увидим в восьмой главе, этот вопрос больше пропитан идеологией, чем подкреплен строгими научными доказательствами. Важно помнить: экономика — это прежде всего социальная наука. «Естественный» размер государства зависит от того, какой теории вы придерживаетесь и какова, по вашему мнению, цель государственной власти. Если считать государство бесполезным или лишь «пожарным», исправляющим случайные сбои, его оптимальный размер будет казаться меньше. Если же видеть в нем ключевой двигатель роста, способный инвестировать в создание ценности, то и подход к его масштабам будет иным.

---

### 5. `p0124` — длина озвучки / длина оригинала: 0.85; классы правки: —

**Исходный абзац:**

> Second, the lack of analysis of value has massive implications for one particular area: the distribution of income between different members of society. When value is determined by price (rather than vice versa), the level and distribution of income seem justified as long as there is a market for the goods and services which, when bought and sold, generate that income. All income, according to this logic, is earned income: gone is any analysis of activities in terms of whether they are productive or unproductive.

**В озвучку попало:**

> Во-вторых, отсутствие анализа стоимости имеет серьезные последствия для распределения доходов между членами общества. Когда стоимость определяется ценой, а не наоборот, уровень и распределение доходов кажутся справедливыми до тех пор, пока существует рынок для товаров и услуг, приносящих этот доход. Согласно такой логике, любой доход считается заслуженным. Исчезает само понятие разделения деятельности на продуктивную и непродуктивную.

---

### 6. `p0130` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> Once impediments to competition are removed, the outcome should benefit everyone. How different notions of value might affect the distribution of revenues between workers, public agencies, managers and shareholders at, say, Google, General Electric or BAE Systems, goes unquestioned.

**В озвучку попало:**

> Считается, что как только препятствия для конкуренции будут устранены, результат принесет пользу всем. Вопрос о том, как различные представления о стоимости влияют на распределение доходов между работниками, государственными органами, менеджерами и акционерами, скажем, в Google, General Electric или BAE Systems, остается без внимания.

---

### 7. `p0151` — длина озвучки / длина оригинала: 1.11; классы правки: truncated_sentence

**Исходный абзац:**

> To create a fairer economy, one where prosperity is more broadly shared and is therefore more sustainable, we need to reinvigorate a serious discussion about the nature and origin of value. We must reconsider the stories we are telling about who the value creators are, and what that says to us about how we define activities as economically productive and unproductive. We cannot limit progressive politics to taxing wealth, but require a new understanding of and debate about wealth creation so that it is more fiercely and openly contested. Words matter: we need a new vocabulary for policymaking. Policy is not just about ‘intervening’. It is about shaping a different future: co-creating markets and value, not just ‘fixing’ markets or redistributing value. It’s about taking risks, not only

**В озвучку попало:**

> Чтобы создать более справедливую экономику, где процветание распределяется шире и потому является более устойчивым, нам нужно возобновить серьезный разговор о природе и происхождении ценности. Мы должны пересмотреть истории, которые рассказываем о том, кто является создателем ценности, и как это влияет на наше определение продуктивной и непродуктивной деятельности. Мы не можем ограничить прогрессивную политику лишь налогообложением богатства. Нам нужно новое понимание процесса создания богатства, чтобы этот вопрос стал предметом открытого и острого спора. Слова имеют значение: нам нужен новый словарь для формирования государственной политики. Политика — это не просто «вмешательство». Это формирование будущего: совместное создание рынков и ценностей, а не просто «исправление» рыночных ошибок или перераспределение уже созданного. Речь идет о принятии рисков, а не только о

---

### 8. `p0153` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> This idea that we can shape markets has important consequences. We can create a better economy by understanding that markets are outcomes of decisions that are made – in business, in public organizations and in civil society. The eight-hour working day has formed markets – and that was the result of a fight held in labour organizations. And perhaps the reason there is so much despair across the globe – despair now leading to populist politics – is that the economy is presented to us simply as ‘made’ by trade rules, technocrats and neoliberal forces. Indeed, as the book will show, ‘value’ theory itself is presented as a sort of objective force determined by supply and demand, rather than deeply embedded in particular ways of seeing the world. The economy can indeed be made and shaped – but it can be done either in fear or in hope.

**В озвучку попало:**

> [thoughtful] Идея о том, что мы способны формировать рынки, имеет важные последствия. Мы можем создать лучшую экономику, если осознаем: рынки — это результат решений, принимаемых в бизнесе, государственных организациях и гражданском обществе. Восьмичасовой рабочий день сформировал рынки, и это стало итогом борьбы профсоюзов. Возможно, причина повсеместного отчаяния, которое сегодня подпитывает популизм, кроется в том, что нам преподносят экономику как нечто, созданное исключительно торговыми правилами, технократами и неолиберальными силами. В этой книге мы увидим, что сама теория стоимости подается как объективная сила, определяемая спросом и предложением, а не как концепция, глубоко укорененная в определенных взглядах на мир. Экономику действительно можно создавать и менять, но делать это можно либо из страха, либо с надеждой.

---

### 9. `p0232` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Smith’s penetrating analysis of how advanced capitalist economies functioned won him many followers. Equally, his staunch advocacy of free trade, in an era in which mercantilist policies were beginning to be seen as old-fashioned (Smith, indeed, believed that merchants were unproductive because they only provided the ephemeral service of moving goods around, rather than producing anything of value), made his book a hit among the ‘free traders’ who eventually overturned England’s Corn Laws, which imposed heavy tariffs on imported corn to protect domestic landowners, and other protectionist measures. Armed with Smith’s ideas, free traders showed that nations could get richer even if there was no trade surplus and no gold accumulation. Amassing gold was unnecessary and insufficient for growth. Huge amounts of gold flowed to Spain from its colonies, but the kingdom did not become more productive.

**В озвучку попало:**

> Проницательный анализ того, как функционируют развитые капиталистические экономики, принес Смиту множество последователей. Его решительная поддержка свободной торговли также сделала книгу хитом среди сторонников фритредерства. В то время меркантилистская политика уже начинала казаться старомодной. Смит, к слову, считал торговцев непроизводительными, поскольку они лишь оказывали мимолетную услугу по перемещению товаров, а не создавали ничего ценного. Сторонники свободной торговли в итоге добились отмены «хлебных законов», которые вводили высокие пошлины на импортное зерно для защиты местных землевладельцев, и других протекционистских мер. Вооружившись идеями Смита, они доказали, что нации могут богатеть, даже если у них нет торгового профицита или накоплений золота. Накопление золота было излишним и недостаточным условием для роста. Огромные потоки золота текли в Испанию из колоний, но королевство от этого не стало производительнее.

---

### 10. `p0294` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Marx then identified ‘interest-bearing’ capital – capitalists such as banks who earned interest on loans that production capitalists took out to expand production. The generation of interest is possible because, in capitalism, money represents not just purchasing power – buying commodities for consumption – but also the potential to generate more profit in the future through investment as capital.⁵⁷ The interest is deducted from the production capitalist’s profit rate. Interest-bearing capital, unlike commercial capital, does not lower the general rate of profit; it just subdivides it between recipients of interest and earners of profit.

**В озвучку попало:**

> [thoughtful] Маркс также выделил «ссудный» капитал. Это капиталисты, например банки, которые получают проценты по кредитам, выдаваемым производственным компаниям для расширения их деятельности. Получение процентов возможно потому, что в условиях капитализма деньги — это не просто покупательная способность для приобретения товаров. Это еще и потенциал для извлечения будущей прибыли через инвестиции в капитал. Проценты вычитаются из прибыли производственного капиталиста. В отличие от торгового капитала, ссудный капитал не снижает общую норму прибыли, а лишь распределяет её между теми, кто получает проценты, и теми, кто зарабатывает прибыль.

---

### 11. `p0323` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> The marginal utility theory of value states that all income is reward for a productive undertaking. Given the large investments being made in factories and the edifices of the Industrial Revolution, it suited the changing circumstances of the second half of the nineteenth century. But it did not come out of nowhere; indeed, it has a long history. In medieval times, thinkers argued that ‘just prices’ were those that reflected an object’s utility. In his *Summa Theologica*, the thirteenth century philosopher-theologian Thomas Aquinas discussed the concept of the just price in a section of the book called ‘Of Cheating, Which Is Committed in Buying and Selling’. Just price was a normative concept, against what was seen as the wrong price resulting from morally evil greed. The medieval Church inveighed against the sin of greed and avarice, which broadly meant profiteering by middlemen and moneylenders. In Dante’s *Inferno*, usurers are consigned to the hottest part of hell (circle 7) because they are making money not from the productive sources, which for Dante were Nature or Art, but from speculative changes in interest rates. Indeed, he is so disgusted by usury that he puts usurers just below the circle of hell housing the sodomites.

**В озвучку попало:**

> Теория предельной полезности утверждает, что любой доход — это вознаграждение за производительную деятельность. Учитывая огромные инвестиции в заводы и инфраструктуру промышленной революции, эта идея хорошо вписалась в меняющиеся условия второй половины девятнадцатого века. Однако она не возникла на пустом месте; у неё долгая история. В Средние века мыслители доказывали, что «справедливые цены» — это те, что отражают полезность объекта. В своей «Сумме теологии» философ и теолог тринадцатого века Фома Аквинский обсуждал понятие справедливой цены в разделе «О мошенничестве, совершаемом при купле и продаже». Справедливая цена была нормативным понятием, противопоставленным тому, что считалось неверной ценой, порожденной греховной жадностью. Средневековая церковь клеймила грех алчности, под которым в широком смысле понималась нажива посредников и ростовщиков. В «Аду» Данте ростовщики отправлены в самую жаркую часть преисподней, потому что они зарабатывают деньги не на производительных источниках — которыми для Данте были природа или искусство, — а на спекулятивных изменениях процентных ставок. Данте настолько презирал ростовщичество, что поместил ростовщиков даже ниже круга ада, где мучаются содомиты.

---

### 12. `p0329` — длина озвучки / длина оригинала: 1.17; классы правки: truncated_sentence

**Исходный абзац:**

> At some point the utility gained from eating them will decrease.⁷ In this way, the utility of the last bar is less, possibly much less, than that of earlier bars. This is ‘marginal utility’ – in the case of a Mars Bar, worth less to you than the previous one, ‘decreasing marginal utility’. By the same token, the scarcer a thing is, the more utility it gives you –

**В озвучку попало:**

> В какой-то момент полезность от поедания батончиков начнет снижаться. Таким образом, полезность последнего съеденного батончика меньше, а возможно, и значительно меньше, чем предыдущих. Это и есть «предельная полезность». В случае с батончиком, он стоит для вас меньше, чем предыдущий — это называется «убывающей предельной полезностью». По той же логике, чем более редкой является вещь, тем больше полезности она вам приносит —

---

### 13. `p0473` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Capital gains on buying and selling property are treated like those that apply to a business or a financial asset – although the extent to which a building is ‘productive’ is debatable. Capital gains from holding property arise out of increases in land value, which itself are determined by collective investment (in roads, schools, etc.) – little to do with the effort of the property owner.

**В озвучку попало:**

> [serious] Прибыль от купли-продажи недвижимости облагается налогами так же, как доходы от бизнеса или финансовых активов. Однако вопрос о том, насколько здание является «продуктивным» активом, остается спорным. Рост стоимости недвижимости часто обусловлен повышением цен на землю, что, в свою очередь, зависит от коллективных инвестиций — например, в строительство дорог или школ, — а не от усилий самого владельца.

---

### 14. `p0477` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Equally importantly, the boundary loops around the issue of the environment. Consider a river polluted by industrial waste. When the polluter pays to clean it up, the expenditure is treated as a cost which reduces profits and GDP. But when the government pays another company to clean up the river, the expenditure adds to GDP because paying workers adds value. If the cost of cleaning up pollution is borne by someone other than the polluter it is called an externality – the cost is ‘outside’ the polluter’s profit-and-loss account – and increases GDP. Kuznets argued that such a calculation should be balanced by the ‘disservice’ that has been created by pollution, and therefore that the cost of that ‘disservice’ be taken out of the ‘net’ calculation of value added. But national accounts do not do that: instead, they state that it is not ‘appropriate’ or ‘analytically useful’ for ‘economic accounts to try to correct for presumed institutional failures of this kind by attributing costs to producers that society does not 34 choose to recognize’.

**В озвучку попало:**

> Не менее важна и экологическая составляющая. Представьте реку, загрязненную промышленными отходами. Когда виновник загрязнения платит за очистку, эти расходы считаются издержками, которые снижают прибыль и ВВП. Но если правительство платит другой компании за очистку той же реки, эти расходы увеличивают ВВП, поскольку оплата труда рабочих создает добавленную стоимость. Если расходы на борьбу с загрязнением несет кто-то другой, а не виновник, это называют внешним эффектом — затраты остаются «вне» отчета о прибылях и убытках загрязнителя, — и при этом ВВП растет. Саймон Кузнец утверждал, что такие расчеты должны уравновешиваться «ущербом», нанесенным загрязнением, и что стоимость этого ущерба следует вычитать из чистого показателя добавленной стоимости. Однако национальные счета этого не делают. Вместо этого статистики заявляют, что экономический учет не должен пытаться исправлять институциональные провалы, возлагая на производителей расходы, которые общество не считает нужным признавать.

---

### 15. `p0478` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> National accountants present this question of whether something is ‘analytically useful’ or not as a vague argument, without reference to value. To be fair, they also rightly caution that it would be extremely difficult comprehensively to cost such externalities – negative or positive ‘side effects’ of production – which are not priced. All of which just highlights the difficulties of being consistent and drawing a clear production boundary.

**В озвучку попало:**

> [serious] Национальные бухгалтеры представляют вопрос о том, является ли что-то «аналитически полезным», как некий расплывчатый аргумент, не опираясь на понятие ценности. Справедливости ради, они также верно предупреждают: крайне сложно всесторонне оценить такие внешние эффекты — негативные или позитивные «побочные продукты» производства, — у которых нет рыночной цены. Все это лишь подчеркивает, как трудно быть последовательным и проводить четкую границу производства.

---

### 16. `p0540` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> It is, then, difficult to think about the financial sector as anything but a *rentier*: a value extractor. This, indeed, was the economic verdict on finance before the 1970s, incorporated into national accounts, until a decision was taken to ascribe ‘value added’ to banks and their financial-market activities. That decision redesignated, as results of productive activity, financial profits that economists previously had little problem ascribing to banks’ monopoly power, associated with economies of scale and governments’ recognition that the biggest were ‘too big to fail’. The redrawing of the production boundary to include finance was in part a response to banks’ lobbying, which was itself a feature of their market power and influence. By showing finance as a large and growing source of national output, it overthrew the logic of previous financial regulation.

**В озвучку попало:**

> [thoughtful] Трудно рассматривать финансовый сектор иначе, чем как рантье — то есть как структуру, извлекающую ценность. Именно такой была экономическая оценка финансов до 1970-х годов, пока не было принято решение приписать «добавленную стоимость» банкам и их операциям на финансовых рынках. Это решение переквалифицировало в результаты производительной деятельности те финансовые прибыли, которые экономисты раньше без труда относили на счет монопольной власти банков. Эта власть была связана с эффектом масштаба и тем, что правительства признали крупнейшие банки «слишком большими, чтобы обанкротиться». Пересмотр границ производства с включением туда финансов был отчасти ответом на лоббизм банков, который сам по себе являлся следствием их рыночной силы и влияния. Представив финансы как крупный и растущий источник национального продукта, сторонники этой идеи опрокинули логику прежнего финансового регулирования.

---

### 17. `p0546` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Such measures made it hard for financial institutions to shift their business to low-tax or low-regulation jurisdictions. The rules reflected policymakers’ consensus that financial institutions acted at best like a lubricant for the ‘real’ motors of the economy – agriculture, manufacturing and business services – and were not significantly productive in themselves. It was feared that a deregulated financial sector could become excessively speculative, causing disruption domestically and to the external value of currencies. But in the 1960s, as the idea of ‘light-touch’ regulation became increasingly attractive, such measures were increasingly viewed on both sides of the Atlantic as an obstacle to circumvent.

**В озвучку попало:**

> Такие меры мешали финансовым институтам переводить бизнес в юрисдикции с низкими налогами или слабым регулированием. Политики того времени сходились во мнении, что финансовые институты — это лишь своего рода смазка для реальных двигателей экономики: сельского хозяйства, промышленности и сферы услуг. Сами по себе они не создавали значимой ценности. Существовало опасение, что дерегулированный финансовый сектор станет чрезмерно спекулятивным и вызовет потрясения как внутри страны, так и на валютных рынках. Однако в шестидесятых годах идея «мягкого» регулирования стала все более привлекательной. По обе стороны Атлантики такие меры стали восприниматься как досадное препятствие, которое нужно обойти.

---

### 18. `p0555` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> In the late 1990s, supercharged by the IT revolution, the volume of securities trading rocketed. Commercial banks could now use their huge balance sheets, based on customers’ deposits, to speculate. Their investment banking arms, along with independent investment banks such as Goldman Sachs, developed financial instruments of increasingly mind-blowing complexity.

**В озвучку попало:**

> В конце девяностых годов, получив мощный импульс от ИТ-революции, объемы торговли ценными бумагами резко возросли. Коммерческие банки теперь могли использовать свои огромные балансы, сформированные за счет депозитов клиентов, для спекуляций. Их инвестиционные подразделения, наряду с независимыми инвестиционными банками, такими как Goldman Sachs, разработали финансовые инструменты невероятной сложности.

---

### 19. `p0580` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> There is danger in a complex system with many players. Greater stability might be achieved when a few large companies serve the real economy, subject to heavy regulation in order to make sure that they concentrate on value creation and not value extraction. By contrast, deregulation designed to reinvigorate a part of the financial sector may well promote risk-taking behaviour – the opposite of what is intended.

**В озвучку попало:**

> Сложные системы с большим числом игроков опасны. Большая стабильность может быть достигнута, когда несколько крупных компаний обслуживают реальную экономику под строгим контролем, гарантирующим их ориентацию на создание стоимости, а не на ее извлечение. Напротив, дерегулирование, призванное оживить финансовый сектор, зачастую лишь поощряет рискованное поведение, что прямо противоположно поставленным целям.

---

### 20. `p0635` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> Indeed, the crash of 2008 vindicated the warnings of Keynes, Minsky and others about the dangers of excessive financialization. Yet while the crash and the ensuing crisis weakened banks, it still left them in a dominant position in the economy, sparing the embarrassment of those who had extolled the value of financial services in the years before they imploded into bankruptcy and fraud.

**В озвучку попало:**

> Крах 2008 года подтвердил правоту Кейнса, Мински и других экспертов, предупреждавших об опасностях чрезмерной финансовизации. Хотя кризис ослабил банки, они сохранили доминирующее положение в экономике. Это избавило от неловкости тех, кто превозносил ценность финансовых услуг прямо перед тем, как они рухнули в пучину банкротств и мошенничества.

---

### 21. `p0773` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Jensen, now a professor at the University of Rochester, wrote a paper with the Dean of Rochester’s business school, William Meckling (who, like Jensen, was a student of Friedman at Chicago), on how to implement Friedman’s idea. It was called ‘Theory of the firm: Managerial behavior, agency costs, and ownership structure’. The key argument was that managers (the agents) were not being disciplined by competitive financial markets or product markets, since they could misallocate resources or run up unnecessary expenses without incurring losses or endangering their jobs, and so it was hard for investors (the principals) to keep them accountable. The only way to do so was through strengthening the ‘market’, which was neutral and objective enough to make sure the company thrived. The result was a body of theory that argued that the only way for companies to be well run was if they maximized their ‘shareholder value’. In this way, investors would indirectly keep company managers accountable.

**В озвучку попало:**

> Дженсен, ставший к тому времени профессором Рочестерского университета, написал статью совместно с деканом бизнес-школы того же университета Уильямом Меклингом — который, как и Дженсен, был учеником Фридмана в Чикаго. Работа была посвящена тому, как реализовать идеи Фридмана на практике. Она называлась «Теория фирмы: управленческое поведение, агентские издержки и структура собственности». Ключевой аргумент заключался в том, что менеджеры — агенты — не контролируются конкурентными финансовыми или товарными рынками. Они могли неэффективно распределять ресурсы или нести лишние расходы, не опасаясь убытков или потери работы, поэтому инвесторам — принципалам — было трудно привлечь их к ответственности. Единственный путь решения проблемы — укрепление «рынка», который был достаточно нейтральным и объективным, чтобы обеспечить процветание компании. В результате появилась теория, утверждавшая: единственный способ хорошо управлять компанией — это максимизировать «акционерную стоимость». Так инвесторы могли косвенно контролировать менеджеров.

---

### 22. `p0797` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Diversification was more appropriately left to the shareholders, with the bosses of each company ‘sticking to the knitting’ and not venturing beyond their narrow zone of expertise. Conglomerates’ inefficiency could be practically demonstrated if their constituent parts, broken up and floated separately, could command a higher total share price than the coagulated whole. Whether right or wrong, the assumption about managers’ professionalism did not address the problem that they might not always act in the best interests of shareholders. When the US and other Western economies slowed down in the 1970s, Friedman and other agency theorists argued that because principals and agents are motivated by self-interest, the inevitable conflicts could best be resolved by giving the ultimate owner, the shareholder, the overriding interest. Conventional wisdom was turned on its head and conglomerates were broken up, a step also justified by seeing corporations as nothing more than a collection of cash flows.

**В озвучку попало:**

> Диверсификацию лучше оставить самим акционерам, а руководителям каждой компании стоит «заниматься своим делом», не выходя за рамки узкой зоны компетенций. Неэффективность конгломератов легко доказывалась на практике: если разбить их на части и вывести каждую на биржу отдельно, общая рыночная стоимость этих частей могла оказаться выше, чем стоимость целого конгломерата. Верно это было или нет, но предположение о профессионализме менеджеров не решало проблему того, что они не всегда действуют в интересах акционеров. Когда в семидесятые годы экономика США и других западных стран замедлилась, Милтон Фридман и другие теоретики агентских отношений заявили: поскольку и принципалы, и агенты движимы личным интересом, конфликты лучше всего разрешать, отдав приоритет конечному владельцу — акционеру. Общепринятые взгляды перевернулись с ног на голову, и конгломераты начали дробить. Этот шаг также оправдывали тем, что корпорация — это не что иное, как набор денежных потоков.

---

### 23. `p0833` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Sales growth and improved profit margins, the two components of earnings growth, are positively influenced by investment, whether in plant and equipment (capital expenditure) or R&D. Investment is the story corporate managers like to tell. But there is another, quicker and more predictable way to improve margins, about which managers are less forthcoming: cutting costs. It’s a process that companies have embraced – to the detriment of investment.

**В озвучку попало:**

> [thoughtful] Рост продаж и увеличение прибыли — два двигателя роста — напрямую зависят от инвестиций в оборудование или в исследования и разработки. Именно об инвестициях менеджеры любят рассказывать чаще всего. Но есть и другой, более быстрый и предсказуемый способ повысить маржу, о котором они говорят неохотно: сокращение расходов. Компании активно взяли этот метод на вооружение, зачастую в ущерб реальным инвестициям.

---

### 24. `p0864` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Inequality reveals what we think of millions of our fellow humans. The economic issue with value extraction is not normative, however. As we have seen, in a capitalist economy some rent is necessary: there is an unavoidable price tag to maintaining the circulation of capital in the economic system. But the scale of the financial sector and of financialization generally has increased value extraction to the point where two critical questions must be answered: where is value created, extracted and even destroyed? And how can we steer the economy away from excessive financialization towards true value creation? Proposals such as taxing away very high incomes and accumulations of wealth may treat some of the symptoms of excessive finance. They do not, however, treat the causes, which lie deep in a system of value extraction which has grown up over the last forty years or so.

**В озвучку попало:**

> Неравенство показывает, как мы относимся к миллионам других людей. Однако экономическая проблема извлечения стоимости не является нормативной. Как мы уже видели, в капиталистической экономике некоторая доля ренты необходима: поддержание обращения капитала в системе всегда имеет свою цену. Но масштабы финансового сектора и финансовизации в целом увеличили извлечение стоимости до такой степени, что необходимо ответить на два критических вопроса. Где именно стоимость создается, где извлекается, а где даже уничтожается? И как нам направить экономику от чрезмерной финансовизации к реальному созданию ценности? Предложения вроде налогообложения сверхвысоких доходов и накоплений могут помочь в борьбе с симптомами, но они не устраняют причины. А они кроются глубоко в системе извлечения стоимости, которая формировалась последние сорок лет.

---

### 25. `p0930` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> IPOs are, first, a way for early investors to get their money out. The very possibility of an IPO encourages investment – although it has to be said that investors with one eye on the exit door and the other on the clock might not be ideal for nurturing a company to its potential. Second, IPOs can raise new capital for business expansion, which can be valuable in some sectors but less significant in others (like software), where the most important capital is human. Third, founders can realize the value of their ingenuity and sweat equity that has remained latent in the company.

**В озвучку попало:**

> Во-первых, IPO — это способ для ранних инвесторов вернуть свои вложения. Сама возможность выхода на биржу стимулирует инвестиции. Хотя стоит признать, что инвесторы, которые одной рукой держатся за выходную дверь, а другой следят за часами, вряд ли идеально подходят для того, чтобы помочь компании полностью раскрыть свой потенциал. Во-вторых, IPO позволяет привлечь новый капитал для расширения бизнеса. В некоторых секторах это ценно, но в других, например в разработке программного обеспечения, где важнейшим капиталом являются люди, это менее значимо. В-третьих, основатели могут реализовать стоимость своей изобретательности и вложенного труда, которая до этого момента оставалась скрытой внутри компании.

---

### 26. `p0936` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> The classical economists would have had little time for the way in which the VC industry has extracted value by shifting money around rather than creating value: for them the point was to nurture the production of value rather than its simple circulation.

**В озвучку попало:**

> [thoughtful] Классические экономисты вряд ли одобрили бы то, как индустрия венчурного капитала извлекает прибыль. Они предпочитали просто перекладывать деньги с места на место, вместо того чтобы создавать реальную ценность. Для экономистов прошлого суть заключалась в поддержке производства, а не в простом обращении капитала.

---

### 27. `p0941` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Patents are protections granted to inventions that are novel, inventive (non-obvious) and suitable for industrial application. In theory they protect the innovator from having his or her idea copied. In practice, however, most innovations are not patented, which in itself shows that patents are not really necessary, as there are other ways to protect innovations, including lead-times and trade secrecy. One study found that between 1977 and 2004, only 10 per cent of ‘important’ innovations were patented.²² Patents tend to be granted for two reasons, which must be held in constant tension for the system to function effectively. The first is to reward and incentivize inventors for developing new ideas by granting them a time-limited monopoly entitlement over their inventions,23 or what is known as the *appropriability function* of patents. In exchange for this monopoly entitlement, the inventor must reveal detailed information about his or her invention. Which brings us to the second reason: once the patent has expired, the invention can diffuse rapidly through the economy in a process known as the *disclosure function* of patents. If the system works well, the appropriability function is properly balanced against the disclosure function and the public gains from the rapid diffusion of this 24 new knowledge through the economy.

**В озвучку попало:**

> Патенты — это защита, предоставляемая изобретениям, которые являются новыми, неочевидными и пригодными для промышленного применения. Теоретически они защищают новатора от копирования его идей. На практике же большинство инноваций не патентуется. Это само по себе доказывает, что патенты не всегда необходимы, ведь существуют другие способы защиты, например, преимущество во времени выхода на рынок или коммерческая тайна. Одно исследование показало, что в период с 1977 по 2004 год было запатентовано лишь 10 процентов «важных» инноваций. Патенты обычно выдаются по двум причинам, которые должны находиться в постоянном равновесии для эффективной работы системы. Первая — это вознаграждение и стимулирование изобретателей путем предоставления им временной монополии на использование своих идей. Это называют функцией присвоения. В обмен на такую монополию изобретатель обязан раскрыть подробную информацию о своем продукте. Это подводит нас ко второй причине: после истечения срока действия патента изобретение может быстро распространиться в экономике. Это называется функцией раскрытия информации. Если система работает исправно, функция присвоения сбалансирована с функцией раскрытия, и общество выигрывает от быстрого распространения новых знаний.

---

### 28. `p1024` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> IBM and Microsoft – virtually monopolize it. But the problem is not just a question of competition – the size and number of firms in the sector. It could be argued that a few large companies can achieve the economies of scale required to drive down costs and make data cheaper – not a bad thing given falling real incomes.

**В озвучку попало:**

> IBM и Microsoft — практически монополизировала эту сферу. Но проблема не только в конкуренции, то есть в размере и количестве фирм в секторе. Можно возразить, что несколько крупных компаний способны достичь эффекта масштаба, необходимого для снижения затрат и удешевления данных, что было бы неплохо на фоне падения реальных доходов.

---

### 29. `p1032` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> Policymakers should have a clear understanding of who the different actors in the process are in order to prevent free-riding on publicly funded innovation and a ‘winner-takes-all’ outcome. Rather than creating myths about actors in the innovation economy such as venture capitalists, it is important to recognize the stages at which each of these actors is important. Tax policy could be changed to encourage truly dynamic links between the different participants in innovation, for example by bringing the rewards and tax breaks that venture capitalists enjoy more into line with the risks they actually take compared with other stakeholders.

**В озвучку попало:**

> [serious] Политикам следует четко понимать, кто именно участвует в инновационном процессе, чтобы предотвратить паразитирование на государственных инвестициях и ситуации, когда «победитель забирает всё». Вместо того чтобы создавать мифы о таких участниках инновационной экономики, как венчурные капиталисты, важно осознавать, на каких именно этапах каждый из них играет свою роль. Налоговую политику можно изменить так, чтобы стимулировать по-настоящему динамичные связи между всеми участниками инноваций. Например, стоит привести налоговые льготы и вознаграждения, которыми пользуются венчурные капиталисты, в соответствие с реальными рисками, которые они несут по сравнению с другими сторонами.

---

### 30. `p1114` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Let’s remind ourselves that Keynes was concerned in his *General* *Theory* to explain how an economy might find itself in a state of ‘involuntary unemployment’ due to insufficient demand – that is, workers who wanted work would not be able to find it. This, he argued, would produce a low level of GDP, compared to a situation in which the economy would be running at full capacity (and full employment).

**В озвучку попало:**

> Напомним, что в своей «Общей теории» Кейнс стремился объяснить, как экономика может оказаться в состоянии «вынужденной безработицы» из-за недостаточного спроса. Иными словами, работники, которые хотели трудиться, не могли найти работу. Он доказывал, что это приводит к низкому уровню валового внутреннего продукта по сравнению с ситуацией, когда экономика работает на полную мощность и при полной занятости.

---

### 31. `p1115` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> Neoclassical economic theory is ill suited to explain this situation because it assumes that people choose what they prefer, including how much labour they ‘supply’ to the market at a given price (the wage), and that the market makes sure to sort things out so that everyone gets the maximum utility out of it. In such a view, unemployment becomes voluntary.

**В озвучку попало:**

> Неоклассическая экономическая теория плохо подходит для объяснения этой ситуации. Она исходит из того, что люди выбирают то, что предпочитают, включая объем труда, который они «предлагают» рынку по заданной цене — заработной плате. Согласно этой теории, рынок сам все урегулирует так, чтобы каждый получил максимум пользы. В такой системе координат любая безработица становится добровольной.

---

### 32. `p1157` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Taken to its extreme, Public Choice theory, which derives from marginalism, calls for government to intervene as little as possible in the economy in order to minimize the risk of government failure. The public sector should be insulated from the private sector, for example to avoid agency capture – when a regulatory body grows too close to the industry it is meant to regulate.

**В озвучку попало:**

> В своей крайней форме теория общественного выбора, выросшая из маржинализма, призывает государство к минимальному вмешательству в экономику, чтобы снизить риски провалов. Государственный сектор должен быть изолирован от частного, чтобы избежать так называемого захвата регулятора — ситуации, когда надзорный орган становится слишком зависимым от отрасли, которую должен контролировать.

---

### 33. `p1168` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> It will provide you with all medical, dental, and nursing care. Everyone – rich or poor, man, woman or child – can use it or any part of it.’ The National Health Service (NHS) was created that year, following the initiative of the Minister of Health, Aneurin Bevan. The following three 45 core principles were behind its establishment: that it meets the needs of everyone that it be free at the point of delivery that it be based on clinical need, not ability to pay

**В озвучку попало:**

> «Она обеспечит вас всем необходимым медицинским, стоматологическим и сестринским уходом. Каждый — богатый или бедный, мужчина, женщина или ребенок — может воспользоваться ею целиком или любой её частью». Национальная служба здравоохранения была создана в том же году по инициативе министра здравоохранения Эньюрина Бивена. В её основу легли три ключевых принципа: доступность для всех, бесплатное обслуживание в момент обращения и ориентация на клиническую необходимость, а не на платежеспособность пациента.

---

### 34. `p1169` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Over its almost seventy years of existence, the NHS has become one of the most efficient and equitable healthcare systems in the world, as recognized by the World Health Organization⁴⁶ and also more recently by the Commonwealth Foundation.⁴⁷ In the UK it is considered a national treasure, sharing its place in the pantheon with the Queen and the BBC.

**В озвучку попало:**

> За почти семьдесят лет своего существования Национальная служба здравоохранения стала одной из самых эффективных и справедливых систем здравоохранения в мире. Это признали Всемирная организация здравоохранения, а позднее и Фонд Содружества. В Великобритании её считают национальным достоянием, ставя в один ряд с королевой и Би-би-си.

---

### 35. `p1173` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> With the National Health Service and Community Care Act of 1990, management and patient care were forced to behave as part of an ‘internal market’, with health authorities and general practitioners becoming autonomous purchasers of services under a limited budget. Hospitals were transformed into self-governing NHS trusts and their resources became dependent on contracts stipulated with purchasers. Contracting out to the lowest bidder was also introduced as a first element of outsourcing, with the NHS progressively moving away from its role of provider towards becoming a mere customer. Since 1992, the outsourcing process created by the Private Financing Initiative (PFI) has involved also the building of NHS hospitals. Through PFI, private companies were allowed to build hospitals which were then rented back to the NHS for a substantially high price. PFI was widely used throughout the ‘New Labour’ governments to save on infrastructure investment, with the renting price of hospitals subsequently burdening the NHS budget. Finally, the 2012 Health and Social Care Act de facto abolished the second principle of the original NHS, by introducing user charges and an insurance-based system that resembles the US healthcare model, passing costs and risks to patients, now customers in a market for healthcare provision. This final reform has also further increased the scope for outsourcing in many different areas, such as cleaning, facilities management, GP ‘out of hours’ services, 50 clinical services, IT and so on.

**В озвучку попало:**

> [serious] Закон о Национальной службе здравоохранения и социальной помощи 1990 года заставил систему управления и ухода за пациентами действовать в рамках так называемого внутреннего рынка. Органы здравоохранения и терапевты стали автономными покупателями услуг с ограниченным бюджетом. Больницы превратились в самоуправляемые трасты, а их ресурсы стали зависеть от контрактов с покупателями. В качестве первого шага к аутсорсингу была введена практика передачи заказов по тендерам — тому, кто предложит самую низкую цену. В результате Национальная служба здравоохранения постепенно перестала быть поставщиком услуг, превратившись в обычного клиента. С 1992 года процесс аутсорсинга, запущенный через «Инициативу частного финансирования», затронул и строительство больниц. Частным компаниям разрешили строить здания, которые затем сдавались Национальной службе здравоохранения в аренду по очень высокой цене. Правительства «новых лейбористов» активно использовали этот механизм, чтобы экономить на капитальных вложениях, однако арендные платежи впоследствии стали тяжелым бременем для бюджета здравоохранения. Наконец, закон 2012 года о здравоохранении и социальной помощи фактически отменил второй основополагающий принцип системы, введя плату за услуги и страховую модель, похожую на американскую. Теперь пациенты стали клиентами на рынке медицинских услуг, а риски и расходы легли на них. Эта реформа еще больше расширила аутсорсинг в таких сферах, как клининг, управление объектами, работа терапевтов в нерабочее время, клинические услуги и IT.

---

### 36. `p1233` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> Today, these ways of thinking could significantly benefit many crucial institutions which are neither fully private nor fully public. Universities could proudly promote the pursuit of knowledge, without having to worry about generating immediately profitable patents and spin-off companies.

**В озвучку попало:**

> Сегодня такой образ мышления мог бы принести огромную пользу многим ключевым институтам, которые не являются ни чисто частными, ни чисто государственными. Например, университеты могли бы с гордостью заниматься поиском знаний, не беспокоясь о том, чтобы в первую очередь создавать коммерчески выгодные патенты или спин-офф компании.

---

### 37. `p1249` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> By losing our ability to recognize the difference between value creation and value extraction, we have made it easier for some to call themselves value creators and in the process extract value. Understanding how the stories about value creation are around us everywhere – even though the category itself is not – is a key concern of the book, and essential for the future viability of capitalism.

**В озвучку попало:**

> Потеряв способность различать создание ценности и ее извлечение, мы облегчили некоторым людям задачу: называть себя создателями ценности, попутно извлекая ее для личной выгоды. Понимание того, как истории о создании ценности окружают нас повсюду — даже если сама эта категория больше не обсуждается всерьез, — является одной из главных тем этой книги и критически важно для будущего капитализма.

---

### 38. `p1256` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> Second, the conventional discourse devalues and frightens actual and would-be value creators outside the private business sector. It’s not easy to feel good about yourself when you are constantly being told you’re rubbish and/or part of the problem. That’s often the situation for people working in the public sector, whether these be nurses, civil servants or teachers. The static metrics used to measure the contribution of the public sector, and the influence of Public Choice theory on making governments more ‘efficient’, has convinced many civil-sector workers they are second-best. It’s enough to depress any bureaucrat and induce him or her to get up, leave and join the private sector, where there is often more money to be made.

**В озвучку попало:**

> [serious] Во-вторых, общепринятый дискурс обесценивает работу тех, кто действительно создает ценности вне частного бизнеса, и заставляет их чувствовать себя неполноценными. Трудно сохранять мотивацию, когда тебе постоянно твердят, что ты бесполезен или сам являешься частью проблемы. Именно в такой ситуации часто оказываются люди в государственном секторе: медсестры, госслужащие или учителя. Статичные показатели, используемые для оценки вклада госсектора, и влияние теории общественного выбора, направленной на «повышение эффективности» правительств, убедили многих бюджетников в их второсортности. Это угнетает и заставляет людей уходить в частный сектор, где платят больше.

---

### 39. `p1275` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> That is a very modest demand. The discussion of the kind of infrastructure, and its relationship to greater social goals, has been puerile. Just roads and bridges? Public investment that is driven by ambition and a vision cannot be limited to a laundry list of traditional physical infrastructure projects.

**В озвучку попало:**

> Но это очень скромное требование. Разговоры о том, какая именно инфраструктура нам нужна и как она соотносится с более широкими социальными целями, зачастую выглядят по-детски. Неужели речь только о дорогах и мостах? Государственные инвестиции, движимые амбициями и видением будущего, не могут ограничиваться лишь списком традиционных строительных проектов.

---

### 40. `p1282` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> I began the book stating that the goal was not to argue that one value theory is better than another. My aim is for the book to stir a new debate, putting value back at the centre of economic reasoning. This is not about drawing firm and static fences around the production boundary, arguing that some actors are parasitic or takers, while others are glorious producers and makers. Rather we should have a more dynamic understanding of what making and taking are in the context of the societal objectives we have.

**В озвучку попало:**

> В начале книги я сказала, что моя цель — не доказать превосходство одной теории ценности над другой. Я хочу, чтобы эта книга подтолкнула к новой дискуссии и вернула ценность в центр экономического анализа. Речь не идет о том, чтобы провести жесткие и неизменные границы вокруг производства, объявляя одних участников «паразитами» или «потребителями», а других — «великими созидателями». Нам нужно более динамичное понимание того, что значит создавать и что значит изымать ценность в контексте наших общественных целей.

---

### 41. `p2284` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> In 2013 I wrote a book called *The Entrepreneurial State*. In it I debunked how myths about lone entrepreneurs and start-ups have captured the theory and practice of innovation, ignoring one of the key actors that has been an investor of first resort: the state. Innovation is a collective process, with different types of public institutions playing a pivotal role. That role is ignored, so our theory of value creation is flawed. And this is a major reason for wealth often being distributed in dysfunctional ways.

**В озвучку попало:**

> [thoughtful] В 2013 году я написала книгу «Предпринимательское государство». В ней я развенчала мифы об одиноких героях-предпринимателях и стартапах, которые захватили теорию и практику инноваций. Эти мифы игнорируют одного из ключевых игроков — государство, которое зачастую выступает инвестором первой очереди. Инновации — это коллективный процесс, где важную роль играют самые разные государственные институты. Поскольку эта роль не учитывается, наша теория создания стоимости оказывается ошибочной. И это одна из главных причин, почему богатство так часто распределяется неэффективно.

---

### 42. `p2285` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The book you have in your hand is a direct consequence of this early reasoning. We cannot understand economic growth if we do not go back to the beginning: what is wealth and where does value come from? Are we sure that much of what is passing for value creation is not just value extraction in disguise?

**В озвучку попало:**

> Книга, которую вы держите в руках, стала прямым следствием моих ранних размышлений. Мы не сможем понять экономический рост, если не вернемся к истокам: что такое богатство и откуда берется стоимость? Можем ли мы быть уверены, что многое из того, что выдается за создание стоимости, на самом деле не является ее скрытым изъятием?

---

### 43. `p2286` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> To write the book I needed to delve into the last 300 years of thinking about value. No easy task, and made no easier by also having to grapple with the application of these ideas to contemporary capitalism as a whole – for example, financialization – and to particular sectors, from finance to big pharma and IT.

**В озвучку попало:**

> Чтобы написать эту книгу, мне пришлось погрузиться в историю экономической мысли за последние триста лет. Задача была непростой. Ее усложняло то, что мне нужно было связать эти идеи с современным капитализмом — например, с финансовизацией экономики — и применить их к конкретным отраслям: от финансов до фармацевтики и IT-сектора.

---

### 44. `p2288` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> I would like to thank Gregor Semeniuk, who like me received a PhD from the Graduate Faculty of the New School in New York – a rare place that still teaches alternative theories of economic thought. He generously shared his extraordinary knowledge about value theory, from the physiocrats to the classicals. Gregor was a tremendous support in helping me document, in a ‘user-friendly’ way, the debates between the Physiocrats, Smith and Ricardo – and the strange fact that even Marx had no real theory of the way in which the state can contribute to value.

**В озвучку попало:**

> Я хочу поблагодарить Грегора Семенюка. Как и я, он получил докторскую степень в Новой школе социальных исследований в Нью-Йорке — редком месте, где до сих пор преподают альтернативные экономические теории. Он щедро поделился своими выдающимися знаниями о теории стоимости, начиная от физиократов и заканчивая классиками. Грегор оказал мне огромную поддержку в том, чтобы изложить в доступной форме споры между физиократами, Смитом и Рикардо. Он также помог мне разобраться со странным фактом: даже у Маркса не было реальной теории того, как государство может способствовать созданию стоимости.

---

### 45. `p2290` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> He cheerfully cycled to our meetings on even the hottest days of the year and was not just a friendly editor but also a great companion, bringing calm to what often felt like hectic months trying to finish a book while I was raising a large family and starting up a new department at UCL. Our weekly meetings in the Lord Stanley pub in Camden to pore over the material often trailed off into a stream of consciousness dwelling on the ills of modern capitalism – and were nothing but pure joy. With the occasional pint (or two) to keep us going.

**В озвучку попало:**

> Он бодро приезжал на наши встречи на велосипеде даже в самые жаркие дни. Майкл был не просто дружелюбным редактором, но и отличным собеседником. Он привносил спокойствие в те месяцы, которые часто казались хаотичными, ведь я пыталась закончить книгу, воспитывая большую семью и создавая новый факультет в Университетском колледже Лондона. Наши еженедельные встречи в пабе «Лорд Стэнли» в Камдене, где мы корпели над материалом, часто перетекали в поток сознания о пороках современного капитализма. Это было чистое удовольствие, подкрепленное кружкой пива — или двумя — для бодрости.

---

### 46. `p2291` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> I would like to thank the following people for looking at particular chapters in the book and double checking it for errors in its final stages, selflessly offering their wisdom and care: (in alphabetical order) Matteo Deleidi, Lukas Fuchs Tommaso Gabellini, Simone Gasperin, Edward Hadas, Andrea Laplane, Alain Rizk, and Josh Ryan Collins.

**В озвучку попало:**

> Я хочу поблагодарить тех, кто просмотрел отдельные главы книги и проверил их на наличие ошибок на финальных этапах, бескорыстно предложив свою мудрость и заботу. В алфавитном порядке это: Маттео Делейди, Лукас Фукс, Томмазо Габеллини, Симоне Гасперин, Эдвард Хадас, Андреа Лаплан, Ален Ризк и Джош Райан Коллинз.

---

### 47. `p2292` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> My editor Tom Penn at Penguin was a great sounding board during our endless coffee-filled meetings at the British Library – having the rare qualities of a meticulous proofreader while also retaining a deep engagement with the content, both economic and philosophical.

**В озвучку попало:**

> Мой редактор Том Пенн из издательства Penguin стал отличным советчиком во время наших бесконечных встреч за кофе в Британской библиотеке. Он обладает редким сочетанием качеств: он дотошный корректор, который при этом глубоко погружен в содержание — как экономическое, так и философское.

---

### 48. `p2293` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> I also want to thank the excellent administrative assistance I have had over the last four years, first at SPRU in the University of Sussex and now in a new institute that I have founded at UCL, the Institute for Innovation and Public Purpose IIPP). Gemma Smith in particular has helped me always try to get messages across – whether on the 10 o’clock news or in a policy brief – that could be understood by the general public. With the new team at IIPP, I hope the book’s message about the need for revived debate about key questions around value can be linked with the IIPP’s ambition to redefine ways of conceptualizing public value in particular: how to create it, nurture it and evaluate it.

**В озвучку попало:**

> Я также хочу поблагодарить всех, кто помогал мне с административными вопросами в последние четыре года — сначала в отделе исследований научной политики в Университете Сассекса, а теперь в новом институте, который я основала в Университетском колледже Лондона: Институте инноваций и общественного предназначения. Джемма Смит, в частности, всегда помогала мне доносить мысли так, чтобы они были понятны широкой публике — будь то в вечерних новостях или в политических обзорах. Надеюсь, что вместе с новой командой института мы сможем связать идеи этой книги о необходимости дискуссий вокруг стоимости с нашей главной целью: переосмыслить способы концептуализации общественной ценности — как ее создавать, развивать и оценивать.

---

### 49. `p2294` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> Lastly, I want to thank Carlo, Leon, Micol, Luce and Sofia for putting up with the many long nights and weekends that the book entailed – letting me climb up the stairs and plop myself down to the most happy and conversive dinner table a wife and mother can ask for – putting life back at the centre, where it should be.

**В озвучку попало:**

> Наконец, я хочу поблагодарить Карло, Леона, Миколь, Люс и Софию за то, что они терпели долгие ночи и выходные, которые отнимала у меня эта книга. Спасибо, что позволяли мне спуститься по лестнице и сесть за самый счастливый и оживленный обеденный стол, о котором только может мечтать жена и мать. Вы вернули жизнь в центр всего, где ей и место.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p1028` — длина озвучки / длина оригинала: 0.73; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Current stories about value, wealth creation and risk-taking that privilege the contribution of individual inventors and capitalists lead to ways of thinking whereby it is acceptable to divide up the fruits of innovation between them – the concept of ‘just deserts’. The term comes from the English philosopher John Locke (1632–1704). His concept of individual entitlement – ‘just deserts’ – to the product of work was based on a production system where individual labour was more important, and was easier to identify, than it is today when collective contributions have been central to technology-driven growth. This point was made by Herbert Simon (1916–2001), who made his name in the study of organizational decision-making, and who won the Nobel Prize in Economics in 1978. ‘If we are generous with ourselves,’ Simon considered, ‘I suppose that we might claim that we “earned” as much as one-fifth of our income. The rest of the patrimony [is] associated with being a member of an enormously productive social system, which has accumulated a vast store of physical capital, and an even larger store of intellectual capital – including knowledge, skills, and organizational know-how held by all of us.’78 Ignoring this collectively produced social system, certain individuals feel justified in earning a much higher proportion of a nation’s income than their own contribution warrants. But, more specifically, it has affected policies on taxes, patents and prices, thus fuelling the dynamics of inequality.

**В озвучку попало:**

> Современные представления о богатстве и риске превозносят вклад отдельных изобретателей и капиталистов. Это порождает логику «заслуженного вознаграждения», когда плоды инноваций делятся исключительно между ними. Сам термин восходит к английскому философу Джону Локку. Его концепция индивидуального права на продукт труда возникла в эпоху, когда личный вклад был заметнее, чем сегодня, в мире, где технологический рост держится на коллективных усилиях. Герберт Саймон, лауреат Нобелевской премии по экономике, однажды заметил: «Если мы будем щедры к себе, то можем заявить, что заработали одну пятую часть своего дохода. Остальное — это наследство, полученное благодаря участию в невероятно продуктивной социальной системе». Эта система накопила огромные запасы физического и интеллектуального капитала — знаний, навыков и организационного опыта, которые принадлежат всем нам. Игнорируя этот факт, некоторые люди считают оправданным присвоение доли национального дохода, которая значительно превышает их реальный вклад. Это влияет на налоговую, патентную и ценовую политику, подпитывая неравенство.

---

### 2. `p1258` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> Third, this market story confuses policymakers. By and large, policymakers of all stripes want to help their communities and their country, and they think the way to do so is to put more trust in market mechanisms, with policy just a matter of tinkering at the edges. The crucial thing is to be seen as progressive while also ‘business-friendly’. But with a very limited understanding of where value comes from, politicians and all too many government employees are like putty in the hands of those who claim to be value creators. Regulators end up being lobbied by businesses and induced to endorse policies which make incumbents even richer – increasing profits but with little effect on investment. Examples include ways in which governments across much of the Western world have been persuaded to reduce capital gains tax, even though there is no reason to do so if the aim is to promote long-term investments rather than short-term ones. And lobbyists with their innovation stories have pushed through the Patent Box policy, which reduces tax on the profits generated from 20-year patent-based monopolies – even though the policy’s main impact has been merely to reduce government revenue, rather than increasing the types of investments that led to the patents in the first place.⁵ All of which serves only to subtract value from the economy and make for a less attractive future for almost everyone. Not having a clear view of the collective value creation process, the public sector is thus ‘captured’ – entranced by stories about wealth creation which have led to regressive tax policies that increase inequality.

**В озвучку попало:**

> [thoughtful] В-третьих, эта рыночная риторика сбивает с толку политиков. В большинстве своем они хотят помочь своим сообществам и стране, полагая, что для этого нужно больше доверять рыночным механизмам, ограничиваясь лишь косметическими правками. Важно выглядеть прогрессивным и при этом «дружелюбным к бизнесу». Но из-за ограниченного понимания того, откуда берется ценность, политики и многие чиновники становятся податливыми в руках тех, кто называет себя «создателями ценностей». Регуляторы поддаются лоббизму и поддерживают политику, которая делает владельцев бизнеса еще богаче, увеличивая прибыль, но почти не влияя на реальные инвестиции. Примером может служить снижение налога на прирост капитала, хотя это не способствует долгосрочным вложениям. Или политика «патентных боксов», которая снижает налоги на прибыль от двадцатилетних монополий, хотя ее главный эффект — лишь сокращение государственных доходов. Это не создает ценности для экономики, а лишь ухудшает будущее для большинства. Не имея четкого представления о коллективном процессе создания ценности, госсектор оказывается в ловушке историй об обогащении, которые ведут к регрессивным налоговым реформам и росту неравенства.

---

### 3. `p0808` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> The ‘short-termism’ which Keynes anticipated is encapsulated in index fund pioneer John Bogle’s concept that institutional investors rent the shares of the companies they invest in rather than take ownership for the long term. Consider the increased turnover of domestic shares: according to the World Federation of Exchanges, which represents the world’s publicly regulated stock exchanges, in the US turnover of domestic shares was around 20 per cent a year in the 1970s, rising steeply to consistently over 100 per cent a year in the 2000s. Turnover measures how often a share changes hands and is calculated by dividing the number of shares traded in a given period by the number of shares outstanding in the same period. Increasing turnover is a sign that institutional investors’ sights were trained on the short-term movement of stock prices rather the intrinsic, long-term value of the corporation. High turnover can be more profitable for institutional investors than passive, long-term holding of shares. It should also be said that the short-termist behaviour of institutional investors reflects mounting pressure over the last four decades from clients who, expecting quick results and with a dislike of surprises, quickly withdraw their funds when disappointed. The result has been a corporate fixation on quarterly performance, which encourages consistent earnings growth to generate acceptable share price performance.

**В озвучку попало:**

> «Краткосрочность», которую предвидел Кейнс, хорошо описывает концепция Джона Богла, пионера индексных фондов. Он считал, что институциональные инвесторы не владеют компаниями в долгосрочной перспективе, а лишь «арендуют» их акции. По данным Всемирной федерации бирж, оборачиваемость внутренних акций в США в семидесятых годах составляла около 20 процентов в год. К двухтысячным годам этот показатель стабильно превышал 100 процентов. Оборачиваемость показывает, как часто акции переходят из рук в руки. Рост этого показателя — верный признак того, что инвесторы сосредоточены на сиюминутных движениях котировок, а не на долгосрочной стоимости бизнеса. Для институциональных игроков высокая оборачиваемость часто выгоднее, чем пассивное долгосрочное владение. Стоит отметить, что такое поведение — это реакция на давление со стороны клиентов, которые ждут быстрых результатов и склонны немедленно забирать средства при первых признаках разочарования. В итоге компании фиксируются на квартальных отчетах, стремясь к постоянному росту прибыли ради поддержания курса акций.

---

### 4. `p0371` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> When students learn about microeconomics in the classroom (e.g. how prices are determined, including wages), they are not told that this is only one of many different approaches to thinking about value. It is, as far as they are concerned, the only one – and, as a result, there is no need to refer to the word ‘value’. The term essentially disappears from the discourse. It is simply Microeconomics 101.

**В озвучку попало:**

> [serious] Когда студенты изучают микроэкономику, например, то, как формируются цены и заработные платы, им не говорят, что это лишь один из многих подходов к пониманию ценности. Для них это единственный подход, и в результате слово «ценность» просто исчезает из дискурса. Это стандартный курс микроэкономики.

---

### 5. `p0465` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> In explaining why housework is accounted as unproductive, national accountants are forced constantly to fall back on their ‘comprehensive’ production boundary, and are at pains to invoke ‘common sense’. Their explanations include: ‘the relative isolation and independence of these activities from markets, the extreme difficulty of making economically meaningful estimates of their values, and the adverse effects it would have on the usefulness of the accounts for policy purposes and the analysis of 29 markets and market disequilibria’.

**В озвучку попало:**

> Объясняя, почему домашний труд считается непродуктивным, национальные счетоводы постоянно вынуждены возвращаться к своим «всеобъемлющим» границам производства и изо всех сил взывать к здравому смыслу. Их аргументы включают в себя относительную изоляцию этих видов деятельности от рынков, крайнюю сложность оценки их стоимости и опасения, что включение этих данных повредит анализу рынков и рыночных диспропорций.

---

### 6. `p0684` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Private equity (PE) firms invest in companies, usually to take ownership and manage them, later – typically after three to seven years – selling them at a profit. They make their profit, if successful, from the increase in the equity value of the company after the debt has been paid off. They then realize the equity value by selling the company (sometimes to another PE firm) or through an IPO (initial public offering – in other words, a stock market launch).

**В озвучку попало:**

> Фирмы частного капитала инвестируют в компании, обычно с целью получения контроля над управлением, чтобы через три-семь лет продать их с прибылью. В случае успеха они зарабатывают на росте стоимости капитала компании после погашения долгов. Затем они фиксируют прибыль, продавая компанию другой фирме или через первичное публичное размещение акций на бирже.

---

### 7. `p1259` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Fourth, and last, the confusion between profits and rents appears in the ways we measure growth itself: GDP. Indeed, it is here that the production boundary comes back to haunt us: if anything that fetches a price is value, then the way national accounting is done wont be able to distinguish value creation from value extraction and thus policies aimed that the former might simply lead to the latter. This is not only true for the environment where picking up the mess of pollution will definitely increase GDP (due to the cleaning services paid for) while a cleaner environment won’t necessarily (indeed if it leads to less ‘things’ produced it could decrease GDP), but also as we saw to the world of finance where the distinction between financial services that feed industry’s need for long-term credit versus those financial services that simply feed other parts of the financial sector are not distinguished.

**В озвучку попало:**

> [serious] В-четвертых, путаница между прибылью и рентой отражается на способах измерения роста, то есть на валовом внутреннем продукте. Именно здесь границы производства начинают играть против нас. Если ценностью считается все, что имеет цену, то национальная статистика не сможет отличить создание ценности от ее извлечения. Политика, направленная на развитие, может привести лишь к росту извлечения ренты. Это верно не только для экологии, где уборка мусора после загрязнения повышает ВВП, а чистая среда — не обязательно. Это касается и финансов, где не проводится различие между услугами, которые питают промышленность долгосрочными кредитами, и теми, что просто перекачивают деньги внутри финансового сектора.

---

### 8. `p0448` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Indeed, following this logic, government is also a producer of intermediate inputs for businesses. Surely education, roads, or the police, or courts of law can be seen as necessary inputs into the production of a variety of goods? But herein lies is a twist. If government spending were to increase, this would mean that government was producing more intermediate goods. Businesses would buy at least some of those goods (e.g. some public services cost money) with a fee; but because they were spending more on them (than if government was not producing anything, and therefore not buying supplies from businesses), their operating surplus and value added would inevitably fall. Government’s share of GDP would rise, but the absolute size of GDP would stay the same. This does, of course, run counter to Keynesian attempts to show how increases in government demand could lift GDP.

**В озвучку попало:**

> [curious] Если следовать этой логике, государство выступает производителем промежуточных ресурсов для бизнеса. Образование, дороги, полиция или суды — разве это не необходимые условия для производства самых разных товаров? Но здесь кроется подвох. Если бы государственные расходы выросли, это означало бы, что государство производит больше промежуточных товаров. Бизнес покупал бы часть этих услуг за плату, но из-за роста этих издержек его операционная прибыль и добавленная стоимость неизбежно снизились бы. Доля государства в ВВП выросла бы, а общий размер ВВП остался бы прежним. Это, конечно, противоречит кейнсианским идеям о том, как рост государственных расходов может стимулировать ВВП.

---

### 9. `p0593` — длина озвучки / длина оригинала: 0.79; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Political leaders and financial experts praised financial markets for helping goods and services markets to work more efficiently and grease the wheels of capitalism. In his ‘The Great Moderation’ speech in 2004, Ben Bernanke, who later became the Chairman of the US Federal Reserve, said: ‘The increased depth and sophistication of financial markets, deregulation in many industries, the shift away from manufacturing toward services, and increased openness to trade and international capital flows are other examples of structural changes that may have increased macroeconomic flexibility and stability.’35 Spectacular growth in the volume of derivatives – which can be traded even if the underlying assets were never delivered or deliverable – was viewed as helping to reduce systemic risks and ‘get prices right’. The often enormous profits were dressed up as fulfilling the worthy social objective of spreading and managing risk so that the previously unbankable and uncreditworthy could be brought in from the cold and sold products – especially homes – that the more affluent took for granted.

**В озвучку попало:**

> [thoughtful] Политики и финансовые эксперты превозносили рынки за то, что те помогают эффективно распределять ресурсы и смазывают колеса капитализма. В две тысячи четвертом году Бен Бернанке, будущий глава Федеральной резервной системы США, заявил, что углубление финансовых рынков, дерегуляция и переход от производства к услугам повышают гибкость и стабильность экономики. Впечатляющий рост объема деривативов — которыми можно торговать, даже если базовый актив никогда не будет поставлен, — воспринимался как способ снижения системных рисков и «правильного» ценообразования. Огромные прибыли преподносились как результат выполнения благородной социальной задачи: распределения рисков. Якобы это позволяло вовлечь в финансовую систему тех, кто раньше был «нерукопожатным», и продавать им продукты, например, собственное жилье, которое раньше было доступно только богатым.

---

### 10. `p0110` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> For centuries, economists and policymakers – people who set a plan for an organization such as government or a business – have divided activities according to whether they produce value or not; that is, whether they are productive or unproductive. This has essentially created a boundary – the fence in Figure 1 below – thereby establishing a conceptual boundary – sometimes referred to as a ‘production boundary’ – between these activities.¹⁶ Inside the boundary are the wealth creators. Outside are the beneficiaries of that wealth, who benefit either because they can extract it through rent-seeking activities, as in the case of a monopoly, or because wealth created in the productive area is redistributed to them, for example through modern welfare policies. Rents, as understood by the classical economists, were *unearned* income and fell squarely outside the production boundary. Profits were instead the returns earned for productive activity inside the boundary.

**В озвучку попало:**

> На протяжении столетий экономисты и политики — те, кто задает вектор развития государства или бизнеса, — делили все виды деятельности на производительные и непроизводительные. По сути, это создало своего рода концептуальный барьер, который часто называют «границей производства». Внутри этой границы находятся создатели богатства. Снаружи — те, кто лишь пользуется этим богатством. Они получают его либо путем извлечения ренты, как в случае с монополиями, либо через перераспределение, например, с помощью современных социальных программ. Классики экономической мысли считали ренту незаработанным доходом, поэтому она всегда оставалась за пределами границы производства. Прибыль же, напротив, рассматривалась как вознаграждение за производительную деятельность внутри этой зоны.

---

### 11. `p0252` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> By highlighting the different types of incomes earned, such as rent, profits and wages, Ricardo drew attention to an important question. When goods are sold, how are the proceeds of that sale divided? Does everyone involved get their ‘just share’ for the amount of effort they put into production? Ricardo’s answer was an emphatic ‘No’.

**В озвучку попало:**

> Выделяя разные виды доходов — ренту, прибыль и заработную плату, — Рикардо привлек внимание к важному вопросу. Как распределяются доходы от продажи товаров? Получает ли каждый участник свою «справедливую долю» за вложенные усилия? Ответ Рикардо был категоричным: «Нет».

---

### 12. `p0094` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> Value can be defined in different ways, but at its heart it is the production of new goods and services. How these outputs are produced (production), how they are shared across the economy (distribution) and what is done with the earnings that are created from their production (reinvestment) are key questions in defining economic value. Also crucial is whether what it is that is being created is useful: are the products and services being created increasing or decreasing the resilience of the productive system?

**В озвучку попало:**

> [serious] Стоимость можно определять по-разному, но в своей основе это производство новых товаров и услуг. Как эти результаты создаются, как они распределяются в экономике и что делается с доходами от их производства — вот ключевые вопросы для определения экономической стоимости. Также важно, является ли создаваемое полезным: увеличивают ли продукты и услуги устойчивость производственной системы или снижают ее?

---

### 13. `p0547` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> During this time, banks never ceased to lobby against the regulations that deprived them of significant markets, and others (like the Glass– Steagall Act) which restricted their scope to combine operations in different markets. As well as pushing for an end to regulations, banks proved adept at persuading politicians that restrictive regulations were unworkable, by finding ways to work around them. Bans on speculative derivatives trading, enacted in the US in the 1930s because of its role in magnifying the 1929 Crash and Great Depression, were effectively sidestepped by the growth of unregulated over-the-counter derivatives trading, which grew explosively in the 1980s and defied subsequent efforts at re-regulation.¹³ Banks’ invention of ‘offshore’ currencies, to sidestep cross-border capital controls, was especially effective. In 1944, the Bretton Woods system had pegged the value of the dollar to gold. But when the post-war boom, based on manufacturing, tailed off around 1970, ‘light-touch’ financial regulation increasingly appealed to policymakers on both sides of the Atlantic. The financial sector reacted to this interest by developing a new currency, the Eurodollar.

**В озвучку попало:**

> [serious] В это время банки не прекращали лоббировать отмену правил, которые лишали их доступа к прибыльным рынкам или запрещали объединять разные виды деятельности. Они не только требовали отмены ограничений, но и мастерски убеждали политиков в их неэффективности, находя способы обойти закон. Запреты на торговлю спекулятивными деривативами, введенные в США после краха 1929 года, были фактически сведены на нет развитием нерегулируемого внебиржевого рынка. В восьмидесятых годах он начал взрывной рост, игнорируя любые попытки повторного регулирования. Особенно эффективным стало создание банками «офшорных» валют для обхода контроля за движением капитала. В 1944 году Бреттон-Вудская система привязала доллар к золоту. Но когда послевоенный бум, основанный на производстве, начал угасать около 1970 года, «мягкое» регулирование стало всё больше привлекать политиков. Финансовый сектор отреагировал на этот интерес, разработав новую валюту — евродоллар.

---

### 14. `p0132` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> Contrary to the widespread assumption that policy should be directionless, simply removing barriers and focusing on ‘levelling the playing field’ for businesses, an immense amount of policymaking is needed to reach these particular objectives. Growth will not somehow go in this direction by itself. Different types of policy are needed to tilt the playing field in the direction deemed desirable. This is very different from the usual assumption that policy should be directionless, simply removing barriers so that businesses can get on with smooth production.

**В озвучку попало:**

> Вопреки распространенному мнению, что политика должна быть нейтральной, а задача государства — лишь устранять барьеры для бизнеса, для достижения этих целей требуется огромная работа. Рост не пойдет в нужном направлении сам по себе. Необходимы разные виды политики, чтобы склонить чашу весов в желаемую сторону. Это сильно отличается от привычного допущения, что политика должна быть «беспристрастной» и просто позволять бизнесу заниматься производством.

---

### 15. `p1030` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> As is the nature of early-stage investment in technologies with uncertain prospects, some investments are winners, but many are losers. For every Internet (a success story of US government financing), there are many Concordes (a white elephant funded by the British and French governments). Consider the twin tales of Solyndra and Tesla Motors. In 2009, Solyndra, a solar-power-panel start-up, received a $535 million guaranteed loan from the US Department of Energy; that same year, Tesla, the electric-car manufacturer, got approval for a similar loan, of $465 million. In the years afterwards, Tesla was wildly successful, and the firm repaid its loan in 2013. Solyndra, by contrast, filed for bankruptcy in 2011, and among fiscal conservatives became a byword for the government’s sorry track record when it comes to picking winners. Of course, if the government is to act like a venture capitalist, it will necessarily encounter many failures. The problem, however, is that governments, unlike venture capital firms, are often saddled with the costs of the failures while earning next to nothing from the successes. Taxpayers footed the bill for Solyndra’s losses – yet got hardly any of Tesla’s profits. Strangely, the US government had put in a claim for 3 million shares into Tesla only if it did not pay back the loan – almost as if the US government has an interest in owning a part of failed companies! Tesla did pay back the loan in 2013, and so had the US government taken a stake in Tesla as a success rather than as a failure, it would have been able to more than cover its losses from Solyndra. The year Tesla received its government loan, the company went public at an opening price of $17 a share; that figure had risen to $93 by the time the loan was repaid. Today shares in Tesla trade above $200.

**В озвучку попало:**

> [serious] Инвестиции в ранние технологии всегда сопряжены с неопределенностью: одни проекты выигрывают, другие проигрывают. На каждый успех, вроде финансирования интернета правительством США, приходится множество неудач, подобных «Конкорду». Вспомним историю компаний Solyndra и Tesla. В 2009 году производитель солнечных панелей Solyndra получил от Министерства энергетики США кредит на 535 миллионов долларов. В том же году Tesla получила аналогичный кредит на 465 миллионов. В последующие годы Tesla добилась невероятного успеха и погасила заем в 2013 году. Solyndra же обанкротилась в 2011-м, став для консерваторов примером того, как государство «не умеет выбирать победителей». Конечно, если государство действует как венчурный инвестор, оно неизбежно будет сталкиваться с потерями. Проблема в том, что в отличие от частных фондов, государство часто берет на себя все убытки, почти ничего не зарабатывая на успехах. Налогоплательщики оплатили крах Solyndra, но не получили почти ничего от прибыли Tesla. Как ни странно, правительство США претендовало на долю в Tesla только в случае невозврата кредита — будто государство заинтересовано в том, чтобы владеть лишь долями в провальных компаниях! Если бы правительство взяло долю в Tesla как в успешном проекте, оно с лихвой покрыло бы потери от Solyndra. Когда компания получила кредит, ее акции стоили 17 долларов, а к моменту погашения долга цена выросла до 93 долларов. Сегодня акции Tesla стоят более 200 долларов.

---

### 16. `p0813` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Morgan,26 the weighted average cost of capital remains quite low at 8.5 per cent but the median hurdle rate (minimum return on investment needed to justify a new project) reported by S&P 500 companies is 18 per cent. This suggests that companies are not pursuing investment opportunities unless the differential between their expected returns and their cost of capital is around 10 percentage points. Why would they leave such opportunities on the table? One explanation, given the exigencies of MSV, is that they have easier alternatives – such as share repurchases.

**В озвучку попало:**

> При этом медианная пороговая ставка, которую заявляют компании из индекса S&P 500, составляет 18 процентов. Это значит, что компании не берутся за проекты, если ожидаемая доходность не превышает стоимость капитала как минимум на 10 процентных пунктов. Почему они упускают такие возможности? Одно из объяснений, продиктованное логикой максимизации акционерной стоимости, заключается в том, что у них есть более простые альтернативы — например, обратный выкуп акций.

---

### 17. `p0255` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Indeed, as is also argued today, Ricardo believed that the pool of (mainly unskilled) workers held the losing ticket. In Ricardo’s day, agricultural labour flocked to the fast-growing cities and the supply of unskilled labour exceeded demand for it. Without bargaining power, these workers were paid a meagre subsistence wage. Ricardo’s portrayal of rents dominating production also had a political impact. It helped to persuade Britain to abolish the Corn Laws in 1846 and embrace free trade, which diminished the power of big vested interests and allowed production costs, rather than embedded monopoly and the privileges that went with it, to govern production. The ensuing decades saw Britain become the ‘workshop of the world’. But the abolition of the Corn Laws brought about a political transformation as well as an economic one: it tipped the balance of power away from aristocratic landlords and towards manufacturing as the nineteenth century wore on. Value theory influenced political behaviour, and vice versa – the performativity referred to in the Preface.

**В озвучку попало:**

> [serious] Рикардо также считал, что в проигрыше остается основная масса неквалифицированных рабочих. В его время сельские жители массово устремлялись в быстрорастущие города, и предложение дешевой рабочей силы превышало спрос. Не имея возможности торговаться, эти люди получали лишь скудную плату на уровне выживания. Взгляд Рикардо на доминирование ренты имел и политические последствия. Он помог убедить Британию отменить «хлебные законы» в 1846 году и перейти к свободной торговле. Это ослабило влияние крупных собственников и позволило производственным издержкам, а не монопольным привилегиям, определять экономическую жизнь. В последующие десятилетия Британия стала «мастерской мира». Отмена законов привела к политической трансформации: власть постепенно переходила от аристократов-землевладельцев к промышленникам. Теория стоимости влияла на политику, а политика — на теорию.

---

### 18. `p0390` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> According to marginalists, because value derives from price, somebody earning a very high salary is indicative of their productivity and worth. At the same time, anybody holding down a job at all is supposed to reflect their preference for work: the utility of work against that of leisure. GDP can be measured as the total amount of products produced, the total amount demanded, or the total income earned (with adjustments reviewed below). But if income is not necessarily a sign of productivity but of something else – for example the classicals’ notion of rent as ‘unearned income’ – what are the implications for GDP as a reliable measure of an economy’s productiveness?

**В озвучку попало:**

> Согласно маржиналистам, поскольку ценность проистекает из цены, очень высокая зарплата свидетельствует о продуктивности и ценности работника. В то же время считается, что любая работа отражает предпочтения человека: его выбор в пользу труда, а не отдыха. ВВП можно измерить как общую стоимость произведенных товаров, общий спрос или общий доход. Но если доход не всегда является признаком продуктивности, а чем-то иным — например, классической рентой как «незаработанным доходом» — то что это значит для ВВП как надежного индикатора продуктивности экономики?

---

### 19. `p0191` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Contrasting sharply with the prevailing mercantilist thinking that gave gold a privileged place, Quesnay believed that land was the source of all value. Figure 3 illustrates how for him, in the end, everything that nourished humans came from the earth. He pointed out that, unlike humans, Nature actually produced new things: grain out of small seeds for food, trees out of saplings and mineral ores from the earth from which houses and ships and machinery were built. By contrast, humans could not produce value. They could only transform it: bread from seeds, timber from wood, steel from iron. Since agriculture, husbandry, fishing, hunting and mining (all in the darker blob in Figure 3) bring Nature’s bounty to society, Quesnay called them the ‘productive class’. By contrast, he thought that nearly all other sectors of the economy – households, government, services and even industry, lumped together in the lighter blob – were unproductive.

**В озвучку попало:**

> [thoughtful] В резком противоречии с господствующей меркантилистской мыслью, отводившей золоту привилегированное место, Кенэ считал, что источником всей стоимости является земля. Он указывал, что, в отличие от людей, природа действительно создаёт новые вещи: зерно из маленьких семян, деревья из саженцев, минеральные руды, из которых строят дома, корабли и механизмы. Люди же, напротив, не могут создавать стоимость. Они могут лишь преобразовывать её: хлеб из семян, доски из древесины, сталь из железа. Поскольку сельское хозяйство, животноводство, рыболовство, охота и добыча ископаемых приносят обществу дары природы, Кенэ назвал их «продуктивным классом». Все остальные секторы экономики — домохозяйства, правительство, сферу услуг и даже промышленность — он считал непродуктивными.

---

### 20. `p0215` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> With Britain well on the path to industrial capitalism, Smith’s *The* *Wealth of Nations* highlighted the role of the division of labour in manufacturing. His account of pin-manufacturing continues to be cited today as one of the first examples of organizational and technological change at the centre of the economic growth process. Explaining the immense increase in productivity that occurred when one worker was no longer responsible for producing an entire pin, but only for a small part of it, Smith related how the division of labour allowed an increase in specialization and hence productivity: I have seen a small manufactory of this kind where ten men only were employed, and where some of them consequently performed two or three distinct operations. But though they were very poor, and therefore but indifferently accommodated with the necessary machinery, they could, when they exerted themselves, make among them about twelve pounds of pins in a day. There are in a pound upwards of four thousand pins of a middling size. Those ten persons, therefore, could make among them upwards of forty-eight thousand pins in a day. Each person, therefore, making a tenth part of forty-eight thousand pins, might be considered as making four thousand eight hundred pins in a day. But if they had all wrought separately and independently, and without any of them having been educated to this peculiar business, they certainly could not each of them have made twenty, perhaps not one pin in a day; that is, certainly, not the two hundred and fortieth, perhaps not the four thousand eight hundredth part of what they are at present capable of performing, in consequence of a proper division and combination of their different operations.²⁰

**В озвучку попало:**

> Когда Британия уже уверенно встала на путь промышленного капитализма, Смит в своем труде «Богатство народов» подчеркнул значение разделения труда в производстве. Его описание изготовления булавок до сих пор приводят как один из первых примеров организационных и технологических перемен, лежащих в основе экономического роста. Смит объяснял огромный скачок производительности тем, что рабочий перестал отвечать за создание всего изделия целиком, сосредоточившись лишь на одной операции. Он писал: «Я видел небольшую мануфактуру такого рода, где было занято всего десять человек. Некоторые из них выполняли по две или три отдельные операции. Несмотря на то что они были очень бедны и плохо обеспечены необходимыми станками, при должном усердии они могли произвести около двенадцати фунтов булавок в день. В фунте содержится более четырех тысяч булавок среднего размера. Таким образом, эти десять человек могли изготовить более сорока восьми тысяч булавок в день. Получается, что каждый из них, выполняя десятую часть работы, создавал четыре тысячи восемьсот булавок. Но если бы они работали отдельно и независимо, не будучи обученными этому ремеслу, каждый из них наверняка не смог бы сделать и двадцати булавок в день, а возможно, и ни одной. То есть они не смогли бы произвести даже двухсот сороковой, а может, и четырехтысячной восьмисотой части того, что способны сделать сейчас благодаря правильному разделению и сочетанию своих операций».

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0691` — длина озвучки / длина оригинала: 1.54; классы правки: —

**Исходный абзац:**

> How does finance extract value? There are broadly three related answers: by inserting a wedge, in the form of transaction costs, between providers and receivers of finance; through monopoly power, especially in the case of banks; and with high charges relative to risks run, notably in fund management.

**В озвучку попало:**

> [thoughtful] Как именно финансовая система извлекает прибыль? Можно выделить три взаимосвязанных способа. Во-первых, это создание посреднического барьера в виде транзакционных издержек между теми, кто предоставляет капитал, и теми, кто его получает. Во-вторых, использование монопольной власти, что особенно характерно для банков. И в-третьих, установление высоких комиссий, которые несоразмерны принимаемым рискам, что ярко проявляется в сфере управления фондами.

---

### 2. `p1139` — длина озвучки / длина оригинала: 1.53; классы правки: —

**Исходный абзац:**

> Fourth, governments often own productive businesses such as railways, postal services or energy providers. But, by accounting convention, state-owned enterprises that sell products at market prices are counted as private enterprises in the value added of the relevant sector: public railways are part of the transport sector, not the government sector. Even though state-owned corporations earn profits (and in the stats, higher profits means higher value added), their profits are accounted for in the industrial sector they work for, not the ‘government’ sector. So if the state-owned railway makes huge sales and profits (high value added), it boosts the transport sector value added, even if that sector is perhaps only successful because of state ownership. Only government-owned entities that don’t sell at market prices are by definition included in the government sector. In short, from the perspective of national accounting, you don’t count as government if you are doing market production. So, in the case of free public education, while increasing the number of teachers might add to

**В озвучку попало:**

> В-четвертых, государства часто владеют производственными предприятиями, такими как железные дороги, почтовые службы или энергетические компании. Но по правилам бухгалтерского учета государственные предприятия, продающие товары по рыночным ценам, учитываются как частные компании в добавленной стоимости соответствующего сектора. Например, государственные железные дороги относятся к транспортному сектору, а не к государственному. Даже если такие корпорации получают прибыль — а в статистике более высокая прибыль означает более высокую добавленную стоимость — эта прибыль учитывается в той отрасли, где они работают, а не в секторе «государство». Поэтому, если государственная железная дорога показывает огромные продажи и прибыль, это увеличивает добавленную стоимость транспортного сектора, даже если успех этого сектора обусловлен именно государственной собственностью. По определению, в государственный сектор включаются только те структуры, которые не продают свои услуги по рыночным ценам. Короче говоря, с точки зрения национальных счетов, если вы занимаетесь рыночным производством, вы не считаетесь государством. Так, в случае с бесплатным государственным образованием: хотя увеличение числа учителей может добавить цифр в ВВП, так как им платят зарплату, стоимость, которую они реально создают, не увеличивает ВВП. Все это означает, что государство может увеличить свою добавленную стоимость только за счет нерыночного производства. Это скрывает истинную важность государства в экономике: стоимость, которую *действительно* создают государственные предприятия, не отражается в официальной статистике, как и ценность, которую генерируют образование или здравоохранение.

---

### 3. `p0743` — длина озвучки / длина оригинала: 1.30; классы правки: —

**Исходный абзац:**

> Reform is not impossible. Financial regulation can be used to reward long-termism and also help to direct finance towards the real economy, as opposed to feeding on itself. Indeed, the point of the financial transaction tax – which has yet to be implemented – is precisely to reward long-term investments over quick millisecond trades.

**В озвучку попало:**

> Реформы возможны. Финансовое регулирование можно использовать для поощрения долгосрочного планирования и перенаправления капитала в реальный сектор экономики, вместо того чтобы позволять финансам замыкаться на самих себе. Собственно, смысл налога на финансовые транзакции, который до сих пор не внедрен, как раз и заключается в том, чтобы сделать долгосрочные инвестиции более выгодными, чем быстрые сделки, совершаемые за миллисекунды.

---

### 4. `p1067` — длина озвучки / длина оригинала: 1.30; классы правки: —

**Исходный абзац:**

> After the 2008 financial crash – a crisis chiefly brought about by private, not public, debt – governments saved the capitalist system from breakdown. Not only did they pump money into the financial system: they took over private assets. A few months after Lehman Brothers collapsed, the US government was in charge of General Motors and Chrysler, the British government was running high street banks and, across the OECD, governments had committed the equivalent of 2.5 per cent of GDP to rescuing the system.

**В озвучку попало:**

> [serious] После финансового краха 2008 года — кризиса, вызванного прежде всего частным, а не государственным долгом, — правительства спасли капиталистическую систему от развала. Они не просто вливали деньги в финансовый сектор, они брали под контроль частные активы. Через несколько месяцев после банкротства банка «Леман Бразерс» правительство США фактически управляло компаниями «Дженерал Моторс» и «Крайслер», британское правительство взяло на себя руководство крупными банками, а страны Организации экономического сотрудничества и развития направили на спасение системы сумму, эквивалентную двум с половиной процентам мирового валового внутреннего продукта.

---

### 5. `p0730` — длина озвучки / длина оригинала: 1.29; классы правки: —

**Исходный абзац:**

> This same ‘2 and 20’ model is also used in venture capital. Like hedge funds, VC claims special skill in picking profitable opportunities in young businesses and technologies. In practice, VC usually enters the fray after others, notably taxpayer-funded basic research, have taken the biggest risks and the technology is already proven.

**В озвучку попало:**

> Такая же модель «2 и 20» используется и в венчурном капитале. Как и хедж-фонды, венчурные компании заявляют об особых навыках в поиске прибыльных возможностей в молодых компаниях и технологиях. На практике же венчурные инвесторы обычно вступают в игру после того, как другие — в частности, фундаментальные исследования, финансируемые налогоплательщиками, — уже взяли на себя основные риски и технология доказала свою состоятельность.

---

### 6. `p0627` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> Among the richest 10 per cent, it was only 1.8 per cent. This means that poorer families were much more indebted than richer ones in relative terms. The stagnation or outright decline in real incomes of the poorest group forced them to borrow to finance current consumption.

**В озвучку попало:**

> Среди 10 процентов самых богатых семей этот показатель составил всего 1,8 процента. Это означает, что бедные семьи были гораздо более закредитованы, чем богатые, если рассматривать ситуацию в относительном выражении. Стагнация или прямое снижение реальных доходов в беднейших группах вынуждали их брать в долг, чтобы финансировать текущее потребление.

---

### 7. `p1069` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> In a nutshell, austerity assumes that public debt is bad for growth, and that the only way to reduce it is to cut government spending and debt by running a budget surplus, irrespective of the possible social cost. With debt down to an unspecified level and government finances ‘sound’, the private sector will be freed to reignite prosperity.

**В озвучку попало:**

> Если говорить кратко, политика жесткой экономии исходит из предположения, что государственный долг вредит росту, и единственный способ его уменьшить — это сократить государственные расходы, добиваясь профицита бюджета, невзирая на возможные социальные издержки. Считается, что как только долг снизится до определенного уровня, а государственные финансы придут в норму, частный сектор получит свободу и вновь запустит механизм процветания.

---

### 8. `p0717` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> But performance must be balanced with fees. Consider investing long-term, say over the forty-year working life of a given employee. One of the leading figures in the US fund management industry is John Bogle. He founded Vanguard, a very large index investment group (not an active investor) which charges low fees. Bogle has estimated an all-in cost for actively managed funds of 2.27 per cent of the funds’ value. The amounts may not seem excessive. But Bogle never tires of saying to fund investors:

**В озвучку попало:**

> [serious] Однако доходность нужно сопоставлять с комиссиями. Представьте, что вы инвестируете в долгосрочной перспективе, скажем, на протяжении всей сорокалетней трудовой карьеры. Один из ведущих деятелей индустрии управления фондами в США — Джон Богл. Он основал Vanguard, очень крупную группу индексных инвестиционных фондов, которая не занимается активным управлением и взимает низкие комиссии. Богл подсчитал, что совокупные расходы для инвесторов в активно управляемые фонды составляют два целых двадцать семь сотых процента от стоимости активов. Эти суммы могут показаться не такими уж большими. Но Богл не устает повторять инвесторам:

---

### 9. `p0936` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> The classical economists would have had little time for the way in which the VC industry has extracted value by shifting money around rather than creating value: for them the point was to nurture the production of value rather than its simple circulation.

**В озвучку попало:**

> [thoughtful] Классические экономисты вряд ли одобрили бы то, как индустрия венчурного капитала извлекает прибыль. Они предпочитали просто перекладывать деньги с места на место, вместо того чтобы создавать реальную ценность. Для экономистов прошлого суть заключалась в поддержке производства, а не в простом обращении капитала.

---

### 10. `p1138` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> Austerity aimed to cut back the inputs (government spending) while producing the ‘same’ outputs.³⁴ It is hardly surprising that this kind of productivity ‘improvement’ does not result in better services – we only have to look at the long NHS waiting times to see this.

**В озвучку попало:**

> Политика жесткой экономии была направлена на сокращение затрат — то есть государственных расходов — при сохранении прежнего уровня услуг. Неудивительно, что такое «повышение» производительности не привело к улучшению качества обслуживания. Достаточно взглянуть на длинные очереди в Национальную службу здравоохранения, чтобы в этом убедиться.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1011` — совпадение символов с оригиналом: 27%; классы правки: —

**Исходный абзац:**

> Six firms (Facebook, Google, Yahoo, AOL, Twitter and Amazon) account for around 53 per cent of the digital advertising market (with just Google and Facebook making up 39 per cent).⁷¹ Such dominance implies that online giants can impose their conditions on users and customer firms.

**В озвучку попало:**

> Шесть компаний — Facebook, Google, Yahoo, AOL, Twitter и Amazon — контролируют около пятидесяти трех процентов рынка цифровой рекламы, причем на долю Google и Facebook приходится тридцать девять процентов. Такое доминирование означает, что интернет-гиганты могут диктовать свои условия пользователям и компаниям-клиентам.

---

### 2. `p0999` — совпадение символов с оригиналом: 22%; классы правки: —

**Исходный абзац:**

> All this sounds fine until you ask yourself what it might mean for the size of companies. A strong source of increasing returns to scale necessarily expands companies. Google’s size is a direct result of the network effects typical of Internet-based services. Google is not just a search engine. It is also an email address (Gmail), a conference call maker (Google Hangout), a document creator and editor – all designed to maximize the advantages of sticking to Google: you cannot use Google Hangout without a Gmail address.

**В озвучку попало:**

> [serious] Всё это звучит неплохо, пока вы не зададитесь вопросом, что это означает для размера компаний. Мощный источник возрастающей отдачи от масштаба неизбежно приводит к их укрупнению. Масштабы Google — прямой результат сетевых эффектов, характерных для интернет-сервисов. Google — это не просто поисковик. Это электронная почта, сервис для конференц-связи, инструменты для создания и редактирования документов. Всё это спроектировано так, чтобы вы не могли отказаться от экосистемы Google: например, вы не воспользуетесь Google Hangout без учетной записи Gmail.

---

### 3. `p0046` — совпадение символов с оригиналом: 21%; классы правки: —

**Исходный абзац:**

> These stories of value creation are not limited to finance. In 2014 the pharmaceutical giant Gilead priced its new treatment for the life-threatening hepatitis C virus, Harvoni, at $94,500 for a three-month course. Gilead justified charging this price by insisting that it represented ‘value’ to health systems. John LaMattina, former President of R&D at the drugs company Pfizer, argued that the high price of speciality drugs is justified by how beneficial they are for patients and for society in general.

**В озвучку попало:**

> [serious] Эти истории о создании ценности не ограничиваются финансами. В 2014 году фармацевтический гигант Gilead установил цену на свой новый препарат от гепатита С, Харвони, в размере 94 500 долларов за трехмесячный курс. В Gilead оправдывали такую цену тем, что она якобы отражает «ценность» для систем здравоохранения. Джон ЛаМаттина, бывший президент по исследованиям и разработкам компании Pfizer, утверждал, что высокая стоимость специализированных лекарств оправдана их пользой для пациентов и общества в целом.

---

### 4. `p1008` — совпадение символов с оригиналом: 21%; классы правки: —

**Исходный абзац:**

> Uber, like Google, Facebook and Amazon, seems to have no limit to its size. The network effects that pervade online markets add an important peculiarity: once a firm establishes leadership in a market its dominance increases and becomes self-perpetuating almost automatically. If everyone is on Facebook, no one wants to join a different social network. As most people search on Google, the gap between Google and its competitors grows wider because it can elaborate on more data. And as its market share rises, so does its capacity to attract users, which in turn increases its 70 market dominance.

**В озвучку попало:**

> [serious] Uber, как и Google, Facebook и Amazon, кажется, не имеет пределов роста. Сетевые эффекты, пронизывающие онлайн-рынки, добавляют важную особенность: как только фирма устанавливает лидерство, ее доминирование усиливается и становится почти автоматическим. Если все сидят в Facebook, никто не хочет переходить в другую социальную сеть. Поскольку большинство людей ищут информацию через Google, разрыв между ним и конкурентами увеличивается, ведь компания может обрабатывать всё больше данных. А по мере роста доли рынка растет и способность привлекать пользователей, что, в свою очередь, еще больше укрепляет позиции компании.

---

### 5. `p0130` — совпадение символов с оригиналом: 20%; классы правки: —

**Исходный абзац:**

> Once impediments to competition are removed, the outcome should benefit everyone. How different notions of value might affect the distribution of revenues between workers, public agencies, managers and shareholders at, say, Google, General Electric or BAE Systems, goes unquestioned.

**В озвучку попало:**

> Считается, что как только препятствия для конкуренции будут устранены, результат принесет пользу всем. Вопрос о том, как различные представления о стоимости влияют на распределение доходов между работниками, государственными органами, менеджерами и акционерами, скажем, в Google, General Electric или BAE Systems, остается без внимания.

---

### 6. `p1010` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Google alone accounts for 70 per cent of online searches in the US, and 90 per cent in Europe. Facebook has more than 1.5 billion users, a quarter of the planet’s population and streets ahead of its competitors. Amazon now accounts for around half of the US books market, not to mention e-books.

**В озвучку попало:**

> Только на долю Google приходится семьдесят процентов поисковых запросов в США и девяносто процентов в Европе. У Facebook более полутора миллиардов пользователей — это четверть населения планеты, что намного опережает конкурентов. Amazon сейчас занимает около половины книжного рынка США, не говоря уже об электронных книгах.

---

### 7. `p0668` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> So when the global financial crisis arrived in 2007 it blew apart the ideology that had promoted financialization above all else. Yet the crisis did not fundamentally change how the sector is valued: two years later the head of Goldman Sachs could still keep a straight face when arguing that his bankers were the most productive in the world. And the fact that ex- Goldman Sachs employees were abundant in both the Obama and Trump administrations shows the power of the ‘story’ of the value created by Goldman Sachs across political parties.

**В озвучку попало:**

> Поэтому, когда в 2007 году разразился мировой финансовый кризис, он разрушил идеологию, ставившую финансиализацию превыше всего. Тем не менее кризис не изменил фундаментально подход к оценке этого сектора. Два года спустя глава Goldman Sachs мог с невозмутимым лицом утверждать, что его банкиры — самые продуктивные в мире. А тот факт, что бывшие сотрудники Goldman Sachs занимали множество постов в администрациях Обамы и Трампа, лишь подтверждает силу истории о ценности, создаваемой этой компанией, независимо от политических предпочтений.

---

### 8. `p0795` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> MSV’s origins are often traced to the development of the ‘portfolio theory of the firm’, a popular explanation for the development of the large industrial conglomerates of the 1950s and 1960s. The portfolio theory of the firm held that companies – like other investors – could spread their risks by owning assets in diverse industries. It assumed that corporations were only a collection of asset-generating cash flows and that professional managers, who were emerging as the heroes of modern capitalism, were capable of running any type of industry equally well. Business schools aimed to train managers with exactly this purpose in mind. Perhaps the epitome of the conglomerate of the time was the Transamerica Corporation, which at one stage counted among its sprawling interests the Bank of America, the United Artists film studio, Transamerica Airlines, Budget Rent a Car and various insurance operations.

**В озвучку попало:**

> [serious] Корни концепции максимизации акционерной стоимости часто связывают с развитием «портфельной теории фирмы». Это было популярное объяснение того, почему в пятидесятые и шестидесятые годы возникали огромные промышленные конгломераты. Портфельная теория гласила, что компании, подобно частным инвесторам, могут снижать риски, владея активами в самых разных отраслях. Предполагалось, что корпорации — это просто набор активов, генерирующих денежные потоки, а профессиональные менеджеры, ставшие героями современного капитализма, способны одинаково эффективно управлять любым бизнесом. Бизнес-школы стремились готовить управленцев именно с такой установкой. Пожалуй, ярчайшим примером конгломерата того времени была корпорация Transamerica. В какой-то момент в ее разветвленную империю входили банк Bank of America, киностудия United Artists, авиакомпания Transamerica Airlines, сервис проката автомобилей Budget и различные страховые компании.

---

### 9. `p1024` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> IBM and Microsoft – virtually monopolize it. But the problem is not just a question of competition – the size and number of firms in the sector. It could be argued that a few large companies can achieve the economies of scale required to drive down costs and make data cheaper – not a bad thing given falling real incomes.

**В озвучку попало:**

> IBM и Microsoft — практически монополизировала эту сферу. Но проблема не только в конкуренции, то есть в размере и количестве фирм в секторе. Можно возразить, что несколько крупных компаний способны достичь эффекта масштаба, необходимого для снижения затрат и удешевления данных, что было бы неплохо на фоне падения реальных доходов.

---

### 10. `p0931` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Fourth, employees, who may have been induced to leave secure jobs by the promise of equity in a risky venture, can realize the value of that equity – or at least see the possibility of doing so now that there is some liquidity in the company’s stock. This, indeed, was the primary motivation for Microsoft’s IPO in 1986, having awarded stock options to its employees 17 since 1982.

**В озвучку попало:**

> В-четвертых, сотрудники, которых могли убедить оставить надежную работу обещанием доли в рискованном предприятии, получают возможность реализовать стоимость своих акций — или, по крайней мере, увидеть такую перспективу теперь, когда акции компании стали ликвидными. Именно это было главной мотивацией для IPO компании Microsoft в 1986 году, которая начала выдавать опционы на акции своим сотрудникам еще в 1982-м.

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

> ### ФИЗИОКРАТЫ: ОТВЕТ СКРЫТ В ПОЧВЕ

---

### 4. `p0399` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### A Brief History of National Accounts

**В озвучку попало:**

> ### Краткая история национальных счетов

---

### 5. `p0542` — длина озвучки / длина оригинала: 0.79; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### DEREGULATION AND THE SEEDS OF THE CRASH

**В озвучку попало:**

> ### Дерегулирование и истоки краха

---

### 6. `p0747` — длина озвучки / длина оригинала: 0.95; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 6 Financialization of the Real Economy

**В озвучку попало:**

> ## 6 Финансиализация реальной экономики

---

### 7. `p0989` — длина озвучки / длина оригинала: 0.00; классы правки: absent_from_artifact

**Исходный абзац:**

> ### NETWORK EFFECTS AND FIRST-MOVER ADVANTAGES

**В озвучку попало:**

> *(модель не вернула этот абзац)*

---
