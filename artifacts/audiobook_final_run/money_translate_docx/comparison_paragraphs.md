# Перевод (читаемый DOCX), финальный прогон 2026-08-06 — материал для просмотра глазами

Книга: Bernard Lietaer et al., *Money and Sustainability: The Missing Link* (`tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-160516072426.pdf`).
Режим: `processing_operation = "translate"`, профиль
`ui-parity-translate-benchmark-advisory-image-safe-no-cleanup` (дефолт документа в реестре), auto → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_fin2_money_translate`. Seed выборки: `20260804` — тот же, что у аудиокнижного разбора.

**Это другой продукт.** Здесь человек читает документ, а не слушает его, поэтому
«на слух безразлично» тут не применяется: формат заголовка, список, курсив и картинка —
часть продукта. Пары «оригинал → перевод» взяты из перехваченного трафика к модели по
маркерам `[[DOCX_PARA_...]]`; в файл попадают только те, чей перевод дословно
присутствует в доставленном `.docx`.

## Что в файле

1. **Случайная выборка, 60 абзацев прозы** — до 20 из каждой трети книги, `random.Random(20260804)`.
2. **20 абзацев с максимальным сжатием**.
3. **10 абзацев с максимальным раздуванием**.
4. **10 самых буквальных абзацев**.

Отдано модели: 1383; дошло до документа: 1335.
Пул прозы: 463. Медианное отношение длин: 1.0395.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0048` — длина перевода / длина оригинала: 0.96

**Оригинал:**

> Governments, media and most leaders mak e every possible effort to convince public opinion to stick to mainstream think ing. If society wishes to be or to become successful, they say, we have to k eep faith in the current paradigm. The gospel still is that everything has to be expressed in monetary terms. And that there is no salvation outside the dominant financial systems and bank ing practices, a monopoly and a major power instrument. Closed systems are preferred to open ones. Complexity is avoided. Indeed a shortsighted vision on sustainable solutions…

**Перевод в документе:**

> Правительства, СМИ и большинство лидеров делают всё возможное, чтобы убедить общественность придерживаться мейнстримного мышления. Они утверждают: если общество хочет добиться успеха, мы должны хранить верность текущей парадигме. Догма гласит, что всё должно быть выражено в денежном эквиваленте и что нет спасения вне доминирующих финансовых систем и банковской практики — монополии и важнейшего инструмента власти. Закрытые системы предпочитаются открытым. Сложность игнорируется. Поистине близорукий взгляд на пути к устойчивому развитию…

---

### 2. `p0053` — длина перевода / длина оригинала: 1.00

**Оригинал:**

> While the issue is by definition global, the CoR-EU felt the Report should primarily be addressed on its behalf to a recognised, authoritative and independent European body. The most appropriate choice seemed to be *Finance Watch,* a public interest association, recently created on the initiative of members of the European Parliament. It is dedicated to mak ing finance work for the good of society, strengthening the voice of society in financial regulation reforms by conducting citizen advocacy and presenting public interest arguments to lawmak ers as a counterweight to private interest lobbying by the financial industry.

**Перевод в документе:**

> Хотя проблема по определению носит глобальный характер, в CoR-EU посчитали, что доклад должен быть адресован от нашего имени признанному, авторитетному и независимому европейскому органу. Наиболее подходящим выбором показалась ассоциация общественных интересов *Finance Watch*, недавно созданная по инициативе членов Европейского парламента. Она призвана сделать финансы полезными для общества, усиливая голос граждан в реформах финансового регулирования, проводя адвокационную деятельность и представляя законодателям аргументы в пользу общественных интересов как противовес лоббированию частных интересов финансовой индустрии.

---

### 3. `p0058` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> There is a great challenge here for the European U nion. We dare hope that the publication of *Money and Sustainability: The Missing Link* will inspire many a decision mak er and opinion leader to change course now, choosing new, creative approaches in monetary issues.

**Перевод в документе:**

> Перед Европейским союзом стоит серьезный вызов. Мы смеем надеяться, что публикация доклада «Деньги и устойчивое развитие: недостающее звено» вдохновит многих лиц, принимающих решения, и лидеров общественного мнения сменить курс и выбрать новые, творческие подходы к решению денежно-кредитных вопросов.

---

### 4. `p0072` — длина перевода / длина оригинала: 1.05

**Оригинал:**

> The book contains powerful arguments that need to be listened to, digested and acted upon. The section on how money affects sustainability mak es the k ey point that the global crises we face are interconnected. The financial crisis is but one dimension of a multi-dimensional puzzle. However, the book is more than a diagnosis of the ills and travails of our monetary system; it also points to new ways of reforming our financial system, to pioneering ideas and to potential solutions. The call for alternative think ing and innovative strategies is timely and necessary.

**Перевод в документе:**

> В книге содержатся веские аргументы, к которым необходимо прислушаться, осмыслить их и начать действовать. В разделе о влиянии денег на устойчивое развитие подчеркивается ключевая мысль: глобальные кризисы, с которыми мы сталкиваемся, взаимосвязаны. Финансовый кризис — лишь одна из граней многомерной головоломки. Однако эта книга — не просто диагноз болезней и проблем нашей денежной системы; она указывает пути к реформированию финансового сектора, предлагает новаторские идеи и возможные решения. Призыв к альтернативному мышлению и инновационным стратегиям звучит своевременно и крайне необходимо.

---

### 5. `p0081` — длина перевода / длина оригинала: 1.14

**Оригинал:**

> This study complements other endeavours of WAAS stressing the essential value and role of human capital. The Report reminds us that money is a man-made instrument intended to help society optimise human welfare. The prevailing monetary system encourages the multiplication of money for destabilising speculative investment rather than for productive investment that creates jobs, raises real incomes and promotes social equity. The Report examines alternative monetary strategies that can help mobilise under-utilised social resources, especially the huge number of unemployed and underemployed young people and adults whose human potential is ignored and squandered by the current system. This Report is a call for prompt political and economic action.

**Перевод в документе:**

> Данное исследование дополняет другие начинания ВАИН, подчеркивающие исключительную ценность и роль человеческого капитала. В отчете напоминается, что деньги — это созданный человеком инструмент, призванный помогать обществу оптимизировать благосостояние людей. Нынешняя денежно-кредитная система поощряет приумножение денег ради дестабилизирующих спекулятивных вложений, а не ради продуктивных инвестиций, которые создают рабочие места, повышают реальные доходы и способствуют социальному равенству. В отчете рассматриваются альтернативные денежные стратегии, способные помочь мобилизовать неиспользуемые социальные ресурсы, особенно огромную массу безработных и частично занятых молодых людей и взрослых, чей человеческий потенциал игнорируется и растрачивается нынешней системой. Этот отчет — призыв к решительным политическим и экономическим действиям.

---

### 6. `p0099` — длина перевода / длина оригинала: 1.19

**Оригинал:**

> Fiat currency issued by private institutions through the creation of debt has been used by nations for centuries. Its deadly effects are becoming apparent. But its ability to alleviate the symptoms of distress has led to its use anyway. We can only hope that in this century we will begin to use less deadly alternatives.

**Перевод в документе:**

> Фиатные деньги, выпускаемые частными институтами через механизм создания долга, используются государствами уже много веков. Их губительные последствия становятся всё более очевидными. Однако способность этих денег притуплять симптомы кризиса по-прежнему заставляет нас ими пользоваться. Остаётся лишь надеяться, что в нынешнем столетии мы начнём применять менее опасные альтернативы.

---

### 7. `p0101` — длина перевода / длина оригинала: 1.23

**Оригинал:**

> A fish will never create fire while immersed in water. We will never create sustainability while immersed in the present financial system. There is no tax, or interest rate, or disclosure requirement that can overcome the many ways the current money system blocks sustainability.

**Перевод в документе:**

> Рыба никогда не добудет огонь, пока находится под водой. Мы никогда не достигнем устойчивого развития, пока остаёмся внутри нынешней финансовой системы. Никакие налоги, процентные ставки или требования к раскрытию информации не способны преодолеть те многочисленные барьеры, которыми существующая денежная система блокирует устойчивое развитие.

---

### 8. `p0102` — длина перевода / длина оригинала: 1.03

**Оригинал:**

> I used not to think this. Indeed, I did not think about the money system at all. I took it for granted as a neutral and inevitable aspect of human society. But since beginning to read Bernard’s analyses I have a very different view. He is not alone. For example Thomas Greco has written on this topic. But the depth of Bernard’s practical experience, theoretical understanding, and historical perspectives on the financial system leave him without peer.

**Перевод в документе:**

> Раньше я так не думал. По правде говоря, я вообще не задумывался о денежной системе. Я воспринимал её как нечто нейтральное и неизбежное, как данность человеческого общества. Но, начав изучать аналитические работы Бернара, я стал смотреть на вещи иначе. И я не одинок: например, об этом писал Томас Греко. Однако глубина практического опыта, теоретических знаний и исторического видения финансовой системы, которыми обладает Бернар, делают его уникальным специалистом.

---

### 9. `p0143` — длина перевода / длина оригинала: 0.97

**Оригинал:**

> It is our contention that the ‘Missing Link’ between finance and the environment, between money and sustainability, lies elsewhere. What this Report demonstrates beyond doubt is a structural monetary flaw – a flaw in the very manner in which we create money – that is generating our disconcerting problems. The inescapable conclusion? That, in order to face the challenges of the 21st century, we need to rethink and overhaul our entire monetary system.

**Перевод в документе:**

> Мы утверждаем, что «недостающее звено» между финансами и окружающей средой, между деньгами и устойчивостью находится в другой плоскости. Этот отчет вне всяких сомнений доказывает наличие структурного денежного изъяна — изъяна в самом способе создания денег, — который и порождает наши тревожные проблемы. Неизбежный вывод? Чтобы противостоять вызовам XXI века, нам необходимо переосмыслить и полностью перестроить всю нашу денежную систему.

---

### 10. `p0151` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> Debates about economic issues rarely reveal the paradigm from which an economist is speaking. We start by making explicit the conceptual framework that underlies our approach, and compare it with other paradigms currently in use. Rather than defining environmental and social issues as ‘externalities’, our approach sees economic activities as a subset of the social realm, which, in turn, is a subset of the biosphere. This view provides the basis for the emergence of a new set of pragmatic tools, flexible enough to address many of our economic, social and environmental challenges.

**Перевод в документе:**

> В экономических дискуссиях редко проясняется парадигма, с позиций которой выступает тот или иной эксперт. Мы начнем с того, что четко обозначим концептуальную базу нашего подхода и сравним ее с другими парадигмами, существующими на сегодняшний день. Вместо того чтобы определять экологические и социальные проблемы как «внешние эффекты», мы рассматриваем экономическую деятельность как часть социальной сферы, которая, в свою очередь, является частью биосферы. Такой взгляд создает основу для появления комплекса новых прагматичных инструментов, достаточно гибких, чтобы справиться со многими нашими экономическими, социальными и экологическими вызовами.

---

### 11. `p0209` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> In closing, it would be naïve to think of complementary currencies as a magic bullet to solve all our current and future problems. However, rethinking our money is a necessary ingredient in any effective solution. We can no longer afford to overlook complementary currencies as the ‘Missing Link’ that can deliver a money system which promotes sustainability rather than undermining it at every turn.

**Перевод в документе:**

> В заключение хочу сказать: было бы наивно полагать, что дополнительные валюты — это волшебная таблетка от всех наших нынешних и будущих бед. И все же переосмысление денег — необходимый компонент любого эффективного решения. Мы больше не можем позволить себе игнорировать дополнительные валюты как то самое «недостающее звено», способное создать денежную систему, которая будет способствовать устойчивому развитию, а не подрывать его на каждом шагу.

---

### 12. `p0272` — длина перевода / длина оригинала: 1.04

**Оригинал:**

> Similarly, humans are reduced to their productive labour input, and their interactions are relevant only if they qualify as ‘services’. As a consequence, work performed by a stay-at-home carer for an elderly relative or a child are not counted in a nation’s GDP, because they do not get paid for it.

**Перевод в документе:**

> Точно так же люди сводятся лишь к их вкладу в производительный труд, а их взаимодействие становится значимым, только если оно классифицируется как «услуга». Как следствие, труд человека, который ухаживает дома за пожилым родственником или ребенком, не учитывается в ВВП страны, поскольку за эту работу не платят.

---

### 13. `p0306` — длина перевода / длина оригинала: 1.02

**Оригинал:**

> We previously stated that the world is currently undergoing a powerful set of shifting conditions including large-scale biodiversity extinction, climate change in the form of extreme weather conditions (including higher frequency of extreme floods and droughts), deterioration of arable soil through salination, pollutants and organic exhaustion as well as fresh water shortages. If not properly addressed, these shifting conditions will threaten the survival of the biosphere, which business, the economy, and all other human activities depend on. The following figure provides a summary of the most important threats to long-term ecological sustainability if we continue along our current economic path.²⁰

**Перевод в документе:**

> Ранее мы отмечали, что мир в настоящее время сталкивается с целым рядом серьезных изменений, включая массовое вымирание видов, изменение климата, проявляющееся в экстремальных погодных явлениях (в том числе участившихся катастрофических наводнениях и засухах), а также деградацию пахотных земель из-за засоления, загрязнения и истощения органических веществ и нехватку пресной воды. Если не принять надлежащих мер, эти изменения поставят под угрозу выживание биосферы, от которой зависят бизнес, экономика и вся человеческая деятельность в целом. На следующем рисунке представлены основные угрозы долгосрочной экологической устойчивости, с которыми мы столкнемся, если продолжим следовать нынешним экономическим курсом.²⁰

---

### 14. `p0310` — длина перевода / длина оригинала: 1.04

**Оригинал:**

> Contrary to this view, we see the ‘sustainability sector ’ as one of the most promising business opportunities of the 21st century. During the first ten years of this century, sustainable economic, social and ecological development has become strategically important for business. Corporations with serious environmental and social governance strategies and integrated policies are performing better than the average.²³ There is greater demand for products and services that impose lower burdens on ecosystems. This not only relates to *new* products and services such as renewable energy, but also to ‘redefining business’ such as, cradle-to-cradle or bio-mimicry industries.²⁴ Among the pioneers of such new business models, Interface carpets and Herman Miller office furniture are examples of long-existing corporations that have transformed themselves into different and more sustainable entities. Many more examples of such transformations exist and their numbers continue to increase rapidly.²⁵

**Перевод в документе:**

> Вопреки этому мнению, мы рассматриваем «сектор устойчивого развития» как одну из самых перспективных бизнес-возможностей XXI века. За первые десять лет этого столетия устойчивое экономическое, социальное и экологическое развитие приобрело стратегическое значение для бизнеса. Корпорации, внедряющие серьезные стратегии экологического и социального управления и комплексные политики, показывают результаты выше средних.²³ Растет спрос на товары и услуги, оказывающие меньшую нагрузку на экосистемы. Это касается не только *новых* продуктов и услуг, таких как возобновляемые источники энергии, но и «переосмысления бизнеса» в целом — например, внедрения принципов «от колыбели до колыбели» (cradle-to-cradle) или биомимикрии.²⁴ Среди пионеров таких бизнес-моделей можно назвать компании Interface (ковровые покрытия) и Herman Miller (офисная мебель) — это давно существующие корпорации, которые трансформировались в иные, более устойчивые структуры. Существует множество других примеров подобных преобразований, и их число стремительно растет.²⁵

---

### 15. `p0346` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> In order to spell out the economic paradigm in which we operate, the monetary dimension of the economy must explicitly be explored. Not all paradigms do this – some, and most notably the dominant Traditional Economics approach, view money as a passive element not affecting the way that individuals and collectives choose to act. The Ecological Economics paradigm, in the way we conceive it here, takes the monetary dimension much more seriously. How so? This is what we intend to explain in the remainder of this chapter. The exploration of this feature is what most sets this study apart from other economic texts and studies on sustainability.³²

**Перевод в документе:**

> Чтобы четко обозначить экономическую парадигму, в рамках которой мы действуем, необходимо детально рассмотреть денежный аспект экономики. Не все парадигмы делают это — некоторые, и прежде всего доминирующий подход традиционной экономики, рассматривают деньги как пассивный элемент, не влияющий на выбор действий отдельных лиц и коллективов. Парадигма экологической экономики, в том виде, в каком мы ее здесь представляем, относится к денежному аспекту гораздо серьезнее. Каким образом? Именно это мы и намерены объяснить в оставшейся части главы. Исследование этой особенности — то, что больше всего отличает данное исследование от других экономических текстов и работ по устойчивому развитию.³²

---

### 16. `p0348` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> For better and for worse, it has made a human population explosion possible, from 250 million in 1750 to over seven billion today. The production of goods over time follows a similar curve to that of population growth: between 1800 and the present, GDP per capita in the developed world multiplied by a factor of at least twenty. China, India and Brazil are in the process of reproducing this process as we write. As a result of industrialisation, many people in Europe, North America and parts of Asia have seen their standard of living soar from subsistence to what our ancestors would have considered extraordinary affluence. These are immense accomplishments, which, irrespective of their drawbacks, should be recognised and honoured.

**Перевод в документе:**

> Хорошо это или плохо, но именно она сделала возможным демографический взрыв: численность населения планеты выросла с 250 миллионов в 1750 году до более чем семи миллиардов сегодня. Производство товаров с течением времени следовало по той же кривой, что и рост населения: с 1800 года по настоящее время ВВП на душу населения в развитых странах увеличился как минимум в двадцать раз. Китай, Индия и Бразилия в момент написания этих строк повторяют данный процесс. Благодаря индустриализации многие люди в Европе, Северной Америке и некоторых частях Азии увидели, как их уровень жизни взлетел от простого выживания до того, что наши предки сочли бы невероятным богатством. Это огромные достижения, которые, вне зависимости от их негативных сторон, должны быть признаны и оценены по достоинству.

---

### 17. `p0405` — длина перевода / длина оригинала: 0.98

**Оригинал:**

> For example, excessive public debt is generally considered to be the problem in the ongoing euro crisis. The large-scale use of derivatives during a US real-estate bubble is seen as the proximate cause of the 2008 crash. The inflexible link between the national currency and the US dollar was determined to be the proximate cause of the 2001 Argentine peso collapse. The 1999 Asian crash, which affected a dozen countries, was blamed on ‘crony capitalism’. While such proximate factors may indeed act as triggers, they never reveal structural causes. Even when different breakdowns are analysed in conjunction, they are usually regrouped within specific categories: for example, ‘banking crises’, ‘monetary crises’, ‘sovereign-debt crises’, and so on. Each category is then analysed to understand the common causes associated with it; however, deeper structural issues still tend to be neglected. To use another metaphor, if one is dealing with a proverbial ‘house of cards’, different triggers can bring about different categories of crashes. What would truly make a difference would be to identify the structural brittleness of the house of cards itself.

**Перевод в документе:**

> Например, чрезмерный государственный долг обычно считается главной проблемой текущего кризиса еврозоны. Масштабное использование деривативов во время «пузыря» на рынке недвижимости в США рассматривается как непосредственная причина краха 2008 года. Негибкая привязка национальной валюты к доллару США была признана основной причиной обвала аргентинского песо в 2001 году. Азиатский кризис 1999 года, затронувший дюжину стран, списали на «кумовской капитализм». Хотя подобные факторы могут выступать в роли триггеров, они никогда не вскрывают глубинных структурных причин. Даже когда различные сбои анализируются в совокупности, их обычно группируют по узким категориям: например, «банковские кризисы», «валютные кризисы», «кризисы суверенного долга» и так далее. Каждую категорию затем изучают, чтобы понять свойственные ей причины, однако более глубокие структурные проблемы по-прежнему остаются без внимания. Используя другую метафору: если перед нами пресловутый «карточный домик», разные триггеры могут приводить к разным типам обрушений. Но по-настоящему важно было бы выявить структурную хрупкость самого этого карточного домика.

---

### 18. `p0453` — длина перевода / длина оригинала: 1.06

**Оригинал:**

> The timing of this sudden increase in government debt is particularly unfortunate. The current decade is one in which the OECD countries and their governments have to deal with unprecedented pressures not amenable to being postponed. As mentioned in Chapter I, two critical and predictable challenges during the next decade will be the transition to a post-carbon economy and the sharp increase in financial requirements for retiring baby boomers.

**Перевод в документе:**

> Время этого внезапного роста государственного долга выбрано крайне неудачно. Нынешнее десятилетие — это период, когда страны ОЭСР и их правительства сталкиваются с беспрецедентным давлением, которое невозможно отложить на потом. Как уже упоминалось в первой главе, двумя критическими и предсказуемыми вызовами на ближайшие десять лет станут переход к посткарбоновой экономике и резкое увеличение финансовых потребностей в связи с выходом на пенсию поколения «бэби-бумеров».

---

### 19. `p0454` — длина перевода / длина оригинала: 1.09

**Оригинал:**

> There is currently wide acceptance that massive investments are needed to avoid the worst-case scenarios of global warming. Similarly, there is agreement that will require strong leadership from governmental bodies for such a shift to occur. Because the private sector has invariably required financial incentives to make the necessary commitments, either subsidies or tax deductions are required. After making an inventory of the breakthrough possibilities in current renewable energy technologies, the MIT’s *Technology Review* concluded:

**Перевод в документе:**

> Сегодня существует широкое понимание того, что для предотвращения наихудших сценариев глобального потепления необходимы колоссальные инвестиции. Также есть согласие в том, что для осуществления такого перехода потребуется решительное руководство со стороны государственных органов. Поскольку частный сектор неизменно требует финансовых стимулов для принятия необходимых обязательств, требуются либо субсидии, либо налоговые льготы. Проведя инвентаризацию прорывных возможностей в современных технологиях возобновляемой энергетики, журнал MIT *Technology Review* пришел к следующему выводу:

---

### 20. `p0456` — длина перевода / длина оригинала: 1.02

**Оригинал:**

> Postponing the transition to a time when the pressures on government finances are alleviated is not an option: beyond a given level of carbon dioxide in the atmosphere and of higher average temperatures, we truly risk runaway climate change. This would lead to rising sea levels, requiring roughly one third of humanity to move to higher ground. As described in Chapter I, the phenomenon of ‘dust-bowlification’ would damage the biosphere to a grave extent. Humanity is playing Russian roulette with the global climate and with the biosphere, while breakthrough energy solutions are available, albeit only with massive governmental support. How will we explain to future generations that this support was not forthcoming because we were not able to think outside the box of our monetary arrangements, a legacy system whose main features are centuries old?

**Перевод в документе:**

> Откладывать переход на время, когда давление на государственные финансы ослабнет, — не вариант: при превышении определенного уровня углекислого газа в атмосфере и росте средней температуры мы рискуем столкнуться с необратимым изменением климата. Это приведет к повышению уровня моря, что заставит примерно треть человечества переселяться на более возвышенные территории. Как описано в первой главе, феномен «опустынивания» нанесет тяжелейший ущерб биосфере. Человечество играет в русскую рулетку с глобальным климатом и биосферой, в то время как прорывные энергетические решения уже существуют, хотя и требуют массированной государственной поддержки. Как мы объясним будущим поколениям, что эта поддержка не была оказана, потому что мы оказались неспособны выйти за рамки наших денежных механизмов — устаревшей системы, основные черты которой сложились еще столетия назад?

---

### 21. `p0489` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> Budgetary pressures and the threat of a major monetary crash will continue for many years. The social and political consequences are hard to imagine, but will no doubt include large-scale social unrest in a number of countries, which may favour more nationalistic and extremist political parties.

**Перевод в документе:**

> Бюджетное давление и угроза масштабного финансового краха сохранятся еще долгие годы. Социальные и политические последствия трудно даже вообразить, но они, несомненно, будут включать массовые общественные беспорядки в ряде стран, что может сыграть на руку более националистическим и экстремистским политическим силам.

---

### 22. `p0490` — длина перевода / длина оригинала: 0.93

**Оригинал:**

> Such movements are already identifiable both in the USA and in Europe even though the big financial squeeze is just beginning. History has shown that it is easier to start extremist movements than to stop them, and that such scenarios often end up being ‘resolved’ through conflict.

**Перевод в документе:**

> Подобные движения уже заметны как в США, так и в Европе, хотя основные финансовые трудности только начинаются. История показывает, что запустить экстремистские движения гораздо проще, чем остановить их, и что такие сценарии зачастую «разрешаются» через конфликты.

---

### 23. `p0532` — длина перевода / длина оригинала: 1.04

**Оригинал:**

> Eric Beinhock er is a Senior Advisor to M cKinsey & Co and author of the book *The Origin of Wealth*. The magazine *Fortune* named him “Business Leader of the Next Century”. What follows are highlights of his reasoning. “Without realising it and with the best intentions, the late-nineteenth-century economists borrowed from physics a set of ideas that fundamentally misclassifi ed the economy as a closed equilibrium system. Their approach set the framework for the Traditional Economics we see today. U nfortunately, [this] misclassifi cation has acted as a straightjack et, forcing economists to mak e highly unrealistic assumptions and limiting the fi eld’s empirical success.”9 Indeed, Walras and his contemporaries were unaware of the distinction between closed and open systems. A closed system is one in which there are no inputs from, or outputs to, the outside world: all energy originates and remains within the system itself. An open system operates with inputs and outputs. 19th century scientists believed most systems to be closed. We now k now that economies function as open systems, absorbing massive amounts of energy from the outside (e.g., solar, mineral, human and animal inputs). They also produce significant amounts of unwanted by-products (e.g., gases, waste, pollution). Even our planet can be classified as an open system, sitting in the middle of a river of energy from the sun that promotes life and evolution at all levels. While closed systems have a predictable end state, open systems do not necessarily. They can remain relatively stable and in relative equilibrium for a period, but also exhibit patterns of exponential growth, radical collapse or cyclical oscillations. These patterns all exist in actual economies and are dismissed as ‘anomalies’ in the Traditional Economics paradigm. The second fundamental error in the Traditional Economics paradigm relates to the state of k nowledge of thermodynamics until the late 19th century. At that time, scientists only k new about the First Law of thermodynamics, which “states that energy is neither created nor destroyed and is otherwise k nown as the *Conservation of Energy Principle*. This was developed in the early to mid-nineteenth century and was clearly spelled out in the texts that Walras… and others read.”10 However, “the Second Law, which was missing from the physics Walras and J evons k new, states that *entropy*, a measure of disorder or randomness in a system, is always increasing (…) Over time all order, structure, and pattern in the universe break s down, decays and dissipates. Cars rust, buildings crumble, mountains erode, apples rot and cream poured into coffee dissipates until it is evenly mixed.” 11

**Перевод в документе:**

> Эрик Бейнхокер — старший советник McKinsey & Co и автор книги «Происхождение богатства». Журнал *Fortune* назвал его «бизнес-лидером следующего столетия». Ниже приведены основные тезисы его рассуждений: «Сами того не осознавая и из лучших побуждений, экономисты конца XIX века позаимствовали из физики набор идей, которые фундаментально неверно классифицировали экономику как закрытую равновесную систему. Их подход задал рамки для традиционной экономики, которую мы видим сегодня. К сожалению, [эта] ошибочная классификация стала смирительной рубашкой, вынуждая экономистов принимать крайне нереалистичные допущения и ограничивая эмпирический успех этой области».⁹ Действительно, Вальрас и его современники не осознавали различия между закрытыми и открытыми системами. Закрытая система — это та, в которую не поступают ресурсы извне и из которой ничего не выходит: вся энергия возникает и остается внутри самой системы. Открытая система работает с входящими и исходящими потоками. Ученые XIX века полагали, что большинство систем являются закрытыми. Сейчас мы знаем, что экономики функционируют как открытые системы, поглощая огромное количество энергии извне (например, солнечную энергию, минеральные, человеческие и животные ресурсы). Они также производят значительное количество нежелательных побочных продуктов (например, газы, отходы, загрязнения). Даже нашу планету можно классифицировать как открытую систему, находящуюся посреди потока солнечной энергии, который способствует жизни и эволюции на всех уровнях. В то время как закрытые системы имеют предсказуемое конечное состояние, открытые — не обязательно. Они могут оставаться относительно стабильными и находиться в состоянии относительного равновесия в течение некоторого времени, но также могут демонстрировать модели экспоненциального роста, радикального коллапса или циклических колебаний. Все эти модели существуют в реальных экономиках, но в парадигме традиционной экономики их отбрасывают как «аномалии». Вторая фундаментальная ошибка парадигмы традиционной экономики связана с уровнем знаний о термодинамике до конца XIX века. В то время ученым был известен только Первый закон термодинамики, который «гласит, что энергия не создается и не уничтожается, и иначе известен как *принцип сохранения энергии*. Он был сформулирован в первой половине XIX века и был четко изложен в текстах, которые читали Вальрас… и другие».¹⁰ Однако «Второй закон, который отсутствовал в физике, известной Вальрасу и Джевонсу, гласит, что *энтропия*, мера беспорядка или случайности в системе, постоянно возрастает (…) Со временем весь порядок, структура и закономерности во Вселенной разрушаются, распадаются и рассеиваются. Машины ржавеют, здания рушатся, горы подвергаются эрозии, яблоки гниют, а сливки, налитые в кофе, рассеиваются, пока не перемешаются равномерно».¹¹

---

### 24. `p0550` — длина перевода / длина оригинала: 0.98

**Оригинал:**

> Because this is the case, complexity laws may even be more important to understanding real-world systems than the law of gravity itself. In particular, recent findings in thermodynamics unite long-standing observations about universal patterns of growth and development into a law of physics with profound implications for our understanding of developmental change and evolution itself, as astrophysicist François Roddier claims, along with many others (see Box 4.2).

**Перевод в документе:**

> Поскольку это так, законы сложности могут оказаться даже более важными для понимания систем реального мира, чем сам закон всемирного тяготения. В частности, недавние открытия в термодинамике объединяют давние наблюдения об универсальных закономерностях роста и развития в единый закон физики, имеющий глубокие последствия для нашего понимания эволюционных изменений и самой эволюции, как утверждает астрофизик Франсуа Роддье и многие другие (см. врезку 4.2).

---

### 25. `p0573` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> This, of course, causes the big organisations to get bigger still, and the smaller ones to die off, just as Schumpeter ’s classical ‘creative destruction’ theory predicts. Unfortunately, killing off large numbers of smaller organisations reduces resilience, increases instability and steadily moves the whole system towards collapse (i.e., sustainability = 0). Common examples include: large, unrestrained predators killing off all their prey causing an ecosystem to collapse; digging large canals in the New Orleans delta, which drained soil from the wetlands, causing the city to sink and the wetlands to die; and monopolies of commerce which kill off so many small competitors that a positive feedback cycle of ‘the more you have, the more you get’ locks into a ‘winner takes all’ game. This can lead to an economic ‘bubble’, a shimmering bubble of wealth over a feeble, eviscerated real economy. This law of physics explains why we once introduced anti-trust laws.

**Перевод в документе:**

> Разумеется, это заставляет крупные организации расти еще больше, а мелкие — отмирать, в точности как предсказывает классическая теория «созидательного разрушения» Шумпетера. К несчастью, уничтожение большого количества малых организаций снижает жизнестойкость, увеличивает нестабильность и неуклонно ведет всю систему к коллапсу (то есть устойчивость = 0). Типичные примеры: крупные, ничем не сдерживаемые хищники, истребляющие всю добычу, что приводит к краху экосистемы; прокладка больших каналов в дельте Нового Орлеана, из-за чего из водно-болотных угодий ушла почва, город начал проседать, а экосистема — гибнуть; или коммерческие монополии, которые уничтожают столько мелких конкурентов, что положительная обратная связь «чем больше имеешь, тем больше получаешь» превращается в игру «победитель забирает всё». Это может привести к экономическому «пузырю» — мерцающей оболочке богатства, натянутой поверх слабой, обескровленной реальной экономики. Этот закон физики объясняет, почему в свое время были введены антимонопольные законы.

---

### 26. `p0579` — длина перевода / длина оригинала: 1.14

**Оригинал:**

> The main point is that nature does not select for maximum efficiency but for an optimal balance between the two opposing poles of throughput efficiency and resilience. In other words, sustainability requires just enough, and not too much, of both efficiency and resilience. In most human-designed systems, and certainly in the monetary domain, we have been concerned only with efficiency, and have therefore tended to unduly sacrifice resilience.

**Перевод в документе:**

> Главный вывод заключается в том, что природа выбирает не максимальную эффективность, а оптимальный баланс между двумя противоположными полюсами: пропускной способностью и устойчивостью. Иными словами, для жизнеспособности системы требуется ровно столько эффективности и устойчивости, сколько нужно, — не больше и не меньше. В большинстве систем, созданных человеком, и особенно в денежно-кредитной сфере, мы беспокоимся исключительно об эффективности, а потому склонны неоправданно жертвовать устойчивостью.

---

### 27. `p0581` — длина перевода / длина оригинала: 1.00

**Оригинал:**

> Finally, we can assume that nature has solved many of the developmental problems in ecosystems over time. Otherwise, these ecosystems would no longer exist today. These are the same type of problems with which humanity is still struggling in economic terms. Also of interest is that all ecosystems have their most critical structural parameters such as diversity and interconnectivity within a very specific narrow range or what we have called the window of viability.

**Перевод в документе:**

> Наконец, можно предположить, что природа за долгие годы решила многие проблемы развития экосистем. В противном случае эти экосистемы просто перестали бы существовать. Это те же самые проблемы, с которыми человечество до сих пор сталкивается в экономике. Также примечательно, что все экосистемы удерживают свои критически важные структурные параметры — такие как разнообразие и взаимосвязанность — в очень узком диапазоне, который мы назвали «окном жизнеспособности».

---

### 28. `p0584` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> For instance, electrical power grids have been optimised for decades for greater technical and economic efficiency. It may come as a surprise to many engineers that it is precisely because these power grids have approached maximum efficiency that large-scale electrical blackouts are occurring in the technologically most advanced countries (e.g. Germany or the USA). Over-efficient streamlining has caused them to lose their resilience.

**Перевод в документе:**

> Например, электроэнергетические сети десятилетиями оптимизировались для повышения технической и экономической эффективности. Многих инженеров может удивить тот факт, что именно из-за приближения этих сетей к максимальной эффективности в технологически наиболее развитых странах (например, в Германии или США) происходят масштабные отключения электроэнергии. Чрезмерная оптимизация лишила их устойчивости.

---

### 29. `p0585` — длина перевода / длина оригинала: 1.08

**Оригинал:**

> Similarly, one can intuitively grasp that a balance between efficiency and resilience is key to economic sustainability. For example, vibrant businesses must maintain resilience by creating and maintaining well-knit systems of production, marketing, delivering, accounting and training that have numerous interconnections. Once these are in place, organisations must stay competitive by honing their processes following efficiency principles, typically through streamlining. Yet to survive changing times, organisations must also be able to adjust their business strategies to respond to changes in markets and in the economic climate. Overemphasis on efficiency through streamlining can become problematic when it reduces the diversity needed for adaptability and for the multiplicity of paths. In a business model, this diversity can be seen as agility and choice among different strategic options for dealing with unexpected problems, failures or opportunities.

**Перевод в документе:**

> Точно так же можно интуитивно понять, что баланс между эффективностью и устойчивостью является ключом к экономической стабильности. Например, жизнеспособные компании должны поддерживать устойчивость, создавая и сохраняя слаженные системы производства, маркетинга, поставок, учёта и обучения, имеющие множество взаимосвязей. Как только эти системы налажены, организации должны оставаться конкурентоспособными, оттачивая свои процессы в соответствии с принципами эффективности, как правило, за счёт оптимизации. Однако, чтобы выжить в меняющихся условиях, организации также должны уметь корректировать свои бизнес-стратегии, реагируя на изменения рынка и экономической ситуации. Чрезмерный упор на эффективность через оптимизацию становится проблемой, когда он снижает разнообразие, необходимое для адаптации и выбора различных путей развития. В бизнес-модели это разнообразие проявляется как гибкость и наличие альтернативных стратегических вариантов для решения неожиданных проблем, преодоления неудач или использования новых возможностей.

---

### 30. `p0641` — длина перевода / длина оригинала: 1.05

**Оригинал:**

> There are two ideal candidates for empirically testing and proving our claims: electrical distribution networks and the banking system. In both cases, we are dealing with a complex flow network, which may run very efficiently most of the time; but both have also been victims of repeated large-scale systemic crashes, worldwide. The practical impediment to performing these tests is the same in both cases: the data exist, but are considered confidential because of competitive relevance.

**Перевод в документе:**

> Существует два идеальных кандидата для эмпирической проверки и подтверждения наших выводов: сети электроснабжения и банковская система. В обоих случаях мы имеем дело со сложной сетью потоков, которая большую часть времени может работать весьма эффективно, но при этом обе системы по всему миру неоднократно становились жертвами масштабных системных крахов. Практическое препятствие для проведения таких тестов в обоих случаях одинаково: данные существуют, но считаются конфиденциальными из соображений конкуренции.

---

### 31. `p0646` — длина перевода / длина оригинала: 1.02

**Оригинал:**

> The remainder of this Report will explain why a strategy of multiple media of exchange makes not only theoretical, but also pragmatic sense. Randomly implementing exchange media other than conventional money may not be the best way forward. Rather, correctly designing and implementing exchange media to complement the current system and compensate for biases inherently generated by the conventional monetary system would be critically useful. The starting point for such a corrective, complementary strategy is to identify any existing biases and incentives that lead to unsustainable behaviour patterns. Only after understanding this built-in drift can we meaningfully choose from an infinity of potential new currency designs those that will best compensate for these propensities.

**Перевод в документе:**

> В оставшейся части этого отчета будет объяснено, почему стратегия использования множественных средств обмена имеет смысл не только с теоретической, но и с прагматической точки зрения. Хаотичное внедрение средств обмена, отличных от обычных денег, возможно, не лучший путь. Скорее, критически важно правильно спроектировать и внедрить такие средства, которые дополняли бы текущую систему и компенсировали перекосы, неизбежно порождаемые традиционной денежной системой. Отправной точкой для такой корректирующей, дополняющей стратегии является выявление существующих перекосов и стимулов, ведущих к неустойчивым моделям поведения. Только поняв этот встроенный «дрейф», мы сможем осмысленно выбрать из бесконечного множества потенциальных конструкций валют те, что лучше всего компенсируют эти склонности.

---

### 32. `p0670` — длина перевода / длина оригинала: 1.18

**Оригинал:**

> From a systemic perspective, none of these effects is a simple linear cause-effect relationship. They also interact and even reinforce one another. The outcome is a set of built-in mechanisms that cause a bank-debt monopoly to be incompatible with sustainability in the long-term. We discuss each of these effects separately and attempt to describe their interactions at the end of the chapter.

**Перевод в документе:**

> С системной точки зрения ни один из этих эффектов не является простой линейной причинно-следственной связью. Они взаимодействуют и даже усиливают друг друга. В результате формируется комплекс встроенных механизмов, из-за которых монополия банковского кредита как основы денежной системы становится несовместимой с устойчивым развитием в долгосрочной перспективе. Мы рассмотрим каждый из этих эффектов отдельно, а в конце главы попытаемся описать их взаимодействие.

---

### 33. `p0774` — длина перевода / длина оригинала: 0.99

**Оригинал:**

> Once upon a time, in a small village in the Outback , people used barter for all their transactions. On every mark et day, people walk ed around with chick ens, eggs, hams, and breads, and engaged in prolonged negotiations among themselves to exchange what they needed. At k ey periods of the year, such as during harvests or when someone’s barn required big repairs after a storm, people recalled the tradition of helping each other out, brought from the old country. They k new that if they had a problem someday, others would help them in return. One mark et day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral the six chick ens he wanted to exchange for a big ham, he could not refrain from laughing. “Poor people”, he said, “so primitive”. The farmer’s wife overheard him and challenged the stranger, “Do you think you can do a better job handling chick ens?” “Chick ens, no”, responded the stranger, “But there is a much better way to eliminate all that hassle. “Oh yes, how so?” ask ed the woman. “See that tree there?” the stranger replied. “Well, I will go wait there for one of you to bring me one large cowhide. Then have every family visit me. I’ll explain the better way.” And so it happened. He took the cowhide, and cut perfect leather rounds in it, and put an elaborate and graceful little stamp on each round. Then he gave to each family 10 rounds, and explained that each represented the value of one chick en. “Now you can trade and bargain with the rounds instead of the unwieldy chick ens”, he explained. It made sense. Everybody was impressed with the man with the shiny shoes and inspiring hat. “Oh, by the way”, he added after every family had received their 10 rounds, “in a year’s time, I will come back and sit under that same tree. I want you to each bring me back 11 rounds. That 11th round is a tok en of appreciation for the technological improvement I just made possible in your lives.” “But where will the 11th round come from?” ask ed the farmer with the six chick ens. “You’ll see”, said the man with a reassuring smile.

**Перевод в документе:**

> Жили-были люди в одной деревушке в глубинке, и все свои сделки они совершали путем обмена. В каждый базарный день жители ходили по площади с курами, яйцами, окороками и хлебом, ведя долгие переговоры, чтобы выменять то, что им было нужно. В важные периоды года, например во время сбора урожая или когда после бури кому-то требовался серьезный ремонт амбара, люди вспоминали традицию взаимопомощи, привезенную еще со старой родины. Они знали: если у них случится беда, другие придут на выручку. Однажды на базар забрел незнакомец в начищенных до блеска черных туфлях и элегантной белой шляпе; он наблюдал за всем происходящим с саркастической усмешкой. Увидев, как один фермер бегает по площади, пытаясь поймать шесть кур, чтобы обменять их на большой окорок, он не удержался от смеха. «Бедняги, — сказал он, — до чего же примитивно». Жена фермера услышала его и бросила вызов: «Думаете, вы справились бы с курами лучше?» «С курами — нет, — ответил незнакомец, — но есть способ гораздо лучше, чтобы избавить вас от всей этой суеты». «О да, и какой же?» — спросила женщина. «Видите вон то дерево? — ответил незнакомец. — Я буду ждать там, пока кто-нибудь из вас не принесет мне одну большую коровью шкуру. А потом пусть каждая семья придет ко мне. Я объясню, в чем заключается этот лучший способ». Так и вышло. Он взял шкуру, вырезал из нее идеальные кожаные кружки и поставил на каждом из них изящный затейливый штамп. Затем он раздал каждой семье по 10 кружков и пояснил, что каждый из них равен по стоимости одной курице. «Теперь вы можете торговаться и обмениваться кружками, а не таскаться с неудобными курами», — объяснил он. Это имело смысл. Все были впечатлены человеком в блестящих туфлях и эффектной шляпе. «О, кстати, — добавил он, когда каждая семья получила свои 10 кружков, — через год я вернусь и сяду под тем же деревом. Я хочу, чтобы каждый из вас принес мне обратно по 11 кружков. Эта одиннадцатая монета — знак признательности за технологическое усовершенствование, которое я только что внедрил в вашу жизнь». «Но откуда возьмется одиннадцатая монета?» — спросил фермер с шестью курами. «Увидите», — ответил человек с обнадеживающей улыбкой.

---

### 34. `p0781` — длина перевода / длина оригинала: 1.00

**Оригинал:**

> Many indirect indices have been used to measure social capital. They have ranged from education and income, to the percentage of women at work; from forms of business organisation and social safety nets, to the degree to which we can participate in the running of our society; from the freedom of the press, to the legal constitution of states. The availability of jobs and the quality of working conditions has a key influence on the formation of social capital. Regardless of the definition or data set used, the tendency over decades is a decrease in social capital in most developed societies.

**Перевод в документе:**

> Для измерения социального капитала использовалось множество косвенных показателей. Они варьировались от уровня образования и доходов до процента работающих женщин; от форм организации бизнеса и систем социальной защиты до степени нашего участия в управлении обществом; от свободы прессы до государственного устройства. Наличие рабочих мест и качество условий труда оказывают ключевое влияние на формирование социального капитала. Независимо от используемого определения или набора данных, на протяжении десятилетий в большинстве развитых обществ наблюдается тенденция к снижению социального капитала.

---

### 35. `p0791` — длина перевода / длина оригинала: 1.09

**Оригинал:**

> In comparison to the neutrally primed participant group, participants in the money-primed group demonstrated significantly higher rates of playing alone, working alone, and put more physical distance between themselves and their neighbours. The money-primed group also hesitated to ask others for help, and tended to respond to requests for help as if they were insensitive to others. They also preferred the pursuit of individualistic goals and individual freedom to that of collaboration. The results of this and other similar studies strongly support our hypothesis that money is non-neutral with regards to human interactions and behavioural patterns. Indeed, it increases social isolation and thereby a decline in human social capital.

**Перевод в документе:**

> По сравнению с группой, подвергшейся нейтральному воздействию, участники, «настроенные» на деньги, значительно чаще предпочитали играть и работать в одиночку, а также старались держать большую физическую дистанцию между собой и окружающими. Члены этой группы реже обращались за помощью к другим и склонны были реагировать на просьбы о помощи так, будто они менее чувствительны к нуждам ближних. Они также отдавали предпочтение достижению индивидуальных целей и личной свободе, а не сотрудничеству. Результаты этого и других подобных исследований убедительно подтверждают нашу гипотезу о том, что деньги не являются нейтральными по отношению к человеческому взаимодействию и моделям поведения. Более того, они усиливают социальную изоляцию и тем самым способствуют снижению человеческого социального капитала.

---

### 36. `p0838` — длина перевода / длина оригинала: 0.93

**Оригинал:**

> According to Ferguson, the dynamic between these four institutions explains the evolution of the nexus between power and modern money. A particularly effective synergy among these four institutions emerged for the first time in Britain during the 18th century. It is this synergy that made it possible for Britain to industrialise, defeat Napoleon, and build its empire. Let us briefly summarise the specific role played by each institution.

**Перевод в документе:**

> По мнению Фергюсона, динамика взаимодействия между этими четырьмя институтами объясняет эволюцию связи между властью и современными деньгами. Особенно эффективная синергия между ними впервые возникла в Британии в XVIII веке. Именно это взаимодействие позволило Британии провести индустриализацию, победить Наполеона и создать свою империю. Давайте кратко подытожим специфическую роль каждого из этих институтов.

---

### 37. `p0859` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> The Old Lady of Threadneedle Street, as the British central bank in the City of London is still referred to, “is in all respects to money as St. Peter ’s is to the Faith. And the reputation is deserved, for most of the art as well as much of the mystery associated with the management of money originated there.”¹⁴ For the USA, this same sequence was completed with the Federal Reserve Act of 1913.¹⁵

**Перевод в документе:**

> «Старая леди с Треднидл-стрит», как до сих пор называют британский центральный банк в лондонском Сити, «во всех отношениях относится к деньгам так же, как собор Святого Петра — к вере. И эта репутация заслуженна, ибо большая часть искусства, равно как и немалая доля таинственности, связанных с управлением деньгами, зародились именно там»¹⁴. В США эта же последовательность завершилась принятием Закона о Федеральной резервной системе в 1913 году¹⁵.

---

### 38. `p0868` — длина перевода / длина оригинала: 0.97

**Оригинал:**

> What changes are available to Europe that would reverse or soften the impact of today’s monetary arrangements? The most radical policy option proposed used to be known as the ‘Chicago Plan’ and dates back to the 1930s. While it would indeed be a far-reaching policy shift, it is not an option we actually recommend for reasons explained at the end of this chapter.

**Перевод в документе:**

> Какие изменения доступны Европе, чтобы обратить вспять или смягчить последствия нынешних монетарных механизмов? Самый радикальный вариант политики, предложенный еще в 1930-х годах, был известен как «Чикагский план». Хотя это действительно был бы масштабный сдвиг в политике, мы не рекомендуем его к реализации по причинам, изложенным в конце этой главы.

---

### 39. `p0894` — длина перевода / длина оригинала: 0.98

**Оригинал:**

> If not the Chicago Plan, then what can governments do at this point? Two stories are relevant. The one most people are familiar with is referred to as the ‘Official Paradigm’ because it is embedded in the majority of financial media and mainstream economic textbooks.³² It does not offer governments many options except that of submitting to the dictates of the ‘financial markets’. The second story is the ‘Fiat Currency Paradigm’ which opens up a very different set of possibilities.³³

**Перевод в документе:**

> Если не «Чикагский план», то что могут сделать правительства в текущей ситуации? Здесь уместны две истории. Та, что знакома большинству, называется «Официальной парадигмой», поскольку она глубоко укоренилась в большинстве финансовых СМИ и учебниках по экономике мейнстрима³². Она не оставляет правительствам особого выбора, кроме как подчиниться диктату «финансовых рынков». Вторая история — это «Парадигма фиатных денег», которая открывает совершенно иной спектр возможностей³³.

---

### 40. `p0898` — длина перевода / длина оригинала: 1.01

**Оригинал:**

> A long time ago, this official story did indeed reflect reality. This was the case, for instance, when the Byzantine Empire issued the bezant, a gold coin issued with the same weight (4.55 grams) and same purity (98%) for a record 700 years.³⁵ Producing these coins on such a consistent basis required a continuous supply of the precious metal. This gold was obtained through mining, conquest, trade and taxation.

**Перевод в документе:**

> Давным-давно эта официальная история действительно отражала реальность. Так было, например, в Византийской империи, где на протяжении рекордных 700 лет выпускалась золотая монета — безант — с неизменным весом (4,55 грамма) и пробой (98%).³⁵ Для поддержания такой стабильности требовался постоянный приток драгоценного металла, который добывался путем разработки месторождений, завоеваний, торговли и налогообложения.

---

### 41. `p0951` — длина перевода / длина оригинала: 1.11

**Оригинал:**

> For all their diversity, the nine systems we describe share two common denominators. First, they are all designed to act as *complementary systems*, i.e. they are designed to operate in parallel with the existing national bank-debt money system. Second, they should ideally all be as transparent for their users as possible. For example, before making an exchange, each party could have the right to see the other party’s account. Transparency allows these systems to be self-policing and reduce potential fraud. These systems would be most cost-effective if they used mobile electronic devices such as mobile phones.

**Перевод в документе:**

> При всем своем разнообразии девять описываемых нами систем имеют два общих знаменателя. Во-первых, все они разработаны как *дополнительные системы*, то есть предназначены для работы параллельно с существующей национальной системой банковских долговых денег. Во-вторых, в идеале все они должны быть максимально прозрачными для своих пользователей. Например, перед совершением обмена каждая сторона могла бы иметь право видеть счет другой стороны. Прозрачность позволяет этим системам осуществлять самоконтроль и снижать риск потенциального мошенничества. Такие системы были бы наиболее экономически эффективными при использовании мобильных электронных устройств, таких как смартфоны.

---

### 42. `p0982` — длина перевода / длина оригинала: 0.93

**Оригинал:**

> This Dora learning-economy is intended to operate in parallel with the conventional monetary system. We are, therefore, witnessing the beginnings of an exchange media ecosystem. At the end of the first planning session, one of the participants asked the 17-year-old whether he would be willing to teach English and get paid in *Lita* (the Lithuanian national currency), in dollars or in euros. His answer was, “No, I’d prefer to get paid in Dora, because that would get me closer to my dream. These other currencies only would get me the airline ticket!” For this teenager, the Dora had already become a ‘superior currency’, a currency that he preferred over all others. Doraland is an example of a complementary system that encourages non-spontaneous but desirable behaviour patterns. Figure 7.1 summarises the Doraland model in a flow diagram.

**Перевод в документе:**

> Эта экономика знаний на базе дор призвана функционировать параллельно с традиционной денежной системой. Таким образом, мы наблюдаем зарождение экосистемы обменных средств. В конце первой сессии планирования один из участников спросил того самого 17-летнего юношу, согласился бы он преподавать английский за литы (национальную валюту Литвы), доллары или евро. Он ответил: «Нет, я бы предпочел получить оплату в дорах, потому что это приблизит меня к моей мечте. Эти другие валюты позволили бы мне купить только авиабилет!» Для этого подростка дора уже стала «превосходящей валютой» — той, которую он ценит выше всех остальных. Doraland — это пример дополнительной системы, поощряющей не спонтанные, но желательные модели поведения. На рис. 7.1 представлена блок-схема модели Doraland.

---

### 43. `p0989` — длина перевода / длина оригинала: 1.03

**Оригинал:**

> Market failures in health care have been well documented. Causes of these failures include asymmetric information, adverse patient selection, entry barriers, absence of risk pooling and moral hazard.³ We hypothesise the existence of an additional market failure. In fact, no developed country really has a ‘health care’ system; rather, they are all funding ‘medical care’ systems. The economic incentives in a medical care system are therefore skewed towards keeping sick people alive, rather than preventively keeping the general population healthy. This is because medical care stakeholders, including the pharmaceutical industry, medical technology suppliers and health care professionals — all acting rationally — end up earning most of their money by treating sick or unwell individuals, as opposed to providing preventive health care to a healthy population.⁴ Because the vast majority of the global medical care budget is spent on acute and chronic diseases, preventive health care accounts for only a very small fraction of the overall health care services provided in industrialised countries.⁵ For instance, recent studies in the USA estimate that 50% of all mortality is linked to social and behavioural factors such as smoking, diet, alcohol use, sedentary lifestyle and preventable accidents.⁶ Yet, less than 5% of the approximately US$1 trillion spent annually on health care is devoted to addressing the root causes of these preventable conditions.⁷

**Перевод в документе:**

> Провалы рынка в сфере здравоохранения хорошо изучены. Среди их причин — асимметрия информации, неблагоприятный отбор пациентов, барьеры для входа, отсутствие механизмов распределения рисков и моральный риск.³ Мы выдвигаем гипотезу о существовании еще одного рыночного провала. По сути, ни в одной развитой стране нет системы «охраны здоровья» — все они финансируют системы «медицинской помощи». Экономические стимулы в таких системах смещены в сторону поддержания жизни уже заболевших людей, а не профилактики здоровья населения в целом. Это происходит потому, что участники рынка медицинских услуг — включая фармацевтическую промышленность, поставщиков медицинских технологий и самих специалистов, — действуя рационально, зарабатывают большую часть средств именно на лечении больных или нездоровых людей, а не на предоставлении профилактических услуг здоровому населению.⁴ Поскольку подавляющая часть мирового бюджета здравоохранения расходуется на борьбу с острыми и хроническими заболеваниями, на долю профилактики приходится лишь ничтожная часть всех медицинских услуг в индустриально развитых странах.⁵ Например, согласно недавним исследованиям в США, 50% всех случаев смертности связаны с социальными и поведенческими факторами: курением, питанием, употреблением алкоголя, малоподвижным образом жизни и предотвратимыми несчастными случаями.⁶ Тем не менее менее 5% из примерно 1 триллиона долларов, ежегодно расходуемых на здравоохранение, направляется на устранение первопричин этих предотвратимых состояний.⁷

---

### 44. `p0990` — длина перевода / длина оригинала: 1.11

**Оригинал:**

> Even if the medical care market were a theoretically ‘perfect’ one – with fully informed actors, no moral hazard, less asymmetry, more efficiency, fair access and so on – the economic preference for ‘sick and alive’ clients would remain a problematic bias. The current system thus makes it tempting to treat an obese patient who develops diabetes by using medication, rather than by using an early detection/ prevention approach with exercise and weight-loss programmes, to mitigate or even avoid the disease. In addition, improved technology has allowed an increase in the life expectancy of chronically ill individuals, with a corresponding increase in the consumption of health care resources. Prevention is thus side-lined in the face of this additional disease burden. The ‘sick and alive’ bias then becomes an additional cause for a market failure that contributes to the ineffective systemic organisation of health care services.

**Перевод в документе:**

> Даже если бы рынок медицинских услуг был теоретически «совершенным» — с полностью информированными участниками, отсутствием морального риска, меньшей асимметрией, высокой эффективностью и равным доступом, — экономическое предпочтение клиентов категории «больной, но живой» оставалось бы проблемным искажением. Нынешняя система подталкивает к тому, чтобы лечить пациента с ожирением, у которого развился диабет, с помощью медикаментов, вместо того чтобы применять методы ранней диагностики и профилактики, включая программы по снижению веса и физические нагрузки, для смягчения или даже предотвращения болезни. Кроме того, развитие технологий позволило увеличить продолжительность жизни хронических больных, что привело к соответствующему росту потребления ресурсов здравоохранения. В условиях такого дополнительного бремени болезней профилактика отходит на второй план. Таким образом, предвзятость «больной, но живой» становится дополнительной причиной рыночного провала, способствующего неэффективной системной организации медицинских услуг.

---

### 45. `p1018` — длина перевода / длина оригинала: 1.13

**Оригинал:**

> This idea was initially developed as a micro-savings instrument for India, but can easily be adapted to many other environments.¹⁹ It consists of a savings instrument fully backed by a natural growth process and useable as a local medium of exchange. The backing could be any commercially valuable product that grows organically over time, whose ownership can be secured and which can be maintained and harvested without unduly high costs. Examples of such products include trees or any other commercial plant that grows organically in value over years, or breeding fish in a protected lake, or wild game in an enclosed forest. Here we will focus on the example of a tree plantation, because the benefits are wide ranging. Forests act as carbon sinks and deforestation is a growing global ecological concern that makes a significant contribution to climate change.

**Перевод в документе:**

> Эта идея изначально разрабатывалась как инструмент микросбережений для Индии, но её легко адаптировать для самых разных условий.¹⁹ Суть её заключается в сберегательном инструменте, который полностью обеспечен процессом естественного роста и может использоваться в качестве локального средства обмена. Обеспечением может служить любой коммерчески ценный продукт, который органически растет со временем, право собственности на который можно закрепить, а содержание и сбор урожая не требуют чрезмерно высоких затрат. Примерами таких продуктов могут быть деревья или любые другие коммерческие культуры, стоимость которых органически увеличивается с годами, разведение рыбы в охраняемом водоеме или дичь в огороженном лесном массиве. Мы сосредоточимся на примере лесных плантаций, поскольку они приносят разностороннюю пользу. Леса служат поглотителями углерода, а вырубка лесов — это растущая глобальная экологическая проблема, которая вносит значительный вклад в изменение климата.

---

### 46. `p1041` — длина перевода / длина оригинала: 0.94

**Оригинал:**

> A third option, requiring prudent management, would be for the Savings Company to allow the shares to be ‘cashed in’ for payment in conventional money before reaching maturity. This would be useful to build trust in the system. In situations where immediate cash was required, such as after an accident or disease, or for a wedding, this option would allow an individual or family to address the situation without having to dump the shares at a price below their real value.

**Перевод в документе:**

> Третий вариант, требующий осмотрительного управления, заключается в том, чтобы компания «Природные сбережения» позволяла «обналичивать» акции до наступления срока их погашения. Это укрепило бы доверие к системе. В ситуациях, когда деньги требуются срочно — например, из-за болезни, несчастного случая или свадьбы, — такая возможность позволила бы человеку или семье решить проблему, не прибегая к продаже акций по цене ниже их реальной стоимости.

---

### 47. `p1042` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> The value of an early redemption could be based on a value curve such as that shown in Figure 7.3, less a transaction fee. This fee would encourage share owners to use them primarily as a store of value continuing exchanges within the community rather than cashing shares in for conventional money. If this third option were made available, the Natural Savings Company would need to have access to sufficient cash (e.g. by securing a line of credit with a bank), to avoid a ‘run on the savings company’ – the equivalent to a ‘run on the bank’ in a conventional system.

**Перевод в документе:**

> Стоимость досрочного погашения может рассчитываться на основе кривой стоимости, подобной той, что показана на рисунке 7.3, за вычетом комиссии за транзакцию. Эта комиссия будет стимулировать владельцев использовать акции прежде всего как средство сбережения и инструмент для обмена внутри сообщества, а не обменивать их на обычные деньги. Если такая опция будет доступна, компании «Природные сбережения» необходимо иметь доступ к достаточному объему наличности (например, через кредитную линию в банке), чтобы избежать «набега на сберегательную компанию» — аналога банковской паники в традиционной системе.

---

### 48. `p1081` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> Monetary instability has become the leading concern for international business — often greater than political or market risks. In a *Fortune 500* survey in the USA, all corporate participants reported foreign exchange instability as the largest risk of doing business internationally.²³

**Перевод в документе:**

> Валютная нестабильность стала главной проблемой для международного бизнеса, зачастую затмевающей политические или рыночные риски. Согласно опросу компаний из списка *Fortune 500* в США, все корпоративные участники назвали нестабильность валютных курсов основным риском при ведении международного бизнеса.²³

---

### 49. `p1082` — длина перевода / длина оригинала: 1.21

**Оригинал:**

> The TRC system provides an effective solution for this while making it profitable for corporations to think long-term. It does this by resolving the ongoing conflict between shareholders’ short-term priorities and the long-term requirement of society at large. It also stabilises the world economy through its counter-cyclical impact.

**Перевод в документе:**

> Система TRC предлагает эффективное решение этой проблемы, позволяя корпорациям с выгодой для себя ориентироваться на долгосрочную перспективу. Это достигается за счет разрешения постоянного конфликта между краткосрочными приоритетами акционеров и долгосрочными потребностями общества в целом. Кроме того, система способствует стабилизации мировой экономики благодаря своему контрциклическому воздействию.

---

### 50. `p1122` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> In contrast, when the business cycle booms, both suppliers and corporations have an increased need for raw materials and demand for them goes up. The TRCs could be cashed in and used in the commodity markets. The amount of TRCs in circulation would decrease when the business cycle is at its maximum and counteract inflationary pressures. In summary, by providing monetary liquidity during phases when credit gets tight in the conventional system and contracting when business is booming, TRC-denominated exchanges would stabilise the overall business cycle.

**Перевод в документе:**

> И наоборот, в периоды экономического подъема спрос на сырье со стороны поставщиков и корпораций растет. В такие моменты TRC можно обналичивать и использовать на товарных рынках. Объем TRC в обращении будет сокращаться на пике делового цикла, что позволит сдерживать инфляционное давление. В конечном счете, обеспечивая денежную ликвидность в периоды, когда в традиционной системе кредитование затруднено, и сокращаясь в периоды бума, расчеты в TRC будут способствовать стабилизации общего делового цикла.

---

### 51. `p1134` — длина перевода / длина оригинала: 1.00

**Оригинал:**

> The political context for an international monetary treaty does not exist. The TRC avoids this difficulty by relying on private initiative. As we have already emphasised, from a legal or tax standpoint, the TRC functions within the official framework of countertrade and does not require any formal governmental agreements to be made operational.

**Перевод в документе:**

> Политическая почва для заключения международного валютного договора отсутствует. TRC обходит эту трудность, опираясь на частную инициативу. Как мы уже подчёркивали, с правовой и налоговой точек зрения TRC функционирует в рамках официальной системы встречной торговли и не требует никаких формальных правительственных соглашений для начала работы.

---

### 52. `p1155` — длина перевода / длина оригинала: 1.07

**Оригинал:**

> The City of Ghent wanted to encourage ecological and health-promoting activities, beautify the neighbourhood and improve the overall quality of life in Rabot. They started with a survey asking local residents what was most desirable to them. The answer was access to a small plot of land to grow vegetables and flowers. The city made land available, including an unused factory lot, on which over a hundred 4m² gardens were created. These little gardens have been made available for a yearly rent of 150 Torekes, payable only in Torekes.

**Перевод в документе:**

> Городские власти Гента стремились стимулировать экологически полезную и оздоровительную деятельность, облагородить район и повысить общее качество жизни в Работе. Они начали с опроса местных жителей, чтобы выяснить, что для них наиболее важно. Ответ был прост: доступ к небольшому участку земли для выращивания овощей и цветов. Город предоставил землю, включая неиспользуемую заводскую территорию, где было разбито более сотни огородов площадью по 4 м². Эти маленькие участки сдаются в аренду за 150 «торекесов» в год, причем оплата принимается исключительно в этой валюте.

---

### 53. `p1221` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> A Civics system also gives opportunities to build a stronger sense of community. Modern societies suffer high levels of isolation and fractured social networks and family systems. Shared work in a local community is an effective way to counteract this loss of social capital while generating economic and environmental resilience.

**Перевод в документе:**

> Система Civics также дает возможности для укрепления чувства общности. Современное общество страдает от высокого уровня изоляции, разрыва социальных связей и ослабления семейных институтов. Совместный труд на благо местного сообщества — эффективный способ противостоять этой утрате социального капитала, одновременно повышая экономическую и экологическую устойчивость.

---

### 54. `p1222` — длина перевода / длина оригинала: 1.00

**Оригинал:**

> The Civics system could operate at any scale: local, city, region, or even across a country as a whole. Engagement by the population in the decision-making process about which projects get implemented is essential for success. Various processes exist to accomplish this and modern civil society may still have something to learn from forms of governance in traditional communities. For instance, the Balinese banjar system has been working for over twelve centuries and has proven adaptable to modern environments.² New systems like sociocracy³ and holacracy⁴ also look promising.

**Перевод в документе:**

> Система Civics может работать в любом масштабе: на уровне микрорайона, города, региона или даже всей страны. Успех невозможен без участия населения в принятии решений о том, какие именно проекты следует реализовывать. Для этого существуют различные механизмы, и современное гражданское общество может многому поучиться у традиционных сообществ. Например, балийская система «банджар» успешно функционирует уже более двенадцати веков и доказала свою способность адаптироваться к современным условиям². Также перспективно выглядят новые системы, такие как социократия³ и холакратия⁴.

---

### 55. `p1256` — длина перевода / длина оригинала: 1.12

**Оригинал:**

> Figure 1.1 and Appendix A as evidence for this statement.) Because the devastation will unfold over decades, and reducing its likelihood will require collective action by humanity as a whole, this ‘war ’ may also be more difficult to wage than any previous one. It may not have to be so hard if governments require ECOs to win a war against climate change.

**Перевод в документе:**

> рисунку 1.1 и приложению А в качестве подтверждения этого утверждения.) Поскольку катастрофа будет разворачиваться десятилетиями, а снижение ее вероятности потребует коллективных усилий всего человечества, эта «война» может оказаться даже сложнее любой из предыдущих. Однако она может стать менее изнурительной, если правительства введут ECO как инструмент для победы в войне с изменением климата.

---

### 56. `p1265` — длина перевода / длина оригинала: 1.04

**Оригинал:**

> The ECOs would be created by governments electronically and bear no interest. Corporations would earn ECOs by providing quantitatively verifiable evidence of investment and activities reducing the risk of climate change. There would be a clear description of how many ECOs a business would earn for each type of activity. An independently verifiable audit trail would be required before any ECO payment could be obtained. Qualifying activities could include: reductions in carbon emissions (e.g., 1 ECO for each 1000 tons of verified carbon reductions), investments in natural carbon sinks (e.g. 1 ECO for each 1000 tons of carbon sequestration in new, sustainably managed forests) or in other sequestration technologies.

**Перевод в документе:**

> ECO будут создаваться правительствами в электронном виде и не будут приносить процентов. Корпорации будут зарабатывать ECO, предоставляя количественно проверяемые доказательства инвестиций и деятельности, снижающей риски изменения климата. Будет четко определено, сколько ECO получает бизнес за каждый вид деятельности. Перед получением любого платежа в ECO потребуется пройти независимый проверяемый аудит. К числу квалифицируемых видов деятельности могут относиться: сокращение выбросов углерода (например, 1 ECO за каждые 1000 тонн подтвержденного сокращения выбросов), инвестиции в природные поглотители углерода (например, 1 ECO за каждые 1000 тонн секвестрации углерода в новых, устойчиво управляемых лесах) или в другие технологии секвестрации.

---

### 57. `p1269` — длина перевода / длина оригинала: 1.15

**Оригинал:**

> If we want to reverse humanity’s collective suicidal rush towards irreversible climate change, governments may have to declare war on it. From this perspective, would not corporate ECO contributions be a rather modest change, compared to what Roosevelt was ordering?

**Перевод в документе:**

> Если мы хотим остановить коллективное самоубийственное движение человечества к необратимому изменению климата, правительствам, возможно, придется объявить ему войну. В этом свете разве корпоративные взносы в ECO не будут выглядеть довольно скромным изменением по сравнению с тем, что предписывал Рузвельт?

---

### 58. `p1329` — длина перевода / длина оригинала: 0.96

**Оригинал:**

> Ultimately, our plea for a monetary ecology is a call for a new mode of economic governance. The aim is to allow two types of economy to coexist peacefully: on the one hand, the mainstream economy will continue to use conventional money in the competitive economy and, on the other hand, the rebirth of a cooperative economy will see regions, cities, neighbourhoods, NGOs and grass-roots citizens’ organisations develop the full potential of their projects without needing to depend on the supply of bank-debt currency.

**Перевод в документе:**

> В конечном счете, наш призыв к денежной экологии — это призыв к новому способу экономического управления. Цель состоит в том, чтобы позволить двум типам экономики мирно сосуществовать: с одной стороны, основная экономика продолжит использовать обычные деньги в конкурентной среде, а с другой — возрождение кооперативной экономики позволит регионам, городам, районам, НКО и низовым гражданским инициативам полностью раскрыть потенциал своих проектов, не завися от притока банковских кредитных денег.

---

### 59. `p1330` — длина перевода / длина оригинала: 1.02

**Оригинал:**

> Most crucially, we need to revisit our *monetary governance*. This is a highly unusual question in the current framework. Democratic governance is a weak spot for all monetary systems, be it the official one, or the ongoing complementary experimental systems. Due to our monetary ‘blind spot’, we are used to leaving governance of the monetary system to an opaque and highly centralised set of institutions. We can hardly envisage what the democratic management of a plurality of currencies might look like. This may be the most crucial unresolved organisational question we need to deal with, if we are serious about sustainability.

**Перевод в документе:**

> Самое важное — нам необходимо пересмотреть наше *денежное управление*. В нынешней системе это крайне необычный вопрос. Демократическое управление — слабое место всех денежных систем, будь то официальная или экспериментальные дополнительные системы. Из-за нашего «слепого пятна» в денежных вопросах мы привыкли доверять управление финансовой системой непрозрачным и крайне централизованным институтам. Мы с трудом можем представить, как могло бы выглядеть демократическое управление множеством валют. Возможно, это самый важный нерешенный организационный вопрос, с которым нам предстоит разобраться, если мы всерьез заботимся об устойчивом развитии.

---

### 60. `p1340` — длина перевода / длина оригинала: 1.02

**Оригинал:**

> The stakes are unprecedentedly high. But the possibilities for creative solutions are also near at hand – solutions that do not further strain public budgets, that have already demonstrated their effectiveness in practice, that can turn populations from hopeless rage to fruitful engagement within their communities, and that can preserve corporate profits, but not at the expense of social and environmental health. We still have a fighting chance to give birth to a sustainable world that works for everyone…

**Перевод в документе:**

> Ставки высоки как никогда. Но и возможности для творческих решений совсем рядом — решения, которые не ложатся дополнительным бременем на государственные бюджеты, которые уже доказали свою эффективность на практике, которые способны превратить безнадежную ярость населения в продуктивное участие в жизни общества и которые могут сохранить корпоративные прибыли, не принося при этом в жертву социальное и экологическое благополучие. У нас все еще есть шанс построить устойчивый мир, который будет работать на благо каждого…

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение длин — сюда стекается всё, что модель сократила или выбросила.

### 1. `p0208` — длина перевода / длина оригинала: 0.81

**Оригинал:**

> For the population at large, perhaps the most important learning needed is to understand non-linearity, specifically the difference between linear and exponential growth. We are now dealing with an increasingly non-linear world. Grasping these different dynamics will be useful in understanding what is happening to us, and what to do about it.

**Перевод в документе:**

> Для широких слоев населения, пожалуй, важнее всего осознать нелинейность процессов, а именно — разницу между линейным и экспоненциальным ростом. Мы живем во все более нелинейном мире. Понимание этих различий поможет разобраться в том, что с нами происходит и что с этим делать.

---

### 2. `p1040` — длина перевода / длина оригинала: 0.84

**Оригинал:**

> A second option would be to trade shares for goods or services within the community. The tree shares would thus function as a local medium of exchange and provide some additional liquidity in that community. In principle, the value of the exchange should reflect the value of the tree currency at the time of the exchange, but the owner of the shares and the person accepting them could decide for themselves the most appropriate arrangement.

**Перевод в документе:**

> Второй вариант — обменивать акции на товары или услуги внутри сообщества. В этом случае акции будут выполнять функцию местного средства платежа и обеспечат дополнительную ликвидность. В принципе, стоимость обмена должна отражать текущую ценность «древесной валюты», но владелец акций и принимающая сторона могут самостоятельно договориться о наиболее подходящих условиях.

---

### 3. `p0572` — длина перевода / длина оригинала: 0.84

**Оригинал:**

> Of perhaps even greater importance, the physics of flow networks also explains why excessively large and efficient organisations may pull the whole system toward collapse. In essence, large, highly efficient organisations in the network ‘out compete’ the smaller organisations for resources, drawing ever more energy, information and resources into the big, and away from the smaller participants.

**Перевод в документе:**

> Пожалуй, еще важнее то, что физика сетей потоков объясняет, почему чрезмерно крупные и эффективные организации могут привести всю систему к краху. По сути, крупные, высокоэффективные организации в сети «вытесняют» более мелких участников в борьбе за ресурсы, забирая все больше энергии, информации и ресурсов себе и лишая их остальных.

---

### 4. `p0095` — длина перевода / длина оригинала: 0.86

**Оригинал:**

> The World Business Academy has long been committed to advancing cutting-edge business information among business executives charged with navigating their businesses through the challenging times we live in. The Academy thank s Bernard Lietaer and his associates for presenting this Report to us, and encourages all levels of government and private enterprises to use the Report to begin a serious conversation on the critical issues the Report illuminates – while there is still time.

**Перевод в документе:**

> World Business Academy уже давно стремится распространять передовую бизнес-информацию среди руководителей, которым приходится вести свои компании через сложные времена, в которые мы живем. Академия благодарит Бернара Литара и его коллег за представленный доклад и призывает все уровни власти и частные предприятия использовать его как основу для серьезного обсуждения критических проблем — пока у нас еще есть время.

---

### 5. `p0634` — длина перевода / длина оригинала: 0.86

**Оригинал:**

> From our perspective, based on the Ecological Economics Paradigm illustrated in Figure 2.3 (page 31), the issue of keeping both inflation and deflation at bay is also relevant, but represents only one of several relevant issues with regards to sustainability.

**Перевод в документе:**

> С нашей точки зрения, основанной на парадигме экологической экономики (см. рис. 2.3 на стр. 31), проблема сдерживания инфляции и дефляции также актуальна, но она представляет собой лишь один из аспектов устойчивого развития.

---

### 6. `p1342` — длина перевода / длина оригинала: 0.88

**Оригинал:**

> Our sincere hope is that as the world of the old economy breaks down, the seeds of a new and more humane economy may be given a chance to emerge. “There is a rabbinical teaching that if the world is ending and the Messiah arrives, you first plant a tree; and then see if the story is true. Islam has a similar teaching that tells its adherents that if they have a palm cutting in their hand on Judgement Day, plant the cutting.”¹⁷

**Перевод в документе:**

> Мы искренне надеемся, что по мере того, как старая экономика рушится, семена новой, более гуманной экономики получат шанс прорасти. «В раввинистическом учении говорится: если мир подходит к концу и приходит Мессия, сначала посади дерево, а потом посмотри, правдива ли эта история. В исламе есть похожее наставление: если в Судный день у тебя в руках саженец пальмы, посади его».¹⁷

---

### 7. `p0524` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> The fourth step will consist of testing the ‘complex flow network’ methodology on real-life natural ecosystems and exposing the structural conditions required for a network to be sustainable. We will demonstrate that these findings are applicable to any complex system possessing a similar structure regardless of what circulates in a given network – biomass in an ecosystem, electrons in an electrical power network or money in an economy.

**Перевод в документе:**

> Четвертый этап будет посвящен тестированию методологии «сложных потоковых сетей» на реальных природных экосистемах и выявлению структурных условий, необходимых для устойчивости сети. Мы покажем, что эти выводы применимы к любой сложной системе с аналогичной структурой, независимо от того, что именно циркулирует в сети — биомасса в экосистеме, электроны в энергосистеме или деньги в экономике.

---

### 8. `p0047` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> We are not telling the truth about money. Yet money is at the core of the economy. And economy is ruling the world. It dominates human welfare from cradle to grave. It rules the use of the planet’s natural resources and the quality of the environment. Today it is generally admitted that many limits of the Earth’s ecosystem have been overshot. There is evidence that the present course is not sustainable.

**Перевод в документе:**

> Мы не говорим правду о деньгах. А ведь деньги — основа экономики. Экономика же правит миром. Она определяет благополучие человека от колыбели до могилы, распоряжается использованием природных ресурсов планеты и состоянием окружающей среды. Сегодня общепризнанно, что многие пределы экосистемы Земли уже превышены. Очевидно, что нынешний курс не является устойчивым.

---

### 9. `p0979` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> For example, one 17-year-old at the Vilnius event had the dream of learning Buddhism in the mountains of Burma. The Doraland Foundation would contractually promise to make this experience possible in exchange for 3,000 Doras. Doraland would not only raise the funds — through sponsorships and donations — to purchase the airline ticket payable in national currency, but also arrange for the necessary contacts in Burma. The teenager could earn 3,000 Doras by teaching 300 hours of conversational English to others, for example, or perhaps by training adults wanting to acquire computer skills. Another young person wanted to spend a weekend with her hero, a Nobel laureate in physics. In exchange for 2,000 Doras or the equivalent of 200 hours of teaching an art skill, the Foundation would facilitate the meeting with the physicist. Another group might want to learn to sail around the world or to create a neighbourhood greenhouse for year-round food production. The media attention attracted by these endeavours will help to raise sponsorships and donations and can also help generate more creative and socially useful dreams, as well as more offers to teach/train a range of skills.

**Перевод в документе:**

> Например, один 17-летний участник встречи в Вильнюсе мечтал изучать буддизм в горах Бирмы. Фонд Doraland мог бы по контракту взять на себя обязательство осуществить эту мечту в обмен на 3000 дор. Фонд не только собрал бы средства (через спонсорство и пожертвования) на покупку авиабилета, оплачиваемого в национальной валюте, но и обеспечил бы необходимые контакты в Бирме. Подросток мог бы заработать 3000 дор, например, преподавая разговорный английский в течение 300 часов или обучая взрослых компьютерной грамотности. Другая участница хотела провести выходные со своим кумиром — лауреатом Нобелевской премии по физике. В обмен на 2000 дор (эквивалент 200 часов обучения какому-либо творческому навыку) фонд организовал бы ей встречу с ученым. Другая группа могла бы захотеть научиться кругосветному плаванию или создать общественный огород для круглогодичного выращивания продуктов. Внимание СМИ к таким начинаниям поможет привлечь спонсоров, а также стимулирует появление более креативных и социально значимых проектов и предложений по обучению различным навыкам.

---

### 10. `p1122` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> In contrast, when the business cycle booms, both suppliers and corporations have an increased need for raw materials and demand for them goes up. The TRCs could be cashed in and used in the commodity markets. The amount of TRCs in circulation would decrease when the business cycle is at its maximum and counteract inflationary pressures. In summary, by providing monetary liquidity during phases when credit gets tight in the conventional system and contracting when business is booming, TRC-denominated exchanges would stabilise the overall business cycle.

**Перевод в документе:**

> И наоборот, в периоды экономического подъема спрос на сырье со стороны поставщиков и корпораций растет. В такие моменты TRC можно обналичивать и использовать на товарных рынках. Объем TRC в обращении будет сокращаться на пике делового цикла, что позволит сдерживать инфляционное давление. В конечном счете, обеспечивая денежную ликвидность в периоды, когда в традиционной системе кредитование затруднено, и сокращаясь в периоды бума, расчеты в TRC будут способствовать стабилизации общего делового цикла.

---

### 11. `p1322` — длина перевода / длина оригинала: 0.90

**Оригинал:**

> Citizens, NGOs, businesses and political decision-makers are already using the concept of a monetary ecology, simply by creating it. Fortunately for all of us, these courageous pioneers are following Sophocles’ centuries-old advice: “One must learn by doing the thing; for though you think you know it, you have no certainty, until you try.”

**Перевод в документе:**

> Граждане, НПО, бизнес и политические лидеры уже используют концепцию денежной экологии, просто создавая её. К счастью для всех нас, эти смелые первопроходцы следуют многовековому совету Софокла: «Нужно учиться, делая дело; ибо, хотя ты думаешь, что знаешь его, у тебя нет уверенности, пока ты не попробуешь».

---

### 12. `p0414` — длина перевода / длина оригинала: 0.91

**Оригинал:**

> A *monetary (or currency) crisis¹⁵* takes place when the currency of a country suddenly suffers a substantial drop in value in relation to other currencies. In order to refer to the three types of crises above using a single word, we will define as a *systemic crisis* any large-scale disturbance involving either a sovereign-debt crisis, a monetary crisis and/or a banking crisis or any combination of those three.

**Перевод в документе:**

> *Валютный (или денежный) кризис¹⁵* происходит, когда валюта страны внезапно и существенно обесценивается по отношению к другим валютам. Чтобы обозначить все три вышеупомянутых типа кризисов одним термином, мы будем называть *системным кризисом* любое масштабное потрясение, включающее кризис суверенного долга, валютный кризис и/или банковский кризис, либо любое их сочетание.

---

### 13. `p0723` — длина перевода / длина оригинала: 0.91

**Оригинал:**

> The fourth built-in mechanism causing our current monetary system to be unsustainable is the tendency over time for wealth to become concentrated. The renowned historian Arnold Toynbee concluded that the collapse of twenty-one different civilisations could be attributed to just two causes:

**Перевод в документе:**

> Четвертый встроенный механизм, делающий нашу нынешнюю денежную систему неустойчивой, — это тенденция к постепенной концентрации богатства. Известный историк Арнольд Тойнби пришел к выводу, что крах двадцати одной цивилизации можно объяснить всего двумя причинами:

---

### 14. `p1356` — длина перевода / длина оригинала: 0.91

**Оригинал:**

> This report has been substantially enriched with suggestions by academic colleagues from various backgrounds. It was not possible to reference all of them in footnotes, for which we apologise. The responsibility for any remaining errors and omissions rests with the co-authors.

**Перевод в документе:**

> Доклад был существенно дополнен предложениями наших коллег-ученых из самых разных областей. К сожалению, мы не смогли упомянуть их всех в сносках, за что приносим свои извинения. Ответственность за любые оставшиеся ошибки и недочеты лежит на соавторах.

---

### 15. `p1001` — длина перевода / длина оригинала: 0.91

**Оригинал:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a *personal-responsibility-building* dimension to the Wellness Tokens, in the direction of what has been called ‘genuine autonomy’ of the patient in recent literature inspired by Ivan Illich.¹⁴ The system offers positive rather than negative incentives to motivate and reward people for their behaviours rather than punish them for ‘misbehaviours’. The perception should be that the system increases the opportunities available to people rather than imposing restrictions on them.

**Перевод в документе:**

> Важно подчеркнуть: система Wellness-токенов, будучи направленной на улучшение поведения в вопросах здоровья, не относится к категории «неовикторианских» карательных механизмов, где людей лишают финансовой поддержки, если они заболевают из-за (как утверждается) определенного образа жизни (например, при раке легких у заядлых курильщиков или болезнях сердца у тех, кто придерживался вредного рациона). Наша цель, как мы уже объясняли, носит просветительский характер и связана с повышением осознанности и стремлением к личной автономии. Именно поэтому система делает акцент на профилактике, а не на лечении. Идея состоит не в том, чтобы использовать «финансовые стимулы» для запугивания людей, как это делают санкционные механизмы, включающиеся уже после того, как болезнь развилась. В Wellness-токенах действительно заложен аспект *формирования личной ответственности* в духе того, что в литературе, вдохновленной работами Ивана Иллича, называют «подлинной автономией» пациента.¹⁴ Система предлагает позитивные, а не негативные стимулы: она поощряет людей за правильное поведение, а не наказывает за «неправильное». Восприниматься это должно как расширение возможностей человека, а не как наложение ограничений.

---

### 16. `p0695` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> Too often, growth is confused with progress. Growth is the quantitative increase in size or throughput of an entity. In contrast, progress is the idea that the world can increasingly become better. The former is purely quantitative, while the latter is primarily qualitative. One should not automatically assume that all growth leads to progress. That is why American essayist Edward Abbey could claim that “growth for the sake of growth is the ideology of the cancer cell”.¹³

**Перевод в документе:**

> Слишком часто рост путают с прогрессом. Рост — это количественное увеличение размера или пропускной способности системы. Прогресс же — это идея о том, что мир может становиться лучше. Первое чисто количественно, второе — преимущественно качественно. Не стоит автоматически полагать, что любой рост ведет к прогрессу. Именно поэтому американский эссеист Эдвард Эбби мог утверждать, что «рост ради роста — это идеология раковой клетки»¹³.

---

### 17. `p0525` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> The fifth step will then consist of applying this methodology to monetary systems. We will clarify how the pressures towards greater efficiency in finance, economics and engineering have often occurred at the expense of resilience. This is the cause of the systemic brittleness of the monetary and banking system. This dynamic is also the key to a solution that offers greater monetary sustainability.

**Перевод в документе:**

> Пятый этап — применение этой методологии к денежным системам. Мы проясним, как стремление к повышению эффективности в финансах, экономике и инженерии зачастую шло в ущерб живучести. Именно это является причиной системной хрупкости денежно-кредитной и банковской сферы. Эта динамика также содержит ключ к решению, которое может обеспечить большую денежную устойчивость.

---

### 18. `p0978` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> The starting point was the formation of a Lithuanian Learning Foundation with the working title ‘Doraland’. This foundation is designed to enable individuals or groups to make one of their dreams come true, in exchange for a contractually agreed amount of ‘Dora’ currency. This currency is earned through teaching and/or learning activities, such as offering courses in English, in computer skills, in Italian cuisine or in any other skill that can be contributed.

**Перевод в документе:**

> Отправной точкой стало создание Литовского фонда знаний с рабочим названием «Doraland». Задача фонда — дать возможность отдельным людям или группам воплотить свою мечту в обмен на договорное количество валюты «дора». Эта валюта зарабатывается через преподавание или обучение: например, проведение курсов английского языка, компьютерной грамотности, итальянской кухни или любых других навыков, которыми человек готов поделиться.

---

### 19. `p0230` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> The response of governments to our current monetary predicaments brings to mind a statement by Winston Churchill about the United States during World War II: “You can always count on the Americans to do the right thing… after they have tried everything else!” Since the great banking meltdown of 2008, policy makers have indeed been trying everything possible to resolve the financial crisis except addressing the structure of the monetary system itself.

**Перевод в документе:**

> Реакция правительств на нынешние денежные трудности напоминает высказывание Уинстона Черчилля о США времен Второй мировой войны: «Американцы всегда найдут единственно верное решение… после того, как перепробуют все остальные!» После масштабного банковского краха 2008 года политики действительно перепробовали всё возможное для преодоления финансового кризиса, кроме одного — изменения самой структуры денежной системы.

---

### 20. `p0661` — длина перевода / длина оригинала: 0.92

**Оригинал:**

> Money is generally assumed to be a passive accounting instrument that facilitates exchanges more efficiently than barter. Money is seen as an oil lubricating the exchange process, but not otherwise changing its nature. It is therefore automatically assumed that the type of exchange medium one uses does not affect the nature of exchanges, the time horizon of our investments, or the relationships between us as users. We will demonstrate why all these assumptions are wrong.

**Перевод в документе:**

> Обычно деньги считают пассивным инструментом учета, который просто делает обмен более эффективным, чем бартер. Деньги воспринимаются как своего рода смазка для процесса обмена, не меняющая его сути. Поэтому автоматически предполагается, что тип используемого средства обмена никак не влияет на характер сделок, горизонт планирования инвестиций или отношения между нами как пользователями. Мы покажем, почему все эти предположения ошибочны.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин.

### 1. `p1231` — длина перевода / длина оригинала: 1.30

**Оригинал:**

> From a purely economic angle, if an annual tax of €1,000 can be replaced with 10 hours of civic activity per household, anyone earning less than €100 per hour should be interested in joining the system. Ideally, however, the Civic Economy’s goals and activities would have the support of the residents, as something they would gladly volunteer for if they didn’t have to earn a living. The Civics system has the added benefit of allowing people to earn an income from the activities; see

**Перевод в документе:**

> С чисто экономической точки зрения, если ежегодный налог в 1000 евро можно заменить 10 часами общественно полезной деятельности на домохозяйство, то любой, кто зарабатывает менее 100 евро в час, должен быть заинтересован в участии в этой системе. В идеале, однако, цели и виды деятельности в рамках «Гражданской экономики» (Civic Economy) должны пользоваться поддержкой жителей — они должны воспринимать их как то, чем они с радостью занялись бы добровольно, если бы им не приходилось зарабатывать на жизнь. Дополнительное преимущество системы Civics заключается в том, что она позволяет людям получать доход от такой деятельности; см.

---

### 2. `p0676` — длина перевода / длина оригинала: 1.27

**Оригинал:**

> This results in joblessness and the host of social problems it causes. Most social indicators (such as mental health, crime or suicide) deteriorate significantly during recessions. Political instabilities including violent revolutions are usually triggered by economic downturns.

**Перевод в документе:**

> Это приводит к безработице и целому ряду сопутствующих социальных проблем. Большинство социальных показателей (таких как психическое здоровье, уровень преступности или количество самоубийств) значительно ухудшаются во время рецессий. Политическая нестабильность, включая насильственные революции, как правило, провоцируется именно экономическими спадами.

---

### 3. `p0795` — длина перевода / длина оригинала: 1.24

**Оригинал:**

> Social capital is a mediator between different social variables. One measure of this is the prevalence of stress-related psychosomatic syndromes, which is inversely correlated to perceived social capital.⁵⁴ Eroding social capital is also accompanied by large income inequality and higher mortality rates.⁵⁵ Such findings point to a link between social capital, money, wealth distribution and health parameters. A motivation system relying primarily on monetary incentives to promote unconscious competition among its users may currently not be the best way forward. As explained above, we know that cooperative approaches yield superior results for all participants in the long run.

**Перевод в документе:**

> Социальный капитал выступает посредником между различными социальными переменными. Одним из показателей этого является распространенность психосоматических синдромов, связанных со стрессом, которая обратно пропорциональна уровню воспринимаемого социального капитала.⁵⁴ Разрушение социального капитала также сопровождается значительным неравенством доходов и более высокими показателями смертности.⁵⁵ Подобные выводы указывают на связь между социальным капиталом, деньгами, распределением богатства и показателями здоровья. Система мотивации, опирающаяся прежде всего на денежные стимулы для поощрения подсознательной конкуренции между пользователями, в настоящее время может оказаться не лучшим путем развития. Как было объяснено выше, мы знаем, что кооперативные подходы в долгосрочной перспективе приносят лучшие результаты для всех участников.

---

### 4. `p1255` — длина перевода / длина оригинала: 1.24

**Оригинал:**

> Niall Ferguson’s study of ‘The Cash Nexus’ has shown that all major innovations in the domain of government finance over the past three centuries were triggered by wars. Armed conflict seems to trigger innovations and technologies that otherwise might never come to light. The scale of destruction caused by the most-likely climate change scenarios is worse than any war ever fought on this planet and is one of our main motivations for publishing this report now. (Please refer back to

**Перевод в документе:**

> Исследование Найла Фергюсона «Денежная связь» (The Cash Nexus) показало, что все значимые инновации в сфере государственных финансов за последние три столетия были спровоцированы войнами. Вооруженные конфликты, по-видимому, подталкивают к созданию инноваций и технологий, которые в ином случае могли бы никогда не появиться. Масштабы разрушений, предсказываемые наиболее вероятными сценариями изменения климата, превосходят последствия любой войны, когда-либо случавшейся на нашей планете, и это одна из главных причин, побудивших нас опубликовать данный отчет именно сейчас. (Пожалуйста, обратитесь к

---

### 5. `p0338` — длина перевода / длина оригинала: 1.24

**Оригинал:**

> The reference material for our analysis in this Report also includes the work known as ‘The Natural Step’, by Karl-Henrik Robert, a physician from Sweden who started by researching the systemic reasons for the escalating cancer rates in his medical practice. The Natural Step offers four system conditions that must be met for a sustainable world:

**Перевод в документе:**

> В качестве справочного материала для анализа в данном Отчете мы также используем концепцию «Естественный шаг» (The Natural Step), разработанную шведским врачом Карлом-Хенриком Робером. Его исследования начались с попыток выявить системные причины роста заболеваемости раком, с которыми он сталкивался в своей медицинской практике. «Естественный шаг» предлагает четыре системных условия, необходимых для создания устойчивого мира:

---

### 6. `p0745` — длина перевода / длина оригинала: 1.23

**Оригинал:**

> We have found only one study of the transfer of wealth via interest. It was performed in Germany in 1982 when interest rates were at 5.5%.²⁸ The German population was grouped into ten income categories of 2.5 million households each. Over a one-year period, transfers between these ten groups totalled Deutsche Mark (DM) 270 billion in interest paid and received. Graphing the net interest transfers (interest gained minus interest paid) for each of these ten household categories allows us to see the net effect (see Figure 5.5).

**Перевод в документе:**

> Нам удалось найти лишь одно исследование, посвященное перераспределению богатства через механизм процентных ставок. Оно было проведено в Германии в 1982 году, когда процентные ставки составляли 5,5%²⁸. Население Германии было разделено на десять доходных групп по 2,5 миллиона домохозяйств в каждой. За один год общая сумма перечислений между этими десятью группами в виде выплаченных и полученных процентов составила 270 миллиардов немецких марок (DM). Построение графика чистого перераспределения процентов (полученные проценты минус выплаченные) для каждой из этих десяти категорий домохозяйств позволяет нам увидеть итоговый эффект (см. Рисунок 5.5).

---

### 7. `p0101` — длина перевода / длина оригинала: 1.23

**Оригинал:**

> A fish will never create fire while immersed in water. We will never create sustainability while immersed in the present financial system. There is no tax, or interest rate, or disclosure requirement that can overcome the many ways the current money system blocks sustainability.

**Перевод в документе:**

> Рыба никогда не добудет огонь, пока находится под водой. Мы никогда не достигнем устойчивого развития, пока остаёмся внутри нынешней финансовой системы. Никакие налоги, процентные ставки или требования к раскрытию информации не способны преодолеть те многочисленные барьеры, которыми существующая денежная система блокирует устойчивое развитие.

---

### 8. `p0706` — длина перевода / длина оригинала: 1.23

**Оригинал:**

> The core question is therefore: what kind of growth does the financial system require from the real economy? The short answer is that compound interest requires exponential growth. Compounded interest is a mathematical impossibility on a finite planet.¹⁶

**Перевод в документе:**

> Таким образом, главный вопрос заключается в следующем: какого именно роста требует финансовая система от реальной экономики? Краткий ответ: сложные проценты требуют экспоненциального роста. Но на планете с ограниченными ресурсами экспоненциальный рост, основанный на сложных процентах, математически невозможен.¹⁶

---

### 9. `p0468` — длина перевода / длина оригинала: 1.22

**Оригинал:**

> As of early 2012, forty-four out of the fifty US States face bankruptcy. They are under increasing pressure to start ‘Public-Private Partnerships’, called P3s in the USA and Private Finance Initiatives (PFI) in the UK. What actually occurs in these benign-sounding partnerships is that governments are obliged to sell off existing infrastructure, built and paid for with taxpayers’ money, in order to reduce existing debt or pay for current public expenditures. Once the infrastructure is privatised, new owners can charge fees for the use of a once free public utility, or increase existing tolls. Thus taxpayers will end up paying twice for the same infrastructure and the second time could be more expensive than the first, given that many infrastructural assets are natural monopolies.

**Перевод в документе:**

> По состоянию на начало 2012 года сорок четыре из пятидесяти штатов США оказались на грани банкротства. Они испытывают растущее давление, вынуждающее их переходить к «государственно-частному партнерству» (ГЧП, в США называемому P3, а в Великобритании — PFI). То, что на самом деле происходит в рамках этих благозвучных партнерств, заключается в том, что правительства вынуждены распродавать существующую инфраструктуру, построенную и оплаченную на деньги налогоплательщиков, чтобы сократить существующий долг или оплатить текущие государственные расходы. Как только инфраструктура приватизируется, новые владельцы могут взимать плату за пользование тем, что когда-то было бесплатным общественным благом, или повышать существующие тарифы. Таким образом, налогоплательщики в конечном итоге заплатят дважды за одну и ту же инфраструктуру, причем второй раз может обойтись дороже первого, учитывая, что многие инфраструктурные объекты являются естественными монополиями.

---

### 10. `p0430` — длина перевода / длина оригинала: 1.22

**Оригинал:**

> In 2010, the US Census Bureau reported 4 million additional Americans in poverty, making a total of 44 million, or one in every seven residents. The rise was steepest for children, with one in five children affected.²¹ Because the crisis started later in Europe than in the USA, the full impact on poverty in Europe has not yet been fully documented.

**Перевод в документе:**

> В 2010 году Бюро переписи населения США сообщило об увеличении числа бедных американцев на 4 миллиона человек, в результате чего их общее количество достигло 44 миллионов, или каждого седьмого жителя страны. Наиболее резкий рост наблюдался среди детей: пострадал каждый пятый ребенок.²¹ Поскольку в Европе кризис начался позже, чем в США, полное влияние на уровень бедности в Европе пока еще не задокументировано в полной мере.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до документа.

### 1. `p1285` — совпадение символов с оригиналом: 30%

**Оригинал:**

> Systems like Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu, and Civics provide environments for people who otherwise would never meet to work together on projects that develop their gifts and the health and strength of their community. If people are given a powerful voice on which projects are chosen, these systems can rebuild and strengthen social capital over time.

**Перевод в документе:**

> Такие системы, как Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu и Civics, создают среду, в которой люди, иначе никогда бы не встретившиеся, могут вместе работать над проектами, развивающими их таланты, а также укрепляющими здоровье и силу их сообщества. Если предоставить людям реальную возможность влиять на выбор проектов, эти системы способны со временем восстановить и укрепить социальный капитал.

---

### 2. `p0379` — совпадение символов с оригиналом: 26%

**Оригинал:**

> USA, where he was acknowledged as Distinguished Fellow of the American Economic Association. He made significant contributions in both conventional economics (utility theory, input-output analysis, production theory) and in paradigm-shifting economics – what along the lines of Thomas Kuhn might be labelled ‘revolutionary’ economics. He applied rigorous systemic thinking on how to link economics to the physical laws of sustainability in *Analytical Economics* (1966). Paul Samuelson said in the Preface that he considered Georgescu-Roegen to be “a scholar’s scholar, and an economist’s economist”. He added: “I defy any informed economist to remain complacent after meditating over this essay”. Nevertheless, complacency is what has greeted that book and its successor, *The Entropy Law and the Economic Process*. Ecological economist Herman Daly concludes in his ‘Obituary Essay on Georgescu-Roegen’: “One does not expect fundamental change to occur overnight. But twenty-five years is a reasonable time over which to hope for progress. What is the matter with our discipline?” (Daly [1996] p.192 and p.198). Even Samuelson himself, for all his professed lack of complacency, never updated his bestselling economics textbooks to integrate Georgescu-Roegen’s findings. Even 30 years before Georgescu-Roegen, Frederick Soddy, a Nobel laureate in Chemistry, had drawn the attention of economists to their ignorance of entropy and the unsustainability of compound interest, all without success. 14 Orio Giarini ‘Science and Economy: The Case of Uncertainty and Disequilibrium’ *Cadmus,* Vol I, No.2 (April 2011) pp.25-34. 15 Hazel Henderson: *Paradigms in Progress: Life beyond Economics* (1991). See also Hazel Henderson: *Creating Alternative*

**Перевод в документе:**

> США, где был признан почетным членом Американской экономической ассоциации. Он внес значительный вклад как в традиционную экономическую теорию (теория полезности, анализ «затраты-выпуск», теория производства), так и в экономику, меняющую парадигму — то, что в духе Томаса Куна можно назвать «революционной» экономикой. В своей книге *Analytical Economics* (1966) он применил строгий системный подход к тому, как связать экономику с физическими законами устойчивого развития. Пол Самуэльсон в предисловии отметил, что считает Джорджеску-Регена «ученым для ученых и экономистом для экономистов». Он добавил: «Бросаю вызов любому сведущему экономисту: попробуйте остаться спокойными после размышлений над этим эссе». Тем не менее именно спокойствие стало ответом на эту книгу и ее продолжение — *The Entropy Law and the Economic Process*. Эколог-экономист Герман Дейли в своем некрологе Джорджеску-Регену заключил: «Не стоит ожидать, что фундаментальные перемены произойдут в одночасье. Но двадцать пять лет — разумный срок, чтобы надеяться на прогресс. Что не так с нашей дисциплиной?» (Дейли [1996], с. 192 и 198). Даже сам Самуэльсон, несмотря на свое декларируемое отсутствие самоуспокоенности, так и не обновил свои бестселлеры по экономике, чтобы включить в них выводы Джорджеску-Регена. Еще за 30 лет до Джорджеску-Регена Фредерик Содди, лауреат Нобелевской премии по химии, пытался обратить внимание экономистов на их невежество в вопросах энтропии и неустойчивости сложных процентов, но все было тщетно. 14 Орио Джарини, «Science and Economy: The Case of Uncertainty and Disequilibrium», *Cadmus*, том I, № 2 (апрель 2011 г.), с. 25–34. 15 Хейзел Хендерсон: *Paradigms in Progress: Life beyond Economics* (1991). См. также Хейзел Хендерсон: *Creating Alternative*

---

### 3. `p0370` — совпадение символов с оригиналом: 26%

**Оригинал:**

> What is colloquially called the ‘Nobel prize for economics’ has as official title the ‘Sveriges Riksbank Prize in Economic Sciences in Memory of Alfred Nobel’ (Swedish: *Sveriges riksbanks pris* *i ekonomisk vetenskap till Alfred Nobels minne*). This prize happens to be funded by a central bank, actually the oldest central bank in existence, also called today the Bank of Sweden. Does this reinforce some biases within academia? Peter Nobel, the great-great nephew of Alfred Nobel, seems to think so.

**Перевод в документе:**

> То, что в обиходе называют «Нобелевской премией по экономике», официально именуется «Премией Шведского государственного банка по экономическим наукам памяти Альфреда Нобеля» (швед. *Sveriges riksbanks pris i ekonomisk vetenskap till Alfred Nobels minne*). Так вышло, что эта премия финансируется центральным банком — фактически старейшим из существующих, который сегодня называется Банком Швеции. Усиливает ли это определенные предвзятости в академической среде? Петер Нобель, внучатый племянник Альфреда Нобеля, по-видимому, считает, что да.

---

### 4. `p1410` — совпадение символов с оригиналом: 23%

**Оригинал:**

> It continues with portraits of agencies that research, develop and support local currencies such as IRTA, STRO, QOIN, Community Forge and the German Regional Money Association. The book ends with ‘Future Positive’, a summary of lessons learned, recommendations for action and brief portraits of the Bristol Pound (to be launched in 2012) and the Nanto (launch due in 2013) – both being supported by local authorities.

**Перевод в документе:**

> Далее в книге представлены организации, которые занимаются исследованием, разработкой и поддержкой местных валют, такие как IRTA, STRO, QOIN, Community Forge и Ассоциация региональных денег Германии. Завершает книгу раздел «Позитивное будущее» — краткое изложение извлеченных уроков, рекомендации к действию и описание Бристольского фунта (запуск в 2012 году) и валюты Nanto (запуск в 2013 году), внедрение которых поддерживается местными органами власти.

---

### 5. `p0929` — совпадение символов с оригиналом: 20%

**Оригинал:**

> Footnotes 1 John Kenneth Galbraith, *Money: Whence It Came, Where It Went* (1975), p.5. 2 For instance, the Natural Savings instrument presented in Chapter VII would mainly be a savings tool, not a medium of exchange or unit of account. In many civilisations, the unit of account was also different from the medium of exchange. A case in point is Homeric Greece, where the unit of account was the ox but where, for the sake of convenience, actual exchanges were often performed with ingots of bronze or other commodities. 3 For the arguments offered in this paragraph, see Philippe Derudder and André-Jacques Holbecq (2008) p.17. 4 Friedrich Nietzsche, *Thus Spoke Zarathustra,* translated by Adrian del Caro and edited by Robert Pippin (2006). 5 The original is elegantly succinct: *“Nervos belli, pecuniam infinitam”* from Cicero’s *Fifth* *Philippic.* See Jon Hall, *The Philippics*, in

**Перевод в документе:**

> Сноски 1 Джон Кеннет Гэлбрейт, *«Деньги: откуда они берутся и куда уходят»* (1975), с. 5. 2 Например, инструмент «Естественные сбережения», представленный в главе VII, был бы преимущественно инструментом накопления, а не средством обмена или счетной единицей. Во многих цивилизациях счетная единица также отличалась от средства обмена. Яркий тому пример — гомеровская Греция, где счетной единицей был бык, но для удобства реальные обмены часто совершались с помощью бронзовых слитков или других товаров. 3 Аргументы, приведенные в этом абзаце, см. в работе Филиппа Деруддера и Андре-Жака Ольбека (2008), с. 17. 4 Фридрих Ницше, *«Так говорил Заратустра»*, перевод Адриана дель Каро под редакцией Роберта Пиппина (2006). 5 Оригинал элегантно лаконичен: *«Nervos belli, pecuniam infinitam»* («Нервы войны — бесконечные деньги») из «Пятой филиппики» Цицерона. См. Джон Холл, *«Филиппики»*, в

---

### 6. `p0113` — совпадение символов с оригиналом: 20%

**Оригинал:**

> A common English idiom is, ‘Like a fish out of water ’. It refers to someone or something in a very unaccustomed and awkward situation. But unless the fish does move out of water, its experiments will never lead to fire. We are going to have to go through an awkward period, experimenting with new currency systems, if we are to have any chance of our efforts leading to sustainability.

**Перевод в документе:**

> В английском языке есть идиома «как рыба без воды» (like a fish out of water). Она описывает человека или ситуацию, в которой кто-то чувствует себя крайне неуютно и неловко. Но если рыба не выберется из воды, она никогда не научится добывать огонь. Нам придётся пройти через период неловких экспериментов с новыми валютными системами, если мы хотим, чтобы наши усилия привели к устойчивому развитию.

---

### 7. `p1231` — совпадение символов с оригиналом: 20%

**Оригинал:**

> From a purely economic angle, if an annual tax of €1,000 can be replaced with 10 hours of civic activity per household, anyone earning less than €100 per hour should be interested in joining the system. Ideally, however, the Civic Economy’s goals and activities would have the support of the residents, as something they would gladly volunteer for if they didn’t have to earn a living. The Civics system has the added benefit of allowing people to earn an income from the activities; see

**Перевод в документе:**

> С чисто экономической точки зрения, если ежегодный налог в 1000 евро можно заменить 10 часами общественно полезной деятельности на домохозяйство, то любой, кто зарабатывает менее 100 евро в час, должен быть заинтересован в участии в этой системе. В идеале, однако, цели и виды деятельности в рамках «Гражданской экономики» (Civic Economy) должны пользоваться поддержкой жителей — они должны воспринимать их как то, чем они с радостью занялись бы добровольно, если бы им не приходилось зарабатывать на жизнь. Дополнительное преимущество системы Civics заключается в том, что она позволяет людям получать доход от такой деятельности; см.

---

### 8. `p0157` — совпадение символов с оригиналом: 20%

**Оригинал:**

> Today’s foreign exchange and financial derivatives markets dwarf anything else on our planet. In 2010, the volume of foreign exchange transactions reached $4 trillion *per day*. One day’s exports or imports of *all* goods and services in the world amount to about 2% of that figure. Which means that 98% of transactions on these markets are purely speculative. This foreign exchange figure does not include derivatives, whose notional volume was $600 trillion – or eight times the entire world’s *annual* GDP in 2010.

**Перевод в документе:**

> Сегодняшние рынки иностранной валюты и финансовых деривативов затмевают собой всё остальное на нашей планете. В 2010 году объем валютных операций достигал 4 триллионов долларов *в день*. Мировой объем экспорта и импорта *всех* товаров и услуг за сутки составляет лишь около 2% от этой суммы. Это означает, что 98% сделок на этих рынках носят чисто спекулятивный характер. Данный показатель по валютному рынку даже не включает деривативы, условный объем которых составил 600 триллионов долларов — это в восемь раз больше всего мирового ВВП за 2010 год.

---

### 9. `p1277` — совпадение символов с оригиналом: 19%

**Оригинал:**

> It would also be possible for governments to stimulate the economy deliberately in a counter-cyclical way with Biwa, Civics and ECOs. When a country or city experiences recession in the bank-debt money economy, and unemployment is high – as is the case today in Europe or the USA – the government at the appropriate level increases the quantities of Biwa, Civics or ECOs that it requires from citizens or businesses. If and when an inflationary boom occurs, governments can correspondingly reduce the requirement for government-issued currency.

**Перевод в документе:**

> Правительства также могли бы целенаправленно стимулировать экономику контрциклическими методами с помощью Biwa, Civics и ECO. Когда в стране или городе наблюдается рецессия в экономике, основанной на банковском долге, и растет безработица — как это происходит сегодня в Европе или США, — власти соответствующего уровня могут увеличивать объем Biwa, Civics или ECO, которые они принимают от граждан или предприятий. В случае же инфляционного бума правительства могут, соответственно, сокращать требования по использованию государственных валют.

---

### 10. `p1098` — совпадение символов с оригиналом: 18%

**Оригинал:**

> Once the TRC is created, it remains in circulation for a period determined entirely by the users. For example: **(2a) First user –** The oil producer decides to pay one of his or her suppliers (e.g., a German engineering company for the construction of an off-shore rig) partly or completely in TRCs. **(2b) Next user(s) –** The German engineering firm decides, in turn, to purchase speciality steel from a Korean steel mill partly or completely in TRCs. The Korean mill then uses the TRCs to pay a mining company in Australia and so on. **(2c) End user –** Each TRC remains in circulation for as long as its various users continue to use it. This could be for just one transaction or an infinite number of transactions, without any particular date of expiration. The process comes to an end when a particular user decides to cash in the TRCs, thereby becoming the End User.

**Перевод в документе:**

> После создания TRC остается в обращении в течение периода, определяемого исключительно самими пользователями. Например: **(2a) Первый пользователь —** нефтедобывающая компания решает расплатиться со своим поставщиком (например, немецкой инжиниринговой компанией, строящей морскую буровую платформу) частично или полностью в TRC. **(2b) Следующий пользователь (пользователи) —** немецкая инжиниринговая фирма, в свою очередь, решает закупить специальную сталь у корейского металлургического завода, оплатив сделку частично или полностью в TRC. Затем корейский завод использует эти TRC для оплаты услуг горнодобывающей компании в Австралии, и так далее. **(2c) Конечный пользователь —** каждая единица TRC остается в обращении до тех пор, пока ее владельцы продолжают ею пользоваться. Это может быть как одна-единственная транзакция, так и бесконечное их количество — срок действия валюты не ограничен. Процесс завершается, когда конкретный пользователь решает обналичить TRC, становясь тем самым «конечным пользователем».

---
