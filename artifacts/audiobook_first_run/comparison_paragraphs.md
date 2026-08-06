# Аудиокнига — первый живой прогон, материал для просмотра глазами

Книга: Bernard Lietaer et al., *Money and Sustainability: The Missing Link* (epub-derived PDF, `tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-160516072426.pdf`).
Режим: `processing_operation = "audiobook"` (standalone), en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260804T_money_audiobook_first_run`. Seed выборки: `20260804`.

Пары «исходный абзац → что попало в озвучку» взяты из перехваченного трафика к модели:
в запросе каждый абзац помечен маркером `[[DOCX_PARA_...]]`, в ответе — тем же маркером,
поэтому сопоставление точное, а не восстановленное по тексту.

В файл попадают только те абзацы, чей озвученный текст **дословно присутствует в итоговом
narration-артефакте** (`.tts.txt`) после того же `strip_markdown_for_narration`, который
применяет пайплайн. Абзацы, которые пайплайн переспрашивал и откатывал, в выборку не берутся.

**Про метрику.** Здесь озвучка — это перевод с английского на русский, поэтому посимвольный
diff «до/после» равен ~100 % у всех абзацев и ничего не ранжирует. Крайние случаи отобраны по
`длина озвучки / длина оригинала`: сильное сжатие — там, где содержание могло потеряться.
«Самые нетронутые» — по посимвольному совпадению с оригиналом: это абзацы, которые модель
вернула по-английски, не тронув.

## Что в файле

1. **Случайная выборка, 60 абзацев прозы** — по 20 из первой, средней и последней трети книги,
   `random.Random(20260804)`, без отбора «по красоте».
2. **20 абзацев с максимальным сжатием** — низ списка по отношению длин.
3. **10 абзацев с максимальным раздуванием** — верх того же списка.
4. **10 самых буквальных абзацев** — максимальное совпадение символов с оригиналом.
5. **25 абзацев, оставшихся в озвучке на английском** — самый крупный дефект прогона по объёму.
6. **Пустые и почти пустые абзацы — все 21**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1318; вернулось: 1317;
дошло до narration-артефакта: 1255.
Пул прозы, из которого делалась выборка: 454 абзацев.
Медианное отношение длин по прозе: 0.9965.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, по 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0048` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> Governments, media and most leaders mak e every possible effort to convince public opinion to stick to mainstream think ing. If society wishes to be or to become successful, they say, we have to k eep faith in the current paradigm. The gospel still is that everything has to be expressed in monetary terms. And that there is no salvation outside the dominant financial systems and bank ing practices, a monopoly and a major power instrument. Closed systems are preferred to open ones. Complexity is avoided. Indeed a shortsighted vision on sustainable solutions…

**В озвучку попало:**

> Правительства, средства массовой информации и большинство лидеров делают всё возможное, чтобы убедить общественность придерживаться традиционных взглядов. Они утверждают: если общество хочет добиться успеха, мы должны сохранять веру в текущую парадигму. Господствует убеждение, что всё должно быть выражено в денежном эквиваленте. Нам внушают, что нет спасения вне доминирующих финансовых систем и банковских практик, которые являются монополией и мощным инструментом влияния. Закрытые системы предпочитают открытым, а сложность стараются игнорировать. Это, безусловно, близорукий взгляд на поиск устойчивых решений.

---

### 2. `p0053` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> While the issue is by definition global, the CoR-EU felt the Report should primarily be addressed on its behalf to a recognised, authoritative and independent European body. The most appropriate choice seemed to be *Finance Watch,* a public interest association, recently created on the initiative of members of the European Parliament. It is dedicated to mak ing finance work for the good of society, strengthening the voice of society in financial regulation reforms by conducting citizen advocacy and presenting public interest arguments to lawmak ers as a counterweight to private interest lobbying by the financial industry.

**В озвучку попало:**

> Хотя проблема по определению носит глобальный характер, мы в Европейском отделении сочли, что доклад должен быть адресован признанному, авторитетному и независимому европейскому органу. Наиболее подходящим выбором стала организация Finance Watch — ассоциация общественных интересов, созданная по инициативе членов Европейского парламента. Она посвящена тому, чтобы финансы работали на благо общества, усиливая голос граждан в реформах финансового регулирования. Организация занимается адвокацией и представляет интересы общества перед законодателями, выступая противовесом лоббированию частных интересов со стороны финансовой индустрии.

---

### 3. `p0058` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> There is a great challenge here for the European U nion. We dare hope that the publication of *Money and Sustainability: The Missing Link* will inspire many a decision mak er and opinion leader to change course now, choosing new, creative approaches in monetary issues.

**В озвучку попало:**

> Перед Европейским союзом стоит серьезная задача. Мы смеем надеяться, что публикация доклада «Деньги и устойчивость: недостающее звено» вдохновит многих лиц, принимающих решения, и лидеров общественного мнения изменить курс. Мы призываем их выбрать новые, творческие подходы к денежно-кредитным вопросам.

---

### 4. `p0072` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> The book contains powerful arguments that need to be listened to, digested and acted upon. The section on how money affects sustainability mak es the k ey point that the global crises we face are interconnected. The financial crisis is but one dimension of a multi-dimensional puzzle. However, the book is more than a diagnosis of the ills and travails of our monetary system; it also points to new ways of reforming our financial system, to pioneering ideas and to potential solutions. The call for alternative think ing and innovative strategies is timely and necessary.

**В озвучку попало:**

> В этой книге представлены веские аргументы, к которым необходимо прислушаться, осмыслить их и начать действовать. Раздел о влиянии денег на устойчивое развитие подчеркивает ключевую мысль: глобальные кризисы, с которыми мы сталкиваемся, взаимосвязаны. Финансовый кризис — лишь одна из частей многогранной головоломки. Однако эта книга — не просто диагноз проблем нашей денежной системы. Она указывает на новые пути реформирования финансового сектора, предлагает новаторские идеи и возможные решения. Призыв к альтернативному мышлению и инновационным стратегиям сейчас как никогда актуален и необходим.

---

### 5. `p0081` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> This study complements other endeavours of WAAS stressing the essential value and role of human capital. The Report reminds us that money is a man-made instrument intended to help society optimise human welfare. The prevailing monetary system encourages the multiplication of money for destabilising speculative investment rather than for productive investment that creates jobs, raises real incomes and promotes social equity. The Report examines alternative monetary strategies that can help mobilise under-utilised social resources, especially the huge number of unemployed and underemployed young people and adults whose human potential is ignored and squandered by the current system. This Report is a call for prompt political and economic action.

**В озвучку попало:**

> Это исследование дополняет другие начинания Академии, подчеркивающие исключительную ценность и роль человеческого капитала. Доклад напоминает нам, что деньги — это инструмент, созданный человеком для повышения общественного благосостояния. Однако нынешняя денежная система поощряет приумножение капитала ради дестабилизирующих спекуляций, а не ради продуктивных инвестиций, которые создают рабочие места, повышают реальные доходы и способствуют социальному равенству. В докладе рассматриваются альтернативные денежные стратегии. Они могут помочь мобилизовать недоиспользуемые социальные ресурсы, особенно огромную армию безработных и частично занятых людей, чей потенциал нынешняя система просто игнорирует и растрачивает. Этот доклад — призыв к решительным политическим и экономическим действиям.

---

### 6. `p0099` — длина озвучки / длина оригинала: 1.17; классы правки: —

**Исходный абзац:**

> Fiat currency issued by private institutions through the creation of debt has been used by nations for centuries. Its deadly effects are becoming apparent. But its ability to alleviate the symptoms of distress has led to its use anyway. We can only hope that in this century we will begin to use less deadly alternatives.

**В озвучку попало:**

> Фиатные деньги, которые частные институты выпускают через создание долга, используются государствами на протяжении веков. Сейчас их губительные последствия становятся очевидны. Однако способность таких денег временно притуплять симптомы кризиса по-прежнему заставляет нас их использовать. Остается надеяться, что в этом столетии мы начнем применять менее опасные альтернативы.

---

### 7. `p0101` — длина озвучки / длина оригинала: 1.16; классы правки: —

**Исходный абзац:**

> A fish will never create fire while immersed in water. We will never create sustainability while immersed in the present financial system. There is no tax, or interest rate, or disclosure requirement that can overcome the many ways the current money system blocks sustainability.

**В озвучку попало:**

> Рыба никогда не добудет огонь, пока находится под водой. Мы никогда не добьемся устойчивого развития, пока погружены в нынешнюю финансовую систему. Никакие налоги, процентные ставки или требования к отчетности не смогут преодолеть те многочисленные барьеры, которыми нынешняя денежная система блокирует устойчивое развитие.

---

### 8. `p0102` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> I used not to think this. Indeed, I did not think about the money system at all. I took it for granted as a neutral and inevitable aspect of human society. But since beginning to read Bernard’s analyses I have a very different view. He is not alone. For example Thomas Greco has written on this topic. But the depth of Bernard’s practical experience, theoretical understanding, and historical perspectives on the financial system leave him without peer.

**В озвучку попало:**

> Раньше я так не думал. По правде говоря, я вообще не задумывался о денежной системе. Я принимал её как нечто нейтральное и неизбежное в человеческом обществе. Но после того, как я начал читать аналитические работы Бернарда, мой взгляд кардинально изменился. Он не одинок в своих выводах. Например, об этом писал Томас Греко. Но глубина практического опыта, теоретических знаний и исторического видения финансовой системы делает Бернарда непревзойденным экспертом в этой области.

---

### 9. `p0143` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> It is our contention that the ‘Missing Link’ between finance and the environment, between money and sustainability, lies elsewhere. What this Report demonstrates beyond doubt is a structural monetary flaw – a flaw in the very manner in which we create money – that is generating our disconcerting problems. The inescapable conclusion? That, in order to face the challenges of the 21st century, we need to rethink and overhaul our entire monetary system.

**В озвучку попало:**

> Мы утверждаем, что «недостающее звено» между финансами и окружающей средой, между деньгами и устойчивостью находится в другой плоскости. Этот отчет вне всяких сомнений доказывает наличие структурного денежного изъяна — ошибки в самом способе создания денег, — который и порождает наши тревожные проблемы. Неизбежный вывод таков: чтобы справиться с вызовами двадцать первого века, нам необходимо переосмыслить и полностью перестроить всю нашу денежную систему.

---

### 10. `p0151` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Debates about economic issues rarely reveal the paradigm from which an economist is speaking. We start by making explicit the conceptual framework that underlies our approach, and compare it with other paradigms currently in use. Rather than defining environmental and social issues as ‘externalities’, our approach sees economic activities as a subset of the social realm, which, in turn, is a subset of the biosphere. This view provides the basis for the emergence of a new set of pragmatic tools, flexible enough to address many of our economic, social and environmental challenges.

**В озвучку попало:**

> [thoughtful] Споры об экономических вопросах редко проясняют, с позиций какой парадигмы выступает тот или иной эксперт. Мы начнем с того, что четко обозначим концептуальную основу нашего подхода и сравним ее с другими моделями, существующими сегодня. Вместо того чтобы считать экологические и социальные проблемы «внешними факторами», мы рассматриваем экономическую деятельность как часть социальной сферы, которая, в свою очередь, является частью биосферы. Такой взгляд позволяет создать набор практических инструментов, достаточно гибких для решения многих наших экономических, социальных и экологических проблем.

---

### 11. `p0209` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> In closing, it would be naïve to think of complementary currencies as a magic bullet to solve all our current and future problems. However, rethinking our money is a necessary ingredient in any effective solution. We can no longer afford to overlook complementary currencies as the ‘Missing Link’ that can deliver a money system which promotes sustainability rather than undermining it at every turn.

**В озвучку попало:**

> В заключение хочу сказать: было бы наивно считать дополнительные валюты волшебной таблеткой от всех текущих и будущих проблем. Однако переосмысление денег — необходимый элемент любого эффективного решения. Мы больше не можем игнорировать дополнительные валюты как недостающее звено. Именно они способны создать денежную систему, которая будет способствовать устойчивому развитию, а не подрывать его на каждом шагу.

---

### 12. `p0271` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Conceptual relationships between the field of economics and the natural world can be described in three different ways. The most conventional view is to treat anything that is not dealt with unambiguously within one’s own theoretical framework as an ‘externality’ (see Figure 2.1). This economic view defines its own field as completely self-contained and excludes any other consideration as irrelevant. For instance, in such a view, the natural world is reduced to a resource, an input that is considered to be cost-free – to the extent that no money is exchanged to acquire it.

**В озвучку попало:**

> [serious] Концептуальные связи между экономикой и миром природы можно описать тремя способами. Самый распространенный подход — рассматривать всё, что не вписывается в рамки теории, как «внешний фактор». Эта экономическая модель определяет свою область как замкнутую систему, а всё остальное считает неважным. Например, в такой системе мир природы сводится лишь к ресурсам и сырью. Если за их получение не нужно платить деньги, они считаются бесплатными.

---

### 13. `p0290` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The standard measurement of economic progress thus remains the Gross National Product (GNP) per capita, which captures neither the depletion of natural resources, nor the quality of growth, nor the distribution of its benefits. Furthermore, market prices rarely reveal the real costs of a product or service. Their production and disposal can create damage that remains ignored in the conventional accounting system.¹⁶ Sufficient evidence now exists for a fundamental rethinking to take place if sustainability is taken seriously. If humanity’s decisions continue to be made on the basis of the Traditional Economics paradigm (Figure 2.1) or even the OECD paradigm (Figure 2.2), all signs point to a bleak future for our human condition and our planet. Indeed, humanity’s unsustainable behaviour is provoking the sixth great mass extinction of the geological record at a rate of 30,000 species per year or three species per hour. Having a greater awareness of the limitations of the dominant economic paradigms is therefore not merely of academic relevance.

**В озвучку попало:**

> [serious] Стандартным показателем экономического прогресса остается валовой национальный продукт на душу населения. Он не учитывает ни истощение природных ресурсов, ни качество роста, ни распределение его плодов. Более того, рыночные цены редко отражают реальную стоимость продукта или услуги. Их производство и утилизация могут наносить ущерб, который игнорируется в традиционной системе учета. Сегодня накоплено достаточно доказательств того, что если мы серьезно относимся к устойчивому развитию, необходим фундаментальный пересмотр подходов. Если решения человечества по-прежнему будут приниматься на основе традиционной экономической парадигмы или даже подхода Организации экономического сотрудничества и развития, все указывает на мрачное будущее для нас и нашей планеты. Неустойчивое поведение человечества уже провоцирует шестое массовое вымирание видов в истории Земли. Мы теряем около тридцати тысяч видов в год, или три вида каждый час. Поэтому осознание ограничений доминирующих экономических парадигм — это не просто академический вопрос.

---

### 14. `p0309` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> In some circles, the word ‘sustainability’ has become synonymous with constraints, heavy-handed governmental regulations, or even a leftist conspiracy. This perception has been amplified by well-funded disinformation campaigns underwritten by various vested business interests, in particular from the carbon energy industries.²² As will be seen in Chapter V, such campaigns are an example of the systematic short-term thinking automatically generated by our monetary system and the manner in which it ‘programs’ our behaviour.

**В озвучку попало:**

> [serious] В некоторых кругах слово «устойчивость» стало синонимом ограничений, жесткого государственного регулирования или даже левацкого заговора. Такое восприятие подогревается хорошо финансируемыми кампаниями по дезинформации, которые спонсируются различными заинтересованными бизнес-структурами, в особенности представителями индустрии углеродной энергетики. Как будет показано в пятой главе, подобные кампании — это пример систематического краткосрочного мышления, которое автоматически порождается нашей денежной системой и тем, как она «программирует» наше поведение.

---

### 15. `p0344` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> Understanding the community systems that are capable of satisfying a fuller range of human needs is a cornerstone of environmental and human sustainability. The Earth Charter Commission, working with the World Resources Institute and Global Community Initiatives, developed a comprehensive methodology for communities to evaluate their own sustainability and plan for a more sustainable future.³¹

**В озвучку попало:**

> [serious] Понимание общественных систем, способных удовлетворять широкий спектр человеческих потребностей, является краеугольным камнем экологической и социальной устойчивости. Комиссия по Хартии Земли в сотрудничестве с Институтом мировых ресурсов и инициативой «Глобальное сообщество» разработала комплексную методику. Она позволяет общинам оценивать уровень собственной устойчивости и планировать более стабильное будущее.

---

### 16. `p0346` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In order to spell out the economic paradigm in which we operate, the monetary dimension of the economy must explicitly be explored. Not all paradigms do this – some, and most notably the dominant Traditional Economics approach, view money as a passive element not affecting the way that individuals and collectives choose to act. The Ecological Economics paradigm, in the way we conceive it here, takes the monetary dimension much more seriously. How so? This is what we intend to explain in the remainder of this chapter. The exploration of this feature is what most sets this study apart from other economic texts and studies on sustainability.³²

**В озвучку попало:**

> [serious] Чтобы прояснить экономическую парадигму, в которой мы существуем, необходимо детально изучить денежный аспект экономики. Не все подходы делают это. Наиболее заметный из них — традиционная экономическая школа — рассматривает деньги как пассивный элемент, который не влияет на выбор людей и коллективов. Экологическая экономика, в том виде, в котором мы её здесь представляем, относится к денежной сфере гораздо серьёзнее. Почему? Именно это мы и собираемся объяснить в оставшейся части главы. Исследование этой особенности — то, что больше всего отличает данное исследование от других работ по экономике и устойчивому развитию.

---

### 17. `p0404` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> What most analysts fail to realise is that to identify structural problems, one must focus on what is common among all financial and monetary crises rather than on their differences. In metaphorical terms, a view of the entire forest is required, rather than a close-up inspection of any individual tree or of a specific type of tree.

**В озвучку попало:**

> Большинство аналитиков не осознают главного: чтобы выявить структурные проблемы, нужно сосредоточиться на том, что общего у всех финансовых и денежных кризисов, а не на их различиях. Метафорически говоря, нужно видеть весь лес целиком, а не рассматривать каждое отдельное дерево или конкретный вид деревьев.

---

### 18. `p0448` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Notice that this impact is completely independent of the quality of any government’s own policies, before or during the crisis. While much has been made of the case of Greece where fraud was involved, not much can be blamed on governments or citizens in Iceland, Ireland, Latvia, Denmark or Spain, all hit with sudden increases in their national debt, which reached 35% - 75% of their GDP. The irony is that, as soon as governments borrow these large sums from the financial system to save the system itself from bankruptcy, the financial system concludes that governments are now too indebted and need to be ‘disciplined’.

**В озвучку попало:**

> Заметьте, что этот эффект никак не зависит от качества политики правительства до или во время кризиса. Хотя много шума было вокруг случая с Грецией, где имели место махинации, в Исландии, Ирландии, Латвии, Дании или Испании винить правительства или граждан в чем-то сложно. Все эти страны столкнулись с внезапным ростом национального долга, который достиг 35–75 процентов их ВВП. Ирония в том, что как только правительства занимают эти огромные суммы у финансовой системы, чтобы спасти саму систему от банкротства, финансовая система приходит к выводу, что правительства теперь слишком закредитованы и их нужно «дисциплинировать».

---

### 19. `p0449` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> Figure 3.4 brings together the various components of the impact of banking crises on government finances. The direct fiscal cost of bailing out the banking system is added to output losses with an automatic drop in tax income. Governments thus have no other option than to increase their indebtedness. This, in turn, results in the downgrading of the creditworthiness of affected countries and makes their debt more expensive. What does all this lead to?

**В озвучку попало:**

> Рисунок 3.4 объединяет различные компоненты влияния банковских кризисов на государственные финансы. Прямые фискальные расходы на спасение банковской системы добавляются к потерям объемов производства, сопровождающимся автоматическим падением налоговых поступлений. У правительств не остается иного выбора, кроме как увеличивать свою задолженность. Это, в свою очередь, приводит к снижению кредитного рейтинга пострадавших стран и удорожанию их долга. К чему же все это ведет?

---

### 20. `p0453` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> The timing of this sudden increase in government debt is particularly unfortunate. The current decade is one in which the OECD countries and their governments have to deal with unprecedented pressures not amenable to being postponed. As mentioned in Chapter I, two critical and predictable challenges during the next decade will be the transition to a post-carbon economy and the sharp increase in financial requirements for retiring baby boomers.

**В озвучку попало:**

> [thoughtful] Время этого резкого роста государственного долга крайне неудачно. Нынешнее десятилетие требует от правительств стран Организации экономического сотрудничества и развития решения беспрецедентных проблем, которые невозможно отложить на потом. Как уже упоминалось в первой главе, двумя критическими и неизбежными вызовами ближайших десяти лет станут переход к экономике с низким уровнем выбросов углерода и резкое увеличение финансовых потребностей в связи с выходом на пенсию поколения бэби-бумеров.

---

### 21. `p0468` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> As of early 2012, forty-four out of the fifty US States face bankruptcy. They are under increasing pressure to start ‘Public-Private Partnerships’, called P3s in the USA and Private Finance Initiatives (PFI) in the UK. What actually occurs in these benign-sounding partnerships is that governments are obliged to sell off existing infrastructure, built and paid for with taxpayers’ money, in order to reduce existing debt or pay for current public expenditures. Once the infrastructure is privatised, new owners can charge fees for the use of a once free public utility, or increase existing tolls. Thus taxpayers will end up paying twice for the same infrastructure and the second time could be more expensive than the first, given that many infrastructural assets are natural monopolies.

**В озвучку попало:**

> [serious] К началу 2012 года сорок четыре из пятидесяти штатов США оказались на грани банкротства. Они испытывают растущее давление, вынуждающее их переходить к так называемым государственно-частным партнерствам. В США их называют «Пи-три», а в Великобритании — «Частными финансовыми инициативами». На деле в этих партнерствах с благозвучными названиями правительства вынуждены распродавать существующую инфраструктуру, построенную и оплаченную на деньги налогоплательщиков, чтобы сократить долг или покрыть текущие расходы. После приватизации новые владельцы могут взимать плату за пользование тем, что раньше было бесплатным общественным благом, или повышать существующие дорожные сборы. В итоге налогоплательщики платят за одну и ту же инфраструктуру дважды, причем второй раз может обойтись дороже, учитывая, что многие инфраструктурные объекты являются естественными монополиями.

---

### 22. `p0469` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Private investments in public utilities can generate a ‘win-win’ situation when designed and implemented properly. In several European countries, there is a well-established practice of, for instance, the private sector building new toll-paying highways. When such auctions are well prepared and transparent, the results can be beneficial to all parties. However, the P3s currently being proposed are different from their historical precedents in three ways:

**В озвучку попало:**

> Частные инвестиции в коммунальные услуги могут создать ситуацию «выигрыш-выигрыш», если они правильно спроектированы и реализованы. В ряде европейских стран существует устоявшаяся практика, когда частный сектор строит новые платные автомагистрали. Когда такие аукционы подготовлены прозрачно, результаты могут быть полезны всем сторонам. Однако предлагаемые сейчас государственно-частные партнерства отличаются от исторических прецедентов по трем пунктам.

---

### 23. `p0524` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> The fourth step will consist of testing the ‘complex flow network’ methodology on real-life natural ecosystems and exposing the structural conditions required for a network to be sustainable. We will demonstrate that these findings are applicable to any complex system possessing a similar structure regardless of what circulates in a given network – biomass in an ecosystem, electrons in an electrical power network or money in an economy.

**В озвучку попало:**

> Четвёртый шаг будет заключаться в тестировании методологии «сложных сетей потоков» на реальных природных экосистемах и выявлении структурных условий, необходимых для устойчивости сети. Мы покажем, что эти выводы применимы к любой сложной системе со схожей структурой, независимо от того, что именно циркулирует в ней — биомасса в экосистеме, электроны в энергосети или деньги в экономике.

---

### 24. `p0546` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> This phenomenon of *ordered complexity* does not occur in systems ruled by simple linear causality, nor does it arise when the components are only weakly coupled. It is the key attribute of the realm of complexity. A system can therefore be labelled complex if, and only if, it has two characteristics: a high diversity of components and a dense network of interactions between these components. As Beinhocker and others²¹ have shown, this is certainly the case with economic processes.

**В озвучку попало:**

> Феномен упорядоченной сложности не встречается в системах, подчиняющихся простой линейной причинности, и не возникает там, где компоненты связаны слабо. Это ключевой признак сферы сложности. Систему можно назвать сложной только в том случае, если она обладает двумя характеристиками: большим разнообразием компонентов и плотной сетью взаимодействий между ними. Как показали Эрик Бейнхокер и другие исследователи, это в полной мере относится к экономическим процессам.

---

### 25. `p0569` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> When we want to express sustainability graphically, three variables are involved: diversity, interconnectivity and the relative weight put on efficiency *vs.* resilience. We are thus dealing with a four-dimensional object, which is difficult to render in a two-dimensional graph. In Appendix D2, a one-minute animation movie presents all four dimensions. In the same section a sequence of three-dimensional graphs gives an idea of what shape we are dealing with.

**В озвучку попало:**

> Когда мы хотим графически выразить устойчивость, нам приходится учитывать три переменные: разнообразие, взаимосвязанность и относительный приоритет эффективности по сравнению с устойчивостью. Таким образом, мы имеем дело с четырехмерным объектом, который трудно отобразить на обычном плоском графике. В приложении D2 представлена минутная анимация, демонстрирующая все четыре измерения. В том же разделе приводится серия трехмерных графиков, помогающих представить форму этой системы.

---

### 26. `p0573` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> This, of course, causes the big organisations to get bigger still, and the smaller ones to die off, just as Schumpeter ’s classical ‘creative destruction’ theory predicts. Unfortunately, killing off large numbers of smaller organisations reduces resilience, increases instability and steadily moves the whole system towards collapse (i.e., sustainability = 0). Common examples include: large, unrestrained predators killing off all their prey causing an ecosystem to collapse; digging large canals in the New Orleans delta, which drained soil from the wetlands, causing the city to sink and the wetlands to die; and monopolies of commerce which kill off so many small competitors that a positive feedback cycle of ‘the more you have, the more you get’ locks into a ‘winner takes all’ game. This can lead to an economic ‘bubble’, a shimmering bubble of wealth over a feeble, eviscerated real economy. This law of physics explains why we once introduced anti-trust laws.

**В озвучку попало:**

> Это, разумеется, заставляет крупные организации расти еще больше, а мелкие — отмирать, в точности как предсказывает классическая теория «созидательного разрушения» Шумпетера. К несчастью, уничтожение большого числа мелких организаций снижает жизнестойкость, увеличивает нестабильность и постепенно подталкивает всю систему к коллапсу, то есть к нулевой устойчивости. Примеров множество: крупные хищники, бесконтрольно истребляющие добычу, что ведет к гибели экосистемы; прокладка больших каналов в дельте Нового Орлеана, из-за чего почва осушилась, город начал проседать, а водно-болотные угодья погибли; или торговые монополии, которые уничтожают так много мелких конкурентов, что запускается цикл положительной обратной связи «чем больше имеешь, тем больше получаешь», превращаясь в игру, где «победитель получает всё». Это может привести к экономическому «пузырю» — сверкающей оболочке богатства над слабой, обескровленной реальной экономикой. Этот физический закон объясняет, почему в свое время были введены антимонопольные законы.

---

### 27. `p0579` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> The main point is that nature does not select for maximum efficiency but for an optimal balance between the two opposing poles of throughput efficiency and resilience. In other words, sustainability requires just enough, and not too much, of both efficiency and resilience. In most human-designed systems, and certainly in the monetary domain, we have been concerned only with efficiency, and have therefore tended to unduly sacrifice resilience.

**В озвучку попало:**

> [thoughtful] Главный вывод заключается в том, что природа стремится не к максимальной эффективности, а к оптимальному балансу между двумя противоположностями: пропускной способностью и устойчивостью. Иными словами, для жизнеспособности системы нужно ровно столько эффективности и устойчивости, сколько необходимо, и не более того. В большинстве созданных человеком систем, и особенно в финансовой сфере, мы заботимся исключительно об эффективности, из-за чего зачастую неоправданно жертвуем устойчивостью.

---

### 28. `p0581` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> Finally, we can assume that nature has solved many of the developmental problems in ecosystems over time. Otherwise, these ecosystems would no longer exist today. These are the same type of problems with which humanity is still struggling in economic terms. Also of interest is that all ecosystems have their most critical structural parameters such as diversity and interconnectivity within a very specific narrow range or what we have called the window of viability.

**В озвучку попало:**

> Можно предположить, что природа за долгие годы решила многие проблемы развития экосистем. В противном случае они бы просто не сохранились до наших дней. Человечество сталкивается с аналогичными проблемами в экономике. Примечательно, что все экосистемы поддерживают свои критические параметры — такие как разнообразие и взаимосвязанность — в очень узком, специфическом диапазоне, который мы называем «окном жизнеспособности».

---

### 29. `p0583` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Similarly, complexity theorist Predrag Cvitanovic states, “The wonderful thing about this universality is that it does not matter much how close our equations are to the ones chosen by nature, as long as the model is in the same universality class … as the real system. This means that we can get the right physics out of very crude models.”³³ In other words, insights about the behaviour of a system do not require ever more refined modelling, as is the case with linear models. It is simply a matter of determining the class of model characterising that particular system. The findings from one network are valid for any other network displaying the same *structure*, whether the components are alligators and fish in an ecosystem, electrons in an electrical circuit, or money in an economy.

**В озвучку попало:**

> [curious] Специалист по теории сложности Предраг Цвитанович добавляет: «Удивительная особенность этой универсальности в том, что не так уж важно, насколько наши уравнения близки к тем, что выбрала природа, если модель принадлежит к тому же классу универсальности, что и реальная система. Это значит, что даже из очень грубых моделей можно извлечь верные физические принципы». Иными словами, чтобы понять поведение системы, не нужны всё более усложняющиеся модели, как в случае с линейными системами. Достаточно просто определить класс модели, характерный для конкретной системы. Выводы, сделанные для одной сети, верны для любой другой с такой же структурой — будь то аллигаторы и рыбы в экосистеме, электроны в цепи или деньги в экономике.

---

### 30. `p0638` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> This chapter has provided a step-by-step explanation, with backing from scientific evidence, that a structural cause is behind the repeated systemic crises described in Chapter III. The complex flow network approach to monetary and financial stability is *not* a metaphor: it is systemic bio-mimicry.

**В озвучку попало:**

> [serious] В этой главе мы шаг за шагом, опираясь на научные данные, объяснили, что за повторяющимися системными кризисами, описанными ранее, стоят структурные причины. Подход к денежно-кредитной стабильности через теорию сложных сетей потоков — это не просто метафора, а применение принципов системного биомимикрирования.

---

### 31. `p0643` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> Three hundred years of cat-and-mouse games between regulatory authorities and the financial system have proven that regulation – while useful and necessary – may reduce the frequency, but never avoid the re-occurrence, of systemic crises. Paul Romer, a Senior Fellow at the Stanford Institute for Economic Policy Research, says: “Every decade or so, any finite system of financial regulation will lead to a systemic financial crisis”.⁵¹ Is infinite regulation really the only solution?

**В озвучку попало:**

> Триста лет игры в кошки-мышки между регулирующими органами и финансовой системой доказали, что регулирование, при всей его полезности и необходимости, может снизить частоту системных кризисов, но никогда не предотвратит их повторение. Пол Ромер, старший научный сотрудник Стэнфордского института исследований экономической политики, отмечает: «Примерно раз в десятилетие любая конечная система финансового регулирования будет приводить к системному финансовому кризису». Неужели бесконечное регулирование — это действительно единственное решение?

---

### 32. `p0661` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Money is generally assumed to be a passive accounting instrument that facilitates exchanges more efficiently than barter. Money is seen as an oil lubricating the exchange process, but not otherwise changing its nature. It is therefore automatically assumed that the type of exchange medium one uses does not affect the nature of exchanges, the time horizon of our investments, or the relationships between us as users. We will demonstrate why all these assumptions are wrong.

**В озвучку попало:**

> Обычно деньги считают пассивным инструментом учёта, который просто упрощает обмен, заменяя бартер. Деньги воспринимаются как «смазка» для экономических процессов, которая не меняет их сути. Поэтому автоматически предполагается, что тип используемого средства обмена не влияет ни на характер сделок, ни на горизонт планирования инвестиций, ни на отношения между людьми. Мы покажем, почему все эти предположения ошибочны.

---

### 33. `p0766` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Sociologist Robert Putnam defines social capital as “Features of social organisation, such as trust, norms and networks, that can improve the efficiency of society by facilitating coordinated actions”.³⁴ The content of this concept has not evolved for almost a century, as illustrated by the 1916 definition by Lyda Judson Hanifan: “The whole community will profit from the co-operation of its parts, and the individual, as a result of the links forged, will experience benefits such as help, compassion and community spirit from its neighbours…When people in a community trust each other, and when it has become customary to come together for entertainment purposes, to exchange views or for personal pleasure, skilful leaders can easily employ this social capital for the general improvement of welfare in the community as a whole.”³⁵ Hazel Henderson uses a very short but effective label for it all, referring to the “love economy”.³⁶

**В озвучку попало:**

> [thoughtful] Социолог Роберт Патнэм определяет социальный капитал как «особенности социальной организации, такие как доверие, нормы и сети, которые могут повысить эффективность общества за счет содействия скоординированным действиям». Содержание этого понятия практически не изменилось за столетие. Еще в 1916 году Лида Джадсон Ханифан писала: «Все общество выиграет от сотрудничества своих частей, а индивид благодаря созданным связям получит такие блага, как помощь, сострадание и чувство общности со стороны соседей... Когда люди в сообществе доверяют друг другу и когда становится обычаем собираться вместе для развлечения, обмена мнениями или личного удовольствия, умелые лидеры могут легко использовать этот социальный капитал для общего улучшения благосостояния всего сообщества». Хейзел Хендерсон использует для этого очень короткое и емкое определение — «экономика любви».

---

### 34. `p0777` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> This is how today’s monetary system pits participants in the economy against each other. This story isolates the role of interest – the 11th round – as part of the money creation process, and its impact on the participants.⁴⁵ The point of the ‘11th Round’ is simple: competition to obtain the money necessary to pay the interest, which is not initially created along with the principal, is structurally embedded in our current system. How does such a permanent undertow affect social capital? Can we measure such an effect? Can social capital even be measured in the first place?

**В озвучку попало:**

> Именно так современная денежная система сталкивает участников экономики друг с другом. Эта история наглядно показывает роль процента — той самой одиннадцатой монеты — в процессе создания денег и его влияние на людей. Суть «одиннадцатого раунда» проста: конкуренция за деньги, необходимые для выплаты процентов, которые изначально не создаются вместе с основной суммой долга, структурно заложена в нашу нынешнюю систему. Как такое постоянное скрытое напряжение влияет на социальный капитал? Можно ли измерить этот эффект? И можно ли вообще измерить социальный капитал?

---

### 35. `p0787` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The second source of evidence of the role money plays in eroding social capital comes from clinical psychology. Neuro-imaging studies have demonstrated that the mere presence of conventional money can alter social behaviour. Greed, as well as other negative emotions such as fear, anger, intolerance, scapegoating, and panic are increased whenever money is present. It even 49 measurably decreases the performance of the brain in making rational decisions!⁵⁰

**В озвучку попало:**

> [serious] Вторым источником доказательств того, что деньги подрывают социальный капитал, служит клиническая психология. Исследования с помощью нейровизуализации показали, что одно лишь присутствие привычных нам денег способно изменить поведение человека. Жадность, а также другие негативные эмоции — страх, гнев, нетерпимость, поиск козлов отпущения и паника — усиливаются, когда в поле зрения появляются деньги. Более того, они заметно снижают способность мозга принимать рациональные решения.

---

### 36. `p0834` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Friedrich Nietzsche defined money as “the crowbar of power”.⁴ Napoleon similarly claimed that three things were needed to effectively wage war: “Money, money and money”. Napoleon’s realisation of an ironclad connection between money and war was hardly new. Twenty centuries earlier, the Roman statesman and orator Cicero concluded that, “the sinews of war are unlimited money”.⁵

**В озвучку попало:**

> Фридрих Ницше называл деньги «рычагом власти». Наполеон Бонапарт утверждал, что для ведения войны нужны три вещи: «Деньги, деньги и еще раз деньги». Осознание Наполеоном неразрывной связи между деньгами и войной не было чем-то новым. Еще за двадцать веков до него римский государственный деятель и оратор Цицерон пришел к выводу, что «деньги — это нерв войны».

---

### 37. `p0844` — длина озвучки / длина оригинала: 1.05; классы правки: —

**Исходный абзац:**

> On the side of the financial sector, the development of a *market for government* *debt* made it possible to deal with sudden increases in expenditures, typically triggered by wars. For a government, the benefit of borrowing was to spread the costs of a war over time, and smoothing out the subsequent need for increased taxation over many years. While private debt has more than 5,000 years of recorded history, the emergence of public debt is much more recent. The earliest government debt goes back to 12th century Venice. At that time, public debt was secured through a state tax monopoly on salt, of which the revenues were earmarked for debt service and redemption. The modern market for governmental debt took off only after the English Consolidating Act of 1751, in what became known as the British ‘consols’ (the predecessors of today’s ‘gilts’, and all other government bonds). The confidence that interest will be paid on such debt critically depends on the government’s capacity to tax its citizens.

**В озвучку попало:**

> [serious] Со стороны финансового сектора развитие рынка государственного долга позволило справляться с внезапным ростом расходов, обычно вызванным войнами. Для правительства преимущество заимствований заключалось в возможности распределить военные расходы во времени и сгладить необходимость резкого повышения налогов на долгие годы. Хотя частный долг имеет более чем пятитысячелетнюю историю, появление государственного долга произошло гораздо позже. Самые ранние государственные долги относятся к Венеции двенадцатого века. В то время государственный долг был обеспечен государственной монополией на соль, доходы от которой направлялись на обслуживание и погашение долга. Современный рынок государственных облигаций начал активно развиваться только после принятия английского закона о консолидации 1751 года, когда появились так называемые британские «консоли» — предшественники современных государственных облигаций. Уверенность в том, что по такому долгу будут выплачены проценты, критически зависит от способности правительства собирать налоги со своих граждан.

---

### 38. `p0859` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The Old Lady of Threadneedle Street, as the British central bank in the City of London is still referred to, “is in all respects to money as St. Peter ’s is to the Faith. And the reputation is deserved, for most of the art as well as much of the mystery associated with the management of money originated there.”¹⁴ For the USA, this same sequence was completed with the Federal Reserve Act of 1913.¹⁵

**В озвучку попало:**

> Британский центральный банк, расположенный в лондонском Сити, до сих пор называют «Старой леди с Треднидл-стрит». Говорят, что для мира денег он значит то же самое, что собор Святого Петра для веры. И эта репутация заслужена, ведь большая часть искусства и многие тайны управления деньгами зародились именно там. В Соединенных Штатах эта же последовательность завершилась принятием Закона о Федеральной резервной системе в 1913 году.

---

### 39. `p0883` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Realistic debt reduction is not the only argument in favour of nationalising the money creation process. James Robertson²⁸ shows that this change would provide the government with significant additional revenue to spend on what it considers relevant. In the case of the UK, this would represent both:

**В озвучку попало:**

> Реалистичное сокращение долга — не единственный аргумент в пользу национализации процесса создания денег. Джеймс Робертсон показывает, что такие перемены обеспечат правительству значительные дополнительные доходы, которые можно направить на важные цели. В случае с Великобританией это означало бы:

---

### 40. `p0896` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> Governments must, like any household, raise the money needed to pay for what they do, either through income (levying tax revenues) or debt (issuing governmental bonds). Banks are intermediary service providers that collect deposits, hold a small fraction as reserves, and lend out the remainder to creditworthy private or governmental entities that require it.

**В озвучку попало:**

> [serious] Правительства, подобно любому домохозяйству, должны изыскивать средства на свои нужды. Они делают это либо через доходы — собирая налоги, — либо через долги, выпуская государственные облигации. Согласно этой логике, банки выступают лишь посредниками. Они принимают депозиты, оставляют небольшую часть в виде резервов, а остальное выдают в кредит надежным частным или государственным заемщикам.

---

### 41. `p0929` — длина озвучки / длина оригинала: 0.97; классы правки: truncated_sentence

**Исходный абзац:**

> Footnotes 1 John Kenneth Galbraith, *Money: Whence It Came, Where It Went* (1975), p.5. 2 For instance, the Natural Savings instrument presented in Chapter VII would mainly be a savings tool, not a medium of exchange or unit of account. In many civilisations, the unit of account was also different from the medium of exchange. A case in point is Homeric Greece, where the unit of account was the ox but where, for the sake of convenience, actual exchanges were often performed with ingots of bronze or other commodities. 3 For the arguments offered in this paragraph, see Philippe Derudder and André-Jacques Holbecq (2008) p.17. 4 Friedrich Nietzsche, *Thus Spoke Zarathustra,* translated by Adrian del Caro and edited by Robert Pippin (2006). 5 The original is elegantly succinct: *“Nervos belli, pecuniam infinitam”* from Cicero’s *Fifth* *Philippic.* See Jon Hall, *The Philippics*, in

**В озвучку попало:**

> Примечания. 1. Джон Кеннет Гэлбрейт, «Деньги: откуда они берутся и куда уходят» (1975), стр. 5. 2. Например, инструмент «Природные сбережения», представленный в седьмой главе, был бы преимущественно сберегательным инструментом, а не средством обмена или расчетной единицей. Во многих цивилизациях расчетная единица отличалась от средства обмена. Показательный пример — гомеровская Греция, где расчетной единицей был бык, но для удобства реальные обмены часто совершались с помощью бронзовых слитков или других товаров. 3. Аргументы, приведенные в этом абзаце, см. в работе Филиппа Дерудера и Андре-Жака Ольбека (2008), стр. 17. 4. Фридрих Ницше, «Так говорил Заратустра», перевод Адриана дель Каро под редакцией Роберта Пиппина (2006). 5. Оригинал лаконичен и изящен: «Nervos belli, pecuniam infinitam» из Пятой филиппики Цицерона. См. Джон Холл, «Филиппики», в

---

### 42. `p0948` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> We start with the least controversial and finish with the most controversial, moving from systems against which we expect little resistance to those which will elicit the most. For instance, we proceed from purely voluntary systems not requiring anyone’s permission to be started, to compulsory systems that would require new legislation. We are not claiming, however, that the most demanding systems are also the most desirable.

**В озвучку попало:**

> Мы начнем с наименее спорных примеров и закончим самыми дискуссионными, переходя от систем, которые не встретят особого сопротивления, к тем, что вызовут наибольшие споры. Например, мы движемся от чисто добровольных систем, не требующих ничьего разрешения, к обязательным, для которых потребуется новое законодательство. Однако мы не утверждаем, что самые сложные системы — самые желанные.

---

### 43. `p0951` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> For all their diversity, the nine systems we describe share two common denominators. First, they are all designed to act as *complementary systems*, i.e. they are designed to operate in parallel with the existing national bank-debt money system. Second, they should ideally all be as transparent for their users as possible. For example, before making an exchange, each party could have the right to see the other party’s account. Transparency allows these systems to be self-policing and reduce potential fraud. These systems would be most cost-effective if they used mobile electronic devices such as mobile phones.

**В озвучку попало:**

> При всем своем разнообразии, девять описанных нами систем имеют два общих знаменателя. Во-первых, все они разработаны как дополнительные системы, то есть должны работать параллельно с существующей национальной системой банковских долговых денег. Во-вторых, в идеале они должны быть максимально прозрачными для пользователей. Например, перед совершением обмена каждая сторона может иметь право видеть счет другой стороны. Прозрачность позволяет таким системам саморегулироваться и снижать риск мошенничества. Эти системы будут наиболее экономически эффективными, если использовать мобильные электронные устройства, такие как смартфоны.

---

### 44. `p0952` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Again, each of these initiatives could be made viable on its own. However, if several of them were to be implemented in parallel, their cumulative effect could demonstrate the synergistic power and resilience of what we refer to as a ‘monetary ecosystem’ in Chapter IV. They could also combine with systems that are already operational, many of which have been documented elsewhere.²

**В озвучку попало:**

> Каждая из этих инициатив может быть жизнеспособной сама по себе. Однако, если внедрить несколько из них параллельно, их совокупный эффект продемонстрирует синергическую мощь и устойчивость того, что мы называем «денежной экосистемой» в четвертой главе. Они также могут сочетаться с уже действующими системами, многие из которых описаны в других источниках.

---

### 45. `p0993` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Wellness Tokens are specifically designed to use a preventive approach to promote and maintain the good health of participants. Just as ‘Frequent Flyer Miles’ are issued by airline alliances to induce a habit of taking the same airline for all one’s trips, Wellness Tokens would be issued by a Wellness Alliance to induce healthy habits. The members of the Wellness Alliance would be those organisations that have a financial interest in keeping the population healthy (e.g. insurance companies, local government and local employers). One of the purposes of the Wellness Token would be to generate changes in habits towards health promotion and disease prevention by encouraging healthy behaviours and emphasising preventive health care. Such an approach would also be a means of financing supportive care so that the elderly, the chronically ill and the disabled can remain in their own homes, and delay for as long as possible their entry into a long-term medical facility, where the costs escalate.

**В озвучку попало:**

> [serious] Велнес-токены специально разработаны для внедрения профилактического подхода к здоровью. Подобно тому как авиакомпании выпускают бонусные мили, чтобы приучить пассажиров летать именно их рейсами, Велнес-альянс будет выпускать токены для формирования здоровых привычек. В такой альянс войдут организации, финансово заинтересованные в здоровье населения: страховые компании, местные органы власти и работодатели. Одной из целей токенов станет изменение образа жизни через поощрение полезных привычек и акцент на профилактике. Такой подход также позволит финансировать поддерживающий уход на дому для пожилых, хронически больных и людей с ограниченными возможностями. Это поможет им как можно дольше оставаться дома и отсрочить переход в специализированные медицинские учреждения, где стоимость обслуживания резко возрастает.

---

### 46. `p1030` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> If there were 100,000 ‘tree shares’ in the Savings Company, then one share would represent 1/100,000 of the total timber value in the plantation. If the trees were ready for harvest after twenty years, the value curve between planting and harvest would resemble figure 7.3 below. The curve provides an easy reference for the number of shares paid for a day’s work. As long as the members of a community clearly understood the value of a ‘tree share’ in their own terms, the exchange of the shares for goods and services among themselves would be facilitated. Hereafter, we will express the value in terms of workdays.

**В озвучку попало:**

> [serious] Если в компании выпущено сто тысяч «лесных акций», то одна акция представляет собой одну стотысячную часть общей стоимости древесины на плантации. Если деревья будут готовы к рубке через двадцать лет, кривая стоимости между посадкой и сбором урожая будет выглядеть как график, представленный далее. Эта кривая служит удобным ориентиром для определения количества акций, выплачиваемых за день работы. Как только члены сообщества поймут ценность «лесной акции» в привычных для них категориях, они смогут свободно использовать их для обмена товарами и услугами. В дальнейшем мы будем выражать стоимость акций в рабочих днях.

---

### 47. `p1033` — длина озвучки / длина оригинала: 1.02; классы правки: —

**Исходный абзац:**

> Let us assume that the value of a ‘tree share’ at maturity after twenty years is fourteen workdays, and that its growth is reflected in the value curve above, expressed in workdays. For the first two years of the project, one day’s work earns one share. But by the ninth year the shares have grown in value to be worth four days of work, so a day’s work is payable with a quarter of a share. (Note: it is always possible to pay labour partially in tree shares, and the rest in conventional money.)

**В озвучку попало:**

> [thoughtful] Предположим, что через двадцать лет, к моменту созревания, стоимость одной «древесной акции» составит четырнадцать рабочих дней. Рост этой стоимости отражен на графике выше. В первые два года проекта один рабочий день оплачивается одной акцией. Однако к девятому году стоимость акций вырастает до четырех рабочих дней, поэтому за день труда теперь полагается четверть акции. Заметьте: оплату труда всегда можно производить частично «древесными акциями», а остальное выплачивать обычными деньгами.

---

### 48. `p1045` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Natural Savings could potentially reduce the gap between rich and poor. The conventional way of reducing this gap is to increase taxes on the rich and redistribute the proceeds in programmes benefiting the poor. In the Natural Savings system, those willing to work could create real wealth by themselves with long-term protection against inflation, banking or monetary crashes. The best way to earn tree shares would be by participating early in the tree plantation project or other community project approved by the local government and the Natural Savings Company. Those in the poorest levels of society could thus be able to reliably accumulate wealth. An investment in living trees would not only be inflation-proof and secure against monetary crashes, but would organically grow in value until maturity.

**В озвучку попало:**

> Система «Природных сбережений» способна сократить разрыв между богатыми и бедными. Традиционный способ борьбы с неравенством — повышение налогов на богатых и перераспределение средств в пользу нуждающихся. В системе «Природных сбережений» люди, готовые трудиться, могут самостоятельно создавать реальные ценности, защищенные от инфляции, банковских кризисов и денежных обвалов. Лучший способ заработать такие акции — это участие в проектах по посадке деревьев или других инициативах, одобренных местными властями и компанией. Таким образом, даже самые бедные слои населения смогут надежно накапливать богатство. Вложения в живые деревья не только защищены от инфляции и финансовых потрясений, но и органически растут в цене до самого момента сбора урожая.

---

### 49. `p1047` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> In most countries, the vast majority of private jobs (75% to 95%) are created in small and medium-sized enterprises (SMEs). Addressing unemployment as a genuine and serious social sustainability challenge is one way of improving the rates of development and survival of SMEs.

**В озвучку попало:**

> [serious] В большинстве стран подавляющее большинство рабочих мест в частном секторе — от 75 до 95 процентов — создается малыми и средними предприятиями. Решение проблемы безработицы как серьезного вызова для социальной устойчивости — это один из способов повысить выживаемость и темпы развития такого бизнеса.

---

### 50. `p1100` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Throughout the circulation life of each TRC, from its creation to its final cash-in, a demurrage fee of 3.5% to 4% a year is in effect. Demurrage is a time-related charge on money. The demurrage fee acts in a similar manner to a linear parking fee, with the charge increasing in proportion to the time the car is occupying a parking spot. Financially, it corresponds to a negative interest rate. Whoever is holding the TRC is, therefore, charged the demurrage fee in proportion to the time they hold on to it. With a demurrage charge of 3.5% to 4%, the actual cost of holding it for a few days or even a few months is still low compared to today’s international currency transaction costs. Because the TRC exists only in electronic form, it is easy to know exactly how much time has elapsed between the moment a user receives TRCs and the moment they are transferred to others. The demurrage charge serves two key functions:

**В озвучку попало:**

> [serious] На протяжении всего срока обращения каждой единицы TRC — от момента создания до финального обналичивания — взимается комиссия за хранение, или демередж, в размере от трёх с половиной до четырёх процентов годовых. Демередж — это плата за время владения деньгами. Его можно сравнить с оплатой парковки: чем дольше автомобиль занимает место, тем выше стоимость. С финансовой точки зрения это равносильно отрицательной процентной ставке. Таким образом, комиссия начисляется каждому, у кого на счету находятся TRC, пропорционально времени владения ими. При ставке в три с половиной — четыре процента реальные затраты на удержание валюты в течение нескольких дней или даже месяцев остаются низкими по сравнению с нынешними расходами на международные валютные переводы. Поскольку TRC существуют только в электронном виде, система точно фиксирует время между получением единиц пользователем и их переводом другим лицам. Демередж выполняет две ключевые функции:

---

### 51. `p1111` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> The End User returns the TRCs to the TRC Alliance (4a). They are converted either to national currency or a corresponding volume of TRC commodities (which is called ‘taking delivery’ in the commodity market) chosen by the End User, minus the transaction fee of 2%. The cash-in may take place directly with the TRC Alliance or through an intermediary bank, just like any foreign exchange transaction today (4b).

**В озвучку попало:**

> Конечный пользователь возвращает TRC Альянсу. Они конвертируются в национальную валюту или в соответствующий объём товаров из корзины TRC, выбранный пользователем, за вычетом двухпроцентной комиссии. Обналичивание может происходить напрямую через Альянс TRC или через банк-посредник, подобно любой современной валютной операции.

---

### 52. `p1135` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Perhaps the most important difference between the TRC and all previous proposals is the introduction of demurrage. Demurrage provides a powerful incentive for circulation, but also has a built-in mechanism to cover the storage costs of the basket. It thus resolves the biggest problem that previous commodity proposals faced: Who will pay for it all? We believe the TRC mechanism is a win-win approach for all participants in the global trading system, and can succeed where other proposals for monetary innovation have failed.

**В озвучку попало:**

> Пожалуй, самое важное отличие от всех предыдущих проектов — это введение демереджа. Демередж не только создает мощный стимул для обращения валюты, но и содержит встроенный механизм покрытия расходов на хранение товарной корзины. Тем самым он решает главную проблему прошлых товарных предложений: кто за все это будет платить? Мы верим, что механизм торговой эталонной валюты — это подход, выгодный всем участникам глобальной торговой системы, и он может добиться успеха там, где другие денежные инновации потерпели неудачу.

---

### 53. `p1176` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> The intention is that the prefectural government should issue a new ordinance requiring resident households to contribute a certain amount of ‘Biwa Kippu’ environmental activities each year, for example 10 Biwas per family. One Biwa would roughly correspond to one hour of environmental service activities.

**В озвучку попало:**

> [serious] Предполагается, что префектуральное правительство издаст новый указ. Согласно ему, каждое домохозяйство должно будет ежегодно вносить вклад в экологические мероприятия в виде «Бива Киппу» — например, по десять единиц на семью. Один «Бива» будет примерно соответствовать одному часу работы по охране окружающей среды.

---

### 54. `p1177` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> This would be an obligation for every family, but obviously with appropriate exceptions for special circumstances such as people with handicaps or other valid excuses. Biwa Kippu would either be issued by the Prefecture itself or by an appropriate entity such as the Lake Biwa Environmental Research Institute in exchange for undertaking specific, measurable, environmental activities. The Prefecture would determine the scope of these activities each year. Residents or non-profit organisations carrying out these activities would receive Biwa Kippu. The prefectural government would not accept payments in Yen to replace the contributions in Biwa Kippu, nor would it set any exchange rate between Biwa Kippu and Yen. However, residents would be able to exchange Biwa Kippu among themselves on a free local (eBay-type) electronic market.

**В озвучку попало:**

> Это обязательство коснется всех семей, но, разумеется, будут предусмотрены исключения для особых случаев, например, для людей с ограниченными возможностями или по другим уважительным причинам. «Бива Киппу» будут выдаваться самой префектурой или уполномоченной организацией, такой как Исследовательский институт озера Бива, в обмен на конкретные и измеримые экологические работы. Префектура будет ежегодно определять перечень таких мероприятий. Жители или некоммерческие организации, выполняющие эту работу, будут получать «Бива Киппу». Правительство префектуры не будет принимать денежные выплаты в иенах вместо вкладов в «Бива Киппу» и не станет устанавливать курс обмена между ними. Однако жители смогут свободно обмениваться «Бива Киппу» между собой на местном электронном рынке по типу eBay.

---

### 55. `p1236` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The government’s role would be to ensure that fake Civics were not in circulation and that exchanges are transparent and fair. The government would not fix the value of the Civic in terms of national currency. If it wanted the value of the Civics to rise in terms of the national currency, the most effective way would be to require a higher contribution amount payable only in Civics. If it wanted the value to drop, the easiest way would be to reduce the quantities requested.

**В озвучку попало:**

> [thoughtful] Роль правительства заключалась бы в том, чтобы не допускать обращения фальшивых сивиков и следить за прозрачностью и справедливостью обменов. Государство не стало бы фиксировать курс сивика по отношению к национальной валюте. Если бы оно захотело повысить стоимость сивиков, самым эффективным способом было бы увеличение размера обязательного взноса, который принимается только в этой валюте. Если же правительство захотело бы снизить стоимость, проще всего было бы уменьшить требуемое количество сивиков.

---

### 56. `p1252` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> When describing the Civic system, the words ‘money’, ‘currency’ or ‘legal tender ’ were never needed or used. The EU treaty refers to ‘euro banknotes’ and ‘legal tender ’. The Civic does not need the status of ‘legal tender ’ in order to function. It is more cost-effective for the Civic to exist only in electronic form with a mobile phone system as the platform rather than be issued as notes. We will use the word ‘contributions’ when referring to Civics. and reserve the label ‘taxes’ for levies that can only be paid in euros.

**В озвучку попало:**

> При описании системы «Сивик» слова «деньги», «валюта» или «законное платежное средство» не требовались и не использовались. Договор Европейского союза относится именно к «банкнотам евро» и «законному платежному средству». «Сивику» не нужен статус законного платежного средства для функционирования. Экономически выгоднее, чтобы «Сивик» существовал только в электронном виде на базе мобильных телефонов, а не выпускался в виде банкнот. Мы будем использовать термин «взносы» применительно к «Сивикам», а слово «налоги» оставим для платежей, которые можно внести только в евро.

---

### 57. `p1256` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> Figure 1.1 and Appendix A as evidence for this statement.) Because the devastation will unfold over decades, and reducing its likelihood will require collective action by humanity as a whole, this ‘war ’ may also be more difficult to wage than any previous one. It may not have to be so hard if governments require ECOs to win a war against climate change.

**В озвучку попало:**

> Поскольку опустошительные последствия будут нарастать десятилетиями, а предотвращение катастрофы потребует коллективных усилий всего человечества, эта «война» может оказаться сложнее всех предыдущих. Однако задача станет выполнимой, если правительства введут ЭКО как инструмент борьбы с изменением климата.

---

### 58. `p1312` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> For today’s elites, particularly financial elites, revisiting the classic works of Arnold Toynbee⁵ or more recently the writing of Jared Diamond,6 might be useful. Toynbee is the economic historian who demonstrated that the collapse of 21 different civilisations could be attributed to just two causes: too much concentration of wealth and an elite that, confronted with changing circumstances, remains unwilling to shift its priorities until it is too late. Diamond focuses on environmental degradation as a proximate cause for the collapse of civilisations. We are currently pushing the limits on all three causes, at the same time!

**В озвучку попало:**

> [serious] Современным элитам, особенно финансовым, было бы полезно перечитать классические труды Арнольда Тойнби или более современные работы Джареда Даймонда. Экономический историк Тойнби доказал, что крах двадцати одной цивилизации можно объяснить двумя причинами: чрезмерной концентрацией богатства и нежеланием элиты менять свои приоритеты перед лицом меняющихся обстоятельств, пока не станет слишком поздно. Даймонд же делает акцент на разрушении окружающей среды как непосредственной причине гибели цивилизаций. Мы сейчас одновременно доводим до предела все три эти причины.

---

### 59. `p1319` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Exponential growth in population, greenhouse gas emissions or cumulated deficits is mathematically incompatible with sustainability, however the term is defined. However, there also exist ‘good’ non-linearities in the form of dampening mechanisms that can *slow down* growth when and where needed, and stabilise otherwise explosive dynamics. This is what logarithmic or self-slowing growth makes possible. Judicious steering of our current economy requires a subtle combination of positive and negative feedback mechanisms. A monetary ecology is one of the centrepieces of such a combination. Some of the complementary motivation systems described in Chapters VII and VIII offer counter-cyclical stabilisation. Combining several of them may create an economy in which a *global reduction* in environmentally and socially harmful activities is matched with a *local build-up* of ecologically and socially beneficial ones. Sustainable abundance is not generalised poverty – on the contrary, it is generalised prosperity on the basis of a plurality of means of exchange allowing people to gain more awareness and control over their social lives, and over their interactions with the rest of the biosphere.

**В озвучку попало:**

> [serious] Экспоненциальный рост населения, выбросов парниковых газов или накопленных дефицитов математически несовместим с устойчивым развитием, как бы мы ни определяли этот термин. Однако существуют и «полезные» нелинейные процессы — механизмы сдерживания. Они способны замедлять рост там, где это необходимо, и стабилизировать динамику, которая в противном случае стала бы взрывной. Именно это делает возможным логарифмический или самозамедляющийся рост. Разумное управление нашей экономикой требует тонкого сочетания механизмов положительной и отрицательной обратной связи. Денежная экология — один из краеугольных камней такого подхода. Некоторые из дополнительных систем мотивации, описанных в седьмой и восьмой главах, обеспечивают контрциклическую стабилизацию. Их комбинация может создать экономику, в которой глобальное сокращение экологически и социально вредной деятельности будет уравновешено локальным развитием полезных инициатив. Устойчивое изобилие — это не всеобщая бедность. Напротив, это всеобщее процветание, основанное на множестве средств обмена. Они позволяют людям лучше осознавать свою социальную жизнь и контролировать ее, а также влиять на свои взаимодействия с биосферой.

---

### 60. `p1329` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Ultimately, our plea for a monetary ecology is a call for a new mode of economic governance. The aim is to allow two types of economy to coexist peacefully: on the one hand, the mainstream economy will continue to use conventional money in the competitive economy and, on the other hand, the rebirth of a cooperative economy will see regions, cities, neighbourhoods, NGOs and grass-roots citizens’ organisations develop the full potential of their projects without needing to depend on the supply of bank-debt currency.

**В озвучку попало:**

> В конечном счете, наш призыв к денежной экологии — это призыв к новому способу экономического управления. Цель состоит в том, чтобы позволить двум типам экономики мирно сосуществовать. С одной стороны, основная экономика продолжит использовать традиционные деньги в конкурентной среде. С другой — возрождение кооперативной экономики позволит регионам, городам, районам и общественным организациям развивать потенциал своих проектов, не завися от поставок банковской валюты, основанной на долге.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0634` — длина озвучки / длина оригинала: 0.73; классы правки: —

**Исходный абзац:**

> From our perspective, based on the Ecological Economics Paradigm illustrated in Figure 2.3 (page 31), the issue of keeping both inflation and deflation at bay is also relevant, but represents only one of several relevant issues with regards to sustainability.

**В озвучку попало:**

> С нашей точки зрения, основанной на парадигме экологической экономики, задача сдерживания инфляции и дефляции также актуальна, но она представляет собой лишь один из аспектов устойчивости.

---

### 2. `p1041` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> A third option, requiring prudent management, would be for the Savings Company to allow the shares to be ‘cashed in’ for payment in conventional money before reaching maturity. This would be useful to build trust in the system. In situations where immediate cash was required, such as after an accident or disease, or for a wedding, this option would allow an individual or family to address the situation without having to dump the shares at a price below their real value.

**В озвучку попало:**

> Третий вариант требует осторожного управления. Компания могла бы позволить владельцам обменивать акции на обычные деньги до момента их созревания. Это помогло бы укрепить доверие к системе. В экстренных ситуациях, таких как болезнь, несчастный случай или свадьба, это позволило бы семье быстро получить наличные, не продавая акции по заниженной цене.

---

### 3. `p0376` — длина озвучки / длина оригинала: 0.77; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Gowdy & Jon D. Erikson (2005). For a general but exhaustive treatment, see e.g. Molly Scott Cato (2009) and Herman Daly & Joshua Farley (2011). Ecological economics should not be confused with ‘environmental economics’, which was initially part of the Traditional Economics approach and has been a driving force behind the OECD approach shown in Figure 2.2. 9 In this statement, we extend ecological economics into what might be called ‘political ecology’, since traditionally ecological economists emphasise more the embeddedness of the economic within the environmental, and less its embeddedness within the social. However, political ecology and ecological economics are very closely linked, and most ecological economists will have no objection to our graph here.

**В озвучку попало:**

> [serious] Экологическую экономику не следует путать с «экономикой окружающей среды». Последняя изначально была частью традиционного экономического подхода и стала движущей силой стратегии ОЭСР. В этом тексте мы расширяем рамки экологической экономики до того, что можно назвать «политической экологией». Традиционно экологические экономисты делают упор на встроенность экономики в природную среду, уделяя меньше внимания её социальной составляющей. Однако политическая экология и экологическая экономика тесно связаны, и большинство специалистов в этой области согласятся с нашим подходом.

---

### 4. `p0572` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Of perhaps even greater importance, the physics of flow networks also explains why excessively large and efficient organisations may pull the whole system toward collapse. In essence, large, highly efficient organisations in the network ‘out compete’ the smaller organisations for resources, drawing ever more energy, information and resources into the big, and away from the smaller participants.

**В озвучку попало:**

> Возможно, еще важнее то, что физика сетей потоков объясняет, почему чрезмерно крупные и эффективные организации могут привести всю систему к краху. По сути, такие организации в сети «вытесняют» более мелких участников в борьбе за ресурсы, стягивая на себя всё больше энергии, информации и материальных благ.

---

### 5. `p0208` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> For the population at large, perhaps the most important learning needed is to understand non-linearity, specifically the difference between linear and exponential growth. We are now dealing with an increasingly non-linear world. Grasping these different dynamics will be useful in understanding what is happening to us, and what to do about it.

**В озвучку попало:**

> Для широких слоев населения, пожалуй, самое важное — это понимание нелинейности. А именно, разницы между линейным и экспоненциальным ростом. Мы живем во все более нелинейном мире. Осознание этих процессов поможет понять, что с нами происходит и как на это реагировать.

---

### 6. `p0271` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Conceptual relationships between the field of economics and the natural world can be described in three different ways. The most conventional view is to treat anything that is not dealt with unambiguously within one’s own theoretical framework as an ‘externality’ (see Figure 2.1). This economic view defines its own field as completely self-contained and excludes any other consideration as irrelevant. For instance, in such a view, the natural world is reduced to a resource, an input that is considered to be cost-free – to the extent that no money is exchanged to acquire it.

**В озвучку попало:**

> [serious] Концептуальные связи между экономикой и миром природы можно описать тремя способами. Самый распространенный подход — рассматривать всё, что не вписывается в рамки теории, как «внешний фактор». Эта экономическая модель определяет свою область как замкнутую систему, а всё остальное считает неважным. Например, в такой системе мир природы сводится лишь к ресурсам и сырью. Если за их получение не нужно платить деньги, они считаются бесплатными.

---

### 7. `p0095` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> The World Business Academy has long been committed to advancing cutting-edge business information among business executives charged with navigating their businesses through the challenging times we live in. The Academy thank s Bernard Lietaer and his associates for presenting this Report to us, and encourages all levels of government and private enterprises to use the Report to begin a serious conversation on the critical issues the Report illuminates – while there is still time.

**В озвучку попало:**

> World Business Academy давно стремится предоставлять передовую аналитику руководителям, которым приходится вести свои компании через нынешние непростые времена. Академия благодарит Бернара Литера и его коллег за этот доклад. Мы призываем правительственные структуры и частный бизнес использовать его как основу для серьезного разговора о критических проблемах, пока у нас еще есть время.

---

### 8. `p1111` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> The End User returns the TRCs to the TRC Alliance (4a). They are converted either to national currency or a corresponding volume of TRC commodities (which is called ‘taking delivery’ in the commodity market) chosen by the End User, minus the transaction fee of 2%. The cash-in may take place directly with the TRC Alliance or through an intermediary bank, just like any foreign exchange transaction today (4b).

**В озвучку попало:**

> Конечный пользователь возвращает TRC Альянсу. Они конвертируются в национальную валюту или в соответствующий объём товаров из корзины TRC, выбранный пользователем, за вычетом двухпроцентной комиссии. Обналичивание может происходить напрямую через Альянс TRC или через банк-посредник, подобно любой современной валютной операции.

---

### 9. `p1040` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> A second option would be to trade shares for goods or services within the community. The tree shares would thus function as a local medium of exchange and provide some additional liquidity in that community. In principle, the value of the exchange should reflect the value of the tree currency at the time of the exchange, but the owner of the shares and the person accepting them could decide for themselves the most appropriate arrangement.

**В озвучку попало:**

> Второй вариант — использовать акции для оплаты товаров или услуг внутри сообщества. Таким образом, «древесные акции» станут местным средством обмена и обеспечат дополнительную ликвидность. В идеале стоимость такой сделки должна отражать текущую рыночную цену «древесной валюты», но владелец акций и получатель могут договориться об условиях самостоятельно.

---

### 10. `p1251` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> The first question usually raised is whether such a system is legal. Article 104 of the Maastricht treaty and article 128 of the Lisbon treaty specifies “The European Central Bank shall have the exclusive right to authorise the issue of euro banknotes within the Union. The European Central Bank and the national central banks may issue such notes. The banknotes issued by the European Central Bank and the national central banks shall be the only such notes to have the status of legal tender within the Union.”

**В озвучку попало:**

> [serious] Первый вопрос, который обычно возникает: законна ли такая система? Статья 104 Маастрихтского договора и статья 128 Лиссабонского договора гласят, что Европейский центральный банк обладает исключительным правом разрешать выпуск банкнот евро в рамках Союза. Только банкноты, выпущенные Европейским центральным банком и национальными центральными банками, имеют статус законного платежного средства в Союзе.

---

### 11. `p0414` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> A *monetary (or currency) crisis¹⁵* takes place when the currency of a country suddenly suffers a substantial drop in value in relation to other currencies. In order to refer to the three types of crises above using a single word, we will define as a *systemic crisis* any large-scale disturbance involving either a sovereign-debt crisis, a monetary crisis and/or a banking crisis or any combination of those three.

**В озвучку попало:**

> [serious] Валютный кризис происходит, когда национальная валюта внезапно и существенно теряет в стоимости по отношению к другим валютам. Чтобы объединить эти три вида потрясений, мы будем называть системным кризисом любое масштабное событие, включающее в себя кризис суверенного долга, валютный или банковский кризис, либо их сочетание.

---

### 12. `p1226` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> From an economic theory perspective, the Civics approach amounts to a Keynesian stimulus by creating additional demand for services at the city scale. The main difference is that the process is much more bottom-up than the usual central government Keynesian stimulus. Even more importantly: it doesn’t generate any additional debt for anybody. Furthermore, the process can be targeted to specific population segments, and should be countercyclically fine-tuned to local conditions. For instance, specific programmes paid in Civics can be implemented for young people when their unemployment level is abnormally high (as is the case now in Spain, Greece, Ireland, etc.). The contributions requested in Civics should be highest during an economic downturn, and scaled back to zero when close to full employment has been restored. The timing can also be fine-tuned: Civics contributions could be requested on a quarterly basis instead of an annual one, thereby matching more closely real-life conditions. Please remember also that when more Civics contributions are demanded, their value in euros would also increase in the local eBay type market, thereby providing a higher income in euros to the most active participants.

**В озвучку попало:**

> С точки зрения экономической теории, этот подход — своего рода кейнсианский стимул, создающий дополнительный спрос на услуги на уровне города. Главное отличие в том, что процесс идет «снизу вверх», а не навязывается центральным правительством. Важно и то, что система не создает ни у кого дополнительного долга. Кроме того, ее можно настраивать под конкретные группы населения и корректировать в зависимости от ситуации. Например, можно запустить программы для молодежи, если уровень безработицы среди них аномально высок, как это сейчас происходит в Испании, Греции или Ирландии. В периоды спада объем требуемых взносов должен быть максимальным, а при достижении полной занятости его можно снижать до нуля. Сроки внесения взносов можно сделать ежеквартальными, чтобы они лучше соответствовали реалиям жизни. Помните: когда спрос на такие единицы растет, их рыночная стоимость в евро на местной онлайн-площадке также увеличивается, что дает дополнительный доход самым активным участникам.

---

### 13. `p1216` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Another way to fund the labour components in such a project and to strengthen a cooperative local economy in the process is through Civics. The city starts by requiring its residents to make an annual *‘Civics’ contribution*. A Civic is an electronic unit issued by the city that is earned by residents through activities that contribute to the city’s publicly agreed upon aim. The unit of account could be one hour of time, valued at the same rate for everybody. For example, if the aim of a city is to be more green, the activities could include growing food on terraces or rooftops, or taking responsibility for plants and trees in the neighbourhood and parks, or training people in city-based horticulture, and so on. Non-profits would play a key role in the Civics economy by organising the associated activities and verifying the quality and quantity of the work performed. They would actually play in the cooperative economy exactly the same role that businesses play in the competitive economy – the role of initiating projects, organising activities, coordinating and motivating people. A specially-created new type of non-profit would be in charge of auditing all the non-profits involved in this economy to ensure transparency and trust in the system. It would play the role that auditing firms play in the competitive economy, and their reports would be published on the city’s website.

**В озвучку попало:**

> [thoughtful] Еще один способ профинансировать трудозатраты в подобных проектах и одновременно укрепить местную экономику — это внедрение системы «Гражданских единиц». Город вводит ежегодный «гражданский взнос». Это электронная единица, которую город выпускает в обращение, а жители зарабатывают ее, участвуя в общественно полезной деятельности. За единицу можно принять один час работы, причем труд каждого человека оценивается одинаково. Например, если цель города — стать экологичнее, жители могут выращивать продукты на террасах или крышах, ухаживать за парками и деревьями или обучать других городскому садоводству. Ключевую роль здесь играют некоммерческие организации. Они организуют работу, проверяют ее качество и объем. В этой кооперативной экономике они выполняют те же функции, что и бизнес в рыночной среде: запускают проекты, координируют людей и мотивируют их. Чтобы обеспечить прозрачность и доверие, создается специальная надзорная организация. Она проверяет работу всех остальных некоммерческих структур, подобно тому как аудиторские фирмы работают в обычном бизнесе. Отчеты об этих проверках публикуются на городском сайте.

---

### 14. `p1267` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Wide consensus exists in both the scientific and the business world that the development of technologies to switch to a post-carbon world is possible but will require strong governmental leadership. Because many governments will experience a budget squeeze over the next decade, and because government subsidies are the usual way to fund environment conservation and protection measures, many corporations will be left passively waiting for funding to become available before deciding to tackle these issues on their own. The ECO changes this dynamic. In order to wage a war against climate change, governments could require contributions payable only in ECOs, thus giving value to the ECO. As discussed in Chapter V, any fiat currency (including bank-debt money) becomes valuable when a government requires it in payment of fees and taxes. The ECO would also spur serious innovations to reduce climate change.

**В озвучку попало:**

> В научном и деловом мире существует консенсус: переход к пост-углеродному будущему возможен, но требует решительного государственного лидерства. Многие правительства в ближайшее десятилетие столкнутся с бюджетными ограничениями, а поскольку именно субсидии обычно финансируют экологические меры, многие корпорации будут пассивно ждать господдержки, прежде чем самим заняться этими проблемами. ЭКО меняют эту динамику. Чтобы вести войну с изменением климата, правительства могут потребовать уплаты взносов исключительно в ЭКО, тем самым придавая им ценность. Как обсуждалось в пятой главе, любая фиатная валюта становится ценной, когда правительство требует ее для уплаты сборов и налогов. ЭКО также станут мощным стимулом для серьезных инноваций.

---

### 15. `p0942` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> However, many of these existing social purpose systems are intentionally small-scale (e.g. building social capital in a particular neighbourhood), and some of their design features limit their capacity to scale-up to meet the challenges that we can expect to face in the near future. Their function can be compared with that of capillary vessels: they play the important role of keeping us warm and give us a pleasant colour. However, it would be naïve to expect capillary vessels to be able to replace the role of an aorta in the event of a heart attack. To use a different metaphor, in a natural ecosystem, life forms are needed at very different scales: from microbes, earth worms, frogs and rabbits all the way to buffaloes and elephants. Each is vitally important at its own scale. The health of a natural ecosystem depends critically on thriving subsystems at such different scales.

**В озвучку попало:**

> Многие из существующих социальных систем намеренно созданы небольшими, например, для укрепления социальных связей в конкретном районе. Некоторые особенности их устройства ограничивают возможность масштабирования, необходимого для решения будущих проблем. Их функцию можно сравнить с капиллярами: они играют важную роль, согревая нас и придавая здоровый вид. Однако было бы наивно ожидать, что капилляры заменят аорту во время сердечного приступа. Если использовать другую метафору, то в природной экосистеме нужны формы жизни самого разного масштаба: от микробов и дождевых червей до буйволов и слонов. Каждый из них жизненно важен на своем уровне. Здоровье экосистемы критически зависит от процветания подсистем разного масштаба.

---

### 16. `p0982` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> This Dora learning-economy is intended to operate in parallel with the conventional monetary system. We are, therefore, witnessing the beginnings of an exchange media ecosystem. At the end of the first planning session, one of the participants asked the 17-year-old whether he would be willing to teach English and get paid in *Lita* (the Lithuanian national currency), in dollars or in euros. His answer was, “No, I’d prefer to get paid in Dora, because that would get me closer to my dream. These other currencies only would get me the airline ticket!” For this teenager, the Dora had already become a ‘superior currency’, a currency that he preferred over all others. Doraland is an example of a complementary system that encourages non-spontaneous but desirable behaviour patterns. Figure 7.1 summarises the Doraland model in a flow diagram.

**В озвучку попало:**

> [serious] Эта образовательная экономика дор призвана работать параллельно с традиционной денежной системой. Фактически мы наблюдаем зарождение экосистемы обменных средств. В конце первой сессии планирования один из участников спросил того самого 17-летнего юношу, готов ли он преподавать английский за литы, доллары или евро. Он ответил: «Нет, я бы предпочел получить оплату в дорах, потому что это приблизит меня к моей мечте. Другие валюты позволили бы мне купить только билет на самолет!» Для этого подростка дора уже стала «высшей валютой», которую он предпочел всем остальным. Doraland — это пример дополнительной системы, которая поощряет не спонтанные, а осознанные и полезные модели поведения.

---

### 17. `p0993` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Wellness Tokens are specifically designed to use a preventive approach to promote and maintain the good health of participants. Just as ‘Frequent Flyer Miles’ are issued by airline alliances to induce a habit of taking the same airline for all one’s trips, Wellness Tokens would be issued by a Wellness Alliance to induce healthy habits. The members of the Wellness Alliance would be those organisations that have a financial interest in keeping the population healthy (e.g. insurance companies, local government and local employers). One of the purposes of the Wellness Token would be to generate changes in habits towards health promotion and disease prevention by encouraging healthy behaviours and emphasising preventive health care. Such an approach would also be a means of financing supportive care so that the elderly, the chronically ill and the disabled can remain in their own homes, and delay for as long as possible their entry into a long-term medical facility, where the costs escalate.

**В озвучку попало:**

> [serious] Велнес-токены специально разработаны для внедрения профилактического подхода к здоровью. Подобно тому как авиакомпании выпускают бонусные мили, чтобы приучить пассажиров летать именно их рейсами, Велнес-альянс будет выпускать токены для формирования здоровых привычек. В такой альянс войдут организации, финансово заинтересованные в здоровье населения: страховые компании, местные органы власти и работодатели. Одной из целей токенов станет изменение образа жизни через поощрение полезных привычек и акцент на профилактике. Такой подход также позволит финансировать поддерживающий уход на дому для пожилых, хронически больных и людей с ограниченными возможностями. Это поможет им как можно дольше оставаться дома и отсрочить переход в специализированные медицинские учреждения, где стоимость обслуживания резко возрастает.

---

### 18. `p1264` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> In other ways, the ECO system is conceptually similar to the Civic, as illustrated in Figure 8.4. It would start with a governmental authority such as a national government, requiring an annual contribution of ECOs proportional to the total sales volume of each individual corporation. For instance, all corporations would have to contribute 1 ECO for every $1 million of global sales to the government of the country where their headquarters were located.

**В озвучку попало:**

> В остальном система ЭКО концептуально схожа с «Гражданскими». Все начинается с решения государственных органов, например, правительства страны, которое требует от каждой корпорации ежегодных взносов в ЭКО, пропорциональных объему их продаж. Например, компании могли бы вносить один ЭКО на каждый миллион долларов глобальной выручки в бюджет страны, где находится их штаб-квартира.

---

### 19. `p1010` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> For the preventive care providers, the Wellness Token could function as a loyalty currency by attracting customers who might otherwise not patronise them. From a purely financial viewpoint, the role of a loyalty currency is to ensure that the value to the business generated by an exchange is always larger than the marginal cost in conventional money of serving an additional customer. The most logical participants are therefore businesses with comparatively low marginal costs. This is the case for many preventive health care providers. Some businesses have virtually no marginal monetary costs – think, for example, of a massage therapist who is not fully booked. But even a restaurant, for example, typically has marginal costs of about one third of its customers’ bills. This means that only one third of what customers spend pays for the food itself. There is usually another third that goes to fixed costs: renting the location, heating the room, paying the staff, etc. The final third is profit. Therefore, as long as a restaurant would not otherwise be full, it makes economic sense to bring in additional customers who pay partly in conventional money and partly in complementary currency.

**В озвучку попало:**

> Для поставщиков профилактических услуг велнес-токен работает как валюта лояльности, привлекая клиентов, которые иначе могли бы к ним не обратиться. С чисто финансовой точки зрения, такая валюта эффективна, если выгода от сделки превышает предельные затраты в обычных деньгах на обслуживание нового клиента. Логичнее всего участвовать в программе компаниям с относительно низкими предельными издержками. Это характерно для многих центров профилактики. У некоторых из них дополнительные денежные затраты на клиента практически равны нулю — например, у массажиста, чей график не заполнен полностью. Но даже у ресторана предельные издержки составляют около трети от чека. Это значит, что лишь треть суммы уходит на продукты. Еще треть обычно покрывает постоянные расходы: аренду, отопление, зарплату персонала. Последняя треть — это прибыль. Поэтому, если ресторан не заполнен, ему выгодно привлекать дополнительных клиентов, которые платят частично обычными деньгами, а частично — дополнительной валютой.

---

### 20. `p0379` — длина озвучки / длина оригинала: 0.84; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> USA, where he was acknowledged as Distinguished Fellow of the American Economic Association. He made significant contributions in both conventional economics (utility theory, input-output analysis, production theory) and in paradigm-shifting economics – what along the lines of Thomas Kuhn might be labelled ‘revolutionary’ economics. He applied rigorous systemic thinking on how to link economics to the physical laws of sustainability in *Analytical Economics* (1966). Paul Samuelson said in the Preface that he considered Georgescu-Roegen to be “a scholar’s scholar, and an economist’s economist”. He added: “I defy any informed economist to remain complacent after meditating over this essay”. Nevertheless, complacency is what has greeted that book and its successor, *The Entropy Law and the Economic Process*. Ecological economist Herman Daly concludes in his ‘Obituary Essay on Georgescu-Roegen’: “One does not expect fundamental change to occur overnight. But twenty-five years is a reasonable time over which to hope for progress. What is the matter with our discipline?” (Daly [1996] p.192 and p.198). Even Samuelson himself, for all his professed lack of complacency, never updated his bestselling economics textbooks to integrate Georgescu-Roegen’s findings. Even 30 years before Georgescu-Roegen, Frederick Soddy, a Nobel laureate in Chemistry, had drawn the attention of economists to their ignorance of entropy and the unsustainability of compound interest, all without success. 14 Orio Giarini ‘Science and Economy: The Case of Uncertainty and Disequilibrium’ *Cadmus,* Vol I, No.2 (April 2011) pp.25-34. 15 Hazel Henderson: *Paradigms in Progress: Life beyond Economics* (1991). See also Hazel Henderson: *Creating Alternative*

**В озвучку попало:**

> [serious] Николас Джорджеску-Реген родился в Румынии, но большую часть академической карьеры провел в США, в университете Вандербильта, где был признан почетным членом Американской экономической ассоциации. Он внес значительный вклад как в традиционную экономику, так и в экономику, меняющую парадигму, которую в духе Томаса Куна можно назвать «революционной». В своей работе «Аналитическая экономика» он применил системный подход, чтобы связать экономическую теорию с физическими законами устойчивого развития. Пол Самуэльсон в предисловии к этой книге назвал Джорджеску-Регена «ученым для ученых и экономистом для экономистов». Он добавил: «Я бросаю вызов любому информированному экономисту: попробуйте остаться спокойными после размышлений над этим эссе». Тем не менее, именно спокойствие стало реакцией на эту книгу и её продолжение — «Закон энтропии и экономический процесс». Экологический экономист Герман Дейли в своем некрологе писал: «Не стоит ожидать, что фундаментальные перемены произойдут в одночасье. Но двадцать пять лет — это разумный срок, чтобы надеяться на прогресс. Что же не так с нашей дисциплиной?» Даже сам Самуэльсон, несмотря на свои слова, так и не обновил свои бестселлеры по экономике, чтобы включить в них выводы Джорджеску-Регена. Еще за тридцать лет до него Фредерик Содди, лауреат Нобелевской премии по химии, безуспешно пытался обратить внимание экономистов на их игнорирование законов энтропии и неустойчивость сложных процентов.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0605` — длина озвучки / длина оригинала: 1.27; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Should we not learn from nature that growing to the point of becoming ‘too big to fail’ should never be allowed to happen? Instead, in the USA, the ten largest banks now control 42% of the market, compared to 28% before the 2008 crisis. This pattern is the perfect demonstration of what are known as ‘autocatalytic forces’ in natural ecosystems – forces that automatically lead to systemic crashes.

**В озвучку попало:**

> [serious] Не пора ли нам поучиться у природы и понять, что нельзя позволять компаниям разрастаться до статуса «слишком больших, чтобы обанкротиться»? В Соединенных Штатах десять крупнейших банков сегодня контролируют сорок два процента рынка, хотя до кризиса две тысячи восьмого года этот показатель составлял двадцать восемь процентов. Такая тенденция — наглядная демонстрация того, что в природных экосистемах называют автокаталитическими силами. Это процессы, которые неизбежно ведут к системным крахам.

---

### 2. `p0715` — длина озвучки / длина оригинала: 1.24; классы правки: —

**Исходный абзац:**

> Yet we are being told that we still owe about $28 billion. That $28 billion came about because of the foreign creditors’ interest rates. If you ask me what is the worst thing in the world, I would say it is compound interest.” At the time Obasanjo spoke out, the developing world was spending $13 on debt repayment for every one dollar it had received in foreign aid and grants. For the sixty poorest countries in the world, $550 billion have been paid in both principal and interest over the last three decades on a total of $540 billion of loans, and yet there are still $523 billion outstanding in debt burden.

**В озвучку попало:**

> «И всё же нам говорят, что мы всё ещё должны около двадцати восьми миллиардов. Эта сумма возникла из-за процентных ставок иностранных кредиторов. Если спросить меня, что на свете хуже всего, я отвечу: это сложные проценты». В то время, когда Обасанджо сделал это заявление, развивающиеся страны тратили тринадцать долларов на погашение долгов на каждый один доллар, полученный в виде иностранной помощи и грантов. За последние три десятилетия шестьдесят беднейших стран мира выплатили в общей сложности пятьсот пятьдесят миллиардов долларов в качестве основной суммы долга и процентов по кредитам, общая сумма которых составляла пятьсот сорок миллиардов. И при этом у них всё ещё остаётся невыплаченный долг в размере пятисот двадцати трёх миллиардов долларов.

---

### 3. `p0430` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> In 2010, the US Census Bureau reported 4 million additional Americans in poverty, making a total of 44 million, or one in every seven residents. The rise was steepest for children, with one in five children affected.²¹ Because the crisis started later in Europe than in the USA, the full impact on poverty in Europe has not yet been fully documented.

**В озвучку попало:**

> В 2010 году Бюро переписи населения США сообщило об увеличении числа бедных американцев на 4 миллиона человек. Общее число достигло 44 миллионов, то есть каждый седьмой житель страны оказался за чертой бедности. Рост был наиболее заметным среди детей: пострадал каждый пятый ребенок. Поскольку кризис в Европе начался позже, чем в США, его полное влияние на уровень бедности в европейских странах еще не до конца задокументировано.

---

### 4. `p0161` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> The bailouts, followed by a large-scale Keynesian stimulus plan to avoid a deflationary depression, have resulted in enormous budget deficits and additional public debt. In the twenty-three countries most directly affected by the banking crash, government debt jumped by an average of 24% of GDP.

**В озвучку попало:**

> [thoughtful] Спасение банков, за которым последовал масштабный кейнсианский план стимулирования для предотвращения дефляционной депрессии, привело к огромным бюджетным дефицитам и росту государственного долга. В двадцати трех странах, наиболее пострадавших от банковского краха, госдолг вырос в среднем на двадцать четыре процента от валового внутреннего продукта.

---

### 5. `p0338` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> The reference material for our analysis in this Report also includes the work known as ‘The Natural Step’, by Karl-Henrik Robert, a physician from Sweden who started by researching the systemic reasons for the escalating cancer rates in his medical practice. The Natural Step offers four system conditions that must be met for a sustainable world:

**В озвучку попало:**

> [thoughtful] В качестве справочного материала для нашего анализа мы также используем работу под названием «Естественный шаг», автором которой является шведский врач Карл-Хенрик Роберт. Он начал свои исследования, пытаясь понять системные причины роста заболеваемости раком, с которыми сталкивался в своей медицинской практике. «Естественный шаг» предлагает четыре системных условия, необходимых для устойчивого развития мира.

---

### 6. `p0288` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> The clear difference between Figures 2.1 and 2.3 is that the latter contains *no* ‘externalities’. What was considered an externality in Figure 2.1 is the context in which economic activities take place. This context contains overarching rules such as entropy that must be taken into account by economics to avoid getting lost in an ‘autistic’ or ‘fantasy’ world.

**В озвучку попало:**

> [serious] Главное отличие между вторым рисунком один и вторым рисунком три заключается в том, что на последнем нет никаких «внешних эффектов». То, что раньше считалось внешним фактором, теперь становится контекстом, в котором протекает вся экономическая деятельность. Этот контекст включает в себя фундаментальные законы, например, закон энтропии. Экономика обязана учитывать их, чтобы не оказаться в вымышленном, оторванном от реальности мире.

---

### 7. `p0060` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> The CoR-EU is indebted to the World Academy of Art and Science, represented by Ivo Šlaus, President, and Garry J acobs, Chair of the Board and CEO, as well as to Felix U nger, President of the European Academy of Sciences and Arts for supporting this Report by co-signing these brief preliminary remark s.

**В озвучку попало:**

> Европейское отделение Римского клуба выражает признательность Всемирной академии искусств и науки в лице президента Иво Шлауса и председателя совета директоров и генерального директора Гарри Джейкобса. Мы также благодарим Феликса Унгера, президента Европейской академии наук и искусств, за поддержку этого доклада и соавторство в этих кратких вступительных замечаниях.

---

### 8. `p0745` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> We have found only one study of the transfer of wealth via interest. It was performed in Germany in 1982 when interest rates were at 5.5%.²⁸ The German population was grouped into ten income categories of 2.5 million households each. Over a one-year period, transfers between these ten groups totalled Deutsche Mark (DM) 270 billion in interest paid and received. Graphing the net interest transfers (interest gained minus interest paid) for each of these ten household categories allows us to see the net effect (see Figure 5.5).

**В озвучку попало:**

> [thoughtful] Нам удалось найти лишь одно исследование, посвященное перераспределению богатства через процентные ставки. Оно было проведено в Германии в 1982 году, когда процентная ставка составляла пять с половиной процентов. Все население страны разделили на десять групп по уровню дохода, в каждой из которых было по два с половиной миллиона домохозяйств. За один год общая сумма выплаченных и полученных процентов составила двести семьдесят миллиардов немецких марок. Если построить график чистого перераспределения — то есть разницы между полученными и выплаченными процентами — для каждой из этих групп, мы увидим реальный эффект.

---

### 9. `p1283` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> Poverty is caused as much by lack of appropriate savings tools as by lack of income. A widely held prejudice that the poor do not have the desire or capacity to save is false; it turns out that the demand for secure and convenient saving services is often stronger among the poor than the demand for credit services.⁸ This has been confirmed numerous times by empirical evidence, particularly from studies in the field of micro-finance.⁹ Natural Savings provides a better savings instrument than any savings account, and it is able to deal with very small sums.

**В озвучку попало:**

> [serious] Бедность вызвана не только нехваткой доходов, но и отсутствием подходящих инструментов для сбережений. Широко распространенное предубеждение о том, что у бедных нет желания или возможности откладывать деньги, ошибочно. На деле спрос на надежные и удобные услуги по сбережению средств среди малообеспеченных слоев населения часто оказывается выше, чем спрос на кредитные услуги. Это многократно подтверждалось эмпирическими данными, особенно в исследованиях сферы микрофинансирования. Система «Естественных сбережений» предлагает более эффективный инструмент накопления, чем любой обычный сберегательный счет, и позволяет работать даже с очень небольшими суммами.

---

### 10. `p0057` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> At the time of writing these remark s we witness the dismantling of the state as guarantor of public good. Almost everything is for sale in most EU countries. Austerity is imposed at all levels. Public unrest will continue to grow unless new governance structures replace the obsolete ones.

**В озвучку попало:**

> [serious] В то время, когда пишутся эти строки, мы наблюдаем, как государство перестает быть гарантом общественного блага. Почти всё в большинстве стран Европейского союза выставлено на продажу. Повсюду вводится режим жесткой экономии. Общественное недовольство будет только расти, если на смену устаревшим структурам управления не придут новые.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта. Совпадение здесь остаётся низким (16–26 %), потому что это перевод: полностью нетронутых абзацев среди них НЕТ. Абзацы, которые действительно остались английскими, вынесены в следующий раздел — они пришли в артефакт мимо ответа модели.

### 1. `p1285` — совпадение символов с оригиналом: 26%; классы правки: —

**Исходный абзац:**

> Systems like Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu, and Civics provide environments for people who otherwise would never meet to work together on projects that develop their gifts and the health and strength of their community. If people are given a powerful voice on which projects are chosen, these systems can rebuild and strengthen social capital over time.

**В озвучку попало:**

> Системы вроде Doraland, Wellness Tokens, Natural Savings, Torekes, Biwa Kippu и Civics создают условия, в которых люди, иначе никогда бы не встретившиеся, могут вместе работать над проектами. Такие инициативы развивают таланты участников, укрепляют здоровье и сплоченность сообщества. Если люди получают реальное право голоса при выборе проектов, подобные системы способны со временем восстановить и значительно укрепить социальный капитал.

---

### 2. `p0929` — совпадение символов с оригиналом: 19%; классы правки: truncated_sentence

**Исходный абзац:**

> Footnotes 1 John Kenneth Galbraith, *Money: Whence It Came, Where It Went* (1975), p.5. 2 For instance, the Natural Savings instrument presented in Chapter VII would mainly be a savings tool, not a medium of exchange or unit of account. In many civilisations, the unit of account was also different from the medium of exchange. A case in point is Homeric Greece, where the unit of account was the ox but where, for the sake of convenience, actual exchanges were often performed with ingots of bronze or other commodities. 3 For the arguments offered in this paragraph, see Philippe Derudder and André-Jacques Holbecq (2008) p.17. 4 Friedrich Nietzsche, *Thus Spoke Zarathustra,* translated by Adrian del Caro and edited by Robert Pippin (2006). 5 The original is elegantly succinct: *“Nervos belli, pecuniam infinitam”* from Cicero’s *Fifth* *Philippic.* See Jon Hall, *The Philippics*, in

**В озвучку попало:**

> Примечания. 1. Джон Кеннет Гэлбрейт, «Деньги: откуда они берутся и куда уходят» (1975), стр. 5. 2. Например, инструмент «Природные сбережения», представленный в седьмой главе, был бы преимущественно сберегательным инструментом, а не средством обмена или расчетной единицей. Во многих цивилизациях расчетная единица отличалась от средства обмена. Показательный пример — гомеровская Греция, где расчетной единицей был бык, но для удобства реальные обмены часто совершались с помощью бронзовых слитков или других товаров. 3. Аргументы, приведенные в этом абзаце, см. в работе Филиппа Дерудера и Андре-Жака Ольбека (2008), стр. 17. 4. Фридрих Ницше, «Так говорил Заратустра», перевод Адриана дель Каро под редакцией Роберта Пиппина (2006). 5. Оригинал лаконичен и изящен: «Nervos belli, pecuniam infinitam» из Пятой филиппики Цицерона. См. Джон Холл, «Филиппики», в

---

### 3. `p0438` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> This, in turn, sets the scene for further rounds of banking problems. Because all IMF data are based on government statistics provided by the countries involved, the comprehensiveness of this data is debatable. One exception is the case study of the 2007-2008 US banking crash.

**В озвучку попало:**

> Это, в свою очередь, создает почву для новых витков банковских проблем. Поскольку все данные Международного валютного фонда основаны на государственной статистике соответствующих стран, полнота этих данных вызывает вопросы. Исключением является тематическое исследование банковского краха в США в 2007–2008 годах.

---

### 4. `p1359` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Gwendolyn Hallsmith contributed many substantial ideas for Chapters II and VII. Sherry Cox has contributed clarity to all chapters. Last but not least, Stephanie Taché managed to incorporate a feminine sensitivity to what would otherwise be a heavier Report. The illustrations were produced with help from Thibault d’Ursel. Finally, Andrew Carey and Alison Melvin from Triarchy Press helped publish this book in record time, without compromising on quality.

**В озвучку попало:**

> Гвендолин Холлсмит внесла множество важных идей для второй и седьмой глав. Шерри Кокс помогла сделать текст всех глав более ясным. И наконец, Стефани Таше сумела привнести в доклад женскую чуткость, которая сделала его менее сухим. Иллюстрации были созданы при участии Тибо д’Урселя. Мы также благодарим Эндрю Кэри и Элисон Мелвин из издательства Triarchy Press, которые помогли выпустить эту книгу в рекордные сроки, не поступившись качеством.

---

### 5. `p0394` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> The global monetary system seems to run on automatic pilot. What’s more, the current global foreign exchange market dwarfs all other markets in history. By 2010, foreign exchange volumes had routinely reached the equivalent of $4 trillion *every working day.*¹

**В озвучку попало:**

> [serious] Глобальная денежная система, кажется, работает на автопилоте. Более того, нынешний мировой валютный рынок затмевает все остальные рынки в истории. К 2010 году объем валютных операций регулярно достигал эквивалента четырех триллионов долларов каждый рабочий день.

---

### 6. `p0979` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> For example, one 17-year-old at the Vilnius event had the dream of learning Buddhism in the mountains of Burma. The Doraland Foundation would contractually promise to make this experience possible in exchange for 3,000 Doras. Doraland would not only raise the funds — through sponsorships and donations — to purchase the airline ticket payable in national currency, but also arrange for the necessary contacts in Burma. The teenager could earn 3,000 Doras by teaching 300 hours of conversational English to others, for example, or perhaps by training adults wanting to acquire computer skills. Another young person wanted to spend a weekend with her hero, a Nobel laureate in physics. In exchange for 2,000 Doras or the equivalent of 200 hours of teaching an art skill, the Foundation would facilitate the meeting with the physicist. Another group might want to learn to sail around the world or to create a neighbourhood greenhouse for year-round food production. The media attention attracted by these endeavours will help to raise sponsorships and donations and can also help generate more creative and socially useful dreams, as well as more offers to teach/train a range of skills.

**В озвучку попало:**

> [thoughtful] Например, один 17-летний участник встречи в Вильнюсе мечтал изучать буддизм в горах Бирмы. Фонд Doraland мог бы заключить с ним договор: фонд берет на себя организацию поездки в обмен на 3000 дор. Организация не только нашла бы средства через спонсоров и пожертвования на покупку авиабилета за национальную валюту, но и обеспечила бы необходимые контакты в Бирме. Подросток мог бы заработать эти 3000 дор, например, преподавая разговорный английский в течение 300 часов или обучая взрослых компьютерной грамотности. Другая девушка хотела провести выходные со своим кумиром — лауреатом Нобелевской премии по физике. В обмен на 2000 дор, что эквивалентно 200 часам преподавания искусства, фонд помог бы организовать встречу с ученым. Другие группы могли бы захотеть научиться кругосветному плаванию или создать общественную теплицу для круглогодичного выращивания продуктов. Внимание СМИ к таким проектам поможет привлечь спонсоров и создать новые, еще более творческие и полезные для общества идеи.

---

### 7. `p1287` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Another way to understand what an economic ecosystem would look like is to imagine what would currently be different if some of the solutions we are proposing had been well established before the 2007-2008 crisis. The C3 system would have reduced the level of unemployment resulting from the crisis. Civics would have empowered municipal governments to address their social and environmental challenges even with shrinking bank-debt money budgets. Together they would have provided an effective choice of tools to generate healthy local and regional economies.

**В озвучку попало:**

> [thoughtful] Чтобы понять, как могла бы выглядеть экономическая экосистема, представьте, что было бы, если бы некоторые из предлагаемых нами решений уже работали до кризиса 2007–2008 годов. Система C3 помогла бы снизить уровень безработицы, вызванный тем кризисом. Civics позволил бы муниципальным властям решать социальные и экологические задачи даже в условиях сокращения бюджетного финансирования, зависящего от банковских кредитов. Вместе эти инструменты дали бы эффективную возможность для создания здоровой местной и региональной экономики.

---

### 8. `p1138` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> As explained at the beginning of this chapter, we are not elaborating on those useful and highly relevant systems here because they have already been described in detail elsewhere. They obviously could, and should, be part of an emergent monetary ecosystem.

**В озвучку попало:**

> Как мы объяснили в начале главы, мы не стали подробно останавливаться на этих полезных и важных системах, так как они уже были детально описаны в других источниках. Разумеется, они могли бы и должны стать частью формирующейся денежной экосистемы.

---

### 9. `p0054` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> It made sense also to address the business community at large. We are delighted that the *World Business Academy*, a non-profit think -tank and network of business leaders, agreed to be a second recipient of our Report. Its mission is to inspire and help business assume responsibility for the whole of society, exploring its role in relation to critical moral, environmental and social dilemmas. Its objectives are to change business leaders’ consciousness from self-service to servant leadership as well as to change the behaviour of the public at large, so it spends its money where its values are.

**В озвучку попало:**

> Было логично обратиться и к деловому сообществу в целом. Мы рады, что World Business Academy, некоммерческий аналитический центр и сеть бизнес-лидеров, согласилась стать вторым получателем нашего доклада. Их миссия — вдохновлять бизнес брать на себя ответственность за общество в целом, исследуя свою роль в решении критических моральных, экологических и социальных дилемм. Их цель — изменить сознание бизнес-лидеров, перейдя от эгоцентризма к служению обществу, а также изменить поведение потребителей, чтобы они направляли свои средства туда, где важны их ценности.

---

### 10. `p0409` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> To provide more detailed evidence for this argument, we will look at systemic crises, their frequency, types and geographical spreads. We will then probe the consequences of a financial or monetary crisis. Finally, we will take a critical look at privatisation as the solution within the current – and, in our view, defective – monetary paradigm.

**В озвучку попало:**

> Чтобы подкрепить этот аргумент более детальными доказательствами, мы рассмотрим системные кризисы, их частоту, типы и географический охват. Затем мы проанализируем последствия финансовых и валютных потрясений. Наконец, мы критически взглянем на приватизацию как на предлагаемое решение в рамках текущей — и, на наш взгляд, порочной — денежной парадигмы.

---
## Абзацы, оставшиеся в озвучке на английском (25)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Они не могли попасть в разделы выше: пайплайн отбраковал русский ответ модели для этих блоков (`controlled_fallback: source_text_fallback`, 6 блоков по учёту прогона; `model_output_discarded_reason_counts.marker_validation_source_fallback = 6`) и вернул на их место исходный текст. Цитируется сам артефакт `.tts.txt`.

### 1. `narration#509` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> “For plants and animals, information about the environment is stored in genes. Plants and animals have adapted to a specifi c environment. This adaptation takes place through natural selection. The plants and animals selected are those capable of most rapidly and effectively dissipating energy. By doing this, a living being changes its environment. As the environment changes, its genes are no longer adapted. This living being needs to evolve again. To remain in harmony with the environment which it is making evolve, a living being needs to adapt with greater speed. After atoms and molecules, living beings increase in complexity. Those most adept at dissipating energy are the ones that invariably win. “Geothermal energy dissipates not gradually but suddenly, in the form of earthquakes. The same is true with life. Plant and animal ecosystems develop quickly and collapse suddenly, to be replaced by more evolved populations that can better dissipate energy. The Australopithecus species disappeared along with all other humanoid species except for our own, initially because of the domestication of fire and the cooking of food. “From the Neolithic onwards, information about the environment previously only stored in genes started to be stored in the human brain. From this point on, the human brain controls the evolution of humanity. The English zoologist Richard Dawkins has proposed to call ‘memes’ information stored in human brains, by analogy to ‘genes’. For humanity, memes replace genes with notable consequences. Humans start sharing the same memes thereby creating a new type of dissipative structure. Different human societies emerge. …The development of economies is nothing more than the elaboration of the dissipation of energies through structures that have become human societies. “I am convinced that Dewar’s results will become the pillar of a new economic science once economists become aware of its implications. During the 17th century, England, as the most advanced mimetic society of the time, was the first to limit the powers of monarchy. France followed suit during the eighteenth century. Because absolutist monarchy limited the development of economies, it was doomed to disappear. During the nineteenth century, European nations - at that time still different mimetic societies - entered into competition with one another. The consequences of this during the twentieth century included two world wars and a Great Depression. “At the end of the second war, two big ideologies, capitalism and communism, remained and entered into conflict. The memes of the free economy eventually ended up spreading into the USSR. Because the Soviet economy was developing more slowly, it collapsed. Humanity as a whole now dissipates 2kW/kg per person. An average Frenchman dissipates 6kW/kg/person, an average American 10kW/kg/person. By dissipating energy in this way, the economy is rapidly modifying its environment (exhaustion of oil reserves, pollution, etc.), and social inequalities are being exacerbated. “Physics and biology show us where this leads: the extinction of species and the end of civilisations. Biology has demonstrated how our genes are continuously forced to evolve. We now realise that the same is true with our memes. They, too, have to evolve. No isolated individual can unilaterally reduce its energy dissipation without taking the risk of being eliminated by natural selection. Similarly, no country or isolated civilisation can unilaterally limit its economic development. “The only hope is a change of consciousness on a global level – the realisation of the need for a new meme: the need to reduce our energy consumption on a planetary scale. Such a change is starting to occur because, for the very first time, the degradation of the environment is visible within the time span of one generation – the sign of a seismic environmental shift on a global level. Hence the urgent call for sustainable development. While trying to save a planet which could not care less, we may be able to save humanity.”

**В озвучку попало:**

> “For plants and animals, information about the environment is stored in genes. Plants and animals have adapted to a specifi c environment. This adaptation takes place through natural selection. The plants and animals selected are those capable of most rapidly and effectively dissipating energy. By doing this, a living being changes its environment. As the environment changes, its genes are no longer adapted. This living being needs to evolve again. To remain in harmony with the environment which it is making evolve, a living being needs to adapt with greater speed. After atoms and molecules, living beings increase in complexity. Those most adept at dissipating energy are the ones that invariably win. “Geothermal energy dissipates not gradually but suddenly, in the form of earthquakes. The same is true with life. Plant and animal ecosystems develop quickly and collapse suddenly, to be replaced by more evolved populations that can better dissipate energy. The Australopithecus species disappeared along with all other humanoid species except for our own, initially because of the domestication of fire and the cooking of food. “From the Neolithic onwards, information about the environment previously only stored in genes started to be stored in the human brain. From this point on, the human brain controls the evolution of humanity. The English zoologist Richard Dawkins has proposed to call ‘memes’ information stored in human brains, by analogy to ‘genes’. For humanity, memes replace genes with notable consequences. Humans start sharing the same memes thereby creating a new type of dissipative structure. Different human societies emerge. …The development of economies is nothing more than the elaboration of the dissipation of energies through structures that have become human societies. “I am convinced that Dewar’s results will become the pillar of a new economic science once economists become aware of its implications. During the 17th century, England, as the most advanced mimetic society of the time, was the first to limit the powers of monarchy. France followed suit during the eighteenth century. Because absolutist monarchy limited the development of economies, it was doomed to disappear. During the nineteenth century, European nations - at that time still different mimetic societies - entered into competition with one another. The consequences of this during the twentieth century included two world wars and a Great Depression. “At the end of the second war, two big ideologies, capitalism and communism, remained and entered into conflict. The memes of the free economy eventually ended up spreading into the USSR. Because the Soviet economy was developing more slowly, it collapsed. Humanity as a whole now dissipates 2kW/kg per person. An average Frenchman dissipates 6kW/kg/person, an average American 10kW/kg/person. By dissipating energy in this way, the economy is rapidly modifying its environment (exhaustion of oil reserves, pollution, etc.), and social inequalities are being exacerbated. “Physics and biology show us where this leads: the extinction of species and the end of civilisations. Biology has demonstrated how our genes are continuously forced to evolve. We now realise that the same is true with our memes. They, too, have to evolve. No isolated individual can unilaterally reduce its energy dissipation without taking the risk of being eliminated by natural selection. Similarly, no country or isolated civilisation can unilaterally limit its economic development. “The only hope is a change of consciousness on a global level – the realisation of the need for a new meme: the need to reduce our energy consumption on a planetary scale. Such a change is starting to occur because, for the very first time, the degradation of the environment is visible within the time span of one generation – the sign of a seismic environmental shift on a global level. Hence the urgent call for sustainable development. While trying to save a planet which could not care less, we may be able to save humanity.”

---

### 2. `narration#717` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Once upon a time, in a small village in the Outback , people used barter for all their transactions. On every mark et day, people walk ed around with chick ens, eggs, hams, and breads, and engaged in prolonged negotiations among themselves to exchange what they needed. At k ey periods of the year, such as during harvests or when someone’s barn required big repairs after a storm, people recalled the tradition of helping each other out, brought from the old country. They k new that if they had a problem someday, others would help them in return. One mark et day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral the six chick ens he wanted to exchange for a big ham, he could not refrain from laughing. “Poor people”, he said, “so primitive”. The farmer’s wife overheard him and challenged the stranger, “Do you think you can do a better job handling chick ens?” “Chick ens, no”, responded the stranger, “But there is a much better way to eliminate all that hassle. “Oh yes, how so?” ask ed the woman. “See that tree there?” the stranger replied. “Well, I will go wait there for one of you to bring me one large cowhide. Then have every family visit me. I’ll explain the better way.” And so it happened. He took the cowhide, and cut perfect leather rounds in it, and put an elaborate and graceful little stamp on each round. Then he gave to each family 10 rounds, and explained that each represented the value of one chick en. “Now you can trade and bargain with the rounds instead of the unwieldy chick ens”, he explained. It made sense. Everybody was impressed with the man with the shiny shoes and inspiring hat. “Oh, by the way”, he added after every family had received their 10 rounds, “in a year’s time, I will come back and sit under that same tree. I want you to each bring me back 11 rounds. That 11th round is a tok en of appreciation for the technological improvement I just made possible in your lives.” “But where will the 11th round come from?” ask ed the farmer with the six chick ens. “You’ll see”, said the man with a reassuring smile.

**В озвучку попало:**

> Once upon a time, in a small village in the Outback , people used barter for all their transactions. On every mark et day, people walk ed around with chick ens, eggs, hams, and breads, and engaged in prolonged negotiations among themselves to exchange what they needed. At k ey periods of the year, such as during harvests or when someone’s barn required big repairs after a storm, people recalled the tradition of helping each other out, brought from the old country. They k new that if they had a problem someday, others would help them in return. One mark et day, a stranger with shiny black shoes and an elegant white hat came by and observed the whole process with a sardonic smile. When he saw one farmer running around to corral the six chick ens he wanted to exchange for a big ham, he could not refrain from laughing. “Poor people”, he said, “so primitive”. The farmer’s wife overheard him and challenged the stranger, “Do you think you can do a better job handling chick ens?” “Chick ens, no”, responded the stranger, “But there is a much better way to eliminate all that hassle. “Oh yes, how so?” ask ed the woman. “See that tree there?” the stranger replied. “Well, I will go wait there for one of you to bring me one large cowhide. Then have every family visit me. I’ll explain the better way.” And so it happened. He took the cowhide, and cut perfect leather rounds in it, and put an elaborate and graceful little stamp on each round. Then he gave to each family 10 rounds, and explained that each represented the value of one chick en. “Now you can trade and bargain with the rounds instead of the unwieldy chick ens”, he explained. It made sense. Everybody was impressed with the man with the shiny shoes and inspiring hat. “Oh, by the way”, he added after every family had received their 10 rounds, “in a year’s time, I will come back and sit under that same tree. I want you to each bring me back 11 rounds. That 11th round is a tok en of appreciation for the technological improvement I just made possible in your lives.” “But where will the 11th round come from?” ask ed the farmer with the six chick ens. “You’ll see”, said the man with a reassuring smile.

---

### 3. `narration#747` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Far from being the behaviourally neutral and purely facilitative exchange tool that the Traditional Economics paradigm assumes, the conventional monetary system acts as a large-scale, unconscious programming tool. It generates five processes that directly conflict with various dimensions of sustainability. Today’s monetary system combines a pro-cyclical money supply with deregulated capital flows, and uncontrolled speculative incentives. Furthermore, this money is created with built-in compound interest that makes growth obligatory and renders the concentration of wealth automatic. None of these features is a law of nature. They are all conventions that can be systemically counter-balanced by other systems to neutralise these effects.

**В озвучку попало:**

> Far from being the behaviourally neutral and purely facilitative exchange tool that the Traditional Economics paradigm assumes, the conventional monetary system acts as a large-scale, unconscious programming tool. It generates five processes that directly conflict with various dimensions of sustainability. Today’s monetary system combines a pro-cyclical money supply with deregulated capital flows, and uncontrolled speculative incentives. Furthermore, this money is created with built-in compound interest that makes growth obligatory and renders the concentration of wealth automatic. None of these features is a law of nature. They are all conventions that can be systemically counter-balanced by other systems to neutralise these effects.

---

### 4. `narration#748` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Before we can consider what form such adaptations could take, we still must elucidate perhaps the most sensitive topic of all: the role of power with regards to money. This is the topic of the next chapter.

**В озвучку попало:**

> Before we can consider what form such adaptations could take, we still must elucidate perhaps the most sensitive topic of all: the role of power with regards to money. This is the topic of the next chapter.

---

### 5. `narration#749` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, No Logo: Taking Aim at the Brand Bullies (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in The Economist January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see The Economist, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary Policy’, American Economic Review, vol. 68 (1968), pp.1–17. We are not claiming that this process is the only cause of the business cycle, but that it is a contributing factor directly attributable to the prevailing monetary system. See Olivier J. Blanchard & Mark W. Watson (1987). See also ‘Shadow Government Statistics’ at 6 See Milton Friedman & Anna Jacobson Schwartz (1993); J. P. Keeler (2001); Barry Eichengreen & K. Mitchener (2003); Carmen

**В озвучку попало:**

> Footnotes 1 Quoted in Naomi Klein, No Logo: Taking Aim at the Brand Bullies (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in The Economist January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see The Economist, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary Policy’, American Economic Review, vol. 68 (1968), pp.1–17. We are not claiming that this process is the only cause of the business cycle, but that it is a contributing factor directly attributable to the prevailing monetary system. See Olivier J. Blanchard & Mark W. Watson (1987). See also ‘Shadow Government Statistics’ at 6 See Milton Friedman & Anna Jacobson Schwartz (1993); J. P. Keeler (2001); Barry Eichengreen & K. Mitchener (2003); Carmen

---

### 6. `narration#750` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Reinhart et al. (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, Financial

**В озвучку попало:**

> Reinhart et al. (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, Financial

---

### 7. `narration#803` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> The creation of the French central bank , the ‘Banque de France’, dates back to 18 J anuary, 1800. It follows the sequence described by Rittershausen. It was initially set up as a privately owned joint stock company with a share capital of 30 million francs. Napoleon Bonaparte, still only ‘Consul’ at the time, owned parts of the shares, as did several members of his entourage. Annual general meetings were open to the two hundred largest shareholders, who became k nown as France’s richest ‘deux-cents familles’. Fifteen Regents were appointed to sit on the General Council administering the Bank , as well as the three Censors who supervised the Bank ’s management. The Banque de France experienced several difficulties during its first years, including a crisis in the government’s finances and a fall in its gold reserves. This led to a restriction in the redemption of bank notes. As a result, Napoleon implemented reforms giving him greater say in the management of the Bank . On 22 April, 1806, a new law replaced the Central Committee with a Governor and two Deputy Governors, all three of whom were appointed by Emperor Bonaparte. Two years later, the Imperial Decree of 16 J anuary, 1808 set out the ‘Basic Statutes’ which governed the Bank ’s operations until 1936. The political upheaval of 1848 led to the imposition of ‘forced currency’ acceptance, freeing the Bank from the obligation to redeem its own notes for metal (i.e. step 5 in Rittershausen’s sequence). The Bank ’s notes became legal tender and individuals were obliged to accept them for all payments. Forced currency and legal tender were eliminated by the law of 6 August 1850 but reinstated during the Franco-Prussian war of 1870. Thereafter, there were no further challenges to the status of the Bank ’s paper money as legal tender. Following the victory of the Popular Front in the 1936 general election, the French government decided that it was no longer in the public interest for the Bank to be governed by private company law. The Act of 24 J uly 1936 gave the government the means to intervene more directly in the management of the Bank . M ost of the Councillors were appointed by the Government to represent economic and social interests as well as the general interest of the nation. This was only a prelude to the nationalisation of the Bank , decided by the Act of 2 December, 1945, just after France’s liberation from German occupation. This Act stipulated that the capital of the Bank would be transferred to the State on 1 J anuary, 1946. The shareholders were to receive four 20-year bonds for each share. The last 3% Banque de France bonds were redeemed on 1 J anuary, 1965. Throughout its entire history, the Banque de France handled the Treasury’s cash transactions free of charge and granted the government interest-free advances to meet its fi nancial needs. This changed with the Law of 3 J anuary, 1973.17 Article 25 of this law states tersely: “The national Treasury cannot present its own instruments for discounting at the Banque de France.”18 In other words, for the fi rst time since 1800, the French government had to borrow exclusively from the private sector, and thereby pay interest on any new debt it contracted. Figure 6.2 shows what this has meant in practice.

**В озвучку попало:**

> The creation of the French central bank , the ‘Banque de France’, dates back to 18 J anuary, 1800. It follows the sequence described by Rittershausen. It was initially set up as a privately owned joint stock company with a share capital of 30 million francs. Napoleon Bonaparte, still only ‘Consul’ at the time, owned parts of the shares, as did several members of his entourage. Annual general meetings were open to the two hundred largest shareholders, who became k nown as France’s richest ‘deux-cents familles’. Fifteen Regents were appointed to sit on the General Council administering the Bank , as well as the three Censors who supervised the Bank ’s management. The Banque de France experienced several difficulties during its first years, including a crisis in the government’s finances and a fall in its gold reserves. This led to a restriction in the redemption of bank notes. As a result, Napoleon implemented reforms giving him greater say in the management of the Bank . On 22 April, 1806, a new law replaced the Central Committee with a Governor and two Deputy Governors, all three of whom were appointed by Emperor Bonaparte. Two years later, the Imperial Decree of 16 J anuary, 1808 set out the ‘Basic Statutes’ which governed the Bank ’s operations until 1936. The political upheaval of 1848 led to the imposition of ‘forced currency’ acceptance, freeing the Bank from the obligation to redeem its own notes for metal (i.e. step 5 in Rittershausen’s sequence). The Bank ’s notes became legal tender and individuals were obliged to accept them for all payments. Forced currency and legal tender were eliminated by the law of 6 August 1850 but reinstated during the Franco-Prussian war of 1870. Thereafter, there were no further challenges to the status of the Bank ’s paper money as legal tender. Following the victory of the Popular Front in the 1936 general election, the French government decided that it was no longer in the public interest for the Bank to be governed by private company law. The Act of 24 J uly 1936 gave the government the means to intervene more directly in the management of the Bank . M ost of the Councillors were appointed by the Government to represent economic and social interests as well as the general interest of the nation. This was only a prelude to the nationalisation of the Bank , decided by the Act of 2 December, 1945, just after France’s liberation from German occupation. This Act stipulated that the capital of the Bank would be transferred to the State on 1 J anuary, 1946. The shareholders were to receive four 20-year bonds for each share. The last 3% Banque de France bonds were redeemed on 1 J anuary, 1965. Throughout its entire history, the Banque de France handled the Treasury’s cash transactions free of charge and granted the government interest-free advances to meet its fi nancial needs. This changed with the Law of 3 J anuary, 1973.17 Article 25 of this law states tersely: “The national Treasury cannot present its own instruments for discounting at the Banque de France.”18 In other words, for the fi rst time since 1800, the French government had to borrow exclusively from the private sector, and thereby pay interest on any new debt it contracted. Figure 6.2 shows what this has meant in practice.

---

### 8. `narration#933` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> The Wellness Token Alliance, which could be run by an NGO or by a group of insurance companies⁹, would issue Wellness Tokens for two types of activities:

**В озвучку попало:**

> The Wellness Token Alliance, which could be run by an NGO or by a group of insurance companies⁹, would issue Wellness Tokens for two types of activities:

---

### 9. `narration#934` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Promoting preventive health care programmes including primary, secondary and tertiary disease prevention measures, focusing on lifestyle modification for people with or without chronic conditions – including nutrition, physical activity and stress management interventions. Such health-educational programmes have an impact on health care costs and health outcomes.

**В озвучку попало:**

> Promoting preventive health care programmes including primary, secondary and tertiary disease prevention measures, focusing on lifestyle modification for people with or without chronic conditions – including nutrition, physical activity and stress management interventions. Such health-educational programmes have an impact on health care costs and health outcomes.

---

### 10. `narration#936` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> The return on investment (ROI) of such preventive programmes is estimated to range from 300% to 1000% depending on the programme.¹¹ That such rates of return are available in preventive programmes provides hard evidence that the ‘sick and alive’ market failure is quite real. Wellness Tokens would encourage the adoption and maintenance of healthy habitual behaviours. The payment of individuals for maintaining specified healthy behaviours has already been documented through the use of conditional cash transfers, for example to remain HIV negative.¹² For example, a family with two obese children could participate in a weight reduction programme, monitored either through weight or, even more precisely, through the Body Mass Index (BMI). For every kilogram or BMI improvement, the family would receive 10 Wellness Tokens.

**В озвучку попало:**

> The return on investment (ROI) of such preventive programmes is estimated to range from 300% to 1000% depending on the programme.¹¹ That such rates of return are available in preventive programmes provides hard evidence that the ‘sick and alive’ market failure is quite real. Wellness Tokens would encourage the adoption and maintenance of healthy habitual behaviours. The payment of individuals for maintaining specified healthy behaviours has already been documented through the use of conditional cash transfers, for example to remain HIV negative.¹² For example, a family with two obese children could participate in a weight reduction programme, monitored either through weight or, even more precisely, through the Body Mass Index (BMI). For every kilogram or BMI improvement, the family would receive 10 Wellness Tokens.

---

### 11. `narration#937` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Helping the elderly or disabled people requiring chronic care. In industrialised countries, the proportion of people over 60 years of age is growing faster than any other age group due to longer life expectancy and declining birth rates. By 2050, the number of people over 60 will almost double. Technological advances tend to be less relevant for home care than for other health care fields and home care is structurally linked to personal face-to-face interactions, which makes it less costly and more humane in many cases. Therefore, having recourse to home care instead of anonymous, hi-tech hospital treatment, even in the case of chronic conditions, will make a significant positive difference to health care costs and, in many cases, to treatment outcomes.

**В озвучку попало:**

> Helping the elderly or disabled people requiring chronic care. In industrialised countries, the proportion of people over 60 years of age is growing faster than any other age group due to longer life expectancy and declining birth rates. By 2050, the number of people over 60 will almost double. Technological advances tend to be less relevant for home care than for other health care fields and home care is structurally linked to personal face-to-face interactions, which makes it less costly and more humane in many cases. Therefore, having recourse to home care instead of anonymous, hi-tech hospital treatment, even in the case of chronic conditions, will make a significant positive difference to health care costs and, in many cases, to treatment outcomes.

---

### 12. `narration#939` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a personal-responsibility-building dimension to the Wellness Tokens, in the direction of what has been called ‘genuine autonomy’ of the patient in recent literature inspired by Ivan Illich.¹⁴ The system offers positive rather than negative incentives to motivate and reward people for their behaviours rather than punish them for ‘misbehaviours’. The perception should be that the system increases the opportunities available to people rather than imposing restrictions on them.

**В озвучку попало:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a personal-responsibility-building dimension to the Wellness Tokens, in the direction of what has been called ‘genuine autonomy’ of the patient in recent literature inspired by Ivan Illich.¹⁴ The system offers positive rather than negative incentives to motivate and reward people for their behaviours rather than punish them for ‘misbehaviours’. The perception should be that the system increases the opportunities available to people rather than imposing restrictions on them.

---

### 13. `narration#940` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> This approach would also be useful in setting up support groups. Creating pods of people who are tackling a weight problem can be a very effective way to get longer-term commitment. One could then create group objectives, which —when met — earn extra Wellness Tokens for the entire group.

**В озвучку попало:**

> This approach would also be useful in setting up support groups. Creating pods of people who are tackling a weight problem can be a very effective way to get longer-term commitment. One could then create group objectives, which —when met — earn extra Wellness Tokens for the entire group.

---

### 14. `narration#941` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Group support is well known as a key for longer-term maintenance of changes and improvements.

**В озвучку попало:**

> Group support is well known as a key for longer-term maintenance of changes and improvements.

---

### 15. `narration#1075` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, Creating Wealth: Growing Local

**В озвучку попало:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, Creating Wealth: Growing Local

---

### 16. `narration#1076` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Economies with Local Currencies (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, Insurance

**В озвучку попало:**

> Economies with Local Currencies (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, Insurance

---

### 17. `narration#1263` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> On the website (formally a part of this Report) we invite public input on how to deal with the matters presented in this Report. The potential number of issues worthy of attention and debate is infinite. They can be as rich as life itself. Here are just four examples of topics well worth some attention:

**В озвучку попало:**

> On the website (formally a part of this Report) we invite public input on how to deal with the matters presented in this Report. The potential number of issues worthy of attention and debate is infinite. They can be as rich as life itself. Here are just four examples of topics well worth some attention:

---

### 18. `narration#1264` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> • What initiatives or experiments can be started now to help the government and citizens of Greece deal with their country’s economic collapse? Why could Greece not stay within the eurozone for its international transactions (tourism, shipping, exports and imports), while allowing its cities to start Civics systems to replace the vanishing governmental social support mechanisms? Would this not help reduce the Greek central government’s budget deficit while giving a breath of hope to the millions affected by savage cuts in jobs and vital social programmes?

**В озвучку попало:**

> • What initiatives or experiments can be started now to help the government and citizens of Greece deal with their country’s economic collapse? Why could Greece not stay within the eurozone for its international transactions (tourism, shipping, exports and imports), while allowing its cities to start Civics systems to replace the vanishing governmental social support mechanisms? Would this not help reduce the Greek central government’s budget deficit while giving a breath of hope to the millions affected by savage cuts in jobs and vital social programmes?

---

### 19. `narration#1265` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> • How can we address horrendous youth unemployment,13 in countries like Spain (45% official youth unemployment), Slovakia (33.6%), Lithuania (33.2%), Ireland (29.8%), Portugal (28.7%) and Italy (27.7%)? Why not implement C3 systems at the regional level? Wanting ‘regional development’ while using only the euro has been shown to be an economic oxymoron, a contradiction in terms.

**В озвучку попало:**

> • How can we address horrendous youth unemployment,13 in countries like Spain (45% official youth unemployment), Slovakia (33.6%), Lithuania (33.2%), Ireland (29.8%), Portugal (28.7%) and Italy (27.7%)? Why not implement C3 systems at the regional level? Wanting ‘regional development’ while using only the euro has been shown to be an economic oxymoron, a contradiction in terms.

---

### 20. `narration#1267` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> • Why not mobilise the European Investment Fund for launching C3 systems? Several billion euros are available through the JEREMIE program (‘Joint European Resources for Micro to Medium- sized Enterprises’),15 if a 2010 administrative decision to make these funds available only for SMEs starting brand-new activities backed by a formal business plan is reversed. How many SMEs in today’s economic environment are able to start brand-new activities, when they are dying like flies from not getting paid on time for their existing sales? As a consequence, most of these JEREMIE funds will expire unused in 2015. How can such administrative blockages be lifted?

**В озвучку попало:**

> • Why not mobilise the European Investment Fund for launching C3 systems? Several billion euros are available through the JEREMIE program (‘Joint European Resources for Micro to Medium- sized Enterprises’),15 if a 2010 administrative decision to make these funds available only for SMEs starting brand-new activities backed by a formal business plan is reversed. How many SMEs in today’s economic environment are able to start brand-new activities, when they are dying like flies from not getting paid on time for their existing sales? As a consequence, most of these JEREMIE funds will expire unused in 2015. How can such administrative blockages be lifted?

---

### 21. `narration#1268` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> • Much of our approach to education still involves preparing children for an industrial world that no longer exists. Why not experiment with systems such as the Doraland that considers everyone a potential teacher and learner? How might learning multiply with mutual-learning approaches, in and out of school?¹⁶ With an infinite number of domains requiring learning in a world of ever- accelerating change, should we not use all of our collective intelligence, well beyond the mechanisms and horizons encouraged by our out-of-date industrial-age structures?

**В озвучку попало:**

> • Much of our approach to education still involves preparing children for an industrial world that no longer exists. Why not experiment with systems such as the Doraland that considers everyone a potential teacher and learner? How might learning multiply with mutual-learning approaches, in and out of school?¹⁶ With an infinite number of domains requiring learning in a world of ever- accelerating change, should we not use all of our collective intelligence, well beyond the mechanisms and horizons encouraged by our out-of-date industrial-age structures?

---

### 22. `narration#1269` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> We are facing the greatest challenges ever to be faced by humanity. We know that we must switch to a post-carbon economy, and swiftly, if we are to avoid disaster. We know that this is technologically possible, but that it can be implemented within the time available only with massive government support and funding – something which reined-in budgets in conventional money will not allow for at least the next decade. At the same time, we face caring for a booming greying population that will no longer be contributing to the economic base, but will need to rely on social support programmes that are now under frontal attack. We face all this with shrinking economies, under brutal compulsion by an anonymous ‘financial market’ to reduce enormous public debts, bloated by the cost of the 2007-8 banking meltdown and its immediate economic consequences.

**В озвучку попало:**

> We are facing the greatest challenges ever to be faced by humanity. We know that we must switch to a post-carbon economy, and swiftly, if we are to avoid disaster. We know that this is technologically possible, but that it can be implemented within the time available only with massive government support and funding – something which reined-in budgets in conventional money will not allow for at least the next decade. At the same time, we face caring for a booming greying population that will no longer be contributing to the economic base, but will need to rely on social support programmes that are now under frontal attack. We face all this with shrinking economies, under brutal compulsion by an anonymous ‘financial market’ to reduce enormous public debts, bloated by the cost of the 2007-8 banking meltdown and its immediate economic consequences.

---

### 23. `narration#1270` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> The stakes are unprecedentedly high. But the possibilities for creative solutions are also near at hand – solutions that do not further strain public budgets, that have already demonstrated their effectiveness in practice, that can turn populations from hopeless rage to fruitful engagement within their communities, and that can preserve corporate profits, but not at the expense of social and environmental health. We still have a fighting chance to give birth to a sustainable world that works for everyone…

**В озвучку попало:**

> The stakes are unprecedentedly high. But the possibilities for creative solutions are also near at hand – solutions that do not further strain public budgets, that have already demonstrated their effectiveness in practice, that can turn populations from hopeless rage to fruitful engagement within their communities, and that can preserve corporate profits, but not at the expense of social and environmental health. We still have a fighting chance to give birth to a sustainable world that works for everyone…

---

### 24. `narration#1271` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Is this scenario pie-in-the-sky? Are we offering just one more miraculous panacea? We do not think so. We have never claimed that a monetary ecosystem would be sufficient to address the challenges of today. We hope to have shown, however, that rethinking our money system is a necessary part of any solution. This is the core message of this Report.

**В озвучку попало:**

> Is this scenario pie-in-the-sky? Are we offering just one more miraculous panacea? We do not think so. We have never claimed that a monetary ecosystem would be sufficient to address the challenges of today. We hope to have shown, however, that rethinking our money system is a necessary part of any solution. This is the core message of this Report.

---

### 25. `narration#1272` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Our sincere hope is that as the world of the old economy breaks down, the seeds of a new and more humane economy may be given a chance to emerge. “There is a rabbinical teaching that if the world is ending and the Messiah arrives, you first plant a tree; and then see if the story is true. Islam has a similar teaching that tells its adherents that if they have a palm cutting in their hand on Judgement Day, plant the cutting.”¹⁷

**В озвучку попало:**

> Our sincere hope is that as the world of the old economy breaks down, the seeds of a new and more humane economy may be given a chance to emerge. “There is a rabbinical teaching that if the world is ending and the Messiah arrives, you first plant a tree; and then see if the story is true. Islam has a similar teaching that tells its adherents that if they have a palm cutting in their hand on Judgement Day, plant the cutting.”¹⁷

---
## Пустые и почти пустые абзацы (21)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе). Это та самая форма, которая в прогоне литературной правки давала литеральные «(Пусто)».

### 1. `p0055` — длина озвучки / длина оригинала: 0.69; классы правки: —

**Исходный абзац:**

> These objectives are close to the Club of Rome’s heart.

**В озвучку попало:**

> Эти цели близки сердцу Римского клуба.

---

### 2. `p0395` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Emergence of a ‘Global Casino’

**В озвучку попало:**

> ## 1. Появление «глобального казино»

---

### 3. `p0465` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 4. A Solution: The Privatisation of Everything?

**В озвучку попало:**

> ## 4. Решение: приватизация всего?

---

### 4. `p0495` — длина озвучки / длина оригинала: 0.05; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Source:Speech made in New York 25 October 2010 See:*www.qfinance.com ~ bit.ly/TPlink17* 2 ‘The Global Currency Game is Exploding’, *The Wall Street Journal*, 26 September 2007, pp.C1 and C3.

**В озвучку попало:**

> Примечания

---

### 5. `p0496` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> 3 *The CIA Factbook 2012* estimates global GDP at purchasing power parity at US$78.98 trillion. 4 John Maynard Keynes, *The General Theory of Employment, Interest and Money* (1936), p.159. 5 Ludwig von Mises, *Human Action: A Treatise on Economics* (1949). 6 *The Financial Crisis Inquiry Report: Final Report of the National Commission of the Financial and Economic Crisis in the United*

**В озвучку попало:**

> 

---

### 6. `p0497` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *States* (2011). 7 Andrew Ross Sorkin, *Too Big to Fail* (2010). 8 Anton R. Valukas, Lehman Brothers Inc. Chapter 11 Proceedings Examiner’s Report (2010), downloadable from *http://lehmanreport.jenner.com ~ bit.ly/TPlink18* (visited: 8 January 2012). 9 ‘Restoring Ireland’s Credit by Reducing Uncertainty’, Remarks by Mr Patrick Honohan, Governor of the Central Bank of Ireland, at the Institute of International and European Affairs, Dublin, 7 January 2011, downloadable from *www.bis.org* ~ *bit.ly/TPlink19* (visited: 8 January 2012). 10 Máni Arnarson, Þorbjörn Kristjánsson, Atli Bjarnason, Harald Sverdrup and Kristín Vala Ragnarsdóttir*, Icelandic Economic*

**В озвучку попало:**

> 

---

### 7. `p0527` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Misclassification of Economics

**В озвучку попало:**

> ## 1. Ошибочная классификация экономики

---

### 8. `p0559` — длина озвучки / длина оригинала: 0.81; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 3. The Physics of Complex Flow Networks

**В озвучку попало:**

> ## 3. Физика сложных сетей потоков

---

### 9. `p0702` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Wate r lilie s s pre ading in a pond**

**В озвучку попало:**

> **Распространение кувшинок в пруду**

---

### 10. `p0808` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, *No Logo: Taking Aim at the Brand Bullies* (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in *The Economist* January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see *The Economist*, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary Policy’, *American Economic Review*, vol. 68 (1968), pp.1–17. We are not claiming that this process is the only cause of the business cycle, but that it is a contributing factor directly attributable to the prevailing monetary system. See Olivier J. Blanchard & Mark W. Watson (1987). See also ‘Shadow Government Statistics’ at *www.shadowstats.com* 6 See Milton Friedman & Anna Jacobson Schwartz (1993); J. P. Keeler (2001); Barry Eichengreen & K. Mitchener (2003); Carmen

**В озвучку попало:**

> 

---

### 11. `p0809` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_lost

**Исходный абзац:**

> Reinhart *et al.* (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, *Financial*

**В озвучку попало:**

> 

---

### 12. `p0937` — длина озвучки / длина оригинала: 0.65; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## Examples of Private Initiative Solutions

**В озвучку попало:**

> ## Примеры частных инициатив

---

### 13. `p0954` — длина озвучки / длина оригинала: 0.58; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Box 7.1 – Me nu of Motivation Sys te ms

**В озвучку попало:**

> ### Меню систем мотивации

---

### 14. `p1053` — длина озвучки / длина оригинала: 0.62; классы правки: —

**Исходный абзац:**

> The C3 mechanism involves the following seven steps:

**В озвучку попало:**

> Система C3 включает семь этапов:

---

### 15. `p1123` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Benefits for participating businesses**

**В озвучку попало:**

> **Преимущества для бизнеса**

---

### 16. `p1140` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, *Creating Wealth: Growing Local*

**В озвучку попало:**

> 

---

### 17. `p1141` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Economies with Local Currencies* (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, *Insurance*

**В озвучку попало:**

> 

---

### 18. `p1142` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Markets and Adverse Selection: A Handbook for Health* *Economists* (1998). 5 Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine.* 6 *U.S. Health* (2005) National Center for Health Statistics, Department of Health and Human Services, No: 2005-1232. 7 “Behavioral and social interventions therefore offer great promise to reduce disease morbidity and mortality, but as yet their potential to improve the public’s health has been relatively poorly tapped.” Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine*. 8 L.A. Nefiodow, *Der Sechste Kondratieff* (2001). See also Appendix G for more information on Nicolai Kondratieff and ‘long waves’. 9 In the Netherlands an alliance involving the largest insurance company is planning to introduce several city-scaled experiments for motivation systems to deal with the ageing wave of the next decades. 10 Indeed not all preventive programmes are cheaper than the treatment . Studies show that it is more cost effective to treat tuberculosis rather than prevent it. See Borgdorff *et al*. (2002). Influenza vaccination is not cost effective for healthy working adults. See Bridges *et al*. (2000). However, all of these studies only compare the costs for treatment and the costs for prevention. They do not take into consideration the decrease in productivity and the absenteeism due to illness. 11 The most significant benefits occur after the second or third year of the programme. One hundred dollars or euros spent on preventive care programmes per year and per employee will have an ROI after the third year of 300 dollars or euros. See Goetzel (1999); Erfurt (1992); Powell (1999) and Chapman (2003). 12 Lia *et al.* (2008); Bastagli (2009). 13 See *www.cdc.gov* ~ *1.usa.gov/TPlink47n* 14 See Christian Léonard, *Croissance contre santé: Quelle responsabilisation du malade?* (2008). While Léonard, a leading Belgian health care expert, is strongly critical of the current ideology of punitive ‘responsibilisation’ of patients, he does argue in favour of a “genuine” autonomisation, which he links to Ivan Illich’s ideas of autonomy and conviviality: genuine personal responsibility can only flow from a reappropriation, by the patient him/herself, of his/her health. This requires preventive measures, which are under-financed in the current “alive and sick” logic. The Wellness Token system, therefore, moves in the direction called for by Léonard. 15 The Elderplan insurance company in the New York area has implemented successfully part of this idea with a Time Dollar currency.

**В озвучку попало:**

> 

---

### 19. `p1143` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> They have discovered that people participating in a Time Dollar system remain on average healthier because of a better social capital environment. 16 Lia *et al.* (2008); Paxson & Schady (2007). 17 The Swiss business-to-business currency system WIR has been successfully operating on this principle for 75 years. 18 C. J. Ruhm, *Macroeconomic Conditions, Health and Government Policy* (2006). 19 The text of this section is extracted and summarised from Marek Hudon and Bernard Lietaer, ‘Natural Savings: A New Microsavings Product for Inflationary Environments – How to Save Forests with Savings For and By the Poor?’, *Savings and Development*, vol. 4 (2006), pp.357-381 20 If the property is owned by a third party, one could also arrange for a long-term lease of the necessary land and pay the owner in part or whole with shares in the Natural Savings Company. 21 Depending on the size of the land and the community, one could make this a continuous process, with new plantations and harvest on parts of the total forest on a periodic, rotating basis. Well-known forestry management techniques should be applied as appropriate. 22 Lietaer (2001). 23 Dolde (1993). 24 See for example: Harmon (1959); Graham (1937) and (1944); Hart *et al.* (1964); Grondona (1975); Gondriaan (1932) and Jevons (1875).

**В озвучку попало:**

> 

---

### 20. `p1204` — длина озвучки / длина оригинала: 0.93; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • living in a better-quality environment.

**В озвучку попало:**

> • улучшение качества окружающей среды.

---

### 21. `p1247` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> For citizens, the advantages would include:

**В озвучку попало:**

> Для граждан преимущества включают:

---
