# Аудиокнига, прогон четырёх книг 2026-08-06 — creating_wealth, материал для просмотра глазами

Книга: Bernard Lietaer & Gwendolyn Hallsmith, *Creating Wealth* (`tests/sources/book/new_bernardlietaer-creatingwealthpdffromepub-160516072739.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_ab4_creating_wealth`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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
5. **1 абзацев, оставшихся в озвучке на английском** (порог ≥ 60 букв, кириллицы < 30 %).
6. **Пустые и почти пустые абзацы — все 5**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1519; вернулось: 1519;
дошло до narration-артефакта: 1498.
Пул прозы, из которого делалась выборка: 757 абзацев.
Медианное отношение длин по прозе: 0.9901.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0064` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> Those who gain profit from the current global system obviously will vigorously resist any efforts to change it. And they will prevail until industrial society collapses. Current policies will be desperately pursued until they must be changed in response to crisis. But individuals, families, communities, perhaps even regions, can begin now proactively to make the necessary changes that will lead to true happiness and sustainable wealth.

**В озвучку попало:**

> Те, кто извлекает прибыль из нынешней глобальной системы, очевидно, будут решительно сопротивляться любым попыткам ее изменить. И они будут брать верх до тех пор, пока индустриальное общество не рухнет. Нынешняя политика будет отчаянно продолжаться, пока кризис не заставит ее изменить. Но отдельные люди, семьи, сообщества и, возможно, даже целые регионы могут уже сейчас начать проактивно внедрять необходимые изменения, которые приведут к подлинному счастью и устойчивому благосостоянию.

---

### 2. `p0082` — длина озвучки / длина оригинала: 0.98; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Perhaps more than anyone, Gwendolyn’s parents and family are also worth mentioning. Wesley and Joan Hall set amazing examples of principled, intelligent people who worked hard for what they believe. Joan died in 2007, but Wesley continues to be very interested in and supportive of Gwendolyn’s work (even if he does refer to all these complementary currencies as “funny money”).

**В озвучку попало:**

> Нельзя не упомянуть родителей и семью Гвендолин. Уэсли и Джоан Холл стали для неё примером принципиальных и умных людей, которые упорно трудились ради своих убеждений. Джоан ушла из жизни в две тысячи седьмом году, но Уэсли продолжает живо интересоваться работой Гвендолин и поддерживает её, даже если в шутку называет все эти дополнительные валюты «игрушечными деньгами».

---

### 3. `p0094` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> One of the primary mechanisms for the creation of wealth is our banking and monetary system. We all put our money into the banks — the black box of the economy — and we assume the money will be there when we go to withdraw it. At least part of our mind probably believes that the money is there. We receive statements every month that say it’s there, and we earn interest on the deposits.

**В озвучку попало:**

> [thoughtful] Один из главных механизмов создания богатства — это наша банковская и денежная система. Мы доверяем свои деньги банкам, которые работают как «черный ящик» экономики, и рассчитываем, что они будут там, когда нам понадобятся. По крайней мере, какая-то часть нашего сознания в это верит. Мы ежемесячно получаем выписки, подтверждающие наличие средств, и получаем проценты по вкладам.

---

### 4. `p0118` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Wealth. It’s something we all want. Wealthy is rich, after all — but rich in what? In possessions, money, income? This depends on how you define the word. Its original meaning, from the Old English *weal* (as in commonweal), was simply prosperity or well-being.”¹ What a notion! How far from the meaning many of us have come to associate with the word. Wealth is more than the accumulation of money and resources, and it can be generated in ways other than through conventional financial means. In order to truly capture the wealth of our societies, our cultures and our environments, we have to pay heed to that older notion of wealth as well-being. We might think that winning the lottery will make us wealthy and that wealth will make us happy, but we also know that it doesn’t always work that way. While it’s true that poverty does make for unhappiness, lots of money doesn’t necessarily buy happiness.

**В озвучку попало:**

> [thoughtful] Богатство. Это то, к чему мы все стремимся. Быть богатым — значит иметь много денег, верно? Но что именно мы считаем богатством? Имущество, доходы или что-то еще? Всё зависит от определения. Изначально, согласно древнеанглийскому слову «weal», богатство означало просто процветание или благополучие. Какая замечательная идея! Как далеко мы ушли от этого смысла в современном понимании. Богатство — это нечто большее, чем просто накопление денег и ресурсов. Его можно создавать способами, далекими от привычных финансовых инструментов. Чтобы по-настоящему оценить богатство нашего общества, культуры и окружающей среды, нам нужно вернуться к старому пониманию богатства как благополучия. Мы часто думаем, что выигрыш в лотерею сделает нас богатыми, а богатство принесет счастье. Но мы знаем, что это не всегда работает. Бедность действительно делает людей несчастными, но большие деньги вовсе не гарантируют счастья.

---

### 5. `p0145` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> We’ve described several kinds of assets and capital that satisfy the needs we have, and still there has been no mention yet of the financial assets and capital we typically associate with the words *money* and *investment*. That’s partly because money is really more of a means to an end than a need in itself.

**В озвучку попало:**

> Мы описали несколько видов активов и капитала, удовлетворяющих наши потребности, но до сих пор не упомянули финансовые активы, которые обычно ассоциируются со словами «деньги» и «инвестиции». Это отчасти потому, что деньги — скорее средство достижения цели, чем потребность сама по себе.

---

### 6. `p0161` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> A larger vision for a walkable city with friendly neighborhoods and less suburban sprawl still requires changes in the land use ordinances before there will be any measurable change in density. A larger vision for clean air and reduced climate impacts will have to be translated into a number of policies — ranging from a purchasing policy that requires alternatives to energy-intensive items to capital planning for renewable energy production.

**В озвучку попало:**

> [serious] Чтобы превратить общую идею пешеходного города с уютными кварталами и меньшим разрастанием пригородов в реальность, нужно сначала изменить правила землепользования. Только тогда можно будет заметить ощутимые сдвиги в плотности застройки. Точно так же стремление к чистому воздуху и снижению климатического воздействия требует перевода в конкретные политики. Это может быть как правило закупок, исключающее энергозатратные товары, так и долгосрочное планирование капитальных вложений в возобновляемую энергетику.

---

### 7. `p0166` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Environmental policies that marginalize or impoverish a group of people or area in the city (or in another part of the world) won’t succeed in the long run. Housing plans that ignore their impact on important open space, wetlands and agricultural land will hurt the city over the long term. Economic development practices that rely on an unsustainable exploitation of natural resources or human potential will also ultimately have the opposite effect — they will further impoverish the community rather than creating real wealth.

**В озвучку попало:**

> Экологические инициативы, которые ущемляют права или ведут к обнищанию какой-либо группы людей — в городе или в другой части мира, — не будут успешными в долгосрочной перспективе. Жилищные планы, игнорирующие воздействие на важные природные зоны, водно-болотные угодья и сельскохозяйственные земли, в конечном счете навредят городу. Практики экономического развития, основанные на неустойчивой эксплуатации природных ресурсов или человеческого потенциала, также дадут обратный эффект. Вместо создания реального богатства они лишь еще больше обеднят сообщество.

---

### 8. `p0172` — длина озвучки / длина оригинала: 0.84; классы правки: —

**Исходный абзац:**

> Redefining wealth and refocusing local initiatives on meeting human needs can help local leaders see the economy as being at the service of their community, not the other way around. There are many forms of capital that demand investment for a local community to thrive, not just financial capital. Social capital, human capital, natural capital, institutional capital, technological capital, potential exchange capital, built capital and cultural capital all need to be understood and strengthened — and this multidimensional effort is absolutely the domain of local communities.

**В озвучку попало:**

> [serious] Переосмысление богатства и переориентация местных инициатив на удовлетворение человеческих потребностей помогут лидерам увидеть, что экономика должна служить сообществу, а не наоборот. Чтобы местное сообщество процветало, инвестиции нужны не только в финансовый капитал. Социальный, человеческий, природный, институциональный, технологический, культурный и другие виды капитала — всё это нужно понимать и укреплять. И эта многогранная работа — прямая задача местных сообществ.

---

### 9. `p0212` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> One market day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral six chickens wanted in exchange for a big ham, the stranger could not refrain from laughing. “Poor people,” he said, “so primitive.”

**В озвучку попало:**

> Однажды в деревню забрел незнакомец в блестящих черных туфлях и элегантной белой шляпе. Он наблюдал за торгом с саркастической улыбкой. Увидев, как фермер бегает по рынку, пытаясь собрать шесть кур в обмен на большой кусок ветчины, незнакомец не сдержал смеха. «Бедные люди, — сказал он, — до чего же вы примитивны».

---

### 10. `p0213` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Overhearing this, the farmer’s wife challenged him. “Do you think you can do a better job handling chickens?” The stranger responded: “Chickens, no. But there is a much better way to eliminate all the hassles. Bring me one large cowhide and gather the families. I’ll explain the better way.”

**В озвучку попало:**

> Жена фермера услышала это и бросила ему вызов: «Думаете, вы справились бы с курами лучше?» Незнакомец ответил: «С курами — нет. Но есть способ гораздо лучше, чтобы избавиться от всех этих хлопот. Принесите мне большую коровью шкуру и созовите все семьи. Я объясню, в чем дело».

---

### 11. `p0291` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Where are the leverage points, those interventions where a relatively small amount of effort can achieve much larger results? Often, a systems diagram can help identify promising possibilities. In this vicious cycle, there are two important drivers — the bank-debt source of our monetary system and the economic policies we have enacted to facilitate the process of human and natural capital depletion for the sake of the ever higher profits that the system demands. These are the two variables where policy interventions could have an important impact on the destructive force of the system.

**В озвучку попало:**

> Где находятся точки приложения сил — те рычаги, воздействие на которые с относительно небольшими усилиями дает значительный результат? Часто помочь в поиске таких возможностей могут системные диаграммы. В этом порочном круге есть два важных движущих фактора. Первый — это банковский долг как основа нашей денежной системы. Второй — экономическая политика, которую мы проводим, чтобы облегчить процесс истощения человеческого и природного капитала ради постоянно растущей прибыли, требуемой системой. Именно эти две переменные позволяют с помощью политических решений существенно повлиять на разрушительную силу системы.

---

### 12. `p0368` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> When you think of economic capital, the financial capital needed to undertake any type of enterprise is probably what comes to mind. For our purposes however, we will distinguish between three types of economic capital: financial, entrepreneurial and potential exchange capital.

**В озвучку попало:**

> [serious] Когда мы говорим об экономическом капитале, на ум чаще всего приходят финансовые средства, необходимые для запуска любого дела. Однако для целей нашей книги мы разделим экономический капитал на три типа: финансовый, предпринимательский и потенциальный обменный капитал.

---

### 13. `p0398` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Providing a new basis to increase the flow of assets throughout the local economic system in ways that meet real needs (while enhancing generative capacities) strengthens the foundation, the reproductive system, the greenhouse of the economy called capital. In this way, community and complementary currencies create new capital by fostering other forms of capital in the economy. A currency that encourages people to save energy, reduce fossil fuel use and lower emissions strengthens the natural capital of the climate regulation system and creates new capital for innovation in the energy sector. Using a local currency to link vocational trainees with houses that need renovation creates new capital in both the built environment and the human capital sectors. New capital can be created in most areas if we find new ways to unleash our creativity, interdependence and compassion outside and around the constraints national money imposes. Abundance and sufficiency are available to us, even in a finite world.

**В озвучку попало:**

> Создание новых способов увеличения потока активов в местной экономике — способов, которые удовлетворяют реальные потребности и расширяют созидательные возможности, — укрепляет фундамент экономики, ее «репродуктивную систему», которую мы называем капиталом. Таким образом, общественные и дополнительные валюты создают новый капитал, развивая другие его формы. Валюта, которая поощряет людей экономить энергию, снижать потребление ископаемого топлива и сокращать выбросы, укрепляет природный капитал климатической системы и создает капитал для инноваций в энергетике. Использование местной валюты для связи профессиональных стажеров с домами, требующими ремонта, создает новый капитал как в строительной сфере, так и в человеческом потенциале. Мы можем создавать новый капитал практически везде, если найдем способы высвободить нашу креативность, взаимозависимость и сострадание за пределами ограничений, навязываемых национальной валютой. Изобилие и достаток доступны нам даже в ограниченном мире.

---

### 14. `p0409` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> In the first example, from Egypt, people would receive shards of pottery with a date on them when they put their grain into the storehouse. The longer the grain was stored, the more the charge was for the guards and waste as the grain spoiled. Called *ostraka*,1 these shards circulated alongside the precious metals rings and bars that were used for trade with foreigners. The Greeks, Egypt’s main trading partners at that time, would mock the plain clay Egyptian currency. Yet the Egyptians thought the Greek obsession with metals was strange, “a piece of local vanity, patriotism, or advertisement, with no far-reaching importance.”² They would accept Greek coins, but only for their metal content.

**В озвучку попало:**

> В первом примере, египетском, люди получали глиняные черепки с датой, когда сдавали зерно на хранение. Чем дольше зерно лежало в хранилище, тем больше приходилось платить за охрану и за потери от порчи продукта. Эти черепки, называемые остраконами, обращались наряду с кольцами и слитками из драгоценных металлов, которые использовались для торговли с иностранцами. Греки, главные торговые партнеры Египта того времени, посмеивались над простой глиняной валютой египтян. Однако сами египтяне считали греческую одержимость металлами чем-то странным — своего рода местным тщеславием, патриотизмом или рекламой, не имеющей большого значения. Они принимали греческие монеты, но только ради содержания в них металла.

---

### 15. `p0419` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> There is no doubt that the economy of the United States in the 21st century could be called a competitive economy. Competition in free markets is held up as the only way to get low prices and all the benefits of a well-oiled economic system. Schools are competitive, as students vie with each other to get the best grades and to be accepted in exclusive colleges. Sports are competitive, and even families living on the same street have been known to do what it takes to “keep up with the Joneses.”

**В озвучку попало:**

> Нет сомнений, что экономику Соединенных Штатов в двадцать первом веке можно назвать конкурентной. Считается, что только свободная конкуренция на рынках позволяет добиться низких цен и всех преимуществ эффективно работающей системы. Конкуренция пронизывает всё: студенты соревнуются за лучшие оценки и места в престижных колледжах, спорт построен на соперничестве, и даже семьи, живущие на одной улице, стремятся не отставать друг от друга.

---

### 16. `p0421` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> Things are a little different north of the 49th parallel. Although Canada shares many of the characteristics of the United States, its economy and culture is somewhat less competitive. This can be documented by the large number of cooperative enterprises in Canada per capita as compared to the United States, and the fact that Canadians successfully managed to create a national healthcare system, something the US is only now starting. Many other western industrialized countries exhibit more of a balance between competition and cooperation than the US, as demonstrated in public benefits, inexpensive education systems, high quality national healthcare and other policies that strengthen the common good, rather than being oriented toward the individual.

**В озвучку попало:**

> К северу от сорок девятой параллели всё иначе. Хотя Канада во многом похожа на Соединенные Штаты, её экономика и культура менее конкурентны. Это подтверждается большим количеством кооперативных предприятий на душу населения по сравнению с США. Кроме того, канадцам удалось создать национальную систему здравоохранения, к чему Соединенные Штаты только начинают приходить. Многие другие западные индустриальные страны демонстрируют лучший баланс между конкуренцией и сотрудничеством. Это проявляется в социальных льготах, доступном образовании, качественном здравоохранении и других мерах, направленных на общее благо, а не только на интересы индивида.

---

### 17. `p0517` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> In response to the foreclosure crisis, the US Department of Housing and Urban Development created a new program — The Neighborhood Stabilization Program (NSP) — that is providing $4 billion to cities and towns.⁶ The money cannot be used to prevent more foreclosures, but it can be used to buy up foreclosed properties, pay the bank, renovate/ repair them and resell them. If public money is being used to purchase private homes from banks, this investment could be used to create new wealth by developing a means of exchange for housing that will create jobs while at the same time moving homeless people back into homes — all without spending more real taxpayer ’s dollars.

**В озвучку попало:**

> В ответ на кризис Министерство жилищного строительства и городского развития США создало программу стабилизации микрорайонов. Она выделяет городам и поселкам 4 миллиарда долларов. Эти средства нельзя использовать для предотвращения новых изъятий жилья за долги, но их можно направить на выкуп уже изъятой недвижимости. Деньги идут на выплаты банкам, ремонт и последующую перепродажу объектов. Если государственные средства используются для выкупа частных домов у банков, эти инвестиции можно превратить в источник нового благосостояния. Развивая систему обмена жильем, можно создавать рабочие места и одновременно возвращать бездомных в дома — и все это без дополнительных трат денег налогоплательщиков.

---

### 18. `p0596` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Sacred art in many religions takes on such symbolic importance that the forms, styles and even the paints are so closely prescribed that in centuries past breaking from traditional rules could result in the death penalty in some societies. Art historians spend a lifetime understanding the subtle gestures encoded in art from the era prior to mass literacy.

**В озвучку попало:**

> Во многих религиях сакральное искусство обретает такой символический вес, что формы, стили и даже краски строго регламентированы. В прошлые века отступление от традиционных правил в некоторых обществах могло караться смертью. Историки искусства тратят целую жизнь, чтобы расшифровать тонкие жесты, заложенные в произведениях эпохи, когда большинство людей еще не умели читать.

---

### 19. `p0599` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Fast forward to the 21st century, and the majority of our creative workers no longer dedicate their life energy to the creation of enduring beauty and awe-inspiring celebrations of divine energy. Poets are put to work writing syrupy stanzas for greeting cards, visual artists are designing web pages, corporate logos and publications. Sculptors are employed making gravestones, musicians write jingles for television ads and the most lucrative form of theater is the 30-second commercial aired during the Super Bowl. The well-paid artists, in other words, are working for corporations. Recent statistics show, however, that 55.6% of the rest of the “fine artists, art directors and animators” in the workforce are self-employed, compared to 10% of the rest of the population.¹ Career advice for students thinking about majoring in the arts in college is clear: “the number of qualified workers exceeds the number of available openings because the arts attract many talented people with creative ability.”² In short, there are a lot of people who want to be creative, but a real shortage of paid work for artists.

**В озвучку попало:**

> Перенесемся в двадцать первый век. Большинство творческих работников больше не посвящают свою жизнь созданию вечной красоты или прославлению божественной энергии. Поэты пишут слащавые строки для поздравительных открыток, художники разрабатывают веб-страницы, корпоративные логотипы и рекламные буклеты. Скульпторы делают надгробия, музыканты сочиняют джинглы для телерекламы, а самой прибыльной формой театра стал тридцатисекундный ролик, показанный во время Супербоула. Иными словами, высокооплачиваемые художники работают на корпорации. Статистика показывает, что пятьдесят пять и шесть десятых процента остальных «художников, арт-директоров и аниматоров» работают на себя, тогда как среди остального населения таких лишь десять процентов. Советы студентам, планирующим изучать искусство в колледже, звучат однозначно: число квалифицированных специалистов превышает количество доступных вакансий, поскольку искусство привлекает множество талантливых людей. Короче говоря, есть огромное количество желающих творить, но при этом ощущается острая нехватка оплачиваемой работы для художников.

---

### 20. `p0601` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Yet despite these figures, the *creative economy* has taken over a leading role in the US employment profile in the last 20 years. In the early 1990s, the people with jobs associated with the creative economy surpassed those employed in traditional manufacturing jobs for the first time in history.

**В озвучку попало:**

> И все же, несмотря на эти цифры, за последние двадцать лет «креативная экономика» заняла ведущую роль в структуре занятости США. В начале девяностых годов число людей, занятых в креативном секторе, впервые в истории превысило количество работников в традиционной промышленности.

---

### 21. `p0614` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> Notice that this approach would ensure that more of the creative activity would take place in town, that its creative people would obtain income in dollars, but that this wouldn’t cost the city any additional dollars. By setting up a foundation, for example, an organization could make the Art Tokens even more valuable to its users than bank-debt dollars.

**В озвучку попало:**

> Заметьте: такой подход гарантирует, что творческая активность будет сосредоточена внутри города. Творческие люди получат доход в долларах, но для самого города это не потребует дополнительных расходов. А если создать специальный фонд, арт-токены могут стать для пользователей даже ценнее, чем обычные банковские деньги.

---

### 22. `p0667` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> At this point, you might well say, “I’d buy a hybrid, if only they were more affordable,” or “I’d walk to work if I could find a job near my home.” In other words, although you possess the power of choice, you do not have sufficient good choices at your disposal. So how do we create a world where environmentally-friendly choices are widely available and a sustainable lifestyle the norm? We can begin by reducing the amount of CO2 in the atmosphere. Could a complementary carbon currency be part of the solution?

**В озвучку попало:**

> В этот момент вы можете возразить: «Я бы купил гибридный автомобиль, если бы они были доступнее» или «Я бы ходил на работу пешком, если бы нашел ее рядом с домом». Иными словами, хотя у вас есть свобода выбора, у вас нет достаточно хороших вариантов. Как же создать мир, в котором экологичные решения доступны каждому, а устойчивый образ жизни стал нормой? Мы можем начать с сокращения количества углекислого газа в атмосфере. Может ли дополнительная углеродная валюта стать частью решения?

---

### 23. `p0670` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Among the developed nations, only Australia and the US have abstained from the treaty. Its Clean Development Mechanism (CDM) allocates a specific amount of carbon credits to various countries and industries, but allows credits to be bought and sold internationally. A company that produces more greenhouse gases than its allocation needs to purchase carbon credits sold by another producer who has reduced emissions beyond what is required. International trading in carbon contracts on the basis of the CDM protocol of the Kyoto treaty has successfully started.

**В озвучку попало:**

> Среди развитых государств только Австралия и Соединенные Штаты воздержались от участия в этом договоре. Его механизм чистого развития распределяет определенное количество углеродных квот между странами и отраслями, но при этом разрешает международную куплю-продажу этих единиц. Компания, которая производит больше парниковых газов, чем ей позволено, должна выкупить квоты у другого производителя, который сократил выбросы сверх установленной нормы. Международная торговля углеродными контрактами на основе протокола Киотского соглашения уже успешно началась.

---

### 24. `p0698` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> A *Financial Times* investigation has uncovered widespread failings in the new markets for greenhouse gases, suggesting some organizations are paying for emissions reductions that do not take place.⁷ Others are meanwhile making big profits from carbon trading for very small expenditure and, in some cases, for cleanups that would have been made anyway.

**В озвучку попало:**

> [thoughtful] Расследование газеты «Файненшл Таймс» выявило серьезные недостатки на новых рынках парниковых газов. Выяснилось, что некоторые организации платят за сокращение выбросов, которое фактически не происходит. Другие же получают огромную прибыль от торговли углеродными кредитами при минимальных затратах, а иногда и за те экологические мероприятия, которые были бы проведены в любом случае.

---

### 25. `p0751` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Like individuals, businesses, too, can have a cash flow shortage but a surplus of goods. Again in this case, it’s not terribly convenient to pay in corn, pigs or saddle shoes. And doing so might limit what you can purchase. The shoelace supplier probably doesn’t want a warehouse full of shoes.

**В озвучку попало:**

> Как и частные лица, компании могут столкнуться с нехваткой наличности при избытке товаров. И в этом случае расплачиваться зерном, свиньями или обувью по-прежнему неудобно. К тому же это ограничивает ваши возможности: поставщику шнурков вряд ли нужен склад, забитый ботинками.

---

### 26. `p0754` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Needless to say, the banks did not like the idea, and they tried to stop the new currency, called the WIR, in its tracks. (WIR is derived from the word *Wirtschaftsring* or economic circle — but *wir* also means “we” in German.) Nevertheless, the system survived. The WIR system evolved into a full-scale dual currency bank which manages and lends in both WIR and Swiss Francs.

**В озвучку попало:**

> Разумеется, банкам эта идея не понравилась, и они попытались остановить новую валюту, получившую название «ВИР». Слово происходит от немецкого «Виртшафтсринг», что значит «экономический круг», но при этом «вир» по-немецки означает «мы». Тем не менее система выжила. Со временем она превратилась в полноценный банк, работающий с двумя валютами: швейцарскими франками и ВИРами.

---

### 27. `p0762` — длина озвучки / длина оригинала: 0.85; классы правки: —

**Исходный абзац:**

> The C3 approach is probably the most dependable way to systemically reduce unemployment, and accepting C3 units in payment of taxes is the most effective way for governments to support the spread of the C3 system. Businesses with an account in the same regional network have an incentive to spend their balances with each other, and thus further stimulate the regional economy. C3 provides a win-win environment for all participants and therefore promotes other collaborative activities among regional businesses.

**В озвучку попало:**

> Подход C3, вероятно, является самым надежным способом системного снижения безработицы, а прием этой валюты государством — самым эффективным методом поддержки системы. Компании, состоящие в одной региональной сети, заинтересованы тратить свои балансы друг у друга, что дополнительно стимулирует местную экономику. C3 создает взаимовыгодную среду для всех участников и способствует развитию сотрудничества между региональными предприятиями.

---

### 28. `p0766` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> We can do a lot to foster a healthy business climate by expanding the ability of local businesses to use either loyalty or commercial barter systems in new ways. When our cities and other local governments accept C3 units in payment of taxes and fees, this will be one of the most effective ways for local governments and businesses to collaborate in solving local economic problems.

**В озвучку попало:**

> Мы можем многое сделать для развития здорового делового климата, расширяя возможности местных компаний по использованию систем лояльности или коммерческого бартера. Когда города и местные органы власти начнут принимать единицы C3 в счет уплаты налогов и сборов, это станет одним из самых эффективных способов сотрудничества между властью и бизнесом в решении локальных экономических проблем.

---

### 29. `p0774` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> Healthcare in the US is one of the glaring examples of the failure of money, insurance and the privately held healthcare companies’ ability to meet human needs. The US Constitution affirms that we all are created equal — no one born on Earth is more deserving of basic human rights than anyone else. However, the same centripetal forces that consolidate wealth and power in the marketplace and in society are also at work in the healthcare system.

**В озвучку попало:**

> [serious] Здравоохранение в Соединенных Штатах — один из самых ярких примеров того, как не справляются со своей задачей деньги, страхование и частные медицинские компании, призванные удовлетворять человеческие потребности. Конституция США провозглашает, что все люди созданы равными, и никто из рожденных на Земле не имеет больше прав на базовые человеческие потребности, чем другие. Однако те же центростремительные силы, что концентрируют богатство и власть на рынке и в обществе, действуют и в системе здравоохранения.

---

### 30. `p0775` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The starting point should be to recognize that we don’t have a *healthcare* system — instead we have a *medical care* system. Furthermore, income for that medical care system is produced essentially by people who are alive and sick. Therefore only more sick people — not healthy ones — lead to more growth and income in that sector. With such an incentive scheme, that system has become remarkably adept at keeping sick people alive. Over 60% of total lifelong medical expenses are typically incurred in the last three months of a patient’s life; and emergency care is clearly a domain in which Western medicine excels.

**В озвучку попало:**

> Начать стоит с признания того, что у нас нет системы *здравоохранения*. У нас есть система *медицинской помощи*. Более того, доход этой системы по сути создается людьми, которые живы, но больны. Следовательно, только увеличение числа больных — а не здоровых — ведет к росту доходов в этом секторе. При такой системе стимулов отрасль научилась мастерски поддерживать жизнь в больных людях. Как правило, более шестидесяти процентов всех пожизненных медицинских расходов приходится на последние три месяца жизни пациента. И экстренная помощь — это та область, в которой западная медицина действительно преуспевает.

---

### 31. `p0877` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> While they are not focused on child care or elder care, Time Banks provide a system where care for children and elders can take place more easily. In fact, a high percentage of Time Banks find that child care is one of the things people are seeking when they join. The fact that the activities in Time Banks are officially tax-exempt (which means they do not count toward members’ income) also means that when people use services through a Time Bank, they do not put income-based government benefits at risk.

**В озвучку попало:**

> Хотя тайм-банки не специализируются исключительно на уходе за детьми или пожилыми людьми, они создают систему, которая значительно упрощает организацию такой помощи. Более того, многие участники присоединяются к тайм-банкам именно в поисках услуг по присмотру за детьми. Важно и то, что деятельность тайм-банков официально освобождена от налогов. Это значит, что полученные услуги не считаются доходом и не ставят под угрозу государственные пособия, зависящие от уровня заработка.

---

### 32. `p0886` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In order to address this rapidly rising problem, the Japanese have implemented several new time exchange currencies.⁹ In these systems, the hours that a volunteer spends helping older or handicapped persons with their daily routine are credited to that volunteer ’s *time account*. Time accounts are managed like a savings account, except that the unit of account is hours of service instead of Yen. Time account credits are also available to complement normal health insurance programs. One of these time exchange systems is run on a national level by the Sawayaka Foundation in Japan. It’s called the *Fureai Kippu* system and has a lot to teach us about how complementary currencies can address serious social issues.

**В озвучку попало:**

> Чтобы справиться с этой острой проблемой, японцы внедрили несколько новых валют, основанных на обмене временем. В этих системах часы, которые волонтер тратит на помощь пожилым или людям с инвалидностью, зачисляются на его «счет времени». Такие счета работают как сберегательные, только вместо иен единицей накопления выступают часы оказанных услуг. Кредиты на счетах времени также можно использовать как дополнение к обычным программам медицинского страхования. Одной из таких национальных систем управляет фонд «Саваяка». Она называется «Фуреай Киппу» — «билет заботливых отношений», — и этот опыт многому может нас научить в плане использования дополнительных валют для решения серьезных социальных задач.

---

### 33. `p0902` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In the 1970s and 1980s, the government of Botswana started promoting trade among the villages in the Kalahari, and for the first time, money was introduced to the !Kung. This seemingly small change — the introduction of money — had an enormous impact on !Kung society and their social interactions. They began to use money to buy glass beads and other valuables, which they locked in new metal boxes in their homes. Within five years, people sought privacy rather than intimacy, and even the way they laid out their homes changed. No longer were doors open towards a common hearth; instead they faced away from the circle of homes. People started hoarding instead of depending on others, and the hunter-gatherer way of life that had shaped !Kung society over hundreds of generations gave way to totally different life patterns much closer to our own.¹

**В озвучку попало:**

> В семидесятых и восьмидесятых годах правительство Ботсваны начало поощрять торговлю между деревнями Калахари, и в жизнь кунг впервые вошли деньги. Это, казалось бы, небольшое изменение оказало колоссальное влияние на их общество и социальные связи. Люди начали использовать деньги для покупки стеклянных бус и других ценностей, которые они запирали в новые металлические сундуки. Всего за пять лет стремление к близости сменилось тягой к уединению, и даже планировка домов изменилась. Двери больше не смотрели на общий очаг, а были развернуты в сторону от центра лагеря. Люди начали делать запасы вместо того, чтобы полагаться на соседей. Тот образ жизни охотников-собирателей, который формировал общество кунг на протяжении сотен поколений, уступил место совершенно иным моделям поведения, гораздо более близким к нашим собственным.

---

### 34. `p1024` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Two of the priority actions under the Governance goal could have been controversial, but didn’t run into any real opposition as the mayor moved them forward. Since these actions involved changing the city’s charter — the document that forms the constitution for the city — there were several legal protocols to follow, which also could have provided opponents with a place to stop them. Two of these were:

**В озвучку попало:**

> Два приоритетных действия в рамках цели по совершенствованию управления могли бы стать предметом споров, но не встретили реального сопротивления, когда мэр начал их продвигать. Поскольку эти меры требовали внесения изменений в устав города — документ, который служит городской конституцией, — необходимо было соблюсти ряд юридических процедур. Это могло дать оппонентам возможность заблокировать инициативы. Вот эти два пункта:

---

### 35. `p1045` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> The Social Equity Investment Project does a lot through the coordinator working in the community to promote diversity. To do this, she works with a wide variety of community organizations to increase the representation in their leadership groups by people who are not traditionally in leadership positions — people of color, people who are physically challenged and people who have low incomes. Workshops are offered on subjects like “A Solution to Cultural Shifting,” and the coordinator supports projects run by Burlington’s Center for Community and Neighborhoods such as the Inclusive Community Initiative and the We All Belong Initiative.

**В озвучку попало:**

> Проект выполняет важную работу по продвижению многообразия через своего координатора. Она сотрудничает с множеством общественных организаций, чтобы увеличить представительство в их руководстве людей, которые традиционно не занимали таких должностей: цветных граждан, людей с ограниченными возможностями и жителей с низким доходом. Проект проводит семинары на такие темы, как «Решение проблемы культурных сдвигов», а также поддерживает инициативы Центра по работе с сообществами и районами, например, программы «Инклюзивное сообщество» и «Мы все принадлежим этому месту».

---

### 36. `p1063` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> The Social Equity Investment Project, and all the goals and targets the city set for governance and social well-being, represent a significant contribution by the city to ongoing discussions about sustainability. Burlington was the first city to address issues of equity and justice in a planning project that otherwise would have been seen as having only an environmental and economic focus.

**В озвучку попало:**

> [thoughtful] Проект инвестиций в социальное равенство, а также все цели и задачи, которые город поставил в области управления и социального благополучия, стали значимым вкладом Берлингтона в дискуссию об устойчивом развитии. Берлингтон стал первым городом, который включил вопросы справедливости и равенства в проект планирования, который иначе рассматривался бы исключительно через призму экологии и экономики.

---

### 37. `p1132` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> In Figure 1, the feedback loops describe a common system archetype known as Success to the Successful. This pattern of behavior occurs in many places in society, including bright children in school getting more attention from teachers or people moving up the ladder within a corporation.

**В озвучку попало:**

> [serious] На схеме петли обратной связи описывают распространенный системный архетип, известный как «успех приходит к успешным». Подобные модели поведения встречаются во многих сферах жизни общества: от школьников, которые получают больше внимания от учителей, до сотрудников, продвигающихся по карьерной лестнице в корпорациях.

---

### 38. `p1150` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> Developing the vision was a celebration of community participation and imagination! It was an adventure in exploring values, building on assets and incorporating citizens’ hopes and dreams for the next 100 years. Based upon the success of Imagine Chicago and other community movements around the world, imagineCALGARY reached out to Calgarians using a variety of strategies. Over 18,000 responded via:

**В озвучку попало:**

> Разработка этого видения стала настоящим праздником участия и воображения! Это было приключение, в ходе которого жители исследовали свои ценности, опирались на сильные стороны города и делились надеждами и мечтами на ближайшие сто лет. Вдохновившись успехом движения «Imagine Chicago» и другими подобными инициативами по всему миру, проект «imagineCALGARY» использовал множество стратегий взаимодействия. Более восемнадцати тысяч человек откликнулись через:

---

### 39. `p1172` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> At the time of this writing, it is too early to say much about the implementation of the plan, although work has been done to institutionalize it into city government by creating a Sustainability Coordinator in the City Manager ’s office and to establish a formal organization outside of city government that will keep community efforts going. The new coordinator ’s job is intentionally low-key; the goal was not to develop a new department for sustainability, which has the unfortunate unintended consequence of allowing other departments to assume that the job is being taken care of without their involvement. The position will instead continue to integrate the work of the broad range of city departments and to hold their feet to the fire with respect to the targets that were set and refined by the City Council into a shorter term work plan for the city.

**В озвучку попало:**

> На момент написания этой книги еще рано делать выводы о реализации плана. Тем не менее, была проделана работа по его внедрению в структуру городского управления. В офисе городского управляющего появилась должность координатора по вопросам устойчивого развития. Также была создана независимая организация, которая будет поддерживать общественные инициативы. Работа нового координатора намеренно не афишируется. Цель состояла в том, чтобы не создавать отдельный департамент по устойчивому развитию. Иначе возник бы риск, что другие подразделения решили бы, будто эта задача их больше не касается. Вместо этого координатор продолжает объединять усилия различных городских департаментов и следить за выполнением целевых показателей, которые были утверждены городским советом в рамках краткосрочного плана работы.

---

### 40. `p1205` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> People were busy, some of the initial enthusiasm for the project had faded and the stakeholders hadn’t really taken ownership of the visioning process. The December meeting arrived, and the staff of the project were getting nervous that there wouldn’t be enough surveys to be credible as a statement by the people of the city about their values and aspirations.

**В озвучку попало:**

> Люди были заняты, первоначальный энтузиазм угас, а заинтересованные стороны так и не взяли на себя ответственность за процесс формирования видения будущего. Наступил декабрь, и команда проекта начала нервничать: анкет могло не хватить, чтобы их результаты стали весомым заявлением о ценностях и стремлениях жителей города.

---

### 41. `p1215` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> When interviewed by a local cable station during one of the events sponsored by the project, the City Manager described how the stakeholder training had changed the tenor of dialogue at City Council meetings. She said that while a take-no-prisoners approach had been the rule in the past, the level of respectful listening and dialogue “changed the political culture of the city.”¹⁰

**В озвучку попало:**

> В интервью местному телеканалу во время одного из мероприятий проекта сити-менеджер рассказала, как обучение заинтересованных сторон изменило тон диалога на заседаниях городского совета. По ее словам, если раньше правилом был бескомпромиссный подход, то теперь уровень уважительного слушания и ведения диалога «изменил политическую культуру города».

---

### 42. `p1227` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Yet over the past five years, Gwendolyn had noticed that the city would benefit from a different approach to long-range planning. A proposal for housing in an open field to the east of the city had created an enormous public outcry as the neighborhood around the field clamored to save the open space for parkland. To stop the proposed development, interim zoning was adopted and the master plan was amended — all symptoms of an underlying planning process that might not reflect the aspirations of the people. As a resident of the city since 2004, Gwendolyn hadn’t been aware of any real outreach on the part of the planning office or the city to get residents involved. So she applied for the job and started work as the Director of Planning and Community Development in Montpelier in November of 2006.

**В озвучку попало:**

> Тем не менее, за последние пять лет Гвендолин заметила, что городу пошел бы на пользу иной подход к долгосрочному планированию. Предложение о застройке открытого поля к востоку от города вызвало огромный общественный резонанс: жители окрестных домов требовали сохранить это пространство как парковую зону. Чтобы остановить строительство, было принято временное зонирование, а в генеральный план внесли поправки. Все это было симптомами того, что существующий процесс планирования не отражал стремлений горожан. Как жительница города с 2004 года, Гвендолин не видела никакой реальной работы со стороны отдела планирования или городских властей по вовлечению жителей. Поэтому она подала заявку на вакансию и в ноябре 2006 года приступила к работе в качестве директора по планированию и развитию сообщества в Монтпилиере.

---

### 43. `p1229` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> From the beginning, enVision Montpelier was framed as a learning process rather than a traditional planning process, a new approach that resulted from reflection about the work Gwendolyn had done in the other cities and towns where she had worked. Rapid change in the 21st century is already the rule, and so taking the traditional approach to planning — relying on experts to provide short-term strategies based on what worked in the past — will be increasingly irrelevant as the level of chaotic change increases. Old solutions won’t work in the new world we find ourselves in, and so the most important dimension of any sustainability planning process is to make all the stakeholders conscious of learning. Adults don’t particularly like to be learners — we like to be knowers and teachers. Taking a learning posture to city planning is much more challenging than it might seem on the surface — city planning has traditionally been left to experts.

**В озвучку попало:**

> С самого начала проект «enVision Montpelier» задумывался как процесс обучения, а не как традиционное планирование. Этот новый подход стал результатом осмысления опыта работы Гвендолин в других городах. Быстрые перемены в двадцать первом веке стали нормой, поэтому традиционный подход — полагаться на экспертов, предлагающих краткосрочные стратегии на основе прошлого опыта — будет становиться все менее актуальным по мере роста хаоса. Старые решения не сработают в новом мире, в котором мы оказались. Поэтому важнейшее измерение любого процесса планирования устойчивого развития — сделать всех участников сознательными учениками. Взрослые не очень любят учиться: нам больше нравится быть знатоками и учителями. Принять позицию ученика в городском планировании гораздо сложнее, чем кажется на первый взгляд, ведь традиционно эта сфера оставалась уделом экспертов.

---

### 44. `p1233` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> The learning objectives each committee developed framed the early part of their work, as they identified different ways to learn what they needed to know about the assets and issues in the Social Systems in Montpelier, for example, and to set goals for the different needs that were identified. The committees invited professionals to come to their meetings and talk about their work; they read material that was developed for them by the VISTA volunteers; they sponsored community forums on topics such as how the faith community could work together or what the democratic town meeting tradition was like in Switzerland.

**В озвучку попало:**

> [thoughtful] Учебные задачи, которые разработал каждый комитет, определили начальный этап их работы. Участники искали способы лучше понять сильные стороны и проблемы социальной сферы Монпелье, чтобы затем поставить цели для решения выявленных потребностей. Комитеты приглашали специалистов на свои встречи, чтобы те рассказали о своей работе. Они также изучали материалы, подготовленные волонтерами программы VISTA, и проводили общественные форумы. На них обсуждали самые разные темы: от сотрудничества религиозных общин до традиций демократических городских собраний в Швейцарии.

---

### 45. `p1253` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> If cities are going to play a role in wealth creation for their residents, establishing the policy framework that supports this role and clearly identifying strategies that incorporate complementary currencies sets the stage for successful city action. The planning processes described in this chapter obviously address more than the issues complementary currencies can help address, but these processes are very important — they create a context where innovative strategies which rely heavily on collective action are possible.

**В озвучку попало:**

> Если города стремятся играть роль в создании благосостояния для своих жителей, им необходимо сформировать политическую базу, поддерживающую эту задачу, и четко определить стратегии с использованием дополнительных валют. Это создаст условия для успешных действий. Описанные в этой главе процессы планирования затрагивают гораздо более широкий круг вопросов, чем те, что можно решить с помощью дополнительных валют. Однако эти процессы крайне важны: они создают среду, в которой становятся возможными инновационные стратегии, опирающиеся на коллективные действия.

---

### 46. `p1267` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Furthermore, anybody who has taken a course in economic theory is convinced that money is a passive medium that simply facilitates exchanges that would have happened otherwise anyway. In other words, the implicit hypothesis underlying the entire economic theory from Adam Smith to today is that different kinds of money wouldn’t encourage different types of exchanges, don’t affect the relationships among their users or motivate different types of investments. In short, for a conventional economist, using another type of money doesn’t make any sense. That is of course true when one compares the use of different national currencies: they are all generated through bank-debt with interest, i.e., they are all of the same type. But there is plenty of empirical evidence from the thousands of complementary currency systems in existence today that using different types of currencies does encourage different kinds of exchanges, and/or significantly changes the relationships among their users.¹ Many complementary currency systems are in fact introduced with the specific aim of changing relationships in a community, and these systems have demonstrated such behavior changes in practice as well.

**В озвучку попало:**

> Более того, любого, кто изучал экономическую теорию, убеждают, что деньги — это лишь пассивное средство обмена. Подразумевается, что они просто облегчают сделки, которые в любом случае состоялись бы и без них. Иными словами, скрытая гипотеза всей экономической мысли от Адама Смита до наших дней заключается в том, что разные виды денег не могут стимулировать разные типы обмена, не влияют на отношения между людьми и не меняют мотивацию инвестиций. Короче говоря, для традиционного экономиста использование другого типа валюты кажется бессмысленным. Конечно, это верно, если сравнивать разные национальные валюты: все они создаются через банковский долг под процент, то есть они одного типа. Но существует множество эмпирических доказательств на примере тысяч систем дополнительных валют, существующих сегодня: использование разных типов денег действительно поощряет иные виды обмена и существенно меняет отношения между пользователями. Многие такие системы внедряются именно с целью изменить общественные связи, и практика подтверждает, что это работает.

---

### 47. `p1268` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> There are two ways to deal with this blind spot that afflicts our collective perception of money. The first way is to deal with it explicitly by providing empirical evidence; and the second is to bypass this entire issue by selective use of vocabulary. There are two classical arguments to justify the existing monopoly of bank-debt money. The first is efficiency; and the second is that complementary currencies have remained invariably marginal compared to the use of “real” money.

**В озвучку попало:**

> Есть два способа справиться с этим «слепым пятном» в нашем восприятии денег. Первый — открыто предоставить эмпирические доказательства. Второй — обойти этот вопрос, используя другой подход к терминологии. Существует два классических аргумента в пользу монополии банковских денег. Первый — это эффективность. Второй — утверждение, что дополнительные валюты всегда оставались маргинальными по сравнению с «настоящими» деньгами.

---

### 48. `p1293` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Perhaps the next time we visit Reykjavik, they will have recreated their own democratic ecology of currencies, instead of the monoculture/monopoly of bank-debt money that has brought them so much hardship. To reduce unemployment and revalue all of their residents, the city may have introduced a mandatory time contribution, not paid in bank-debt money, but rather using an electronic time currency similar to the Japanese *Fureai Kippu*, as a way to simultaneously reduce taxes and give people work to do. A time currency reduces taxes because people spend their time doing things government pays money for — education, senior care, child care, healthcare, keeping the parks and the streets clean, community justice systems where mediation reduces the load in the courts. Time currency reduces unemployment because not everyone can spend time on these things. People who are willing and able to work above and beyond the time requirement could be paid for their time by those who are not. An e-Bay type electronic market could emerge where the city’s time currency could be sold for bank-debt money or whatever else people are interested in exchanging.

**В озвучку попало:**

> Возможно, когда мы в следующий раз посетим Рейкьявик, они воссоздадут свою собственную демократическую экологию валют вместо монокультуры банковских кредитных денег, которая принесла им столько трудностей. Чтобы снизить безработицу и повысить ценность вклада каждого жителя, город мог бы ввести обязательный временной взнос. Он оплачивался бы не банковскими деньгами, а электронной временной валютой, подобной японской системе «Фурэай Киппу». Это стало бы способом одновременно снизить налоги и обеспечить людей работой. Временная валюта уменьшает налоговую нагрузку, потому что люди тратят своё время на то, за что обычно платит государство: образование, уход за пожилыми и детьми, здравоохранение, уборку парков и улиц, а также системы общественного правосудия, где посредничество снижает нагрузку на суды. Временная валюта снижает безработицу, потому что не каждый может посвящать этому всё своё время. Люди, которые хотят и могут работать сверх обязательной нормы, могли бы получать оплату своим временем от тех, кто этого сделать не может. Мог бы появиться электронный рынок, похожий на eBay, где городскую временную валюту можно было бы продать за обычные деньги или обменять на другие интересные людям товары и услуги.

---

### 49. `p1325` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Remember, the starting point for complementary currencies is to meet needs that remain unfulfilled after transactions facilitated with conventional money have taken place. Similarly, unused resources are those that haven’t been used in economic transactions mediated by conventional money.

**В озвучку попало:**

> Помните: отправная точка для введения дополнительных валют — это решение тех задач, которые остаются невыполненными даже после всех операций с обычными деньгами. Аналогичным образом, неиспользуемые ресурсы — это те, что не были задействованы в экономических сделках с использованием традиционной валюты.

---

### 50. `p1360` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> There is a long tradition of more or less formal but small scale local babysitting groups constituted by families who in turn take care of each other ’s children. A large, national-scale Internet-based system is being designed now in Holland, under the name of “Care Miles.” Its aim is to help the 2.3 million families who have trouble finding access to care centers, particularly for the 0-4 year olds.⁶ Community Building Community healing and rebuilding are the most popular reasons for starting complementary currency systems in neighborhoods where there are no major unemployment or economic stress situations. Various designs have been used for such purpose, including Time Bank systems, LETS and Ithaca HOURS. The Balinese time currency described in Chapter 4 could also be considered a well-established system of this nature, operational for more than 1,000 years.

**В озвучку попало:**

> [thoughtful] Существует давняя традиция создания небольших, более или менее формальных групп взаимопомощи, где семьи по очереди присматривают за детьми друг друга. Сейчас в Нидерландах разрабатывается масштабная общенациональная интернет-система под названием «Care Miles». Её цель — помочь двум миллионам тремстам тысячам семей, которые испытывают трудности с доступом к детским учреждениям, особенно для малышей от рождения до четырех лет. [short pause] Укрепление сообщества и его восстановление — самые популярные причины для запуска дополнительных валютных систем в районах, где нет серьезной безработицы или экономического стресса. Для таких целей используются различные модели, включая банки времени, системы LETS и итака-часы. Балийскую валюту времени, описанную в четвертой главе, также можно считать хорошо отлаженной системой такого рода, которая успешно работает уже более тысячи лет.

---

### 51. `p1403` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> The support(s) used for issuing or handling a currency is one of the easiest features to grasp — we are familiar with the various forms that currency comes in — notes, coins and plastic cards, given that conventional money uses practically all of them today. These supports fall into the following types:

**В озвучку попало:**

> [thoughtful] Носители, которые используются для выпуска или обращения валюты — это одна из самых простых для понимания характеристик. Мы хорошо знакомы с различными формами денег: это банкноты, монеты и пластиковые карты, ведь современные официальные деньги используют практически все эти виды. Такие носители можно разделить на следующие типы:

---

### 52. `p1406` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> Paper and Coins Paper and coins are the most familiar form of money today. Paper is the most popular form for contemporary complementary currencies because it is both easy to carry and handle and comparatively cheap to produce (e.g., Ithaca HOURS, WAT bills of exchange, LETS account booklets).

**В озвучку попало:**

> Бумажные деньги и монеты — самая привычная для нас форма денег. Бумага — наиболее популярный вариант для современных дополнительных валют, поскольку её легко носить с собой, удобно использовать, а производство обходится сравнительно недорого. Примеры такого подхода — валюта «Итака часы», векселя WAT или расчётные книжки систем LETS.

---

### 53. `p1410` — длина озвучки / длина оригинала: 0.87; классы правки: —

**Исходный абзац:**

> When several media are used for the same currency, this provides maximum flexibility. The historical evolution of conventional money has traced a logical sequence towards more convenience: currency started with physical commodity money (such as precious metal coins), but now it is more convenient to handle paper receipts with promises to pay that physical commodity (“I will pay to the bearer the sum of one Pound Sterling” is still written on the English currency bills). And of course, if the appropriate technological infrastructure is available, electronic bits are even cheaper to move around than paper currency. The same currency can and often does take different forms depending on the media that supports it. National currency takes many forms: electronic bits, paper or coins.

**В озвучку попало:**

> [thoughtful] Использование нескольких носителей для одной валюты обеспечивает максимальную гибкость. Историческая эволюция традиционных денег шла по пути повышения удобства. Сначала это были физические товары, например, монеты из драгоценных металлов. Затем стало удобнее использовать бумажные расписки с обязательством выплатить этот товар. На английских банкнотах до сих пор пишут: «Я выплачу предъявителю сумму в один фунт стерлингов». Разумеется, при наличии инфраструктуры электронные данные передавать еще дешевле, чем бумажные деньги. Одна и та же валюта может существовать в разных формах. Национальные деньги сегодня — это и электронные записи, и бумажные купюры, и монеты.

---

### 54. `p1435` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Demurrage Charged Currencies The opposite of an interest bearing currency is a demurrage-charged currency. Demurrage is a time related charge on outstanding balances of a currency. It operates exactly like a negative interest rate and is used as a disincentive to hoard the currency. John Maynard Keynes, Silvio Gesell, Irving Fisher and Dieter Suhr provided a strong theoretical foundation for this approach, and it was extensively implemented in the form of *stamp scrip* in the 1930s. Today, the most successful grassroots complementary currency in Japan, the Peanuts, charges a demurrage of 1% per month.

**В озвучку попало:**

> Валюты с демерреджем. Полной противоположностью валютам с процентной ставкой являются валюты с демерреджем. Демерредж — это плата за хранение валюты, зависящая от времени. По сути, это работает как отрицательная процентная ставка и служит инструментом, который отбивает у людей желание накапливать деньги. Джон Мейнард Кейнс, Сильвио Гезель, Ирвинг Фишер и Дитер Зур создали прочную теоретическую базу для этого подхода. В тридцатые годы двадцатого века он широко применялся в виде так называемых «штемпельных денег». Сегодня самая успешная низовая дополнительная валюта в Японии, «Арахис», взимает демерредж в размере одного процента в месяц.

---

### 55. `p1439` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The advantage of interest bearing currencies is that they provide an income to those who create the currency (called *seigniorage*). Its disadvantage is that it implies a systematic money transfer from people who don’t have money to those who do, so that it tends to concentrate wealth. It also gives an incentive to save in the form of currency as opposed to real assets. Finally, it provides a systematic incentive to think only short-term, as income generated in the distant future is discounted to irrelevance with positive interest-rate currencies.

**В озвучку попало:**

> Преимущество валют с процентной ставкой заключается в том, что они приносят доход тем, кто их создаёт. Это называется сеньоражем. Недостаток же в том, что такая система подразумевает систематический перенос денег от тех, у кого их нет, к тем, у кого они есть, что способствует концентрации богатства. Кроме того, это стимулирует сбережения в денежной форме, а не в реальных активах. Наконец, это побуждает мыслить только краткосрочными категориями, поскольку доход, ожидаемый в далёком будущем, обесценивается из-за положительной процентной ставки.

---

### 56. `p1468` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Mutual credit has as significant advantage: the quantity of money created by definition always perfectly matches need. There are also no risks of inflation in mutual credit systems. By contrast, overissuing is the biggest risk run by currencies that are created by borrowing without collateral or by central issue. It is important with these latter models to cautiously control the quantity of currency issued, otherwise its depreciation and loss of credibility is a predictable outcome.

**В озвучку попало:**

> У взаимного кредита есть существенное преимущество: объем создаваемых денег по определению всегда точно соответствует потребностям. В таких системах нет риска инфляции. Напротив, чрезмерная эмиссия — главный риск для валют, создаваемых через беззалоговое заимствование или централизованный выпуск. В этих моделях важно осторожно контролировать количество выпускаемой валюты. В противном случае ее обесценивание и потеря доверия становятся предсказуемым итогом.

---

### 57. `p1474` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> The first option is not to recover any of the costs. For the complementary currency component of the costs, most mutual credit systems simply open an account for “general overhead,” people doing work for the system are credited and this overhead account is debited.

**В озвучку попало:**

> [serious] Первый вариант — не возмещать расходы вовсе. Что касается затрат в дополнительной валюте, большинство систем взаимного кредита просто открывают счет «общих накладных расходов». Людям, выполняющим работу для системы, начисляются кредиты, а этот счет дебетуется.

---

### 58. `p1515` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> The LETS program was established around 1983, introducing the *green* *dollar* (the LETS currency). This system allowed people to exchange goods and services with one another even when they didn’t have access a lot of official Canadian dollars. The LETS network allowed members to participate in the economy without needing an employer or having money to spend. An additional positive aspect of LETS in Courtenay was that the use of green dollars freed up more Canadian dollars for other uses. It was also an efficient and inexpensive way for local businesses to advertise, since participating businesses were listed in a local directory.

**В озвучку попало:**

> Программа LETS была создана примерно в 1983 году. Она ввела в обращение так называемый «зеленый доллар» — валюту этой системы. Она позволила людям обмениваться товарами и услугами, даже если у них не было доступа к большому количеству официальных канадских долларов. Сеть LETS позволила участникам участвовать в экономике, не нуждаясь в работодателе или наличных деньгах. Дополнительным плюсом системы в Кортни стало то, что использование «зеленых долларов» высвобождало канадские доллары для других целей. Кроме того, это был эффективный и недорогой способ рекламы для местного бизнеса, так как участвующие компании вносились в общий справочник.

---

### 59. `p1546` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> The Guide is based on the idea that we can satisfy our common human needs by building on our strengths, intervening at the system level and integrating all the different parts of community life into a whole package, rather than trying to tinker with different problems in isolation.

**В озвучку попало:**

> В основе этого руководства лежит идея о том, что мы можем удовлетворять наши общие человеческие потребности, опираясь на сильные стороны, воздействуя на систему в целом и объединяя все сферы жизни сообщества в единый комплекс. Это гораздо эффективнее, чем пытаться решать разрозненные проблемы по отдельности.

---

### 60. `p1547` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> The principles and activities outlined in *LASER* are relevant whether you live in a rural village in Afghanistan or a neighborhood in a modern western city. The details will obviously differ, but the broad opportunities exist everywhere. All it takes is you. *LASER* describes how you can take control of your own future and begin to create the sort of economy that will bring real jobs, real prosperity and a high quality of life to you and your family.

**В озвучку попало:**

> Принципы и методы, описанные в LASER, актуальны везде: будь то сельская деревня в Афганистане или район современного западного города. Детали, конечно, будут различаться, но широкие возможности существуют повсюду. Всё, что нужно — это вы. LASER описывает, как взять контроль над своим будущим и начать создавать такую экономику, которая принесет реальные рабочие места, процветание и высокое качество жизни вам и вашей семье.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0990` — длина озвучки / длина оригинала: 0.66; классы правки: —

**Исходный абзац:**

> These cities sent a message to the public that city planning is fun and interesting, and in all cases, people responded by getting involved, either by simply filling out the visioning surveys or by joining stakeholder groups. Some took their interests a step further and stepped up to serve on the City Council or Planning Commissions.

**В озвучку попало:**

> Эти города дали понять: планирование — это интересно. И люди откликнулись: они заполняли анкеты и присоединялись к рабочим группам. Некоторые пошли дальше и стали работать в городском совете или комиссиях по планированию.

---

### 2. `p0689` — длина озвучки / длина оригинала: 0.70; классы правки: —

**Исходный абзац:**

> Businesses providing goods and services that reduce carbon emissions or those that have formally engaged in sustainability activities (green businesses) could accept carbon currency units (CCUs) as a loyalty currency in partial payment for additional carbon-reducing goods and services. Each business would decide what percentage of an invoice or bill they are willing to accept in CCUs (which in turn could be tied to its value on the carbon market). An electric or hybrid car dealer, for example, could decide to accept 10% of the purchase of a new car in CCUs, whereas a shop selling energy efficient light bulbs or solar panels might accept 20% of their payment in this currency.

**В озвучку попало:**

> Компании, предлагающие экологичные товары и услуги, могли бы принимать единицы углеродной валюты в качестве бонусов или частичной оплаты. Каждый бизнес сам решал бы, какой процент от счета готов принять в этих единицах, стоимость которых была бы привязана к рынку углеродных квот. Например, дилер электромобилей мог бы принимать углеродные единицы в счет десяти процентов стоимости новой машины, а магазин энергосберегающих ламп или солнечных панелей — в счет двадцати процентов.

---

### 3. `p0956` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> The light bulb went on, and the ideas for a local food currency started to gel. If there was underutilized food storage capacity in the region and if food storage in general was something we wanted to foster to develop better local food security, then this might provide the basis for a currency.

**В озвучку попало:**

> Идея сразу стала понятной и начала обретать форму. Если в регионе есть свободные мощности для хранения еды и если мы хотим развивать продовольственную безопасность, то именно это может стать основой для валюты.

---

### 4. `p0710` — длина озвучки / длина оригинала: 0.73; классы правки: —

**Исходный абзац:**

> Aside from the obvious advantages of creating a supplementary eco-currency like the Biwa Kippu, the system has several additional benefits. The sale of Biwas to those who haven’t earned enough Biwas through their own environmental activities would provide an income source for environmental non-governmental organizations and activists. Research has shown that more people volunteer and that the turnover of volunteers in nonprofit organizations is significantly reduced when a complementary currency is used to reward volunteers.⁸ Because of these two effects, more nonprofit organizations that focus on environmental needs will tend to emerge spontaneously in Shiga Prefecture.

**В озвучку попало:**

> [thoughtful] Помимо очевидных преимуществ, у системы есть дополнительные плюсы. Продажа «Бив» тем, кто не заработал их самостоятельно, станет источником дохода для экологических некоммерческих организаций и активистов. Исследования показывают, что использование дополнительных валют для поощрения волонтеров повышает их число и значительно снижает текучесть кадров в некоммерческом секторе. Благодаря этому в префектуре Сига будет естественным образом появляться больше экологических организаций.

---

### 5. `p0211` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> Once upon a time, there was a small village where people knew nothing about money or interest. Each market day, people would bring their chickens, eggs, hams and breads to the marketplace and enter into the time-honored ritual of negotiations and exchange for what they needed with one another. At harvests, or whenever someone’s barn needed repairs after a storm, the villagers simply exercised another age-old tradition of helping one another, knowing that if they themselves had a problem one day, others would surely come to their aid in turn.

**В озвучку попало:**

> [thoughtful] Когда-то в одной маленькой деревне люди ничего не знали о деньгах и процентах. В рыночные дни они приносили кур, яйца, ветчину и хлеб, чтобы обменять их на то, что им было нужно. Это был старинный ритуал. А во время сбора урожая или когда после бури нужно было починить чей-то сарай, жители просто помогали друг другу. Они знали: если беда случится у них, соседи обязательно придут на помощь.

---

### 6. `p0856` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> The skills and capacities we need to take care of each other are not scarce, however. Human beings are richly endowed with the capacity to love and nurture each other. It is arguably one of our innate survival skills — everyone knows how to do it, with the rare exception of people who are born with mental disabilities or illnesses that make them sociopaths on some level. In an ideal world, the knowledge and skills we would need to provide adequate nutrition and healthcare would be something we learned as we matured, since these would have been provided to us by our parents and extended family.

**В озвучку попало:**

> При этом навыки и способности, необходимые для заботы друг о друге, вовсе не являются дефицитом. Люди от природы наделены способностью любить и поддерживать близких. Это один из наших врожденных навыков выживания. Почти каждый умеет это делать, за редким исключением людей с серьезными психическими отклонениями. В идеальном мире мы бы учились основам питания и ухода за близкими еще в детстве, перенимая этот опыт у родителей и старших родственников.

---

### 7. `p1125` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> The intermediate level training was given to the consulting team that Calgary hired to manage the Working Groups. Two facilitators were assigned to each group, one to lead the discussion and one to keep a record of their work. In addition, the team members from the planning office also attended each meeting. At this level, the facilitators and record keepers needed to be able to not only understand the diagrams and the logic of systems dynamics that was presented to the group, but they needed to be able to explain it to other people. The workshops for this group were designed as more hands-on training, so they worked with different systems diagrams and were given more practice applying the ideas to real life situations.

**В озвучку попало:**

> Средний уровень обучения прошли консультанты, нанятые Калгари для управления рабочими группами. К каждой группе прикрепили двух фасилитаторов: один вел дискуссию, другой фиксировал ход работы. Кроме того, на встречах присутствовали сотрудники планового отдела. На этом уровне фасилитаторы и секретари должны были не просто понимать логику системной динамики, но и уметь доступно объяснить её другим. Семинары для этой группы были ориентированы на практику: они работали с различными диаграммами и учились применять системные идеи к реальным ситуациям.

---

### 8. `p0349` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> Clearcutting the forest might produce some monetary income for a short period of time for a limited number of people, but it is spending down the region’s capital, just as if you start to use the principal of the savings account that you have in the bank instead of taking the interest income to pay for your expenses. If spending capital goes on for too long, you won’t have any money left. Strengthening our natural capital involves finding ways to protect and enhance those natural systems that provide the environmental services we need — air, water, climate, soil, food, waste assimilation, beauty, recreation, materials — without undermining their capacity to continue to provide the services in the future.

**В озвучку попало:**

> Сплошная вырубка леса может принести быстрый доход небольшой группе людей. Но по сути, это проедание регионального капитала. Это всё равно что тратить основной вклад в банке вместо того, чтобы жить на проценты. Если долго расходовать капитал, в итоге вы останетесь ни с чем. Укрепление природного капитала требует защиты и развития экосистем, которые обеспечивают нас всем необходимым: воздухом, водой, климатом, почвой, едой и материалами. Мы должны пользоваться этими благами, не подрывая способность природы воспроизводить их в будущем.

---

### 9. `p0991` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> A second challenge for cities trying to develop a shared vision for the future is the subject matter of the vision statement. Vague generalities about being a livable city aren’t enough to carry more difficult policy agendas forward when priorities are set and trade-offs need to be made. An overarching view is important, but the vision needs to be detailed enough so that direction is clear.

**В озвучку попало:**

> Вторая проблема при создании общего видения — это содержание самой стратегии. Туманных фраз о «комфортном городе» недостаточно, когда дело доходит до сложных решений и выбора приоритетов. Общий взгляд важен, но видение должно быть достаточно детализированным, чтобы направление движения было ясным.

---

### 10. `p0883` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> At the *specialized* level, you make a higher commitment of time and money each month — eight hours of time and $15 per month for each service cluster you need. This level helps members have access to preventive care services and more highly specialized skills, like those of electricians and carpenters. The preventive services include things like massage therapy, chiropractic care, exercise and yoga classes, herbal therapy and other alternative and complementary healthcare services. The access to these services attracts a broad spectrum of the community to the system and provides the Care Bank with a solid foundation of people’s time to continue to offer the assisted level of care to others.

**В озвучку попало:**

> На специализированном уровне обязательства выше: восемь часов времени и 15 долларов в месяц за каждый пакет услуг. Этот уровень дает доступ к профилактике и помощи высококвалифицированных специалистов, таких как электрики или плотники. Профилактические услуги включают массаж, хиропрактику, занятия йогой, фитотерапию и другие методы дополнительной медицины. Доступ к таким услугам привлекает в систему широкий круг людей и создает прочную основу, позволяющую банку заботы поддерживать работу ассистированного уровня для всех остальных.

---

### 11. `p1193` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Lesson learned: it is critically important to involve youth in the training, but do it when a whole room of adults can help keep them on task by having them participate in the same training as the adults. The fact that the adults were required to take the same training was one of the important pieces of information Gwendolyn gave the youth group — this raised eyebrows and got them to sit up a bit straighter. Of course, being in the same training as the adults would accomplish this same goal.

**В озвучку попало:**

> Вывод: крайне важно вовлекать молодёжь в обучение, но лучше делать это тогда, когда взрослые помогают им сосредоточиться, участвуя в том же тренинге. Тот факт, что взрослые проходили через те же испытания, был важным аргументом для подростков — это заставило их выпрямить спины и отнестись к делу серьёзнее. Разумеется, совместное обучение с самого начала дало бы тот же результат.

---

### 12. `p0823` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> These tokens could be redeemed in part for other services or goods that further promote health, ranging, for instance, from partial payment for preventive therapies to buying or repairing a bicycle or buying appropriate foods. Another use of the tokens could be in partial payment for the insurance premiums, given that participants in this system should have a lower probability of getting or remaining sick. This logic is what justifies the Elderplan Insurance Company in Brooklyn accepting 25% of its health insurance premium for elderly participants in a local Time Bank.¹²

**В озвучку попало:**

> Эти токены можно частично использовать для оплаты товаров и услуг, поддерживающих здоровье: от профилактической терапии до покупки велосипеда или полезных продуктов. Еще один вариант — частичная оплата страховых взносов, ведь участники такой системы с меньшей вероятностью заболеют. Именно эта логика оправдывает решение страховой компании «Элдерплан» в Бруклине принимать в качестве оплаты части страхового взноса баллы местного «Банка времени».

---

### 13. `p0818` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> We know how frequent flyer miles can successfully encourage particular customer behavior patterns, i.e., loyalty to a particular airline alliance. Now imagine a complementary currency — let’s call them Wellness Tokens — that would encourage people to take on healthy habits and practices. For example, one hour of exercise at a gym would earn one Wellness Token; or specific preventive treatments could similarly be encouraged with Wellness Tokens.

**В озвучку попало:**

> Мы знаем, как эффективно работают бонусные мили авиакомпаний, формируя лояльность клиентов. Теперь представьте дополнительную валюту — назовем её «оздоровительными токенами» — которая поощряла бы людей формировать полезные привычки. Например, час тренировки в спортзале или прохождение профилактических процедур приносили бы человеку такие токены.

---

### 14. `p0414` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The second example of demurrage, or negative interest money, was special coinage used for local payments during the Central Middle Ages in Europe. These coins were produced by monasteries, bishops, provincial aristocracy and townships, and bore the resemblance of the current Bishop, Lord or King (*seignoriage* means fees earned through an authority’s issuance of standardized currency, and it is derived from the Old French *seignior*, or lord).³ During Carolingian times, the coins were changed when the rulers changed (a practice called *renovatio monetae*), and a recoinage tax would be assessed on the coins that were turned in. So the last person holding the coins would end up paying the tax. This provided a strong incentive to spend money rather than hoarding it for the future. However, instead of waiting for a lord to die, *renovatio monetae* evolved to a system where every five or six years coins would be reissued. The recoinage dates were not always predictable, and the abuse of this practice resulted in more frequent recalls, the first of which was in England when Harold I recoined only three years after Cnut had done so, and then Harthcnut did it again two years later. Archbishop Wichmann of Magdeburg revoked the money in his domain twice per year!⁴

**В озвучку попало:**

> Вторым примером демереджа, или денег с отрицательным процентом, была особая чеканка монет для местных платежей в Европе эпохи Средневековья. Эти монеты выпускались монастырями, епископами, местной знатью и городами и несли изображение правящего епископа, лорда или короля. В эпоху Каролингов монеты менялись при смене правителей, и с тех, кто сдавал старые монеты, взимался налог на перечеканку. Таким образом, последний владелец монет в итоге оплачивал этот сбор. Это давало сильный стимул тратить деньги, а не копить их на будущее. Однако со временем практика перечеканки эволюционировала: монеты стали выпускать заново каждые пять-шесть лет. Даты перечеканки не всегда были предсказуемыми, а злоупотребление этой практикой приводило к более частым отзывам. Например, в Англии Гарольд Первый провел перечеканку всего через три года после Кнута, а Хардекнут повторил это еще через два года. А архиепископ Вихман Магдебургский и вовсе изымал деньги из обращения в своих владениях дважды в год.

---

### 15. `p0273` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The external factors that influence the outcome of any business venture are the demand for the product, competition for sales of the same or similar products, the costs of production, tax rates and the cost of money. Most of these cost factors are directly related to the product, and need to be considered in the overall business plan when determining if the venture will be profitable.

**В озвучку попало:**

> На успех любого бизнес-проекта влияют внешние факторы: спрос на продукт, конкуренция, производственные затраты, налоговые ставки и стоимость денег. Большинство этих факторов напрямую связаны с самим продуктом. Их необходимо учитывать в общем бизнес-плане, чтобы понять, будет ли предприятие прибыльным.

---

### 16. `p0825` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Participants in such a group would agree to a mutual *wellness contract*, so that the whole group would be affected by the results of each member. For instance, assuming that a group of five people are involved in an obesity reduction program, both the individual and the group weight reduction objectives could be used as a criteria for obtaining Wellness Tokens. In this example, independently verifiable, quantitative results could even be used in a contract with the Wellness Alliance.

**В озвучку попало:**

> Участники такой группы могли бы заключать «контракт здоровья», чтобы результаты каждого члена влияли на общую группу. Например, если пять человек участвуют в программе снижения веса, критерием для получения токенов могут стать как индивидуальные, так и общие цели. В таком случае проверяемые количественные показатели могут стать основой официального соглашения с Альянсом здоровья.

---

### 17. `p0987` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> If the goal is to create a vision statement that does reflect the values of the whole community, how do you get the whole community involved? Most city leaders hold traditional public hearings on policy initiatives, to try to encourage public input. They draft the policy proposal, and they ask the public to comment on it before it becomes official. They complain of community apathy when only a small group of people show up for a hearing, typically at City Hall. Cities that have done a good job of community engagement have learned to attract more people to their policy discussions by structuring the possibilities for public input as the kind of activities that people normally like to attend, like sporting events, celebrations and cultural events. If you make the policy process fun instead of being wonkish and boring, you are more likely to have more people participate.

**В озвучку попало:**

> Если цель — создать стратегию, отражающую ценности всех горожан, как добиться их участия? Большинство городских руководителей ограничиваются традиционными публичными слушаниями. Они готовят проект политики и просят общественность прокомментировать его до официального принятия. А потом сетуют на апатию, когда на слушания в мэрию приходит лишь горстка людей. Города, преуспевшие в вовлечении сообщества, пошли другим путём. Они превращают обсуждения в мероприятия, на которые людям действительно хочется прийти: спортивные праздники, фестивали или культурные события. Если сделать процесс обсуждения живым и интересным, а не скучным и бюрократическим, шансы на массовое участие возрастают.

---

### 18. `p0621` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> If a city makes it mandatory for everyone to pay some contribution every year in a form of complementary currency or accepts partial payment in complementary currencies for some regular taxes and fees, the demand for that currency will significantly increase and therefore obtain a value that it has not had previously. Remember, the main systemic reason we universally accept privately created bank-debt dollars right now is that they are the *only* legal form by which we can pay our taxes.

**В озвучку попало:**

> [thoughtful] Если город сделает обязательным ежегодный взнос в такой валюте или разрешит частично оплачивать ею налоги и сборы, спрос на нее значительно вырастет. В результате она обретет ценность, которой раньше не имела. Помните: главная системная причина, по которой мы все принимаем частные банковские доллары, заключается в том, что это единственный законный способ уплаты налогов.

---

### 19. `p1077` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Gwendolyn attended the ICLEI World Congress in 2000, and was inspired by the connection between what she had seen on the grassroots level in Burlington and on the global level with the Earth Charter — the similarities between the two processes were a clear indication that there was something universal in the aspirations shared by people all over the world that transcended all political, religious, national and cultural boundaries. When she got back to Vermont, she immediately started work to bring the Earth Charter to people and local governments there.

**В озвучку попало:**

> Гвендолин посетила тот конгресс в 2000 году. Её вдохновила связь между тем, что она видела на низовом уровне в Берлингтоне, и глобальным масштабом Хартии Земли. Сходство этих процессов ясно указывало: стремления людей во всём мире универсальны. Они преодолевают любые политические, религиозные, национальные и культурные границы. Вернувшись в Вермонт, она немедленно начала работу по продвижению Хартии среди местных жителей и органов власти.

---

### 20. `p1207` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> He had gone to his principal, who in turn directed him to the school board to obtain permission to distribute the surveys to all the children in the schools. The school board had given him the OK, and he had personally visited a lot of the schools with the surveys in hand.

**В озвучку попало:**

> Он обратился к директору своей школы, который направил его в школьный совет за разрешением на распространение анкет среди всех детей. Получив одобрение, Винни лично обошел множество школ с пачками опросников в руках.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0115` — длина озвучки / длина оригинала: 1.39; классы правки: —

**Исходный абзац:**

> The appeal of big prize lottery tickets comes in part from the fantasy the tickets allow. We imagine all the things we could do, charities, projects, real change that we could help make happen. There is no denying the appeal of vast sums of money. In our dreams, money solves all our problems, gives us resources to meet needs we never knew we had. But is it wealth?

**В озвучку попало:**

> [thoughtful] Привлекательность лотерейных билетов с огромными выигрышами отчасти объясняется фантазиями, которые они позволяют нам строить. Мы представляем, сколько всего могли бы сделать: помочь благотворительным организациям, запустить важные проекты или добиться реальных перемен. Трудно отрицать притягательность больших денег. В своих мечтах мы видим, как деньги решают все наши проблемы и дают ресурсы для удовлетворения потребностей, о которых мы даже не подозревали. Но можно ли назвать это богатством?

---

### 2. `p0284` — длина озвучки / длина оригинала: 1.36; классы правки: —

**Исходный абзац:**

> The total US credit market, i.e., borrowing by governments, corporations and individuals, is as close to a statistical fit of an exponential curve as is scientifically possible. (For those with an econometric background, the R2 value of .9889 means that it is almost a perfect fit.)¹⁴

**В озвучку попало:**

> Общий объём кредитного рынка США, то есть заимствования правительств, корпораций и частных лиц, максимально близок к экспоненциальной кривой, насколько это вообще возможно с научной точки зрения. Для тех, кто знаком с эконометрикой, поясню: коэффициент детерминации ноль целых девять тысяч восемьсот восемьдесят девять десятитысячных означает, что это практически идеальное соответствие.

---

### 3. `p0806` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> Studies on employee activity programs reveal that the productivity of the people involved increased by 12%,8 and absenteeism dropped by up to 45%.⁹ Estimates of the impact of healthcare costs on corporations show a rise from 7% thirty years ago to up to 50% of the corporate profits now. This is why some individual companies are investing in wellness directly. For instance, Johnson & Johnson spends $4.5 million per year on staff wellness programs, avoiding thereby medical costs estimated at $13 million per year. But individual corporate solutions may not be the most effective way to solve the problem.

**В озвучку попало:**

> [serious] Исследования программ активности сотрудников показывают, что производительность труда участников возрастает на двенадцать процентов, а количество прогулов снижается почти наполовину. Оценки влияния расходов на здравоохранение на бизнес показывают тревожный рост: если тридцать лет назад они составляли семь процентов от корпоративной прибыли, то сегодня — до пятидесяти. Именно поэтому некоторые компании инвестируют в здоровье сотрудников напрямую. Например, компания «Джонсон и Джонсон» ежегодно тратит четыре с половиной миллиона долларов на оздоровительные программы, что позволяет избежать медицинских расходов на сумму около тринадцати миллионов долларов в год. Однако частные корпоративные решения могут быть не самым эффективным способом борьбы с этой проблемой.

---

### 4. `p0281` — длина озвучки / длина оригинала: 1.27; классы правки: —

**Исходный абзац:**

> In our current era, where high priced oil and overleveraged assets triggered an economic collapse which forced the US government to provide huge “bailout” loans to banks (created with government bonds and debt) and then other huge “stimulus” grants to state and local governments and businesses (also created with government bonds and debt), this system dynamics hypothesis seems to hold true.

**В озвучку попало:**

> [serious] В наше время дорогая нефть и чрезмерно закредитованные активы спровоцировали экономический крах. Это вынудило правительство Соединённых Штатов предоставить банкам огромные кредиты для спасения, которые были созданы за счёт государственных облигаций и долгов. Затем последовали другие масштабные вливания в виде грантов для штатов, местных органов власти и бизнеса, которые также были обеспечены государственным долгом. Похоже, что эта гипотеза системной динамики подтверждается на практике.

---

### 5. `p1070` — длина озвучки / длина оригинала: 1.25; классы правки: —

**Исходный абзац:**

> Ultimately, the administrative burden and cost of maintaining a paper currency spelled the demise of Burlington Bread, and it doesn’t exist today. It was replaced in Burlington with a Time Bank system that serves the North end of town, a traditionally low-income area, and a new commercial barter system called the Vermont Sustainable Exchange. Since both of these systems are structured as mutual credit systems, they are easier to manage and have promise for long life.

**В озвучку попало:**

> [sad] В конечном итоге, административные сложности и расходы на поддержание бумажной валюты привели к тому, что «Берлингтонский хлеб» прекратил свое существование. Сейчас его уже нет. В Берлингтоне на смену ему пришли другие системы. Во-первых, это «Банк времени», который обслуживает северную часть города — район с традиционно низким уровнем дохода. Во-вторых, новая система коммерческого бартера под названием «Вермонтская биржа устойчивого развития». Поскольку обе эти системы устроены как механизмы взаимного кредитования, ими проще управлять, и у них есть все шансы на долгую жизнь.

---

### 6. `p0874` — длина озвучки / длина оригинала: 1.25; классы правки: —

**Исходный абзац:**

> We need each other. Networks are stronger than individuals. People helping each other reweave communities of support, strength & trust. Community is built upon sinking roots, building trust, creating networks. Special relationships are built on commitment.

**В озвучку попало:**

> [thoughtful] Мы нужны друг другу. Сети всегда сильнее, чем отдельные люди. Когда мы помогаем друг другу, мы заново создаем сообщества, основанные на поддержке, силе и доверии. Сообщество строится на том, чтобы пустить корни, укрепить доверие и создать связи. Особые отношения всегда строятся на взаимных обязательствах.

---

### 7. `p0797` — длина озвучки / длина оригинала: 1.24; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> In 2004, more than one million Americans were financially ruined by illness or medical bills. Most were middle class. Each year, two million Americans face the double disaster of illness and bankruptcy. But the bigger surprise is that ¾ of the medically bankrupt had health insurance. Too sick to work, they suddenly lost their jobs. With the jobs went most of their income and their health insurance — ¼ of all employers cancel coverage the day employees leave work because of a disabling illness; another ¼ do so in less than a year.

**В озвучку попало:**

> [serious] В две тысячи четвёртом году более миллиона американцев оказались на грани разорения из-за болезней или медицинских счетов. Большинство из них принадлежали к среднему классу. Каждый год два миллиона жителей США сталкиваются с двойной бедой: тяжёлым недугом и банкротством. Но самое удивительное, что три четверти из тех, кто обанкротился из-за медицинских расходов, имели медицинскую страховку. Став слишком больными для работы, они внезапно теряли свои места. Вместе с работой уходили доход и страховка. Четверть всех работодателей аннулируют полис в тот же день, когда сотрудник увольняется из-за инвалидности, а ещё четверть делают это в течение года.

---

### 8. `p0798` — длина озвучки / длина оригинала: 1.24; классы правки: —

**Исходный абзац:**

> Bankrupt families lost more than just assets. One out of five went without food. One third had their utilities shut off, and nearly skipped needed doctor or dentist visits. These families arrived at the bankruptcy courthouse exhausted and emotionally spent, brought low by a medical system that could offer physical cures but that left them financially devastated.

**В озвучку попало:**

> [sad] Семьи банкротов теряли не только имущество. Каждый пятый оставался без еды. У трети отключали коммунальные услуги, и почти все они были вынуждены пропускать необходимые визиты к врачу или стоматологу. Эти люди приходили в суд по делам о банкротстве измождёнными и эмоционально опустошёнными. Их доводила до отчаяния медицинская система, которая могла предложить физическое исцеление, но оставляла пациентов в состоянии полной финансовой разрухи.

---

### 9. `p0348` — длина озвучки / длина оригинала: 1.24; классы правки: —

**Исходный абзац:**

> Natural capital is the stock of environmental assets that produces more assets; for example, a healthy forest produces trees, habitat, carbon sequestration, erosion control, beauty, recreation and water purification if the natural capital base — its essential regenerative capacity — is maintained.

**В озвучку попало:**

> Природный капитал — это совокупность экологических ресурсов, которые приносят новые блага. Например, здоровый лес дает древесину, среду обитания для животных, поглощает углекислый газ, предотвращает эрозию почвы, радует глаз, служит местом для отдыха и очищает воду. Все это возможно, если мы сохраняем основу природного капитала — его способность к самовосстановлению.

---

### 10. `p1034` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> Legacy launched its No Idling Campaign in April 2007 with public outreach, education and policy advocacy efforts to reduce unnecessary vehicle idling as a way to improve air quality and overall quality of life for everyone who lives, works and plays in Burlington.⁶ The campaign worked with the city to enforce a city policy already on the books about city vehicles idling, and proposed an idling ordinance for the city to adopt. In March of 2008, the City Council passed a resolution directing the Public Works Commission to amend their parking ordinances to accommodate the anti-idling requirements.

**В озвучку попало:**

> [serious] В апреле 2007 года организация «Легаси» запустила кампанию «Стоп холостой ход». Она включала просветительскую работу, информирование общественности и адвокацию политики, направленной на сокращение необоснованной работы двигателей на холостом ходу. Цель состояла в том, чтобы улучшить качество воздуха и общие условия жизни для всех, кто живет, работает и отдыхает в Берлингтоне. Кампания взаимодействовала с городскими властями для обеспечения соблюдения уже существующих правил в отношении служебного транспорта и предложила городу принять официальный указ о запрете холостого хода. В марте 2008 года городской совет принял резолюцию, поручившую комиссии по общественным работам внести соответствующие изменения в правила парковки.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1544` — совпадение символов с оригиналом: 32%; классы правки: —

**Исходный абзац:**

> Global Community Initiatives has worked in partnership with Natural Capitalism Solutions and the America’s Development Foundation to create a new workbook for local communities to revitalize and develop their local economies in ways that build real wealth, enhance the quality of life and protect and restore the natural environment. The workbook is called *LASER* — *Local Action for* *Sustainable Economic Renewal*.

**В озвучку попало:**

> Организация Global Community Initiatives в партнерстве с Natural Capitalism Solutions и America’s Development Foundation разработала новое практическое руководство для местных сообществ. Оно помогает возрождать и развивать экономику так, чтобы приумножать реальные богатства, повышать качество жизни, а также защищать и восстанавливать природную среду. Это руководство называется LASER — «Местные действия для устойчивого экономического обновления».

---

### 2. `p1150` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Developing the vision was a celebration of community participation and imagination! It was an adventure in exploring values, building on assets and incorporating citizens’ hopes and dreams for the next 100 years. Based upon the success of Imagine Chicago and other community movements around the world, imagineCALGARY reached out to Calgarians using a variety of strategies. Over 18,000 responded via:

**В озвучку попало:**

> Разработка этого видения стала настоящим праздником участия и воображения! Это было приключение, в ходе которого жители исследовали свои ценности, опирались на сильные стороны города и делились надеждами и мечтами на ближайшие сто лет. Вдохновившись успехом движения «Imagine Chicago» и другими подобными инициативами по всему миру, проект «imagineCALGARY» использовал множество стратегий взаимодействия. Более восемнадцати тысяч человек откликнулись через:

---

### 3. `p0880` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> At the *basic* level, REACH works like a Time Bank. You make a donation to the organization of either $25/year or offer two hours of assistance with a fundraiser for the organization. Then you post the things you are willing to do for the Time Bank — your offers — and the things you would like someone to do for you — your requests. The posting is made using the Community Weaver software developed by Time Banks USA. A central website keeps track of all the members, their requests, their offers and the time dollars or, in Montpelier ’s case the Community Credits, that are exchanged by members.

**В озвучку попало:**

> [thoughtful] На базовом уровне REACH работает как обычный тайм-банк. Вы делаете взнос в размере 25 долларов в год или отрабатываете два часа на благо организации. Затем вы публикуете свои предложения — то, что готовы сделать для других, — и свои запросы — то, что нужно вам. Все это происходит через программное обеспечение «Community Weaver». Центральный сайт отслеживает участников, их запросы, предложения и обмен «тайм-долларами» или, как их называют в Монтпилиере, «общественными кредитами».

---

### 4. `p0879` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> Montpelier, the capital city of Vermont, has created both a Time Bank and a Care Bank. The Onion River Exchange is a standard Time Bank, where members post their offers and requests and trade with each other as often as they like. The city also received a federal grant from the US Administration on Aging to create the Rural Elder Assistance for Care and Health (REACH) program. REACH expands traditional Time Bank membership types to include three levels: basic, assisted and specialized.

**В озвучку попало:**

> В Монтпилиере, столице штата Вермонт, созданы и тайм-банк, и банк заботы. «Onion River Exchange» — это классический тайм-банк, где участники свободно обмениваются услугами. Кроме того, город получил федеральный грант на создание программы помощи пожилым людям в сельской местности, известной как REACH. Эта программа расширяет традиционную модель, предлагая три уровня участия: базовый, ассистированный и специализированный.

---

### 5. `p1171` — совпадение символов с оригиналом: 18%; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Since the adoption of the plan, Calgary has won several awards for its work in this area. The Canadian Urban Institute presented imagine-CALGARY with its 2009 Natural City Award to recognize the role the plan has played in creating a sustainable future for the community. Other awards the city received include the Municipal Sustainability Innovator Community Award from the Alberta Urban Municipalities Association and the CH2M Hill Sustainable Communities Award from the Federation of Canadian Municipalities.

**В озвучку попало:**

> [serious] С момента принятия плана Калгари получил несколько наград за свою работу в этой области. Канадский институт урбанистики вручил проекту «ImagineCALGARY» премию «Natural City Award» за две тысячи девятый год. Так была отмечена роль плана в создании устойчивого будущего для общества. Среди других наград, полученных городом, — премия за инновации в области муниципальной устойчивости от Ассоциации городских муниципалитетов Альберты, а также награда за устойчивое развитие сообществ от Федерации канадских муниципалитетов.

---

### 6. `p1175` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> One of the benefits to Calgary Dollars of the imagineCALGARY project was that its importance to the different goals and objectives the city established was articulated in the long-term plan the city developed. This raised awareness among a broader range of stakeholders about the currency and linked it to city objectives.

**В озвучку попало:**

> Одним из преимуществ «imagineCALGARY» для «Калгари Долларс» стало то, что значимость этой валюты для различных городских целей и задач была четко прописана в долгосрочном плане развития города. Это повысило осведомленность среди широкого круга заинтересованных сторон и связало использование валюты с официальными целями города.

---

### 7. `p0876` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Every human being matters. Respect underlies freedom of speech, freedom of religion, and everything we value. Respect supplies the heart and soul of democracy. When respect is denied to anyone, we all are injured. We must respect where people are in the moment, not where we hope they will be at some future point.6

**В озвучку попало:**

> [serious] Каждый человек имеет значение. Уважение лежит в основе свободы слова, свободы вероисповедания и всего, что мы ценим. Оно — сердце и душа демократии. Когда в уважении отказывают кому-то одному, страдают все. Мы должны принимать людей такими, какие они есть сейчас, а не такими, какими мы хотим видеть их в будущем.

---

### 8. `p1237` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> The three currencies that Montpelier designed and implemented as a direct result of the enVision Montpelier project were described in Chapters 10 and 11 — two different projects based on the Time Bank model and a food currency. Businesses in Montpelier were also made aware of the new Vermont Sustainable Exchange that is being developed in Burlington, so it’s possible for businesses to join a commercial barter system as well. There is no question in Montpelier ’s case that the shared vision for the future and the collective action that was mobilized as a result was key to the success of these currency interventions.

**В озвучку попало:**

> [serious] В рамках проекта «enVision Montpelier» город разработал и внедрил три валюты, о которых подробно рассказывалось в десятой и одиннадцатой главах. Это были два проекта на основе модели банка времени и одна продовольственная валюта. Кроме того, предпринимателей Монтпилиера проинформировали о новой «Вермонтской устойчивой бирже», которую развивают в Берлингтоне. Теперь местный бизнес может присоединиться и к этой системе коммерческого бартера. В случае с Монтпилиером не вызывает сомнений, что именно общее видение будущего и мобилизация коллективных усилий стали ключом к успеху этих валютных инициатив.

---

### 9. `p0974` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> What we are calling collective action — one aspect of which is political will — is based ultimately in what we hold dear, the things and values we care about as a people. If we value freedom, the legal and economic systems we create allow for it. If we value justice, there is a reliable rule of law, corrections for inequities, and fair, reciprocal checks and balances for the government. Values themselves contain a goal, or a vision, of an end result.

**В озвучку попало:**

> [thoughtful] То, что мы называем коллективным действием — частью которого является политическая воля, — в конечном счете опирается на наши ценности. На то, что нам дорого как людям. Если мы ценим свободу, созданные нами правовые и экономические системы будут ее обеспечивать. Если мы ценим справедливость, у нас будет надежная правовая база, механизмы исправления несправедливости и честная система сдержек и противовесов в управлении государством. Сами по себе ценности уже содержат в себе цель или видение конечного результата.

---

### 10. `p1174` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> As was the case in Burlington, the City of Calgary already had a complementary currency when imagineCALGARY began. Called Calgary Dollars, the currency is a taxable currency that exists both in printed and in electronic form. The project is supported by the Arusha Center, an organization dedicated to social justice, the United Way of Calgary, and the City of Calgary Family and Community Support Services.⁸

**В озвучку попало:**

> [serious] Как и в случае с Берлингтоном, в Калгари уже существовала дополнительная валюта, когда проект «imagineCALGARY» только начинался. Она называется «Калгари Долларс». Это налогооблагаемая валюта, которая существует как в бумажном, так и в электронном виде. Проект поддерживается Центром Аруша, организацией, занимающейся вопросами социальной справедливости, а также организацией «United Way» в Калгари и службами поддержки семьи и общества городской администрации.

---
## Абзацы, оставшиеся в озвучке на английском (1)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.

### 1. `narration#1481` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Сайт: magic-city-news.com/Community5/KatahdinTimeDollarExchange_38833883.shtml.

**В озвучку попало:**

> Сайт: magic-city-news.com/Community5/KatahdinTimeDollarExchange_38833883.shtml.

---
## Пустые и почти пустые абзацы (5)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0498` — длина озвучки / длина оригинала: 0.61; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## **EXAMPLES OF** **COMPLEMENTARY** **CURRENCIES**

**В озвучку попало:**

> ## Примеры дополнительных валют

---

### 2. `p1236` — длина озвучки / длина оригинала: 0.88; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Montpelier ’s Complementary Currencies

**В озвучку попало:**

> ### Дополнительные валюты Монтпилиера

---

### 3. `p1341` — длина озвучки / длина оригинала: 0.55; классы правки: —

**Исходный абзац:**

> Association (IRTA) and the Corporate Barter Council (CBC).

**В озвучку попало:**

> и Корпоративный бартерный совет.

---

### 4. `p1377` — длина озвучки / длина оригинала: 0.80; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • state service providers for the unemployed

**В озвучку попало:**

> • государственные службы занятости;

---

### 5. `p1489` — длина озвучки / длина оригинала: 0.73; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Establishing a System for Circulation

**В озвучку попало:**

> ### Создание системы обращения

---
