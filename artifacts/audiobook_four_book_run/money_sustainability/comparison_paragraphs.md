# Аудиокнига, прогон четырёх книг 2026-08-06 — money_sustainability, материал для просмотра глазами

Книга: Bernard Lietaer et al., *Money and Sustainability: The Missing Link* (`tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-160516072426.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_ab4_money_sustainability`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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
6. **Пустые и почти пустые абзацы — все 23**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1318; вернулось: 1317;
дошло до narration-артефакта: 1291.
Пул прозы, из которого делалась выборка: 466 абзацев.
Медианное отношение длин по прозе: 0.9976.

---
## Случайная выборка (60 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0048` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Governments, media and most leaders mak e every possible effort to convince public opinion to stick to mainstream think ing. If society wishes to be or to become successful, they say, we have to k eep faith in the current paradigm. The gospel still is that everything has to be expressed in monetary terms. And that there is no salvation outside the dominant financial systems and bank ing practices, a monopoly and a major power instrument. Closed systems are preferred to open ones. Complexity is avoided. Indeed a shortsighted vision on sustainable solutions…

**В озвучку попало:**

> Правительства, средства массовой информации и большинство лидеров делают всё возможное, чтобы убедить общество придерживаться привычных взглядов. Они утверждают: если мы хотим добиться успеха, мы должны сохранять веру в текущую парадигму. По-прежнему считается, что всё на свете должно измеряться в денежном эквиваленте. И что нет спасения вне доминирующих финансовых систем и банковских практик, которые являются монополией и мощным инструментом влияния. Закрытые системы предпочитают открытым. Сложности стараются избегать. Поистине, это близорукий взгляд на устойчивые решения.

---

### 2. `p0053` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> While the issue is by definition global, the CoR-EU felt the Report should primarily be addressed on its behalf to a recognised, authoritative and independent European body. The most appropriate choice seemed to be *Finance Watch,* a public interest association, recently created on the initiative of members of the European Parliament. It is dedicated to mak ing finance work for the good of society, strengthening the voice of society in financial regulation reforms by conducting citizen advocacy and presenting public interest arguments to lawmak ers as a counterweight to private interest lobbying by the financial industry.

**В озвучку попало:**

> Хотя проблема по своей сути глобальна, мы в Европейском отделении посчитали, что отчет должен быть адресован признанному, авторитетному и независимому европейскому органу. Наиболее подходящим выбором стала ассоциация «Finance Watch» — общественная организация, созданная по инициативе депутатов Европейского парламента. Она призвана сделать финансы полезными для общества, усиливая голос граждан в реформах финансового регулирования. Ассоциация выступает как противовес лоббированию частных интересов со стороны финансовой индустрии, представляя аргументы в пользу общественного блага перед законодателями.

---

### 3. `p0058` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> There is a great challenge here for the European U nion. We dare hope that the publication of *Money and Sustainability: The Missing Link* will inspire many a decision mak er and opinion leader to change course now, choosing new, creative approaches in monetary issues.

**В озвучку попало:**

> Перед Европейским союзом стоит серьезный вызов. Мы смеем надеяться, что публикация нашего отчета «Деньги и устойчивое развитие: недостающее звено» вдохновит многих лиц, принимающих решения, и лидеров мнений изменить курс. Мы призываем их выбрать новые, творческие подходы к решению денежных вопросов.

---

### 4. `p0072` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> The book contains powerful arguments that need to be listened to, digested and acted upon. The section on how money affects sustainability mak es the k ey point that the global crises we face are interconnected. The financial crisis is but one dimension of a multi-dimensional puzzle. However, the book is more than a diagnosis of the ills and travails of our monetary system; it also points to new ways of reforming our financial system, to pioneering ideas and to potential solutions. The call for alternative think ing and innovative strategies is timely and necessary.

**В озвучку попало:**

> Книга содержит веские аргументы, которые необходимо услышать, осмыслить и претворить в жизнь. Раздел о влиянии денег на устойчивость подчеркивает ключевую мысль: глобальные кризисы, с которыми мы сталкиваемся, взаимосвязаны. Финансовый кризис — лишь один из аспектов многомерной проблемы. Однако эта книга — не просто диагноз болезням нашей денежной системы. Она указывает на новые пути реформирования, предлагает новаторские идеи и возможные решения. Призыв к альтернативному мышлению и инновационным стратегиям сейчас как никогда актуален и необходим.

---

### 5. `p0081` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> This study complements other endeavours of WAAS stressing the essential value and role of human capital. The Report reminds us that money is a man-made instrument intended to help society optimise human welfare. The prevailing monetary system encourages the multiplication of money for destabilising speculative investment rather than for productive investment that creates jobs, raises real incomes and promotes social equity. The Report examines alternative monetary strategies that can help mobilise under-utilised social resources, especially the huge number of unemployed and underemployed young people and adults whose human potential is ignored and squandered by the current system. This Report is a call for prompt political and economic action.

**В озвучку попало:**

> Это исследование дополняет другие проекты Академии, подчеркивающие исключительную ценность и роль человеческого капитала. Доклад напоминает нам: деньги — это инструмент, созданный человеком, чтобы помогать обществу повышать благосостояние. Нынешняя денежная система поощряет приумножение капитала ради дестабилизирующих спекуляций, а не ради продуктивных инвестиций, которые создают рабочие места, повышают реальные доходы и способствуют социальному равенству. Авторы рассматривают альтернативные денежные стратегии, способные мобилизовать неиспользуемые общественные ресурсы. В первую очередь это касается огромного числа безработных и частично занятых людей, чей потенциал нынешняя система просто игнорирует и растрачивает. Этот доклад — призыв к решительным политическим и экономическим действиям.

---

### 6. `p0099` — длина озвучки / длина оригинала: 1.18; классы правки: —

**Исходный абзац:**

> Fiat currency issued by private institutions through the creation of debt has been used by nations for centuries. Its deadly effects are becoming apparent. But its ability to alleviate the symptoms of distress has led to its use anyway. We can only hope that in this century we will begin to use less deadly alternatives.

**В озвучку попало:**

> Фиатные деньги, которые частные институты выпускают через создание долга, страны используют уже много веков. Их губительные последствия становятся всё более очевидными. Однако способность этих денег временно снимать симптомы кризиса по-прежнему заставляет нас ими пользоваться. Остается лишь надеяться, что в нынешнем столетии мы начнем переходить на менее опасные альтернативы.

---

### 7. `p0101` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> A fish will never create fire while immersed in water. We will never create sustainability while immersed in the present financial system. There is no tax, or interest rate, or disclosure requirement that can overcome the many ways the current money system blocks sustainability.

**В озвучку попало:**

> Рыба никогда не добудет огонь, пока находится под водой. Мы никогда не создадим устойчивое общество, пока погружены в нынешнюю финансовую систему. Никакие налоги, процентные ставки или требования к отчетности не помогут преодолеть те многочисленные барьеры, которыми нынешняя денежная система блокирует устойчивость.

---

### 8. `p0102` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> I used not to think this. Indeed, I did not think about the money system at all. I took it for granted as a neutral and inevitable aspect of human society. But since beginning to read Bernard’s analyses I have a very different view. He is not alone. For example Thomas Greco has written on this topic. But the depth of Bernard’s practical experience, theoretical understanding, and historical perspectives on the financial system leave him without peer.

**В озвучку попало:**

> Раньше я так не думал. По правде говоря, я вообще не задумывался о денежной системе. Я принимал её как нечто нейтральное и неизбежное, как данность человеческого общества. Но, начав читать аналитические работы Бернара, я изменил свой взгляд. И он не одинок в своих выводах. Например, на эту тему писал Томас Греко. Однако глубина практического опыта Бернара, его теоретические знания и исторический взгляд на финансовую систему делают его работу уникальной.

---

### 9. `p0143` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> It is our contention that the ‘Missing Link’ between finance and the environment, between money and sustainability, lies elsewhere. What this Report demonstrates beyond doubt is a structural monetary flaw – a flaw in the very manner in which we create money – that is generating our disconcerting problems. The inescapable conclusion? That, in order to face the challenges of the 21st century, we need to rethink and overhaul our entire monetary system.

**В озвучку попало:**

> Мы утверждаем, что «недостающее звено» между финансами и окружающей средой, между деньгами и устойчивостью, находится в другой плоскости. Этот отчет вне всяких сомнений доказывает наличие структурного изъяна в самой системе создания денег, который и порождает наши тревожные проблемы. Неизбежный вывод таков: чтобы справиться с вызовами двадцать первого века, нам необходимо переосмыслить и полностью перестроить всю нашу денежную систему.

---

### 10. `p0151` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> Debates about economic issues rarely reveal the paradigm from which an economist is speaking. We start by making explicit the conceptual framework that underlies our approach, and compare it with other paradigms currently in use. Rather than defining environmental and social issues as ‘externalities’, our approach sees economic activities as a subset of the social realm, which, in turn, is a subset of the biosphere. This view provides the basis for the emergence of a new set of pragmatic tools, flexible enough to address many of our economic, social and environmental challenges.

**В озвучку попало:**

> [thoughtful] В дискуссиях об экономике редко говорят о том, на какой парадигме основывается позиция эксперта. Мы начнем с того, что четко обозначим концептуальную базу нашего подхода и сравним ее с другими моделями. Мы не считаем экологические и социальные проблемы «внешними эффектами». Напротив, наш подход рассматривает экономическую деятельность как часть социальной сферы, которая, в свою очередь, является частью биосферы. Такой взгляд позволяет создать набор практических инструментов, достаточно гибких для решения многих наших экономических, социальных и экологических задач.

---

### 11. `p0209` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> In closing, it would be naïve to think of complementary currencies as a magic bullet to solve all our current and future problems. However, rethinking our money is a necessary ingredient in any effective solution. We can no longer afford to overlook complementary currencies as the ‘Missing Link’ that can deliver a money system which promotes sustainability rather than undermining it at every turn.

**В озвучку попало:**

> В заключение скажу: было бы наивно считать дополнительные валюты волшебной таблеткой от всех наших текущих и будущих проблем. И все же переосмысление денег — необходимый элемент любого эффективного решения. Мы больше не можем игнорировать дополнительные валюты. Это то самое «недостающее звено», которое позволит создать денежную систему, способствующую устойчивому развитию, а не подрывающую его на каждом шагу.

---

### 12. `p0271` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Conceptual relationships between the field of economics and the natural world can be described in three different ways. The most conventional view is to treat anything that is not dealt with unambiguously within one’s own theoretical framework as an ‘externality’ (see Figure 2.1). This economic view defines its own field as completely self-contained and excludes any other consideration as irrelevant. For instance, in such a view, the natural world is reduced to a resource, an input that is considered to be cost-free – to the extent that no money is exchanged to acquire it.

**В озвучку попало:**

> [serious] Концептуальные отношения между экономикой и миром природы можно описать тремя способами. Самый распространенный подход — рассматривать всё, что не вписывается в рамки текущей теории, как «внешний фактор». Эта экономическая модель определяет свою область как полностью замкнутую, а всё остальное считает неважным. Например, в такой системе мир природы сводится лишь к ресурсу или сырью. Если за получение этого ресурса не нужно платить деньги, он считается бесплатным.

---

### 13. `p0290` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> The standard measurement of economic progress thus remains the Gross National Product (GNP) per capita, which captures neither the depletion of natural resources, nor the quality of growth, nor the distribution of its benefits. Furthermore, market prices rarely reveal the real costs of a product or service. Their production and disposal can create damage that remains ignored in the conventional accounting system.¹⁶ Sufficient evidence now exists for a fundamental rethinking to take place if sustainability is taken seriously. If humanity’s decisions continue to be made on the basis of the Traditional Economics paradigm (Figure 2.1) or even the OECD paradigm (Figure 2.2), all signs point to a bleak future for our human condition and our planet. Indeed, humanity’s unsustainable behaviour is provoking the sixth great mass extinction of the geological record at a rate of 30,000 species per year or three species per hour. Having a greater awareness of the limitations of the dominant economic paradigms is therefore not merely of academic relevance.

**В озвучку попало:**

> [serious] Стандартным мерилом экономического прогресса остается валовой национальный продукт на душу населения. Этот показатель не учитывает ни истощение природных ресурсов, ни качество роста, ни то, как распределяются его плоды. Более того, рыночные цены редко отражают реальную стоимость товара или услуги. Их производство и утилизация могут наносить ущерб, который просто игнорируется в традиционной системе учета. Сейчас накоплено достаточно доказательств того, что если мы всерьез относимся к устойчивому развитию, необходим фундаментальный пересмотр всей системы. Если человечество продолжит принимать решения, опираясь на старые экономические парадигмы, нас ждет мрачное будущее. [sad] Уже сейчас наше неустойчивое поведение провоцирует шестое массовое вымирание видов в истории Земли. Мы теряем тридцать тысяч видов в год — это три вида каждый час. Поэтому глубокое понимание ограничений господствующих экономических моделей — это не просто академический вопрос.

---

### 14. `p0309` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> In some circles, the word ‘sustainability’ has become synonymous with constraints, heavy-handed governmental regulations, or even a leftist conspiracy. This perception has been amplified by well-funded disinformation campaigns underwritten by various vested business interests, in particular from the carbon energy industries.²² As will be seen in Chapter V, such campaigns are an example of the systematic short-term thinking automatically generated by our monetary system and the manner in which it ‘programs’ our behaviour.

**В озвучку попало:**

> [serious] В некоторых кругах слово «устойчивость» стало синонимом ограничений, жесткого государственного регулирования или даже левацкого заговора. Такое восприятие подогревается хорошо финансируемыми кампаниями по дезинформации, которые спонсируются различными заинтересованными бизнес-структурами, в частности, представителями индустрии углеродной энергетики. Как мы увидим в пятой главе, подобные кампании — это пример систематического мышления краткосрочными категориями, которое автоматически порождается нашей денежной системой и тем, как она «программирует» наше поведение.

---

### 15. `p0344` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> Understanding the community systems that are capable of satisfying a fuller range of human needs is a cornerstone of environmental and human sustainability. The Earth Charter Commission, working with the World Resources Institute and Global Community Initiatives, developed a comprehensive methodology for communities to evaluate their own sustainability and plan for a more sustainable future.³¹

**В озвучку попало:**

> [thoughtful] Понимание общественных систем, способных удовлетворять широкий спектр человеческих потребностей, является краеугольным камнем экологической и социальной устойчивости. Комиссия Хартии Земли в сотрудничестве с Институтом мировых ресурсов и инициативой «Глобальное сообщество» разработала комплексную методику. Она позволяет общинам оценивать уровень своей устойчивости и планировать более устойчивое будущее.

---

### 16. `p0346` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In order to spell out the economic paradigm in which we operate, the monetary dimension of the economy must explicitly be explored. Not all paradigms do this – some, and most notably the dominant Traditional Economics approach, view money as a passive element not affecting the way that individuals and collectives choose to act. The Ecological Economics paradigm, in the way we conceive it here, takes the monetary dimension much more seriously. How so? This is what we intend to explain in the remainder of this chapter. The exploration of this feature is what most sets this study apart from other economic texts and studies on sustainability.³²

**В озвучку попало:**

> [serious] Чтобы прояснить экономическую парадигму, в которой мы существуем, необходимо детально изучить денежный аспект экономики. Не все подходы делают это. Наиболее заметный из них, традиционная экономическая теория, рассматривает деньги как пассивный элемент, который не влияет на выбор людей и коллективов. Экологическая экономика, в том виде, в каком мы её здесь представляем, относится к денежной сфере гораздо серьёзнее. Почему? Именно это мы и собираемся объяснить в оставшейся части главы. Исследование этой особенности — то, что больше всего отличает данное исследование от других работ по экономике и устойчивому развитию.

---

### 17. `p0404` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> What most analysts fail to realise is that to identify structural problems, one must focus on what is common among all financial and monetary crises rather than on their differences. In metaphorical terms, a view of the entire forest is required, rather than a close-up inspection of any individual tree or of a specific type of tree.

**В озвучку попало:**

> Большинство аналитиков не осознают главного: чтобы выявить структурные проблемы, нужно сосредоточиться на том, что общего у всех финансовых и денежных кризисов, а не на их различиях. Метафорически говоря, нужно видеть весь лес целиком, а не рассматривать каждое отдельное дерево или конкретный вид деревьев под микроскопом.

---

### 18. `p0448` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Notice that this impact is completely independent of the quality of any government’s own policies, before or during the crisis. While much has been made of the case of Greece where fraud was involved, not much can be blamed on governments or citizens in Iceland, Ireland, Latvia, Denmark or Spain, all hit with sudden increases in their national debt, which reached 35% - 75% of their GDP. The irony is that, as soon as governments borrow these large sums from the financial system to save the system itself from bankruptcy, the financial system concludes that governments are now too indebted and need to be ‘disciplined’.

**В озвучку попало:**

> Заметьте, что это влияние совершенно не зависит от качества политики правительства до или во время кризиса. Хотя много шума было вокруг случая с Грецией, где имело место мошенничество, в бедах Исландии, Ирландии, Латвии, Дании или Испании винить правительства или граждан можно лишь отчасти. Все эти страны столкнулись с внезапным ростом государственного долга, который достиг 35–75 процентов от их ВВП. Ирония в том, что как только правительства занимают эти огромные суммы у финансовой системы, чтобы спасти саму систему от банкротства, эта же система делает вывод, что правительства теперь слишком закредитованы и их нужно «дисциплинировать».

---

### 19. `p0449` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Figure 3.4 brings together the various components of the impact of banking crises on government finances. The direct fiscal cost of bailing out the banking system is added to output losses with an automatic drop in tax income. Governments thus have no other option than to increase their indebtedness. This, in turn, results in the downgrading of the creditworthiness of affected countries and makes their debt more expensive. What does all this lead to?

**В озвучку попало:**

> [thoughtful] На рисунке 3.4 собраны различные компоненты влияния банковских кризисов на государственные финансы. Прямые фискальные расходы на спасение банковской системы суммируются с потерями в объеме производства и автоматическим падением налоговых поступлений. У правительств не остается иного выбора, кроме как увеличивать свою задолженность. Это, в свою очередь, приводит к снижению кредитного рейтинга пострадавших стран и удорожанию их долга. К чему же все это ведет?

---

### 20. `p0453` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The timing of this sudden increase in government debt is particularly unfortunate. The current decade is one in which the OECD countries and their governments have to deal with unprecedented pressures not amenable to being postponed. As mentioned in Chapter I, two critical and predictable challenges during the next decade will be the transition to a post-carbon economy and the sharp increase in financial requirements for retiring baby boomers.

**В озвучку попало:**

> [thoughtful] Время этого резкого роста государственного долга крайне неудачно. Нынешнее десятилетие требует от правительств стран Организации экономического сотрудничества и развития решения беспрецедентных проблем, которые невозможно отложить на потом. Как уже упоминалось в первой главе, двумя критическими и предсказуемыми вызовами станут переход к экономике без углеродных выбросов и резкое увеличение финансовых обязательств перед выходящим на пенсию поколением «беби-бумеров».

---

### 21. `p0468` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> As of early 2012, forty-four out of the fifty US States face bankruptcy. They are under increasing pressure to start ‘Public-Private Partnerships’, called P3s in the USA and Private Finance Initiatives (PFI) in the UK. What actually occurs in these benign-sounding partnerships is that governments are obliged to sell off existing infrastructure, built and paid for with taxpayers’ money, in order to reduce existing debt or pay for current public expenditures. Once the infrastructure is privatised, new owners can charge fees for the use of a once free public utility, or increase existing tolls. Thus taxpayers will end up paying twice for the same infrastructure and the second time could be more expensive than the first, given that many infrastructural assets are natural monopolies.

**В озвучку попало:**

> К началу 2012 года сорок четыре из пятидесяти штатов США оказались на грани банкротства. Они испытывают растущее давление, вынуждающее их переходить к так называемым государственно-частным партнерствам. В США их называют P3, а в Великобритании — частными финансовыми инициативами. На деле в этих партнерствах с благозвучными названиями правительства вынуждены распродавать существующую инфраструктуру, построенную и оплаченную на деньги налогоплательщиков, чтобы уменьшить долг или покрыть текущие расходы. Как только инфраструктура приватизируется, новые владельцы могут взимать плату за пользование тем, что раньше было бесплатным общественным благом, или повышать существующие тарифы. Таким образом, налогоплательщики в итоге платят дважды за одну и ту же инфраструктуру. Причем второй раз может обойтись дороже, учитывая, что многие инфраструктурные объекты являются естественными монополиями.

---

### 22. `p0469` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> Private investments in public utilities can generate a ‘win-win’ situation when designed and implemented properly. In several European countries, there is a well-established practice of, for instance, the private sector building new toll-paying highways. When such auctions are well prepared and transparent, the results can be beneficial to all parties. However, the P3s currently being proposed are different from their historical precedents in three ways:

**В озвучку попало:**

> [thoughtful] Частные инвестиции в коммунальные услуги могут создать ситуацию «выигрыш-выигрыш», если они грамотно спроектированы и реализованы. В ряде европейских стран существует устоявшаяся практика, когда частный сектор строит новые платные автомагистрали. Когда такие аукционы хорошо подготовлены и прозрачны, результаты могут быть полезны всем сторонам. Однако предлагаемые сейчас партнерства отличаются от исторических прецедентов по трем пунктам.

---

### 23. `p0514` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Unfortunately this does not account for what is currently happening in the financial or monetary domain. After each crash, the banking system is bailed out at government expense, and the old way of doing business is taken up again after fine tuning of the regulatory or managerial environment. The fundamental structure – a monopoly of money created through bank debt – is invariably left intact.

**В озвучку попало:**

> К сожалению, это не объясняет того, что происходит в финансовой и денежной сферах сегодня. После каждого краха банковскую систему спасают за государственный счёт. Старые методы ведения бизнеса возобновляются после небольшой настройки регуляторной или управленческой среды. Фундаментальная же структура — монополия на создание денег через банковский долг — неизменно остаётся нетронутой.

---

### 24. `p0538` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> As a starting point, let us distinguish between systems according to the characteristics of their causality mechanism. At one end of the spectrum lies simple *linear causality*. This concept dates back to the classical Greeks. Since Newton’s time, effective mathematical tools such as mechanics have been available to study processes involving linear causality. At the other end of the spectrum, one finds systems with a *lack of causality,* without interaction among variables. This latter realm is best explored with the mathematical tools of statistics. The domain of *complexity* lies between these two extremes; here, there are several causes interacting and there are multiple interactions between variables. Figure 4.1 illustrates this dynamic.

**В озвучку попало:**

> [thoughtful] Для начала давайте разделим системы по типу их причинно-следственных связей. На одном конце спектра находится простая линейная причинность. Эта концепция восходит еще к древним грекам. Со времен Ньютона у нас есть эффективные математические инструменты, такие как механика, для изучения процессов с линейной причинностью. На другом конце спектра находятся системы, где причинность практически отсутствует, а переменные не взаимодействуют друг с другом. Эту область лучше всего исследовать с помощью математического аппарата статистики. Область сложности лежит между этими двумя крайностями. Здесь действуют сразу несколько причин, которые постоянно взаимодействуют между собой.

---

### 25. `p0566` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> In general, a system’s resilience is enhanced by higher diversity and by more pathways (or connections) because there are numerous channels of interaction to fall back on in times of trouble or change. For example, a predator fish may ‘connect’ to – i.e., acquire energy and resources, usually by eating from – three or four other species (e.g. turtles and snakes) or it may link to only one (e.g. prawns). A fish depending on a single other species for its food supply will have difficulty adapting when that one species gets into difficulty. Researchers have therefore been able to use the amount of diversity and connectivity to quantify a system’s resilience.

**В озвучку попало:**

> [curious] Как правило, устойчивость системы повышается при большем разнообразии и наличии множества связей. Это дает системе запасные каналы взаимодействия на случай кризиса. Например, хищная рыба может получать энергию из трех-четырех разных источников, скажем, питаясь черепахами и змеями, а может зависеть только от одного вида, например, креветок. Если рыба зависит от единственного источника пищи, ей будет крайне трудно адаптироваться, когда у этого вида возникнут проблемы. Поэтому исследователи используют показатели разнообразия и связности для оценки устойчивости системы.

---

### 26. `p0568` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> The point being made here is profound and has wide-reaching implications for all complex flow systems, including our worldwide economy. Since resilience and efficiency are both necessary but pull in opposite directions, nature tends to select those systems which have an optimal balance of the two. The exact balance varies depending on the system. Therefore, we propose the working definition of sustainability as *the optimal balance between efficiency and resilience*. A system is maximally sustainable when that balance attains its optimal mix. In Appendix D1, a concrete example is provided of how this methodology applies to the three channels of carbon flow leading from freshwater prawns to the American alligator, via three intermediate predators: turtles, large fish and snakes, located in the Cypress wetlands of South Florida.

**В озвучку попало:**

> [serious] Мысль, которую мы здесь развиваем, имеет далеко идущие последствия для всех сложных систем, включая мировую экономику. Поскольку устойчивость и эффективность необходимы, но тянут систему в противоположные стороны, природа стремится выбирать те варианты, где найден оптимальный баланс. Этот баланс уникален для каждой системы. Поэтому мы предлагаем рабочее определение устойчивости как оптимального соотношения между эффективностью и устойчивостью. Система максимально устойчива, когда этот баланс достигает своего идеального сочетания. В приложении к книге приведен конкретный пример того, как эта методология применяется к потокам углерода в водно-болотных угодьях Южной Флориды.

---

### 27. `p0572` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Of perhaps even greater importance, the physics of flow networks also explains why excessively large and efficient organisations may pull the whole system toward collapse. In essence, large, highly efficient organisations in the network ‘out compete’ the smaller organisations for resources, drawing ever more energy, information and resources into the big, and away from the smaller participants.

**В озвучку попало:**

> Возможно, еще важнее то, что физика сетей потоков объясняет, почему чрезмерно крупные и эффективные организации могут привести всю систему к краху. По сути, такие организации в сети «выигрывают конкуренцию» у более мелких участников за ресурсы. Они забирают всё больше энергии и информации, обескровливая остальных.

---

### 28. `p0574` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> In conclusion: “Life tends to optimise, rather than maximise. Maximisation is another word for addiction.”³⁰ Indeed, in the real world, all networks corresponding to natural ecosystems operate around the optimal point, within a specific range called the ‘window of viability’, 31 which lies on either side of this optimum, as can be seen in Figure 4.5.

**В озвучку попало:**

> В заключение можно сказать: «Жизнь стремится к оптимизации, а не к максимизации. Максимизация — это другое слово для зависимости». В реальном мире все сети, соответствующие природным экосистемам, работают вокруг оптимальной точки. Они находятся в пределах особого диапазона, называемого «окном жизнеспособности», которое расположено по обе стороны от этого оптимума, как показано на рисунке 4.5.

---

### 29. `p0579` — длина озвучки / длина оригинала: 1.15; классы правки: —

**Исходный абзац:**

> The main point is that nature does not select for maximum efficiency but for an optimal balance between the two opposing poles of throughput efficiency and resilience. In other words, sustainability requires just enough, and not too much, of both efficiency and resilience. In most human-designed systems, and certainly in the monetary domain, we have been concerned only with efficiency, and have therefore tended to unduly sacrifice resilience.

**В озвучку попало:**

> [thoughtful] Главный вывод заключается в том, что природа стремится не к максимальной эффективности, а к оптимальному балансу между двумя противоположными полюсами: пропускной способностью и устойчивостью. Иными словами, для жизнеспособности системы требуется ровно столько эффективности и устойчивости, сколько нужно, и не более того. В большинстве созданных человеком систем, и особенно в финансовой сфере, мы заботились исключительно об эффективности, из-за чего зачастую неоправданно жертвовали устойчивостью.

---

### 30. `p0633` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> However, like all economists of his time and like many still today, Hayek remained a prisoner of the paradigm we call Traditional Economics (shown in Figure 2.1 on page 28). His concern was predominantly to find an appropriate balance between inflation and deflation, two important but purely financial issues. This is why his solution is about re-shaping the money creation process as a competition between financial institutions each emitting the same type of bank-debt money.

**В озвучку попало:**

> [thoughtful] Однако, как и все экономисты его времени, да и многие сегодня, Хайек оставался заложником парадигмы, которую мы называем традиционной экономикой. Его главной заботой был поиск баланса между инфляцией и дефляцией — двумя важными, но чисто финансовыми проблемами. Именно поэтому его решение сводится к изменению процесса создания денег через конкуренцию между финансовыми институтами, каждый из которых выпускает один и тот же тип банковских долговых обязательств.

---

### 31. `p0639` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Peer-reviewed theoretical and empirical evidence shows that *any* complex flow network is sustained only when diversity and interconnectivity lie within a specific range. A monoculture – a plurality reduced to only one single type of currency produced by one single type of agent – will, with 100% predictability, turn out not to be sufficiently resilient.

**В озвучку попало:**

> Теоретические и эмпирические исследования подтверждают: любая сложная сеть потоков устойчива лишь тогда, когда её разнообразие и взаимосвязанность находятся в определенных пределах. Монокультура, где всё многообразие сводится к единственному типу валюты, выпускаемой одним типом агентов, неизбежно теряет свою устойчивость. Это предсказуемо на сто процентов.

---

### 32. `p0644` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Similarly, the likelihood that we might change ‘human nature’ – Alan Greenspan’s explanation for the next crisis – amounts to renouncing on trying to stabilise the system. As long as we remain within the confines of a bank-debt money monopoly, there is indeed little hope.

**В озвучку попало:**

> Точно так же попытки изменить «человеческую природу» — как объяснял будущие кризисы Алан Гринспен — равносильны отказу от стабилизации системы. Пока мы остаемся в рамках монополии банковских долгов, надежды на перемены мало.

---

### 33. `p0756` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> Good lobbyists are expensive. Individuals and corporations who can thus pay for them have an advantage over those who cannot afford them. Grass-roots organisations, some non-governmental organisations and ordinary people affected by the same laws are often unable to pay for those expensive lobbyists.

**В озвучку попало:**

> Хорошие лоббисты стоят дорого. Частные лица и корпорации, которые могут себе их позволить, получают преимущество перед теми, у кого нет таких средств. Общественные движения, некоторые неправительственные организации и обычные люди, которых затрагивают одни и те же законы, зачастую не в состоянии оплатить услуги профессиональных лоббистов.

---

### 34. `p0768` — длина озвучки / длина оригинала: 1.18; классы правки: —

**Исходный абзац:**

> It is the ‘glue’ that makes a collection of individuals into a human society. It is a precondition for a functional democracy⁴⁰ and for securing economic prosperity.⁴¹ Indeed, political action and efficient markets are both unthinkable without a modicum of social capital.

**В озвучку попало:**

> [serious] Это тот «клей», который превращает совокупность индивидов в человеческое общество. Он является необходимым условием для функционирования демократии и обеспечения экономического процветания. Действительно, политические действия и эффективные рынки немыслимы без хотя бы минимального уровня социального капитала.

---

### 35. `p0781` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Many indirect indices have been used to measure social capital. They have ranged from education and income, to the percentage of women at work; from forms of business organisation and social safety nets, to the degree to which we can participate in the running of our society; from the freedom of the press, to the legal constitution of states. The availability of jobs and the quality of working conditions has a key influence on the formation of social capital. Regardless of the definition or data set used, the tendency over decades is a decrease in social capital in most developed societies.

**В озвучку попало:**

> Для оценки социального капитала используется множество косвенных показателей. Они варьируются от уровня образования и доходов до доли работающих женщин; от форм организации бизнеса и систем социальной защиты до степени нашего участия в управлении государством; от свободы прессы до конституционного строя. Наличие рабочих мест и качество условий труда играют ключевую роль в формировании социального капитала. Независимо от используемых определений или данных, в большинстве развитых обществ на протяжении десятилетий наблюдается снижение этого показателя.

---

### 36. `p0828` — длина озвучки / длина оригинала: 0.90; классы правки: truncated_sentence

**Исходный абзац:**

> Most economics textbooks define money as: a unit of account, a medium of exchange and a store of value. Because these are three *functions* of money, they characterise what money *does.* This is different from a definition of what money *is.* With such a widely accepted functional definition, there is actually little real inquiry into the *nature* of money. Our own working definition of money is as follows: ‘money is an *agreement* within a *community* to use something standardised as a *medium of* *exchange’*. In contrast with the traditional functional definition, if an agreement does not work, one can at least imagine changing it. One might also envisage that different instruments could perform some – but not necessarily all three – functions.² There are other examples of language traps.³ When an individual or a business gets a loan, the word used is ‘credit’. With governments however, the word used is always ‘debt’. The two processes are identical. But ‘credit’ has positive connotations – someone trusted you and considered you

**В озвучку попало:**

> Большинство учебников экономики определяют деньги через три функции: мера стоимости, средство обращения и средство накопления. Но это лишь описание того, что деньги делают, а не того, чем они являются на самом деле. Из-за такой популярности функционального подхода природа денег почти не исследуется. Мы же предлагаем свое рабочее определение: деньги — это соглашение внутри сообщества об использовании некоего стандартизированного объекта в качестве средства обмена. В отличие от традиционного подхода, если соглашение перестает работать, его можно изменить. Можно представить, что разные инструменты способны выполнять лишь некоторые из этих функций, а не все три сразу. Существуют и другие языковые ловушки. Когда кредит берет частное лицо или бизнес, мы используем слово «кредит». Но когда речь заходит о государстве, всегда говорят «долг». Хотя по сути это одни и те же процессы. Слово «кредит» звучит позитивно — вам доверились и сочли вас

---

### 37. `p0838` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> According to Ferguson, the dynamic between these four institutions explains the evolution of the nexus between power and modern money. A particularly effective synergy among these four institutions emerged for the first time in Britain during the 18th century. It is this synergy that made it possible for Britain to industrialise, defeat Napoleon, and build its empire. Let us briefly summarise the specific role played by each institution.

**В озвучку попало:**

> По мнению Фергюсона, динамика взаимодействия между этими четырьмя институтами объясняет развитие связи между властью и современными деньгами. Впервые особенно эффективная синергия между ними возникла в Британии в восемнадцатом веке. Именно она позволила Британии провести индустриализацию, победить Наполеона и построить империю. Давайте кратко подытожим роль каждого из этих институтов.

---

### 38. `p0843` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> The second player in the square of power is *parliamentary institutions,* which were created to represent taxpayers politically. Parliaments legitimised the budgetary process, thus enhancing a government’s capacity to raise revenue. “For most of history, direct taxation could be collected only with the cooperation of the richer group of society. For that reason, the widening of the direct tax ‘base’ has very often been associated with extensions of political representation, as taxpayers have traded shares of their income for participation in the political process, a fundamental part of which is the enactment of tax legislation. …The slogan ‘no taxation without representation’ neatly encapsulates the trade-off.”¹⁰ The expansion of access to the electoral process from a wealthy landowner elite to universal suffrage was the keystone marking the political evolution of the 19th century. The final step in achieving universal suffrage was attained during the early 20th century, when women were allowed to vote in most countries.

**В озвучку попало:**

> [thoughtful] Вторым участником «квадрата власти» являются парламентские институты, созданные для политического представительства налогоплательщиков. Парламенты узаконили бюджетный процесс, тем самым повысив способность правительства собирать доходы. На протяжении большей части истории прямые налоги можно было собрать только при содействии богатых слоев общества. По этой причине расширение базы прямого налогообложения очень часто связывали с расширением политического представительства. Налогоплательщики обменивали часть своего дохода на участие в политическом процессе, важной частью которого является принятие налогового законодательства. Лозунг «нет налогов без представительства» точно отражает этот компромисс. Расширение доступа к избирательному процессу от элиты богатых землевладельцев до всеобщего избирательного права стало ключевым моментом политической эволюции девятнадцатого века. Последний шаг к достижению всеобщего избирательного права был сделан в начале двадцатого века, когда женщинам в большинстве стран разрешили голосовать.

---

### 39. `p0879` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> Banks would thereby become simple intermediaries, service providers taking in deposits, holding a fraction as reserves and lending out the remainder. They would be forbidden to lend out *more* than the deposits they collected. In other words, banks would have to apply a 100% compulsory reserves rule and, since no bank-debt money could be created at all, banks would *de facto* be limited to the role of money brokers. Ironically, that is exactly what those who believe the Official Paradigm have believed all along!

**В озвучку попало:**

> В такой системе банки превратились бы в простых посредников. Они принимали бы депозиты, удерживали часть из них в качестве резервов, а остальное выдавали в кредит. Им запрещалось бы выдавать в долг больше, чем они получили от вкладчиков. Иными словами, банки обязали бы соблюдать правило стопроцентного резервирования. Поскольку создание денег через долг стало бы невозможным, банки фактически превратились бы в обычных брокеров. Ирония в том, что именно так, по мнению сторонников «официальной парадигмы», банки работают уже сейчас.

---

### 40. `p0882` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> In the USA, Paul Volcker, ex-Chairman of the Federal Reserve, is similarly pushing for some version of Glass-Steagall. In contrast, Congressman Dennis Kucinich is proposing the American Monetary Act,26 an equivalent of the Chicago Plan. On 26 July 2011, Kucinich invited Professor Kaoru Yamaguchi from the University of California at Berkeley and Doshisha University in Japan, to give a congressional monetary briefing on this idea. Yamaguchi’s paper 27 uses a systems approach to show that the liquidation of debts under the current monetary regime will trigger multiple recessions and massive unemployment in the USA with contagion to other economies. In contrast, under the American Monetary Act, debt reduction and even debt liquidation can be put into effect without causing recessions, unemployment and inflation, either in the USA or abroad.

**В озвучку попало:**

> В США Пол Волкер, бывший председатель Федеральной резервной системы, также выступает за возвращение к принципам закона Гласса — Стиголла. В то же время конгрессмен Деннис Кусинич предлагает «Американский денежный акт» — современный аналог «Плана Чикаго». 26 июля 2011 года Кусинич пригласил профессора Каору Ямагучи из Калифорнийского университета в Беркли и японского университета Дошиша для разъяснения этой идеи в Конгрессе. В своей работе Ямагучи использует системный подход, чтобы показать: ликвидация долгов при нынешнем денежном режиме приведет к череде рецессий и массовой безработице в США, что неизбежно затронет и другие экономики. Напротив, «Американский денежный акт» позволил бы сократить или даже списать долги без провоцирования рецессий, безработицы и инфляции как в США, так и за рубежом.

---

### 41. `p0944` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> Dozens of designs exist for innovative exchange media that meet these two criteria, some already operational, many still at the design stage. In combination with the conventional money system, mixes of these could create a great variety of monetary ecosystems. In the next two chapters we discuss nine examples. Each of the examples describes a system that:

**В озвучку попало:**

> Существуют десятки проектов инновационных средств обмена, отвечающих этим критериям. Некоторые уже работают, многие все еще находятся на стадии разработки. В сочетании с традиционной денежной системой их комбинации могут создать разнообразные финансовые экосистемы. В следующих двух главах мы обсудим девять примеров. Каждый из них описывает систему, которая:

---

### 42. `p0949` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Obviously, not *all* these systems need to be implemented for significant improvements to materialise. The German ‘Iron Chancellor ’ Bismarck is reported to have claimed that politics is the art of the possible. Each community, city or country can therefore decide how far it wants to go and how far it is possible, in practice, to stretch policies in new directions. We deliberately present a very broad range of pragmatic solutions simply to illustrate what is possible.

**В озвучку попало:**

> Очевидно, что для достижения значительных улучшений не обязательно внедрять абсолютно все эти системы. Немецкого «железного канцлера» Бисмарка часто цитируют: политика — это искусство возможного. Поэтому каждая община, город или страна может сама решать, как далеко она хочет зайти и насколько возможно на практике расширить границы политики. Мы намеренно представляем широкий спектр прагматичных решений, чтобы просто показать, что возможно сделать.

---

### 43. `p0974` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> More than twice the size of Belgium, it has a population of only 3.2 million. During the 14th century, it was the largest country in Europe, stretching from the Baltic Sea to the Black Sea. Given its small current size and lack of stereotypical tourist attractions, Dalia Grybauskaite, the first woman to become Lithuanian president, would like foreigners to visit Lithuania in order to learn something.

**В озвучку попало:**

> Страна по площади вдвое больше Бельгии, но ее население составляет всего три миллиона двести тысяч человек. В четырнадцатом веке Литва была крупнейшим государством Европы и простиралась от Балтийского до Черного моря. Учитывая небольшие размеры современной Литвы и отсутствие привычных туристических достопримечательностей, Даля Грибаускайте, первая женщина на посту президента страны, хотела бы, чтобы иностранцы приезжали в Литву ради новых знаний.

---

### 44. `p0990` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> Even if the medical care market were a theoretically ‘perfect’ one – with fully informed actors, no moral hazard, less asymmetry, more efficiency, fair access and so on – the economic preference for ‘sick and alive’ clients would remain a problematic bias. The current system thus makes it tempting to treat an obese patient who develops diabetes by using medication, rather than by using an early detection/ prevention approach with exercise and weight-loss programmes, to mitigate or even avoid the disease. In addition, improved technology has allowed an increase in the life expectancy of chronically ill individuals, with a corresponding increase in the consumption of health care resources. Prevention is thus side-lined in the face of this additional disease burden. The ‘sick and alive’ bias then becomes an additional cause for a market failure that contributes to the ineffective systemic organisation of health care services.

**В озвучку попало:**

> [thoughtful] Даже если бы рынок медицинских услуг был теоретически идеальным — с полностью информированными участниками, отсутствием морального риска и равным доступом, — экономическое предпочтение клиентов, которые «больны, но живы», оставалось бы серьезным искажением. Нынешняя система подталкивает врачей лечить диабет у пациента с ожирением с помощью лекарств, вместо того чтобы использовать раннюю диагностику, физические упражнения и программы снижения веса для предотвращения болезни. Кроме того, развитие технологий увеличило продолжительность жизни хронически больных людей, что привело к росту потребления медицинских ресурсов. В условиях такой нагрузки на систему профилактика отходит на второй план. Предвзятость «больной, но живой» становится дополнительным фактором провала рынка, который мешает эффективной организации здравоохранения.

---

### 45. `p1002` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> This approach would also be useful in setting up support groups. Creating pods of people who are tackling a weight problem can be a very effective way to get longer-term commitment. One could then create group objectives, which —when met — earn extra Wellness Tokens for the entire group.

**В озвучку попало:**

> Такой подход также полезен для создания групп поддержки. Объединение людей, которые вместе борются с лишним весом, — очень эффективный способ добиться долгосрочных результатов. Можно ставить общие цели, достижение которых приносит дополнительные велнес-токены всей группе.

---

### 46. `p1005` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> People earning Wellness Tokens could use them in a number of ways, including paying part of their insurance premiums with them¹⁵ or purchasing goods and services related to prevention or health promotion from providers pre-qualified by the Wellness Alliance. After a formal audit, local and regional businesses providing goods and services supporting preventive health care would become certified if their services and goods met specific health promotion criteria. This could include partial payment in Wellness Tokens for preventive care, biological or organic food or restaurants, health promotion/disease prevention courses, and sports equipment such as bicycles, to name just a few examples. In this way, a family earning Wellness Tokens because their children are maintaining their BMI could go shopping within the local community to buy organic food or a bicycle from participating vendors.

**В озвучку попало:**

> [thoughtful] Люди, зарабатывающие велнес-токены, могут использовать их по-разному. Например, ими можно оплатить часть страховых взносов или приобрести товары и услуги, связанные с профилактикой и укреплением здоровья. Продавцы таких товаров должны пройти аккредитацию в «Велнес-альянсе». После официальной проверки местные и региональные компании, поддерживающие профилактическую медицину, получают сертификат, если их товары и услуги соответствуют критериям программы. Это могут быть курсы по укреплению здоровья, профилактика заболеваний, органические продукты или спортивный инвентарь, например, велосипеды. Так, семья, которая получила токены за поддержание индекса массы тела детей в норме, сможет потратить их в местном магазине на полезную еду или покупку велосипеда.

---

### 47. `p1025` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> Investing in a natural resource as a secure long-term savings tool is not a new idea and has been done on an individual level for millennia. Even from an institutional standpoint, major insurance companies today own large forest plantations in Europe and the US for exactly that purpose. The novelty of this proposal is that such investments would be made available as an inflation-proof savings tool for everyone, including the poorer segments of the population.

**В озвучку попало:**

> [serious] Инвестирование в природные ресурсы как в надежный инструмент долгосрочных сбережений — идея не новая. На индивидуальном уровне люди пользуются этим тысячелетиями. Даже крупные страховые компании сегодня владеют обширными лесными плантациями в Европе и Соединенных Штатах именно для таких целей. Новизна нашего предложения заключается в том, чтобы сделать подобные инвестиции доступными для всех, включая наиболее бедные слои населения, в качестве инструмента сбережений, защищенного от инфляции.

---

### 48. `p1042` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> The value of an early redemption could be based on a value curve such as that shown in Figure 7.3, less a transaction fee. This fee would encourage share owners to use them primarily as a store of value continuing exchanges within the community rather than cashing shares in for conventional money. If this third option were made available, the Natural Savings Company would need to have access to sufficient cash (e.g. by securing a line of credit with a bank), to avoid a ‘run on the savings company’ – the equivalent to a ‘run on the bank’ in a conventional system.

**В озвучку попало:**

> Стоимость досрочного погашения может рассчитываться по графику роста цен за вычетом комиссии за транзакцию. Эта комиссия будет стимулировать владельцев использовать акции прежде всего как средство накопления и обмена внутри сообщества, а не обналичивать их. Если такая опция будет доступна, «Природным сбережениям» потребуется достаточный запас наличности, например, кредитная линия в банке. Это поможет избежать «набега на сберегательную компанию», аналогичного банковской панике в традиционной системе.

---

### 49. `p1066` — длина озвучки / длина оригинала: 1.16; классы правки: —

**Исходный абзац:**

> What are the benefits for governments? The greatest one is additional revenue from transactions that would otherwise not occur. Because this additional income ultimately becomes available in conventional national currency, the clearing-network does not upset existing procurement policies.

**В озвучку попало:**

> [curious] Каковы преимущества для правительств? Самое главное из них — это дополнительные доходы от транзакций, которые в противном случае не состоялись бы. Поскольку этот дополнительный доход в конечном итоге становится доступен в обычной национальной валюте, клиринговая сеть не нарушает существующую политику государственных закупок.

---

### 50. `p1122` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> In contrast, when the business cycle booms, both suppliers and corporations have an increased need for raw materials and demand for them goes up. The TRCs could be cashed in and used in the commodity markets. The amount of TRCs in circulation would decrease when the business cycle is at its maximum and counteract inflationary pressures. In summary, by providing monetary liquidity during phases when credit gets tight in the conventional system and contracting when business is booming, TRC-denominated exchanges would stabilise the overall business cycle.

**В озвучку попало:**

> [thoughtful] Напротив, во время экономического подъема спрос на сырье растет как у поставщиков, так и у корпораций. В этот период TRC можно обналичивать и использовать на товарных рынках. Объем TRC в обращении будет сокращаться на пике делового цикла, что поможет сдерживать инфляционное давление. Подводя итог: обеспечивая денежную ликвидность в периоды, когда в обычной системе кредитование затруднено, и сокращаясь во время бума, расчеты в TRC будут стабилизировать деловой цикл в целом.

---

### 51. `p1155` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> The City of Ghent wanted to encourage ecological and health-promoting activities, beautify the neighbourhood and improve the overall quality of life in Rabot. They started with a survey asking local residents what was most desirable to them. The answer was access to a small plot of land to grow vegetables and flowers. The city made land available, including an unused factory lot, on which over a hundred 4m² gardens were created. These little gardens have been made available for a yearly rent of 150 Torekes, payable only in Torekes.

**В озвучку попало:**

> Городские власти Гента стремились поощрить экологические и полезные для здоровья инициативы, а также улучшить внешний вид района и качество жизни в Работе. Они начали с опроса местных жителей, чтобы узнать, что для них важнее всего. Ответ был прост: доступ к небольшому участку земли для выращивания овощей и цветов. Город предоставил землю, включая заброшенную территорию завода, где было создано более сотни огородов площадью по четыре квадратных метра каждый. Эти участки можно арендовать за 150 Торекесов в год, причем оплата принимается исключительно в этой валюте.

---

### 52. `p1159` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> In addition to being used to pay rent for the gardens, Torekes can also be used to buy from local shops specific goods which the city encourages, including low-energy light bulbs and seasonal vegetables. Torekes can also be used to buy tickets for public transport and for the cinema (where otherwise empty seats would have remained unused). Businesses can exchange the Torekes for euros at the community centre office. These simple arrangements with participating stores benefit the residents, the local economy and the environment.

**В озвучку попало:**

> [serious] Помимо оплаты аренды садов, тореки можно использовать для покупки в местных магазинах товаров, которые поощряет городская администрация. К ним относятся энергосберегающие лампочки и сезонные овощи. Также за тореки можно приобрести билеты на общественный транспорт или в кино — на те места, которые иначе остались бы пустыми. Предприниматели могут обменять полученные тореки на евро в офисе общественного центра. Эти простые договоренности с магазинами-партнерами приносят пользу жителям, местной экономике и окружающей среде.

---

### 53. `p1170` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> - **7. ‘Biwa Kippu’: Funding a Regional Environmental Project** Lake Biwa in the Shiga Prefecture of Japan is one of the world’s oldest lakes and is graced with a very diverse and unusual ecosystem. However, the lake has become prone to a number of environmental problems: poor maintenance of water source forests; water contamination from industry, agriculture and households; algae blooms; as well as invasion of exotic fish species that have overwhelmed the native fish population. The Shiga prefectural government has used both environmental regulations and subsidies as policy instruments to address these issues. However, the question was raised: can additional policy instruments be used to obtain greater environmental results without increasing the budgetary burden on public authorities. The Biwa Kippu has been designed to be just such an instrument.

**В озвучку попало:**

> 7. «Бива Киппу»: финансирование регионального экологического проекта. Озеро Бива в префектуре Сига в Японии — одно из старейших в мире, оно обладает уникальной и разнообразной экосистемой. Однако озеро столкнулось с рядом экологических проблем: плохим состоянием лесов в водосборных бассейнах, загрязнением воды промышленными, сельскохозяйственными и бытовыми отходами, цветением водорослей, а также нашествием экзотических видов рыб, которые вытесняют местные виды. Правительство префектуры Сига использовало экологические нормы и субсидии для решения этих задач. Однако возник вопрос: можно ли использовать дополнительные инструменты для достижения лучших экологических результатов, не увеличивая нагрузку на бюджет? Система «Бива Киппу» была разработана именно как такой инструмент.

---

### 54. `p1235` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Notice that there is no obligation to personally perform any of the tasks rewarded in Civics. There are two ways to avoid participating at all. The first would be opting out by paying an extra amount in euros as part of one’s annual taxes. Based on our example, a logical amount would be the €1,000 per year estimated in the conventional process described at the beginning of our example. The second option for people not interested or without the time to personally perform the tasks, would be to purchase Civics via the online market openly and transparently. People having earned more Civics than they needed for their annual contribution could sell them on that market. The buyer of the Civics could make the purchase in conventional money or as an exchange for any good or service acceptable to the other party.

**В озвучку попало:**

> Заметьте, что никто не обязан лично выполнять задачи, за которые начисляются «сивики». Существует два способа вообще не участвовать в этой системе. Первый — отказаться от участия, выплатив дополнительную сумму в евро в рамках ежегодных налогов. Исходя из нашего примера, логичной суммой было бы 1000 евро в год, как мы и предполагали в начале. Второй вариант для тех, кто не заинтересован в выполнении задач или не имеет на это времени, — покупать «сивики» на открытом и прозрачном онлайн-рынке. Те же, кто заработал больше «сивиков», чем требовалось для ежегодного взноса, могут продать излишки. Покупатель может расплатиться за них как обычными деньгами, так и любыми товарами или услугами, которые устроят продавца.

---

### 55. `p1252` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> When describing the Civic system, the words ‘money’, ‘currency’ or ‘legal tender ’ were never needed or used. The EU treaty refers to ‘euro banknotes’ and ‘legal tender ’. The Civic does not need the status of ‘legal tender ’ in order to function. It is more cost-effective for the Civic to exist only in electronic form with a mobile phone system as the platform rather than be issued as notes. We will use the word ‘contributions’ when referring to Civics. and reserve the label ‘taxes’ for levies that can only be paid in euros.

**В озвучку попало:**

> При описании системы «Сивиков» слова «деньги», «валюта» или «законное платежное средство» не использовались и не требовались. Договор Европейского союза относится именно к банкнотам евро и законному платежному средству. «Сивику» не нужен статус законного платежного средства, чтобы функционировать. Экономически выгоднее, чтобы «Сивики» существовали только в электронном виде на базе мобильных телефонов, а не выпускались в виде банкнот. Мы будем использовать термин «взносы» при упоминании «Сивиков», а слово «налоги» оставим для обязательных платежей, которые можно внести только в евро.

---

### 56. `p1289` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> All nine innovative systems could also interact with the thousands of local and social currency experiments already under way around the world. The pioneers who started this movement should be recognised and honoured. They have started at grassroots level a massive education and learning process about monetary literacy that could become essential for informed decision-making in the 21st century.

**В озвучку попало:**

> Все девять инновационных систем могли бы взаимодействовать с тысячами экспериментов по использованию местных и социальных валют, которые уже проводятся по всему миру. Пионеров, начавших это движение, следует признать и поблагодарить. На низовом уровне они запустили масштабный процесс обучения и повышения финансовой грамотности. Эти знания могут стать необходимыми для принятия обоснованных решений в двадцать первом веке.

---

### 57. `p1309` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> In a sense, *The Future of Money* focused on the need to re-think money in order to answer the questions formulated by *The Limits to Growth*. Essentially this was because the conventional principle of creating money through interest-bearing bank credit has a *systemic growth obligation* built into it – not even necessarily out of ideological choice (although this can also be present as an additional factor), but out of sheer mechanical necessity. Therefore, seeking to counteract all the deleterious effects of economic growth without questioning the omnipresent monetary tool that drives this growth, could not work. But getting to the solution requires us to find a way to see some way around the monetary blind spot that we identified in Chapter II.

**В озвучку попало:**

> В некотором смысле, «Будущее денег» было посвящено необходимости переосмыслить финансы, чтобы ответить на вопросы, поставленные в работе «Пределы роста». Это важно, поскольку традиционный принцип создания денег через банковский кредит под проценты имеет встроенное системное требование постоянного роста. Это происходит не обязательно из-за идеологического выбора, а в силу простой механической необходимости. Поэтому попытки противостоять негативным последствиям экономического роста без пересмотра денежного инструмента, который этот рост подпитывает, обречены на провал. Чтобы найти решение, нам нужно преодолеть «денежное слепое пятно», о котором говорилось во второй главе.

---

### 58. `p1342` — длина озвучки / длина оригинала: 0.85; классы правки: —

**Исходный абзац:**

> Our sincere hope is that as the world of the old economy breaks down, the seeds of a new and more humane economy may be given a chance to emerge. “There is a rabbinical teaching that if the world is ending and the Messiah arrives, you first plant a tree; and then see if the story is true. Islam has a similar teaching that tells its adherents that if they have a palm cutting in their hand on Judgement Day, plant the cutting.”¹⁷

**В озвучку попало:**

> Мы искренне надеемся, что по мере разрушения старой экономики у семян новой, более гуманной системы появится шанс прорасти. Существует раввинистическое учение: если мир подходит к концу и приходит Мессия, сначала посади дерево, а потом посмотри, правдива ли эта история. В исламе есть похожее наставление: если в Судный день у тебя в руках саженец пальмы, посади его.

---

### 59. `p1359` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> Gwendolyn Hallsmith contributed many substantial ideas for Chapters II and VII. Sherry Cox has contributed clarity to all chapters. Last but not least, Stephanie Taché managed to incorporate a feminine sensitivity to what would otherwise be a heavier Report. The illustrations were produced with help from Thibault d’Ursel. Finally, Andrew Carey and Alison Melvin from Triarchy Press helped publish this book in record time, without compromising on quality.

**В озвучку попало:**

> Гвендолин Холлсмит внесла множество важных идей для второй и седьмой глав. Шерри Кокс помогла сделать текст всех глав более ясным. И, наконец, Стефани Таше сумела привнести женскую чуткость в то, что иначе могло бы стать слишком сухим отчетом. Иллюстрации были созданы при участии Тибо д’Урселя. Наконец, Эндрю Кэри и Элисон Мелвин из издательства Triarchy Press помогли выпустить эту книгу в рекордно короткие сроки, не жертвуя качеством.

---

### 60. `p1372` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The **Club of Rome**, an affiliation of individual members and over thirty associations all over the world, is unique. The network of Club members and their institutions is extensive. It draws on all sectors and disciplines, including senior individuals from the banking and financial sectors, scientists, academics, technologists, social scientists and philosophers. Many are world renowned, Nobel recipients and exceptional personalities. The members of the Club of Rome work on a wide variety of issues relevant to the future of humankind.

**В озвучку попало:**

> [thoughtful] Римский клуб — это уникальное объединение, в которое входят как отдельные участники, так и более тридцати ассоциаций со всего мира. Сеть членов клуба и связанных с ними организаций весьма обширна. Она охватывает все сферы деятельности и дисциплины: от банковского дела и финансов до науки, технологий, социологии и философии. Многие из участников — всемирно известные эксперты, лауреаты Нобелевской премии и выдающиеся личности. Члены Римского клуба работают над широким кругом вопросов, определяющих будущее человечества.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0645` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> Let us conclude this chapter with a metaphor. Conventional money plays the role of the red blood cells in your blood stream: they carry vital oxygen to all parts of the body. While red blood cells are necessary, they are not sufficient to keep your body healthy. Such a focus on only one type of cell would ignore the roles of white cells, platelets and dozens of other specialised hormones playing complementary functions to sustain your health. The existence of these complementary elements does not reduce the critical role or negate the existence of red blood cells. Likewise for the monetary domain, the key lesson from natural systems is to allow and even encourage the development of specialised media of exchange – other than a monoculture of conventional money created by bank debt – to circulate in parallel with the conventional national currency. While this approach may seem unorthodox, please remember that it is orthodoxy that has led us into our current troubles. Complex flow systems theory demonstrates that continued orthodoxy will compound the trouble. A plurality of media of exchange would provide new incentives and opportunities for all protagonists in the global economy, as will be illustrated in Chapters VII and VIII.

**В озвучку попало:**

> [curious] Давайте завершим главу метафорой. Обычные деньги играют роль эритроцитов в крови: они переносят жизненно важный кислород ко всем органам. Эритроциты необходимы, но их недостаточно для здоровья организма. Если сосредоточиться только на них, мы проигнорируем роль лейкоцитов, тромбоцитов и десятков гормонов, которые работают в комплексе. Наличие этих дополнительных элементов не умаляет значения эритроцитов. Так и в денежной сфере: главный урок природы в том, что нужно поощрять развитие специализированных средств обмена, которые будут циркулировать параллельно с национальной валютой. Этот подход может показаться неортодоксальным, но вспомните: именно ортодоксальные взгляды привели нас к нынешним проблемам. Теория сложных систем доказывает, что следование им лишь усугубит ситуацию. Множество средств обмена создаст новые стимулы для всех участников мировой экономики, что мы и покажем в следующих главах.

---

### 2. `p1001` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> We should insist that while the Wellness Token system is indeed aimed at improving behaviour with respect to health, it does not fall into the category of ‘neo-Victorian’ sanction mechanisms where people are denied financial support when they fall ill due (arguably) to specific behavioural patterns (i.e. get lung cancer while having been heavy smokers or get heart disease while having a history of detrimental eating habits). Our objective here, as we explained, is educational and has more to do with awareness building and the quest for personal autonomy. That is why the system clearly emphasises preventive rather than curative measures. The idea is not to use ‘financial incentives’ in order to scare people into changing their ways, as is the case with a sanction mechanism that kicks in when the disease is already present. There is indeed a *personal-responsibility-building* dimension to the Wellness Tokens, in the direction of what has been called ‘genuine autonomy’ of the patient in recent literature inspired by Ivan Illich.¹⁴ The system offers positive rather than negative incentives to motivate and reward people for their behaviours rather than punish them for ‘misbehaviours’. The perception should be that the system increases the opportunities available to people rather than imposing restrictions on them.

**В озвучку попало:**

> [thoughtful] Важно подчеркнуть: система велнес-токенов направлена на улучшение поведения, но не относится к тем «неовикторианским» механизмам санкций, где людей лишают финансовой поддержки из-за их образа жизни. Мы не наказываем тех, кто заболел, например, раком легких после многолетнего курения или страдает от болезней сердца из-за неправильного питания. Наша цель — просвещение, повышение осознанности и развитие личной автономии. Именно поэтому система делает упор на профилактику, а не на лечение. Мы не хотим использовать финансовые стимулы, чтобы запугивать людей, как это делают карательные механизмы, включающиеся уже после того, как болезнь возникла. Велнес-токены призваны развивать личную ответственность в духе концепции «подлинной автономии» пациента, вдохновленной работами Ивана Иллича. Система предлагает позитивные стимулы, поощряя людей за правильные действия, а не наказывая за ошибки. Она должна восприниматься как инструмент, расширяющий возможности, а не как система ограничений.

---

### 3. `p0634` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> From our perspective, based on the Ecological Economics Paradigm illustrated in Figure 2.3 (page 31), the issue of keeping both inflation and deflation at bay is also relevant, but represents only one of several relevant issues with regards to sustainability.

**В озвучку попало:**

> С нашей точки зрения, основанной на парадигме экологической экономики, задача сдерживания инфляции и дефляции также важна. Однако она представляет собой лишь один из аспектов устойчивого развития.

---

### 4. `p1268` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> Such an approach will undoubtedly be unpopular in many business circles. But let’s see it in the context of what took place in President Roosevelt’s office on 27 December, 1941, when he signed his executive order 9001 stating: “The Office of Production Management will bring about the conversion of manufacturing industries to war production, including the surveying of the war potential of industries, plant by plant; the spreading of war orders; the conversion of facilities; the assurance of efficient and speedy production…”⁶ The only argument given was that the United States had been at war since 7 December, and until that war was over, things would run differently. This was the only justification available and the only one needed.

**В озвучку попало:**

> Такой подход, несомненно, будет непопулярен в деловых кругах. Но давайте вспомним события 27 декабря 1941 года, когда президент Рузвельт подписал указ номер 9001. В нем говорилось, что Управление по производству должно обеспечить перевод промышленности на военные рельсы, включая оценку потенциала каждого завода, распределение военных заказов и перепрофилирование мощностей. Единственным аргументом было то, что Соединенные Штаты находятся в состоянии войны с 7 декабря, и до победы правила игры будут иными. Это было единственное оправдание, и его было достаточно.

---

### 5. `p0646` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> The remainder of this Report will explain why a strategy of multiple media of exchange makes not only theoretical, but also pragmatic sense. Randomly implementing exchange media other than conventional money may not be the best way forward. Rather, correctly designing and implementing exchange media to complement the current system and compensate for biases inherently generated by the conventional monetary system would be critically useful. The starting point for such a corrective, complementary strategy is to identify any existing biases and incentives that lead to unsustainable behaviour patterns. Only after understanding this built-in drift can we meaningfully choose from an infinity of potential new currency designs those that will best compensate for these propensities.

**В озвучку попало:**

> В оставшейся части отчета мы объясним, почему стратегия использования нескольких средств обмена имеет не только теоретический, но и практический смысл. Случайное внедрение новых инструментов — не лучший путь. Нам нужно грамотно проектировать их так, чтобы они дополняли текущую систему и компенсировали перекосы, порождаемые монополией банковского долга. Отправная точка такой стратегии — выявление скрытых стимулов, ведущих к неустойчивому поведению. Только поняв этот встроенный механизм, мы сможем выбрать из бесконечного множества вариантов те конструкции валют, которые лучше всего исправят ситуацию.

---

### 6. `p0993` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Wellness Tokens are specifically designed to use a preventive approach to promote and maintain the good health of participants. Just as ‘Frequent Flyer Miles’ are issued by airline alliances to induce a habit of taking the same airline for all one’s trips, Wellness Tokens would be issued by a Wellness Alliance to induce healthy habits. The members of the Wellness Alliance would be those organisations that have a financial interest in keeping the population healthy (e.g. insurance companies, local government and local employers). One of the purposes of the Wellness Token would be to generate changes in habits towards health promotion and disease prevention by encouraging healthy behaviours and emphasising preventive health care. Such an approach would also be a means of financing supportive care so that the elderly, the chronically ill and the disabled can remain in their own homes, and delay for as long as possible their entry into a long-term medical facility, where the costs escalate.

**В озвучку попало:**

> [serious] Велнес-токены специально разработаны для профилактического подхода к здоровью. Подобно тому, как авиакомпании выдают бонусные мили, чтобы приучить пассажиров летать именно их рейсами, «Велнес-альянс» будет выпускать токены для формирования здоровых привычек. В этот альянс войдут организации, финансово заинтересованные в здоровье населения: страховые компании, местные органы власти и работодатели. Одна из целей велнес-токенов — изменить привычки людей в сторону профилактики заболеваний и здорового образа жизни. Такой подход также позволит финансировать поддерживающий уход, чтобы пожилые, хронически больные и люди с инвалидностью могли дольше оставаться дома, откладывая момент переезда в медицинские учреждения, где расходы на их содержание резко возрастают.

---

### 7. `p1011` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> The Wellness Token is a win-win approach. Going back to our example, the children become healthier and less prone to illness; the family has additional resources to spend on health-related and health-promoting goods and services; the insurance alliance incurs fewer health care costs as a result of healthier clients; and healthcare providers increase their turnover. On a macroeconomic level, society benefits through lower rates of sick leave, increased productivity, less unemployment and greater social capital.

**В озвучку попало:**

> Система велнес-токенов выгодна всем. Вернемся к нашему примеру: дети становятся здоровее, семья получает дополнительные ресурсы на полезные товары и услуги, страховые компании тратят меньше на лечение, а поставщики услуг увеличивают оборот. На макроуровне общество выигрывает за счет снижения числа больничных, роста производительности труда, уменьшения безработицы и укрепления социального капитала.

---

### 8. `p1010` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> For the preventive care providers, the Wellness Token could function as a loyalty currency by attracting customers who might otherwise not patronise them. From a purely financial viewpoint, the role of a loyalty currency is to ensure that the value to the business generated by an exchange is always larger than the marginal cost in conventional money of serving an additional customer. The most logical participants are therefore businesses with comparatively low marginal costs. This is the case for many preventive health care providers. Some businesses have virtually no marginal monetary costs – think, for example, of a massage therapist who is not fully booked. But even a restaurant, for example, typically has marginal costs of about one third of its customers’ bills. This means that only one third of what customers spend pays for the food itself. There is usually another third that goes to fixed costs: renting the location, heating the room, paying the staff, etc. The final third is profit. Therefore, as long as a restaurant would not otherwise be full, it makes economic sense to bring in additional customers who pay partly in conventional money and partly in complementary currency.

**В озвучку попало:**

> Для поставщиков профилактических услуг велнес-токен работает как валюта лояльности, привлекая клиентов, которые иначе могли бы к ним не обратиться. С финансовой точки зрения, ценность такой валюты в том, что выгода от сделки всегда превышает предельные издержки на обслуживание дополнительного клиента. Поэтому выгоднее всего участвовать компаниям с низкими предельными издержками. Это характерно для многих оздоровительных центров. У некоторых из них дополнительные денежные затраты на клиента практически равны нулю — например, если у массажиста есть свободное время в графике. Даже в ресторане предельные издержки составляют лишь около трети от счета клиента. Остальное уходит на фиксированные расходы, такие как аренда, отопление и зарплата персонала, и на прибыль. Поэтому, если ресторан не заполнен полностью, экономически целесообразно привлекать клиентов, которые платят частично деньгами, а частично — дополнительной валютой.

---

### 9. `p1040` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> A second option would be to trade shares for goods or services within the community. The tree shares would thus function as a local medium of exchange and provide some additional liquidity in that community. In principle, the value of the exchange should reflect the value of the tree currency at the time of the exchange, but the owner of the shares and the person accepting them could decide for themselves the most appropriate arrangement.

**В озвучку попало:**

> Второй вариант — использовать акции для оплаты товаров или услуг внутри сообщества. Таким образом, древесные акции станут местным средством обмена и обеспечат дополнительную ликвидность. В идеале стоимость обмена должна соответствовать текущей ценности «древесной валюты», но владелец акций и получатель могут договориться об условиях самостоятельно.

---

### 10. `p0572` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Of perhaps even greater importance, the physics of flow networks also explains why excessively large and efficient organisations may pull the whole system toward collapse. In essence, large, highly efficient organisations in the network ‘out compete’ the smaller organisations for resources, drawing ever more energy, information and resources into the big, and away from the smaller participants.

**В озвучку попало:**

> Возможно, еще важнее то, что физика сетей потоков объясняет, почему чрезмерно крупные и эффективные организации могут привести всю систему к краху. По сути, такие организации в сети «выигрывают конкуренцию» у более мелких участников за ресурсы. Они забирают всё больше энергии и информации, обескровливая остальных.

---

### 11. `p0095` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> The World Business Academy has long been committed to advancing cutting-edge business information among business executives charged with navigating their businesses through the challenging times we live in. The Academy thank s Bernard Lietaer and his associates for presenting this Report to us, and encourages all levels of government and private enterprises to use the Report to begin a serious conversation on the critical issues the Report illuminates – while there is still time.

**В озвучку попало:**

> Всемирная бизнес-академия давно стремится предоставлять передовую информацию руководителям, которым приходится вести свои компании через непростые времена. Академия благодарит Бернара Литера и его коллег за этот отчет. Мы призываем правительственные структуры и частные предприятия использовать его, чтобы начать серьезный разговор о критически важных проблемах, пока у нас еще есть время.

---

### 12. `p0982` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> This Dora learning-economy is intended to operate in parallel with the conventional monetary system. We are, therefore, witnessing the beginnings of an exchange media ecosystem. At the end of the first planning session, one of the participants asked the 17-year-old whether he would be willing to teach English and get paid in *Lita* (the Lithuanian national currency), in dollars or in euros. His answer was, “No, I’d prefer to get paid in Dora, because that would get me closer to my dream. These other currencies only would get me the airline ticket!” For this teenager, the Dora had already become a ‘superior currency’, a currency that he preferred over all others. Doraland is an example of a complementary system that encourages non-spontaneous but desirable behaviour patterns. Figure 7.1 summarises the Doraland model in a flow diagram.

**В озвучку попало:**

> [serious] Эта экономика обучения на базе дор призвана функционировать параллельно с традиционной денежной системой. По сути, мы наблюдаем зарождение экосистемы обменных средств. В конце первой сессии планирования один из участников спросил того самого семнадцатилетнего юношу, готов ли он преподавать английский за литы, доллары или евро. Он ответил: «Нет, я бы предпочел получить оплату в дорах, потому что это приблизит меня к моей мечте. Другие валюты дадут мне только авиабилет». Для этого подростка дора уже стала «высшей валютой», которую он предпочел всем остальным. «Дораленд» — это пример дополнительной системы, которая поощряет не спонтанные, но желательные модели поведения.

---

### 13. `p0208` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> For the population at large, perhaps the most important learning needed is to understand non-linearity, specifically the difference between linear and exponential growth. We are now dealing with an increasingly non-linear world. Grasping these different dynamics will be useful in understanding what is happening to us, and what to do about it.

**В озвучку попало:**

> Для широкой общественности самое важное — осознать суть нелинейности, а именно разницу между линейным и экспоненциальным ростом. Мы живем во все более нелинейном мире. Понимание этих динамических процессов поможет разобраться в том, что с нами происходит и как на это реагировать.

---

### 14. `p0568` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> The point being made here is profound and has wide-reaching implications for all complex flow systems, including our worldwide economy. Since resilience and efficiency are both necessary but pull in opposite directions, nature tends to select those systems which have an optimal balance of the two. The exact balance varies depending on the system. Therefore, we propose the working definition of sustainability as *the optimal balance between efficiency and resilience*. A system is maximally sustainable when that balance attains its optimal mix. In Appendix D1, a concrete example is provided of how this methodology applies to the three channels of carbon flow leading from freshwater prawns to the American alligator, via three intermediate predators: turtles, large fish and snakes, located in the Cypress wetlands of South Florida.

**В озвучку попало:**

> [serious] Мысль, которую мы здесь развиваем, имеет далеко идущие последствия для всех сложных систем, включая мировую экономику. Поскольку устойчивость и эффективность необходимы, но тянут систему в противоположные стороны, природа стремится выбирать те варианты, где найден оптимальный баланс. Этот баланс уникален для каждой системы. Поэтому мы предлагаем рабочее определение устойчивости как оптимального соотношения между эффективностью и устойчивостью. Система максимально устойчива, когда этот баланс достигает своего идеального сочетания. В приложении к книге приведен конкретный пример того, как эта методология применяется к потокам углерода в водно-болотных угодьях Южной Флориды.

---

### 15. `p0644` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Similarly, the likelihood that we might change ‘human nature’ – Alan Greenspan’s explanation for the next crisis – amounts to renouncing on trying to stabilise the system. As long as we remain within the confines of a bank-debt money monopoly, there is indeed little hope.

**В озвучку попало:**

> Точно так же попытки изменить «человеческую природу» — как объяснял будущие кризисы Алан Гринспен — равносильны отказу от стабилизации системы. Пока мы остаемся в рамках монополии банковских долгов, надежды на перемены мало.

---

### 16. `p0271` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Conceptual relationships between the field of economics and the natural world can be described in three different ways. The most conventional view is to treat anything that is not dealt with unambiguously within one’s own theoretical framework as an ‘externality’ (see Figure 2.1). This economic view defines its own field as completely self-contained and excludes any other consideration as irrelevant. For instance, in such a view, the natural world is reduced to a resource, an input that is considered to be cost-free – to the extent that no money is exchanged to acquire it.

**В озвучку попало:**

> [serious] Концептуальные отношения между экономикой и миром природы можно описать тремя способами. Самый распространенный подход — рассматривать всё, что не вписывается в рамки текущей теории, как «внешний фактор». Эта экономическая модель определяет свою область как полностью замкнутую, а всё остальное считает неважным. Например, в такой системе мир природы сводится лишь к ресурсу или сырью. Если за получение этого ресурса не нужно платить деньги, он считается бесплатным.

---

### 17. `p1176` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> The intention is that the prefectural government should issue a new ordinance requiring resident households to contribute a certain amount of ‘Biwa Kippu’ environmental activities each year, for example 10 Biwas per family. One Biwa would roughly correspond to one hour of environmental service activities.

**В озвучку попало:**

> [serious] Предполагается, что префектура издаст постановление, обязывающее домохозяйства ежегодно вносить вклад в виде «Бива Киппу» — например, по десять единиц на семью. Один «Бива» будет примерно соответствовать одному часу экологической деятельности.

---

### 18. `p0906` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> So, contrary to what is often claimed, the degree of control central banks exert over the creation of bank-debt money is more theoretical than practical. Central banks are reduced to the role of pricing the marginal cost of reserve funds for the banking system. They determine only the cost of getting additional reserves from the central bank, a cost that banks pass on to their clients with an additional mark up. They do not determine the amount or timing of bank-debt money being created by the banks.

**В озвучку попало:**

> Таким образом, вопреки распространенному мнению, контроль центральных банков над созданием долговых денег скорее теоретический, чем практический. Их роль сводится к установлению цены на резервные фонды. Они лишь определяют стоимость получения дополнительных резервов, которую банки затем перекладывают на клиентов с наценкой. Но центральные банки не определяют ни объем, ни сроки создания банками новых долговых денег.

---

### 19. `p1267` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Wide consensus exists in both the scientific and the business world that the development of technologies to switch to a post-carbon world is possible but will require strong governmental leadership. Because many governments will experience a budget squeeze over the next decade, and because government subsidies are the usual way to fund environment conservation and protection measures, many corporations will be left passively waiting for funding to become available before deciding to tackle these issues on their own. The ECO changes this dynamic. In order to wage a war against climate change, governments could require contributions payable only in ECOs, thus giving value to the ECO. As discussed in Chapter V, any fiat currency (including bank-debt money) becomes valuable when a government requires it in payment of fees and taxes. The ECO would also spur serious innovations to reduce climate change.

**В озвучку попало:**

> В научном и деловом мире существует широкий консенсус: переход к пост-углеродному миру возможен, но требует решительного государственного лидерства. Многие правительства в ближайшее десятилетие столкнутся с бюджетными ограничениями. Поскольку субсидии — привычный способ финансирования защиты окружающей среды, многие корпорации будут пассивно ждать государственной поддержки, вместо того чтобы решать экологические проблемы самостоятельно. ЭКО меняют эту динамику. Требуя уплаты взносов исключительно в ЭКО, правительства придадут этим единицам реальную ценность. Как обсуждалось в пятой главе, любая фиатная валюта становится ценной, когда государство требует ее для оплаты сборов и налогов. Кроме того, ЭКО станут мощным стимулом для серьезных инноваций.

---

### 20. `p1041` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> A third option, requiring prudent management, would be for the Savings Company to allow the shares to be ‘cashed in’ for payment in conventional money before reaching maturity. This would be useful to build trust in the system. In situations where immediate cash was required, such as after an accident or disease, or for a wedding, this option would allow an individual or family to address the situation without having to dump the shares at a price below their real value.

**В озвучку попало:**

> Третий вариант требует осторожного управления. Сберегательная компания может разрешить досрочное погашение акций в обычной валюте до наступления срока их созревания. Это помогло бы укрепить доверие к системе. Если человеку или семье срочно нужны деньги — например, из-за болезни, несчастного случая или свадьбы, — такая возможность позволит решить проблему, не продавая акции по заниженной цене.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p0430` — длина озвучки / длина оригинала: 1.35; классы правки: —

**Исходный абзац:**

> In 2010, the US Census Bureau reported 4 million additional Americans in poverty, making a total of 44 million, or one in every seven residents. The rise was steepest for children, with one in five children affected.²¹ Because the crisis started later in Europe than in the USA, the full impact on poverty in Europe has not yet been fully documented.

**В озвучку попало:**

> В 2010 году Бюро переписи населения США сообщило о том, что число американцев, живущих за чертой бедности, увеличилось на 4 миллиона человек. Общее количество достигло 44 миллионов, то есть каждый седьмой житель страны оказался в бедственном положении. Наиболее резкий рост наблюдался среди детей: пострадал каждый пятый ребенок. Поскольку кризис в Европе начался позже, чем в США, полная картина влияния на уровень бедности в европейских странах пока не задокументирована.

---

### 2. `p0745` — длина озвучки / длина оригинала: 1.25; классы правки: —

**Исходный абзац:**

> We have found only one study of the transfer of wealth via interest. It was performed in Germany in 1982 when interest rates were at 5.5%.²⁸ The German population was grouped into ten income categories of 2.5 million households each. Over a one-year period, transfers between these ten groups totalled Deutsche Mark (DM) 270 billion in interest paid and received. Graphing the net interest transfers (interest gained minus interest paid) for each of these ten household categories allows us to see the net effect (see Figure 5.5).

**В озвучку попало:**

> [thoughtful] Нам удалось найти лишь одно исследование, посвященное перераспределению богатства через процентные ставки. Оно было проведено в Германии в 1982 году, когда процентная ставка составляла пять с половиной процентов. Население страны разделили на десять групп по уровню дохода, в каждой из которых было по два с половиной миллиона домохозяйств. За один год общая сумма выплаченных и полученных процентов между этими группами составила двести семьдесят миллиардов немецких марок. Если построить график чистого перераспределения процентов — то есть разницы между полученными и выплаченными суммами — для каждой из десяти категорий, мы увидим реальный эффект.

---

### 3. `p0161` — длина озвучки / длина оригинала: 1.25; классы правки: —

**Исходный абзац:**

> The bailouts, followed by a large-scale Keynesian stimulus plan to avoid a deflationary depression, have resulted in enormous budget deficits and additional public debt. In the twenty-three countries most directly affected by the banking crash, government debt jumped by an average of 24% of GDP.

**В озвучку попало:**

> Выплаты по спасению, за которыми последовал масштабный кейнсианский план стимулирования для предотвращения дефляционной депрессии, привели к огромному бюджетному дефициту и росту государственного долга. В двадцати трех странах, наиболее пострадавших от банковского краха, государственный долг вырос в среднем на двадцать четыре процента от валового внутреннего продукта.

---

### 4. `p1214` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> Conventional ways of raising funds include raising taxes or incurring debt. Although the latter involves the same amount of tax revenues over time, plus interest, both avenues directly affect city budgets. Non-profits would typically also be involved in such projects and their funding through tax-deductible donations indirectly reduce governmental income.

**В озвучку попало:**

> Традиционные способы привлечения средств включают повышение налогов или увеличение государственного долга. Хотя второй вариант со временем требует тех же налоговых поступлений, что и первый, плюс проценты, оба пути напрямую влияют на городской бюджет. Некоммерческие организации, как правило, также участвуют в подобных проектах, а их финансирование через пожертвования, не облагаемые налогом, косвенно сокращает доходы государства.

---

### 5. `p0157` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> Today’s foreign exchange and financial derivatives markets dwarf anything else on our planet. In 2010, the volume of foreign exchange transactions reached $4 trillion *per day*. One day’s exports or imports of *all* goods and services in the world amount to about 2% of that figure. Which means that 98% of transactions on these markets are purely speculative. This foreign exchange figure does not include derivatives, whose notional volume was $600 trillion – or eight times the entire world’s *annual* GDP in 2010.

**В озвучку попало:**

> [serious] Сегодняшние рынки иностранной валюты и финансовых деривативов затмевают собой всё остальное на нашей планете. В 2010 году объем валютных операций достигал четырех триллионов долларов в день. При этом объем мирового экспорта и импорта всех товаров и услуг за сутки составляет лишь около двух процентов от этой суммы. Это означает, что девяносто восемь процентов сделок на этих рынках носят чисто спекулятивный характер. В эту цифру даже не включены деривативы, условный объем которых составлял шестьсот триллионов долларов — это в восемь раз больше всего мирового годового валового внутреннего продукта за 2010 год.

---

### 6. `p0060` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> The CoR-EU is indebted to the World Academy of Art and Science, represented by Ivo Šlaus, President, and Garry J acobs, Chair of the Board and CEO, as well as to Felix U nger, President of the European Academy of Sciences and Arts for supporting this Report by co-signing these brief preliminary remark s.

**В озвучку попало:**

> Европейское отделение Римского клуба выражает признательность Всемирной академии искусств и науки в лице президента Иво Шлауса и председателя совета директоров и генерального директора Гарри Джейкобса. Мы также благодарим Феликса Унгера, президента Европейской академии наук и искусств, за поддержку этого отчета и соавторство в этих кратких вступительных замечаниях.

---

### 7. `p0670` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> From a systemic perspective, none of these effects is a simple linear cause-effect relationship. They also interact and even reinforce one another. The outcome is a set of built-in mechanisms that cause a bank-debt monopoly to be incompatible with sustainability in the long-term. We discuss each of these effects separately and attempt to describe their interactions at the end of the chapter.

**В озвучку попало:**

> [thoughtful] С системной точки зрения, ни один из этих эффектов не является простой линейной связью причины и следствия. Они взаимодействуют друг с другом и даже усиливают действие друг друга. В результате формируется набор встроенных механизмов, из-за которых монополия банковских кредитных денег становится несовместимой с устойчивым развитием в долгосрочной перспективе. Мы разберем каждый из этих эффектов отдельно, а в конце главы постараемся описать их взаимодействие.

---

### 8. `p0057` — длина озвучки / длина оригинала: 1.20; классы правки: —

**Исходный абзац:**

> At the time of writing these remark s we witness the dismantling of the state as guarantor of public good. Almost everything is for sale in most EU countries. Austerity is imposed at all levels. Public unrest will continue to grow unless new governance structures replace the obsolete ones.

**В озвучку попало:**

> [serious] В то время, когда пишутся эти строки, мы наблюдаем, как государство перестает быть гарантом общественного блага. Почти всё в большинстве стран Европейского союза выставлено на продажу. Повсюду вводятся меры жесткой экономии. Общественное недовольство будет расти до тех пор, пока устаревшие структуры управления не будут заменены новыми.

---

### 9. `p0605` — длина озвучки / длина оригинала: 1.20; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> Should we not learn from nature that growing to the point of becoming ‘too big to fail’ should never be allowed to happen? Instead, in the USA, the ten largest banks now control 42% of the market, compared to 28% before the 2008 crisis. This pattern is the perfect demonstration of what are known as ‘autocatalytic forces’ in natural ecosystems – forces that automatically lead to systemic crashes.

**В озвучку попало:**

> Не стоит ли нам поучиться у природы и понять, что нельзя допускать появления структур, которые становятся «слишком большими, чтобы обанкротиться»? В Соединенных Штатах сегодня десять крупнейших банков контролируют сорок два процента рынка, по сравнению с двадцатью восемью процентами до кризиса две тысячи восьмого года. Эта тенденция — наглядная демонстрация так называемых автокаталитических сил в природных экосистемах. Это силы, которые неизбежно ведут к системным крахам.

---

### 10. `p0338` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> The reference material for our analysis in this Report also includes the work known as ‘The Natural Step’, by Karl-Henrik Robert, a physician from Sweden who started by researching the systemic reasons for the escalating cancer rates in his medical practice. The Natural Step offers four system conditions that must be met for a sustainable world:

**В озвучку попало:**

> [serious] В качестве справочного материала для нашего отчета мы также используем концепцию под названием «Естественный шаг». Её разработал шведский врач Карл-Хенрик Роберт. Он начал свои исследования, пытаясь понять системные причины роста заболеваемости раком, с которыми столкнулся в своей медицинской практике. «Естественный шаг» предлагает четыре системных условия, необходимых для устойчивого развития мира.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1359` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Gwendolyn Hallsmith contributed many substantial ideas for Chapters II and VII. Sherry Cox has contributed clarity to all chapters. Last but not least, Stephanie Taché managed to incorporate a feminine sensitivity to what would otherwise be a heavier Report. The illustrations were produced with help from Thibault d’Ursel. Finally, Andrew Carey and Alison Melvin from Triarchy Press helped publish this book in record time, without compromising on quality.

**В озвучку попало:**

> Гвендолин Холлсмит внесла множество важных идей для второй и седьмой глав. Шерри Кокс помогла сделать текст всех глав более ясным. И, наконец, Стефани Таше сумела привнести женскую чуткость в то, что иначе могло бы стать слишком сухим отчетом. Иллюстрации были созданы при участии Тибо д’Урселя. Наконец, Эндрю Кэри и Элисон Мелвин из издательства Triarchy Press помогли выпустить эту книгу в рекордно короткие сроки, не жертвуя качеством.

---

### 2. `p0929` — совпадение символов с оригиналом: 18%; классы правки: truncated_sentence

**Исходный абзац:**

> Footnotes 1 John Kenneth Galbraith, *Money: Whence It Came, Where It Went* (1975), p.5. 2 For instance, the Natural Savings instrument presented in Chapter VII would mainly be a savings tool, not a medium of exchange or unit of account. In many civilisations, the unit of account was also different from the medium of exchange. A case in point is Homeric Greece, where the unit of account was the ox but where, for the sake of convenience, actual exchanges were often performed with ingots of bronze or other commodities. 3 For the arguments offered in this paragraph, see Philippe Derudder and André-Jacques Holbecq (2008) p.17. 4 Friedrich Nietzsche, *Thus Spoke Zarathustra,* translated by Adrian del Caro and edited by Robert Pippin (2006). 5 The original is elegantly succinct: *“Nervos belli, pecuniam infinitam”* from Cicero’s *Fifth* *Philippic.* See Jon Hall, *The Philippics*, in

**В озвучку попало:**

> Примечания. 1. Джон Кеннет Гэлбрейт, «Деньги: откуда они берутся и куда уходят» (1975), стр. 5. 2. Например, инструмент «Природные сбережения», представленный в седьмой главе, будет служить преимущественно средством накопления, а не средством обмена или расчётной единицей. Во многих цивилизациях расчётная единица отличалась от средства обмена. Показательный пример — гомеровская Греция, где расчётной единицей был бык, но для удобства сделки часто совершались с помощью бронзовых слитков или других товаров. 3. Аргументы, приведённые в этом абзаце, см. в работе Филиппа Деруддера и Андре-Жака Ольбека (2008), стр. 17. 4. Фридрих Ницше, «Так говорил Заратустра» (перевод Адриана дель Каро, под редакцией Роберта Пиппина, 2006). 5. Оригинал лаконичен: «Nervos belli, pecuniam infinitam» из «Пятой филиппики» Цицерона. См. Джон Холл, «Филиппики» в

---

### 3. `p0610` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> Furthermore, practically all governments are now heavily indebted, further tilting the bargaining power against them. As US Secretary of State Hillary Clinton has said according to WikiLeaks, “it is difficult to be tough with your banker…”³⁶ So, at least in the financial sector, a return to business as usual has been taking place remarkably quickly.

**В озвучку попало:**

> Более того, практически все правительства сейчас сильно закредитованы, что еще больше ослабляет их переговорные позиции. Как сказала госсекретарь США Хиллари Клинтон, согласно данным WikiLeaks, «трудно проявлять жесткость по отношению к своему банкиру». Поэтому, по крайней мере в финансовом секторе, возвращение к привычному положению дел происходит поразительно быстро.

---

### 4. `p0438` — совпадение символов с оригиналом: 17%; классы правки: —

**Исходный абзац:**

> This, in turn, sets the scene for further rounds of banking problems. Because all IMF data are based on government statistics provided by the countries involved, the comprehensiveness of this data is debatable. One exception is the case study of the 2007-2008 US banking crash.

**В озвучку попало:**

> Это, в свою очередь, создает условия для новых витков банковских проблем. Поскольку все данные Международного валютного фонда основаны на правительственной статистике стран-участниц, полнота этих данных вызывает вопросы. Одним из исключений является тематическое исследование банковского краха в США 2007–2008 годов.

---

### 5. `p0394` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> The global monetary system seems to run on automatic pilot. What’s more, the current global foreign exchange market dwarfs all other markets in history. By 2010, foreign exchange volumes had routinely reached the equivalent of $4 trillion *every working day.*¹

**В озвучку попало:**

> [serious] Глобальная денежная система, кажется, работает на автопилоте. Более того, нынешний мировой валютный рынок затмевает собой все остальные рынки в истории. К 2010 году объемы торгов на валютном рынке регулярно достигали эквивалента четырех триллионов долларов каждый рабочий день.

---

### 6. `p0047` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> We are not telling the truth about money. Yet money is at the core of the economy. And economy is ruling the world. It dominates human welfare from cradle to grave. It rules the use of the planet’s natural resources and the quality of the environment. Today it is generally admitted that many limits of the Earth’s ecosystem have been overshot. There is evidence that the present course is not sustainable.

**В озвучку попало:**

> [serious] Мы не говорим правду о деньгах. А ведь деньги — это основа экономики. Экономика же управляет миром. Она определяет благополучие человека от рождения до самой смерти. Она диктует, как мы используем природные ресурсы планеты и каким будет состояние окружающей среды. Сегодня уже общепризнано, что мы вышли за многие пределы возможностей земной экосистемы. Очевидно, что нынешний путь развития не является устойчивым.

---

### 7. `p0102` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> I used not to think this. Indeed, I did not think about the money system at all. I took it for granted as a neutral and inevitable aspect of human society. But since beginning to read Bernard’s analyses I have a very different view. He is not alone. For example Thomas Greco has written on this topic. But the depth of Bernard’s practical experience, theoretical understanding, and historical perspectives on the financial system leave him without peer.

**В озвучку попало:**

> Раньше я так не думал. По правде говоря, я вообще не задумывался о денежной системе. Я принимал её как нечто нейтральное и неизбежное, как данность человеческого общества. Но, начав читать аналитические работы Бернара, я изменил свой взгляд. И он не одинок в своих выводах. Например, на эту тему писал Томас Греко. Однако глубина практического опыта Бернара, его теоретические знания и исторический взгляд на финансовую систему делают его работу уникальной.

---

### 8. `p1341` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Is this scenario pie-in-the-sky? Are we offering just one more miraculous panacea? We do not think so. We have never claimed that a monetary ecosystem would be *sufficient* to address the challenges of today. We hope to have shown, however, that rethinking our money system is a *necessary* part of any solution. This is the core message of this Report.

**В озвучку попало:**

> Неужели это утопия? Предлагаем ли мы очередную чудодейственную панацею? Мы так не считаем. Мы никогда не утверждали, что денежная экосистема сама по себе достаточна для решения современных проблем. Мы надеемся, что смогли показать: переосмысление нашей денежной системы — это необходимая часть любого решения. В этом заключается основной посыл нашего доклада.

---

### 9. `p0750` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> Figure 5.5 clearly displays the systematic transfer of wealth from the bottom 80% of the population to the top 10%. This transfer was due exclusively to the monetary system in use. It is independent of the degree of cleverness or industriousness of the participants, the standard arguments given to justify large income differences.

**В озвучку попало:**

> [serious] Рисунок 5.5 наглядно демонстрирует систематический переток богатства от 80 процентов населения с наименьшими доходами к 10 процентам самых обеспеченных. Этот процесс обусловлен исключительно действующей денежной системой. Он никак не связан с уровнем способностей или трудолюбием участников — а именно эти аргументы обычно приводят для оправдания большого разрыва в доходах.

---

### 10. `p1138` — совпадение символов с оригиналом: 16%; классы правки: —

**Исходный абзац:**

> As explained at the beginning of this chapter, we are not elaborating on those useful and highly relevant systems here because they have already been described in detail elsewhere. They obviously could, and should, be part of an emergent monetary ecosystem.

**В озвучку попало:**

> Как мы объясняли в начале главы, мы не стали подробно останавливаться на этих полезных и важных системах, так как они уже детально описаны в других источниках. Очевидно, что они могли бы и должны стать частью формирующейся денежной экосистемы.

---
## Абзацы, оставшиеся в озвучке на английском (0)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.
## Пустые и почти пустые абзацы (23)

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

### 3. `p0124` — длина озвучки / длина оригинала: 0.85; классы правки: —

**Исходный абзац:**

> Dealing with the Eurozone Crisis… Another Way?

**В озвучку попало:**

> Кризис в еврозоне: есть ли другой путь?

---

### 4. `p0395` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Emergence of a ‘Global Casino’

**В озвучку попало:**

> ## 1. Появление «глобального казино»

---

### 5. `p0465` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 4. A Solution: The Privatisation of Everything?

**В озвучку попало:**

> ## 4. Решение: приватизация всего?

---

### 6. `p0495` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Source:Speech made in New York 25 October 2010 See:*www.qfinance.com ~ bit.ly/TPlink17* 2 ‘The Global Currency Game is Exploding’, *The Wall Street Journal*, 26 September 2007, pp.C1 and C3.

**В озвучку попало:**

> 

---

### 7. `p0496` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> 3 *The CIA Factbook 2012* estimates global GDP at purchasing power parity at US$78.98 trillion. 4 John Maynard Keynes, *The General Theory of Employment, Interest and Money* (1936), p.159. 5 Ludwig von Mises, *Human Action: A Treatise on Economics* (1949). 6 *The Financial Crisis Inquiry Report: Final Report of the National Commission of the Financial and Economic Crisis in the United*

**В озвучку попало:**

> 

---

### 8. `p0497` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *States* (2011). 7 Andrew Ross Sorkin, *Too Big to Fail* (2010). 8 Anton R. Valukas, Lehman Brothers Inc. Chapter 11 Proceedings Examiner’s Report (2010), downloadable from *http://lehmanreport.jenner.com ~ bit.ly/TPlink18* (visited: 8 January 2012). 9 ‘Restoring Ireland’s Credit by Reducing Uncertainty’, Remarks by Mr Patrick Honohan, Governor of the Central Bank of Ireland, at the Institute of International and European Affairs, Dublin, 7 January 2011, downloadable from *www.bis.org* ~ *bit.ly/TPlink19* (visited: 8 January 2012). 10 Máni Arnarson, Þorbjörn Kristjánsson, Atli Bjarnason, Harald Sverdrup and Kristín Vala Ragnarsdóttir*, Icelandic Economic*

**В озвучку попало:**

> 

---

### 9. `p0498` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Collapse: A Systems Analysis Perspective on Financial, Social and World System Links* (2011), online at *http://skemman.is* ~ *bit.ly/TPlink20* (visited: 8 January 2012). 11 See for instance Adrian Buckley, *Financial Crisis: Causes, Context and Consequences*, (2011), pp.74-88. 12 This is the IMF’s definition, “in a systemic banking crisis, a country’s corporate and financial sectors experience a large number of defaults and financial institutions and corporations face great difficulties repaying contracts on time. As a result, non-performing loans increase sharply and all or most of the aggregate banking system capital is exhausted. This situation may be accompanied by depressed asset prices (such as equity and real estate prices) on the heels of run-ups before the crisis, sharp increases in real interest rates, and a slowdown or reversal in capital flows. In some cases, the crisis is triggered by depositor runs on banks, though in most cases it is a general realisation that systemically important financial institutions are in distress… we exclude banking system distress events that affected isolated banks but were not systemic in nature. As a cross-check on the timing of each crisis, we examine whether the crisis year coincides with deposit runs, the introduction of a deposit freeze or blanket guarantee, or extensive liquidity support or bank interventions. This way we are able to confirm about two-thirds of the crisis dates. Alternatively, we require that it becomes apparent that the banking system has a large proportion of nonperforming loans and that most of its capital has been exhausted.” (*www.imf.org ~ bit.ly/TPlink21* p.5) 13 This is the IMF’s definition, “We identify and date episodes of sovereign debt default and restructuring by relying on information from Beim and Calomiris (2001), World Bank (2002), Sturzenegger and Zettelmeyer (2006), and IMF Staff reports. The information compiled includes year of sovereign defaults to private lending and year of debt rescheduling. Using this approach, we identify 63 episodes of sovereign debt defaults and restructurings since 1970.” (*www.imf.org ~* *bit.ly/TPlink21* p.6). More details can be found in Federico Sturzenegger and Jeromin Zettelmeyer, *Debt Defaults and Lessons from a Decade of Crises* (2006), table 1 in Chapter 1. 14 *Sources*: World Bank, IMF. Graph created by Michelle Bishop using IMF definitions and data from Gerard Caprio & Daniela

**В озвучку попало:**

> 

---

### 10. `p0499` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Klingebiel (1996); J. Frankel and A. Rose (1996); Graziela L. Kaminsky & Carmen M. Reinhart (1999); and, for the data after 2006, Luc Laevan & Fabian Valencia (2010). 15 The more detailed definition of a currency crisis as used by the IMF is “a nominal depreciation of the currency of at least 30% that is also at least a 10% increase in the rate of depreciation compared to the year before. In terms of measurement of the exchange rate depreciation, we use the percentage change of the end-of-period official nominal bilateral dollar exchange rate from the World Economic Outlook (WEO) database of the IMF. For countries that meet the criteria for several continuous years, we use the first year of each 5-year window to identify the crisis. This definition yields 208 currency crises during the period 1970-2007. It should be noted that this list also includes large devaluations by countries that adopt fixed exchange rate regimes.” (*www.imf.org ~* *bit.ly/TPlink21* p.6). 16 Rüdiger Dornbusch, Yung Chul Park and Stijn Claessens, ‘Contagion: How It Spreads and How It Can Be Stopped’, *World Bank*

**В озвучку попало:**

> 

---

### 11. `p0500` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Research Observer*, Vol. 15, issue 2 (August 2000), pp.177-197. 17 See *www.nytimes.com ~ nyti.ms/TPlink22* 18 George Kaufman, ‘Banking and Currency Crises and Systemic Risk: Lessons From Recent Events’, *Economic Perspectives: A*

**В озвучку попало:**

> 

---

### 12. `p0527` — длина озвучки / длина оригинала: 0.97; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 1. The Misclassification of Economics

**В озвучку попало:**

> ## 1. Ошибочная классификация экономики

---

### 13. `p0559` — длина озвучки / длина оригинала: 0.81; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## 3. The Physics of Complex Flow Networks

**В озвучку попало:**

> ## 3. Физика сложных сетей потоков

---

### 14. `p0702` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Wate r lilie s s pre ading in a pond**

**В озвучку попало:**

> **Распространение кувшинок в пруду**

---

### 15. `p0808` — длина озвучки / длина оригинала: 0.01; классы правки: year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Quoted in Naomi Klein, *No Logo: Taking Aim at the Brand Bullies* (2000), p.325. 2 See Appendix A for a layperson’s introduction to how bank debt creates money. 3 Heading of an article in *The Economist* January 7th, 2012 p.58. 4 At the time of this writing (in January 2012) bank deposits held overnight at the ECB are reaching an unprecedented level of more than €400 billion (see *The Economist*, 31 December 2011, p.56). 5 All Austrian-school theorists consider the unsustainable expansion of bank credit through fractional reserve banking as the driving force of most business cycles. See, e.g. Detlev S. Schlichter (2011). From a different perspective, Irving Fisher in the 1930s, Hyman Minsky in the 1970s and Barry Eichengreen nowadays have also pointed to this pro-cyclical money creation process as an amplifier of the business cycle. See also Milton Friedman, ‘The Role of Monetary Policy’, *American Economic Review*, vol. 68 (1968), pp.1–17. We are not claiming that this process is the only cause of the business cycle, but that it is a contributing factor directly attributable to the prevailing monetary system. See Olivier J. Blanchard & Mark W. Watson (1987). See also ‘Shadow Government Statistics’ at *www.shadowstats.com* 6 See Milton Friedman & Anna Jacobson Schwartz (1993); J. P. Keeler (2001); Barry Eichengreen & K. Mitchener (2003); Carmen

**В озвучку попало:**

> Примечания

---

### 16. `p0809` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_lost

**Исходный абзац:**

> Reinhart *et al.* (2004). 7 Adrian Blundell-Wignall and Paul Atkinson, ‘Thinking Beyond Basel III: Necessary Solutions for Capital and Liquidity’, *Financial*

**В озвучку попало:**

> 

---

### 17. `p0937` — длина озвучки / длина оригинала: 0.65; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ## Examples of Private Initiative Solutions

**В озвучку попало:**

> ## Примеры частных инициатив

---

### 18. `p0954` — длина озвучки / длина оригинала: 0.58; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Box 7.1 – Me nu of Motivation Sys te ms

**В озвучку попало:**

> ### Меню систем мотивации

---

### 19. `p1123` — длина озвучки / длина оригинала: 0.68; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> **Benefits for participating businesses**

**В озвучку попало:**

> **Преимущества для бизнеса**

---

### 20. `p1140` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> Footnotes 1 Lietaer (2001); Lietaer & Kennedy (2008); Greco (2009); Lietaer & Belgin (2011); Hallsmith & Lietaer (2011). 2 For applications at a city level, see in particular Gwendolyn Hallsmith and Bernard Lietaer, *Creating Wealth: Growing Local*

**В озвучку попало:**

> 

---

### 21. `p1141` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Economies with Local Currencies* (2011). 3 Arrow (1963) and Reinhardt (2001). 4 M. Rothschild and J. E. Stiglitz, “Equilibrium in Competitive Insurance Markets” (1976); D. Cutler and R. Zechhauser, *Insurance*

**В озвучку попало:**

> 

---

### 22. `p1142` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> *Markets and Adverse Selection: A Handbook for Health* *Economists* (1998). 5 Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine.* 6 *U.S. Health* (2005) National Center for Health Statistics, Department of Health and Human Services, No: 2005-1232. 7 “Behavioral and social interventions therefore offer great promise to reduce disease morbidity and mortality, but as yet their potential to improve the public’s health has been relatively poorly tapped.” Committee on Capitalizing on Social Science and Behavioral Research to Improve the Public’s Health (2000) *Institute of Medicine*. 8 L.A. Nefiodow, *Der Sechste Kondratieff* (2001). See also Appendix G for more information on Nicolai Kondratieff and ‘long waves’. 9 In the Netherlands an alliance involving the largest insurance company is planning to introduce several city-scaled experiments for motivation systems to deal with the ageing wave of the next decades. 10 Indeed not all preventive programmes are cheaper than the treatment . Studies show that it is more cost effective to treat tuberculosis rather than prevent it. See Borgdorff *et al*. (2002). Influenza vaccination is not cost effective for healthy working adults. See Bridges *et al*. (2000). However, all of these studies only compare the costs for treatment and the costs for prevention. They do not take into consideration the decrease in productivity and the absenteeism due to illness. 11 The most significant benefits occur after the second or third year of the programme. One hundred dollars or euros spent on preventive care programmes per year and per employee will have an ROI after the third year of 300 dollars or euros. See Goetzel (1999); Erfurt (1992); Powell (1999) and Chapman (2003). 12 Lia *et al.* (2008); Bastagli (2009). 13 See *www.cdc.gov* ~ *1.usa.gov/TPlink47n* 14 See Christian Léonard, *Croissance contre santé: Quelle responsabilisation du malade?* (2008). While Léonard, a leading Belgian health care expert, is strongly critical of the current ideology of punitive ‘responsibilisation’ of patients, he does argue in favour of a “genuine” autonomisation, which he links to Ivan Illich’s ideas of autonomy and conviviality: genuine personal responsibility can only flow from a reappropriation, by the patient him/herself, of his/her health. This requires preventive measures, which are under-financed in the current “alive and sick” logic. The Wellness Token system, therefore, moves in the direction called for by Léonard. 15 The Elderplan insurance company in the New York area has implemented successfully part of this idea with a Time Dollar currency.

**В озвучку попало:**

> 

---

### 23. `p1143` — длина озвучки / длина оригинала: 0.00; классы правки: paragraph_emptied, year_dropped_with_reference_apparatus

**Исходный абзац:**

> They have discovered that people participating in a Time Dollar system remain on average healthier because of a better social capital environment. 16 Lia *et al.* (2008); Paxson & Schady (2007). 17 The Swiss business-to-business currency system WIR has been successfully operating on this principle for 75 years. 18 C. J. Ruhm, *Macroeconomic Conditions, Health and Government Policy* (2006). 19 The text of this section is extracted and summarised from Marek Hudon and Bernard Lietaer, ‘Natural Savings: A New Microsavings Product for Inflationary Environments – How to Save Forests with Savings For and By the Poor?’, *Savings and Development*, vol. 4 (2006), pp.357-381 20 If the property is owned by a third party, one could also arrange for a long-term lease of the necessary land and pay the owner in part or whole with shares in the Natural Savings Company. 21 Depending on the size of the land and the community, one could make this a continuous process, with new plantations and harvest on parts of the total forest on a periodic, rotating basis. Well-known forestry management techniques should be applied as appropriate. 22 Lietaer (2001). 23 Dolde (1993). 24 See for example: Harmon (1959); Graham (1937) and (1944); Hart *et al.* (1964); Grondona (1975); Gondriaan (1932) and Jevons (1875).

**В озвучку попало:**

> 

---
