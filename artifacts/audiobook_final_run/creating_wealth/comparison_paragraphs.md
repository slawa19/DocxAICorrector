# Аудиокнига, финальный подтверждающий прогон 2026-08-06 — creating_wealth, материал для просмотра глазами

Книга: Bernard Lietaer & Gwendolyn Hallsmith, *Creating Wealth* (`tests/sources/book/new_bernardlietaer-creatingwealthpdffromepub-160516072739.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_fin2_creating_wealth`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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

1. **Случайная выборка, 60 абзацев прозы** — до 20 из первой, средней и последней трети книги,
   `random.Random(20260804)`, без отбора «по красоте».
2. **20 абзацев с максимальным сжатием** — низ списка по отношению длин.
3. **10 абзацев с максимальным раздуванием** — верх того же списка.
4. **10 самых буквальных абзацев** — максимальное совпадение символов с оригиналом.
5. **0 абзацев, оставшихся в озвучке на английском** (порог ≥ 60 букв, кириллицы < 30 %).
6. **Пустые и почти пустые абзацы — все 8**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1519; вернулось: 1519;
дошло до narration-артефакта: 1498.
Пул прозы, из которого делалась выборка: 757 абзацев.
Медианное отношение длин по прозе: 0.985.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0064` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> Those who gain profit from the current global system obviously will vigorously resist any efforts to change it. And they will prevail until industrial society collapses. Current policies will be desperately pursued until they must be changed in response to crisis. But individuals, families, communities, perhaps even regions, can begin now proactively to make the necessary changes that will lead to true happiness and sustainable wealth.

**В озвучку попало:**

> Те, кто извлекает прибыль из нынешней глобальной системы, будут решительно сопротивляться любым попыткам изменить её. И они будут брать верх до тех пор, пока индустриальное общество не рухнет. Нынешняя политика будет проводиться отчаянно до самого конца, пока кризис не заставит её изменить. Но отдельные люди, семьи, сообщества и, возможно, даже целые регионы могут уже сейчас начать проактивно внедрять необходимые изменения, которые приведут к подлинному счастью и устойчивому благосостоянию.

---

### 2. `p0082` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> Perhaps more than anyone, Gwendolyn’s parents and family are also worth mentioning. Wesley and Joan Hall set amazing examples of principled, intelligent people who worked hard for what they believe. Joan died in 2007, but Wesley continues to be very interested in and supportive of Gwendolyn’s work (even if he does refer to all these complementary currencies as “funny money”).

**В озвучку попало:**

> Нельзя не упомянуть родителей и семью Гвендолин. Уэсли и Джоан Холл стали для неё примером принципиальных и умных людей, которые упорно трудились ради своих убеждений. Джоан ушла из жизни в 2007 году, но Уэсли продолжает проявлять живой интерес к работе Гвендолин и поддерживать её, даже если в шутку называет все эти дополнительные валюты «игрушечными деньгами».

---

### 3. `p0094` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> One of the primary mechanisms for the creation of wealth is our banking and monetary system. We all put our money into the banks — the black box of the economy — and we assume the money will be there when we go to withdraw it. At least part of our mind probably believes that the money is there. We receive statements every month that say it’s there, and we earn interest on the deposits.

**В озвучку попало:**

> [thoughtful] Один из главных механизмов создания богатства — это наша банковская и денежная система. Мы доверяем свои деньги банкам, своего рода «черным ящикам» экономики, и рассчитываем, что они будут там, когда нам понадобятся. По крайней мере, какая-то часть нашего сознания в это верит. Мы ежемесячно получаем выписки, подтверждающие наличие средств, и получаем проценты по вкладам.

---

### 4. `p0118` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Wealth. It’s something we all want. Wealthy is rich, after all — but rich in what? In possessions, money, income? This depends on how you define the word. Its original meaning, from the Old English *weal* (as in commonweal), was simply prosperity or well-being.”¹ What a notion! How far from the meaning many of us have come to associate with the word. Wealth is more than the accumulation of money and resources, and it can be generated in ways other than through conventional financial means. In order to truly capture the wealth of our societies, our cultures and our environments, we have to pay heed to that older notion of wealth as well-being. We might think that winning the lottery will make us wealthy and that wealth will make us happy, but we also know that it doesn’t always work that way. While it’s true that poverty does make for unhappiness, lots of money doesn’t necessarily buy happiness.

**В озвучку попало:**

> [thoughtful] Богатство. Это то, чего мы все хотим. Быть богатым — значит иметь много денег, верно? Но богатым в чем? В имуществе, деньгах или доходах? Все зависит от того, как мы определяем это слово. Его первоначальное значение, восходящее к древнеанглийскому слову «weal» — как в выражении «общее благо» — означало просто процветание или благополучие. Какая глубокая мысль! И как далеко мы ушли от этого смысла в современном понимании. Богатство — это нечто большее, чем просто накопление денег и ресурсов. Его можно создавать способами, далекими от привычных финансовых инструментов. Чтобы по-настоящему оценить богатство нашего общества, культуры и окружающей среды, мы должны вернуться к старой идее богатства как благополучия. Мы можем думать, что выигрыш в лотерею сделает нас богатыми, а богатство принесет счастье, но мы знаем, что это не всегда работает. Бедность действительно делает людей несчастными, но большие деньги вовсе не гарантируют счастья.

---

### 5. `p0145` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> We’ve described several kinds of assets and capital that satisfy the needs we have, and still there has been no mention yet of the financial assets and capital we typically associate with the words *money* and *investment*. That’s partly because money is really more of a means to an end than a need in itself.

**В озвучку попало:**

> Мы описали несколько видов активов и капитала, которые удовлетворяют наши потребности, но пока не упомянули финансовые активы, которые обычно ассоциируются со словами «деньги» и «инвестиции». Это отчасти потому, что деньги — скорее средство достижения цели, чем потребность сама по себе.

---

### 6. `p0161` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> A larger vision for a walkable city with friendly neighborhoods and less suburban sprawl still requires changes in the land use ordinances before there will be any measurable change in density. A larger vision for clean air and reduced climate impacts will have to be translated into a number of policies — ranging from a purchasing policy that requires alternatives to energy-intensive items to capital planning for renewable energy production.

**В озвучку попало:**

> [serious] Чтобы превратить идею пешеходного города с уютными районами и меньшим разрастанием пригородов в реальность, нужно менять правила землепользования. Только так можно добиться заметных изменений в плотности застройки. Точно так же стремление к чистому воздуху и снижению климатических рисков должно воплощаться в конкретных мерах. Это может быть политика закупок, исключающая энергозатратные товары, или долгосрочное планирование инвестиций в возобновляемые источники энергии.

---

### 7. `p0166` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Environmental policies that marginalize or impoverish a group of people or area in the city (or in another part of the world) won’t succeed in the long run. Housing plans that ignore their impact on important open space, wetlands and agricultural land will hurt the city over the long term. Economic development practices that rely on an unsustainable exploitation of natural resources or human potential will also ultimately have the opposite effect — they will further impoverish the community rather than creating real wealth.

**В озвучку попало:**

> Экологические инициативы, которые ущемляют права или ведут к обнищанию какой-то группы людей или района, в долгосрочной перспективе не сработают. Жилищные планы, игнорирующие влияние на открытые пространства, водно-болотные угодья или сельскохозяйственные земли, в конечном счете навредят городу. Экономические стратегии, основанные на хищническом использовании природных ресурсов или человеческого потенциала, также дадут обратный эффект: они лишь усилят бедность сообщества, вместо того чтобы создавать реальное благосостояние.

---

### 8. `p0172` — длина озвучки / длина оригинала: 0.84; классы правки: —

**Исходный абзац:**

> Redefining wealth and refocusing local initiatives on meeting human needs can help local leaders see the economy as being at the service of their community, not the other way around. There are many forms of capital that demand investment for a local community to thrive, not just financial capital. Social capital, human capital, natural capital, institutional capital, technological capital, potential exchange capital, built capital and cultural capital all need to be understood and strengthened — and this multidimensional effort is absolutely the domain of local communities.

**В озвучку попало:**

> Переосмысление понятия богатства и переориентация местных инициатив на удовлетворение реальных человеческих потребностей помогут лидерам увидеть, что экономика должна служить обществу, а не наоборот. Чтобы сообщество процветало, нужно инвестировать не только в финансовый капитал. Социальный, человеческий, природный, институциональный, технологический и культурный капитал — все это требует внимания и укрепления. И именно эта многогранная работа является прямой задачей местных сообществ.

---

### 9. `p0212` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> One market day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral six chickens wanted in exchange for a big ham, the stranger could not refrain from laughing. “Poor people,” he said, “so primitive.”

**В озвучку попало:**

> Однажды на рынок заглянул незнакомец в начищенных до блеска чёрных туфлях и элегантной белой шляпе. Он наблюдал за происходящим с саркастической улыбкой. Увидев, как один фермер бегает по площади, пытаясь собрать шесть кур в обмен на большой кусок ветчины, незнакомец не удержался от смеха. «Бедные люди, — сказал он, — до чего же вы примитивны».

---

### 10. `p0213` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Overhearing this, the farmer’s wife challenged him. “Do you think you can do a better job handling chickens?” The stranger responded: “Chickens, no. But there is a much better way to eliminate all the hassles. Bring me one large cowhide and gather the families. I’ll explain the better way.”

**В озвучку попало:**

> Услышав это, жена фермера бросила ему вызов: «Думаете, вы справились бы с курами лучше?» Незнакомец ответил: «С курами — нет. Но есть способ гораздо лучше, чтобы избавиться от всех этих хлопот. Принесите мне большую коровью шкуру и соберите все семьи. Я объясню, как сделать жизнь проще».

---

### 11. `p0291` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Where are the leverage points, those interventions where a relatively small amount of effort can achieve much larger results? Often, a systems diagram can help identify promising possibilities. In this vicious cycle, there are two important drivers — the bank-debt source of our monetary system and the economic policies we have enacted to facilitate the process of human and natural capital depletion for the sake of the ever higher profits that the system demands. These are the two variables where policy interventions could have an important impact on the destructive force of the system.

**В озвучку попало:**

> Где находятся точки приложения усилий — те рычаги, с помощью которых относительно небольшое воздействие может принести значительный результат? Часто найти перспективные варианты помогает системная диаграмма. В этом порочном круге есть два важных движущих фактора. Первый — это банковский долг как основа нашей денежной системы. Второй — экономическая политика, которую мы проводим, поощряя истощение человеческого и природного капитала ради постоянно растущей прибыли, требуемой системой. Именно на эти две переменные можно повлиять политическими мерами, чтобы снизить разрушительную силу системы.

---

### 12. `p0368` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> When you think of economic capital, the financial capital needed to undertake any type of enterprise is probably what comes to mind. For our purposes however, we will distinguish between three types of economic capital: financial, entrepreneurial and potential exchange capital.

**В озвучку попало:**

> [serious] Когда мы говорим об экономическом капитале, на ум чаще всего приходят финансовые средства, необходимые для запуска любого дела. Однако для целей этой книги мы разделим экономический капитал на три типа: финансовый, предпринимательский и потенциальный обменный капитал.

---

### 13. `p0398` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Providing a new basis to increase the flow of assets throughout the local economic system in ways that meet real needs (while enhancing generative capacities) strengthens the foundation, the reproductive system, the greenhouse of the economy called capital. In this way, community and complementary currencies create new capital by fostering other forms of capital in the economy. A currency that encourages people to save energy, reduce fossil fuel use and lower emissions strengthens the natural capital of the climate regulation system and creates new capital for innovation in the energy sector. Using a local currency to link vocational trainees with houses that need renovation creates new capital in both the built environment and the human capital sectors. New capital can be created in most areas if we find new ways to unleash our creativity, interdependence and compassion outside and around the constraints national money imposes. Abundance and sufficiency are available to us, even in a finite world.

**В озвучку попало:**

> Создание новой основы для увеличения потока активов в местной экономике — так, чтобы это отвечало реальным нуждам и расширяло созидательные возможности, — укрепляет фундамент экономики, которую мы называем капиталом. Таким образом, общественные и дополнительные валюты создают новый капитал, способствуя развитию других его форм. Валюта, которая поощряет людей экономить энергию, сокращать использование ископаемого топлива и снижать выбросы, укрепляет «природный капитал» климатической системы и создает возможности для инноваций в энергетике. Использование местной валюты для связи профессиональных стажеров с домами, требующими ремонта, создает новый капитал как в строительной сфере, так и в секторе человеческих ресурсов. Новый капитал может быть создан во многих областях, если мы найдем способы раскрыть нашу креативность, взаимозависимость и сострадание за пределами ограничений, навязываемых национальной валютой. Изобилие и достаток доступны нам даже в ограниченном мире.

---

### 14. `p0409` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> In the first example, from Egypt, people would receive shards of pottery with a date on them when they put their grain into the storehouse. The longer the grain was stored, the more the charge was for the guards and waste as the grain spoiled. Called *ostraka*,1 these shards circulated alongside the precious metals rings and bars that were used for trade with foreigners. The Greeks, Egypt’s main trading partners at that time, would mock the plain clay Egyptian currency. Yet the Egyptians thought the Greek obsession with metals was strange, “a piece of local vanity, patriotism, or advertisement, with no far-reaching importance.”² They would accept Greek coins, but only for their metal content.

**В озвучку попало:**

> В первом примере, из Египта, люди получали глиняные черепки с датой, когда сдавали зерно в хранилище. Чем дольше зерно хранилось, тем больше приходилось платить за охрану и за потери от порчи. Эти черепки, называемые остраконами, обращались наряду с кольцами и слитками из драгоценных металлов, которые использовались для торговли с иностранцами. Греки, основные торговые партнеры Египта того времени, посмеивались над простой глиняной валютой египтян. Однако сами египтяне считали одержимость греков металлами чем-то странным — «местным тщеславием, патриотизмом или рекламой, не имеющей глубокого значения». Они принимали греческие монеты, но только как металл.

---

### 15. `p0419` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> There is no doubt that the economy of the United States in the 21st century could be called a competitive economy. Competition in free markets is held up as the only way to get low prices and all the benefits of a well-oiled economic system. Schools are competitive, as students vie with each other to get the best grades and to be accepted in exclusive colleges. Sports are competitive, and even families living on the same street have been known to do what it takes to “keep up with the Joneses.”

**В озвучку попало:**

> Нет сомнений, что экономику Соединенных Штатов в двадцать первом веке можно назвать конкурентной. Свободный рынок преподносится как единственный способ добиться низких цен и всех преимуществ отлаженной экономической системы. Конкуренция пронизывает всё: ученики соревнуются за лучшие оценки и места в престижных колледжах, спорт построен на соперничестве, и даже соседи по улице стремятся «не отставать от других».

---

### 16. `p0421` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Things are a little different north of the 49th parallel. Although Canada shares many of the characteristics of the United States, its economy and culture is somewhat less competitive. This can be documented by the large number of cooperative enterprises in Canada per capita as compared to the United States, and the fact that Canadians successfully managed to create a national healthcare system, something the US is only now starting. Many other western industrialized countries exhibit more of a balance between competition and cooperation than the US, as demonstrated in public benefits, inexpensive education systems, high quality national healthcare and other policies that strengthen the common good, rather than being oriented toward the individual.

**В озвучку попало:**

> К северу от сорок девятой параллели всё немного иначе. Хотя Канада во многом похожа на Соединенные Штаты, её экономика и культура менее конкурентны. Это подтверждается большим количеством кооперативных предприятий на душу населения и тем, что канадцы смогли создать национальную систему здравоохранения — то, к чему США только начинают приходить. Многие другие западные индустриальные страны демонстрируют лучший баланс между конкуренцией и сотрудничеством. Это проявляется в социальных льготах, доступном образовании, качественной медицине и других мерах, направленных на общее благо, а не только на интересы индивида.

---

### 17. `p0517` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> In response to the foreclosure crisis, the US Department of Housing and Urban Development created a new program — The Neighborhood Stabilization Program (NSP) — that is providing $4 billion to cities and towns.⁶ The money cannot be used to prevent more foreclosures, but it can be used to buy up foreclosed properties, pay the bank, renovate/ repair them and resell them. If public money is being used to purchase private homes from banks, this investment could be used to create new wealth by developing a means of exchange for housing that will create jobs while at the same time moving homeless people back into homes — all without spending more real taxpayer ’s dollars.

**В озвучку попало:**

> В ответ на кризис Министерство жилищного строительства и городского развития США создало программу стабилизации микрорайонов. В рамках этой инициативы городам и поселкам было выделено 4 миллиарда долларов. Эти средства нельзя использовать для предотвращения новых случаев изъятия жилья за долги, но их можно тратить на выкуп уже изъятых объектов, выплаты банкам, ремонт и последующую перепродажу. Если государственные деньги используются для выкупа частных домов у банков, эти инвестиции можно направить на создание нового богатства. Это позволит сформировать механизм обмена жильем, который создаст рабочие места и одновременно поможет вернуть бездомных в дома, причем без дополнительных затрат налогоплательщиков.

---

### 18. `p0596` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Sacred art in many religions takes on such symbolic importance that the forms, styles and even the paints are so closely prescribed that in centuries past breaking from traditional rules could result in the death penalty in some societies. Art historians spend a lifetime understanding the subtle gestures encoded in art from the era prior to mass literacy.

**В озвучку попало:**

> Во многих религиях священное искусство обретает такой символический вес, что формы, стили и даже краски строго регламентируются. В прошлые века отступление от традиционных правил в некоторых обществах могло караться смертью. Историки искусства тратят целую жизнь, чтобы расшифровать тонкие жесты, заложенные в произведениях эпохи до массовой грамотности.

---

### 19. `p0599` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Fast forward to the 21st century, and the majority of our creative workers no longer dedicate their life energy to the creation of enduring beauty and awe-inspiring celebrations of divine energy. Poets are put to work writing syrupy stanzas for greeting cards, visual artists are designing web pages, corporate logos and publications. Sculptors are employed making gravestones, musicians write jingles for television ads and the most lucrative form of theater is the 30-second commercial aired during the Super Bowl. The well-paid artists, in other words, are working for corporations. Recent statistics show, however, that 55.6% of the rest of the “fine artists, art directors and animators” in the workforce are self-employed, compared to 10% of the rest of the population.¹ Career advice for students thinking about majoring in the arts in college is clear: “the number of qualified workers exceeds the number of available openings because the arts attract many talented people with creative ability.”² In short, there are a lot of people who want to be creative, but a real shortage of paid work for artists.

**В озвучку попало:**

> Перенесемся в двадцать первый век. Большинство творческих работников больше не посвящают свою жизненную энергию созданию вечной красоты или прославлению божественного. Поэты пишут слащавые стишки для открыток, художники разрабатывают веб-страницы, корпоративные логотипы и рекламные буклеты. Скульпторы делают надгробия, музыканты сочиняют джинглы для телерекламы, а самой прибыльной формой театра стал тридцатисекундный ролик во время Супербоула. Иными словами, высокооплачиваемые художники работают на корпорации. Статистика показывает, что пятьдесят пять и шесть десятых процента остальных «свободных художников, арт-директоров и аниматоров» работают на себя, тогда как среди остального населения этот показатель составляет десять процентов. Студентам, планирующим изучать искусство в колледже, дают четкий совет: число квалифицированных специалистов превышает количество доступных вакансий, потому что искусство привлекает множество талантливых людей. Короче говоря, желающих творить много, а оплачиваемой работы для них не хватает.

---

### 20. `p0601` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Yet despite these figures, the *creative economy* has taken over a leading role in the US employment profile in the last 20 years. In the early 1990s, the people with jobs associated with the creative economy surpassed those employed in traditional manufacturing jobs for the first time in history.

**В озвучку попало:**

> И все же, несмотря на эти цифры, «креативная экономика» за последние двадцать лет заняла ведущую роль в структуре занятости США. В начале девяностых годов число людей, занятых в креативном секторе, впервые в истории превысило количество работников в традиционном промышленном производстве.

---

### 21. `p0614` — длина озвучки / длина оригинала: 0.87; классы правки: —

**Исходный абзац:**

> Notice that this approach would ensure that more of the creative activity would take place in town, that its creative people would obtain income in dollars, but that this wouldn’t cost the city any additional dollars. By setting up a foundation, for example, an organization could make the Art Tokens even more valuable to its users than bank-debt dollars.

**В озвучку попало:**

> [thoughtful] Заметьте, такой подход гарантирует, что творческая жизнь города станет активнее. Творческие люди получат доход в долларах, но город при этом не потратит ни цента из своего бюджета. А если создать специальный фонд, арт-токены могут стать для пользователей даже ценнее, чем обычные банковские деньги.

---

### 22. `p0667` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> At this point, you might well say, “I’d buy a hybrid, if only they were more affordable,” or “I’d walk to work if I could find a job near my home.” In other words, although you possess the power of choice, you do not have sufficient good choices at your disposal. So how do we create a world where environmentally-friendly choices are widely available and a sustainable lifestyle the norm? We can begin by reducing the amount of CO2 in the atmosphere. Could a complementary carbon currency be part of the solution?

**В озвучку попало:**

> [thoughtful] В этот момент вы могли бы сказать: «Я бы купил гибрид, если бы они были доступнее» или «Я бы ходил на работу пешком, если бы нашел ее рядом с домом». Иными словами, хотя у вас есть право выбора, у вас нет достаточно хороших вариантов. Как же создать мир, где экологичные решения доступны каждому, а устойчивый образ жизни стал нормой? Мы можем начать с сокращения количества углекислого газа в атмосфере. Может ли дополнительная углеродная валюта стать частью решения?

---

### 23. `p0670` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> Among the developed nations, only Australia and the US have abstained from the treaty. Its Clean Development Mechanism (CDM) allocates a specific amount of carbon credits to various countries and industries, but allows credits to be bought and sold internationally. A company that produces more greenhouse gases than its allocation needs to purchase carbon credits sold by another producer who has reduced emissions beyond what is required. International trading in carbon contracts on the basis of the CDM protocol of the Kyoto treaty has successfully started.

**В озвучку попало:**

> Среди развитых государств только Австралия и Соединённые Штаты воздержались от участия в этом соглашении. Механизм чистого развития, предусмотренный протоколом, распределяет определённое количество углеродных квот между странами и отраслями промышленности. При этом такие квоты можно свободно покупать и продавать на международном уровне. Если компания производит больше парниковых газов, чем ей разрешено, она должна приобрести квоты у другого производителя, который сократил свои выбросы сверх установленной нормы. Международная торговля углеродными контрактами на основе протоколов Киотского соглашения уже успешно началась.

---

### 24. `p0698` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> A *Financial Times* investigation has uncovered widespread failings in the new markets for greenhouse gases, suggesting some organizations are paying for emissions reductions that do not take place.⁷ Others are meanwhile making big profits from carbon trading for very small expenditure and, in some cases, for cleanups that would have been made anyway.

**В озвучку попало:**

> Расследование газеты «Файненшл Таймс» выявило серьезные недостатки на новых рынках парниковых газов. Выяснилось, что некоторые организации платят за сокращение выбросов, которое фактически не происходит. [short pause] Другие же получают огромную прибыль от торговли углеродом при минимальных затратах, а иногда и за те экологические мероприятия, которые были бы проведены в любом случае.

---

### 25. `p0751` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Like individuals, businesses, too, can have a cash flow shortage but a surplus of goods. Again in this case, it’s not terribly convenient to pay in corn, pigs or saddle shoes. And doing so might limit what you can purchase. The shoelace supplier probably doesn’t want a warehouse full of shoes.

**В озвучку попало:**

> Как и частные лица, компании могут столкнуться с нехваткой наличности при избытке товаров. И в этом случае платить зерном, поросятами или ботинками не очень удобно. К тому же это ограничивает ваши возможности для покупок: поставщику шнурков вряд ли нужен склад, забитый обувью.

---

### 26. `p0754` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> Needless to say, the banks did not like the idea, and they tried to stop the new currency, called the WIR, in its tracks. (WIR is derived from the word *Wirtschaftsring* or economic circle — but *wir* also means “we” in German.) Nevertheless, the system survived. The WIR system evolved into a full-scale dual currency bank which manages and lends in both WIR and Swiss Francs.

**В озвучку попало:**

> Разумеется, банкам эта идея не понравилась, и они попытались остановить новую валюту под названием «ВИР» на корню. Название «ВИР» происходит от немецкого слова, означающего «экономический круг», но при этом само слово «wir» переводится как «мы». Тем не менее система выжила. Она превратилась в полноценный банк с двойной валютой, который выдает кредиты и ведет расчеты как в «ВИРах», так и в швейцарских франках.

---

### 27. `p0762` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> The C3 approach is probably the most dependable way to systemically reduce unemployment, and accepting C3 units in payment of taxes is the most effective way for governments to support the spread of the C3 system. Businesses with an account in the same regional network have an incentive to spend their balances with each other, and thus further stimulate the regional economy. C3 provides a win-win environment for all participants and therefore promotes other collaborative activities among regional businesses.

**В озвучку попало:**

> [serious] Подход C3, вероятно, является самым надежным способом системного снижения безработицы, а прием этих единиц для уплаты налогов — самым эффективным методом поддержки системы со стороны государства. Компании, состоящие в одной региональной сети, заинтересованы тратить свои балансы друг с другом, что дополнительно стимулирует региональную экономику. C3 создает взаимовыгодную среду для всех участников и способствует развитию сотрудничества между местными предприятиями.

---

### 28. `p0766` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> We can do a lot to foster a healthy business climate by expanding the ability of local businesses to use either loyalty or commercial barter systems in new ways. When our cities and other local governments accept C3 units in payment of taxes and fees, this will be one of the most effective ways for local governments and businesses to collaborate in solving local economic problems.

**В озвучку попало:**

> Мы можем многое сделать для развития здорового делового климата, расширяя возможности местных компаний по использованию систем лояльности или коммерческого бартера. Когда города и другие органы местного самоуправления начнут принимать единицы C3 в качестве оплаты налогов и сборов, это станет одним из самых эффективных способов сотрудничества власти и бизнеса в решении локальных экономических проблем.

---

### 29. `p0774` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Healthcare in the US is one of the glaring examples of the failure of money, insurance and the privately held healthcare companies’ ability to meet human needs. The US Constitution affirms that we all are created equal — no one born on Earth is more deserving of basic human rights than anyone else. However, the same centripetal forces that consolidate wealth and power in the marketplace and in society are also at work in the healthcare system.

**В озвучку попало:**

> [serious] Система здравоохранения в Соединенных Штатах — один из самых ярких примеров того, как деньги, страхование и частные медицинские компании не справляются с удовлетворением человеческих потребностей. Конституция США провозглашает, что все люди созданы равными, и никто не имеет больше прав на базовые человеческие ценности, чем другой. Однако те же центростремительные силы, что концентрируют богатство и власть на рынке и в обществе, действуют и в сфере медицины.

---

### 30. `p0775` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> The starting point should be to recognize that we don’t have a *healthcare* system — instead we have a *medical care* system. Furthermore, income for that medical care system is produced essentially by people who are alive and sick. Therefore only more sick people — not healthy ones — lead to more growth and income in that sector. With such an incentive scheme, that system has become remarkably adept at keeping sick people alive. Over 60% of total lifelong medical expenses are typically incurred in the last three months of a patient’s life; and emergency care is clearly a domain in which Western medicine excels.

**В озвучку попало:**

> Начать стоит с признания того, что у нас нет системы *здравоохранения*. У нас есть система *медицинской помощи*. Более того, доходы этой системы по сути формируются за счет живых, но больных людей. Следовательно, именно рост числа пациентов, а не здоровых граждан, ведет к росту доходов в этом секторе. При такой системе стимулов отрасль стала удивительно эффективной в поддержании жизни больных людей. Как правило, более шестидесяти процентов всех пожизненных медицинских расходов приходится на последние три месяца жизни пациента. И экстренная помощь — это та область, в которой западная медицина действительно преуспевает.

---

### 31. `p0877` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> While they are not focused on child care or elder care, Time Banks provide a system where care for children and elders can take place more easily. In fact, a high percentage of Time Banks find that child care is one of the things people are seeking when they join. The fact that the activities in Time Banks are officially tax-exempt (which means they do not count toward members’ income) also means that when people use services through a Time Bank, they do not put income-based government benefits at risk.

**В озвучку попало:**

> Хотя тайм-банки не специализируются исключительно на уходе за детьми или пожилыми людьми, они создают систему, в которой такая забота становится доступнее. На самом деле, многие люди присоединяются к тайм-банкам именно в поисках помощи с детьми. Деятельность тайм-банков официально освобождена от налогов, а значит, полученные услуги не считаются доходом и не ставят под угрозу получение государственных пособий.

---

### 32. `p0886` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> In order to address this rapidly rising problem, the Japanese have implemented several new time exchange currencies.⁹ In these systems, the hours that a volunteer spends helping older or handicapped persons with their daily routine are credited to that volunteer ’s *time account*. Time accounts are managed like a savings account, except that the unit of account is hours of service instead of Yen. Time account credits are also available to complement normal health insurance programs. One of these time exchange systems is run on a national level by the Sawayaka Foundation in Japan. It’s called the *Fureai Kippu* system and has a lot to teach us about how complementary currencies can address serious social issues.

**В озвучку попало:**

> Чтобы справиться с этой острой проблемой, японцы внедрили несколько новых валют, основанных на обмене временем. В этих системах часы, которые волонтер тратит на помощь пожилым или людям с инвалидностью, зачисляются на его «счет времени». Эти счета работают как обычные сберегательные, только вместо иен единицей накопления служат часы оказанных услуг. Кредиты со счетов времени также можно использовать как дополнение к программам медицинского страхования. Одной из таких национальных систем управляет фонд «Саваяка». Она называется «Фуреай Киппу» — «Билет заботливых отношений». Этот опыт многому может нас научить в плане того, как дополнительные валюты помогают решать серьезные социальные задачи.

---

### 33. `p0902` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> In the 1970s and 1980s, the government of Botswana started promoting trade among the villages in the Kalahari, and for the first time, money was introduced to the !Kung. This seemingly small change — the introduction of money — had an enormous impact on !Kung society and their social interactions. They began to use money to buy glass beads and other valuables, which they locked in new metal boxes in their homes. Within five years, people sought privacy rather than intimacy, and even the way they laid out their homes changed. No longer were doors open towards a common hearth; instead they faced away from the circle of homes. People started hoarding instead of depending on others, and the hunter-gatherer way of life that had shaped !Kung society over hundreds of generations gave way to totally different life patterns much closer to our own.¹

**В озвучку попало:**

> В семидесятых и восьмидесятых годах правительство Ботсваны начало поощрять торговлю между деревнями Калахари, и кунг впервые познакомились с деньгами. Это казалось незначительным изменением, но оно оказало колоссальное влияние на их общество и социальные связи. Люди начали использовать деньги для покупки стеклянных бус и других ценностей, которые теперь запирали в металлические сундуки в своих домах. Всего за пять лет стремление к близости сменилось тягой к уединению, изменилась даже планировка жилищ. Двери больше не смотрели на общий очаг, а были развернуты в противоположную сторону. Люди начали копить богатства вместо того, чтобы полагаться друг на друга. Образ жизни охотников-собирателей, формировавшийся сотни поколений, уступил место совершенно иным моделям, гораздо более близким к нашим собственным.

---

### 34. `p1024` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Two of the priority actions under the Governance goal could have been controversial, but didn’t run into any real opposition as the mayor moved them forward. Since these actions involved changing the city’s charter — the document that forms the constitution for the city — there were several legal protocols to follow, which also could have provided opponents with a place to stop them. Two of these were:

**В озвучку попало:**

> Два приоритетных действия в рамках цели по совершенствованию управления могли вызвать споры, но не встретили реального сопротивления, когда мэр начал их продвигать. Поскольку эти шаги требовали изменения городского устава — документа, который служит своего рода конституцией города, — пришлось соблюсти ряд юридических процедур. Это теоретически давало оппонентам возможность заблокировать инициативы. Вот эти два пункта:

---

### 35. `p1045` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> The Social Equity Investment Project does a lot through the coordinator working in the community to promote diversity. To do this, she works with a wide variety of community organizations to increase the representation in their leadership groups by people who are not traditionally in leadership positions — people of color, people who are physically challenged and people who have low incomes. Workshops are offered on subjects like “A Solution to Cultural Shifting,” and the coordinator supports projects run by Burlington’s Center for Community and Neighborhoods such as the Inclusive Community Initiative and the We All Belong Initiative.

**В озвучку попало:**

> Проект выполняет большой объём работы благодаря координатору, который взаимодействует с местным сообществом для продвижения идей разнообразия. Координатор сотрудничает с самыми разными организациями, помогая им привлекать к руководству людей, которые традиционно не занимали таких позиций: представителей этнических меньшинств, людей с ограниченными физическими возможностями и граждан с низким уровнем дохода. В рамках проекта проводятся семинары на такие темы, как «Решение проблемы культурных сдвигов». Также координатор поддерживает инициативы Центра по работе с сообществами и районами Берлингтона, включая программы «Инклюзивное сообщество» и «Мы все здесь свои».

---

### 36. `p1063` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> The Social Equity Investment Project, and all the goals and targets the city set for governance and social well-being, represent a significant contribution by the city to ongoing discussions about sustainability. Burlington was the first city to address issues of equity and justice in a planning project that otherwise would have been seen as having only an environmental and economic focus.

**В озвучку попало:**

> [thoughtful] Проект инвестиций в социальное равенство, как и все цели, которые город поставил перед собой в области управления и социального благополучия, стал значимым вкладом Берлингтона в дискуссию об устойчивом развитии. Берлингтон стал первым городом, который включил вопросы равенства и справедливости в проект планирования, который иначе рассматривался бы исключительно через призму экологии и экономики.

---

### 37. `p1132` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> In Figure 1, the feedback loops describe a common system archetype known as Success to the Successful. This pattern of behavior occurs in many places in society, including bright children in school getting more attention from teachers or people moving up the ladder within a corporation.

**В озвучку попало:**

> [serious] На схеме петли обратной связи описывают распространенный системный архетип, известный как «Успех приходит к успешным». Подобная модель поведения встречается во многих сферах жизни: например, когда способные ученики получают больше внимания от учителей или когда сотрудники продвигаются по карьерной лестнице внутри корпорации.

---

### 38. `p1150` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Developing the vision was a celebration of community participation and imagination! It was an adventure in exploring values, building on assets and incorporating citizens’ hopes and dreams for the next 100 years. Based upon the success of Imagine Chicago and other community movements around the world, imagineCALGARY reached out to Calgarians using a variety of strategies. Over 18,000 responded via:

**В озвучку попало:**

> Разработка концепции стала настоящим праздником участия и воображения! Это было приключение, в ходе которого исследовались ценности, оценивались ресурсы и собирались надежды и мечты граждан на ближайшие сто лет. Опираясь на успех проекта «Imagine Chicago» и других общественных движений по всему миру, инициатива «imagineCALGARY» использовала множество стратегий. Более восемнадцати тысяч человек откликнулись через:

---

### 39. `p1172` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> At the time of this writing, it is too early to say much about the implementation of the plan, although work has been done to institutionalize it into city government by creating a Sustainability Coordinator in the City Manager ’s office and to establish a formal organization outside of city government that will keep community efforts going. The new coordinator ’s job is intentionally low-key; the goal was not to develop a new department for sustainability, which has the unfortunate unintended consequence of allowing other departments to assume that the job is being taken care of without their involvement. The position will instead continue to integrate the work of the broad range of city departments and to hold their feet to the fire with respect to the targets that were set and refined by the City Council into a shorter term work plan for the city.

**В озвучку попало:**

> На момент написания этой книги еще рано судить о результатах реализации плана. Тем не менее, уже проделана работа по внедрению его принципов в структуру городского управления. В аппарате сити-менеджера появилась должность координатора по устойчивому развитию, а вне администрации была создана официальная организация для поддержки общественных инициатив. Работа нового координатора намеренно не афишируется. Цель заключалась в том, чтобы не создавать отдельный департамент по вопросам устойчивости. В противном случае другие подразделения могли бы решить, что эта задача их больше не касается. [thoughtful] Вместо этого новая должность призвана интегрировать работу всех городских департаментов и следить за тем, чтобы они выполняли целевые показатели, утвержденные городским советом в рамках краткосрочного плана развития.

---

### 40. `p1205` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> People were busy, some of the initial enthusiasm for the project had faded and the stakeholders hadn’t really taken ownership of the visioning process. The December meeting arrived, and the staff of the project were getting nervous that there wouldn’t be enough surveys to be credible as a statement by the people of the city about their values and aspirations.

**В озвучку попало:**

> Люди были заняты, первоначальный энтузиазм по поводу проекта угас, а заинтересованные стороны так и не взяли на себя ответственность за процесс формирования видения будущего. Наступил декабрь, время собрания, и сотрудники проекта начали нервничать. Они опасались, что собранных анкет не хватит, чтобы они могли считаться достоверным выражением ценностей и стремлений горожан.

---

### 41. `p1215` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> When interviewed by a local cable station during one of the events sponsored by the project, the City Manager described how the stakeholder training had changed the tenor of dialogue at City Council meetings. She said that while a take-no-prisoners approach had been the rule in the past, the level of respectful listening and dialogue “changed the political culture of the city.”¹⁰

**В озвучку попало:**

> Давая интервью местному кабельному каналу во время одного из мероприятий, сити-менеджер рассказала, как обучение заинтересованных сторон изменило тон дискуссий на заседаниях городского совета. Она отметила, что, хотя раньше нормой был агрессивный подход, теперь уровень уважительного слушания и диалога «изменил политическую культуру города».

---

### 42. `p1227` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Yet over the past five years, Gwendolyn had noticed that the city would benefit from a different approach to long-range planning. A proposal for housing in an open field to the east of the city had created an enormous public outcry as the neighborhood around the field clamored to save the open space for parkland. To stop the proposed development, interim zoning was adopted and the master plan was amended — all symptoms of an underlying planning process that might not reflect the aspirations of the people. As a resident of the city since 2004, Gwendolyn hadn’t been aware of any real outreach on the part of the planning office or the city to get residents involved. So she applied for the job and started work as the Director of Planning and Community Development in Montpelier in November of 2006.

**В озвучку попало:**

> Тем не менее за последние пять лет Гвендолин заметила, что городу пошел бы на пользу иной подход к долгосрочному планированию. Предложение о застройке открытого поля к востоку от города вызвало огромный общественный резонанс: жители окрестных районов требовали сохранить эту землю как парковую зону. Чтобы остановить строительство, пришлось вводить временное зонирование и вносить поправки в генеральный план. Все это было симптомами того, что существующий процесс планирования не отражает чаяний людей. Как жительница города с 2004 года, Гвендолин не видела реальных попыток со стороны мэрии или отдела планирования вовлечь горожан в диалог. Поэтому она подала заявку на вакансию и в ноябре 2006 года приступила к работе в качестве директора по планированию и развитию сообщества в Монпелье.

---

### 43. `p1229` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> From the beginning, enVision Montpelier was framed as a learning process rather than a traditional planning process, a new approach that resulted from reflection about the work Gwendolyn had done in the other cities and towns where she had worked. Rapid change in the 21st century is already the rule, and so taking the traditional approach to planning — relying on experts to provide short-term strategies based on what worked in the past — will be increasingly irrelevant as the level of chaotic change increases. Old solutions won’t work in the new world we find ourselves in, and so the most important dimension of any sustainability planning process is to make all the stakeholders conscious of learning. Adults don’t particularly like to be learners — we like to be knowers and teachers. Taking a learning posture to city planning is much more challenging than it might seem on the surface — city planning has traditionally been left to experts.

**В озвучку попало:**

> С самого начала «enVision Montpelier» задумывался как процесс обучения, а не как традиционное планирование. Этот подход стал результатом осмысления работы, которую Гвендолин вела в других городах. В двадцать первом веке стремительные перемены стали нормой, поэтому традиционный подход, полагающийся на экспертов и краткосрочные стратегии, основанные на прошлом опыте, будет становиться все менее актуальным по мере роста хаоса. Старые решения не работают в новом мире, в котором мы оказались. Поэтому важнейшее измерение любого процесса планирования устойчивого развития — сделать всех участников процесса осознанными учениками. Взрослые не очень любят учиться: мы предпочитаем быть знатоками и учителями. Принять позицию ученика в городском планировании гораздо сложнее, чем кажется на первый взгляд, ведь традиционно это дело оставляли экспертам.

---

### 44. `p1233` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> The learning objectives each committee developed framed the early part of their work, as they identified different ways to learn what they needed to know about the assets and issues in the Social Systems in Montpelier, for example, and to set goals for the different needs that were identified. The committees invited professionals to come to their meetings and talk about their work; they read material that was developed for them by the VISTA volunteers; they sponsored community forums on topics such as how the faith community could work together or what the democratic town meeting tradition was like in Switzerland.

**В озвучку попало:**

> [thoughtful] Учебные задачи, которые разработал каждый комитет, определили начальный этап их работы. Участники искали способы лучше понять сильные стороны и проблемы социальной сферы Монпелье, а также учились ставить цели для решения выявленных потребностей. Комитеты приглашали экспертов на свои встречи, чтобы обсудить их работу. Они изучали материалы, подготовленные волонтерами программы VISTA, и проводили общественные форумы. На таких встречах обсуждали, например, как религиозные общины могут сотрудничать друг с другом или как устроена традиция демократических городских собраний в Швейцарии.

---

### 45. `p1253` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> If cities are going to play a role in wealth creation for their residents, establishing the policy framework that supports this role and clearly identifying strategies that incorporate complementary currencies sets the stage for successful city action. The planning processes described in this chapter obviously address more than the issues complementary currencies can help address, but these processes are very important — they create a context where innovative strategies which rely heavily on collective action are possible.

**В озвучку попало:**

> Если города стремятся участвовать в создании благосостояния для своих жителей, им необходимо заложить основу в виде политики, поддерживающей эту роль, и четко определить стратегии с использованием дополнительных валют. Это создает условия для успешных действий. Описанные в этой главе процессы планирования охватывают гораздо больше вопросов, чем те, что решаются только с помощью дополнительных валют. Однако эти процессы крайне важны: они формируют среду, в которой становятся возможными инновационные стратегии, опирающиеся на коллективные действия.

---

### 46. `p1267` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> Furthermore, anybody who has taken a course in economic theory is convinced that money is a passive medium that simply facilitates exchanges that would have happened otherwise anyway. In other words, the implicit hypothesis underlying the entire economic theory from Adam Smith to today is that different kinds of money wouldn’t encourage different types of exchanges, don’t affect the relationships among their users or motivate different types of investments. In short, for a conventional economist, using another type of money doesn’t make any sense. That is of course true when one compares the use of different national currencies: they are all generated through bank-debt with interest, i.e., they are all of the same type. But there is plenty of empirical evidence from the thousands of complementary currency systems in existence today that using different types of currencies does encourage different kinds of exchanges, and/or significantly changes the relationships among their users.¹ Many complementary currency systems are in fact introduced with the specific aim of changing relationships in a community, and these systems have demonstrated such behavior changes in practice as well.

**В озвучку попало:**

> Более того, любого, кто изучал экономическую теорию, убеждают в том, что деньги — это пассивное средство, которое лишь облегчает обмен, произошедший бы в любом случае. Иными словами, негласная гипотеза, лежащая в основе всей экономической науки от Адама Смита до наших дней, гласит: разные виды денег не могут стимулировать разные типы обмена, не влияют на отношения между пользователями и не меняют мотивацию инвестиций. Короче говоря, для традиционного экономиста использование других видов денег не имеет смысла. Это, конечно, верно, если сравнивать разные национальные валюты: все они создаются через банковский долг под процент, то есть по сути они одного типа. Но существует множество эмпирических доказательств, полученных на примере тысяч существующих сегодня систем дополнительных валют, которые показывают: использование разных типов денег действительно поощряет иные виды обмена и существенно меняет отношения между людьми. Многие такие системы внедряются именно с целью изменения общественных связей, и на практике они доказали свою способность менять поведение людей.

---

### 47. `p1268` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> There are two ways to deal with this blind spot that afflicts our collective perception of money. The first way is to deal with it explicitly by providing empirical evidence; and the second is to bypass this entire issue by selective use of vocabulary. There are two classical arguments to justify the existing monopoly of bank-debt money. The first is efficiency; and the second is that complementary currencies have remained invariably marginal compared to the use of “real” money.

**В озвучку попало:**

> Существует два способа справиться с этим «слепым пятном» в нашем коллективном восприятии денег. Первый — открыто признать проблему, опираясь на эмпирические данные. Второй — обойти этот вопрос, избирательно используя терминологию. Есть два классических аргумента в пользу существующей монополии банковских денег. Первый — эффективность, а второй — утверждение, что дополнительные валюты всегда оставались маргинальными по сравнению с «настоящими» деньгами.

---

### 48. `p1293` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Perhaps the next time we visit Reykjavik, they will have recreated their own democratic ecology of currencies, instead of the monoculture/monopoly of bank-debt money that has brought them so much hardship. To reduce unemployment and revalue all of their residents, the city may have introduced a mandatory time contribution, not paid in bank-debt money, but rather using an electronic time currency similar to the Japanese *Fureai Kippu*, as a way to simultaneously reduce taxes and give people work to do. A time currency reduces taxes because people spend their time doing things government pays money for — education, senior care, child care, healthcare, keeping the parks and the streets clean, community justice systems where mediation reduces the load in the courts. Time currency reduces unemployment because not everyone can spend time on these things. People who are willing and able to work above and beyond the time requirement could be paid for their time by those who are not. An e-Bay type electronic market could emerge where the city’s time currency could be sold for bank-debt money or whatever else people are interested in exchanging.

**В озвучку попало:**

> Возможно, когда мы приедем в Рейкьявик в следующий раз, они уже воссоздадут свою собственную демократическую экологию валют вместо монокультуры банковских долговых денег, которые принесли им столько бед. Чтобы сократить безработицу и повысить ценность вклада каждого жителя, город мог бы ввести обязательный трудовой взнос — не в банковских долговых деньгах, а в электронной временной валюте, похожей на японские «Фуреай Киппу». Это позволило бы одновременно снизить налоги и обеспечить людей работой. Временная валюта снижает налоговую нагрузку, потому что люди тратят свое время на то, за что обычно платит государство: образование, уход за пожилыми, присмотр за детьми, здравоохранение, уборку парков и улиц, а также системы общественного правосудия, где медиация разгружает суды. Временная валюта снижает безработицу, потому что не каждый может посвящать этому всё свое время. Люди, желающие и способные работать сверх обязательной нормы, могли бы получать оплату за свое время от тех, кто этого сделать не может. Мог бы возникнуть электронный рынок, подобный eBay, где городскую временную валюту можно было бы продать за банковские деньги или обменять на что-то другое.

---

### 49. `p1325` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Remember, the starting point for complementary currencies is to meet needs that remain unfulfilled after transactions facilitated with conventional money have taken place. Similarly, unused resources are those that haven’t been used in economic transactions mediated by conventional money.

**В озвучку попало:**

> Помните: отправная точка для введения дополнительных валют — это решение тех задач, которые остаются невыполненными после всех операций с обычными деньгами. Точно так же и неиспользованные ресурсы — это те, что не были задействованы в экономических сделках с использованием традиционной валюты.

---

### 50. `p1360` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> There is a long tradition of more or less formal but small scale local babysitting groups constituted by families who in turn take care of each other ’s children. A large, national-scale Internet-based system is being designed now in Holland, under the name of “Care Miles.” Its aim is to help the 2.3 million families who have trouble finding access to care centers, particularly for the 0-4 year olds.⁶ Community Building Community healing and rebuilding are the most popular reasons for starting complementary currency systems in neighborhoods where there are no major unemployment or economic stress situations. Various designs have been used for such purpose, including Time Bank systems, LETS and Ithaca HOURS. The Balinese time currency described in Chapter 4 could also be considered a well-established system of this nature, operational for more than 1,000 years.

**В озвучку попало:**

> [thoughtful] Существует давняя традиция создания небольших, более или менее формальных групп взаимопомощи, где семьи по очереди присматривают за детьми друг друга. Сейчас в Нидерландах разрабатывается масштабная общенациональная интернет-система под названием «Care Miles». Её цель — помочь двум миллионам тремстам тысячам семей, которым трудно найти доступ к детским учреждениям, особенно для малышей в возрасте до четырех лет. Укрепление сообщества и его восстановление — самые популярные причины для запуска дополнительных валютных систем в районах, где нет серьезной безработицы или экономических проблем. Для этих целей используются разные подходы, включая системы тайм-банков, местные системы взаимного обмена и «Итака-часы». Балийскую валюту времени, описанную в четвертой главе, также можно считать хорошо отлаженной системой такого рода, которая успешно работает уже более тысячи лет.

---

### 51. `p1403` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> The support(s) used for issuing or handling a currency is one of the easiest features to grasp — we are familiar with the various forms that currency comes in — notes, coins and plastic cards, given that conventional money uses practically all of them today. These supports fall into the following types:

**В озвучку попало:**

> [thoughtful] Носители, которые используются для выпуска или обращения валюты — это одна из самых простых для понимания характеристик. Мы хорошо знакомы с различными формами денег: это банкноты, монеты и пластиковые карты, ведь современные официальные деньги используют практически все эти виды. Такие носители можно разделить на следующие типы:

---

### 52. `p1406` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> Paper and Coins Paper and coins are the most familiar form of money today. Paper is the most popular form for contemporary complementary currencies because it is both easy to carry and handle and comparatively cheap to produce (e.g., Ithaca HOURS, WAT bills of exchange, LETS account booklets).

**В озвучку попало:**

> Бумажные деньги и монеты — самая привычная для нас форма денег. Бумага является наиболее популярным носителем для современных дополнительных валют, поскольку её легко носить с собой, она удобна в обращении и относительно дешева в производстве. Примеры тому — часы Итаки, векселя WAT или расчетные книжки систем LETS.

---

### 53. `p1410` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> When several media are used for the same currency, this provides maximum flexibility. The historical evolution of conventional money has traced a logical sequence towards more convenience: currency started with physical commodity money (such as precious metal coins), but now it is more convenient to handle paper receipts with promises to pay that physical commodity (“I will pay to the bearer the sum of one Pound Sterling” is still written on the English currency bills). And of course, if the appropriate technological infrastructure is available, electronic bits are even cheaper to move around than paper currency. The same currency can and often does take different forms depending on the media that supports it. National currency takes many forms: electronic bits, paper or coins.

**В озвучку попало:**

> [thoughtful] Использование нескольких носителей для одной валюты обеспечивает максимальную гибкость. Историческая эволюция обычных денег шла по пути поиска удобства. Сначала это были физические товары, например, монеты из драгоценных металлов. Затем стало удобнее использовать бумажные расписки с обязательством выплатить этот товар. Даже сегодня на английских фунтах стерлингов написано: «Я выплачу предъявителю сумму в один фунт». Разумеется, при наличии подходящей инфраструктуры электронные данные передавать еще дешевле, чем бумажные деньги. Одна и та же валюта может принимать разные формы в зависимости от того, на чем она базируется. Национальная валюта сегодня существует и в виде электронных записей, и в виде бумажных купюр или монет.

---

### 54. `p1435` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Demurrage Charged Currencies The opposite of an interest bearing currency is a demurrage-charged currency. Demurrage is a time related charge on outstanding balances of a currency. It operates exactly like a negative interest rate and is used as a disincentive to hoard the currency. John Maynard Keynes, Silvio Gesell, Irving Fisher and Dieter Suhr provided a strong theoretical foundation for this approach, and it was extensively implemented in the form of *stamp scrip* in the 1930s. Today, the most successful grassroots complementary currency in Japan, the Peanuts, charges a demurrage of 1% per month.

**В озвучку попало:**

> Валюты с демерреджем. Прямая противоположность процентным валютам — это валюты с демерреджем. Демерредж — это плата за хранение валюты, размер которой зависит от времени. По сути, это отрицательная процентная ставка, которая служит стимулом не накапливать деньги, а пускать их в оборот. Джон Мейнард Кейнс, Сильвио Гезель, Ирвинг Фишер и Дитер Зур заложили мощную теоретическую базу для этого подхода. В тридцатые годы двадцатого века он широко применялся в виде так называемых «штемпельных денег». Сегодня самая успешная низовая дополнительная валюта в Японии, «Арахис», взимает демерредж в размере одного процента в месяц.

---

### 55. `p1439` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> The advantage of interest bearing currencies is that they provide an income to those who create the currency (called *seigniorage*). Its disadvantage is that it implies a systematic money transfer from people who don’t have money to those who do, so that it tends to concentrate wealth. It also gives an incentive to save in the form of currency as opposed to real assets. Finally, it provides a systematic incentive to think only short-term, as income generated in the distant future is discounted to irrelevance with positive interest-rate currencies.

**В озвучку попало:**

> [thoughtful] Преимущество процентных валют в том, что они приносят доход тем, кто их создает. Это называется сеньоражем. Недостаток же заключается в систематическом перераспределении средств от тех, у кого денег нет, к тем, у кого они есть, что ведет к концентрации богатства. Кроме того, это стимулирует сбережения именно в валюте, а не в реальных активах. Наконец, такие валюты заставляют мыслить краткосрочно, поскольку доходы в далеком будущем обесцениваются из-за положительной процентной ставки.

---

### 56. `p1468` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Mutual credit has as significant advantage: the quantity of money created by definition always perfectly matches need. There are also no risks of inflation in mutual credit systems. By contrast, overissuing is the biggest risk run by currencies that are created by borrowing without collateral or by central issue. It is important with these latter models to cautiously control the quantity of currency issued, otherwise its depreciation and loss of credibility is a predictable outcome.

**В озвучку попало:**

> [serious] У системы взаимного кредита есть существенное преимущество: количество создаваемых денег по определению всегда точно соответствует потребностям. В таких системах нет риска инфляции. Напротив, чрезмерная эмиссия — это главный риск для валют, создаваемых путем беззалогового заимствования или централизованного выпуска. В этих моделях важно осторожно контролировать объем выпускаемой валюты. В противном случае ее обесценивание и потеря доверия становятся предсказуемым результатом.

---

### 57. `p1474` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> The first option is not to recover any of the costs. For the complementary currency component of the costs, most mutual credit systems simply open an account for “general overhead,” people doing work for the system are credited and this overhead account is debited.

**В озвучку попало:**

> [thoughtful] Первый вариант — не возмещать расходы вовсе. Что касается затрат в дополнительной валюте, большинство систем взаимного кредита просто открывают счет «общих накладных расходов». Людям, выполняющим работу для системы, начисляются средства, а с этого счета они списываются.

---

### 58. `p1515` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> The LETS program was established around 1983, introducing the *green* *dollar* (the LETS currency). This system allowed people to exchange goods and services with one another even when they didn’t have access a lot of official Canadian dollars. The LETS network allowed members to participate in the economy without needing an employer or having money to spend. An additional positive aspect of LETS in Courtenay was that the use of green dollars freed up more Canadian dollars for other uses. It was also an efficient and inexpensive way for local businesses to advertise, since participating businesses were listed in a local directory.

**В озвучку попало:**

> Программа LETS была запущена около 1983 года. Она ввела в обращение «зеленые доллары» — внутреннюю валюту системы. Это позволило людям обмениваться товарами и услугами, даже если у них не было доступа к официальным канадским долларам. Сеть LETS дала возможность участвовать в экономике без необходимости быть наемным работником или иметь наличные. Еще одним плюсом стало то, что использование «зеленых долларов» высвобождало реальные канадские деньги для других нужд. Кроме того, для местного бизнеса это стало эффективным и недорогим способом рекламы, так как всех участников вносили в общий справочник.

---

### 59. `p1546` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The Guide is based on the idea that we can satisfy our common human needs by building on our strengths, intervening at the system level and integrating all the different parts of community life into a whole package, rather than trying to tinker with different problems in isolation.

**В озвучку попало:**

> В основе этого руководства лежит идея о том, что мы можем удовлетворить общие человеческие потребности, опираясь на наши сильные стороны. Важно воздействовать на систему в целом и объединять все сферы жизни сообщества в единый комплекс, а не пытаться решать отдельные проблемы изолированно друг от друга.

---

### 60. `p1547` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> The principles and activities outlined in *LASER* are relevant whether you live in a rural village in Afghanistan or a neighborhood in a modern western city. The details will obviously differ, but the broad opportunities exist everywhere. All it takes is you. *LASER* describes how you can take control of your own future and begin to create the sort of economy that will bring real jobs, real prosperity and a high quality of life to you and your family.

**В озвучку попало:**

> Принципы и методы, описанные в LASER, актуальны везде: живете ли вы в сельской деревне в Афганистане или в районе современного западного мегаполиса. Детали, конечно, будут различаться, но широкие возможности существуют повсюду. Все, что нужно — это вы сами. LASER рассказывает, как взять контроль над собственным будущим в свои руки и начать создавать экономику, которая принесет реальные рабочие места, процветание и высокое качество жизни вам и вашей семье.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p1124` — длина озвучки / длина оригинала: 0.64; классы правки: —

**Исходный абзац:**

> The beginner level training in systems thinking was given to the Round Table and working group participants. At this level, participants needed to understand that systems dynamics was part of the methodology being used, and if systems diagrams were presented to them by the staff or consultants, they needed to understand the diagrams. If they had more understanding than this — and some of them did — it was fine, but the majority of them would not. Gwendolyn provided some of the training to this group, but the city also invited in local experts to demonstrate why systems dynamics were important — one of the first Round Table meetings featured a speaker from a local institute that made connections through a discussion of locally grown food.

**В озвучку попало:**

> Начальный уровень подготовки прошли участники «Круглого стола» и рабочих групп. Им нужно было понимать, что системная динамика — часть используемой методологии, и уметь читать диаграммы, если их представят сотрудники или консультанты. Гвендолин проводила часть занятий, но город также приглашал местных экспертов. Например, на одной из первых встреч выступил специалист из местного института, который объяснил важность системного подхода на примере производства продуктов питания.

---

### 2. `p1126` — длина озвучки / длина оригинала: 0.67; классы правки: —

**Исходный абзац:**

> Finally, the advanced level training was provided to the core staff of the imagineCalgary team. For this group, it was important that they be able to use an understanding of systems to both describe the existing situation and to identify possible interventions that could be made to improve things. This team was provided a lot of material on systems archetypes, and they used the different archetypes to analyze trends over time and describe the causal patterns for different situations in Calgary.² Then they were also given instruction on how to identify leverage points in the systems that were causing problems. Leverage points are a seductive idea for planners — they offer the hope that small changes can lead to big results. The challenge of leverage is that often the “small” changes needed are quite countercultural or expensive, even if in the larger scheme of things they aren’t significant.

**В озвучку попало:**

> Продвинутый уровень обучения прошли ключевые сотрудники команды «imagine-CALGARY». Им было важно научиться использовать системный подход, чтобы описывать текущую ситуацию и находить способы её улучшения. Команда изучила системные архетипы для анализа тенденций и описания причинно-следственных связей в жизни города. [short pause] Также их учили находить «рычаги воздействия». Это заманчивая идея для планировщиков: она дает надежду, что малые изменения приведут к большим результатам. Сложность в том, что часто такие «малые» изменения требуют больших затрат или идут вразрез с общепринятыми нормами.

---

### 3. `p1125` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> The intermediate level training was given to the consulting team that Calgary hired to manage the Working Groups. Two facilitators were assigned to each group, one to lead the discussion and one to keep a record of their work. In addition, the team members from the planning office also attended each meeting. At this level, the facilitators and record keepers needed to be able to not only understand the diagrams and the logic of systems dynamics that was presented to the group, but they needed to be able to explain it to other people. The workshops for this group were designed as more hands-on training, so they worked with different systems diagrams and were given more practice applying the ideas to real life situations.

**В озвучку попало:**

> Средний уровень обучения предназначался для команды консультантов, нанятых Калгари для управления рабочими группами. В каждую группу назначили двух фасилитаторов: один вел дискуссию, другой фиксировал работу. Также на встречах присутствовали сотрудники планового отдела. Фасилитаторы и секретари должны были не только понимать логику системной динамики, но и уметь объяснять её другим. Семинары для них были более практическими: они работали с разными диаграммами и учились применять эти идеи в реальных ситуациях.

---

### 4. `p0956` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> The light bulb went on, and the ideas for a local food currency started to gel. If there was underutilized food storage capacity in the region and if food storage in general was something we wanted to foster to develop better local food security, then this might provide the basis for a currency.

**В озвучку попало:**

> Идея сразу стала понятной и начала обретать форму. Если в регионе есть неиспользуемые склады, а развитие системы хранения важно для продовольственной безопасности, то именно это может стать основой для валюты.

---

### 5. `p0990` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> These cities sent a message to the public that city planning is fun and interesting, and in all cases, people responded by getting involved, either by simply filling out the visioning surveys or by joining stakeholder groups. Some took their interests a step further and stepped up to serve on the City Council or Planning Commissions.

**В озвучку попало:**

> Эти города дали понять жителям: городское планирование — это интересно. И люди откликнулись: они заполняли анкеты и присоединялись к рабочим группам. Некоторые пошли дальше и стали работать в городском совете или комиссиях по планированию.

---

### 6. `p0818` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> We know how frequent flyer miles can successfully encourage particular customer behavior patterns, i.e., loyalty to a particular airline alliance. Now imagine a complementary currency — let’s call them Wellness Tokens — that would encourage people to take on healthy habits and practices. For example, one hour of exercise at a gym would earn one Wellness Token; or specific preventive treatments could similarly be encouraged with Wellness Tokens.

**В озвучку попало:**

> Мы знаем, как эффективно работают бонусные мили авиакомпаний, поощряющие лояльность клиентов. Представьте себе дополнительную валюту — назовем ее «токены здоровья», — которая побуждала бы людей вести здоровый образ жизни. Например, час тренировки в спортзале или прохождение профилактического осмотра могли бы приносить такие токены.

---

### 7. `p1127` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> The training helped make a challenging project — developing a 100 year plan for a city — something that people from many different disciplines, from all political stripes could understand. It established a common language to use, defined a set of goals and created a map to follow through a long series of meetings where controversial issues would be discussed. In many ways, the training and early project organization created a safe space to discuss difficult issues, and the new language of systems also provided some tools to diagnose intractable problems in new ways.

**В озвучку попало:**

> Обучение помогло сделать сложный проект — разработку столетнего плана для города — понятным для людей самых разных профессий и политических взглядов. Оно создало общий язык, определило цели и дало карту для длинной серии встреч, где обсуждались спорные вопросы. Во многом обучение и ранняя организация проекта создали безопасное пространство для дискуссий, а новый системный язык дал инструменты для диагностики застарелых проблем.

---

### 8. `p0832` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> For there to be any hope of the adoption of new systems, like Wellness Tokens, where the incentives work to reward wellness instead of sickness, we need to strengthen the industries that are more profitable when people are well. Fortunately, this includes the vast majority of businesses in the country who suffer when people are out of work, or when their insurance premiums increase because of higher risk employees.

**В озвучку попало:**

> Чтобы новые системы, такие как Велнес-токены, получили распространение, нам нужно поощрять индустрии, которые выигрывают от здоровья людей. К счастью, к ним относится большинство компаний. Ведь бизнес несет убытки, когда сотрудники болеют или когда растут страховые взносы из-за высоких рисков для здоровья персонала.

---

### 9. `p0883` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> At the *specialized* level, you make a higher commitment of time and money each month — eight hours of time and $15 per month for each service cluster you need. This level helps members have access to preventive care services and more highly specialized skills, like those of electricians and carpenters. The preventive services include things like massage therapy, chiropractic care, exercise and yoga classes, herbal therapy and other alternative and complementary healthcare services. The access to these services attracts a broad spectrum of the community to the system and provides the Care Bank with a solid foundation of people’s time to continue to offer the assisted level of care to others.

**В озвучку попало:**

> На специализированном уровне обязательства выше: восемь часов времени и 15 долларов в месяц за каждую группу услуг. Этот уровень дает доступ к профилактике и помощи узких специалистов, таких как электрики или плотники. Профилактические услуги включают массаж, мануальную терапию, занятия йогой, фитотерапию и другие методы дополнительной медицины. Доступ к таким услугам привлекает в систему самых разных людей и создает прочную основу, позволяя банку заботы продолжать оказывать помощь другим участникам на вспомогательном уровне.

---

### 10. `p0619` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> As the recipient of the money and time in the Art Token account, you would engage in a contract for the work. Each contract could reflect the level of mentoring and cost required, and you, the student, would need to contribute as well — either through the more traditional ways of raising funds (finding sponsors, doing a fundraising event, selling things) or by earning Tokens by undertaking activities supporting the arts that normally cause the city, the foundation or the arts organizations in the community to incur conventional money costs. Everything from ushering at the theater to mentoring younger children might qualify as a certified activity that earns you the Tokens you need for your dream to be realized.

**В озвучку попало:**

> Получив средства и время на счет арт-токенов, вы заключаете договор на выполнение работы. Каждый контракт учитывает уровень наставничества и необходимые затраты. Вы, как студент, тоже должны внести свой вклад: либо традиционными способами сбора средств, такими как поиск спонсоров или благотворительные мероприятия, либо зарабатывая токены через поддержку искусства. Например, работа капельдинером в театре или наставничество для младших детей могут стать сертифицированной деятельностью, приносящей токены, необходимые для реализации вашей мечты.

---

### 11. `p0621` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> If a city makes it mandatory for everyone to pay some contribution every year in a form of complementary currency or accepts partial payment in complementary currencies for some regular taxes and fees, the demand for that currency will significantly increase and therefore obtain a value that it has not had previously. Remember, the main systemic reason we universally accept privately created bank-debt dollars right now is that they are the *only* legal form by which we can pay our taxes.

**В озвучку попало:**

> [thoughtful] Если город сделает обязательным ежегодный взнос в такой валюте или разрешит частично оплачивать ею налоги и сборы, спрос на нее значительно вырастет, и она обретет ценность, которой раньше не имела. Помните: главная системная причина, по которой мы все принимаем частные банковские доллары, заключается в том, что это единственный законный способ оплаты налогов.

---

### 12. `p0162` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Today, very few cities have the integrated long-term plans and policies necessary to pursue the types of implementation activities that will move a community in a more sustainable direction. Often the policy context is fragmented, short-term and internally contradictory. The city might have a master plan or a comprehensive plan that addresses infrastructure, land use and economic development over the next three to five years. If city staff and/or the city council are oriented toward integration, the capital plan might actually reflect the goals of the master plan, but all too often a city’s capital plan is a long list of projects that reflect departmental or council imperatives in isolation from each other, without a sense of how they relate to overarching long-term goals such as climate stabilization and poverty eradication. Cities almost never address some of the important underlying drivers for the policy context — a sense of shared values, social and human development issues and governance structures.

**В озвучку попало:**

> Сегодня немногие города обладают комплексными долгосрочными планами, которые позволили бы двигаться к устойчивому развитию. Часто городская политика раздроблена, ориентирована на краткосрочные цели и полна внутренних противоречий. У города может быть генеральный план развития инфраструктуры или экономики на ближайшие три-пять лет. Если администрация и городской совет стремятся к единству, то бюджетные планы могут отражать цели этого генплана. Однако чаще всего бюджет — это просто список разрозненных проектов. В них нет понимания того, как эти проекты связаны с глобальными задачами, такими как стабилизация климата или борьба с бедностью. Города почти никогда не работают с фундаментальными основами: общими ценностями, вопросами социального развития и принципами управления.

---

### 13. `p0979` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Local Agenda 21 was the local government response to the Earth Summit in Rio, which culminated in Agenda 21, a program for the planet to achieve environmental sustainability and community development. While its scope was originally broader than the environmental agenda, as it has been implemented over the past 20 years, the programs that have tended to be implemented as Local Agenda 21 in cities are local recycling campaigns and other environmental projects. Local Agenda 21 offers few tools for systematically considering the economy, the governance systems or the social development of a community.

**В озвучку попало:**

> «Повестка дня на 21 век» стала ответом местных властей на «Саммит Земли» в Рио-де-Жанейро. Это была глобальная программа по достижению экологической устойчивости и развитию сообществ. Хотя изначально её масштаб был шире, за последние двадцать лет в городах она чаще всего сводилась к локальным акциям по переработке отходов и другим экологическим проектам. В ней практически нет инструментов для системного анализа экономики, управления или социального развития общества.

---

### 14. `p1188` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The first group of stakeholders met for the training on a sunny day in the spring of 2005. The local bank, which had a meeting room that offered a beautiful view of the Hudson River, made the training space available — it was to become the main meeting room for the stakeholders for the entire process. There were about 50 people there, representing everyone from the local police department to the leaders of a local group of street poets and rappers who were known for being vocal opponents of city policies.

**В озвучку попало:**

> Первая группа собралась на тренинг солнечным весенним днём 2005 года. Местный банк предоставил свой конференц-зал с прекрасным видом на реку Гудзон. Это помещение стало основным местом встреч для участников на протяжении всего проекта. На встречу пришли около 50 человек: от сотрудников местной полиции до лидеров группы уличных поэтов и рэперов, известных своей резкой критикой городской политики.

---

### 15. `p0543` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> A form of education that systematically marginalizes the majority of the population can be seen in this light as a trend that will lead to our collective destruction if it is not reversed. Further, if those who do manage to navigate the barriers to learning are saddled with debts that prevent them from choosing the kind of creative endeavors that would utilize their knowledge to its fullest, this also works against our future.

**В озвучку попало:**

> [thoughtful] Форма образования, которая систематически маргинализирует большинство населения, — это тенденция, ведущая к коллективному краху, если её не изменить. Более того, если те, кому удаётся преодолеть барьеры на пути к знаниям, обременены долгами, мешающими им выбирать творческие пути, это также работает против нашего будущего.

---

### 16. `p1123` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Three levels emerged — the advanced, intermediate and beginner level — that guided the content of the training that was offered. Systems dynamics is a vast subject area, with many possible schools of thought ranging from what is characterized as hard systems dynamics (the world of computer modelers and mathematical formulas) to soft systems thinking (where diagrams and stories are used to convey the ideas and hard data is not used). Calgary was unusual insofar as it already was using hard systems models to manage its traffic planning, so they had experts on staff. The imagineCALGARY project, on the other hand, was primarily using soft systems thinking, where causal loop diagrams were used to convey the interrelationship of different variables to each other both within and between city systems.

**В озвучку попало:**

> В итоге выделили три уровня: начальный, средний и продвинутый. Системная динамика — обширная область. Она варьируется от «жесткой» системной динамики, где правят компьютерные модели и математические формулы, до «мягкого» системного мышления, использующего диаграммы и истории вместо сухих данных. Калгари был необычным городом, так как там уже использовали жесткие модели для планирования дорожного движения, и в штате были соответствующие эксперты. Проект же «imagine-CALGARY» в основном опирался на мягкое системное мышление, где причинно-следственные диаграммы помогали показать взаимосвязь переменных внутри городских систем.

---

### 17. `p1128` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> For example, some of the more difficult issues in Calgary and in other cities are those associated with economics and livelihoods, since any discussion about poverty and wealth can immediately turn into a politically charged debate. Yet there are systemic patterns of behavior within the economy that can be described with systems diagrams to give participants a new way of looking at a story which otherwise might be layered with ideological misinformation. The staff and working group on the economy in Calgary came up with a diagram to describe a problematic pattern that leads to a high level of economic inequity; this diagram also opened up a good discussion about ways in which different interventions might help reduce the resulting systematic impoverishment.

**В озвучку попало:**

> Например, одни из самых сложных тем в Калгари, как и в других городах, связаны с экономикой и средствами к существованию, ведь любой разговор о бедности и богатстве может быстро перерасти в политический спор. Однако существуют системные модели поведения, которые можно описать диаграммами. Это дает участникам новый взгляд на ситуацию, свободный от идеологических искажений. Сотрудники и рабочая группа по экономике в Калгари создали диаграмму, описывающую закономерности, ведущие к экономическому неравенству. Это открыло дискуссию о том, какие меры могут помочь уменьшить систематическое обнищание.

---

### 18. `p0273` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The external factors that influence the outcome of any business venture are the demand for the product, competition for sales of the same or similar products, the costs of production, tax rates and the cost of money. Most of these cost factors are directly related to the product, and need to be considered in the overall business plan when determining if the venture will be profitable.

**В озвучку попало:**

> На результат любого бизнес-проекта влияют внешние факторы: спрос на продукт, конкуренция, издержки производства, налоговые ставки и стоимость денег. Большинство этих факторов напрямую связаны с самим продуктом. Их необходимо учитывать в общем бизнес-плане, чтобы понять, будет ли предприятие прибыльным.

---

### 19. `p0248` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> To start at the most basic level, the definition of a system is, according to the Merriam-Webster dictionary: “a regularly interacting or interdependent group of items forming a unified whole.”¹⁰ In a car, these are all the components, and the unified whole that is formed is greater than the sum of individual parts. If you lined up the wheels, the engine, the axles, the steering wheel, the windshield, the seats, the body, the mirrors and the gauges along the floor of your garage, it would just be a large pile of stuff. But once all the parts are working together, the car can roll out of the driveway and down the street.

**В озвучку попало:**

> На самом базовом уровне, согласно словарю, система — это группа регулярно взаимодействующих или взаимозависимых элементов, образующих единое целое. В автомобиле это все его компоненты, и это единое целое гораздо больше, чем просто сумма отдельных частей. Если вы разложите на полу в гараже колеса, двигатель, оси, руль, лобовое стекло, сиденья, кузов, зеркала и приборы, это будет просто груда железа. Но когда все детали работают вместе, машина может выехать из гаража и отправиться в путь.

---

### 20. `p0958` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Several people who had attended the Food Systems Council meeting kept talking about the possibilities afterward. Another recurring theme that emerged was the need farmers have to understand their markets and to have dedicated customers in advance of their season every year. One farmer on the committee thought it would be a good idea to get people together to figure out how to organize a buying co-op, so that consumer demand could be aggregated for local farmers, giving them a more predictable market.

**В озвучку попало:**

> Несколько участников совета продолжали обсуждать эти возможности и после встречи. Еще одной важной темой стала потребность фермеров в понимании своих рынков и наличии постоянных покупателей еще до начала сезона. Один из фермеров предложил объединить людей для создания закупочного кооператива. Это позволило бы суммировать потребительский спрос и обеспечить фермерам более предсказуемый рынок сбыта.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0806` — длина озвучки / длина оригинала: 1.44; классы правки: —

**Исходный абзац:**

> Studies on employee activity programs reveal that the productivity of the people involved increased by 12%,8 and absenteeism dropped by up to 45%.⁹ Estimates of the impact of healthcare costs on corporations show a rise from 7% thirty years ago to up to 50% of the corporate profits now. This is why some individual companies are investing in wellness directly. For instance, Johnson & Johnson spends $4.5 million per year on staff wellness programs, avoiding thereby medical costs estimated at $13 million per year. But individual corporate solutions may not be the most effective way to solve the problem.

**В озвучку попало:**

> Исследования программ активности сотрудников показывают, что производительность участников таких программ выросла на двенадцать процентов, а число пропусков работы по болезни сократилось почти вдвое. [short pause] Оценки влияния расходов на здравоохранение на корпоративный сектор показывают, что если тридцать лет назад они составляли семь процентов от прибыли компаний, то сегодня этот показатель достигает пятидесяти процентов. Именно поэтому некоторые компании начинают инвестировать в здоровье персонала напрямую. Например, компания Джонсон и Джонсон ежегодно тратит четыре с половиной миллиона долларов на оздоровительные программы для сотрудников, что позволяет избежать медицинских расходов на сумму около тринадцати миллионов долларов в год. Однако частные корпоративные решения могут оказаться не самым эффективным способом борьбы с проблемой в масштабах страны.

---

### 2. `p0284` — длина озвучки / длина оригинала: 1.42; классы правки: —

**Исходный абзац:**

> The total US credit market, i.e., borrowing by governments, corporations and individuals, is as close to a statistical fit of an exponential curve as is scientifically possible. (For those with an econometric background, the R2 value of .9889 means that it is almost a perfect fit.)¹⁴

**В озвучку попало:**

> Общий объем кредитного рынка Соединенных Штатов — то есть заимствования правительств, корпораций и частных лиц — настолько близок к экспоненциальной кривой, насколько это вообще возможно с научной точки зрения. Для тех, кто знаком с эконометрикой, поясню: коэффициент детерминации ноль целых девять тысяч восемьсот восемьдесят девять десятитысячных означает, что это практически идеальное соответствие.

---

### 3. `p0230` — длина озвучки / длина оригинала: 1.36; классы правки: —

**Исходный абзац:**

> The US federal government also has an array of what it calls *non-marketable securities* that aren’t traded on the market like US Savings Bonds: *intergovernmental* *debts* (when the federal government borrows from savings accounts like Social Security) and *Certificates of Indebtedness* the Treasury issues that don’t pay interest. All of these still represent government debt.

**В озвучку попало:**

> [serious] У федерального правительства США также есть ряд так называемых нерыночных ценных бумаг, которые не торгуются на открытом рынке, подобно сберегательным облигациям. К ним относятся межправительственные долги, когда федеральное правительство заимствует средства из сберегательных фондов, например, из системы социального обеспечения. Также существуют сертификаты задолженности, выпускаемые Казначейством, по которым не выплачиваются проценты. Все эти инструменты по своей сути являются государственным долгом.

---

### 4. `p0115` — длина озвучки / длина оригинала: 1.36; классы правки: —

**Исходный абзац:**

> The appeal of big prize lottery tickets comes in part from the fantasy the tickets allow. We imagine all the things we could do, charities, projects, real change that we could help make happen. There is no denying the appeal of vast sums of money. In our dreams, money solves all our problems, gives us resources to meet needs we never knew we had. But is it wealth?

**В озвучку попало:**

> [thoughtful] Привлекательность лотерейных билетов с огромными выигрышами отчасти объясняется фантазиями, которые они позволяют нам строить. Мы представляем, сколько всего могли бы сделать: помочь благотворительным организациям, запустить важные проекты или добиться реальных перемен. Невозможно отрицать притягательность огромных сумм денег. В наших мечтах деньги решают все проблемы и дают ресурсы для удовлетворения потребностей, о которых мы даже не подозревали. Но является ли это богатством?

---

### 5. `p0797` — длина озвучки / длина оригинала: 1.31; классы правки: —

**Исходный абзац:**

> In 2004, more than one million Americans were financially ruined by illness or medical bills. Most were middle class. Each year, two million Americans face the double disaster of illness and bankruptcy. But the bigger surprise is that ¾ of the medically bankrupt had health insurance. Too sick to work, they suddenly lost their jobs. With the jobs went most of their income and their health insurance — ¼ of all employers cancel coverage the day employees leave work because of a disabling illness; another ¼ do so in less than a year.

**В озвучку попало:**

> [serious] В 2004 году более миллиона американцев оказались на грани финансового краха из-за болезней или непосильных медицинских счетов. Большинство из них принадлежали к среднему классу. Каждый год два миллиона жителей США сталкиваются с двойной бедой: тяжелым недугом и банкротством. Но еще более поразительно то, что три четверти из тех, кто обанкротился из-за медицины, имели медицинскую страховку. Став слишком больными для работы, они внезапно теряли свои места. Вместе с работой уходили основной доход и страховка. Четверть всех работодателей аннулируют полис в тот же день, когда сотрудник уходит на больничный из-за инвалидизирующего заболевания, а еще четверть делают это менее чем через год.

---

### 6. `p0281` — длина озвучки / длина оригинала: 1.30; классы правки: —

**Исходный абзац:**

> In our current era, where high priced oil and overleveraged assets triggered an economic collapse which forced the US government to provide huge “bailout” loans to banks (created with government bonds and debt) and then other huge “stimulus” grants to state and local governments and businesses (also created with government bonds and debt), this system dynamics hypothesis seems to hold true.

**В озвучку попало:**

> [serious] В наше время дорогая нефть и чрезмерная долговая нагрузка спровоцировали экономический крах. Это вынудило правительство Соединенных Штатов предоставить банкам огромные кредиты для спасения, которые были обеспечены государственными облигациями и долгами. Затем последовали другие масштабные вливания в виде грантов для штатов, местных органов власти и бизнеса, которые также были созданы за счет государственных облигаций и долгов. Похоже, что эта гипотеза системной динамики подтверждается на практике.

---

### 7. `p0915` — длина озвучки / длина оригинала: 1.30; классы правки: —

**Исходный абзац:**

> There are problems when subsistence agriculture is the dominant form of agriculture. Food can spoil, and so finding ways to insure that the harvest can be preserved is an important strategy. Land is hard to obtain (unless you inherit it), and so good land is in high demand.

**В озвучку попало:**

> [thoughtful] Когда натуральное хозяйство становится основной формой сельского хозяйства, возникают свои сложности. Продукты могут испортиться, поэтому поиск способов сохранения урожая становится важнейшей задачей. Кроме того, получить землю в собственность непросто, если она не досталась по наследству, поэтому спрос на хорошие участки всегда очень высок.

---

### 8. `p0661` — длина озвучки / длина оригинала: 1.29; классы правки: —

**Исходный абзац:**

> Beyond the simple fact that local is more ecologically sustainable, and complementary currencies are usually local, we can also help restore the environment with eco-currencies, including carbon credits associated with a cap and trade system, which can be local, regional, national or international.

**В озвучку попало:**

> [thoughtful] Помимо того, что локальные системы более экологичны, а дополнительные валюты обычно привязаны к местности, мы можем восстанавливать окружающую среду с помощью эко-валют. Сюда входят, например, углеродные кредиты, связанные с системой ограничения выбросов и торговли квотами. Такие системы могут действовать на местном, региональном, национальном или международном уровнях.

---

### 9. `p0699` — длина озвучки / длина оригинала: 1.26; классы правки: —

**Исходный абзац:**

> In contrast, the CCU approach provides carbon savings that are locally certified, can be tracked within the vicinity in real time and whose use can be electronically audited back to their origin. Each CCU has its own electronic certificate, through which one can follow where and by whom it was created, for what specific purchase and at what time. This gives a much higher degree of verifiability than is typically available with the carbon credits traded under the Kyoto agreement. Finally, as the CCU system is electronically integrated in real time, it enables each community to announce the carbon savings it has generated, providing on the spot feedback on how well it is doing compared to other communities. That way, everybody participates through their own daily decisions.

**В озвучку попало:**

> [thoughtful] В отличие от этого, подход с использованием углеродных единиц обеспечивает экономию, которая сертифицируется на местах. Ее можно отслеживать в режиме реального времени в пределах конкретного региона, а использование единиц — проверять в электронном виде вплоть до их источника. Каждая такая единица имеет собственный электронный сертификат. С его помощью можно проследить, где и кем она была создана, для какой конкретной покупки и в какое время. Это обеспечивает гораздо более высокую степень проверяемости, чем та, что обычно доступна для углеродных кредитов, которыми торгуют в рамках Киотского соглашения. Наконец, поскольку система углеродных единиц интегрирована в электронную сеть в реальном времени, каждое сообщество может отчитываться о достигнутой экономии. Это дает мгновенную обратную связь о том, насколько успешно оно справляется с задачей по сравнению с другими сообществами. Таким образом, каждый человек участвует в процессе через свои повседневные решения.

---

### 10. `p1464` — длина озвучки / длина оригинала: 1.26; классы правки: —

**Исходный абзац:**

> Some systems combine features of various issuing approaches described above. For example WIR is issued both as mutual credit and from a central office with legal collateral. Some social purpose complementary currencies are also accepted in partial payment by local businesses as a loyalty currency.

**В озвучку попало:**

> [thoughtful] Некоторые системы объединяют черты разных подходов к выпуску, описанных выше. Например, валюта WIR выпускается одновременно как через взаимный кредит, так и через центральный офис под юридическое обеспечение. Кроме того, некоторые социальные дополнительные валюты принимаются местным бизнесом в качестве частичной оплаты, работая по принципу программы лояльности.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1544` — совпадение символов с оригиналом: 32%; классы правки: —

**Исходный абзац:**

> Global Community Initiatives has worked in partnership with Natural Capitalism Solutions and the America’s Development Foundation to create a new workbook for local communities to revitalize and develop their local economies in ways that build real wealth, enhance the quality of life and protect and restore the natural environment. The workbook is called *LASER* — *Local Action for* *Sustainable Economic Renewal*.

**В озвучку попало:**

> Организация Global Community Initiatives в партнерстве с Natural Capitalism Solutions и America’s Development Foundation разработала новое практическое руководство для местных сообществ. Оно помогает возрождать и развивать экономику так, чтобы приумножать реальное благосостояние, повышать качество жизни, а также защищать и восстанавливать природную среду. Это руководство называется LASER — «Местные действия для устойчивого экономического обновления».

---

### 2. `p1150` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Developing the vision was a celebration of community participation and imagination! It was an adventure in exploring values, building on assets and incorporating citizens’ hopes and dreams for the next 100 years. Based upon the success of Imagine Chicago and other community movements around the world, imagineCALGARY reached out to Calgarians using a variety of strategies. Over 18,000 responded via:

**В озвучку попало:**

> Разработка концепции стала настоящим праздником участия и воображения! Это было приключение, в ходе которого исследовались ценности, оценивались ресурсы и собирались надежды и мечты граждан на ближайшие сто лет. Опираясь на успех проекта «Imagine Chicago» и других общественных движений по всему миру, инициатива «imagineCALGARY» использовала множество стратегий. Более восемнадцати тысяч человек откликнулись через:

---

### 3. `p0879` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Montpelier, the capital city of Vermont, has created both a Time Bank and a Care Bank. The Onion River Exchange is a standard Time Bank, where members post their offers and requests and trade with each other as often as they like. The city also received a federal grant from the US Administration on Aging to create the Rural Elder Assistance for Care and Health (REACH) program. REACH expands traditional Time Bank membership types to include three levels: basic, assisted and specialized.

**В озвучку попало:**

> В Монтпилиере, столице штата Вермонт, созданы и тайм-банк, и банк заботы. «Onion River Exchange» — это обычный тайм-банк, где участники размещают свои предложения и запросы. Кроме того, город получил федеральный грант на создание программы помощи сельским пожилым людям, известной как REACH. Эта программа расширяет традиционное членство в тайм-банке до трех уровней: базового, вспомогательного и специализированного.

---

### 4. `p1393` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> Working with a team, especially a team with diverse backgrounds and perspectives, can be a challenge — there are many skills that can make the work more effective. A lot has been written about leadership, listening, conflict management, meeting facilitation and introducing innovation, and there is no need to repeat it all here. Global Community Initiatives offers a free resource guide to all of these community organizing skills.⁸

**В озвучку попало:**

> Работа в команде, особенно если она состоит из людей с разным опытом и взглядами, может быть непростой задачей. Существует множество навыков, которые делают такую работу эффективнее: лидерство, умение слушать, управление конфликтами, проведение встреч и внедрение инноваций. Нет нужды пересказывать всё это здесь. Организация Global Community Initiatives предлагает бесплатное руководство по всем этим навыкам организации сообществ.

---

### 5. `p0880` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> At the *basic* level, REACH works like a Time Bank. You make a donation to the organization of either $25/year or offer two hours of assistance with a fundraiser for the organization. Then you post the things you are willing to do for the Time Bank — your offers — and the things you would like someone to do for you — your requests. The posting is made using the Community Weaver software developed by Time Banks USA. A central website keeps track of all the members, their requests, their offers and the time dollars or, in Montpelier ’s case the Community Credits, that are exchanged by members.

**В озвучку попало:**

> На базовом уровне программа REACH работает как обычный тайм-банк. Вы делаете взнос в размере 25 долларов в год или отрабатываете два часа на мероприятиях по сбору средств. Затем вы публикуете свои предложения — то, что готовы сделать для других, — и свои запросы — то, что нужно вам. Все это происходит через программное обеспечение «Community Weaver». Центральный сайт отслеживает всех участников, их потребности и время, которое они обменивают — в Монтпилиере такие единицы называют «общественными кредитами».

---

### 6. `p1175` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> One of the benefits to Calgary Dollars of the imagineCALGARY project was that its importance to the different goals and objectives the city established was articulated in the long-term plan the city developed. This raised awareness among a broader range of stakeholders about the currency and linked it to city objectives.

**В озвучку попало:**

> Одним из преимуществ проекта «imagineCALGARY» для «Калгари Долларс» стало то, что значимость этой валюты для достижения целей города была четко прописана в долгосрочном плане развития. Это повысило осведомленность среди широкого круга заинтересованных сторон и связало использование валюты с конкретными задачами города.

---

### 7. `p1430` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Store of Value The last classical function of money is as store of value. As noted before, it may be desirable to have as complementary currency one that is not used as a store of value. Currency was indeed not the preferred store of value in most civilizations. For example, the word capital derives from the Latin *capus* which means head. This word referred to heads of cattle and is still used today in Texas or among the Watutsi in Africa: “He is worth 1,000 head.” In the Western world, from Egyptian times through the Middle Ages and until the late 18th century, wealth was stored mainly in land and improvements, that’s why it’s called *Real Estate* (irrigations, plantations).

**В озвучку попало:**

> [thoughtful] Последняя классическая функция денег — это накопление стоимости. Как отмечалось ранее, иногда желательно, чтобы дополнительная валюта не использовалась как средство сбережения. В большинстве цивилизаций деньги вообще не были предпочтительным способом накопления. Например, слово «капитал» происходит от латинского «capus», что означает «голова». Изначально оно относилось к поголовью скота и до сих пор используется в таком значении в Техасе или среди народа тутси в Африке: «Он стоит тысячу голов». В западном мире, от времен Древнего Египта через Средневековье и до конца восемнадцатого века, богатство хранилось преимущественно в земле и улучшениях — именно поэтому в английском языке недвижимость называется «Real Estate» (включая ирригационные системы и плантации).

---

### 8. `p0876` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Every human being matters. Respect underlies freedom of speech, freedom of religion, and everything we value. Respect supplies the heart and soul of democracy. When respect is denied to anyone, we all are injured. We must respect where people are in the moment, not where we hope they will be at some future point.6

**В озвучку попало:**

> [serious] Каждый человек имеет значение. Уважение лежит в основе свободы слова, свободы вероисповедания и всего, что мы ценим. Оно — сердце и душа демократии. Когда в уважении отказывают кому-то одному, страдают все. Мы должны принимать людей такими, какие они есть сейчас, а не такими, какими мы надеемся увидеть их в будущем.

---

### 9. `p0086` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Other editing assistance from Gina Ottoboni came at a critical time when my schedule was very demanding and I needed help pulling the last pieces together. Finally, I’m grateful to the Balaton Group and Dennis Meadows, who saw the importance of what we were talking about and scheduled the 2010 meeting in Iceland. That gave us a reason to travel there and meet with all the activists who were trying to put that country back on its feet. They also were an inspiration, and we wish them the best as the country struggles with real economic challenges.

**В озвучку попало:**

> Джина Оттобони оказала помощь в редактировании в критический момент, когда мой график был крайне плотным и мне требовалась поддержка, чтобы собрать последние фрагменты воедино. Наконец, я благодарна группе Balaton и Деннису Медоузу. Они осознали важность наших идей и организовали встречу 2010 года в Исландии. Это дало нам повод поехать туда и встретиться с активистами, которые пытались поставить страну на ноги. Они тоже стали для нас источником вдохновения, и мы желаем им всего наилучшего в борьбе с реальными экономическими трудностями.

---

### 10. `p0737` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Like Stonyfield, Seventh Generation also models what a company can and should be. From a first glance at their website, it’s clear this is no ordinary company, no business as usual. “Protecting Planet Home,” is front and center, along with their mission, “help[ing] you protect your world with our naturally safe and effective household products.” You can participate in “Ask Scienceman,” a Q&A, or purchase a copy of “The Responsibility Revolution.” Seventh Generation isn’t just selling eco-friendly products, they are teaching people how to steward Earth. Recently, the company began a crowd-source project to produce an online book featuring best practices in corporate social responsibility and sustainability. Contrast this with a large, conventional competitor whose website proclaims “Everyone is an innovator” and lists “Investor Relations” as the first tab.

**В озвучку попало:**

> [serious] Как и Stonyfield, компания Seventh Generation служит примером того, какой может и должна быть современная фирма. Уже при первом взгляде на их сайт становится ясно: это не обычный бизнес. На самом видном месте красуется девиз «Защищая планету — наш дом» и миссия: «помогать вам беречь свой мир с помощью наших безопасных и эффективных товаров для дома». Посетители сайта могут поучаствовать в рубрике «Спроси ученого» или купить книгу «Революция ответственности». Seventh Generation не просто продает экологичные товары — она учит людей заботиться о Земле. Недавно компания запустила краудсорсинговый проект по созданию онлайн-книги, где собраны лучшие практики корпоративной социальной ответственности и устойчивого развития. Сравните это с крупным традиционным конкурентом, чей сайт встречает лозунгом «Каждый — инноватор», а первой вкладкой в меню указывает «Отношения с инвесторами».

---
## Абзацы, оставшиеся в озвучке на английском (0)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.
## Пустые и почти пустые абзацы (8)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0173` — длина озвучки / длина оригинала: 0.80; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### The Myth (and Potential) of Individual Wealth

**В озвучку попало:**

> ### Миф (и потенциал) личного богатства

---

### 2. `p0257` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> FIGURE 2.1. The Limits to Growth Archetype

**В озвучку попало:**

> Рисунок 2.1. Архетип «Пределы роста»

---

### 3. `p0498` — длина озвучки / длина оригинала: 0.61; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## **EXAMPLES OF** **COMPLEMENTARY** **CURRENCIES**

**В озвучку попало:**

> ## Примеры дополнительных валют

---

### 4. `p1236` — длина озвучки / длина оригинала: 0.88; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Montpelier ’s Complementary Currencies

**В озвучку попало:**

> ### Дополнительные валюты Монтпилиера

---

### 5. `p1341` — длина озвучки / длина оригинала: 0.59; классы правки: —

**Исходный абзац:**

> Association (IRTA) and the Corporate Barter Council (CBC).

**В озвучку попало:**

> и Совет по корпоративному бартеру.

---

### 6. `p1377` — длина озвучки / длина оригинала: 0.80; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • state service providers for the unemployed

**В озвучку попало:**

> • государственные службы занятости;

---

### 7. `p1489` — длина озвучки / длина оригинала: 0.73; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Establishing a System for Circulation

**В озвучку попало:**

> ### Создание системы обращения

---

### 8. `p1807` — длина озвучки / длина оригинала: 0.31; классы правки: url_left_in, year_lost

**Исходный абзац:**

> 2010]. magic-city-news.com/Community_5/Katahdin_Time_Dollar_Exchange_38833883.shtml.

**В озвучку попало:**

> Сайт: magic-city-news.com.

---
