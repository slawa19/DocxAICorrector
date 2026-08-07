# Аудиокнига, финальный подтверждающий прогон 2026-08-06 — money_sustainability, материал для просмотра глазами

Книга: Bernard Lietaer et al., *Money and Sustainability: The Missing Link* (`tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-160516072426.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_fin2_money_sustainability`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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
6. **Пустые и почти пустые абзацы — все 16**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1318; вернулось: 1317;
дошло до narration-артефакта: 1296.
Пул прозы, из которого делалась выборка: 467 абзацев.
Медианное отношение длин по прозе: 0.9963.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0048` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Governments, media and most leaders mak e every possible effort to convince public opinion to stick to mainstream think ing. If society wishes to be or to become successful, they say, we have to k eep faith in the current paradigm. The gospel still is that everything has to be expressed in monetary terms. And that there is no salvation outside the dominant financial systems and bank ing practices, a monopoly and a major power instrument. Closed systems are preferred to open ones. Complexity is avoided. Indeed a shortsighted vision on sustainable solutions…

**В озвучку попало:**

> Правительства, средства массовой информации и большинство лидеров делают всё возможное, чтобы убедить общество придерживаться привычных взглядов. Они говорят: если мы хотим добиться успеха, нужно сохранять веру в текущую парадигму. Господствует убеждение, что всё должно измеряться в денежном эквиваленте. И что нет спасения вне доминирующих финансовых систем и банковских практик, которые стали монополией и главным инструментом власти. Закрытые системы предпочитают открытым. Сложности стараются избегать. Поистине, это близорукий взгляд на устойчивые решения.

---

### 2. `p0053` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> While the issue is by definition global, the CoR-EU felt the Report should primarily be addressed on its behalf to a recognised, authoritative and independent European body. The most appropriate choice seemed to be *Finance Watch,* a public interest association, recently created on the initiative of members of the European Parliament. It is dedicated to mak ing finance work for the good of society, strengthening the voice of society in financial regulation reforms by conducting citizen advocacy and presenting public interest arguments to lawmak ers as a counterweight to private interest lobbying by the financial industry.

**В озвучку попало:**

> Хотя проблема по определению носит глобальный характер, мы посчитали, что доклад следует адресовать признанному, авторитетному и независимому европейскому органу. Наилучшим выбором показалась организация «Finance Watch» — ассоциация общественных интересов, созданная по инициативе членов Европейского парламента. Она призвана сделать финансы полезными для общества, усиливая его голос в реформах финансового регулирования. Организация занимается гражданской адвокацией и представляет аргументы в пользу общественных интересов перед законодателями, выступая противовесом лоббированию частных интересов со стороны финансовой индустрии.

---

### 3. `p0058` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> There is a great challenge here for the European U nion. We dare hope that the publication of *Money and Sustainability: The Missing Link* will inspire many a decision mak er and opinion leader to change course now, choosing new, creative approaches in monetary issues.

**В озвучку попало:**

> Перед Европейским союзом стоит серьезный вызов. Мы смеем надеяться, что публикация нашего доклада «Деньги и устойчивое развитие: недостающее звено» вдохновит многих лиц, принимающих решения, и лидеров мнений изменить курс. Мы призываем их выбрать новые, творческие подходы к решению денежных вопросов.

---

### 4. `p0072` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> The book contains powerful arguments that need to be listened to, digested and acted upon. The section on how money affects sustainability mak es the k ey point that the global crises we face are interconnected. The financial crisis is but one dimension of a multi-dimensional puzzle. However, the book is more than a diagnosis of the ills and travails of our monetary system; it also points to new ways of reforming our financial system, to pioneering ideas and to potential solutions. The call for alternative think ing and innovative strategies is timely and necessary.

**В озвучку попало:**

> Эта книга содержит весомые аргументы, к которым необходимо прислушаться, осмыслить их и начать действовать. Раздел о влиянии денег на устойчивое развитие подчеркивает ключевую мысль: глобальные кризисы, с которыми мы сталкиваемся, взаимосвязаны. Финансовый кризис — лишь одно из измерений многогранной проблемы. Однако книга — это не просто диагноз болезней нашей денежной системы. Она указывает на новые пути реформирования финансов, предлагает новаторские идеи и возможные решения. Призыв к альтернативному мышлению и инновационным стратегиям сегодня как никогда актуален и необходим.

---

### 5. `p0081` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> This study complements other endeavours of WAAS stressing the essential value and role of human capital. The Report reminds us that money is a man-made instrument intended to help society optimise human welfare. The prevailing monetary system encourages the multiplication of money for destabilising speculative investment rather than for productive investment that creates jobs, raises real incomes and promotes social equity. The Report examines alternative monetary strategies that can help mobilise under-utilised social resources, especially the huge number of unemployed and underemployed young people and adults whose human potential is ignored and squandered by the current system. This Report is a call for prompt political and economic action.

**В озвучку попало:**

> Это исследование дополняет другие начинания нашей Академии, подчеркивающие исключительную ценность и роль человеческого капитала. Доклад напоминает нам, что деньги — это созданный человеком инструмент, призванный помогать обществу повышать уровень благосостояния. Нынешняя денежная система поощряет приумножение капитала ради дестабилизирующих спекулятивных инвестиций, а не ради продуктивных вложений, которые создают рабочие места, повышают реальные доходы и способствуют социальному равенству. В докладе рассматриваются альтернативные денежные стратегии. Они могут помочь задействовать неиспользуемые социальные ресурсы, особенно огромную армию безработных и частично занятых молодых людей и взрослых, чей потенциал нынешняя система игнорирует и растрачивает впустую. Этот доклад — призыв к решительным политическим и экономическим действиям.

---

### 6. `p0099` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> Fiat currency issued by private institutions through the creation of debt has been used by nations for centuries. Its deadly effects are becoming apparent. But its ability to alleviate the symptoms of distress has led to its use anyway. We can only hope that in this century we will begin to use less deadly alternatives.

**В озвучку попало:**

> Фиатные деньги, которые частные институты выпускают через создание долга, страны используют уже много веков. Их губительные последствия становятся всё более очевидными. Но способность этих денег временно снимать симптомы кризиса заставляет пользоваться ими и дальше. Остается надеяться, что в этом столетии мы начнем применять менее опасные альтернативы.

---

### 7. `p0101` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> A fish will never create fire while immersed in water. We will never create sustainability while immersed in the present financial system. There is no tax, or interest rate, or disclosure requirement that can overcome the many ways the current money system blocks sustainability.

**В озвучку попало:**

> Рыба никогда не добудет огонь, пока находится под водой. Мы никогда не создадим устойчивую систему, пока погружены в нынешнюю финансовую модель. Никакие налоги, процентные ставки или требования к отчетности не помогут преодолеть многочисленные барьеры, которыми нынешняя денежная система блокирует устойчивое развитие.

---

### 8. `p0102` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> I used not to think this. Indeed, I did not think about the money system at all. I took it for granted as a neutral and inevitable aspect of human society. But since beginning to read Bernard’s analyses I have a very different view. He is not alone. For example Thomas Greco has written on this topic. But the depth of Bernard’s practical experience, theoretical understanding, and historical perspectives on the financial system leave him without peer.

**В озвучку попало:**

> Раньше я так не думал. По правде говоря, я вообще не задумывался о денежной системе. Я принимал её как нечто нейтральное и неизбежное в человеческом обществе. Но, начав изучать аналитику Бернарда, я изменил свое мнение. И я не одинок. Например, об этом писал Томас Греко. Однако глубина практического опыта, теоретических знаний и исторический взгляд Бернарда на финансовую систему делают его уникальным экспертом.

---

### 9. `p0143` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> It is our contention that the ‘Missing Link’ between finance and the environment, between money and sustainability, lies elsewhere. What this Report demonstrates beyond doubt is a structural monetary flaw – a flaw in the very manner in which we create money – that is generating our disconcerting problems. The inescapable conclusion? That, in order to face the challenges of the 21st century, we need to rethink and overhaul our entire monetary system.

**В озвучку попало:**

> Мы утверждаем, что «недостающее звено» между финансами и окружающей средой, между деньгами и устойчивостью, кроется в другом. Этот отчет вне всяких сомнений доказывает наличие структурного денежного изъяна — ошибки в самом способе создания денег, — которая и порождает наши тревожные проблемы. Неизбежный вывод таков: чтобы справиться с вызовами двадцать первого века, нам необходимо переосмыслить и полностью перестроить всю нашу денежную систему.

---

### 10. `p0151` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Debates about economic issues rarely reveal the paradigm from which an economist is speaking. We start by making explicit the conceptual framework that underlies our approach, and compare it with other paradigms currently in use. Rather than defining environmental and social issues as ‘externalities’, our approach sees economic activities as a subset of the social realm, which, in turn, is a subset of the biosphere. This view provides the basis for the emergence of a new set of pragmatic tools, flexible enough to address many of our economic, social and environmental challenges.

**В озвучку попало:**

> [thoughtful] Споры об экономических проблемах редко раскрывают парадигму, с позиций которой выступает экономист. Мы начнем с того, что четко обозначим концептуальную основу нашего подхода и сравним ее с другими моделями, которые используются сегодня. Вместо того чтобы считать экологические и социальные проблемы «внешними эффектами», мы рассматриваем экономическую деятельность как часть социальной сферы, которая, в свою очередь, является частью биосферы. Такой взгляд позволяет создать набор практических инструментов, достаточно гибких для решения многих наших экономических, социальных и экологических задач.

---

### 11. `p0209` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> In closing, it would be naïve to think of complementary currencies as a magic bullet to solve all our current and future problems. However, rethinking our money is a necessary ingredient in any effective solution. We can no longer afford to overlook complementary currencies as the ‘Missing Link’ that can deliver a money system which promotes sustainability rather than undermining it at every turn.

**В озвучку попало:**

> В заключение скажу: было бы наивно считать дополнительные валюты волшебной таблеткой от всех наших текущих и будущих проблем. И все же переосмысление денег — необходимая часть любого эффективного решения. Мы больше не можем игнорировать дополнительные валюты. Это то самое «недостающее звено», которое позволит создать денежную систему, способствующую устойчивому развитию, а не подрывающую его на каждом шагу.

---

### 12. `p0271` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Conceptual relationships between the field of economics and the natural world can be described in three different ways. The most conventional view is to treat anything that is not dealt with unambiguously within one’s own theoretical framework as an ‘externality’ (see Figure 2.1). This economic view defines its own field as completely self-contained and excludes any other consideration as irrelevant. For instance, in such a view, the natural world is reduced to a resource, an input that is considered to be cost-free – to the extent that no money is exchanged to acquire it.

**В озвучку попало:**

> [serious] Концептуальные отношения между экономикой и миром природы можно описать тремя способами. Самый распространенный подход — рассматривать всё, что не вписывается в рамки текущей теории, как «внешний фактор». Эта экономическая модель определяет свою область как полностью самодостаточную, а всё остальное считает неважным. Например, в такой системе мир природы сводится лишь к ресурсу или сырью. Если за получение этого ресурса не нужно платить деньги, он считается бесплатным.

---

### 13. `p0290` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> The standard measurement of economic progress thus remains the Gross National Product (GNP) per capita, which captures neither the depletion of natural resources, nor the quality of growth, nor the distribution of its benefits. Furthermore, market prices rarely reveal the real costs of a product or service. Their production and disposal can create damage that remains ignored in the conventional accounting system.¹⁶ Sufficient evidence now exists for a fundamental rethinking to take place if sustainability is taken seriously. If humanity’s decisions continue to be made on the basis of the Traditional Economics paradigm (Figure 2.1) or even the OECD paradigm (Figure 2.2), all signs point to a bleak future for our human condition and our planet. Indeed, humanity’s unsustainable behaviour is provoking the sixth great mass extinction of the geological record at a rate of 30,000 species per year or three species per hour. Having a greater awareness of the limitations of the dominant economic paradigms is therefore not merely of academic relevance.

**В озвучку попало:**

> [serious] В результате стандартным мерилом экономического прогресса остается валовой национальный продукт на душу населения. Этот показатель не учитывает ни истощение природных ресурсов, ни качество роста, ни распределение его плодов. Более того, рыночные цены редко отражают реальную стоимость продукта или услуги. Их производство и утилизация могут наносить ущерб, который игнорируется традиционной системой учета. Сейчас накоплено достаточно доказательств того, что если мы всерьез относимся к устойчивому развитию, необходим фундаментальный пересмотр подходов. Если человечество продолжит принимать решения, опираясь на традиционную экономическую парадигму или даже на модель Организации экономического сотрудничества и развития, все указывает на мрачное будущее для нас и нашей планеты. Неустойчивое поведение человечества уже провоцирует шестое великое массовое вымирание видов. Оно идет со скоростью тридцать тысяч видов в год, или три вида в час. Поэтому лучшее понимание ограничений доминирующих экономических парадигм — это не просто академический интерес.

---

### 14. `p0309` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> In some circles, the word ‘sustainability’ has become synonymous with constraints, heavy-handed governmental regulations, or even a leftist conspiracy. This perception has been amplified by well-funded disinformation campaigns underwritten by various vested business interests, in particular from the carbon energy industries.²² As will be seen in Chapter V, such campaigns are an example of the systematic short-term thinking automatically generated by our monetary system and the manner in which it ‘programs’ our behaviour.

**В озвучку попало:**

> [serious] В некоторых кругах слово «устойчивость» стало синонимом ограничений, жесткого государственного регулирования или даже левацкого заговора. Такое восприятие подогревается хорошо финансируемыми кампаниями по дезинформации, которые спонсируются различными заинтересованными бизнес-структурами, в особенности представителями индустрии ископаемого топлива. Как мы увидим в пятой главе, подобные кампании — это пример систематического мышления краткосрочными категориями, которое автоматически порождается нашей денежной системой и тем, как она «программирует» наше поведение.

---

### 15. `p0344` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> Understanding the community systems that are capable of satisfying a fuller range of human needs is a cornerstone of environmental and human sustainability. The Earth Charter Commission, working with the World Resources Institute and Global Community Initiatives, developed a comprehensive methodology for communities to evaluate their own sustainability and plan for a more sustainable future.³¹

**В озвучку попало:**

> [thoughtful] Понимание общественных систем, способных удовлетворять более широкий спектр человеческих потребностей, является краеугольным камнем экологической и социальной устойчивости. Комиссия Хартии Земли в сотрудничестве с Институтом мировых ресурсов и инициативой «Глобальное сообщество» разработала комплексную методологию. Она помогает сообществам оценивать собственную устойчивость и планировать более благополучное будущее.

---

### 16. `p0346` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In order to spell out the economic paradigm in which we operate, the monetary dimension of the economy must explicitly be explored. Not all paradigms do this – some, and most notably the dominant Traditional Economics approach, view money as a passive element not affecting the way that individuals and collectives choose to act. The Ecological Economics paradigm, in the way we conceive it here, takes the monetary dimension much more seriously. How so? This is what we intend to explain in the remainder of this chapter. The exploration of this feature is what most sets this study apart from other economic texts and studies on sustainability.³²

**В озвучку попало:**

> [serious] Чтобы прояснить экономическую парадигму, в которой мы существуем, необходимо детально изучить денежный аспект экономики. Не все подходы делают это. Наиболее заметный из них — традиционная экономическая школа — рассматривает деньги как пассивный элемент, который не влияет на выбор людей и коллективов. Экологическая экономика, в том виде, в каком мы её здесь представляем, относится к денежной сфере гораздо серьёзнее. Почему? Именно это мы и собираемся объяснить в оставшейся части главы. Исследование этой особенности — то, что больше всего отличает данное исследование от других работ по экономике и устойчивому развитию.

---

### 17. `p0404` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> What most analysts fail to realise is that to identify structural problems, one must focus on what is common among all financial and monetary crises rather than on their differences. In metaphorical terms, a view of the entire forest is required, rather than a close-up inspection of any individual tree or of a specific type of tree.

**В озвучку попало:**

> Большинство аналитиков не осознают главного: чтобы выявить структурные проблемы, нужно сосредоточиться на том, что общего у всех финансовых и денежных кризисов, а не на их различиях. Говоря метафорически, нам нужен взгляд на весь лес целиком, а не пристальное изучение каждого отдельного дерева или конкретного их вида.

---

### 18. `p0448` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Notice that this impact is completely independent of the quality of any government’s own policies, before or during the crisis. While much has been made of the case of Greece where fraud was involved, not much can be blamed on governments or citizens in Iceland, Ireland, Latvia, Denmark or Spain, all hit with sudden increases in their national debt, which reached 35% - 75% of their GDP. The irony is that, as soon as governments borrow these large sums from the financial system to save the system itself from bankruptcy, the financial system concludes that governments are now too indebted and need to be ‘disciplined’.

**В озвучку попало:**

> Заметьте, что это воздействие совершенно не зависит от качества политики того или иного правительства до или во время кризиса. Много говорилось о случае Греции, где имело место мошенничество. Однако нельзя винить правительства или граждан Исландии, Ирландии, Латвии, Дании или Испании. Все эти страны столкнулись с внезапным ростом национального долга, который достиг 35–75 процентов от их ВВП. Ирония в том, что как только правительства занимают эти огромные суммы у финансовой системы, чтобы спасти саму систему от банкротства, эта же система приходит к выводу, что правительства теперь слишком закредитованы и их нужно «дисциплинировать».

---

### 19. `p0449` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Figure 3.4 brings together the various components of the impact of banking crises on government finances. The direct fiscal cost of bailing out the banking system is added to output losses with an automatic drop in tax income. Governments thus have no other option than to increase their indebtedness. This, in turn, results in the downgrading of the creditworthiness of affected countries and makes their debt more expensive. What does all this lead to?

**В озвучку попало:**

> На рисунке 3.4 собраны различные компоненты влияния банковских кризисов на государственные финансы. К прямым бюджетным расходам на спасение банковской системы добавляются потери от снижения производства и автоматическое падение налоговых поступлений. У правительств не остается иного выбора, кроме как увеличивать свою задолженность. Это, в свою очередь, приводит к снижению кредитного рейтинга пострадавших стран и делает их долг более дорогим. К чему все это ведет?

---

### 20. `p0453` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> The timing of this sudden increase in government debt is particularly unfortunate. The current decade is one in which the OECD countries and their governments have to deal with unprecedented pressures not amenable to being postponed. As mentioned in Chapter I, two critical and predictable challenges during the next decade will be the transition to a post-carbon economy and the sharp increase in financial requirements for retiring baby boomers.

**В озвучку попало:**

> [thoughtful] Время для такого резкого роста государственного долга выбрано крайне неудачно. В нынешнем десятилетии правительства стран Организации экономического сотрудничества и развития столкнулись с беспрецедентным давлением, которое невозможно отложить на потом. Как уже упоминалось в первой главе, в ближайшие десять лет перед нами встанут две критически важные и предсказуемые задачи: переход к экономике, свободной от углеродного топлива, и резкое увеличение расходов на обеспечение вышедшего на пенсию поколения «бэби-бумеров».

---

### 21. `p0468` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> As of early 2012, forty-four out of the fifty US States face bankruptcy. They are under increasing pressure to start ‘Public-Private Partnerships’, called P3s in the USA and Private Finance Initiatives (PFI) in the UK. What actually occurs in these benign-sounding partnerships is that governments are obliged to sell off existing infrastructure, built and paid for with taxpayers’ money, in order to reduce existing debt or pay for current public expenditures. Once the infrastructure is privatised, new owners can charge fees for the use of a once free public utility, or increase existing tolls. Thus taxpayers will end up paying twice for the same infrastructure and the second time could be more expensive than the first, given that many infrastructural assets are natural monopolies.

**В озвучку попало:**

> [thoughtful] К началу 2012 года сорок четыре из пятидесяти штатов США оказались на грани банкротства. Они испытывают растущее давление, вынуждающее их переходить к так называемым государственно-частным партнерствам. В США их называют «Пи-три», а в Великобритании — «Частными финансовыми инициативами». На деле в этих партнерствах с благозвучными названиями правительства вынуждены распродавать существующую инфраструктуру, построенную и оплаченную на деньги налогоплательщиков, чтобы сократить долг или покрыть текущие расходы. После приватизации новые владельцы могут взимать плату за пользование тем, что раньше было бесплатным общественным благом, или повышать существующие тарифы. В итоге налогоплательщики платят за одну и ту же инфраструктуру дважды, причем второй раз может обойтись дороже первого, учитывая, что многие инфраструктурные объекты являются естественными монополиями.

---

### 22. `p0469` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Private investments in public utilities can generate a ‘win-win’ situation when designed and implemented properly. In several European countries, there is a well-established practice of, for instance, the private sector building new toll-paying highways. When such auctions are well prepared and transparent, the results can be beneficial to all parties. However, the P3s currently being proposed are different from their historical precedents in three ways:

**В озвучку попало:**

> Частные инвестиции в коммунальные услуги могут создать ситуацию «выигрыш-выигрыш», если они грамотно спроектированы и реализованы. В ряде европейских стран существует устоявшаяся практика, когда частный сектор строит новые платные автомагистрали. Если такие аукционы подготовлены прозрачно, результаты могут быть полезны всем сторонам. Однако предлагаемые сейчас государственно-частные партнерства отличаются от исторических прецедентов по трем пунктам.

---

### 23. `p0514` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Unfortunately this does not account for what is currently happening in the financial or monetary domain. After each crash, the banking system is bailed out at government expense, and the old way of doing business is taken up again after fine tuning of the regulatory or managerial environment. The fundamental structure – a monopoly of money created through bank debt – is invariably left intact.

**В озвучку попало:**

> К сожалению, это не объясняет того, что происходит в финансовой и денежной сферах сегодня. После каждого краха банковскую систему спасают за государственный счёт. А после небольшой настройки правил или смены руководства старый способ ведения дел возобновляется. Фундаментальная структура — монополия на деньги, создаваемые через банковский долг, — остаётся неизменной.

---

### 24. `p0538` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> As a starting point, let us distinguish between systems according to the characteristics of their causality mechanism. At one end of the spectrum lies simple *linear causality*. This concept dates back to the classical Greeks. Since Newton’s time, effective mathematical tools such as mechanics have been available to study processes involving linear causality. At the other end of the spectrum, one finds systems with a *lack of causality,* without interaction among variables. This latter realm is best explored with the mathematical tools of statistics. The domain of *complexity* lies between these two extremes; here, there are several causes interacting and there are multiple interactions between variables. Figure 4.1 illustrates this dynamic.

**В озвучку попало:**

> [thoughtful] Для начала давайте разделим системы по типу их причинно-следственных связей. На одном полюсе находится простая линейная причинность. Эта концепция восходит еще к древним грекам. Со времен Ньютона у нас есть эффективные математические инструменты, такие как механика, для изучения процессов с линейной причинностью. На другом полюсе находятся системы, где причинность практически отсутствует, а переменные не взаимодействуют друг с другом. Эту область лучше всего исследовать с помощью математического аппарата статистики. Область сложности лежит между этими двумя крайностями. Здесь действуют сразу несколько причин, которые постоянно взаимодействуют между собой, создавая множество связей.

---

### 25. `p0565` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Resilience measures the ability of a system to recover from a disturbance, an attack or a change in the environment*.* With these definitions in mind, we can now define and precisely quantify a complex flow system’s sustainability using a single metric.

**В озвучку попало:**

> Устойчивость измеряет способность системы восстанавливаться после потрясений, внешних воздействий или изменений среды. С учетом этих определений мы можем точно измерить устойчивость сложной потоковой системы с помощью одного показателя.

---

### 26. `p0567` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Diversity and connectivity also play an important role in throughput efficiency, but in the opposite direction: *effi ciency increases* as diversity and connectivity *decreases*. Furthermore, as a flow system becomes more efficient, it tends to build up a kind of self-fuelling momentum (technically called ‘autocatalysis’) that eliminates diversity as it gradually streamlines the process. In general, increasingly efficient systems tend to become more directed, less diverse and, consequently, more brittle.

**В озвучку попало:**

> Разнообразие и связность также важны для пропускной эффективности, но действуют в обратном направлении: эффективность растет по мере снижения разнообразия и количества связей. Более того, по мере роста эффективности система склонна наращивать своего рода самоподдерживающийся импульс, который технически называется «автокатализом». Он постепенно устраняет разнообразие, упрощая процессы. В целом, все более эффективные системы становятся более направленными, менее разнообразными и, как следствие, более хрупкими.

---

### 27. `p0569` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> When we want to express sustainability graphically, three variables are involved: diversity, interconnectivity and the relative weight put on efficiency *vs.* resilience. We are thus dealing with a four-dimensional object, which is difficult to render in a two-dimensional graph. In Appendix D2, a one-minute animation movie presents all four dimensions. In the same section a sequence of three-dimensional graphs gives an idea of what shape we are dealing with.

**В озвучку попало:**

> Когда мы хотим выразить устойчивость графически, в игру вступают три переменные: разнообразие, взаимосвязанность и относительный вес эффективности по сравнению с устойчивостью. Мы имеем дело с четырехмерным объектом, который трудно отобразить на обычном двухмерном графике. В приложении D2 представлена минутная анимация, показывающая все четыре измерения. В том же разделе серия трехмерных графиков дает представление о том, с какой формой мы работаем.

---

### 28. `p0573` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> This, of course, causes the big organisations to get bigger still, and the smaller ones to die off, just as Schumpeter ’s classical ‘creative destruction’ theory predicts. Unfortunately, killing off large numbers of smaller organisations reduces resilience, increases instability and steadily moves the whole system towards collapse (i.e., sustainability = 0). Common examples include: large, unrestrained predators killing off all their prey causing an ecosystem to collapse; digging large canals in the New Orleans delta, which drained soil from the wetlands, causing the city to sink and the wetlands to die; and monopolies of commerce which kill off so many small competitors that a positive feedback cycle of ‘the more you have, the more you get’ locks into a ‘winner takes all’ game. This can lead to an economic ‘bubble’, a shimmering bubble of wealth over a feeble, eviscerated real economy. This law of physics explains why we once introduced anti-trust laws.

**В озвучку попало:**

> Конечно, это заставляет крупные организации расти еще больше, а мелкие — отмирать, как и предсказывает классическая теория «созидательного разрушения» Шумпетера. К сожалению, уничтожение большого числа мелких организаций снижает жизнестойкость, увеличивает нестабильность и неуклонно ведет всю систему к коллапсу, когда устойчивость падает до нуля. Примеры этого повсюду: крупные хищники, бесконтрольно истребляющие добычу, что ведет к гибели экосистемы; прокладка больших каналов в дельте Нового Орлеана, из-за чего почва осушилась, город начал проседать, а водно-болотные угодья погибли; или торговые монополии, которые устраняют так много мелких конкурентов, что запускается цикл положительной обратной связи «чем больше имеешь, тем больше получаешь», превращаясь в игру «победитель получает всё». Это может привести к экономическому «пузырю» — сверкающей оболочке богатства над слабой, обескровленной реальной экономикой. Именно этот физический закон объясняет, почему в свое время были введены антимонопольные законы.

---

### 29. `p0574` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> In conclusion: “Life tends to optimise, rather than maximise. Maximisation is another word for addiction.”³⁰ Indeed, in the real world, all networks corresponding to natural ecosystems operate around the optimal point, within a specific range called the ‘window of viability’, 31 which lies on either side of this optimum, as can be seen in Figure 4.5.

**В озвучку попало:**

> В заключение можно сказать: «Жизнь стремится к оптимизации, а не к максимизации. Максимизация — это другое слово для обозначения зависимости». Действительно, в реальном мире все сети, соответствующие природным экосистемам, работают вокруг оптимальной точки. Они находятся в пределах особого диапазона, называемого «окном жизнеспособности», которое лежит по обе стороны от этого оптимума, как показано на рисунке четыре-пять.

---

### 30. `p0628` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> Coming from a completely different perspective, Friedrich Hayek, one of the leaders of the Austrian school of economics, wrote a short book in 1976 that has remained mostly ignored, entitled *Denationalization of Money*.⁴⁸ His premise was that a monopoly can no more competently manage the equilibrium between the supply of, and demand for, money than it can for shoes, automobiles, food or health care. As a solution he recommended competition between financial institutions: each bank should be allowed to print its own paper money. Such competition between banks would keep the value of money stable, since money losing in value hurts creditors, while money gaining in value hurts debtors. Hence the market would select the ‘best monies’, the ones that strike the best balance between depreciation and appreciation. Although we do not agree with Hayek or the Austrian school in other domains, we certainly can agree with Hayek’s assessment of the current monetary system:

**В озвучку попало:**

> [serious] Фридрих Хайек, один из лидеров австрийской экономической школы, подошел к вопросу с совершенно иной стороны. В 1976 году он написал небольшую книгу под названием «Частные деньги», которая долгое время оставалась почти незамеченной. Его исходная посылка заключалась в том, что монополия не может эффективно управлять балансом спроса и предложения денег — точно так же, как она не может эффективно управлять рынком обуви, автомобилей, продуктов питания или медицинских услуг. В качестве решения Хайек предложил конкуренцию между финансовыми институтами: каждому банку следовало бы разрешить выпускать собственные бумажные деньги. Такая конкуренция между банками поддерживала бы стабильность стоимости денег, поскольку обесценивание валюты вредит кредиторам, а рост ее стоимости — должникам. В итоге рынок сам выбрал бы «лучшие деньги», которые обеспечивают оптимальный баланс между инфляцией и дефляцией. Хотя мы не во всем согласны с Хайеком и австрийской школой, мы определенно поддерживаем его оценку нынешней денежной системы:

---

### 31. `p0638` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> This chapter has provided a step-by-step explanation, with backing from scientific evidence, that a structural cause is behind the repeated systemic crises described in Chapter III. The complex flow network approach to monetary and financial stability is *not* a metaphor: it is systemic bio-mimicry.

**В озвучку попало:**

> [serious] В этой главе мы шаг за шагом, опираясь на научные данные, объяснили, что за повторяющимися системными кризисами, описанными ранее, стоят глубинные структурные причины. Подход к финансовой стабильности через теорию сложных сетей потоков — это не просто метафора, а применение принципов биомимикрии к экономическим системам.

---

### 32. `p0643` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> Three hundred years of cat-and-mouse games between regulatory authorities and the financial system have proven that regulation – while useful and necessary – may reduce the frequency, but never avoid the re-occurrence, of systemic crises. Paul Romer, a Senior Fellow at the Stanford Institute for Economic Policy Research, says: “Every decade or so, any finite system of financial regulation will lead to a systemic financial crisis”.⁵¹ Is infinite regulation really the only solution?

**В озвучку попало:**

> Триста лет игры в кошки-мышки между регулирующими органами и финансовой системой доказали, что регулирование — при всей его полезности и необходимости — может снизить частоту кризисов, но никогда не предотвратит их повторение. Пол Ромер, старший научный сотрудник Стэнфордского института исследований экономической политики, отмечает: «Примерно раз в десятилетие любая конечная система финансового регулирования будет приводить к системному финансовому кризису». Неужели бесконечное ужесточение правил — единственный выход?

---

### 33. `p0755` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> The third built-in mechanism leading to wealth disparity is related to special interest groups, and lobbying. Lobbies can play a positive role in a democracy. They provide a feedback loop between the branch of government that creates laws and the citizens and organisations affected by those laws.

**В озвучку попало:**

> [thoughtful] Третий встроенный механизм, ведущий к неравенству богатства, связан с группами особых интересов и лоббизмом. Лобби могут играть положительную роль в демократическом обществе. Они создают обратную связь между законодательной властью и гражданами или организациями, на которых эти законы влияют.

---

### 34. `p0767` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Cohesion within a society arises not as a result of spatial proximity, common language, religious beliefs or relationships, but through that society’s ability to create mechanisms, rituals and behaviour patterns that generate a spirit of cooperation, trust and shared responsibility.³⁷ These behaviours are learned and continually reinforced through socialisation. Studies have demonstrated that the acts of giving and receiving activate the same regions in the brain; and giving usually leads to greater happiness than spending on oneself.³⁸ Social capital can be private or public, can vary in formality and organisation, but always has an aspect of social commitment. It also defines the types of institutions and rules that give a society its identity. “A peculiar feature of social capital is that it is not accumulated through a standard mechanism of individual investment, since most of its benefits are not privately appropriable. Rather, or at least to a much greater extent, it is accumulated through social participation in group activities.”³⁹ Social capital is therefore not a mere by-product of society.

**В озвучку попало:**

> Сплоченность общества возникает не из-за географической близости, общего языка, религии или родственных связей. Она рождается благодаря способности общества создавать механизмы, ритуалы и модели поведения, которые формируют дух сотрудничества, доверия и общей ответственности. Эти навыки усваиваются и постоянно подкрепляются в процессе социализации. Исследования показали, что акты дарения и получения помощи активируют одни и те же области мозга, причем дарение обычно приносит человеку больше счастья, чем траты на самого себя. Социальный капитал может быть частным или общественным, различаться по степени формальности, но он всегда подразумевает социальные обязательства. Он также определяет типы институтов и правил, формирующих идентичность общества. Особенность социального капитала в том, что он не накапливается через стандартные механизмы индивидуальных инвестиций, поскольку большинство его преимуществ невозможно присвоить частным образом. Скорее, он накапливается через участие в групповой деятельности. Таким образом, социальный капитал — это не просто побочный продукт общества.

---

### 35. `p0780` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Perhaps the reason why social capital is so hard to quantify is that the term itself is an economic projection on a foreign realm. It represents a reductionist view, objectifying the human spirit and the most elevated of human capacities as just another input into material production. It implicitly assumes that material production is the only relevant criterion for the good and wellbeing of a society.

**В озвучку попало:**

> Возможно, социальный капитал так трудно поддается количественной оценке потому, что сам термин является попыткой навязать экономические рамки чуждой им сфере. Это редукционистский подход, который превращает человеческий дух и высшие способности человека в еще один ресурс для материального производства. Он неявно предполагает, что материальное производство — единственный критерий благополучия общества.

---

### 36. `p0827` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> There is also a great deal of emphasis on central banks being ‘independent’, meaning ‘independent from any political influence’. What is *not* meant is ‘independent from the influence of the banking system’; however this remains unstated. For instance, the majority of board members of the US Federal Reserve are bankers.

**В озвучку попало:**

> Также много внимания уделяется «независимости» центральных банков, под которой понимается их независимость от политического влияния. При этом никто не говорит о независимости от влияния самой банковской системы. Этот момент остается за скобками. Показательно, что большинство членов совета управляющих Федеральной резервной системы США — это банкиры.

---

### 37. `p0835` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Political and financial historian Niall Ferguson provides an insightful analysis of the connection between money and power in modern times in his book *The Cash Nexus*. He shows how most significant financial and fiscal innovations of the past three hundred years have evolved from the need to finance wars. “The costs of war have fluctuated quite widely throughout history. These fluctuations have been the driving force of financial innovation.”⁶ Today’s monetary framework is therefore an institutionalisation of arrangements between government and the financial system, historically negotiated in a context of war.

**В озвучку попало:**

> Историк политики и финансов Ниал Фергюсон в своей книге «Денежный узел» дает глубокий анализ связи между деньгами и властью в современную эпоху. Он показывает, как большинство значимых финансовых и фискальных инноваций за последние триста лет возникли из необходимости финансировать войны. Фергюсон отмечает, что расходы на войну сильно колебались на протяжении истории, и именно эти колебания были движущей силой финансовых инноваций. Таким образом, современная денежная система — это институционализация договоренностей между правительством и финансовой системой, которые исторически складывались в условиях войны.

---

### 38. `p0842` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Today we could call the French approach a privatised tax collecting system. It is estimated that half the revenues that the French tax farmers generated never reached the government, simply because they kept it for themselves.⁸ In contrast, between 1650 and 1715, the new fiscal bureaucracy in England managed to multiply government revenues by a factor of 8, and a century later by a factor of thirty-six.⁹ The relevance and importance of a professional tax bureaucracy prevails even today: when this institution appears too weak, as was the case during the Greek sovereign-debt crisis of 2011, the financial markets will tend to require higher interest rates, which can make the burden of servicing national debt unbearable.

**В озвучку попало:**

> Сегодня французский подход того времени можно было бы назвать приватизированной системой сбора налогов. По оценкам, половина доходов, которые собирали французские откупщики, так и не доходила до казны, поскольку они просто оставляли эти деньги себе. В Англии же новая фискальная бюрократия в период с 1650 по 1715 год сумела увеличить государственные доходы в восемь раз, а столетие спустя — уже в тридцать шесть раз. Значимость профессиональной налоговой бюрократии сохраняется и сегодня. Когда этот институт оказывается слишком слабым, как это было во время греческого долгового кризиса 2011 года, финансовые рынки склонны требовать более высоких процентных ставок, что может сделать бремя обслуживания государственного долга непосильным.

---

### 39. `p0876` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> However, the best-known academics of the time favoured another proposal known as the ‘Chicago Plan’. Its promoters included most leading American economists of the 1930s: Henry Simons and Paul Douglas from Chicago University, Irving Fisher from Yale (who published a book about it 24), Frank Graham and Charles Whittlesley from Princeton and Earl Hamilton from Duke University.

**В озвучку попало:**

> Однако самые известные ученые того времени отдавали предпочтение другому предложению, которое называли «Чикагским планом». Среди его сторонников были ведущие американские экономисты 1930-х годов: Генри Саймонс и Пол Дуглас из Чикагского университета, Ирвинг Фишер из Йеля, Фрэнк Грэм и Чарльз Уиттлси из Принстона, а также Эрл Гамильтон из Университета Дьюка.

---

### 40. `p0881` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Reinstating some form of the Glass-Steagall Act, or implementing some version of the Chicago Plan, are once again being debated. Predictably, it is the former that meets with more approval from both bankers and regulators. In the UK, the equivalent of the Glass-Steagall Act was enacted in 2011.

**В озвучку попало:**

> Сегодня вновь ведутся споры о восстановлении закона Гласса — Стиголла или внедрении какой-либо версии Чикагского плана. Предсказуемо, что первый вариант встречает больше одобрения как у банкиров, так и у регуляторов. В Великобритании аналог закона Гласса — Стиголла был принят в 2011 году.

---

### 41. `p0944` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Dozens of designs exist for innovative exchange media that meet these two criteria, some already operational, many still at the design stage. In combination with the conventional money system, mixes of these could create a great variety of monetary ecosystems. In the next two chapters we discuss nine examples. Each of the examples describes a system that:

**В озвучку попало:**

> Существуют десятки проектов инновационных средств обмена, отвечающих этим двум критериям. Некоторые из них уже работают, многие все еще находятся на стадии разработки. В сочетании с традиционной денежной системой их комбинации могут создать огромное разнообразие денежных экосистем. В следующих двух главах мы обсудим девять примеров. Каждый из них описывает систему, которая:

---

### 42. `p0949` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Obviously, not *all* these systems need to be implemented for significant improvements to materialise. The German ‘Iron Chancellor ’ Bismarck is reported to have claimed that politics is the art of the possible. Each community, city or country can therefore decide how far it wants to go and how far it is possible, in practice, to stretch policies in new directions. We deliberately present a very broad range of pragmatic solutions simply to illustrate what is possible.

**В озвучку попало:**

> Очевидно, что для достижения значительных улучшений не обязательно внедрять *все* эти системы. Немецкий «железный канцлер» Бисмарк, как говорят, утверждал, что политика — это искусство возможного. Поэтому каждая община, город или страна может сама решать, как далеко она хочет зайти и насколько возможно на практике расширить границы политики в новых направлениях. Мы намеренно представляем очень широкий спектр прагматичных решений, просто чтобы проиллюстрировать, что возможно сделать.

---

### 43. `p0974` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> More than twice the size of Belgium, it has a population of only 3.2 million. During the 14th century, it was the largest country in Europe, stretching from the Baltic Sea to the Black Sea. Given its small current size and lack of stereotypical tourist attractions, Dalia Grybauskaite, the first woman to become Lithuanian president, would like foreigners to visit Lithuania in order to learn something.

**В озвучку попало:**

> Литва в два с лишним раза больше Бельгии, но ее население составляет всего три миллиона двести тысяч человек. В четырнадцатом веке это было крупнейшее государство Европы, простиравшееся от Балтийского до Черного моря. Учитывая нынешние скромные размеры страны и отсутствие привычных туристических достопримечательностей, Даля Грибаускайте, первая женщина на посту президента Литвы, хотела бы, чтобы иностранцы приезжали в Литву учиться чему-то новому.

---

### 44. `p0990` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> Even if the medical care market were a theoretically ‘perfect’ one – with fully informed actors, no moral hazard, less asymmetry, more efficiency, fair access and so on – the economic preference for ‘sick and alive’ clients would remain a problematic bias. The current system thus makes it tempting to treat an obese patient who develops diabetes by using medication, rather than by using an early detection/ prevention approach with exercise and weight-loss programmes, to mitigate or even avoid the disease. In addition, improved technology has allowed an increase in the life expectancy of chronically ill individuals, with a corresponding increase in the consumption of health care resources. Prevention is thus side-lined in the face of this additional disease burden. The ‘sick and alive’ bias then becomes an additional cause for a market failure that contributes to the ineffective systemic organisation of health care services.

**В озвучку попало:**

> [thoughtful] Даже если бы рынок медицинских услуг был теоретически идеальным — с полностью информированными участниками, отсутствием морального риска и справедливым доступом, — экономическое предпочтение «больных, но живых» клиентов оставалось бы проблемным искажением. Нынешняя система подталкивает к тому, чтобы лечить пациента с диабетом, развившимся на фоне ожирения, с помощью лекарств, вместо того чтобы использовать раннюю диагностику и программы по снижению веса для предотвращения болезни. Кроме того, современные технологии увеличивают продолжительность жизни хронически больных людей, что ведет к росту потребления медицинских ресурсов. В условиях такой нагрузки на систему профилактика отходит на второй план. Предвзятость «больной, но живой» становится дополнительной причиной провала рынка, препятствующей эффективной организации медицинских услуг.

---

### 45. `p1002` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> This approach would also be useful in setting up support groups. Creating pods of people who are tackling a weight problem can be a very effective way to get longer-term commitment. One could then create group objectives, which —when met — earn extra Wellness Tokens for the entire group.

**В озвучку попало:**

> Такой подход также полезен для создания групп поддержки. Объединение людей, решающих общую проблему, например, лишнего веса, помогает добиться долгосрочных результатов. Можно ставить групповые цели, выполнение которых приносит дополнительные велнес-токены всем участникам.

---

### 46. `p1005` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> People earning Wellness Tokens could use them in a number of ways, including paying part of their insurance premiums with them¹⁵ or purchasing goods and services related to prevention or health promotion from providers pre-qualified by the Wellness Alliance. After a formal audit, local and regional businesses providing goods and services supporting preventive health care would become certified if their services and goods met specific health promotion criteria. This could include partial payment in Wellness Tokens for preventive care, biological or organic food or restaurants, health promotion/disease prevention courses, and sports equipment such as bicycles, to name just a few examples. In this way, a family earning Wellness Tokens because their children are maintaining their BMI could go shopping within the local community to buy organic food or a bicycle from participating vendors.

**В озвучку попало:**

> [serious] Люди, зарабатывающие велнес-токены, могут использовать их по-разному. Например, ими можно оплатить часть страховых взносов или приобрести товары и услуги, направленные на профилактику и укрепление здоровья, у поставщиков, аккредитованных «Велнес-альянсом». После официальной проверки местные и региональные компании, поддерживающие профилактическую медицину, получают сертификат, если их товары и услуги соответствуют критериям оздоровления. Это может быть частичная оплата токенами профилактических осмотров, покупка натуральных продуктов, посещение курсов по укреплению здоровья или приобретение спортивного инвентаря, например велосипедов. Так, семья, получающая токены за поддержание здорового индекса массы тела у детей, может потратить их в местных магазинах на полезную еду или велосипед.

---

### 47. `p1025` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Investing in a natural resource as a secure long-term savings tool is not a new idea and has been done on an individual level for millennia. Even from an institutional standpoint, major insurance companies today own large forest plantations in Europe and the US for exactly that purpose. The novelty of this proposal is that such investments would be made available as an inflation-proof savings tool for everyone, including the poorer segments of the population.

**В озвучку попало:**

> [serious] Инвестирование в природные ресурсы как в надежный инструмент долгосрочных сбережений — идея не новая. На индивидуальном уровне люди пользуются этим уже тысячи лет. Даже с институциональной точки зрения крупные страховые компании сегодня владеют большими лесными плантациями в Европе и США именно с этой целью. Новизна нашего предложения в том, что такие инвестиции станут доступным инструментом сбережений, защищенным от инфляции, для всех, включая беднейшие слои населения.

---

### 48. `p1042` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> The value of an early redemption could be based on a value curve such as that shown in Figure 7.3, less a transaction fee. This fee would encourage share owners to use them primarily as a store of value continuing exchanges within the community rather than cashing shares in for conventional money. If this third option were made available, the Natural Savings Company would need to have access to sufficient cash (e.g. by securing a line of credit with a bank), to avoid a ‘run on the savings company’ – the equivalent to a ‘run on the bank’ in a conventional system.

**В озвучку попало:**

> Стоимость досрочного выкупа может рассчитываться на основе графика роста цен за вычетом комиссии за транзакцию. Эта комиссия будет стимулировать владельцев использовать акции прежде всего как средство сбережения и обмена внутри сообщества, а не обналичивать их. Если такая опция будет доступна, компании потребуется иметь доступ к достаточному объему наличных средств — например, через кредитную линию в банке. Это поможет избежать «набега на сберегательную кассу», подобного банковской панике в традиционной системе.

---

### 49. `p1066` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> What are the benefits for governments? The greatest one is additional revenue from transactions that would otherwise not occur. Because this additional income ultimately becomes available in conventional national currency, the clearing-network does not upset existing procurement policies.

**В озвучку попало:**

> [serious] Каковы преимущества для правительств? Самое главное — это дополнительные доходы от сделок, которые в противном случае не состоялись бы. Поскольку этот дополнительный доход в конечном итоге становится доступен в обычной национальной валюте, клиринговая сеть не нарушает существующую политику государственных закупок.

---

### 50. `p1122` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> In contrast, when the business cycle booms, both suppliers and corporations have an increased need for raw materials and demand for them goes up. The TRCs could be cashed in and used in the commodity markets. The amount of TRCs in circulation would decrease when the business cycle is at its maximum and counteract inflationary pressures. In summary, by providing monetary liquidity during phases when credit gets tight in the conventional system and contracting when business is booming, TRC-denominated exchanges would stabilise the overall business cycle.

**В озвучку попало:**

> Напротив, во время экономического подъема спрос на сырье растет как у поставщиков, так и у корпораций. В этот период TRC можно обналичивать и использовать на товарных рынках. Объем TRC в обращении будет сокращаться на пике деловой активности, что поможет сдерживать инфляционное давление. Подводя итог, можно сказать, что TRC обеспечивает денежную ликвидность, когда в обычной системе кредитование затруднено, и сокращает ее во время бума. Таким образом, расчеты в TRC будут стабилизировать общий деловой цикл.

---

### 51. `p1155` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> The City of Ghent wanted to encourage ecological and health-promoting activities, beautify the neighbourhood and improve the overall quality of life in Rabot. They started with a survey asking local residents what was most desirable to them. The answer was access to a small plot of land to grow vegetables and flowers. The city made land available, including an unused factory lot, on which over a hundred 4m² gardens were created. These little gardens have been made available for a yearly rent of 150 Torekes, payable only in Torekes.

**В озвучку попало:**

> Городские власти Гента стремились поощрять экологические и оздоровительные инициативы, а также улучшить внешний вид района и общее качество жизни в Работе. Они начали с опроса местных жителей, чтобы узнать, что для них наиболее важно. Выяснилось, что люди мечтают о небольших участках земли для выращивания овощей и цветов. Город предоставил землю, включая заброшенную заводскую территорию, где было создано более сотни садов площадью по четыре квадратных метра. Эти участки стали доступны для аренды за 150 «торекесов» в год — валюту, которую можно было заработать только участием в жизни района.

---

### 52. `p1159` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> In addition to being used to pay rent for the gardens, Torekes can also be used to buy from local shops specific goods which the city encourages, including low-energy light bulbs and seasonal vegetables. Torekes can also be used to buy tickets for public transport and for the cinema (where otherwise empty seats would have remained unused). Businesses can exchange the Torekes for euros at the community centre office. These simple arrangements with participating stores benefit the residents, the local economy and the environment.

**В озвучку попало:**

> [thoughtful] Помимо оплаты аренды садов, тореки можно использовать для покупки в местных магазинах определенных товаров, которые поощряет городская администрация. К ним относятся энергосберегающие лампочки и сезонные овощи. Также за тореки можно приобрести билеты на общественный транспорт или в кино — на те места, которые иначе остались бы пустыми. Предприниматели могут обменять полученные тореки на евро в офисе общественного центра. Эти простые договоренности с магазинами-участниками приносят пользу жителям, местной экономике и окружающей среде.

---

### 53. `p1170` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> - **7. ‘Biwa Kippu’: Funding a Regional Environmental Project** Lake Biwa in the Shiga Prefecture of Japan is one of the world’s oldest lakes and is graced with a very diverse and unusual ecosystem. However, the lake has become prone to a number of environmental problems: poor maintenance of water source forests; water contamination from industry, agriculture and households; algae blooms; as well as invasion of exotic fish species that have overwhelmed the native fish population. The Shiga prefectural government has used both environmental regulations and subsidies as policy instruments to address these issues. However, the question was raised: can additional policy instruments be used to obtain greater environmental results without increasing the budgetary burden on public authorities. The Biwa Kippu has been designed to be just such an instrument.

**В озвучку попало:**

> 7. «Бива Киппу»: финансирование регионального экологического проекта. Озеро Бива в японской префектуре Сига — одно из старейших в мире, оно обладает уникальной и разнообразной экосистемой. Однако озеро столкнулось с рядом экологических проблем. Среди них: плохой уход за лесами в водосборных бассейнах, загрязнение воды промышленными, сельскохозяйственными и бытовыми отходами, цветение водорослей, а также нашествие чужеродных видов рыб, которые вытесняют местную фауну. Правительство префектуры Сига использовало для решения этих задач экологические нормы и субсидии. Однако возник вопрос: можно ли найти дополнительные инструменты, чтобы добиться лучших экологических результатов, не увеличивая нагрузку на бюджет. Именно таким инструментом и стала система «Бива Киппу».

---

### 54. `p1235` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Notice that there is no obligation to personally perform any of the tasks rewarded in Civics. There are two ways to avoid participating at all. The first would be opting out by paying an extra amount in euros as part of one’s annual taxes. Based on our example, a logical amount would be the €1,000 per year estimated in the conventional process described at the beginning of our example. The second option for people not interested or without the time to personally perform the tasks, would be to purchase Civics via the online market openly and transparently. People having earned more Civics than they needed for their annual contribution could sell them on that market. The buyer of the Civics could make the purchase in conventional money or as an exchange for any good or service acceptable to the other party.

**В озвучку попало:**

> Заметьте, что никого не обязывают лично выполнять задачи, за которые полагается вознаграждение в «сивиках». Существует два способа вовсе не участвовать в этой системе. Первый — отказаться от участия, доплатив определенную сумму в евро в рамках ежегодных налогов. Исходя из нашего примера, логичной суммой была бы одна тысяча евро в год, как и предполагалось в традиционной схеме, описанной ранее. Второй вариант для тех, кто не заинтересован в выполнении задач или не имеет на это времени, — покупать «сивики» на открытом и прозрачном онлайн-рынке. Люди, заработавшие больше «сивиков», чем им требовалось для ежегодного взноса, могли бы продавать излишки на этой же площадке. Покупатель может расплатиться за «сивики» обычными деньгами или обменять их на любые товары и услуги, которые устроят продавца.

---

### 55. `p1252` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> When describing the Civic system, the words ‘money’, ‘currency’ or ‘legal tender ’ were never needed or used. The EU treaty refers to ‘euro banknotes’ and ‘legal tender ’. The Civic does not need the status of ‘legal tender ’ in order to function. It is more cost-effective for the Civic to exist only in electronic form with a mobile phone system as the platform rather than be issued as notes. We will use the word ‘contributions’ when referring to Civics. and reserve the label ‘taxes’ for levies that can only be paid in euros.

**В озвучку попало:**

> При описании системы «Сивиков» слова «деньги», «валюта» или «законное платежное средство» не требовались и не использовались. Договор Европейского союза касается именно банкнот евро и статуса законного платежного средства. «Сивику» не нужен такой статус для функционирования. Экономически выгоднее, чтобы «Сивик» существовал только в электронном виде на базе мобильной платформы, а не в форме банкнот. Мы будем использовать термин «взносы» при упоминании «Сивиков», а слово «налоги» оставим для обязательных платежей, которые можно внести только в евро.

---

### 56. `p1289` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> All nine innovative systems could also interact with the thousands of local and social currency experiments already under way around the world. The pioneers who started this movement should be recognised and honoured. They have started at grassroots level a massive education and learning process about monetary literacy that could become essential for informed decision-making in the 21st century.

**В озвучку попало:**

> Все девять инновационных систем могут взаимодействовать с тысячами экспериментов по внедрению местных и социальных валют, которые уже проводятся по всему миру. Первопроходцев, начавших это движение, следует признать и поблагодарить. На низовом уровне они запустили масштабный процесс обучения и повышения финансовой грамотности, который может стать ключевым для принятия взвешенных решений в двадцать первом веке.

---

### 57. `p1309` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> In a sense, *The Future of Money* focused on the need to re-think money in order to answer the questions formulated by *The Limits to Growth*. Essentially this was because the conventional principle of creating money through interest-bearing bank credit has a *systemic growth obligation* built into it – not even necessarily out of ideological choice (although this can also be present as an additional factor), but out of sheer mechanical necessity. Therefore, seeking to counteract all the deleterious effects of economic growth without questioning the omnipresent monetary tool that drives this growth, could not work. But getting to the solution requires us to find a way to see some way around the monetary blind spot that we identified in Chapter II.

**В озвучку попало:**

> В некотором смысле, «Будущее денег» было посвящено необходимости переосмыслить деньги, чтобы ответить на вопросы, поставленные в работе «Пределы роста». По сути, это было необходимо потому, что традиционный принцип создания денег через банковский кредит под проценты имеет встроенное «системное обязательство роста». Это происходит не обязательно из-за идеологического выбора, хотя и он может присутствовать как дополнительный фактор, а из-за простой механической необходимости. Поэтому попытки противодействовать всем пагубным последствиям экономического роста, не ставя под сомнение вездесущий денежный инструмент, который этот рост подпитывает, не могли увенчаться успехом. Но чтобы найти решение, нам нужно научиться видеть выход из «денежного слепого пятна», о котором мы говорили во второй главе.

---

### 58. `p1342` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Our sincere hope is that as the world of the old economy breaks down, the seeds of a new and more humane economy may be given a chance to emerge. “There is a rabbinical teaching that if the world is ending and the Messiah arrives, you first plant a tree; and then see if the story is true. Islam has a similar teaching that tells its adherents that if they have a palm cutting in their hand on Judgement Day, plant the cutting.”¹⁷

**В озвучку попало:**

> Мы искренне надеемся, что по мере того, как старая экономика разрушается, семена новой, более гуманной экономики получат шанс прорасти. Существует раввинистическое учение: если мир подходит к концу и приходит Мессия, сначала посади дерево, а потом посмотри, правдива ли эта история. В исламе есть похожее наставление: если в Судный день у тебя в руках саженец пальмы, посади его.

---

### 59. `p1359` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Gwendolyn Hallsmith contributed many substantial ideas for Chapters II and VII. Sherry Cox has contributed clarity to all chapters. Last but not least, Stephanie Taché managed to incorporate a feminine sensitivity to what would otherwise be a heavier Report. The illustrations were produced with help from Thibault d’Ursel. Finally, Andrew Carey and Alison Melvin from Triarchy Press helped publish this book in record time, without compromising on quality.

**В озвучку попало:**

> Гвендолин Холлсмит внесла множество важных идей для второй и седьмой глав. Шерри Кокс помогла сделать текст всех глав более ясным. И наконец, Стефани Таше сумела привнести женскую чуткость в то, что иначе могло бы стать слишком сухим докладом. Иллюстрации были созданы при участии Тибо д’Урселя. Наконец, Эндрю Кэри и Элисон Мелвин из издательства Triarchy Press помогли выпустить эту книгу в рекордные сроки, не жертвуя качеством.

---

### 60. `p1372` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The **Club of Rome**, an affiliation of individual members and over thirty associations all over the world, is unique. The network of Club members and their institutions is extensive. It draws on all sectors and disciplines, including senior individuals from the banking and financial sectors, scientists, academics, technologists, social scientists and philosophers. Many are world renowned, Nobel recipients and exceptional personalities. The members of the Club of Rome work on a wide variety of issues relevant to the future of humankind.

**В озвучку попало:**

> [thoughtful] Римский клуб — это уникальное объединение, в которое входят как отдельные участники, так и более тридцати организаций по всему миру. Сеть членов клуба и связанных с ними институтов весьма обширна. Она охватывает все сферы деятельности и дисциплины, включая ведущих экспертов банковского и финансового секторов, ученых, преподавателей, технологов, социологов и философов. Многие из них — люди с мировым именем, лауреаты Нобелевской премии и выдающиеся личности. Члены Римского клуба работают над широким спектром вопросов, имеющих решающее значение для будущего человечества.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0634` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> From our perspective, based on the Ecological Economics Paradigm illustrated in Figure 2.3 (page 31), the issue of keeping both inflation and deflation at bay is also relevant, but represents only one of several relevant issues with regards to sustainability.

**В озвучку попало:**

> С нашей точки зрения, основанной на парадигме экологической экономики, задача сдерживания инфляции и дефляции также важна, но она представляет собой лишь один из аспектов устойчивости.

---

### 2. `p0379` — длина озвучки / длина оригинала: 0.75; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> USA, where he was acknowledged as Distinguished Fellow of the American Economic Association. He made significant contributions in both conventional economics (utility theory, input-output analysis, production theory) and in paradigm-shifting economics – what along the lines of Thomas Kuhn might be labelled ‘revolutionary’ economics. He applied rigorous systemic thinking on how to link economics to the physical laws of sustainability in *Analytical Economics* (1966). Paul Samuelson said in the Preface that he considered Georgescu-Roegen to be “a scholar’s scholar, and an economist’s economist”. He added: “I defy any informed economist to remain complacent after meditating over this essay”. Nevertheless, complacency is what has greeted that book and its successor, *The Entropy Law and the Economic Process*. Ecological economist Herman Daly concludes in his ‘Obituary Essay on Georgescu-Roegen’: “One does not expect fundamental change to occur overnight. But twenty-five years is a reasonable time over which to hope for progress. What is the matter with our discipline?” (Daly [1996] p.192 and p.198). Even Samuelson himself, for all his professed lack of complacency, never updated his bestselling economics textbooks to integrate Georgescu-Roegen’s findings. Even 30 years before Georgescu-Roegen, Frederick Soddy, a Nobel laureate in Chemistry, had drawn the attention of economists to their ignorance of entropy and the unsustainability of compound interest, all without success. 14 Orio Giarini ‘Science and Economy: The Case of Uncertainty and Disequilibrium’ *Cadmus,* Vol I, No.2 (April 2011) pp.25-34. 15 Hazel Henderson: *Paradigms in Progress: Life beyond Economics* (1991). See also Hazel Henderson: *Creating Alternative*

**В озвучку попало:**

> [serious] Он внес значительный вклад как в традиционную экономику, так и в экономику, меняющую парадигму — то, что вслед за Томасом Куном можно назвать «революционной» экономикой. В своей работе «Аналитическая экономика» он применил системный подход к связям экономики с физическими законами устойчивого развития. Пол Самуэльсон в предисловии назвал его «ученым для ученых и экономистом для экономистов». Он добавил: «Я бросаю вызов любому компетентному экономисту, который сможет остаться спокойным после размышлений над этим эссе». Тем не менее, именно спокойствие стало реакцией на эту книгу и ее продолжение — «Закон энтропии и экономический процесс». Экологический экономист Герман Дейли в своем некрологе, посвященном Джорджеску-Регену, заключил: «Не стоит ожидать, что фундаментальные изменения произойдут в одночасье. Но двадцать пять лет — это разумный срок, чтобы надеяться на прогресс. Что же не так с нашей дисциплиной?». Даже сам Самуэльсон, несмотря на свое показное беспокойство, так и не обновил свои бестселлеры по экономике, чтобы включить в них выводы Джорджеску-Регена. Еще за тридцать лет до него Фредерик Содди, нобелевский лауреат по химии, пытался обратить внимание экономистов на их игнорирование энтропии и неустойчивость сложных процентов, но все его попытки оказались безуспешными.

---

### 3. `p1264` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> In other ways, the ECO system is conceptually similar to the Civic, as illustrated in Figure 8.4. It would start with a governmental authority such as a national government, requiring an annual contribution of ECOs proportional to the total sales volume of each individual corporation. For instance, all corporations would have to contribute 1 ECO for every $1 million of global sales to the government of the country where their headquarters were located.

**В озвучку попало:**

> В остальном система ЭКО концептуально схожа с «Сивиками». Она предполагает, что государственные органы будут требовать от корпораций ежегодные взносы в ЭКО, пропорциональные их общему объему продаж. Например, все компании могли бы выплачивать один ЭКО на каждый миллион долларов глобальной выручки правительству страны, где находится их штаб-квартира.

---

### 4. `p1268` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Such an approach will undoubtedly be unpopular in many business circles. But let’s see it in the context of what took place in President Roosevelt’s office on 27 December, 1941, when he signed his executive order 9001 stating: “The Office of Production Management will bring about the conversion of manufacturing industries to war production, including the surveying of the war potential of industries, plant by plant; the spreading of war orders; the conversion of facilities; the assurance of efficient and speedy production…”⁶ The only argument given was that the United States had been at war since 7 December, and until that war was over, things would run differently. This was the only justification available and the only one needed.

**В озвучку попало:**

> Такой подход, несомненно, будет непопулярен в деловых кругах. Но давайте вспомним 27 декабря 1941 года, когда президент Рузвельт подписал исполнительный указ номер 9001. В нем говорилось, что Управление по производству должно обеспечить перевод промышленности на военные рельсы, включая оценку потенциала каждого завода, распределение военных заказов и обеспечение эффективного производства. Единственным аргументом было то, что Соединенные Штаты находятся в состоянии войны, и до её окончания правила игры меняются. Это было единственное и вполне достаточное оправдание.

---

### 5. `p0993` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Wellness Tokens are specifically designed to use a preventive approach to promote and maintain the good health of participants. Just as ‘Frequent Flyer Miles’ are issued by airline alliances to induce a habit of taking the same airline for all one’s trips, Wellness Tokens would be issued by a Wellness Alliance to induce healthy habits. The members of the Wellness Alliance would be those organisations that have a financial interest in keeping the population healthy (e.g. insurance companies, local government and local employers). One of the purposes of the Wellness Token would be to generate changes in habits towards health promotion and disease prevention by encouraging healthy behaviours and emphasising preventive health care. Such an approach would also be a means of financing supportive care so that the elderly, the chronically ill and the disabled can remain in their own homes, and delay for as long as possible their entry into a long-term medical facility, where the costs escalate.

**В озвучку попало:**

> [serious] Велнес-токены специально разработаны для внедрения профилактического подхода к здоровью. Подобно тому как авиакомпании выпускают бонусные мили, чтобы приучить пассажиров летать только с ними, велнес-токены будут выпускаться «Велнес-альянсом» для формирования здоровых привычек. В этот альянс войдут организации, финансово заинтересованные в здоровье населения: страховые компании, местные органы власти и работодатели. Одна из целей токенов — стимулировать изменения в образе жизни, поощряя здоровое поведение и профилактику. Такой подход также позволит финансировать поддерживающий уход, чтобы пожилые люди, хронические больные и инвалиды могли дольше оставаться дома, откладывая момент попадания в медицинские учреждения, где стоимость лечения резко возрастает.

---

### 6. `p1011` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> The Wellness Token is a win-win approach. Going back to our example, the children become healthier and less prone to illness; the family has additional resources to spend on health-related and health-promoting goods and services; the insurance alliance incurs fewer health care costs as a result of healthier clients; and healthcare providers increase their turnover. On a macroeconomic level, society benefits through lower rates of sick leave, increased productivity, less unemployment and greater social capital.

**В озвучку попало:**

> Велнес-токен — это подход, где выигрывают все. Вернемся к нашему примеру: дети становятся здоровее, у семьи появляются дополнительные ресурсы на товары для здоровья, страховой альянс несет меньше расходов, а поставщики услуг увеличивают оборот. На макроуровне общество выигрывает за счет снижения числа больничных, роста производительности, сокращения безработицы и укрепления социального капитала.

---

### 7. `p0228` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> In practice, the new system we describe provides ordinary people with more freedom to live a life that honours more of their humanity*, it gives them choice from a wider spectrum of activities to meet* *their needs, and increases their chances of expressing their gifts and developing their creative* *passions*. For members of today’s wealthy elite, the proposed approach makes it possible *to remain* *financially wealthy, and to do so without this being at the expense of the rest of humanity*.

**В озвучку попало:**

> На практике новая система даст обычным людям больше свободы жить в согласии с человеческими ценностями. Она расширит выбор видов деятельности для удовлетворения потребностей и увеличит шансы на реализацию талантов и творческих стремлений. Для представителей сегодняшней элиты предлагаемый подход позволит оставаться финансово обеспеченными, не делая это за счет остального человечества.

---

### 8. `p0663` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> However, there are unfortunately also several mechanisms that turn out to be incompatible with sustainability. Specifically, we identify five effects that are detrimental to sustainability, and we can trace them back to characteristics of bank-debt money itself.

**В озвучку попало:**

> Однако, к сожалению, существуют механизмы, которые несовместимы с принципами устойчивого развития. Мы выделили пять негативных эффектов, которые можно проследить в самой природе банковских кредитных денег.

---

### 9. `p0095` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The World Business Academy has long been committed to advancing cutting-edge business information among business executives charged with navigating their businesses through the challenging times we live in. The Academy thank s Bernard Lietaer and his associates for presenting this Report to us, and encourages all levels of government and private enterprises to use the Report to begin a serious conversation on the critical issues the Report illuminates – while there is still time.

**В озвучку попало:**

> Всемирная бизнес-академия давно стремится предоставлять передовую информацию руководителям, которым приходится вести свои компании через сложные времена. Академия благодарит Бернара Литера и его коллег за этот отчет и призывает государственные структуры и частный сектор использовать его как основу для серьезного диалога по критически важным вопросам, пока у нас еще есть время.

---

### 10. `p1001` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a *personal-responsibility-building* dimension to the Wellness Tokens, in the direction of what has been called ‘genuine autonomy’ of the patient in recent literature inspired by Ivan Illich.¹⁴ The system offers positive rather than negative incentives to motivate and reward people for their behaviours rather than punish them for ‘misbehaviours’. The perception should be that the system increases the opportunities available to people rather than imposing restrictions on them.

**В озвучку попало:**

> [thoughtful] Важно подчеркнуть: система велнес-токенов направлена на улучшение здоровья, а не на создание «неовикторианских» механизмов наказания. Мы не стремимся лишать финансовой поддержки тех, кто заболел из-за своего образа жизни — например, курильщиков с раком легких или людей с сердечными заболеваниями, вызванными неправильным питанием. Наша цель — просвещение, повышение осознанности и развитие личной автономии. Именно поэтому система делает упор на профилактику, а не на лечение. Мы не хотим использовать финансовые стимулы, чтобы запугивать людей, как это делают карательные системы, начинающие действовать только после того, как болезнь уже наступила. Велнес-токены призваны развивать личную ответственность, способствуя тому, что в литературе вслед за Иваном Илличем называют «подлинной автономией» пациента. Система предлагает позитивные, а не негативные стимулы: она мотивирует и вознаграждает за правильные действия, а не наказывает за ошибки. Люди должны воспринимать эту систему как расширение своих возможностей, а не как навязывание ограничений.

---

### 11. `p0208` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> For the population at large, perhaps the most important learning needed is to understand non-linearity, specifically the difference between linear and exponential growth. We are now dealing with an increasingly non-linear world. Grasping these different dynamics will be useful in understanding what is happening to us, and what to do about it.

**В озвучку попало:**

> Для широкой общественности, пожалуй, важнее всего понять суть нелинейности, а именно — разницу между линейным и экспоненциальным ростом. Мы живем во все более нелинейном мире. Понимание этих динамических процессов поможет осознать, что с нами происходит и как на это реагировать.

---

### 12. `p1267` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Wide consensus exists in both the scientific and the business world that the development of technologies to switch to a post-carbon world is possible but will require strong governmental leadership. Because many governments will experience a budget squeeze over the next decade, and because government subsidies are the usual way to fund environment conservation and protection measures, many corporations will be left passively waiting for funding to become available before deciding to tackle these issues on their own. The ECO changes this dynamic. In order to wage a war against climate change, governments could require contributions payable only in ECOs, thus giving value to the ECO. As discussed in Chapter V, any fiat currency (including bank-debt money) becomes valuable when a government requires it in payment of fees and taxes. The ECO would also spur serious innovations to reduce climate change.

**В озвучку попало:**

> [thoughtful] В научных и деловых кругах существует широкий консенсус: переход к пост-углеродному миру возможен, но требует решительного государственного лидерства. Многие правительства в ближайшее десятилетие столкнутся с бюджетными ограничениями. Поскольку субсидии — привычный способ финансирования охраны окружающей среды, многие корпорации будут пассивно ждать господдержки, прежде чем самостоятельно решать экологические проблемы. ЭКО меняют эту динамику. Требуя уплаты взносов исключительно в ЭКО, правительства придают этой валюте реальную ценность. Как обсуждалось в пятой главе, любая фиатная валюта становится ценной, когда государство требует её для уплаты сборов и налогов. ЭКО также станут мощным стимулом для серьезных инноваций.

---

### 13. `p0431` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Even countries theoretically immune to the financial side of a crisis end up being hit through unemployment and increases in poverty. For instance, the World Bank estimates that the impact of the 2008 crisis in Poland will result in a 3% increase in the number of people in poverty; in the Philippines and Bangladesh, an additional 5% of the population will be in poverty, and in Mexico an additional 8%.²² **Output losses** The economic impact of a crisis is broadly measured by the GDP ‘output loss’, the difference between the actual GDP of a country and the output that had been expected based on the long-term trend before the crisis. It provides an indirect estimate of how non-financial businesses within the country are affected, and the extent to which external trade for other businesses with that country suffers. Here are two recent analyses:

**В озвучку попало:**

> Даже страны, теоретически защищенные от финансовой стороны кризиса, в конечном итоге страдают от безработицы и роста бедности. Например, по оценкам Всемирного банка, последствия кризиса 2008 года в Польше приведут к увеличению числа бедных на 3%. На Филиппинах и в Бангладеш этот показатель вырастет на 5%, а в Мексике — на 8%. Потери объема производства. Экономическое влияние кризиса принято измерять через потери ВВП — разницу между фактическим внутренним валовым продуктом страны и тем уровнем, который ожидался исходя из долгосрочного тренда до начала кризиса. Это дает косвенную оценку того, как пострадал нефинансовый сектор и насколько сократилась внешняя торговля. Вот два недавних анализа:

---

### 14. `p0572` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Of perhaps even greater importance, the physics of flow networks also explains why excessively large and efficient organisations may pull the whole system toward collapse. In essence, large, highly efficient organisations in the network ‘out compete’ the smaller organisations for resources, drawing ever more energy, information and resources into the big, and away from the smaller participants.

**В озвучку попало:**

> Возможно, еще важнее то, что физика сетей потоков объясняет, почему чрезмерно крупные и эффективные организации могут привести всю систему к краху. По сути, такие организации в сети «выигрывают конкуренцию» у более мелких участников за ресурсы. Они стягивают на себя все больше энергии, информации и ресурсов, лишая их остальных.

---

### 15. `p0766` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Sociologist Robert Putnam defines social capital as “Features of social organisation, such as trust, norms and networks, that can improve the efficiency of society by facilitating coordinated actions”.³⁴ The content of this concept has not evolved for almost a century, as illustrated by the 1916 definition by Lyda Judson Hanifan: “The whole community will profit from the co-operation of its parts, and the individual, as a result of the links forged, will experience benefits such as help, compassion and community spirit from its neighbours…When people in a community trust each other, and when it has become customary to come together for entertainment purposes, to exchange views or for personal pleasure, skilful leaders can easily employ this social capital for the general improvement of welfare in the community as a whole.”³⁵ Hazel Henderson uses a very short but effective label for it all, referring to the “love economy”.³⁶

**В озвучку попало:**

> [thoughtful] Социолог Роберт Патнэм определяет социальный капитал как «элементы социальной организации, такие как доверие, нормы и сети, которые повышают эффективность общества, способствуя скоординированным действиям». Содержание этого понятия практически не изменилось за столетие. Еще в 1916 году Лида Джадсон Ханифан писала: «Все общество выигрывает от сотрудничества своих частей. Благодаря созданным связям индивид получает помощь, сострадание и поддержку соседей. Когда люди в сообществе доверяют друг другу, когда у них принято собираться вместе для отдыха, обмена мнениями или просто ради общения, умелые лидеры могут легко использовать этот социальный капитал для общего блага». Хейзел Хендерсон дает этому явлению очень короткое и точное название — «экономика любви».

---

### 16. `p0584` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> For instance, electrical power grids have been optimised for decades for greater technical and economic efficiency. It may come as a surprise to many engineers that it is precisely because these power grids have approached maximum efficiency that large-scale electrical blackouts are occurring in the technologically most advanced countries (e.g. Germany or the USA). Over-efficient streamlining has caused them to lose their resilience.

**В озвучку попало:**

> Например, электросети десятилетиями оптимизировались ради технической и экономической эффективности. Многих инженеров может удивить тот факт, что именно из-за стремления к максимальной эффективности в самых технологически развитых странах, таких как Германия или США, происходят масштабные отключения электроэнергии. Чрезмерная оптимизация лишила их устойчивости.

---

### 17. `p0982` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> This Dora learning-economy is intended to operate in parallel with the conventional monetary system. We are, therefore, witnessing the beginnings of an exchange media ecosystem. At the end of the first planning session, one of the participants asked the 17-year-old whether he would be willing to teach English and get paid in *Lita* (the Lithuanian national currency), in dollars or in euros. His answer was, “No, I’d prefer to get paid in Dora, because that would get me closer to my dream. These other currencies only would get me the airline ticket!” For this teenager, the Dora had already become a ‘superior currency’, a currency that he preferred over all others. Doraland is an example of a complementary system that encourages non-spontaneous but desirable behaviour patterns. Figure 7.1 summarises the Doraland model in a flow diagram.

**В озвучку попало:**

> [serious] Эта экономика обучения на базе дор призвана работать параллельно с традиционной денежной системой. Фактически, мы наблюдаем зарождение экосистемы обменных средств. В конце первой сессии планирования один из участников спросил того самого семнадцатилетнего юношу, готов ли он преподавать английский за литы, доллары или евро. Он ответил: «Нет, я бы предпочел получить оплату в дорах, потому что это приблизит меня к моей мечте. Другие валюты дадут мне только билет на самолет». Для этого подростка дора уже стала «превосходящей валютой» — той, которую он ценит выше всех остальных. «Doraland» — это пример дополнительной системы, которая поощряет не спонтанные, а желательные модели поведения.

---

### 18. `p0791` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> In comparison to the neutrally primed participant group, participants in the money-primed group demonstrated significantly higher rates of playing alone, working alone, and put more physical distance between themselves and their neighbours. The money-primed group also hesitated to ask others for help, and tended to respond to requests for help as if they were insensitive to others. They also preferred the pursuit of individualistic goals and individual freedom to that of collaboration. The results of this and other similar studies strongly support our hypothesis that money is non-neutral with regards to human interactions and behavioural patterns. Indeed, it increases social isolation and thereby a decline in human social capital.

**В озвучку попало:**

> По сравнению с контрольной группой, участники, видевшие символы денег, значительно чаще предпочитали играть и работать в одиночку. Они старались держаться на большем физическом расстоянии от окружающих. Люди из «денежной» группы реже просили о помощи и сами реагировали на чужие просьбы с меньшим участием. Они также чаще выбирали индивидуальные цели и личную свободу, а не сотрудничество. Результаты этого и подобных исследований подтверждают гипотезу: деньги далеко не нейтральны по отношению к человеческому поведению. Они усиливают социальную изоляцию и способствуют снижению человеческого социального капитала.

---

### 19. `p0909` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> They also seem to have difficulty grasping the notion that in a floating-exchange world, when a country such as the USA pumps trillions of additional dollars into its economy, the inflation that is being created may manifest on the other side of the world. For instance, these additional dollars could end up being spent by wealthy Russians on real estate on the French Riviera, regardless of what the French or European Central Bank may want to do about it.

**В озвучку попало:**

> Похоже, им также трудно осознать, что в мире с плавающими курсами валют инфляция, вызванная, например, вливанием триллионов долларов в экономику США, может проявиться на другом конце света. Скажем, эти дополнительные доллары могут быть потрачены богатыми россиянами на недвижимость на Лазурном берегу, и французский или Европейский центральный банк никак не смогут на это повлиять.

---

### 20. `p0589` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> In short, poorly connected networks are fragile, brittle and may collapse when they meet an unexpected challenge; while overly connected networks tend to become stagnant. The key to a successful sustainability strategy is therefore *the appropriate balance*, in all complex flow systems, be they corporations, ecosystems, or economies.

**В озвучку попало:**

> Коротко говоря, слабо связанные сети хрупки и могут рухнуть при неожиданном вызове, тогда как избыточно связанные сети склонны к застою. Ключ к успешной стратегии устойчивости — это надлежащий баланс во всех сложных системах потоков, будь то корпорации, экосистемы или экономики.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0161` — длина озвучки / длина оригинала: 1.31; классы правки: —

**Исходный абзац:**

> The bailouts, followed by a large-scale Keynesian stimulus plan to avoid a deflationary depression, have resulted in enormous budget deficits and additional public debt. In the twenty-three countries most directly affected by the banking crash, government debt jumped by an average of 24% of GDP.

**В озвучку попало:**

> [thoughtful] Выплаты по спасению банков, за которыми последовал масштабный кейнсианский план стимулирования для предотвращения дефляционной депрессии, привели к огромным бюджетным дефицитам и росту государственного долга. В двадцати трех странах, наиболее пострадавших от банковского краха, государственный долг вырос в среднем на двадцать четыре процента от валового внутреннего продукта.

---

### 2. `p0745` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> We have found only one study of the transfer of wealth via interest. It was performed in Germany in 1982 when interest rates were at 5.5%.²⁸ The German population was grouped into ten income categories of 2.5 million households each. Over a one-year period, transfers between these ten groups totalled Deutsche Mark (DM) 270 billion in interest paid and received. Graphing the net interest transfers (interest gained minus interest paid) for each of these ten household categories allows us to see the net effect (see Figure 5.5).

**В озвучку попало:**

> [thoughtful] Нам удалось найти лишь одно исследование, посвященное перераспределению богатства через процентные платежи. Оно было проведено в Германии в 1982 году, когда процентные ставки составляли пять с половиной процентов. Население страны разделили на десять доходных групп по два с половиной миллиона домохозяйств в каждой. За один год общая сумма перечислений между этими группами в виде выплаченных и полученных процентов составила двести семьдесят миллиардов немецких марок. Если построить график чистого перераспределения процентов — то есть разницы между полученными и выплаченными суммами — для каждой из этих десяти категорий, можно наглядно увидеть итоговый эффект.

---

### 3. `p0605` — длина озвучки / длина оригинала: 1.24; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Should we not learn from nature that growing to the point of becoming ‘too big to fail’ should never be allowed to happen? Instead, in the USA, the ten largest banks now control 42% of the market, compared to 28% before the 2008 crisis. This pattern is the perfect demonstration of what are known as ‘autocatalytic forces’ in natural ecosystems – forces that automatically lead to systemic crashes.

**В озвучку попало:**

> [thoughtful] Не пора ли нам поучиться у природы и понять, что нельзя допускать появления компаний, которые становятся «слишком большими, чтобы рухнуть»? В Соединенных Штатах десять крупнейших банков сегодня контролируют сорок два процента рынка, хотя до кризиса две тысячи восьмого года этот показатель составлял двадцать восемь процентов. Эта тенденция — наглядная демонстрация так называемых автокаталитических сил в природных экосистемах. Это силы, которые неизбежно ведут к системным крахам.

---

### 4. `p0057` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> At the time of writing these remark s we witness the dismantling of the state as guarantor of public good. Almost everything is for sale in most EU countries. Austerity is imposed at all levels. Public unrest will continue to grow unless new governance structures replace the obsolete ones.

**В озвучку попало:**

> [serious] В то время, когда мы пишем эти строки, мы наблюдаем, как государство перестает быть гарантом общественного блага. Почти всё в большинстве стран Европейского союза выставлено на продажу. Повсеместно вводится режим жесткой экономии. Общественное недовольство будет расти до тех пор, пока устаревшие структуры управления не будут заменены новыми.

---

### 5. `p0060` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> The CoR-EU is indebted to the World Academy of Art and Science, represented by Ivo Šlaus, President, and Garry J acobs, Chair of the Board and CEO, as well as to Felix U nger, President of the European Academy of Sciences and Arts for supporting this Report by co-signing these brief preliminary remark s.

**В озвучку попало:**

> Европейское отделение Римского клуба выражает признательность Всемирной академии искусств и науки в лице ее президента Иво Шлауса и председателя совета директоров и генерального директора Гарри Джейкобса. Мы также благодарим Феликса Унгера, президента Европейской академии наук и искусств, за поддержку этого доклада и соавторство в этих кратких вступительных замечаниях.

---

### 6. `p0574` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> In conclusion: “Life tends to optimise, rather than maximise. Maximisation is another word for addiction.”³⁰ Indeed, in the real world, all networks corresponding to natural ecosystems operate around the optimal point, within a specific range called the ‘window of viability’, 31 which lies on either side of this optimum, as can be seen in Figure 4.5.

**В озвучку попало:**

> В заключение можно сказать: «Жизнь стремится к оптимизации, а не к максимизации. Максимизация — это другое слово для обозначения зависимости». Действительно, в реальном мире все сети, соответствующие природным экосистемам, работают вокруг оптимальной точки. Они находятся в пределах особого диапазона, называемого «окном жизнеспособности», которое лежит по обе стороны от этого оптимума, как показано на рисунке четыре-пять.

---

### 7. `p0919` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> While these scholars don’t all necessarily agree on many topics, they all concur that *the systemic role of taxes is to give value to a currency, which, in the case of a fi at currency, would otherwise have no intrinsic value whatsoever*. If these ideas appear new or strange, it is because they have been systematically ignored in practice, rather than because they have been proven invalid or wrong.

**В озвучку попало:**

> [thoughtful] Хотя эти ученые не всегда согласны друг с другом по многим вопросам, они единодушны в одном: системная роль налогов заключается в том, чтобы придавать ценность валюте. В случае с фиатными деньгами, которые иначе не имели бы никакой внутренней стоимости, это единственный источник их ценности. Если эти идеи кажутся новыми или странными, то лишь потому, что их систематически игнорировали на практике, а вовсе не потому, что они были опровергнуты или признаны ошибочными.

---

### 8. `p0715` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> Yet we are being told that we still owe about $28 billion. That $28 billion came about because of the foreign creditors’ interest rates. If you ask me what is the worst thing in the world, I would say it is compound interest.” At the time Obasanjo spoke out, the developing world was spending $13 on debt repayment for every one dollar it had received in foreign aid and grants. For the sixty poorest countries in the world, $550 billion have been paid in both principal and interest over the last three decades on a total of $540 billion of loans, and yet there are still $523 billion outstanding in debt burden.

**В озвучку попало:**

> «И все же нам говорят, что мы все еще должны около двадцати восьми миллиардов. Эта сумма возникла из-за процентных ставок иностранных кредиторов. Если вы спросите меня, что на свете самое страшное, я отвечу — это сложные проценты». В то время, когда Обасанджо сделал это заявление, развивающиеся страны тратили тринадцать долларов на погашение долгов на каждый один доллар, полученный в виде иностранной помощи и грантов. За последние три десятилетия шестьдесят беднейших стран мира выплатили в счет основного долга и процентов пятьсот пятьдесят миллиардов долларов при общей сумме полученных кредитов в пятьсот сорок миллиардов. И несмотря на это, их непогашенная задолженность все еще составляет пятьсот двадцать три миллиарда долларов.

---

### 9. `p0184` — длина озвучки / длина оригинала: 1.20; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> It is often assumed that the relationship between the banking system and governments has remained unchanged for centuries. A case study of France shows that this is not necessarily the case. Indeed, since 1973, the French government has been forced to borrow exclusively from the private sector and therefore pay interest on new debt. Without this change, French government debt would now be at 8.6% of GDP instead of the current 78%. Furthermore, the Maastricht and Lisbon Treaties have generalised this same process to all signatory countries.

**В озвучку попало:**

> Часто предполагают, что отношения между банковской системой и правительствами оставались неизменными на протяжении веков. Однако пример Франции показывает, что это не всегда так. С тысяча девятьсот семьдесят третьего года французское правительство было вынуждено занимать средства исключительно в частном секторе и, следовательно, выплачивать проценты по новому долгу. Без этого изменения государственный долг Франции сейчас составлял бы восемь целых и шесть десятых процента от валового внутреннего продукта, а не текущие семьдесят восемь процентов. Кроме того, Маастрихтский и Лиссабонский договоры распространили этот процесс на все страны-участницы.

---

### 10. `p0453` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> The timing of this sudden increase in government debt is particularly unfortunate. The current decade is one in which the OECD countries and their governments have to deal with unprecedented pressures not amenable to being postponed. As mentioned in Chapter I, two critical and predictable challenges during the next decade will be the transition to a post-carbon economy and the sharp increase in financial requirements for retiring baby boomers.

**В озвучку попало:**

> [thoughtful] Время для такого резкого роста государственного долга выбрано крайне неудачно. В нынешнем десятилетии правительства стран Организации экономического сотрудничества и развития столкнулись с беспрецедентным давлением, которое невозможно отложить на потом. Как уже упоминалось в первой главе, в ближайшие десять лет перед нами встанут две критически важные и предсказуемые задачи: переход к экономике, свободной от углеродного топлива, и резкое увеличение расходов на обеспечение вышедшего на пенсию поколения «бэби-бумеров».

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1285` — совпадение символов с оригиналом: 25%; классы правки: —

**Исходный абзац:**

> Systems like Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu, and Civics provide environments for people who otherwise would never meet to work together on projects that develop their gifts and the health and strength of their community. If people are given a powerful voice on which projects are chosen, these systems can rebuild and strengthen social capital over time.

**В озвучку попало:**

> Системы вроде Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu и Civics создают среду, в которой люди, иначе никогда бы не встретившиеся, могут работать вместе. Они объединяются для проектов, которые развивают их таланты, а также укрепляют здоровье и силу местного сообщества. Если дать людям возможность влиять на выбор таких проектов, эти системы способны со временем восстановить и значительно укрепить социальный капитал.

---

### 2. `p0929` — совпадение символов с оригиналом: 19%; классы правки: truncated_sentence

**Исходный абзац:**

> Footnotes 1 John Kenneth Galbraith, *Money: Whence It Came, Where It Went* (1975), p.5. 2 For instance, the Natural Savings instrument presented in Chapter VII would mainly be a savings tool, not a medium of exchange or unit of account. In many civilisations, the unit of account was also different from the medium of exchange. A case in point is Homeric Greece, where the unit of account was the ox but where, for the sake of convenience, actual exchanges were often performed with ingots of bronze or other commodities. 3 For the arguments offered in this paragraph, see Philippe Derudder and André-Jacques Holbecq (2008) p.17. 4 Friedrich Nietzsche, *Thus Spoke Zarathustra,* translated by Adrian del Caro and edited by Robert Pippin (2006). 5 The original is elegantly succinct: *“Nervos belli, pecuniam infinitam”* from Cicero’s *Fifth* *Philippic.* See Jon Hall, *The Philippics*, in

**В озвучку попало:**

> Примечания. 1. Джон Кеннет Гэлбрейт, «Деньги: откуда они берутся и куда уходят» (1975), стр. 5. 2. Например, инструмент «Природных сбережений», представленный в седьмой главе, был бы преимущественно инструментом накопления, а не средством обмена или расчётной единицей. Во многих цивилизациях расчётная единица отличалась от средства обмена. Показательный пример — гомеровская Греция, где расчётной единицей был бык, но для удобства сделки часто совершались с использованием бронзовых слитков или других товаров. 3. Аргументы, приведённые в этом абзаце, см. в работе Филиппа Деруддера и Андре-Жака Ольбека (2008), стр. 17. 4. Фридрих Ницше, «Так говорил Заратустра», перевод Адриана дель Каро, под редакцией Роберта Пиппина (2006). 5. Оригинал звучит лаконично: «Nervos belli, pecuniam infinitam» из Пятой филиппики Цицерона. См. Джон Холл, «Филиппики», в

---

### 3. `p1359` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Gwendolyn Hallsmith contributed many substantial ideas for Chapters II and VII. Sherry Cox has contributed clarity to all chapters. Last but not least, Stephanie Taché managed to incorporate a feminine sensitivity to what would otherwise be a heavier Report. The illustrations were produced with help from Thibault d’Ursel. Finally, Andrew Carey and Alison Melvin from Triarchy Press helped publish this book in record time, without compromising on quality.

**В озвучку попало:**

> Гвендолин Холлсмит внесла множество важных идей для второй и седьмой глав. Шерри Кокс помогла сделать текст всех глав более ясным. И наконец, Стефани Таше сумела привнести женскую чуткость в то, что иначе могло бы стать слишком сухим докладом. Иллюстрации были созданы при участии Тибо д’Урселя. Наконец, Эндрю Кэри и Элисон Мелвин из издательства Triarchy Press помогли выпустить эту книгу в рекордные сроки, не жертвуя качеством.

---

### 4. `p1288` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> Five years after the start of the crisis, there is much that local communities can do to dampen its effects and to address austerity measures. The Doraland Foundation, city-generated Torekes and Civics systems all demonstrate ways to mobilise local human resources and make a significant difference without burdening city finances. In the event of a euro or dollar crisis, the role of the TRC in preserving a global web of vital trade would become obvious. It could, for instance, rescue us from the biggest and broadest global trade disruption in human history if a dollar crisis were to occur.

**В озвучку попало:**

> Спустя пять лет после начала кризиса местные сообщества всё еще могут многое сделать, чтобы смягчить его последствия и противостоять мерам жесткой экономии. Фонд Doraland, городские системы Torekes и Civics показывают, как мобилизовать человеческие ресурсы и добиться значительных результатов, не обременяя городские бюджеты. В случае кризиса евро или доллара роль системы TRC в сохранении глобальной сети жизненно важной торговли стала бы очевидной. Она могла бы, например, спасти нас от крупнейшего и самого масштабного сбоя в мировой торговле за всю историю человечества, если бы разразился долларовый кризис.

---

### 5. `p0438` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> This, in turn, sets the scene for further rounds of banking problems. Because all IMF data are based on government statistics provided by the countries involved, the comprehensiveness of this data is debatable. One exception is the case study of the 2007-2008 US banking crash.

**В озвучку попало:**

> Это, в свою очередь, создает условия для новых витков банковских проблем. Поскольку все данные МВФ основаны на официальной статистике стран, полнота этих данных вызывает вопросы. Исключением является исследование банковского краха в США 2007–2008 годов.

---

### 6. `p0394` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> The global monetary system seems to run on automatic pilot. What’s more, the current global foreign exchange market dwarfs all other markets in history. By 2010, foreign exchange volumes had routinely reached the equivalent of $4 trillion *every working day.*¹

**В озвучку попало:**

> [serious] Мировая денежная система, кажется, работает на автопилоте. Более того, нынешний глобальный валютный рынок затмевает все остальные рынки в истории. К 2010 году объем валютных операций регулярно достигал эквивалента четырех триллионов долларов каждый рабочий день.

---

### 7. `p0441` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> This programme was managed by the US Treasury Department. As banks reimbursed these funds over time, the total amount gradually dropped so that by December 2010, the estimated total cost was assessed at “only $25 billion”.²⁵ Public attention has been primarily focused on this programme.

**В озвучку попало:**

> Этой программой управляло Министерство финансов США. По мере того как банки возвращали средства, общая сумма постепенно снижалась, и к декабрю 2010 года оценочная стоимость программы составляла «всего 25 миллиардов долларов». Общественное внимание было сосредоточено именно на этой программе.

---

### 8. `p0703` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Let us assume water lilies double the surface they cover in a pond every day. Initially, their growth may seem quite reasonable. If a quarter of the pond is covered in 50 days, how many days will it tak e for the lilies to cover the entire pond? If the growth were linear, it would tak e another 150 days. If the growth were exponential, it would tak e one day to cover a second quarter of the pond and by day 52 it would be completely covered!

**В озвучку попало:**

> [thoughtful] Представьте, что площадь, которую занимают кувшинки в пруду, удваивается каждый день. Поначалу их рост кажется вполне умеренным. Если через 50 дней кувшинки покрывают четверть пруда, то сколько времени им понадобится, чтобы заполнить его целиком? При линейном росте на это ушло бы еще 150 дней. Но при экспоненциальном росте им потребуется всего один день, чтобы покрыть вторую четверть, и уже на пятьдесят второй день пруд будет полностью заросшим.

---

### 9. `p1287` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Another way to understand what an economic ecosystem would look like is to imagine what would currently be different if some of the solutions we are proposing had been well established before the 2007-2008 crisis. The C3 system would have reduced the level of unemployment resulting from the crisis. Civics would have empowered municipal governments to address their social and environmental challenges even with shrinking bank-debt money budgets. Together they would have provided an effective choice of tools to generate healthy local and regional economies.

**В озвучку попало:**

> Чтобы понять, как может выглядеть экономическая экосистема будущего, представьте, что изменилось бы, если бы некоторые из наших предложений были внедрены еще до кризиса 2007–2008 годов. Система C3 помогла бы снизить уровень безработицы, вызванный тем кризисом. Civics позволил бы муниципальным властям решать социальные и экологические задачи, даже при сокращении бюджетных средств, основанных на банковских кредитах. Вместе эти инструменты обеспечили бы эффективный способ создания здоровой местной и региональной экономики.

---

### 10. `p1310` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> An economy based on several currency systems running in parallel would actually not be new. In reality, it would be the recovery of an ancient idea. In Dynastic Egypt and the Central Middle Ages in Western Europe – to name two examples – such an idea was considered totally obvious. As Jean Houston put it elegantly: “The icons of old are the codings of tomorrow. And tomorrow holds the promise of recovery of forgotten wisdom.”⁴

**В озвучку попало:**

> Экономика, основанная на нескольких параллельно существующих валютных системах, на самом деле не была бы чем-то новым. По сути, это было бы возрождением древней идеи. В Древнем Египте или в средневековой Европе — если привести два примера — такая идея считалась совершенно очевидной. Как изящно выразилась Джин Хьюстон: «Иконы прошлого — это коды будущего. А завтрашний день несет в себе обещание восстановления забытой мудрости».

---
## Абзацы, оставшиеся в озвучке на английском (0)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.
## Пустые и почти пустые абзацы (16)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0055` — длина озвучки / длина оригинала: 0.69; классы правки: —

**Исходный абзац:**

> These objectives are close to the Club of Rome’s heart.

**В озвучку попало:**

> Эти цели близки сердцу Римского клуба.

---

### 2. `p0078` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### The World Academy of Art and Science

**В озвучку попало:**

> ### Всемирная академия искусств и науки

---

### 3. `p0395` — длина озвучки / длина оригинала: 0.82; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Emergence of a ‘Global Casino’

**В озвучку попало:**

> ## 1. Появление «мирового казино»

---

### 4. `p0465` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 4. A Solution: The Privatisation of Everything?

**В озвучку попало:**

> ## 4. Решение: приватизация всего?

---

### 5. `p0527` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Misclassification of Economics

**В озвучку попало:**

> ## 1. Ошибочная классификация экономики

---

### 6. `p0559` — длина озвучки / длина оригинала: 0.81; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 3. The Physics of Complex Flow Networks

**В озвучку попало:**

> ## 3. Физика сложных сетей потоков

---

### 7. `p0702` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Wate r lilie s s pre ading in a pond**

**В озвучку попало:**

> **Распространение кувшинок в пруду**

---

### 8. `p0808` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, *No Logo: Taking Aim at the Brand Bullies* (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in *The Economist* January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see *The Economist*, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary Policy’, *American Economic Review*, vol. 68 (1968), pp.1–17. We are not claiming that this process is the only cause of the business cycle, but that it is a contributing factor directly attributable to the prevailing monetary system. See Olivier J. Blanchard & Mark W. Watson (1987). See also ‘Shadow Government Statistics’ at *www.shadowstats.com* 6 See Milton Friedman & Anna Jacobson Schwartz (1993); J. P. Keeler (2001); Barry Eichengreen & K. Mitchener (2003); Carmen

**В озвучку попало:**

> 

---

### 9. `p0809` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_lost

**Исходный абзац:**

> Reinhart *et al.* (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, *Financial*

**В озвучку попало:**

> 

---

### 10. `p0937` — длина озвучки / длина оригинала: 0.65; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## Examples of Private Initiative Solutions

**В озвучку попало:**

> ## Примеры частных инициатив

---

### 11. `p0954` — длина озвучки / длина оригинала: 0.67; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Box 7.1 – Me nu of Motivation Sys te ms

**В озвучку попало:**

> ### Меню мотивационных систем

---

### 12. `p1123` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Benefits for participating businesses**

**В озвучку попало:**

> **Преимущества для бизнеса**

---

### 13. `p1140` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, *Creating Wealth: Growing Local*

**В озвучку попало:**

> 

---

### 14. `p1141` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Economies with Local Currencies* (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, *Insurance*

**В озвучку попало:**

> 

---

### 15. `p1142` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Markets and Adverse Selection: A Handbook for Health* *Economists* (1998). 5 Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine.* 6 *U.S. Health* (2005) National Center for Health Statistics, Department of Health and Human Services, No: 2005-1232. 7 “Behavioral and social interventions therefore offer great promise to reduce disease morbidity and mortality, but as yet their potential to improve the public’s health has been relatively poorly tapped.” Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine*. 8 L.A. Nefiodow, *Der Sechste Kondratieff* (2001). See also Appendix G for more information on Nicolai Kondratieff and ‘long waves’. 9 In the Netherlands an alliance involving the largest insurance company is planning to introduce several city-scaled experiments for motivation systems to deal with the ageing wave of the next decades. 10 Indeed not all preventive programmes are cheaper than the treatment . Studies show that it is more cost effective to treat tuberculosis rather than prevent it. See Borgdorff *et al*. (2002). Influenza vaccination is not cost effective for healthy working adults. See Bridges *et al*. (2000). However, all of these studies only compare the costs for treatment and the costs for prevention. They do not take into consideration the decrease in productivity and the absenteeism due to illness. 11 The most significant benefits occur after the second or third year of the programme. One hundred dollars or euros spent on preventive care programmes per year and per employee will have an ROI after the third year of 300 dollars or euros. See Goetzel (1999); Erfurt (1992); Powell (1999) and Chapman (2003). 12 Lia *et al.* (2008); Bastagli (2009). 13 See *www.cdc.gov* ~ *1.usa.gov/TPlink47n* 14 See Christian Léonard, *Croissance contre santé: Quelle responsabilisation du malade?* (2008). While Léonard, a leading Belgian health care expert, is strongly critical of the current ideology of punitive ‘responsibilisation’ of patients, he does argue in favour of a “genuine” autonomisation, which he links to Ivan Illich’s ideas of autonomy and conviviality: genuine personal responsibility can only flow from a reappropriation, by the patient him/herself, of his/her health. This requires preventive measures, which are under-financed in the current “alive and sick” logic. The Wellness Token system, therefore, moves in the direction called for by Léonard. 15 The Elderplan insurance company in the New York area has implemented successfully part of this idea with a Time Dollar currency.

**В озвучку попало:**

> 

---

### 16. `p1143` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> They have discovered that people participating in a Time Dollar system remain on average healthier because of a better social capital environment. 16 Lia *et al.* (2008); Paxson & Schady (2007). 17 The Swiss business-to-business currency system WIR has been successfully operating on this principle for 75 years. 18 C. J. Ruhm, *Macroeconomic Conditions, Health and Government Policy* (2006). 19 The text of this section is extracted and summarised from Marek Hudon and Bernard Lietaer, ‘Natural Savings: A New Microsavings Product for Inflationary Environments – How to Save Forests with Savings For and By the Poor?’, *Savings and Development*, vol. 4 (2006), pp.357-381 20 If the property is owned by a third party, one could also arrange for a long-term lease of the necessary land and pay the owner in part or whole with shares in the Natural Savings Company. 21 Depending on the size of the land and the community, one could make this a continuous process, with new plantations and harvest on parts of the total forest on a periodic, rotating basis. Well-known forestry management techniques should be applied as appropriate. 22 Lietaer (2001). 23 Dolde (1993). 24 See for example: Harmon (1959); Graham (1937) and (1944); Hart *et al.* (1964); Grondona (1975); Gondriaan (1932) and Jevons (1875).

**В озвучку попало:**

> 

---
