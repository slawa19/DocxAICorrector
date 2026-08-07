# Аудиокнига, финальный подтверждающий прогон 2026-08-06 — rethinking_money, материал для просмотра глазами

Книга: Bernard Lietaer & Jacqui Dunne, *Rethinking Money* (`tests/sources/book/Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_fin2_rethinking_money`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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

1. **Случайная выборка, 55 абзацев прозы** — до 20 из первой, средней и последней трети книги,
   `random.Random(20260804)`, без отбора «по красоте».
2. **20 абзацев с максимальным сжатием** — низ списка по отношению длин.
3. **10 абзацев с максимальным раздуванием** — верх того же списка.
4. **10 самых буквальных абзацев** — максимальное совпадение символов с оригиналом.
5. **1 абзацев, оставшихся в озвучке на английском** (порог ≥ 60 букв, кириллицы < 30 %).
6. **Пустые и почти пустые абзацы — все 24**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 1736; вернулось: 1735;
дошло до narration-артефакта: 1732.
Пул прозы, из которого делалась выборка: 670 абзацев.
Медианное отношение длин по прозе: 0.9741.

---
## Случайная выборка (55 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0018` — длина озвучки / длина оригинала: 1.11; классы правки: truncated_sentence

**Исходный абзац:**

> “The new understanding this book offers is critical because economics has become the dominant—and increasingly only—discipline with which important decisions are being made. This is a must-read for anyone who wants to be part of the timely conversation on how to move forward to create the just, sustainable, and equitable world we all desire.” —Thom Hartmann, internationally syndicated talk show host and author of twenty-four books

**В озвучку попало:**

> «Новое понимание, которое предлагает эта книга, критически важно, поскольку экономика стала доминирующей — и все чаще единственной — дисциплиной, на основе которой принимаются важные решения. Это обязательное чтение для каждого, кто хочет участвовать в своевременном разговоре о том, как двигаться вперед к созданию справедливого, устойчивого и равноправного мира, которого мы все желаем». — Том Хартманн, ведущий международного синдицированного ток-шоу и автор двадцати четырех книг

---

### 2. `p0090` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> Soon money became the tool empires used in a global dash for assets in a world that didn’t seem to lack for earth, water, air, and natural resources. A contrivance of competition, it pitted one against the other in a fabricated Darwinian contest of survival, refl ecting and perpetuat-ing the values and the Zeitgeist of that time.

**В озвучку попало:**

> Вскоре деньги стали инструментом империй в глобальной гонке за активами в мире, где, казалось, не было недостатка в земле, воде, воздухе и природных ресурсах. Будучи механизмом конкуренции, они стравливали людей друг с другом в искусственной дарвиновской борьбе за выживание, отражая и закрепляя дух того времени.

---

### 3. `p0103` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Regular people have discovered not only that it is possible to create money in suffi ciency for their needs but also that it is simultaneously possible to build their societies with greater cooperation, care, and collaboration. In other words, they are proving not only that it is possible to redesign money but also that doing so fosters very different and highly desirable outcomes.

**В озвучку попало:**

> Обычные люди обнаружили, что можно не только создавать деньги в достаточном для своих нужд количестве, но и одновременно строить общество на принципах сотрудничества, заботы и взаимодействия. Иными словами, они доказывают, что можно не только перепроектировать деньги, но и что это приводит к совершенно иным и весьма желанным результатам.

---

### 4. `p0134` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> In the history of the United States, this is the fi rst time when the younger generation of people will be poorer and less educated than their parents.² In a country that claims to be one of the richest in the world, some 100 million people— one in three Americans— either lives in poverty or in the distressed zone hovering just above the offi cial poverty threshold.³ More than one in three Americans lived in house holds that received Medicaid, food stamps, or other means- based government assistance in mid- 2010, according to an analysis of the 2010 census. And when Social Security, Medicare, and unemployment benefi ts are included, nearly half of the nation lived in a house hold that received a government check.⁴ According to the *New York Times*, “Demographically, they look more like ‘The Brady Bunch’ than ‘The Wire.’ Half live in house holds headed by a married couple; 49 percent live in the suburbs. Nearly half are non- Hispanic white, 18 percent are black, and 26 percent are Latino. Perhaps the most surprising fi nding is that 28 percent work full- time, year round. These estimates defy the ste reo types of low-income families.”⁵

**В озвучку попало:**

> В истории Соединенных Штатов это первый случай, когда молодое поколение будет беднее и менее образованно, чем их родители. В стране, которая претендует на звание одной из самых богатых в мире, около ста миллионов человек — каждый третий американец — живут либо в нищете, либо на грани официального уровня бедности. Согласно анализу переписи 2010 года, более трети американцев проживали в домохозяйствах, получавших государственную помощь: талоны на питание, медицинское страхование для малоимущих или другие пособия. А если учесть социальное страхование, пенсионное обеспечение и пособия по безработице, то почти половина страны жила в семьях, получавших государственные выплаты. Газета «Нью-Йорк Таймс» отмечала: «Демографически они больше похожи на героев сериала "Семейка Брейди", чем на персонажей "Прослушки". Половина живет в семьях, возглавляемых супружеской парой, сорок девять процентов — в пригородах. Почти половина — белые нелатиноамериканского происхождения, восемнадцать процентов — чернокожие, двадцать шесть процентов — латиноамериканцы. Пожалуй, самый удивительный факт заключается в том, что двадцать восемь процентов работают полный рабочий день круглый год. Эти данные разрушают стереотипы о малообеспеченных семьях».

---

### 5. `p0141` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> Yet, the commonly trotted- out explanations for all that ails the fi - nancial systems, or conversely what is working, just don’t provide the complete picture. There is a yearning to put into language something that still remains elusive, lingering in the shadows of awareness just out of reach. It’s that gnawing feeling in the pit of the stomach that something deeper is going on, something that can’t quite be brought to consciousness, let alone expressed in words.

**В озвучку попало:**

> И все же общепринятые объяснения того, что не так с финансовыми системами или, наоборот, что в них работает, не дают полной картины. Существует потребность выразить словами то, что до сих пор остается неуловимым, скрываясь в тенях нашего сознания. Это грызущее чувство в глубине души, что происходит что-то более глубокое, что невозможно до конца осознать, не говоря уже о том, чтобы выразить словами.

---

### 6. `p0146` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> At the core of these assumptions is the false belief that it is merely the lack of money that is the problem. If there were more to go around, everything could be put to rights. However, what you’ll discover in the following pages is this: It is not the *amount* of money in circulation that is the root cause of this current malaise. It’s the *type* of money that is being used.

**В озвучку попало:**

> В основе этих заблуждений лежит ложное убеждение, будто проблема лишь в нехватке денег. Мол, если бы их было больше, всё наладилось бы само собой. Однако на следующих страницах вы узнаете, что корень нынешних проблем кроется не в количестве денег, находящихся в обращении, а в самой их природе.

---

### 7. `p0172` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> And fi nally, and perhaps most important, is the *crisis of identity,* particularly for those who have inherited wealth. The questions of self- worth and one’s uniqueness, which arise for everyone, become much more painful when one is seen by others as having money. Phi los-o pher Jacob Needleman observes, “The only thing that money will not buy is meaning.”¹⁷ Often, wealthy people suffer from guilt, anxiety, and a sense of meaninglessness.

**В озвучку попало:**

> И, наконец, самое важное — это кризис идентичности, особенно для тех, кто получил наследство. Вопросы самооценки и собственной уникальности, которые возникают у каждого, становятся гораздо болезненнее, когда окружающие видят в тебе прежде всего деньги. Философ Джейкоб Нидлман отмечает: «Единственное, что нельзя купить за деньги, — это смысл». Часто богатые люди страдают от вины, тревоги и ощущения бессмысленности жизни.

---

### 8. `p0173` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> In an environment and culture where so much is shaped by fi nancial worth, the scarcest commodity seems to be trust. Indeed, each of these four conditions shares a common thread— the loss of trust in society, in friends, in family, and fi nally, in oneself. An all- too- common response to the issues faced by the wealthy is “I wish I had that problem.” This denies, however, the depth of the anguish experienced by some and the reality that money has become an equal- opportunity problem maker.

**В озвучку попало:**

> В культуре, где так многое определяется финансовым состоянием, самым дефицитным товаром кажется доверие. Действительно, все эти четыре состояния объединяет общая нить — потеря доверия к обществу, друзьям, семье и, наконец, к самому себе. Слишком распространенная реакция на проблемы богатых — «хотел бы я иметь такие проблемы». Однако это отрицает глубину страданий, которые испытывают некоторые люди, и тот факт, что деньги стали источником проблем для всех, независимо от достатка.

---

### 9. `p0252` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> As economists Clifford Cobb, Ted Halstead, and Jonathan Rowe point out, “The GDP not only masks the breakdown of the social structure and the natural habitat upon which the economy— and life itself— ultimately depend; worse, it actually portrays such breakdown as economic gain.”¹⁰ Herman Daly put it this way: “The current national accounting system treats the earth as a business in liquidation.”¹¹

**В озвучку попало:**

> Как отмечают экономисты Клиффорд Кобб, Тед Холстед и Джонатан Роу, валовой внутренний продукт не только маскирует разрушение социальной структуры и природной среды, от которых в конечном счете зависят экономика и сама жизнь; хуже того, он фактически изображает это разрушение как экономический выигрыш. Герман Дейли выразился еще резче: «Нынешняя система национальных счетов рассматривает Землю как бизнес в стадии ликвидации».

---

### 10. `p0343` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The fi rst eight groups of house holds are in the negative, which means that they have paid out more in interest than they received. In the ninth group, interest gained and paid roughly cancel each other out. However, in the tenth group, the total gains add up to the total losses of the fi rst eight groups.

**В озвучку попало:**

> Первые восемь групп домохозяйств оказались в минусе: они выплатили по процентам больше, чем получили. В девятой группе полученные и выплаченные проценты примерно уравновесили друг друга. Однако в десятой группе общая сумма доходов по процентам в точности совпала с суммарными потерями первых восьми групп.

---

### 11. `p0382` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> There are thousands of new monetary pacts operating within communities in the United States and beyond that are not conducted solely with legal tender, leading to some very different outcomes. These pacts are called “common tender,” in contrast with “legal tender.”

**В озвучку попало:**

> Сегодня в США и других странах действуют тысячи новых денежных соглашений, которые не ограничиваются законным платежным средством. Они приводят к совершенно иным результатам. Такие соглашения называют «общепринятыми средствами платежа» в противовес «законным».

---

### 12. `p0390` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> Today, we have a plethora of both unmet needs and unused resources. Cooperative currencies tie these together and get the fundamental circuit of giving and receiving, buying and selling, moving again as people get their lives back on track. Completely new circuits of trade are being established by ordinary people as they create new solutions to their area’s problems. Accordingly, a community can be anything from a small local neighborhood to a group of multinational companies doing business together. The actual currency can address many issues: for example, the creation of an el der ly care currency, an energy conservation currency, or a local food- growing currency. When and wherever there is an unused resource and an unmet need in an economy, they can be linked with a purposefully designed currency. The or ga ni za tion responsible for the issuance of a currency can be a nonprofi t, a religious entity, a business federation, a community group, a union, a company, a government agency, or, of course, any body of government from a municipality to the federal echelon. In reality, the only conceptual limitation is imagination. Together with conventional national currencies, they can form what we call a monetary ecosystem.

**В озвучку попало:**

> Сегодня у нас в избытке как неудовлетворенных потребностей, так и неиспользуемых ресурсов. Кооперативные валюты связывают их воедино, запуская фундаментальный цикл обмена: отдачи и получения, покупки и продажи. Это помогает людям вернуться к нормальной жизни. Обычные люди создают совершенно новые торговые цепочки, находя собственные решения проблем своего региона. Сообществом при этом может быть что угодно: от небольшого квартала до группы транснациональных компаний. Такая валюта может решать самые разные задачи. Например, оплата ухода за пожилыми людьми, поощрение энергосбережения или поддержка местного фермерства. Везде, где есть неиспользованный ресурс и неудовлетворенная потребность, их можно связать с помощью специально разработанной валюты. Эмитентом может выступать кто угодно: некоммерческая организация, религиозная община, бизнес-федерация, профсоюз, компания или государственный орган любого уровня — от муниципалитета до федерального центра. По сути, единственное ограничение здесь — это наше воображение. Вместе с обычными национальными деньгами такие валюты формируют то, что мы называем денежной экосистемой.

---

### 13. `p0558` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> In the case of simple barter exchanges, where no currency is involved at all, the only effect of such an exchange is who owns what. No infl ationary pressures arise from barter exchanges, given that the overall quantity of both goods and currency in circulation remains unchanged.

**В озвучку попало:**

> В случае простого бартера, где деньги вообще не используются, единственным эффектом обмена является переход права собственности. Бартер не создает инфляционного давления, поскольку общее количество товаров и денег в обращении остается неизменным.

---

### 14. `p0561` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> The ability of businesses themselves to better manage their excess capacity— from a theoretical infl ation- control viewpoint— is one of the intriguing aspects of using a cooperative currency approach. Within a fi at currency environment, there is no easy way for businesses to dif-ferentiate among customers to improve the use of their spare capacity and thus increase productivity.

**В озвучку попало:**

> Способность бизнеса лучше управлять своими избыточными мощностями — с точки зрения теории контроля инфляции — является одним из самых любопытных аспектов использования кооперативной валюты. В условиях фиатной денежной системы у бизнеса нет простого способа дифференцировать клиентов, чтобы эффективнее использовать свободные мощности и тем самым повысить производительность.

---

### 15. `p0565` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> As Edgar Kampers, Director of Qoin— Money That Matters, a Dutch not- for- profi t or ga ni za tion that designs, implements, and supports community cooperative currencies, cogently remarks, “It’s critical to understand the defi nition of the word *currency.* So for me currency is information between a buyer and a seller. Two people are involved in a transaction where the money symbolizes the exchange of value. So, I buy a sweater. We agree that it’s worth 20 units of what ever. The sweater is the thing with the value; the money is not, of course. Money is not valuable at all, but money allows you to buy things, which are valuable.

**В озвучку попало:**

> Эдгар Камперс, директор голландской некоммерческой организации Qoin, которая занимается разработкой и внедрением местных кооперативных валют, убедительно отмечает: «Критически важно понимать определение слова "валюта". Для меня валюта — это информация между покупателем и продавцом. Двое людей участвуют в сделке, где деньги символизируют обмен ценностями. Я покупаю свитер. Мы договариваемся, что он стоит 20 условных единиц. Ценность имеет свитер, а не деньги. Деньги сами по себе не ценны, но они позволяют покупать ценные вещи».

---

### 16. `p0643` — длина озвучки / длина оригинала: 1.16; классы правки: —

**Исходный абзац:**

> “Our plans are to create 1,000 banks in the near future, of which 300 should be in the northeast of Brazil, and to have at least one community bank in each state of Brazil. Furthermore, we’d like to help spread this community banking network across Latin America.

**В озвучку попало:**

> [excited] «В ближайшем будущем мы планируем создать тысячу таких банков, триста из которых должны появиться на северо-востоке Бразилии. Мы хотим, чтобы в каждом штате страны был хотя бы один общественный банк. Кроме того, мы стремимся распространить эту сеть общественных банков по всей Латинской Америке».

---

### 17. `p0649` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> The loans are fi nanced solely by members’ savings. No money is made by the bank for providing these loans, nor is money made by the banks’ customers on their savings with the bank. In a nutshell, the bank does not partake in the traditional banking practice of money creation.

**В озвучку попало:**

> Кредиты здесь финансируются исключительно за счет сбережений самих участников. Банк не получает прибыли от выдачи займов, а вкладчики, в свою очередь, не получают процентов по своим депозитам. По сути, этот банк не участвует в традиционной для финансового сектора практике создания денег.

---

### 18. `p0666` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> There has been a solid push in recent years to reach out to other countries internationally. According to Miguel Ganzo, “There are projects underway to establish the JAK model in Germany, Spain, Italy, and Finland. The JAK bank in Denmark was established in 1931 and is totally in de pen dent from us. It started off strongly, then went through a period of decline, and is now on the rise again. There is also interest from Arab countries because our model respects traditional Shari’a principles.”

**В озвучку попало:**

> В последние годы банк активно расширяет свое присутствие на международном уровне. По словам Мигеля Ганзо, сейчас ведутся проекты по внедрению модели JAK в Германии, Испании, Италии и Финляндии. Банк JAK в Дании был основан еще в 1931 году и работает полностью независимо от нас. Он начал свою деятельность успешно, затем пережил период спада, а сейчас снова находится на подъеме. Также интерес проявляют арабские страны, поскольку наша модель соответствует традиционным принципам шариата.

---

### 19. `p0693` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> The convergence between ever- cheaper computing and growing access to the Internet and to mobile phones will drastically change the global banking scene. More important, it will trigger the proliferation of further innovations and real prosperity around the globe, in domains that today seem to be the stuff of science fi ction.

**В озвучку попало:**

> Сближение дешевеющих вычислительных мощностей с растущим доступом к интернету и мобильным телефонам кардинально изменит мировую банковскую сферу. Что еще важнее, это даст толчок дальнейшим инновациям и реальному процветанию во всем мире, в областях, которые сегодня кажутся научной фантастикой.

---

### 20. `p0743` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Then the Teachers’ Cooperative Patricia was part of joined the C3 Program. Like all members of this and other cooperatives (civil ser-vants, professionals, police offi cers, the retired), Patricia now can view, choose, change, pay, and receive the purchased items from the store closest to her residence. A signifi cant number of consumer cooperatives are keen to be a part of this program, which is only viable when they, together with the chain of suppliers, are all part of the C3 network. The decentralization of ser vices and the social inclusion are part of state policy, and obviously this scheme supports these objectives.

**В озвучку попало:**

> Ситуация изменилась, когда кооператив Патрисии присоединился к программе C3. Теперь она и другие члены кооперативов — государственные служащие, специалисты, полицейские и пенсионеры — могут выбирать, оплачивать и получать товары в ближайшем к дому магазине. Многие потребительские кооперативы стремятся стать частью этой программы. Она становится эффективной только тогда, когда сами кооперативы и сеть поставщиков объединены в систему C3. Децентрализация услуг и социальная интеграция являются частью государственной политики, и эта схема, безусловно, помогает достижению таких целей.

---

### 21. `p0756` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> The Hub is a place for purpose- driven people to connect and build solutions for a better world. “Members work at the Hub, attend and produce events, run their own boot camps, access funding and men-torship, source clients and coconspirators, fi nd social networks, build campaigns, launch companies, prototype and test products. The members can create what they want, as it is their space and their community to build upon,” says Jean Luc Roux, a member of the board of the Brussels chapter.

**В озвучку попало:**

> «Хаб» — это место, где люди, движимые общей целью, могут общаться и создавать решения для лучшего мира. Члены сообщества работают здесь, посещают и организуют мероприятия, проводят собственные интенсивы, получают доступ к финансированию и менторству, находят клиентов и единомышленников, расширяют социальные связи, запускают кампании, создают компании, а также тестируют прототипы продуктов. По словам Жана-Люка Ру, члена правления брюссельского отделения, участники могут создавать всё, что пожелают, ведь это их пространство и их сообщество.

---

### 22. `p0760` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> “Before, people were working more alone, looking at the other not necessarily as a friend, not necessarily as a collaborator, but more as a potential competitor. And now, because they can offer ser vices among themselves, they see that they have more to win by working together.

**В озвучку попало:**

> «Раньше люди работали обособленно. Они смотрели друг на друга не как на друзей или соратников, а скорее как на потенциальных конкурентов. Теперь же, имея возможность предлагать услуги друг другу, они видят, что сотрудничество приносит гораздо больше выгоды».

---

### 23. `p0779` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> Many pre ce dents demonstrate that whenever attempts at regulation or moral persuasion run up against fi nancial interests, the latter tends to win. The war against drugs is but one example. The Terra provides a solution that doesn’t pit fi nancial interests against human concerns— in other words, it is a real- world solution.

**В озвучку попало:**

> Множество примеров доказывает: когда попытки регулирования или морального убеждения сталкиваются с финансовыми интересами, последние почти всегда побеждают. Война с наркотиками — лишь один из примеров. Валюта «Терра» предлагает решение, которое не противопоставляет финансовые интересы человеческим потребностям. Это решение, применимое в реальном мире.

---

### 24. `p0883` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Thousands of children responded by picking the neighborhoods clean. The children have taught their parents how to do it. Lerner no-ticed that to earn bus tokens, some slum dwellers even collected and sorted garbage along the highways, making it easier to get the waste picked up by trucks.

**В озвучку попало:**

> Тысячи детей начали собирать мусор, очищая свои районы. Дети научили этому родителей. Лернер заметил, что ради автобусных талонов некоторые жители трущоб даже собирали и сортировали мусор вдоль шоссе, что значительно упростило работу коммунальных служб.

---

### 25. `p0896` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> The many initiatives— environmental cleanup, city restoration, job creation, improved education, disease intervention, and hunger prevention— were each tackled with various cooperative currency systems. This all happened without having to raise taxes, redistribute wealth, issue bonds, rely on charity, or obtain loans from the federal government or organizations such as the World Bank and the International Monetary Fund (IMF). The improvements burdened no one.

**В озвучку попало:**

> [serious] Множество инициатив — от очистки окружающей среды и восстановления города до создания рабочих мест, улучшения образования, борьбы с болезнями и предотвращения голода — решались с помощью различных систем кооперативных валют. Всё это удалось осуществить без повышения налогов, перераспределения богатства, выпуска облигаций, благотворительности или получения кредитов от федерального правительства или таких организаций, как Всемирный банк и Международный валютный фонд. Эти улучшения никого не обременяли.

---

### 26. `p0921` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> In terms of a national crisis, a C3 currency, as explored in Chapter 7, could be used to take care of some of the commercial business currently conducted in national currencies. In a case for the eurozone, for example, countries like Spain, Portugal, Greece, or whichever is in trouble could continue using the euro currency for everything having to do with international activities: tourism, shipping, importing, and exporting. Their respective governments could, in addition, create a new version of the peseta, escudo, or drachma to be used for internal social and environmental businesses. This neonational currency essentially could be spent into existence by the government itself, for specifi c purposes, without incurring debt in the fi nancial system.

**В озвучку попало:**

> В условиях национального кризиса можно использовать валюту типа C3, как это рассматривалось в седьмой главе, для обслуживания части коммерческих операций, которые сейчас проводятся в национальных валютах. В случае с еврозоной, например, такие страны, как Испания, Португалия или Греция, могли бы продолжать использовать евро для всех международных операций: туризма, грузоперевозок, импорта и экспорта. При этом их правительства могли бы создать новую версию песеты, эскудо или драхмы для внутренних социальных и экологических нужд. Эта «неонациональная» валюта, по сути, могла бы выпускаться самим правительством для конкретных целей, не создавая долгов в финансовой системе.

---

### 27. `p0975` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The residents of Blaengarw worked their way out of the all- too-common story of social blight and decay by making an assessment of their unused resources and their unmet needs and, in this case, linking these with a time- banking currency coordinated by a regional and local NGO.

**В озвучку попало:**

> Жители Блангарва смогли преодолеть типичную историю социального упадка и разрухи. Они провели оценку своих неиспользованных ресурсов и нереализованных потребностей, а затем связали их с валютой тайм-банкинга, координируемой региональной и местной некоммерческой организацией.

---

### 28. `p0979` — длина озвучки / длина оригинала: 1.68; классы правки: —

**Исходный абзац:**

> Activities are centered around the town’s 100- year- old Miners’ Welfare Hall. The local activities are run by a community nonprofi t or ga-ni za tion, Creation Development Trust, which employs two workers to oversee the TimeBanking. For each hour of ser vice given to the community, a credit of one hour is exchanged. In the fi rst year, 150 people took part; there are now over 1,000 members and 30 groups; 15 new social enterprises have been established, and new learning opportuni-

**В озвучку попало:**

> Деятельность сосредоточена вокруг столетнего Зала благосостояния шахтеров. Местные инициативы управляются некоммерческой организацией Creation Development Trust, которая нанимает двух сотрудников для контроля за тайм-банкингом. За каждый час работы на благо общества начисляется один кредит. В первый год в программе участвовало сто пятьдесят человек, сейчас — более тысячи членов и тридцать групп. Создано пятнадцать новых социальных предприятий и открыты новые возможности для обучения. Участники вносят шестьдесят тысяч часов труда в год на нужды своего сообщества. Зал посещают в среднем шестьсот человек в неделю. Вход на мероприятия оплачивается либо временными кредитами, либо обычными деньгами: двухчасовой вечер бинго или киносеанс стоят два временных кредита, а трехчасовое культурное представление — три.

---

### 29. `p0995` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> They have made millions of dollars worth of trades with HOURS, representing hundreds of job equivalents at $20,000 each. Businesses accepting the local currency include the Ithaca Health Alliance, Cayuga Medical Center, Alternatives Federal Credit Union, the public library, many local farmers, movie theaters, restaurants, healers, plumbers, carpenters, electricians, and landlords.

**В озвучку попало:**

> С помощью «часов» они совершили сделок на миллионы долларов. Это эквивалентно сотням рабочих мест, каждое из которых оценивается в двадцать тысяч долларов. Местную валюту принимают многие организации: «Итака Хелс Альянс», медицинский центр Каюга, федеральный кредитный союз «Альтернативы», публичная библиотека, а также фермеры, кинотеатры, рестораны, целители, сантехники, плотники, электрики и арендодатели.

---

### 30. `p1002` — длина озвучки / длина оригинала: 1.15; классы правки: —

**Исходный абзац:**

> Glover explains, “The clinic will provide community- based health care that is genuinely nonprofi t, preventive, humane, and, in the spirit of Patch Adams, fun. It is a refuge for doctors and nurses who want time to heal patients. It is a refuge for patients who want to be treated with dignity. For a small annual fee, members will own this clinic, gaining diagnosis and referral, dentistry, chronic and urgent care, counseling, pediatrics, birthing, hospice care, massage, family planning, chi-ropractic, acu punc ture, and other therapies. “More than a health facility, the clinic is an economic development model that solves several urban problems. Existing medical facilities are overcrowded and underfunded. Suffering is untended, both mental and physical. Infectious disease rates are high.”⁷

**В озвучку попало:**

> Гловер поясняет: «Клиника обеспечит медицинское обслуживание, которое по-настоящему некоммерческое, профилактическое, гуманное и, в духе Пэтча Адамса, веселое. Это убежище для врачей и медсестер, которые хотят иметь время на то, чтобы лечить пациентов. Это убежище для пациентов, которые хотят, чтобы к ним относились с достоинством. За небольшой ежегодный взнос члены сообщества становятся совладельцами клиники. Они получают доступ к диагностике, стоматологии, лечению хронических и острых заболеваний, консультациям, педиатрии, родовспоможению, хоспису, массажу, планированию семьи, хиропрактике, акупунктуре и другим видам терапии. Это не просто медицинское учреждение, а модель экономического развития, решающая целый ряд городских проблем. Существующие больницы переполнены и недофинансированы. Люди страдают от нелеченных физических и психических заболеваний, а уровень инфекционных болезней остается высоким».

---

### 31. `p1005` — длина озвучки / длина оригинала: 1.14; классы правки: —

**Исходный абзац:**

> “Expenses are kept low by relying least on U.S. dollars. To the maximum possible, we rely on the gift economy, barter, and credit systems such as Time Dollars and HOURS (‘MediCash’). Staff members are primarily volunteers: professionals, students, religious congregants, neighbors, and members. Membership may be paid with labor to maintain the facility and its grounds. Both volunteers and staff may be rewarded with Philadelphia MediCash, (HOURS) gift certifi cates, health care, sweat equity credits, college course credit, and scholarships. Barter agreements will also meet personal needs,” he adds.⁸

**В озвучку попало:**

> «Расходы сведены к минимуму за счет отказа от использования американских долларов, — добавляет он. — Мы максимально опираемся на экономику дарения, бартер и кредитные системы, такие как "Тайм Долларс" и "Часы" — или, как мы их называем, "МедиКэш". Персонал — это в основном волонтеры: профессионалы, студенты, прихожане церквей, соседи и члены сообщества. Членские взносы можно оплачивать трудом, поддерживая здание и территорию в порядке. И волонтеры, и штатные сотрудники могут получать вознаграждение в виде филадельфийских "МедиКэш", подарочных сертификатов, медицинских услуг, кредитов на обучение или стипендий. Личные потребности также будут решаться через бартерные соглашения».

---

### 32. `p1099` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> So another important lesson for me was to do the preparations and training *before* the crisis starts. Today, I foresee the interface to be easier, thanks to cell phones, so people can access their accounts and make payments through their phones. I saw phones used to buy sodas in 2002 in Japan, and in South Africa in 2005, so eventually we shall have it in the United States as well.”²¹

**В озвучку попало:**

> «Поэтому еще один важный урок для меня заключается в том, что подготовку и обучение нужно проводить до начала кризиса. Сегодня я предвижу, что интерфейсы станут проще благодаря мобильным телефонам, и люди смогут получать доступ к своим счетам и совершать платежи через них. Я видел, как телефоны использовали для покупки газировки в Японии в 2002 году и в Южной Африке в 2005-м, так что со временем это появится и в Соединенных Штатах».

---

### 33. `p1121` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> Intertwined with their time- honored agricultural and social practices is the longest- surviving cooperative currency ecosystem in the world. Before Indonesian in de pen dence in 1945, the conventional currency was the Dutch guilder, followed by the Indonesian rupiah. Working in parallel with this conventional money is a social currency networked through the Banjar system, which has been in use since before written rec ords. Everyone in the Banjar is obliged to contribute to the well- being of the community by helping with jointly decided projects. The Banjar system extends beyond religious or cultural events and may include civic activities, such as support for building local roads, especially when the central government is unable to provide funding. In short, local resources are mobilized regularly to support a full spectrum of undertakings, what ever the community chooses to focus on. It is this system of mutual cooperation and assistance that accounts for the resiliency of Balinese culture.³

**В озвучку попало:**

> С этими сельскохозяйственными и социальными практиками тесно переплетена старейшая в мире кооперативная валютная экосистема. До обретения Индонезией независимости в 1945 году основной валютой был голландский гульден, а затем индонезийская рупия. Параллельно с ними через систему банджаров использовалась социальная валюта, существующая еще с дописьменных времен. Каждый член банджара обязан вносить вклад в благополучие общины, помогая в реализации совместных проектов. Система банджаров охватывает не только религиозные и культурные события, но и гражданские инициативы, например, строительство местных дорог, когда центральное правительство не выделяет на это средства. Ресурсы общины регулярно мобилизуются для самых разных задач. Именно эта система взаимной поддержки обеспечивает устойчивость балийской культуры.

---

### 34. `p1134` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> These are the same lessons learned from the Argentinean debacle, for instance, that convinced the German regio movement to incorporate the following principles into their eight conditions for a currency to be granted the use of the regio label, according to Margrit Kennedy, the initiator for the regio movement.¹¹ These conditions state that these criteria need to be satisfi ed:

**В озвучку попало:**

> Это те же уроки, которые были извлечены из аргентинского кризиса. Именно они убедили немецкое движение «регио» включить ряд принципов в свои восемь условий для получения валютой права использовать знак «регио», как утверждает инициатор движения Маргрит Кеннеди. Эти критерии должны быть соблюдены:

---

### 35. `p1244` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> The Board decided unanimously to implement the 100- year sub- Sahara project, given that the internal rate of return on this project is clearly superior to the 25- year project. The chairman added that the contribution of this project to overall global climate stability has been an additional incentive for him to vote for this project. The currency of all payments for goods and suppliers is the demurrage charged, similar to the Terra currency. The annual reports to the shareholders are similarly expressed in Terra.

**В озвучку попало:**

> Совет единогласно решил реализовать столетний проект в Сахаре, поскольку внутренняя норма доходности по нему явно выше, чем у двадцатипятилетнего проекта. Председатель добавил, что вклад этого проекта в общую стабильность мирового климата стал для него дополнительным стимулом проголосовать «за». Валютой для всех расчетов с поставщиками товаров и услуг служит валюта с демереджем, аналогичная «Терре». Годовые отчеты для акционеров также выражены в «Терре».

---

### 36. `p1246` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> Embu, a 23- year- old Kenyan Bantu- speaking woman and mother of one, takes the microphone and beams a broad, proud smile at the assembled group of representatives. They’ve traveled from far and wide across the expansive Nyanza Province, which borders on Lake Victoria, for this important quarterly joint NGO meeting. Delegates from across the culturally diverse region, including members of the Luo, Gusii, and Kuria tribes, sit in excited anticipation to hear the fi nancial reports and updates on their area’s comprehensive network of cooperatives and trade associations. Preliminary accounts and animated gossip, along with obvious evidence of vibrant commerce transacted daily, bode well for good news and a well- deserved celebration later that eve ning.

**В озвучку попало:**

> [excited] Эмбу, двадцатитрехлетняя кенийка из народа банту и мать одного ребенка, берет микрофон и широко, с гордостью улыбается собравшимся представителям. Они приехали издалека со всей обширной провинции Ньянза, граничащей с озером Виктория, на важное ежеквартальное совместное собрание неправительственных организаций. Делегаты из разных культурных групп региона, включая представителей племен луо, гусии и куриа, в радостном предвкушении ждут финансовых отчетов и новостей о работе их сети кооперативов и торговых ассоциаций. Предварительные данные и оживленные разговоры, а также очевидные признаки активной ежедневной торговли сулят хорошие новости и заслуженный праздник, который состоится позже вечером.

---

### 37. `p1325` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> What is being touted as the Third Industrial Revolution is now well underway. “The old way of making things involved taking lots of parts and screwing or welding them together. Now a product can be designed on a computer and ‘printed’ on a 3D printer, which creates a solid object by building up successive layers of material. The digital design can be tweaked with a few mouse clicks. The 3D printer can run unattended and can make many things which are too complex for a traditional factory to handle. In time, these amazing machines may be able to make almost anything, anywhere— from your garage to an African village.”⁸

**В озвучку попало:**

> То, что называют Третьей промышленной революцией, уже идет полным ходом. Раньше производство вещей требовало сборки множества деталей с помощью винтов или сварки. Теперь изделие можно спроектировать на компьютере и «распечатать» на 3D-принтере, который создает твердый объект, слой за слоем наращивая материал. Цифровую модель можно подправить парой кликов мыши. 3D-принтер может работать без присмотра и создавать вещи, слишком сложные для традиционного завода. Со временем эти удивительные машины смогут производить почти что угодно и где угодно — от вашего гаража до африканской деревни.

---

### 38. `p1339` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> “Frankly, it’s not good enough to just simply think outside the box anymore. We need to throw the box away and think in an entirely different way. In order to do that, we need to teach our children *how* to learn by capitalizing on their individual strengths. And each is unique.

**В озвучку попало:**

> «Честно говоря, уже недостаточно просто мыслить нестандартно. Нам нужно отбросить саму коробку и начать мыслить совершенно иначе. Для этого мы должны научить детей тому, как учиться, опираясь на их индивидуальные сильные стороны. А каждый ребенок уникален».

---

### 39. `p1340` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> That way a life of continual learning, adaptation and empowerment is possible. Each person can truly access his or her genius— a compass to follow one’s individual bliss,” comments Kimberly Kassner, author of *You’re a Genius— And I Can Prove It!* Each person, when given the opportunity, becomes a unique and brilliant being.¹⁵

**В озвучку попало:**

> «Так становится возможной жизнь, полная постоянного обучения, адаптации и расширения возможностей. Каждый человек может по-настоящему раскрыть свою гениальность — этот компас, помогающий следовать своему призванию», — комментирует Кимберли Касснер, автор книги «Ты гений, и я могу это доказать!». Каждый человек, если дать ему такую возможность, становится уникальным и блестящим существом.

---

### 40. `p1343` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> She explains that contemporary leaders of courage and compassion are operating from a profound space. These leaders are pattern makers, not just problem solvers. They deal with what is not working by creating alternatives. They are able to identify, distinguish, design, and generate responses that integrate the different domains related to the entangled hierarchies of any given situation. They do more than solve complex societal problems at a surface level. They actively address the deeper dimensions of reality. They demonstrate that it is possible to design and implement programs differently: solving problems; synthe-sizing and making sense of the invisible patterns affecting reality, as well as endless incomprehensible bits of information; breaking new ground; and establishing alternatives— ethical and principled action sourcing their inner values and wisdom.

**В озвучку попало:**

> Она объясняет, что современные лидеры, обладающие мужеством и состраданием, действуют из глубокого внутреннего пространства. Эти лидеры не просто решают проблемы, они создают новые модели. Они справляются с тем, что не работает, предлагая альтернативы. Они способны выявлять, различать, проектировать и создавать ответы, которые объединяют разные области, связанные с запутанными иерархиями любой ситуации. Они делают больше, чем просто решают сложные социальные проблемы на поверхностном уровне. Они активно работают с более глубокими измерениями реальности. Они доказывают, что можно проектировать и внедрять программы иначе: синтезируя и осмысливая невидимые закономерности, влияющие на реальность, прокладывая новые пути и создавая этичные альтернативы, основанные на внутренних ценностях и мудрости.

---

### 41. `p1798` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> A special word of thanks to Ed and Deb Shapiro, Frank Baylin, Kimberly Kassner, Nigel Seale, Aureya Magdalen, Jean Houston, Paul Ray, Jan Coleman, and Sally Dunne- Lee. To Michelle Bishop for her diligent assistance with some of the research. Also, to our agents David Nelson and Neil Gudovitz at Waterside Productions for their consummate support and guidance.

**В озвучку попало:**

> [thoughtful] Особая благодарность Эду и Деб Шапиро, Фрэнку Бэйлину, Кимберли Касснер, Найджелу Силу, Орее Магдален, Джин Хьюстон, Полу Рэю, Джану Коулману и Салли Данн-Ли. Спасибо Мишель Бишоп за усердную помощь в проведении исследований. Мы также признательны нашим агентам Дэвиду Нельсону и Нилу Гудовицу из компании «Уотерсайд Продакшнс» за их неизменную поддержку и советы.

---

### 42. `p1800` — длина озвучки / длина оригинала: 0.96; классы правки: —

**Исходный абзац:**

> This book is the result of, quite literally, thousands of conversations over time and scores of interviews across the globe during the course of writing this book. Unfortunately, while many discussions didn’t make it into the book, they were seminal in shaping our work. There are too many people to thank here by name for their time, contributions, and generosity of spirit. Know that you are all held in our hearts with deep and abiding gratitude.

**В озвучку попало:**

> Эта книга — результат тысяч разговоров и множества интервью, которые мы провели по всему миру во время работы над ней. К сожалению, далеко не все обсуждения вошли в текст, но они сыграли ключевую роль в формировании наших идей. Людей, которым стоит сказать спасибо за их время, вклад и душевную щедрость, слишком много, чтобы перечислить всех поименно. Знайте, что мы храним вас в своих сердцах с глубокой и искренней благодарностью.

---

### 43. `p2236` — длина озвучки / длина оригинала: 1.04; классы правки: —

**Исходный абзац:**

> Bernard has been a star since 1969, when he received an MBA from MIT and *Time* magazine selected him as one of the top-10 graduates of U.S. business schools. His post- graduate thesis, entitled *Financial* *Management of Foreign Exchange,* was published by MIT Press in 1970 and received wide attention in the fi nancial world. In his thesis, he discussed applying nonlinear programming to global currency management for multinational corporations. This was considered the fi rst book to explore the applications of systems theory to international fi - nance. It described how to optimize currency management for corporations working in a large number of countries and currencies, and included the techniques to deal with fl oating exchanges, at the time a rare occurrence limited to some exotic currencies in Latin America. A major U.S. bank negotiated exclusive rights to Bernard’s approach prompting him to start a new career and move to South America. He developed, for the largest mining company in Peru, a new system for worldwide allocation of mining resources, which ended up being used to optimize two- thirds of all foreign exchange earnings of Peru. Subsequently, he wrote the only book (published in 1979) to foretell the Latin American debt crisis that exploded as he predicted in the early 1980s.

**В озвучку попало:**

> Бернар стал известен еще в 1969 году, когда получил степень магистра делового администрирования в Массачусетском технологическом институте, а журнал Time включил его в десятку лучших выпускников бизнес-школ США. Его диссертация «Финансовое управление иностранной валютой» была опубликована издательством Массачусетского технологического института в 1970 году и привлекла большое внимание в финансовых кругах. В работе он предложил применять методы нелинейного программирования для управления глобальными валютными потоками в транснациональных корпорациях. Это была первая книга, в которой теория систем рассматривалась применительно к международным финансам. Лиетар описал способы оптимизации валютного управления для компаний, работающих во многих странах, и предложил методы работы с плавающими курсами — явлением, которое в то время было редкостью и встречалось лишь в некоторых странах Латинской Америки. Крупный американский банк выкупил эксклюзивные права на подход Бернара, что побудило его начать новую карьеру и переехать в Южную Америку. Там он разработал для крупнейшей горнодобывающей компании Перу систему распределения ресурсов, которая в итоге позволила оптимизировать две трети всех валютных поступлений страны. Позже он написал книгу, изданную в 1979 году, в которой предсказал латиноамериканский долговой кризис, разразившийся в начале восьмидесятых.

---

### 44. `p2237` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Later, Bernard was widely credited with being one of the principal architects of the euro, the single Eu ro pe an currency. This came about after he accepted a job offer as the head of the Or ga ni za tion and Computer Department at the Central Bank in Belgium. Because Belgium received the chairmanship of the Eu ro pe an Currency Unit (the ECU), his fi rst project at the Bank was the design and implementation of the convergence system, which evolved into the euro in January,

**В озвучку попало:**

> Позже Бернара признали одним из главных архитекторов евро, единой европейской валюты. Это произошло после того, как он принял предложение возглавить отдел организации и вычислительной техники в Центральном банке Бельгии. Поскольку Бельгия получила право председательства в Европейской валютной единице, его первым проектом в банке стала разработка системы конвергенции, которая в январе 1999 года эволюционировала в евро.

---

### 45. `p2239` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> In the mid- 1990s, Bernard changed his focus. He has spent the past two de cades as one of the world’s leading designers and implementers of cooperative currencies. He has consulted with communities, governments, banks, and businesses around the globe. He has written several books on the topic of money, including the classic, *The* *Future of Money,* along with hundreds of articles and interviews. One of Bernard’s current projects in terms of new currencies is the Trade Reference Currency, which is a privately- issued, cooperative, global reference currency that is backed by a noninfl ationary, standardized basket of the dozen most important commodities and ser vices in the global market. It is poised to drastically change barter and counter-trade along with creating stability and predictability in the fi nancial and business sectors by providing a robust standard of value for international trade. Most importantly, it will resolve the current confl ict between short- term fi nancial interest and long- term sustainability thereby providing, for the fi rst time since the gold- standard days, an international standard of value that is infl ation- resistant. This mechanism would work in parallel with national currencies. Currently, Bernard is a Research Fellow at the Center for Sustainable Resources of the University of California at Berkeley. He is also Visiting Professor at the Finance University of Moscow.

**В озвучку попало:**

> В середине девяностых Бернар сменил сферу деятельности. Последние два десятилетия он является одним из ведущих в мире разработчиков и внедренцев кооперативных валют. Он консультирует сообщества, правительства, банки и бизнес по всему миру. Бернар написал несколько книг о деньгах, включая классическую работу «Будущее денег», а также сотни статей и интервью. Один из его текущих проектов — «Торговая эталонная валюта». Это частная кооперативная глобальная валюта, обеспеченная неинфляционной стандартизированной корзиной из двенадцати важнейших товаров и услуг мирового рынка. Она призвана радикально изменить бартерную и встречную торговлю, а также обеспечить стабильность и предсказуемость в финансовом и деловом секторах, предоставляя надежный стандарт стоимости для международной торговли. Что наиболее важно, она разрешит текущий конфликт между краткосрочными финансовыми интересами и долгосрочной устойчивостью, впервые со времен золотого стандарта обеспечив международный стандарт стоимости, устойчивый к инфляции. Этот механизм будет работать параллельно с национальными валютами. В настоящее время Бернар является научным сотрудником Центра устойчивых ресурсов Калифорнийского университета в Беркли и приглашенным профессором Финансового университета в Москве.

---

### 46. `p2240` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> He is a member of the Club of Rome; a Fellow at the World Academy of Arts and Sciences, the World Business Academy, and the Euro pe an Academy of Sciences and Arts; and a founding member of the Global Futures Forum. He currently resides in his native Belgium. He is fl uent in En glish, French, Spanish, German, and Dutch, and reads Latin and Greek.

**В озвучку попало:**

> Он является членом Римского клуба, почетным членом Всемирной академии искусств и наук, Всемирной бизнес-академии, Европейской академии наук и искусств, а также одним из основателей форума Global Futures Forum. В настоящее время он проживает в родной Бельгии. Бернар свободно владеет английским, французским, испанским, немецким и голландским языками, а также читает на латыни и древнегреческом.

---

### 47. `p2242` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Danu Resources is a for- profi t or ga ni za tion that brings together and aligns donors and projects that focus on environmental and energy initiatives to move the world to greater sustainability while empower-ing people with dignity and the essentials of life. Danu’s unique value is its ability to work from a future reference point that draws out the greatness, and builds upon the strengths, of both the donor and the company or initiative, thus creating a fl ourishing paradigm shift for people and the planet. Where feasible, ventures operate using a multiple-currency ecosystem.

**В озвучку попало:**

> Danu Resources — это коммерческая организация, которая объединяет доноров и проекты, ориентированные на экологические и энергетические инициативы. Их цель — сделать мир более устойчивым, обеспечивая при этом людям достойные условия жизни. Уникальность Danu заключается в способности работать, опираясь на будущие ориентиры, которые раскрывают потенциал и укрепляют сильные стороны как доноров, так и инициаторов проектов, создавая процветающую парадигму для людей и планеты. Там, где это возможно, предприятия работают с использованием экосистемы из нескольких валют.

---

### 48. `p2243` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> She serves on the board of, or is an advisor to, several U.S. and international companies. These fi rms are engaged in innovative solutions in the domains of green energy (the Swedish corporation Mimer Energy and Blue Energy in Canada), decentralized local food production (Perpetua in the United States), and a natural resolution for nuclear and other waste streams, Amo Terra. She is a principal strategist with the launching of the business- to- business currency, the Terra, that is designed to create more stability and predictability in the fi nancial and business sectors by providing a mechanism for contractual, payment, and planning purposes worldwide.

**В озвучку попало:**

> Она входит в советы директоров или выступает советником ряда американских и международных компаний. Эти фирмы занимаются инновационными решениями в таких областях, как «зеленая» энергетика — шведская корпорация Mimer Energy и канадская Blue Energy, децентрализованное местное производство продуктов питания — Perpetua в США, а также естественные способы утилизации ядерных и других отходов — Amo Terra. Она является ведущим стратегом по запуску межкорпоративной валюты «Терра», которая призвана повысить стабильность и предсказуемость в финансовом и деловом секторах, предоставляя механизм для контрактных, платежных и плановых целей по всему миру.

---

### 49. `p2245` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> An award- winning journalist, she started her career in her native Ireland. While still in college, Jacqui reported on a freelance basis on Spain’s transition to democracy in the late 1970s for both the *Irish Times* and RTE (Irish Radio). Later, she joined the *Sunday In-**de pen dent* as a staff reporter and features writer and covered a variety of stories from the po liti cal unrest in Northern Ireland to famine in Ethiopia. For several years, she wrote a monthly column for the *Irish* *Tattler* and codesigned special events for the magazine to encourage women’s entrepreneurship.

**В озвучку попало:**

> Джеки — отмеченный наградами журналист. Свою карьеру она начала на родине, в Ирландии. Еще будучи студенткой, она работала внештатным корреспондентом и освещала переход Испании к демократии в конце семидесятых годов для газеты «Айриш Таймс» и ирландской телерадиокомпании RTE. Позже она стала штатным репортером и автором статей в газете «Санди Индепендент». Там она писала о самых разных событиях: от политических волнений в Северной Ирландии до голода в Эфиопии. Несколько лет она вела ежемесячную колонку в журнале «Айриш Таттлер» и участвовала в разработке специальных мероприятий, направленных на поддержку женского предпринимательства.

---

### 50. `p2246` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> In New York, she wrote for *Interview Magazine, Elle,* and the *Daily* *News,* then headed west to San Francisco, where she wrote for *Grass**roots/Dresdner RCM Bank,* compiling investigative reports on companies and industry sector analysis. She produced radio interviews with thought leaders and was an occasional on- air host for *New Dimen**sions Radio,* syndicated to NPR and community radio stations nationally and overseas.

**В озвучку попало:**

> В Нью-Йорке она писала для журналов «Интервью», «Элль» и газеты «Дейли Ньюс». Затем она переехала на запад, в Сан-Франциско, где сотрудничала с банком «Грассрутс Дрезднер РСМ». Там она занималась подготовкой аналитических отчетов о различных компаниях и отраслях экономики. Джеки также записывала радиоинтервью с лидерами мнений и время от времени выступала в качестве ведущей на радиостанции «Нью Дименшнс», чьи программы транслировались на национальном уровне через сеть NPR и местные общественные радиостанции.

---

### 51. `p2247` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> In order to gain experience in how business really works, Jacqui conducted market research for multinational biotech and pharmaceutical companies. She was vice president of a former boutique technology public and investor relations company, ContentOne, which handled media and investor relations for fi rms ranging from start- ups to publicly traded companies.

**В озвучку попало:**

> Чтобы лучше понять, как на самом деле устроен бизнес, Джеки проводила маркетинговые исследования для транснациональных биотехнологических и фармацевтических компаний. Она занимала пост вице-президента в компании «КонтентУан», которая специализировалась на технологическом пиаре и связях с инвесторами. Эта фирма работала с самыми разными клиентами: от стартапов до крупных публичных корпораций.

---

### 52. `p2248` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Lately, she has worked as a content editor for *Money and* *Sustainability— The Missing Link, A Report from the Club of Rome,* which reveals the hidden dynamics among the conventional money system, climate change, and ecological sustainability. This report was addressed to Finance Watch, an in de pen dent Eu ro pe an public interest association tasked by the Eu ro pe an Union with reporting on the causes of the current banking and fi nancial debacle.

**В озвучку попало:**

> В последнее время она работала редактором контента над докладом Римского клуба «Деньги и устойчивое развитие: недостающее звено». В этом отчете раскрываются скрытые взаимосвязи между традиционной денежной системой, изменением климата и экологической устойчивостью. Доклад был подготовлен для «Финанс Вотч» — независимой европейской общественной организации, которой Евросоюз поручил изучить причины текущего банковского и финансового кризиса.

---

### 53. `p2251` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> We believe that to truly create a better world, action is needed at all levels— individual, organizational, and societal. At the individual level, our publications help people align their lives with their values and with their aspirations for a better world. At the organizational level, our publications promote progres-sive leadership and management practices, socially responsible approaches to business, and humane and effective organizations. At the societal level, our publications advance social and economic justice, shared prosperity, sustainability, and new solutions to national and global issues.

**В озвучку попало:**

> Мы верим, что для создания лучшего мира необходимы действия на всех уровнях: индивидуальном, организационном и общественном. На индивидуальном уровне наши книги помогают людям привести свою жизнь в соответствие с их ценностями и стремлением к лучшему будущему. На уровне организаций мы продвигаем прогрессивное руководство, ответственные подходы к бизнесу, а также создание гуманных и эффективных коллективов. На уровне общества наши публикации способствуют социальной и экономической справедливости, всеобщему процветанию, устойчивому развитию и поиску новых решений национальных и глобальных проблем.

---

### 54. `p2252` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> A major theme of our publications is “Opening Up New Space.” Berrett- Koehler titles challenge conventional thinking, introduce new ideas, and foster positive change. Their common quest is changing the underlying beliefs, mindsets, institutions, and structures that keep generating the same cycles of problems, no matter who our leaders are or what improvement programs we adopt.

**В озвучку попало:**

> Одна из главных тем наших публикаций — «Открывая новые горизонты». Книги издательства «Берретт-Кёлер» бросают вызов привычному мышлению, предлагают новые идеи и способствуют позитивным переменам. Наша общая цель — изменить глубинные убеждения, установки, институты и структуры, которые раз за разом порождают одни и те же проблемы, независимо от того, кто стоит у власти или какие программы реформ мы принимаем.

---

### 55. `p2253` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> We strive to practice what we preach—to operate our publishing company in line with the ideas in our books. At the core of our approach is stewardship, which we deﬁ ne as a deep sense of responsibility to administer the company for the beneﬁ t of all of our “stakeholder” groups: authors, customers, employees, investors, service providers, and the communities and environment around us.

**В озвучку попало:**

> Мы стремимся следовать собственным советам и управлять издательством в соответствии с идеями, изложенными в наших книгах. В основе нашего подхода лежит концепция ответственного управления. Мы определяем ее как глубокое чувство ответственности за развитие компании на благо всех наших заинтересованных сторон: авторов, клиентов, сотрудников, инвесторов, партнеров и общества в целом.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p0411` — длина озвучки / длина оригинала: 0.52; классы правки: —

**Исходный абзац:**

> Therefore, in this environment, Fisher’s equation becomes: *E* = (*Qs* × *Vs*) + (*Qc* × *Vc*), where *Qs* equals quantity of money that can be used for savings (i.e., typically conventional money), *Vs* equals average velocity of circulation of that kind of money, *Qc* equals quantity of complementary currency used as pure medium of exchange, and *Vc* equals average velocity of these complementary currencies.

**В озвучку попало:**

> В таких условиях уравнение Фишера принимает новый вид. Общая активность равна сумме двух произведений: количества обычных денег на их скорость обращения плюс количество кооперативной валюты на скорость её обращения.

---

### 2. `p1123` — длина озвучки / длина оригинала: 0.65; классы правки: —

**Исходный абзац:**

> “Chinese money, known also as *pis bolong* in Bali, has circulated as a local medium of exchange here for at least the past 1,000 years and only ceased to be used for local purchases in the early 1970s. Up until that time, a Balinese could use uang kepeng in many ways, from buying meat and vegetables in the market or snacks in front of the school, to watching movies with friends at an outdoor theater,” says Stephen DeMeulenaere, found er of the Cooperative Currency Resource Center and a long- term resident of Bali.⁶ According to DeMeulenaere, uang kepeng became the offi cial medium of exchange of the Banjar and could be taxed, spent on public works projects, and circulated as a fully functioning currency. Thus its signifi cance to Balinese society was formalized.⁷

**В озвучку попало:**

> [serious] «Китайские деньги, известные на Бали как пис болонг, служили местным средством обмена не менее тысячи лет и вышли из употребления только в начале семидесятых годов», — говорит Стивен ДеМёленаре, основатель Центра ресурсов кооперативных валют, долгое время проживший на Бали. По его словам, уанг кепенг были официальным средством обмена в банджарах: ими платили налоги, финансировали общественные проекты и использовали как полноценную валюту. Это закрепило их значение для балийского общества.

---

### 3. `p0425` — длина озвучки / длина оригинала: 0.71; классы правки: —

**Исходный абзац:**

> Barter is the direct exchange of goods or ser vices unmediated by any type of money. For example, a boy agreed to cut his neighbor’s lawn. The neighbor had two tickets to an upcoming Van Halen reunion concert he couldn’t use; he also had an earlier version of an iPod lying around. But the tickets were not of interest to the boy, and the used iPod, the neighbor realized, was far more valuable than the boy’s time and effort warranted. Bartering requires matching the needs and resources of both parties involved in the transaction, yet it’s not always possible to line up an equitable exchange of goods or ser vices. So the neighbor may decide to pay the boy in cash rather than bartering, and put the items up for auction on eBay.

**В озвучку попало:**

> Бартер — это прямой обмен товарами или услугами без участия каких-либо денег. Например, мальчик согласился подстричь газон у соседа. У соседа были два лишних билета на концерт группы Ван Хален и старый плеер Айпод. Но билеты мальчику были не нужны, а плеер, как понял сосед, стоил гораздо больше, чем время и усилия мальчика. Бартер требует совпадения потребностей и ресурсов у обеих сторон, что не всегда возможно. Поэтому сосед может решить заплатить мальчику наличными, а свои вещи выставить на аукцион в интернете.

---

### 4. `p0404` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> Seeing the entire global monetary system in terms of a network structure reveals why it is brittle and subject to breakdown: the monopoly of one *type* of money, namely, national currencies, all created through bank debt, that fl ow within each country or group of countries, as in the case of the euro, and interconnect on a global level. Since there are no other options within the system than this one kind of currency, the entire network is frail. This is clearly borne out by the facts. As mentioned already in the Introduction, according to International Monetary Fund data, in the four de cades between 1970 and 2010, there were no fewer than 145 banking crises, 208 monetary crashes, and 72 sovereign debt crises. This adds up to an astounding total of 425 systemic crises— an average of more than 10 countries in crisis each and every year!⁵

**В озвучку попало:**

> [serious] Взгляд на глобальную денежную систему как на сетевую структуру объясняет, почему она так хрупка и склонна к сбоям. Проблема в монополии одного типа денег — национальных валют, которые создаются через банковские долги. Поскольку внутри системы нет альтернатив, вся сеть становится уязвимой. Факты это подтверждают: согласно данным Международного валютного фонда, за четыре десятилетия, с 1970 по 2010 год, произошло не менее 145 банковских кризисов, 208 валютных крахов и 72 кризиса суверенного долга. В сумме это 425 системных кризисов — в среднем более десяти стран ежегодно сталкивались с серьезными потрясениями.

---

### 5. `p0381` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> They are designed to facilitate transactions (i.e., as a medium of exchange), used both as units of account and as savings (i.e., as temporary stores of value), and are particularly well adapted for business and industrial applications and settings. As already seen, the use of interest, especially compound interest, has very precise outcomes that do not necessarily benefi t society at large. However, money can also be archi-tected in other ways.

**В озвучку попало:**

> Они созданы для облегчения транзакций, служат единицами учета и средством сбережения. Такие деньги особенно хорошо подходят для бизнеса и промышленности. Но, как мы видели, использование процентов, особенно сложных, приводит к результатам, которые не всегда идут на пользу обществу в целом. Однако деньги можно проектировать и иначе.

---

### 6. `p0214` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> It’s the same story worldwide. This is true regardless of the country of issuance, the po liti cal philosophy (capitalist, communist, socialist, fascist, totalitarian, despotic, or demo cratic), and the different designa-tions, and despite differences in material composition, shape, or par tic-u lar motif. The currencies are, each and every one of them, the same type of money that is required by the state for the payment of taxes.

**В озвучку попало:**

> Такая история повторяется по всему миру. Это верно вне зависимости от страны, политического строя — будь то капитализм, коммунизм, социализм, фашизм или демократия, — а также от дизайна, формы или материала купюр. Все национальные валюты без исключения — это один и тот же тип денег, требуемых государством для сбора налогов.

---

### 7. `p0091` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> This epoch produced remarkable advances, thrusting society out of the shackles of superstition and stagnant social order that had preceded it. It brought about the rigor of science founded in that which could be proven, rather than divine dogma. It enabled the individual, no matter how lowly his birth, to scale the heights of his unbridled imagination and keen ambition through learning and labor.

**В озвучку попало:**

> Эта эпоха принесла поразительные достижения, вырвав общество из оков суеверий и застойного социального порядка. Она утвердила строгость науки, основанной на доказательствах, а не на догмах. Она позволила человеку, независимо от его происхождения, достичь невероятных высот благодаря обучению и труду.

---

### 8. `p1233` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> As a result, there is nothing theoretical about her experience of poverty. And there was no book learning to fi nd an answer. Her way out was culled from observing how the women took care of one another, sharing what they had and giving of themselves in terms of time, street smarts, and friendship.

**В озвучку попало:**

> Поэтому ее опыт бедности — это не теория. И ответов не было в книгах. Ее путь к спасению был найден благодаря тому, как женщины заботились друг о друге: делились тем, что имели, отдавали свое время, житейскую мудрость и дружбу.

---

### 9. `p0653` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> “Savings points” are the cooperative currency internally used as the key method by which JAK manages member savings and loans, thus increasing its liquidity. Saving points are awarded for one’s saving efforts. For example, saving one Swedish crown for one month yields one savings point, and one crown borrowed for one month consumes one savings point. Thus savings points are used to ensure the sustainability of the system. Savings points are earned by the member on savings that accumulate prior to exercising the loan option and on savings accumulated during the loan repayment period.

**В озвучку попало:**

> «Сберегательные баллы» — это внутренняя кооперативная валюта. С их помощью JAK управляет вкладами и кредитами, поддерживая ликвидность системы. Баллы начисляются за накопления: например, одна шведская крона, пролежавшая на счету месяц, дает один балл, а кредит в одну крону на тот же срок — один балл «забирает». Таким образом, баллы обеспечивают устойчивость системы. Участник зарабатывает их как до получения кредита, так и в период его погашения.

---

### 10. `p1118` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> John Stephen Lansing, a professor at the Santa Fe Institute whose research explores the ecol ogy, common property, and social theories of Bali, as well as integrative modeling of environmental changes, explains that an agrarian system of rice cultivation fl ourished there for almost 1,000 years.¹ Then, in the 1970s, the World Bank insisted, as part of its fi nancial aid package, that the “unsophisticated traditional methods” be replaced with modern techniques and know- how, coupled with the use of chemical fertilizers. The well- documented experiment was a disaster, causing crop failures and massive ecological issues, such as the depletion of large swaths of native coral reefs. It was then decided that the customary agricultural practices could be reintroduced.

**В озвучку попало:**

> Джон Стивен Лэнсинг, профессор Института Санта-Фе, исследующий экологию, общую собственность и социальные теории Бали, отмечает, что аграрная система выращивания риса процветала там почти тысячу лет. Однако в семидесятые годы двадцатого века Всемирный банк в рамках финансовой помощи настоял на замене «несовершенных традиционных методов» современными технологиями и химическими удобрениями. Этот эксперимент закончился катастрофой: урожаи погибли, а экология острова, включая коралловые рифы, серьезно пострадала. В итоге было решено вернуть привычные методы ведения сельского хозяйства.

---

### 11. `p1050` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Mostly forgotten today is that the large number of cooperative currencies arose in the aftermath of the German hyperinfl ation of the 1920s, when the Reichsmark, the German currency at the time, became worthless. Similarly, there was an explosion of local currencies in both Western Eu rope and North America following the economic crash of 1929 and, more recently, in Argentina, following the collapse of its national currency in 2001. And now, at present, there is a resurgence of cooperative currencies and other innovations as the shadow of recession looms, but the dire consequences and tough lessons from these experiences seem to have lapsed from memory.

**В озвучку попало:**

> Сегодня почти забыто, что множество кооперативных валют возникло после гиперинфляции в Германии двадцатых годов, когда рейхсмарка обесценилась. Похожий всплеск появления местных денег произошел в Западной Европе и Северной Америке после краха 1929 года, а позднее — в Аргентине, после обвала национальной валюты в 2001 году. Сейчас, когда над миром вновь нависла тень рецессии, мы наблюдаем возрождение кооперативных валют и другие инновации. Однако суровые уроки прошлого, кажется, уже стерлись из памяти.

---

### 12. `p0400` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> In nature’s networks, there is a constant push- pull between two emergent properties: effi ciency and resilience. *Effi ciency* is defi ned as a network’s capacity to pro cess volume of what ever fl ows through it in an or ga nized and streamlined manner. *Resilience* is a network’s capacity to deal with and adapt to changes, while maintaining the integrity of the network. So for a complex fl ow network to sustain itself, it must be not only effi ciently or ga nized but also able to adjust to changes in its environment, such as droughts, famine, disease, or attacks in a natural ecosystem. What make a network resilient is its options or choices, which can be best expressed as a network having access to *di**versity* and *interconnectivity.*

**В озвучку попало:**

> В природных сетях постоянно идет борьба между двумя свойствами: эффективностью и устойчивостью. Эффективность — это способность сети обрабатывать потоки организованно и быстро. Устойчивость — это способность сети справляться с изменениями, сохраняя свою целостность. Чтобы сложная сеть могла существовать долго, она должна быть не только эффективной, но и способной адаптироваться к внешним условиям, таким как засуха, голод, болезни или внешние угрозы. Устойчивость сети обеспечивается наличием выбора, который лучше всего выражается через разнообразие и взаимосвязанность.

---

### 13. `p0278` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> A year passes and on another market day the stranger with the styl-ish hat returns, and from his vantage point he observes the village below. While sitting under the broad- limbed oak tree, he reaches into his knapsack and pulls out a silver canteen fi lled with a single- malt whis-key, takes a swig, savoring its peaty warmth at the back of his throat, and waits for the village folk to fi le past him with each family’s repayment of the eleventh round.

**В озвучку попало:**

> Прошел год. В очередной базарный день незнакомец в стильной шляпе вернулся. С высоты своего положения он наблюдал за деревней. Сидя под раскидистым дубом, он достал из сумки серебряную фляжку с односолодовым виски, сделал глоток, смакуя его торфяное тепло, и стал ждать, пока сельские жители пройдут мимо него, чтобы вернуть по одиннадцатому кружку.

---

### 14. `p0146` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> At the core of these assumptions is the false belief that it is merely the lack of money that is the problem. If there were more to go around, everything could be put to rights. However, what you’ll discover in the following pages is this: It is not the *amount* of money in circulation that is the root cause of this current malaise. It’s the *type* of money that is being used.

**В озвучку попало:**

> В основе этих заблуждений лежит ложное убеждение, будто проблема лишь в нехватке денег. Мол, если бы их было больше, всё наладилось бы само собой. Однако на следующих страницах вы узнаете, что корень нынешних проблем кроется не в количестве денег, находящихся в обращении, а в самой их природе.

---

### 15. `p0605` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Stodder added, “So when conventional banks are cutting their credit because there’s a big lack of fi nancial confi dence, and banks are essentially closing their doors to small creditors, there’s no question that historically these periods are those in which cooperative currencies spring up. It happened during the Great Depression, and it’s happened again during the current world downturn.”

**В озвучку попало:**

> [curious] Стоддер добавил: «Когда обычные банки сокращают кредитование из-за нехватки финансового доверия и фактически закрывают двери для малых заемщиков, кооперативные валюты неизбежно выходят на первый план. Так было во время Великой депрессии, и это происходит снова во время нынешнего мирового спада».

---

### 16. `p0687` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> A carbon premium exchange (CPX) system could be an Internet-based information exchange system where additional data about the carbon credit producers are made available to potential buyers— for example, their exact location, type of soil used, volume of crops produced, and individual history of carbon sequestration. Since the verifi ability of carbon sequestration is a key criterion for registration of projects under the clean development mechanism (CDM) of the Kyoto Protocol, information about the producers and their sequestering process would, in any case, need to be mea sured.

**В озвучку попало:**

> Система обмена углеродными премиями могла бы стать интернет-платформой, где покупатели получают доступ к дополнительным данным о производителях углеродных кредитов. Например, к их точному местоположению, типу почвы, объему урожая и истории поглощения углерода. Поскольку проверяемость поглощения углерода — ключевой критерий для регистрации проектов в рамках Киотского протокола, информация о производителях и их методах в любом случае должна фиксироваться.

---

### 17. `p0071` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Circumstances like these generate revolutions. The Agricultural Revolution. The Industrial Revolution. The American Revolution. We have entered such a time. Future historians, I believe, will defi ne this as a Revolution in Consciousness. People around the world are waking up to the fact that a very few extremely wealthy individuals are enslav-ing the rest of us. The shackles take the form of the currencies and debt that are interwoven with global monetary systems.

**В озвучку попало:**

> Подобные обстоятельства порождают революции. Аграрную, промышленную, американскую. Мы вступили в такое время. Я верю, что будущие историки назовут его революцией сознания. Люди по всему миру начинают осознавать, что очень узкий круг невероятно богатых людей порабощает всех остальных. Оковы здесь — это валюты и долги, которыми пронизаны глобальные денежные системы.

---

### 18. `p1134` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> These are the same lessons learned from the Argentinean debacle, for instance, that convinced the German regio movement to incorporate the following principles into their eight conditions for a currency to be granted the use of the regio label, according to Margrit Kennedy, the initiator for the regio movement.¹¹ These conditions state that these criteria need to be satisfi ed:

**В озвучку попало:**

> Это те же уроки, которые были извлечены из аргентинского кризиса. Именно они убедили немецкое движение «регио» включить ряд принципов в свои восемь условий для получения валютой права использовать знак «регио», как утверждает инициатор движения Маргрит Кеннеди. Эти критерии должны быть соблюдены:

---

### 19. `p1326` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> With the press of a button, the replacement for a broken vacuum cleaner part, for example, will be instantaneous and localized, if not at home, then at the neighborhood print shop. In such a scenario, industrial hubs with their networks of roads and railways that support the distribution of goods will become a thing of the past.

**В озвучку попало:**

> Нажатием кнопки можно будет мгновенно получить замену сломанной детали пылесоса прямо у себя дома или в ближайшей мастерской печати. В таком сценарии промышленные центры с их сетью дорог и железных дорог, поддерживающих распределение товаров, уйдут в прошлое.

---

### 20. `p0230` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Smith’s inquiries were set against the background of the development of our modern- day banking system with the formation of central banks in Sweden and En gland, while the earlier discoveries of Newton and his contemporaries ignited the imaginations of the ruling and educated upper class. The Age of Enlightenment’s zeitgeist was one of cool- headed rationalism and empiricism, which stood in stark contrast to the era of dark religious superstition that had preceded it. For example, Newtonian physics made it possible to calculate the distance and velocity of a cannonball being shot out of a cannon and to predict the movement of the heavenly bodies in interstellar space, both with precise meticulous-ness, theoretically down to a fraction of an inch. Consequently, everything had to be mea sured and codifi ed. If it couldn’t be *sensed,* in other words quantifi ed, then it was deemed *nonsense* and duly dismissed.

**В озвучку попало:**

> [serious] Исследования Смита проходили на фоне формирования современной банковской системы и создания центральных банков в Швеции и Англии. В то же время открытия Ньютона и его современников будоражили воображение правящего класса. Дух эпохи Просвещения был пронизан хладнокровным рационализмом и эмпиризмом, что резко контрастировало с предшествующей эпохой религиозных суеверий. Например, ньютоновская физика позволяла с математической точностью рассчитать дистанцию и скорость полета пушечного ядра или предсказать движение небесных тел. В результате всё должно было быть измерено и систематизировано. Если что-то нельзя было «почувствовать» — то есть количественно измерить, — это объявлялось бессмыслицей и отбрасывалось.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p1009` — длина озвучки / длина оригинала: 1.81; классы правки: —

**Исходный абзац:**

> He explains that by getting involved in community projects such as garbage collection and a variety of renovation projects, people can earn a local currency that, in turn, is good for Internet access. As a *Time* magazine feature noted: “One of the surest signs that you’re in a

**В озвучку попало:**

> Он объясняет, что, участвуя в общественных проектах — например, в уборке мусора или ремонтных работах, — люди могут зарабатывать местную валюту, которую затем можно обменять на доступ в интернет. Как отмечалось в журнале «Тайм»: «Один из самых верных признаков того, что вы находитесь в развивающейся стране, — это мусор под ногами, что связано не столько с плохими привычками, сколько с тем, что организация вывоза отходов для бедного правительства является затратной и не самой приоритетной задачей».

---

### 2. `p0979` — длина озвучки / длина оригинала: 1.68; классы правки: —

**Исходный абзац:**

> Activities are centered around the town’s 100- year- old Miners’ Welfare Hall. The local activities are run by a community nonprofi t or ga-ni za tion, Creation Development Trust, which employs two workers to oversee the TimeBanking. For each hour of ser vice given to the community, a credit of one hour is exchanged. In the fi rst year, 150 people took part; there are now over 1,000 members and 30 groups; 15 new social enterprises have been established, and new learning opportuni-

**В озвучку попало:**

> Деятельность сосредоточена вокруг столетнего Зала благосостояния шахтеров. Местные инициативы управляются некоммерческой организацией Creation Development Trust, которая нанимает двух сотрудников для контроля за тайм-банкингом. За каждый час работы на благо общества начисляется один кредит. В первый год в программе участвовало сто пятьдесят человек, сейчас — более тысячи членов и тридцать групп. Создано пятнадцать новых социальных предприятий и открыты новые возможности для обучения. Участники вносят шестьдесят тысяч часов труда в год на нужды своего сообщества. Зал посещают в среднем шестьсот человек в неделю. Вход на мероприятия оплачивается либо временными кредитами, либо обычными деньгами: двухчасовой вечер бинго или киносеанс стоят два временных кредита, а трехчасовое культурное представление — три.

---

### 3. `p0555` — длина озвучки / длина оригинала: 1.34; классы правки: —

**Исходный абзац:**

> One of the strongest objections to issuing currency is that it could create uncontrollable infl ation. Infl ation is commonly defi ned by its outcome— higher prices— rather than its cause, which is simply too much money in circulation chasing too few goods and ser vices.

**В озвучку попало:**

> [serious] Одно из главных возражений против выпуска собственных денег заключается в том, что это якобы может вызвать неконтролируемую инфляцию. Однако инфляцию чаще определяют по её внешнему проявлению — росту цен, — а не по её истинной причине. А причина проста: слишком большое количество денег в обращении гонится за слишком малым количеством товаров и услуг.

---

### 4. `p0701` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> If this prospect isn’t tough enough, Silicon Valley entrepreneur Martin Ford writes about how automation eventually will eliminate most jobs.² Jeremy Rifkin makes a similar case in his insightful book, *The End of* *Work*. MIT economist David Autor predicts that automation will eliminate middle- class jobs, and shows that the trend of demand for mainly high- and low- wage extremes will continue for the foreseeable future.

**В озвучку попало:**

> [serious] Если эта перспектива кажется недостаточно суровой, предприниматель из Кремниевой долины Мартин Форд пишет о том, как автоматизация со временем уничтожит большинство профессий. Джереми Рифкин приводит аналогичные доводы в своей глубокой книге «Конец работы». Экономист из Массачусетского технологического института Дэвид Отор предсказывает, что автоматизация устранит рабочие места для среднего класса, и показывает, что спрос на крайности — либо очень высокооплачиваемый, либо низкооплачиваемый труд — сохранится в обозримом будущем.

---

### 5. `p0891` — длина озвучки / длина оригинала: 1.26; классы правки: —

**Исходный абзац:**

> “When we realized the low cost of monthly baskets of food, and how they helped those living in poverty by freeing up their limited resources to pay for other things, everybody got very excited. Instead of having to use all their money to buy food, they could now use the

**В озвучку попало:**

> «Когда мы осознали, насколько дешево обходятся продуктовые корзины и как они помогают бедным семьям, высвобождая их ограниченные ресурсы на другие нужды, все были в восторге. Теперь им не нужно было тратить все деньги на еду. Они могли использовать средства иначе и при этом быть уверенными, что их дети ходят в школу», — вспоминает Лернер.

---

### 6. `p0519` — длина озвучки / длина оригинала: 1.25; классы правки: —

**Исходный абзац:**

> TimeBanking to create a new form of extended family. It is too early to project cost savings. But a recent study reveals that, as home-based care gets cut by state governments, hospital costs are likely to rise as people put off preventive care or end up rehospitalized due to the lack of transitional care.

**В озвучку попало:**

> [thoughtful] Тайм-банкинг позволяет создать новую форму расширенной семьи. Пока рано говорить о конкретной экономии средств. Однако недавнее исследование показывает: когда государственные органы сокращают расходы на уход на дому, больничные расходы, скорее всего, вырастут. Люди начинают откладывать профилактику или попадают в больницу повторно из-за отсутствия необходимой поддержки.

---

### 7. `p0709` — длина озвучки / длина оригинала: 1.24; классы правки: —

**Исходный абзац:**

> The solution that emerged is called the Commercial Credit Circle, or C3 for short. The C3 plan uses insured invoices or other payment claims as backing for a liquid payment instrument within a business-to- business clearing network. Each recipient of such an instrument has the choice to either cash it in national money (at a cost) or directly pay its own suppliers with the proceeds in a cooperative currency backed by the insured invoice (at no cost).

**В озвучку попало:**

> [thoughtful] Решением стала система под названием «Коммерческий кредитный круг», или сокращенно C3. В основе модели C3 лежат застрахованные счета-фактуры или другие долговые обязательства. Они служат обеспечением для платежного инструмента внутри сети взаиморасчетов между компаниями. Получатель такого инструмента может либо обналичить его в национальной валюте за определенную комиссию, либо, что выгоднее, сразу расплатиться им со своими поставщиками. В последнем случае используется кооперативная валюта, обеспеченная страховкой счета, и комиссия не взимается.

---

### 8. `p1179` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> This phrase is still used today as a way of saying that money is unaffected by its source or its users.²³ What Jonker invented, by contrast, is a system of money that tracks all its users. The currency’s originator and its users leave an indelible imprint so that subsequent users can express their opinion. It is now possible to have “smelly money,” as a previous user’s reputation may stink!

**В озвучку попало:**

> Эта фраза до сих пор используется, чтобы подчеркнуть: деньги не зависят от своего происхождения или тех, кто ими пользовался. Система, которую предложил Йонкер, работает иначе: она отслеживает всех участников сделок. Создатель валюты и её пользователи оставляют неизгладимый след, позволяя последующим владельцам денег составить мнение о предыдущих. Теперь вполне можно столкнуться с «дурно пахнущими» деньгами, если репутация того, кто ими расплачивался, оставляет желать лучшего.

---

### 9. `p0721` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> The C3 will need to borrow 120,000 euros from a fi nancial institution for three months to fi nance the LED installer. The costs of this loan are much lower for the C3 network than for an individual company. The costs are covered by the fee paid by the municipality and the malus fee.

**В озвучку попало:**

> [serious] Сети C3 потребуется занять сто двадцать тысяч евро у финансовой организации на три месяца, чтобы профинансировать установщика светодиодов. Для сети C3 стоимость такого кредита значительно ниже, чем для отдельной компании. Эти расходы покрываются за счет комиссии, которую платит муниципалитет, и так называемого малуса — сбора за обмен.

---

### 10. `p0299` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> Debt- based money requires endless growth because borrowers must fi nd additional money to pay back the interest on their debt. For the better- rated debtors (e.g., in normal times, government debt), the interest is simply covered through additional debt, resulting in *compound* *interest:* paying interest on interest. Compound interest implies exponential growth in the long run, something mathematically impossible in a *fi nite* world.

**В озвучку попало:**

> [serious] Денежная система, основанная на долгах, требует бесконечного роста. Заемщикам постоянно нужны новые деньги, чтобы выплачивать проценты по своим обязательствам. У надежных должников, например, у государств в стабильные времена, проценты часто покрываются за счет новых займов. Это приводит к так называемым сложным процентам: когда приходится платить проценты на уже начисленные проценты. В долгосрочной перспективе сложные проценты означают экспоненциальный рост, что математически невозможно в условиях ограниченного мира.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1146` — совпадение символов с оригиналом: 24%; классы правки: —

**Исходный абзац:**

> Dee Hock is the found er and a former CEO of the VISA credit card association. Back in 1968, he convinced Bank of America to give up own ership and control of their BankAmericard credit card licensing program. The new entity was a nonstock membership corporation owned by its member banks. In 1976, its name changed to VISA. This new structure he calls a *chaord*, a word that comprises both the terms *chaos* and *order*.

**В озвучку попало:**

> Ди Хок — основатель и бывший генеральный директор ассоциации кредитных карт VISA. Еще в 1968 году он убедил Bank of America отказаться от владения и контроля над программой лицензирования кредитных карт BankAmericard. Новая организация стала неакционерной корпорацией, принадлежащей банкам-членам. В 1976 году она была переименована в VISA. Эту новую структуру он называет «хаорд» — слово, объединяющее понятия «хаос» и «порядок».

---

### 2. `p0004` — совпадение символов с оригиналом: 22%; классы правки: truncated_sentence

**Исходный абзац:**

> “*Rethinking Money* does a brilliant job of eradicating the concepts and stories that our economists and other professionals in the ﬁ eld hold dear. The authors write that ‘money is our last taboo,’ but they don’t recommend abolishing the ﬁ at zeitgeist. Rather, they wisely call on the various new currencies and other monetary innovations to complement the existing system.” —Nigel Seale, former worldwide Chairman, Earth Day International, and founder of Earth Day Canada

**В озвучку попало:**

> «Книга "Переосмысление денег" блестяще справляется с задачей разрушения стереотипов, которые так дороги нашим экономистам и другим профессионалам в этой области. Авторы пишут, что "деньги — это наше последнее табу", но они не призывают к отмене фиатных валют. Напротив, они мудро предлагают использовать новые валюты и другие денежные инновации как дополнение к существующей системе». — Найджел Сил, бывший председатель Earth Day International и основатель Earth Day Canada

---

### 3. `p0922` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Thomas Mayer, former chief economist for Deutsche Bank, made in July 2012 a proposal for Greece that is surprisingly radical for his background. It acknowledges that the great majority of Greeks don’t want to leave the euro and that they don’t agree with the extreme austerity program imposed in Greece.

**В озвучку попало:**

> Томас Майер, бывший главный экономист Deutsche Bank, в июле 2012 года выступил с предложением для Греции, которое выглядит удивительно радикальным для человека его уровня. Он признает, что подавляющее большинство греков не хотят отказываться от евро и не согласны с жесткой программой экономии, навязанной стране.

---

### 4. `p2240` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> He is a member of the Club of Rome; a Fellow at the World Academy of Arts and Sciences, the World Business Academy, and the Euro pe an Academy of Sciences and Arts; and a founding member of the Global Futures Forum. He currently resides in his native Belgium. He is fl uent in En glish, French, Spanish, German, and Dutch, and reads Latin and Greek.

**В озвучку попало:**

> Он является членом Римского клуба, почетным членом Всемирной академии искусств и наук, Всемирной бизнес-академии, Европейской академии наук и искусств, а также одним из основателей форума Global Futures Forum. В настоящее время он проживает в родной Бельгии. Бернар свободно владеет английским, французским, испанским, немецким и голландским языками, а также читает на латыни и древнегреческом.

---

### 5. `p0476` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> The LETS system can be used for any number of needs and transactions. For instance, Anne cuts hair, John fi xes cars, and Lisa is an organic farmer. Anne and John negotiate the price of a haircut and decide on L15 (15 LETS units) and $5. Anne’s account is credited L15, while John’s is debited L15. With her earned LETS credits, hairdresser Anne negotiates with farmer Lisa to get some organic vegetables for L10.

**В озвучку попало:**

> Систему LETS можно использовать для любых нужд и сделок. Например, Энн стрижет волосы, Джон чинит машины, а Лиза — фермер, выращивающий органические продукты. Энн и Джон договариваются о цене стрижки: 15 единиц LETS и 5 долларов. На счет Энн зачисляется 15 единиц, а со счета Джона списывается 15. Получив эти кредиты, парикмахер Энн договаривается с фермером Лизой о покупке овощей на 10 единиц LETS.

---

### 6. `p0445` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> The Glass- Steagall Act was repealed with the Gramm- Leach- Bliley Act, signed by President Clinton. Since then, this repeal has been blamed for triggering the subprime crisis and the collapse of Lehman Brothers in September 2008, which in turn precipitated the global banking scramble, leaving so many governments overindebted.

**В озвучку попало:**

> Закон Гласса — Стиголла был отменен законом Грэмма — Лича — Блайли, который подписал президент Клинтон. С тех пор эту отмену часто называют причиной ипотечного кризиса и краха банка Lehman Brothers в сентябре 2008 года. Эти события, в свою очередь, спровоцировали глобальную банковскую панику и привели к тому, что многие правительства оказались обременены огромными долгами.

---

### 7. `p0448` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> Second, although it is true that a Chicago Plan reform would eliminate the risk of widespread banking crashes and sovereign debt crises, there would still be monetary crises. In other words, the 145 banking crises and 76 sovereign- debt crises that have hit the world since 1970 would not have happened if such a reform had been in place. The 208 monetary crashes would not necessarily have been avoided.

**В озвучку попало:**

> Во-вторых, хотя реформа по «Чикагскому плану» действительно устранила бы риск масштабных банковских крахов и кризисов суверенного долга, денежные кризисы никуда бы не делись. Иными словами, 145 банковских кризисов и 76 кризисов суверенного долга, произошедших в мире с 1970 года, возможно, и не случились бы, но 208 денежных крахов, скорее всего, все равно бы произошли.

---

### 8. `p0666` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> There has been a solid push in recent years to reach out to other countries internationally. According to Miguel Ganzo, “There are projects underway to establish the JAK model in Germany, Spain, Italy, and Finland. The JAK bank in Denmark was established in 1931 and is totally in de pen dent from us. It started off strongly, then went through a period of decline, and is now on the rise again. There is also interest from Arab countries because our model respects traditional Shari’a principles.”

**В озвучку попало:**

> В последние годы банк активно расширяет свое присутствие на международном уровне. По словам Мигеля Ганзо, сейчас ведутся проекты по внедрению модели JAK в Германии, Испании, Италии и Финляндии. Банк JAK в Дании был основан еще в 1931 году и работает полностью независимо от нас. Он начал свою деятельность успешно, затем пережил период спада, а сейчас снова находится на подъеме. Также интерес проявляют арабские страны, поскольку наша модель соответствует традиционным принципам шариата.

---

### 9. `p0682` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> At present, there are technology silos that hamper the fl uid and seamless movement of money within the marketplace. Mark Fischer, found er of Inspire Commerce and a recognized e-commerce expert, comments, “In closed networks, users are captured in a specifi c channel.

**В озвучку попало:**

> Сейчас существуют технологические барьеры, которые мешают свободному и беспрепятственному движению денег на рынке. Марк Фишер, основатель компании Inspire Commerce и признанный эксперт в области электронной коммерции, отмечает: «В закрытых сетях пользователи оказываются заперты в рамках конкретного канала».

---

### 10. `p0901` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> In the case of Curitiba, the results of using a cooperative currency in purely economic terms are worth noting. From 1975 to 1995, the GDP of the city increased by 75 percent more than the rest of the state of Paraná and by 48 percent more than Brazil’s as a whole. The average Curitibano earned more than three times the country’s minimum wage. If nontraditional monetary gains, such as the exchange of garbage for provisions, are taken into consideration, the real total income for residents was at least 30 percent higher still. The results in human terms— in the renewal of dignity and hope for a better future— are incalculable.⁴

**В озвучку попало:**

> [serious] В случае Куритибы результаты использования кооперативной валюты с чисто экономической точки зрения заслуживают особого внимания. С 1975 по 1995 год валовой внутренний продукт города рос на 75 процентов быстрее, чем в остальной части штата Парана, и на 48 процентов быстрее, чем в целом по Бразилии. Средний житель Куритибы зарабатывал более чем в три раза больше минимальной заработной платы по стране. Если учесть нетрадиционные денежные доходы — например, обмен мусора на продукты питания, — то реальный совокупный доход жителей был еще как минимум на 30 процентов выше. Результаты в человеческом измерении, выраженные в восстановлении достоинства и надежды на лучшее будущее, просто невозможно переоценить.

---
## Абзацы, оставшиеся в озвучке на английском (1)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.

### 1. `narration#1450` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> International Architecture Exhibition, 85 131 International Monetary Fund (IMF), 144, Hate group, 182 182, 184 Health care, 14, 16; free clinic, 162– 165; International reserve currency, 57– 58 in Mae Hong Son, 205 Internet: community, 57– 58; technologies,

**В озвучку попало:**

> International Architecture Exhibition, 85 131 International Monetary Fund (IMF), 144, Hate group, 182 182, 184 Health care, 14, 16; free clinic, 162– 165; International reserve currency, 57– 58 in Mae Hong Son, 205 Internet: community, 57– 58; technologies,

---
## Пустые и почти пустые абзацы (24)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0496` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Park TimeBank. *Photo credit*: Zach Lipp.

**В озвучку попало:**

> Тайм-банк в парке. Фотограф: Зак Липп.

---

### 2. `p1141` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> 7. Guaranteed circulation of the currency.

**В озвучку попало:**

> 7. Гарантированное обращение валюты.

---

### 3. `p1195` — длина озвучки / длина оригинала: 0.80; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • a multitude of local cooperative currencies

**В озвучку попало:**

> • массу местных кооперативных валют;

---

### 4. `p1196` — длина озвучки / длина оригинала: 0.93; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • a wide variety of functional currencies

**В озвучку попало:**

> • широкий спектр функциональных валют.

---

### 5. `p1305` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> # From Scarcity to Sustainable Abundance

**В озвучку попало:**

> # От дефицита к устойчивому изобилию

---

### 6. `p1867` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Concentration of wealth, 21– 22, 49– 53,

**В озвучку попало:**

> Концентрация богатства, 21–22, 49–53,

---

### 7. `p1870` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Conjunto Palmeira, 103– 108, *104*, *105*

**В озвучку попало:**

> Конжунто Палмейра, 103–108, 104, 105

---

### 8. `p1887` — длина озвучки / длина оригинала: 0.25; классы правки: —

**Исходный абзац:**

> Denver, 11– 12 Credit: access to, 96; business cycle and, Development, 33 52; need for, 12; short- term, 126; in

**В озвучку попало:**

> Денвер, 11–12. Развитие, 33.

---

### 9. `p1913` — длина озвучки / длина оригинала: 0.41; классы правки: —

**Исходный абзац:**

> Flow network, 32– 33, 61– 63 226–227*n*13; wispos and, 156– 157.

**В озвучку попало:**

> Сеть потоков, 32–33, 61–63

---

### 10. `p1964` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Infrastructure, 15, 20– 21, 103, 194 227*n*21

**В озвучку попало:**

> Инфраструктура, 15, 20–21, 103, 194

---

### 11. `p1977` — длина озвучки / длина оригинала: 0.48; классы правки: —

**Исходный абзац:**

> Growth pressure, 2, 42– 43, 52– 53 Intergenerational thinking, 44

**В озвучку попало:**

> Давление роста, 2, 42–43, 52–53

---

### 12. `p1980` — длина озвучки / длина оригинала: 0.14; классы правки: —

**Исходный абзац:**

> International Architecture Exhibition, 85 131 International Monetary Fund (IMF), 144, Hate group, 182 182, 184 Health care, 14, 16; free clinic, 162– 165; International reserve currency, 57– 58 in Mae Hong Son, 205 Internet: community, 57– 58; technologies,

**В озвучку попало:**

> Happy Futures Global Challenge, 131

---

### 13. `p1984` — длина озвучки / длина оригинала: 0.28; классы правки: —

**Исходный абзац:**

> Holacracy, 191 165– 166, *166*; in multicurrency world, 55

**В озвучку попало:**

> Холакратия, 191.

---

### 14. `p2037` — длина озвучки / длина оригинала: 0.45; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Medium of exchange, 57, 58; assumption

**В озвучку попало:**

> ### Средство обмена

---

### 15. `p2041` — длина озвучки / длина оригинала: 0.35; классы правки: —

**Исходный абзац:**

> Mile High Business Alliance (MHBA), 104– 105, 107; Revolving Loan Fund,

**В озвучку попало:**

> Бизнес-альянс «Майл Хай».

---

### 16. `p2042` — длина озвучки / длина оригинала: 0.69; классы правки: —

**Исходный абзац:**

> 128– 130 129– 130. *See also* Debt; Student loan

**В озвучку попало:**

> Фонды револьверного кредитования.

---

### 17. `p2048` — длина озвучки / длина оригинала: 0.83; классы правки: —

**Исходный абзац:**

> Local currency, 5, 58– 59; BerkShare, 75,

**В озвучку попало:**

> Местные системы взаимных расчетов.

---

### 18. `p2056` — длина озвучки / длина оригинала: 0.17; классы правки: —

**Исходный абзац:**

> Overcrowding, 164 currency creation, 24, 27– 28; as Overdraft, 39 medium of exchange, 201; of money type, 63; privatization and, 20– 21; Panda, 32– 33 state- owned, 128

**В озвучку попало:**

> Мораль: страницы 48–49, 134.

---

### 19. `p2073` — длина озвучки / длина оригинала: 0.60; классы правки: —

**Исходный абзац:**

> National debt, 42– 43, 70, 145– 147, 227*n*21 Poverty trap, 108

**В озвучку попало:**

> Национальный долг, 42–43, 70, 145–147.

---

### 20. `p2076` — длина озвучки / длина оригинала: 0.49; классы правки: —

**Исходный абзац:**

> National Program of Oriented Productive Principled society, 193– 194

**В озвучку попало:**

> Принципиальное общество, 193–194.

---

### 21. `p2082` — длина озвучки / длина оригинала: 0.29; классы правки: —

**Исходный абзац:**

> Nigeria, 42– 43 Profi t- neutral investment system,

**В озвучку попало:**

> Нигерия, 42–43.

---

### 22. `p2131` — длина озвучки / длина оригинала: 0.57; классы правки: —

**Исходный абзац:**

> Revolving Loan Fund, 128– 130 Solidus, 24, 65, 227*n*2, 230*n*9

**В озвучку попало:**

> Револьверный кредитный фонд, 128–130

---

### 23. `p2201` — длина озвучки / длина оригинала: 0.93; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### United Nations Environmental Program

**В озвучку попало:**

> ### Программа ООН по окружающей среде

---

### 24. `p2218` — длина озвучки / длина оригинала: 0.33; классы правки: —

**Исходный абзац:**

> Work, 219– 220, 239*n*10 bility (VBSR), 102– 103

**В озвучку попало:**

> Работа, 219–220.

---
