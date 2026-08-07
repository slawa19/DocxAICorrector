# Аудиокнига, прогон четырёх книг 2026-08-06 — rethinking_money, материал для просмотра глазами

Книга: Bernard Lietaer & Jacqui Dunne, *Rethinking Money* (`tests/sources/book/Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.pdf`).
Режим: `processing_operation = "audiobook"`, профиль `ui-parity-standalone-audiobook`, en → ru.
Модель: `openrouter:google/gemini-3.1-flash-lite-preview`.
Run id: `20260806T_ab4_rethinking_money`. Seed выборки: `20260804` (тот же, что 2026-08-04).

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
6. **Пустые и почти пустые абзацы — все 39**: исходный абзац ≥ 40 символов, а в озвучке < 40.

Всего абзацев отдано модели: 2187; вернулось: 2186;
дошло до narration-артефакта: 2183.
Пул прозы, из которого делалась выборка: 670 абзацев.
Медианное отношение длин по прозе: 0.973.

---
## Случайная выборка (55 абзацев прозы)

Начало / середина / конец книги, до 20 абзацев из каждой трети, seed `20260804`.

### 1. `p0018` — длина озвучки / длина оригинала: 1.09; классы правки: truncated_sentence

**Исходный абзац:**

> “The new understanding this book offers is critical because economics has become the dominant—and increasingly only—discipline with which important decisions are being made. This is a must-read for anyone who wants to be part of the timely conversation on how to move forward to create the just, sustainable, and equitable world we all desire.” —Thom Hartmann, internationally syndicated talk show host and author of twenty-four books

**В озвучку попало:**

> «Новое понимание, которое предлагает эта книга, критически важно, поскольку экономика стала доминирующей — и все чаще единственной — дисциплиной, на основе которой принимаются важные решения. Это обязательное чтение для каждого, кто хочет участвовать в своевременной дискуссии о том, как двигаться вперед к справедливому, устойчивому и равноправному миру, которого мы все желаем». — Том Хартманн, ведущий международного синдицированного ток-шоу и автор двадцати четырех книг

---

### 2. `p0090` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Soon money became the tool empires used in a global dash for assets in a world that didn’t seem to lack for earth, water, air, and natural resources. A contrivance of competition, it pitted one against the other in a fabricated Darwinian contest of survival, refl ecting and perpetuat-ing the values and the Zeitgeist of that time.

**В озвучку попало:**

> Вскоре деньги стали инструментом империй в глобальной гонке за активами в мире, где, казалось, нет недостатка в земле, воде, воздухе и природных ресурсах. Будучи механизмом конкуренции, они стравливали людей друг с другом в искусственном дарвиновском состязании за выживание, отражая и закрепляя ценности и дух того времени.

---

### 3. `p0103` — длина озвучки / длина оригинала: 0.87; классы правки: —

**Исходный абзац:**

> Regular people have discovered not only that it is possible to create money in suffi ciency for their needs but also that it is simultaneously possible to build their societies with greater cooperation, care, and collaboration. In other words, they are proving not only that it is possible to redesign money but also that doing so fosters very different and highly desirable outcomes.

**В озвучку попало:**

> Обычные люди обнаружили, что можно не только создавать деньги в достаточном для своих нужд количестве, но и одновременно строить общество на принципах сотрудничества, заботы и взаимодействия. Иными словами, они доказывают, что перепроектирование денег не только возможно, но и ведет к совершенно иным, крайне желательным результатам.

---

### 4. `p0134` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> In the history of the United States, this is the fi rst time when the younger generation of people will be poorer and less educated than their parents.² In a country that claims to be one of the richest in the world, some 100 million people— one in three Americans— either lives in poverty or in the distressed zone hovering just above the offi cial poverty threshold.³ More than one in three Americans lived in house holds that received Medicaid, food stamps, or other means- based government assistance in mid- 2010, according to an analysis of the 2010 census. And when Social Security, Medicare, and unemployment benefi ts are included, nearly half of the nation lived in a house hold that received a government check.⁴ According to the *New York Times*, “Demographically, they look more like ‘The Brady Bunch’ than ‘The Wire.’ Half live in house holds headed by a married couple; 49 percent live in the suburbs. Nearly half are non- Hispanic white, 18 percent are black, and 26 percent are Latino. Perhaps the most surprising fi nding is that 28 percent work full- time, year round. These estimates defy the ste reo types of low-income families.”⁵

**В озвучку попало:**

> Впервые в истории Соединенных Штатов молодое поколение будет беднее и менее образованно, чем их родители. В стране, которая считается одной из самых богатых в мире, около ста миллионов человек — это каждый третий американец — живут либо в нищете, либо на грани официального порога бедности. По данным анализа переписи населения 2010 года, более трети американцев жили в семьях, получавших талоны на питание, медицинскую помощь по программе «Медикейд» или другие виды государственной поддержки. А если учесть социальное обеспечение, программу «Медикэр» и пособия по безработице, то почти половина страны жила в домохозяйствах, получавших государственные чеки. Как отмечает газета «Нью-Йорк Таймс», демографически эти люди больше похожи на персонажей сериала «Семейка Брейди», чем на героев «Прослушки». Половина из них живет в семьях, возглавляемых супружеской парой, сорок девять процентов живут в пригородах. Почти половина — белые нелатиноамериканского происхождения, восемнадцать процентов — чернокожие, двадцать шесть процентов — латиноамериканцы. Пожалуй, самый удивительный факт заключается в том, что двадцать восемь процентов из них работают полный рабочий день круглый год. Эти цифры разрушают стереотипы о малообеспеченных семьях.

---

### 5. `p0141` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> Yet, the commonly trotted- out explanations for all that ails the fi - nancial systems, or conversely what is working, just don’t provide the complete picture. There is a yearning to put into language something that still remains elusive, lingering in the shadows of awareness just out of reach. It’s that gnawing feeling in the pit of the stomach that something deeper is going on, something that can’t quite be brought to consciousness, let alone expressed in words.

**В озвучку попало:**

> И все же привычные объяснения того, что не так с финансовыми системами или, наоборот, что в них работает, не дают полной картины. Существует потребность выразить словами то, что остается неуловимым, скрываясь в тенях нашего сознания. Это то самое грызущее чувство в глубине души: что-то идет не так, что-то более глубокое, что невозможно до конца осознать, а тем более выразить словами.

---

### 6. `p0146` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> At the core of these assumptions is the false belief that it is merely the lack of money that is the problem. If there were more to go around, everything could be put to rights. However, what you’ll discover in the following pages is this: It is not the *amount* of money in circulation that is the root cause of this current malaise. It’s the *type* of money that is being used.

**В озвучку попало:**

> В основе этих заблуждений лежит ложная вера в то, что проблема заключается лишь в нехватке денег. Мол, если бы их было больше, всё наладилось бы само собой. Однако на следующих страницах вы обнаружите иное: корень нынешнего недуга кроется не в количестве денег в обращении, а в самой их природе — в том, какого типа деньги мы используем.

---

### 7. `p0172` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> And fi nally, and perhaps most important, is the *crisis of identity,* particularly for those who have inherited wealth. The questions of self- worth and one’s uniqueness, which arise for everyone, become much more painful when one is seen by others as having money. Phi los-o pher Jacob Needleman observes, “The only thing that money will not buy is meaning.”¹⁷ Often, wealthy people suffer from guilt, anxiety, and a sense of meaninglessness.

**В озвучку попало:**

> И, наконец, самое важное — это кризис идентичности, особенно у тех, кто получил наследство. Вопросы о собственной ценности и уникальности, которые возникают у каждого, становятся гораздо болезненнее, когда окружающие видят в тебе прежде всего деньги. Философ Джейкоб Нидлман отмечает: «Единственное, что нельзя купить за деньги, — это смысл». Часто богатые люди страдают от вины, тревоги и ощущения бессмысленности существования.

---

### 8. `p0173` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> In an environment and culture where so much is shaped by fi nancial worth, the scarcest commodity seems to be trust. Indeed, each of these four conditions shares a common thread— the loss of trust in society, in friends, in family, and fi nally, in oneself. An all- too- common response to the issues faced by the wealthy is “I wish I had that problem.” This denies, however, the depth of the anguish experienced by some and the reality that money has become an equal- opportunity problem maker.

**В озвучку попало:**

> В культуре, где так многое определяется финансовым состоянием, самым дефицитным товаром кажется доверие. Действительно, все эти четыре состояния объединяет общая нить: потеря доверия к обществу, друзьям, семье и, наконец, к самому себе. Слишком распространенный ответ на проблемы богатых звучит так: «Мне бы такие проблемы». Однако это отрицает глубину страданий, которые испытывают некоторые люди, и тот факт, что деньги стали источником проблем для всех, независимо от достатка.

---

### 9. `p0252` — длина озвучки / длина оригинала: 1.06; классы правки: —

**Исходный абзац:**

> As economists Clifford Cobb, Ted Halstead, and Jonathan Rowe point out, “The GDP not only masks the breakdown of the social structure and the natural habitat upon which the economy— and life itself— ultimately depend; worse, it actually portrays such breakdown as economic gain.”¹⁰ Herman Daly put it this way: “The current national accounting system treats the earth as a business in liquidation.”¹¹

**В озвучку попало:**

> Как отмечают экономисты Клиффорд Кобб, Тед Холстед и Джонатан Роу: «Валовой внутренний продукт не только маскирует разрушение социальной структуры и природной среды, от которых в конечном счете зависят экономика и сама жизнь; хуже того, он фактически выдает это разрушение за экономический рост». Герман Дейли выразился еще резче: «Нынешняя система национального учета относится к Земле как к бизнесу в процессе ликвидации».

---

### 10. `p0343` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> The fi rst eight groups of house holds are in the negative, which means that they have paid out more in interest than they received. In the ninth group, interest gained and paid roughly cancel each other out. However, in the tenth group, the total gains add up to the total losses of the fi rst eight groups.

**В озвучку попало:**

> Первые восемь групп домохозяйств оказались в минусе: они выплатили процентов больше, чем получили. В девятой группе полученные и выплаченные проценты примерно сравнялись. Однако в десятой группе общая сумма прибыли от процентов в точности соответствует суммарным потерям первых восьми групп.

---

### 11. `p0382` — длина озвучки / длина оригинала: 1.07; классы правки: —

**Исходный абзац:**

> There are thousands of new monetary pacts operating within communities in the United States and beyond that are not conducted solely with legal tender, leading to some very different outcomes. These pacts are called “common tender,” in contrast with “legal tender.”

**В озвучку попало:**

> Сегодня в Соединенных Штатах и за их пределами действуют тысячи новых денежных соглашений, которые не ограничиваются только законным платежным средством. Они приводят к совершенно иным результатам. Такие соглашения называют «общепринятым платежным средством» в противовес «законному».

---

### 12. `p0390` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> Today, we have a plethora of both unmet needs and unused resources. Cooperative currencies tie these together and get the fundamental circuit of giving and receiving, buying and selling, moving again as people get their lives back on track. Completely new circuits of trade are being established by ordinary people as they create new solutions to their area’s problems. Accordingly, a community can be anything from a small local neighborhood to a group of multinational companies doing business together. The actual currency can address many issues: for example, the creation of an el der ly care currency, an energy conservation currency, or a local food- growing currency. When and wherever there is an unused resource and an unmet need in an economy, they can be linked with a purposefully designed currency. The or ga ni za tion responsible for the issuance of a currency can be a nonprofi t, a religious entity, a business federation, a community group, a union, a company, a government agency, or, of course, any body of government from a municipality to the federal echelon. In reality, the only conceptual limitation is imagination. Together with conventional national currencies, they can form what we call a monetary ecosystem.

**В озвучку попало:**

> [thoughtful] Сегодня мы видим множество неудовлетворенных потребностей и неиспользуемых ресурсов. Кооперативные валюты связывают их воедино, запуская фундаментальный цикл обмена — отдачи и получения, покупки и продажи. Люди возвращаются к активной жизни, а обычные граждане выстраивают совершенно новые торговые цепочки, создавая решения для проблем своего региона. Сообществом может быть как небольшой район, так и группа транснациональных корпораций. Валюта может решать самые разные задачи: например, оплата ухода за пожилыми людьми, стимулирование энергосбережения или поддержка местного фермерства. Везде, где есть неиспользуемый ресурс и неудовлетворенная потребность, можно внедрить специально разработанную валюту. Эмитентом может выступать кто угодно: от некоммерческой организации или религиозной общины до бизнес-федерации, профсоюза, компании или государственного органа любого уровня. Единственное ограничение здесь — это воображение. Вместе с традиционными национальными деньгами такие инструменты формируют то, что мы называем денежной экосистемой.

---

### 13. `p0558` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> In the case of simple barter exchanges, where no currency is involved at all, the only effect of such an exchange is who owns what. No infl ationary pressures arise from barter exchanges, given that the overall quantity of both goods and currency in circulation remains unchanged.

**В озвучку попало:**

> В случае простого бартера, где деньги вообще не используются, единственным результатом обмена является переход права собственности. Бартер не создает инфляционного давления, поскольку общий объем товаров и денежная масса в обращении остаются неизменными.

---

### 14. `p0561` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> The ability of businesses themselves to better manage their excess capacity— from a theoretical infl ation- control viewpoint— is one of the intriguing aspects of using a cooperative currency approach. Within a fi at currency environment, there is no easy way for businesses to dif-ferentiate among customers to improve the use of their spare capacity and thus increase productivity.

**В озвучку попало:**

> Способность бизнеса лучше управлять избыточными мощностями — с точки зрения контроля над инфляцией — один из самых интересных аспектов использования кооперативных валют. В условиях фиатной денежной системы у компаний нет простого способа дифференцировать клиентов, чтобы эффективнее использовать резервные мощности и повышать производительность.

---

### 15. `p0565` — длина озвучки / длина оригинала: 0.82; классы правки: —

**Исходный абзац:**

> As Edgar Kampers, Director of Qoin— Money That Matters, a Dutch not- for- profi t or ga ni za tion that designs, implements, and supports community cooperative currencies, cogently remarks, “It’s critical to understand the defi nition of the word *currency.* So for me currency is information between a buyer and a seller. Two people are involved in a transaction where the money symbolizes the exchange of value. So, I buy a sweater. We agree that it’s worth 20 units of what ever. The sweater is the thing with the value; the money is not, of course. Money is not valuable at all, but money allows you to buy things, which are valuable.

**В озвучку попало:**

> [thoughtful] Эдгар Камперс, директор голландской некоммерческой организации Qoin, которая занимается разработкой и внедрением местных кооперативных валют, замечает: «Важно понимать определение слова "валюта". Для меня валюта — это информация между покупателем и продавцом. Двое людей участвуют в сделке, где деньги символизируют обмен ценностями. Я покупаю свитер. Мы договариваемся, что он стоит 20 условных единиц. Ценность имеет свитер, а не деньги. Деньги сами по себе не ценны, но они позволяют покупать ценные вещи».

---

### 16. `p0643` — длина озвучки / длина оригинала: 1.13; классы правки: —

**Исходный абзац:**

> “Our plans are to create 1,000 banks in the near future, of which 300 should be in the northeast of Brazil, and to have at least one community bank in each state of Brazil. Furthermore, we’d like to help spread this community banking network across Latin America.

**В озвучку попало:**

> «В ближайшем будущем мы планируем создать тысячу таких банков, триста из которых должны появиться на северо-востоке Бразилии. Мы хотим, чтобы хотя бы один общественный банк был в каждом штате страны. Кроме того, мы стремимся распространить эту сеть общественных банков по всей Латинской Америке».

---

### 17. `p0649` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> The loans are fi nanced solely by members’ savings. No money is made by the bank for providing these loans, nor is money made by the banks’ customers on their savings with the bank. In a nutshell, the bank does not partake in the traditional banking practice of money creation.

**В озвучку попало:**

> Кредиты здесь финансируются исключительно за счет сбережений самих участников. Банк не получает прибыли от выдачи займов, а вкладчики, в свою очередь, не получают процентов по своим депозитам. По сути, банк не занимается традиционным для финансового сектора созданием денег.

---

### 18. `p0666` — длина озвучки / длина оригинала: 0.94; классы правки: —

**Исходный абзац:**

> There has been a solid push in recent years to reach out to other countries internationally. According to Miguel Ganzo, “There are projects underway to establish the JAK model in Germany, Spain, Italy, and Finland. The JAK bank in Denmark was established in 1931 and is totally in de pen dent from us. It started off strongly, then went through a period of decline, and is now on the rise again. There is also interest from Arab countries because our model respects traditional Shari’a principles.”

**В озвучку попало:**

> В последние годы банк активно расширяет свое присутствие на международной арене. По словам Мигеля Ганзо, сейчас ведутся проекты по внедрению модели JAK в Германии, Испании, Италии и Финляндии. Банк JAK в Дании был основан в 1931 году и полностью независим от нас. Он начал свою работу успешно, затем пережил период спада, а сейчас снова находится на подъеме. Также интерес проявляют арабские страны, поскольку наша модель соответствует традиционным принципам шариата.

---

### 19. `p0693` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> The convergence between ever- cheaper computing and growing access to the Internet and to mobile phones will drastically change the global banking scene. More important, it will trigger the proliferation of further innovations and real prosperity around the globe, in domains that today seem to be the stuff of science fi ction.

**В озвучку попало:**

> [excited] Сближение всё более дешевых вычислительных мощностей с растущим доступом к интернету и мобильным телефонам кардинально изменит мировую банковскую сферу. Что еще важнее, это спровоцирует волну инноваций и реального процветания по всему миру в тех областях, которые сегодня кажутся научной фантастикой.

---

### 20. `p0743` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> Then the Teachers’ Cooperative Patricia was part of joined the C3 Program. Like all members of this and other cooperatives (civil ser-vants, professionals, police offi cers, the retired), Patricia now can view, choose, change, pay, and receive the purchased items from the store closest to her residence. A signifi cant number of consumer cooperatives are keen to be a part of this program, which is only viable when they, together with the chain of suppliers, are all part of the C3 network. The decentralization of ser vices and the social inclusion are part of state policy, and obviously this scheme supports these objectives.

**В озвучку попало:**

> [thoughtful] Ситуация изменилась, когда кооператив Патрисии присоединился к программе C3. Теперь она и другие участники — госслужащие, специалисты, полицейские и пенсионеры — могут выбирать, оплачивать и получать товары в ближайшем к дому магазине. Многие потребительские кооперативы стремятся стать частью этой программы. Она эффективна только тогда, когда и сами кооперативы, и сеть поставщиков объединены в систему C3. Децентрализация услуг и социальная интеграция являются частью государственной политики, и эта схема, безусловно, помогает достижению таких целей.

---

### 21. `p0756` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> The Hub is a place for purpose- driven people to connect and build solutions for a better world. “Members work at the Hub, attend and produce events, run their own boot camps, access funding and men-torship, source clients and coconspirators, fi nd social networks, build campaigns, launch companies, prototype and test products. The members can create what they want, as it is their space and their community to build upon,” says Jean Luc Roux, a member of the board of the Brussels chapter.

**В озвучку попало:**

> Хаб — это место, где люди с общими целями могут объединяться и создавать решения для улучшения мира. Члены сообщества работают в Хабе, посещают и организуют мероприятия, проводят собственные интенсивы, получают доступ к финансированию и наставничеству, находят клиентов и единомышленников, расширяют социальные связи, запускают кампании, создают компании, а также тестируют прототипы продуктов. Как говорит Жан-Люк Ру, член совета директоров брюссельского отделения, участники могут создавать всё, что захотят, ведь это их пространство и их сообщество.

---

### 22. `p0760` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> “Before, people were working more alone, looking at the other not necessarily as a friend, not necessarily as a collaborator, but more as a potential competitor. And now, because they can offer ser vices among themselves, they see that they have more to win by working together.

**В озвучку попало:**

> «Раньше люди работали обособленно. Они видели в других не обязательно друзей или партнёров, а скорее потенциальных конкурентов. Теперь, когда они могут предлагать услуги друг другу, они понимают, что сотрудничество приносит гораздо больше пользы».

---

### 23. `p0779` — длина озвучки / длина оригинала: 1.10; классы правки: —

**Исходный абзац:**

> Many pre ce dents demonstrate that whenever attempts at regulation or moral persuasion run up against fi nancial interests, the latter tends to win. The war against drugs is but one example. The Terra provides a solution that doesn’t pit fi nancial interests against human concerns— in other words, it is a real- world solution.

**В озвучку попало:**

> Множество примеров доказывает: когда попытки регулирования или морального убеждения сталкиваются с финансовыми интересами, последние обычно побеждают. Война с наркотиками — лишь один из примеров. Валюта «Терра» предлагает решение, которое не противопоставляет финансовые интересы человеческим потребностям. Иными словами, это решение, применимое в реальном мире.

---

### 24. `p0883` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> Thousands of children responded by picking the neighborhoods clean. The children have taught their parents how to do it. Lerner no-ticed that to earn bus tokens, some slum dwellers even collected and sorted garbage along the highways, making it easier to get the waste picked up by trucks.

**В озвучку попало:**

> Тысячи детей начали очищать свои районы от мусора. Они научили этому своих родителей. Лернер заметил, что ради автобусных жетонов некоторые жители трущоб даже собирали и сортировали мусор вдоль шоссе, что облегчало работу мусоровозам.

---

### 25. `p0896` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> The many initiatives— environmental cleanup, city restoration, job creation, improved education, disease intervention, and hunger prevention— were each tackled with various cooperative currency systems. This all happened without having to raise taxes, redistribute wealth, issue bonds, rely on charity, or obtain loans from the federal government or organizations such as the World Bank and the International Monetary Fund (IMF). The improvements burdened no one.

**В озвучку попало:**

> Многие инициативы — очистка окружающей среды, восстановление города, создание рабочих мест, улучшение образования, борьба с болезнями и предотвращение голода — решались с помощью различных систем кооперативных валют. Всё это происходило без повышения налогов, перераспределения богатства, выпуска облигаций, опоры на благотворительность или получения кредитов от федерального правительства и таких организаций, как Всемирный банк или Международный валютный фонд. Эти улучшения никого не обременяли.

---

### 26. `p0921` — длина озвучки / длина оригинала: 0.90; классы правки: —

**Исходный абзац:**

> In terms of a national crisis, a C3 currency, as explored in Chapter 7, could be used to take care of some of the commercial business currently conducted in national currencies. In a case for the eurozone, for example, countries like Spain, Portugal, Greece, or whichever is in trouble could continue using the euro currency for everything having to do with international activities: tourism, shipping, importing, and exporting. Their respective governments could, in addition, create a new version of the peseta, escudo, or drachma to be used for internal social and environmental businesses. This neonational currency essentially could be spent into existence by the government itself, for specifi c purposes, without incurring debt in the fi nancial system.

**В озвучку попало:**

> В условиях национального кризиса можно использовать валюту типа C3, как мы рассматривали в седьмой главе, для обслуживания части коммерческих операций, которые сейчас проводятся в национальных деньгах. Возьмем, к примеру, еврозону: страны вроде Испании, Португалии или Греции могли бы продолжать использовать евро для всех международных операций — туризма, грузоперевозок, импорта и экспорта. В дополнение к этому их правительства могли бы создать новую версию песеты, эскудо или драхмы для внутренних социальных и экологических нужд. Эта «неонациональная» валюта, по сути, могла бы выпускаться самим правительством для конкретных целей, не создавая при этом долгов в финансовой системе.

---

### 27. `p0975` — длина озвучки / длина оригинала: 0.95; классы правки: —

**Исходный абзац:**

> The residents of Blaengarw worked their way out of the all- too-common story of social blight and decay by making an assessment of their unused resources and their unmet needs and, in this case, linking these with a time- banking currency coordinated by a regional and local NGO.

**В озвучку попало:**

> Жители Блангарва смогли выбраться из типичной ловушки социального упадка. Они оценили свои неиспользованные ресурсы и нереализованные потребности, а затем связали их с валютой тайм-банкинга, которую координировала региональная и местная некоммерческая организация.

---

### 28. `p0979` — длина озвучки / длина оригинала: 1.62; классы правки: —

**Исходный абзац:**

> Activities are centered around the town’s 100- year- old Miners’ Welfare Hall. The local activities are run by a community nonprofi t or ga-ni za tion, Creation Development Trust, which employs two workers to oversee the TimeBanking. For each hour of ser vice given to the community, a credit of one hour is exchanged. In the fi rst year, 150 people took part; there are now over 1,000 members and 30 groups; 15 new social enterprises have been established, and new learning opportuni-

**В озвучку попало:**

> Вся деятельность сосредоточена вокруг столетнего Зала шахтеров. Местными проектами управляет некоммерческая организация «Криэйшн Девелопмент Траст», которая нанимает двух сотрудников для контроля за тайм-банкингом. За каждый час работы на благо общества начисляется один кредит. В первый год участвовало сто пятьдесят человек, сейчас их уже более тысячи, а также тридцать групп. Создано пятнадцать новых социальных предприятий и открыты новые возможности для обучения. Участники вносят шестьдесят тысяч часов труда в год на нужды своего сообщества. Зал посещают в среднем шестьсот человек в неделю. Вход на мероприятия оплачивается либо временными кредитами, либо обычными деньгами: двухчасовой вечер бинго или киносеанс стоят два кредита, а трехчасовое культурное представление — три.

---

### 29. `p0995` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> They have made millions of dollars worth of trades with HOURS, representing hundreds of job equivalents at $20,000 each. Businesses accepting the local currency include the Ithaca Health Alliance, Cayuga Medical Center, Alternatives Federal Credit Union, the public library, many local farmers, movie theaters, restaurants, healers, plumbers, carpenters, electricians, and landlords.

**В озвучку попало:**

> С помощью этой валюты они совершили сделки на миллионы долларов, что эквивалентно сотням рабочих мест стоимостью по двадцать тысяч долларов каждое. Среди предприятий, принимающих местную валюту, — «Итака Хелс Альянс», медицинский центр «Каюга», федеральный кредитный союз «Альтернативы», публичная библиотека, многие местные фермеры, кинотеатры, рестораны, целители, сантехники, плотники, электрики и арендодатели.

---

### 30. `p1002` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> Glover explains, “The clinic will provide community- based health care that is genuinely nonprofi t, preventive, humane, and, in the spirit of Patch Adams, fun. It is a refuge for doctors and nurses who want time to heal patients. It is a refuge for patients who want to be treated with dignity. For a small annual fee, members will own this clinic, gaining diagnosis and referral, dentistry, chronic and urgent care, counseling, pediatrics, birthing, hospice care, massage, family planning, chi-ropractic, acu punc ture, and other therapies. “More than a health facility, the clinic is an economic development model that solves several urban problems. Existing medical facilities are overcrowded and underfunded. Suffering is untended, both mental and physical. Infectious disease rates are high.”⁷

**В озвучку попало:**

> Гловер поясняет: «Клиника обеспечит общественную медицинскую помощь, которая по-настоящему некоммерческая, профилактическая, гуманная и, в духе Пэтча Адамса, веселая. Это убежище для врачей и медсестер, которые хотят иметь время на лечение пациентов, и для пациентов, которые хотят, чтобы с ними обращались с достоинством. За небольшой ежегодный взнос участники становятся совладельцами клиники. Они получают доступ к диагностике, стоматологии, лечению хронических и острых заболеваний, психологической помощи, педиатрии, ведению родов, хосписной помощи, массажу, планированию семьи, хиропрактике, акупунктуре и другим методам терапии. Это больше, чем просто медицинское учреждение. Клиника — это модель экономического развития, решающая целый ряд городских проблем. Существующие медучреждения переполнены и недофинансированы, а люди страдают от отсутствия помощи — как физической, так и ментальной. Уровень инфекционных заболеваний остается высоким».

---

### 31. `p1005` — длина озвучки / длина оригинала: 1.08; классы правки: —

**Исходный абзац:**

> “Expenses are kept low by relying least on U.S. dollars. To the maximum possible, we rely on the gift economy, barter, and credit systems such as Time Dollars and HOURS (‘MediCash’). Staff members are primarily volunteers: professionals, students, religious congregants, neighbors, and members. Membership may be paid with labor to maintain the facility and its grounds. Both volunteers and staff may be rewarded with Philadelphia MediCash, (HOURS) gift certifi cates, health care, sweat equity credits, college course credit, and scholarships. Barter agreements will also meet personal needs,” he adds.⁸

**В озвучку попало:**

> «Расходы сведены к минимуму за счет минимального использования долларов США, — добавляет он. — Мы максимально опираемся на экономику дарения, бартер и кредитные системы, такие как "Тайм Долларс" и итака-часы, которые мы называем "МедиКэш". Персонал — это в основном волонтеры: профессионалы, студенты, прихожане церквей, соседи и члены сообщества. Членство можно оплатить трудом по обслуживанию здания и территории. Волонтеры и сотрудники могут получать вознаграждение в виде филадельфийских "МедиКэш", подарочных сертификатов, медицинских услуг, кредитов на обучение в колледже и стипендий. Бартерные соглашения также помогут закрыть личные потребности».

---

### 32. `p1099` — длина озвучки / длина оригинала: 1.16; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> So another important lesson for me was to do the preparations and training *before* the crisis starts. Today, I foresee the interface to be easier, thanks to cell phones, so people can access their accounts and make payments through their phones. I saw phones used to buy sodas in 2002 in Japan, and in South Africa in 2005, so eventually we shall have it in the United States as well.”²¹

**В озвучку попало:**

> «Так что еще один важный урок для меня — нужно проводить подготовку и обучение до того, как начнется кризис. Сегодня я предвижу, что интерфейсы станут проще благодаря мобильным телефонам, и люди смогут получать доступ к своим счетам и совершать платежи через них. Я видел, как телефоны использовали для покупки газировки в Японии в две тысячи втором году и в Южной Африке в две тысячи пятом, так что со временем это появится и в Соединенных Штатах».

---

### 33. `p1121` — длина озвучки / длина оригинала: 0.91; классы правки: —

**Исходный абзац:**

> Intertwined with their time- honored agricultural and social practices is the longest- surviving cooperative currency ecosystem in the world. Before Indonesian in de pen dence in 1945, the conventional currency was the Dutch guilder, followed by the Indonesian rupiah. Working in parallel with this conventional money is a social currency networked through the Banjar system, which has been in use since before written rec ords. Everyone in the Banjar is obliged to contribute to the well- being of the community by helping with jointly decided projects. The Banjar system extends beyond religious or cultural events and may include civic activities, such as support for building local roads, especially when the central government is unable to provide funding. In short, local resources are mobilized regularly to support a full spectrum of undertakings, what ever the community chooses to focus on. It is this system of mutual cooperation and assistance that accounts for the resiliency of Balinese culture.³

**В озвучку попало:**

> С этими древними сельскохозяйственными и социальными практиками тесно связана старейшая в мире кооперативная валютная экосистема. До обретения Индонезией независимости в 1945 году основной валютой был голландский гульден, а затем индонезийская рупия. Параллельно с официальными деньгами существовала социальная валюта, работающая через систему банджаров, которая использовалась еще до появления письменных источников. Каждый член банджара обязан вносить вклад в благополучие общины, помогая в реализации совместных проектов. Система банджаров охватывает не только религиозные или культурные события, но и гражданские инициативы, например, строительство местных дорог, когда центральное правительство не выделяет на это средства. Проще говоря, местные ресурсы регулярно мобилизуются для решения любых задач, которые считает важными община. Именно эта система взаимной помощи обеспечивает устойчивость балийской культуры.

---

### 34. `p1134` — длина озвучки / длина оригинала: 0.80; классы правки: —

**Исходный абзац:**

> These are the same lessons learned from the Argentinean debacle, for instance, that convinced the German regio movement to incorporate the following principles into their eight conditions for a currency to be granted the use of the regio label, according to Margrit Kennedy, the initiator for the regio movement.¹¹ These conditions state that these criteria need to be satisfi ed:

**В озвучку попало:**

> Именно эти уроки, извлеченные, например, из аргентинского кризиса, убедили участников немецкого движения «регио» включить ряд принципов в свои восемь условий для получения права на использование знака «регио». По словам инициатора движения Маргрит Кеннеди, для этого должны соблюдаться следующие критерии:

---

### 35. `p1244` — длина озвучки / длина оригинала: 0.89; классы правки: —

**Исходный абзац:**

> The Board decided unanimously to implement the 100- year sub- Sahara project, given that the internal rate of return on this project is clearly superior to the 25- year project. The chairman added that the contribution of this project to overall global climate stability has been an additional incentive for him to vote for this project. The currency of all payments for goods and suppliers is the demurrage charged, similar to the Terra currency. The annual reports to the shareholders are similarly expressed in Terra.

**В озвучку попало:**

> Совет единогласно решил реализовать столетний проект в Сахаре, поскольку внутренняя норма доходности по нему явно выше, чем у двадцатипятилетнего проекта. Председатель добавил, что вклад этого проекта в общую стабильность мирового климата стал для него дополнительным стимулом проголосовать «за». Валютой для всех расчетов с поставщиками товаров и услуг служит валюта с демерреджем, аналогичная «Терре». Годовые отчеты для акционеров также выражаются в «Терре».

---

### 36. `p1246` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Embu, a 23- year- old Kenyan Bantu- speaking woman and mother of one, takes the microphone and beams a broad, proud smile at the assembled group of representatives. They’ve traveled from far and wide across the expansive Nyanza Province, which borders on Lake Victoria, for this important quarterly joint NGO meeting. Delegates from across the culturally diverse region, including members of the Luo, Gusii, and Kuria tribes, sit in excited anticipation to hear the fi nancial reports and updates on their area’s comprehensive network of cooperatives and trade associations. Preliminary accounts and animated gossip, along with obvious evidence of vibrant commerce transacted daily, bode well for good news and a well- deserved celebration later that eve ning.

**В озвучку попало:**

> [excited] Эмбу, двадцатитрехлетняя кенийская женщина из народа банту и мать одного ребенка, берет микрофон и одаривает собравшихся представителей широкой, гордой улыбкой. Они приехали издалека со всей обширной провинции Ньянза, граничащей с озером Виктория, на важное ежеквартальное совместное собрание неправительственных организаций. Делегаты из культурно разнообразного региона, включая представителей племен луо, гусии и куриа, в радостном ожидании готовятся услышать финансовые отчеты и новости о комплексной сети кооперативов и торговых ассоциаций их области. Предварительные данные, оживленные разговоры и очевидные свидетельства активной ежедневной торговли сулят хорошие новости и заслуженный праздник, который состоится позже вечером.

---

### 37. `p1325` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> What is being touted as the Third Industrial Revolution is now well underway. “The old way of making things involved taking lots of parts and screwing or welding them together. Now a product can be designed on a computer and ‘printed’ on a 3D printer, which creates a solid object by building up successive layers of material. The digital design can be tweaked with a few mouse clicks. The 3D printer can run unattended and can make many things which are too complex for a traditional factory to handle. In time, these amazing machines may be able to make almost anything, anywhere— from your garage to an African village.”⁸

**В озвучку попало:**

> То, что называют Третьей промышленной революцией, уже идет полным ходом. Старый способ производства требовал сборки множества деталей с помощью винтов или сварки. Теперь изделие можно спроектировать на компьютере и «напечатать» на 3D-принтере, который создает твердый объект, слой за слоем наращивая материал. Цифровой проект можно подправить парой кликов мыши. 3D-принтер может работать без присмотра и создавать вещи, слишком сложные для традиционного завода. Со временем эти удивительные машины смогут производить почти всё и где угодно — от вашего гаража до африканской деревни.

---

### 38. `p1339` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> “Frankly, it’s not good enough to just simply think outside the box anymore. We need to throw the box away and think in an entirely different way. In order to do that, we need to teach our children *how* to learn by capitalizing on their individual strengths. And each is unique.

**В озвучку попало:**

> «Честно говоря, мыслить нестандартно уже недостаточно. Нам нужно вовсе отбросить рамки и начать думать совершенно иначе. Для этого необходимо научить детей учиться, опираясь на их индивидуальные сильные стороны. А каждый ребенок уникален».

---

### 39. `p1340` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> That way a life of continual learning, adaptation and empowerment is possible. Each person can truly access his or her genius— a compass to follow one’s individual bliss,” comments Kimberly Kassner, author of *You’re a Genius— And I Can Prove It!* Each person, when given the opportunity, becomes a unique and brilliant being.¹⁵

**В озвучку попало:**

> «Так становится возможной жизнь, полная постоянного обучения, адаптации и внутренней силы. Каждый человек может по-настоящему раскрыть свой гений — компас, помогающий следовать своему призванию», — комментирует Кимберли Касснер, автор книги «Ты гений, и я могу это доказать!». Если дать человеку возможность, он становится уникальной и блестящей личностью.

---

### 40. `p1343` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> She explains that contemporary leaders of courage and compassion are operating from a profound space. These leaders are pattern makers, not just problem solvers. They deal with what is not working by creating alternatives. They are able to identify, distinguish, design, and generate responses that integrate the different domains related to the entangled hierarchies of any given situation. They do more than solve complex societal problems at a surface level. They actively address the deeper dimensions of reality. They demonstrate that it is possible to design and implement programs differently: solving problems; synthe-sizing and making sense of the invisible patterns affecting reality, as well as endless incomprehensible bits of information; breaking new ground; and establishing alternatives— ethical and principled action sourcing their inner values and wisdom.

**В озвучку попало:**

> Она объясняет, что современные лидеры, обладающие мужеством и состраданием, действуют из глубокого осознания. Они не просто решают проблемы, они создают новые модели. Они справляются с тем, что не работает, предлагая альтернативы. Такие лидеры способны видеть, различать и создавать решения, которые объединяют разные уровни любой ситуации. Они делают больше, чем просто решают поверхностные социальные проблемы. Они активно работают с глубинными аспектами реальности. Они доказывают, что можно проектировать и внедрять программы иначе: синтезируя невидимые закономерности, пробивая новые пути и создавая этичные альтернативы, основанные на внутренней мудрости.

---

### 41. `p1798` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> A special word of thanks to Ed and Deb Shapiro, Frank Baylin, Kimberly Kassner, Nigel Seale, Aureya Magdalen, Jean Houston, Paul Ray, Jan Coleman, and Sally Dunne- Lee. To Michelle Bishop for her diligent assistance with some of the research. Also, to our agents David Nelson and Neil Gudovitz at Waterside Productions for their consummate support and guidance.

**В озвучку попало:**

> [thoughtful] Особая благодарность Эду и Деб Шапиро, Фрэнку Бейлину, Кимберли Касснер, Найджелу Силу, Орее Магдален, Джин Хьюстон, Полу Рэю, Джен Коулман и Салли Данн-Ли. Спасибо Мишель Бишоп за усердную помощь в проведении исследований. Мы также признательны нашим агентам Дэвиду Нельсону и Нилу Гудовицу из Waterside Productions за их неизменную поддержку и советы.

---

### 42. `p1800` — длина озвучки / длина оригинала: 0.99; классы правки: —

**Исходный абзац:**

> This book is the result of, quite literally, thousands of conversations over time and scores of interviews across the globe during the course of writing this book. Unfortunately, while many discussions didn’t make it into the book, they were seminal in shaping our work. There are too many people to thank here by name for their time, contributions, and generosity of spirit. Know that you are all held in our hearts with deep and abiding gratitude.

**В озвучку попало:**

> Эта книга — результат буквально тысяч разговоров и множества интервью, проведенных по всему миру за время работы над ней. К сожалению, далеко не все обсуждения вошли в текст, но они сыграли ключевую роль в формировании наших идей. Людей, которым мы хотели бы сказать спасибо за их время, вклад и душевную щедрость, слишком много, чтобы перечислить всех поименно. Знайте, что мы храним вас в своих сердцах с глубокой и искренней благодарностью.

---

### 43. `p2236` — длина озвучки / длина оригинала: 1.12; классы правки: —

**Исходный абзац:**

> Bernard has been a star since 1969, when he received an MBA from MIT and *Time* magazine selected him as one of the top-10 graduates of U.S. business schools. His post- graduate thesis, entitled *Financial* *Management of Foreign Exchange,* was published by MIT Press in 1970 and received wide attention in the fi nancial world. In his thesis, he discussed applying nonlinear programming to global currency management for multinational corporations. This was considered the fi rst book to explore the applications of systems theory to international fi - nance. It described how to optimize currency management for corporations working in a large number of countries and currencies, and included the techniques to deal with fl oating exchanges, at the time a rare occurrence limited to some exotic currencies in Latin America. A major U.S. bank negotiated exclusive rights to Bernard’s approach prompting him to start a new career and move to South America. He developed, for the largest mining company in Peru, a new system for worldwide allocation of mining resources, which ended up being used to optimize two- thirds of all foreign exchange earnings of Peru. Subsequently, he wrote the only book (published in 1979) to foretell the Latin American debt crisis that exploded as he predicted in the early 1980s.

**В озвучку попало:**

> Бернар стал известен еще в 1969 году, когда получил степень магистра делового администрирования в Массачусетском технологическом институте, а журнал «Тайм» включил его в десятку лучших выпускников бизнес-школ США. Его диссертация под названием «Финансовое управление иностранной валютой» была опубликована издательством Массачусетского технологического института в 1970 году и привлекла большое внимание в финансовых кругах. В работе он рассматривал применение нелинейного программирования для управления глобальными валютными потоками в транснациональных корпорациях. Это была первая книга, в которой исследовалось применение теории систем к международным финансам. В ней описывалось, как оптимизировать управление валютой для компаний, работающих во многих странах, и предлагались методы работы с плавающими курсами — явлением, которое в то время было редкостью и ограничивалось лишь некоторыми экзотическими валютами Латинской Америки. Крупный американский банк выкупил исключительные права на подход Бернара, что побудило его начать новую карьеру и переехать в Южную Америку. Там, для крупнейшей горнодобывающей компании Перу, он разработал новую систему распределения ресурсов, которая впоследствии использовалась для оптимизации двух третей всех валютных поступлений страны. Позже он написал единственную книгу, опубликованную в 1979 году, в которой предсказал латиноамериканский долговой кризис, разразившийся в начале восьмидесятых, как он и прогнозировал.

---

### 44. `p2237` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> Later, Bernard was widely credited with being one of the principal architects of the euro, the single Eu ro pe an currency. This came about after he accepted a job offer as the head of the Or ga ni za tion and Computer Department at the Central Bank in Belgium. Because Belgium received the chairmanship of the Eu ro pe an Currency Unit (the ECU), his fi rst project at the Bank was the design and implementation of the convergence system, which evolved into the euro in January,

**В озвучку попало:**

> Позже Бернара стали называть одним из главных архитекторов евро, единой европейской валюты. Это произошло после того, как он принял предложение возглавить департамент организации и компьютерных систем в Центральном банке Бельгии. Поскольку Бельгия получила председательство в Европейской валютной единице, ЭКЮ, его первым проектом в банке стала разработка и внедрение системы конвергенции, которая в январе 1999 года эволюционировала в евро.

---

### 45. `p2239` — длина озвучки / длина оригинала: 0.92; классы правки: —

**Исходный абзац:**

> In the mid- 1990s, Bernard changed his focus. He has spent the past two de cades as one of the world’s leading designers and implementers of cooperative currencies. He has consulted with communities, governments, banks, and businesses around the globe. He has written several books on the topic of money, including the classic, *The* *Future of Money,* along with hundreds of articles and interviews. One of Bernard’s current projects in terms of new currencies is the Trade Reference Currency, which is a privately- issued, cooperative, global reference currency that is backed by a noninfl ationary, standardized basket of the dozen most important commodities and ser vices in the global market. It is poised to drastically change barter and counter-trade along with creating stability and predictability in the fi nancial and business sectors by providing a robust standard of value for international trade. Most importantly, it will resolve the current confl ict between short- term fi nancial interest and long- term sustainability thereby providing, for the fi rst time since the gold- standard days, an international standard of value that is infl ation- resistant. This mechanism would work in parallel with national currencies. Currently, Bernard is a Research Fellow at the Center for Sustainable Resources of the University of California at Berkeley. He is also Visiting Professor at the Finance University of Moscow.

**В озвучку попало:**

> В середине девяностых Бернар сменил фокус своей деятельности. Последние два десятилетия он является одним из ведущих мировых разработчиков и внедренцев кооперативных валют. Он консультировал сообщества, правительства, банки и бизнес по всему земному шару. Бернар написал несколько книг о деньгах, включая классическую работу «Будущее денег», а также сотни статей и интервью. Один из его текущих проектов в области новых валют — «Торговая эталонная валюта». Это частная кооперативная глобальная валюта, обеспеченная неинфляционной стандартизированной корзиной из дюжины важнейших товаров и услуг на мировом рынке. Она призвана радикально изменить бартер и встречную торговлю, а также создать стабильность и предсказуемость в финансовом и деловом секторах за счет обеспечения надежного стандарта стоимости для международной торговли. Самое важное: она разрешит текущий конфликт между краткосрочными финансовыми интересами и долгосрочной устойчивостью. Это обеспечит, впервые со времен золотого стандарта, международный стандарт стоимости, устойчивый к инфляции. Данный механизм будет работать параллельно с национальными валютами. В настоящее время Бернар является научным сотрудником Центра устойчивых ресурсов Калифорнийского университета в Беркли, а также приглашенным профессором Финансового университета в Москве.

---

### 46. `p2240` — длина озвучки / длина оригинала: 1.16; классы правки: —

**Исходный абзац:**

> He is a member of the Club of Rome; a Fellow at the World Academy of Arts and Sciences, the World Business Academy, and the Euro pe an Academy of Sciences and Arts; and a founding member of the Global Futures Forum. He currently resides in his native Belgium. He is fl uent in En glish, French, Spanish, German, and Dutch, and reads Latin and Greek.

**В озвучку попало:**

> Он является членом Римского клуба, научным сотрудником Всемирной академии искусств и наук, Всемирной бизнес-академии, Европейской академии наук и искусств, а также одним из основателей Глобального форума будущего. В настоящее время он проживает в своей родной Бельгии. Бернар свободно владеет английским, французским, испанским, немецким и голландским языками, а также читает на латыни и древнегреческом.

---

### 47. `p2242` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> Danu Resources is a for- profi t or ga ni za tion that brings together and aligns donors and projects that focus on environmental and energy initiatives to move the world to greater sustainability while empower-ing people with dignity and the essentials of life. Danu’s unique value is its ability to work from a future reference point that draws out the greatness, and builds upon the strengths, of both the donor and the company or initiative, thus creating a fl ourishing paradigm shift for people and the planet. Where feasible, ventures operate using a multiple-currency ecosystem.

**В озвучку попало:**

> «Дану Ресурсес» — коммерческая организация, которая объединяет доноров и проекты, ориентированные на экологические и энергетические инициативы. Цель компании — сделать мир более устойчивым, обеспечивая при этом людям достойные условия жизни. Уникальность «Дану» заключается в способности работать с точки зрения будущего, раскрывая потенциал и опираясь на сильные стороны как донора, так и компании или инициативы. Это создает процветающий сдвиг парадигмы для людей и планеты. Там, где это возможно, предприятия работают с использованием экосистемы из нескольких валют.

---

### 48. `p2243` — длина озвучки / длина оригинала: 1.00; классы правки: —

**Исходный абзац:**

> She serves on the board of, or is an advisor to, several U.S. and international companies. These fi rms are engaged in innovative solutions in the domains of green energy (the Swedish corporation Mimer Energy and Blue Energy in Canada), decentralized local food production (Perpetua in the United States), and a natural resolution for nuclear and other waste streams, Amo Terra. She is a principal strategist with the launching of the business- to- business currency, the Terra, that is designed to create more stability and predictability in the fi nancial and business sectors by providing a mechanism for contractual, payment, and planning purposes worldwide.

**В озвучку попало:**

> Джеки входит в советы директоров или выступает советником ряда американских и международных компаний. Эти фирмы занимаются инновационными решениями в таких областях, как «зеленая» энергетика — шведская корпорация «Мимер Энерджи» и «Блю Энерджи» в Канаде, децентрализованное местное производство продуктов питания — «Перпетуа» в США, а также естественное решение проблемы ядерных и других отходов — «Амо Терра». Она является главным стратегом запуска межкорпоративной валюты «Терра», которая призвана создать больше стабильности и предсказуемости в финансовом и деловом секторах, предоставляя механизм для контрактных, платежных и плановых целей по всему миру.

---

### 49. `p2245` — длина озвучки / длина оригинала: 1.09; классы правки: —

**Исходный абзац:**

> An award- winning journalist, she started her career in her native Ireland. While still in college, Jacqui reported on a freelance basis on Spain’s transition to democracy in the late 1970s for both the *Irish Times* and RTE (Irish Radio). Later, she joined the *Sunday In-**de pen dent* as a staff reporter and features writer and covered a variety of stories from the po liti cal unrest in Northern Ireland to famine in Ethiopia. For several years, she wrote a monthly column for the *Irish* *Tattler* and codesigned special events for the magazine to encourage women’s entrepreneurship.

**В озвучку попало:**

> Джеки — отмеченный наградами журналист, начавшая свою карьеру на родине, в Ирландии. Еще будучи студенткой, она работала внештатным корреспондентом и освещала переход Испании к демократии в конце семидесятых годов для газеты «Айриш Таймс» и ирландской телерадиокомпании «Ар-Ти-И». Позже она стала штатным репортером и автором статей в газете «Санди Индепендент». Там она писала о самых разных событиях: от политических беспорядков в Северной Ирландии до голода в Эфиопии. Несколько лет она вела ежемесячную колонку в журнале «Айриш Таттлер» и участвовала в разработке специальных мероприятий, призванных поддержать женское предпринимательство.

---

### 50. `p2246` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> In New York, she wrote for *Interview Magazine, Elle,* and the *Daily* *News,* then headed west to San Francisco, where she wrote for *Grass**roots/Dresdner RCM Bank,* compiling investigative reports on companies and industry sector analysis. She produced radio interviews with thought leaders and was an occasional on- air host for *New Dimen**sions Radio,* syndicated to NPR and community radio stations nationally and overseas.

**В озвучку попало:**

> В Нью-Йорке Джеки писала для журналов «Интервью», «Эль» и газеты «Дейли Ньюс». Затем она переехала на запад, в Сан-Франциско, где сотрудничала с компанией «Грассрутс» и банком «Дрезднер Ар-Си-Эм». Там она составляла аналитические отчеты о работе различных компаний и отраслей. Она также готовила радиоинтервью с лидерами мнений и время от времени выступала в качестве ведущей на радиостанции «Нью Дайменшнс», чьи программы транслировались на Национальное общественное радио и другие станции в США и за рубежом.

---

### 51. `p2247` — длина озвучки / длина оригинала: 1.11; классы правки: —

**Исходный абзац:**

> In order to gain experience in how business really works, Jacqui conducted market research for multinational biotech and pharmaceutical companies. She was vice president of a former boutique technology public and investor relations company, ContentOne, which handled media and investor relations for fi rms ranging from start- ups to publicly traded companies.

**В озвучку попало:**

> Чтобы лучше понять, как на самом деле работает бизнес, Джеки проводила маркетинговые исследования для транснациональных биотехнологических и фармацевтических компаний. Она занимала пост вице-президента в компании «Контент-Уан», которая специализировалась на технологическом пиаре и связях с инвесторами. Эта компания работала с самыми разными клиентами: от стартапов до крупных публичных корпораций.

---

### 52. `p2248` — длина озвучки / длина оригинала: 0.98; классы правки: —

**Исходный абзац:**

> Lately, she has worked as a content editor for *Money and* *Sustainability— The Missing Link, A Report from the Club of Rome,* which reveals the hidden dynamics among the conventional money system, climate change, and ecological sustainability. This report was addressed to Finance Watch, an in de pen dent Eu ro pe an public interest association tasked by the Eu ro pe an Union with reporting on the causes of the current banking and fi nancial debacle.

**В озвучку попало:**

> В последнее время она работала редактором контента для доклада Римского клуба «Деньги и устойчивое развитие: недостающее звено». В этом документе раскрываются скрытые взаимосвязи между традиционной денежной системой, изменением климата и экологической устойчивостью. Доклад был подготовлен для организации «Файнэнс Уотч» — независимого европейского объединения, которому Евросоюз поручил изучить причины текущего банковского и финансового кризиса.

---

### 53. `p2251` — длина озвучки / длина оригинала: 1.01; классы правки: —

**Исходный абзац:**

> We believe that to truly create a better world, action is needed at all levels— individual, organizational, and societal. At the individual level, our publications help people align their lives with their values and with their aspirations for a better world. At the organizational level, our publications promote progres-sive leadership and management practices, socially responsible approaches to business, and humane and effective organizations. At the societal level, our publications advance social and economic justice, shared prosperity, sustainability, and new solutions to national and global issues.

**В озвучку попало:**

> Мы верим, что для создания лучшего мира необходимы действия на всех уровнях: индивидуальном, организационном и общественном. На индивидуальном уровне наши книги помогают людям привести свою жизнь в соответствие с их ценностями и стремлениями. На организационном уровне мы продвигаем прогрессивное руководство, социально ответственный подход к бизнесу и создание гуманных, эффективных компаний. На общественном уровне наши публикации способствуют установлению социальной и экономической справедливости, всеобщего процветания и устойчивого развития, а также предлагают новые решения национальных и глобальных проблем.

---

### 54. `p2252` — длина озвучки / длина оригинала: 1.03; классы правки: —

**Исходный абзац:**

> A major theme of our publications is “Opening Up New Space.” Berrett- Koehler titles challenge conventional thinking, introduce new ideas, and foster positive change. Their common quest is changing the underlying beliefs, mindsets, institutions, and structures that keep generating the same cycles of problems, no matter who our leaders are or what improvement programs we adopt.

**В озвучку попало:**

> Одна из главных тем наших публикаций — «Открывая новые горизонты». Книги «Берретт-Кёлер» бросают вызов привычному мышлению, предлагают новые идеи и способствуют позитивным переменам. Наша общая цель — изменить глубинные убеждения, установки и институты, которые раз за разом порождают одни и те же проблемы, независимо от того, кто находится у власти и какие программы улучшений мы внедряем.

---

### 55. `p2253` — длина озвучки / длина оригинала: 0.97; классы правки: —

**Исходный абзац:**

> We strive to practice what we preach—to operate our publishing company in line with the ideas in our books. At the core of our approach is stewardship, which we deﬁ ne as a deep sense of responsibility to administer the company for the beneﬁ t of all of our “stakeholder” groups: authors, customers, employees, investors, service providers, and the communities and environment around us.

**В озвучку попало:**

> Мы стремимся следовать собственным советам и управлять издательством в соответствии с идеями, изложенными в наших книгах. В основе нашего подхода лежит концепция ответственного управления. Мы определяем ее как глубокое чувство ответственности за развитие компании на благо всех заинтересованных сторон: авторов, клиентов, сотрудников, инвесторов, партнеров и общества в целом.

---
## Край 1: максимальное сжатие (20 абзацев)

Самое низкое отношение «длина озвучки / длина оригинала» среди прозы — сюда стекается всё, что модель выбросила или сократила.

### 1. `p1123` — длина озвучки / длина оригинала: 0.69; классы правки: —

**Исходный абзац:**

> “Chinese money, known also as *pis bolong* in Bali, has circulated as a local medium of exchange here for at least the past 1,000 years and only ceased to be used for local purchases in the early 1970s. Up until that time, a Balinese could use uang kepeng in many ways, from buying meat and vegetables in the market or snacks in front of the school, to watching movies with friends at an outdoor theater,” says Stephen DeMeulenaere, found er of the Cooperative Currency Resource Center and a long- term resident of Bali.⁶ According to DeMeulenaere, uang kepeng became the offi cial medium of exchange of the Banjar and could be taxed, spent on public works projects, and circulated as a fully functioning currency. Thus its signifi cance to Balinese society was formalized.⁷

**В озвучку попало:**

> [serious] «Китайские деньги, известные на Бали как пис болонг, были местным средством обмена на протяжении как минимум тысячи лет и вышли из употребления только в начале семидесятых», — говорит Стивен ДеМюленаре, основатель Центра ресурсов кооперативных валют и давний житель Бали. По его словам, уанг кепенг стал официальным средством обмена внутри банджаров: ими платили налоги, финансировали общественные работы и использовали как полноценную валюту. Таким образом, их значение для балийского общества было официально закреплено.

---

### 2. `p0278` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> A year passes and on another market day the stranger with the styl-ish hat returns, and from his vantage point he observes the village below. While sitting under the broad- limbed oak tree, he reaches into his knapsack and pulls out a silver canteen fi lled with a single- malt whis-key, takes a swig, savoring its peaty warmth at the back of his throat, and waits for the village folk to fi le past him with each family’s repayment of the eleventh round.

**В озвучку попало:**

> Прошел год. В очередной базарный день незнакомец в стильной шляпе вернулся. С высоты своего положения он наблюдал за деревней. Сидя под раскидистым дубом, он достал из сумки серебряную фляжку с односолодовым виски, сделал глоток, смакуя его торфяное тепло, и стал ждать, пока сельчане пройдут мимо него, чтобы вернуть одиннадцатый кружок.

---

### 3. `p1019` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> Rui Izumi, an associate professor at the Senshu University School of Economics in Tokyo, points to government support as a major contributor to the growth in cooperative currencies: “The central government and many local governments are supporting local currencies in positive ways. For example, they have given fi nancial support to some organizations, and [both] the Minister of Economy, Trade and Industry and the president of the Bank of Japan have made several encouraging remarks publicly about these systems.”¹² A former minister for economy and industrial policies described government support for complementary currencies in surprising terms: “The use of cooperative currencies can bring an end to the long- lasting defl ation of the Japa nese economy by supplying additional monies of various types at the local level.”¹³

**В озвучку попало:**

> Руи Изуми, доцент Токийского университета Сэнсю, отмечает, что государственная поддержка стала важным фактором роста таких валют. «Центральное правительство и многие местные органы власти активно поддерживают локальные валюты, — говорит он. — Например, они оказывают финансовую помощь некоторым организациям, а министр экономики, торговли и промышленности и президент Банка России публично высказывались в поддержку этих систем». Бывший министр экономики даже заявил, что кооперативные валюты могут помочь положить конец затяжной дефляции в японской экономике, обеспечив приток дополнительных средств на местном уровне.

---

### 4. `p0653` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> “Savings points” are the cooperative currency internally used as the key method by which JAK manages member savings and loans, thus increasing its liquidity. Saving points are awarded for one’s saving efforts. For example, saving one Swedish crown for one month yields one savings point, and one crown borrowed for one month consumes one savings point. Thus savings points are used to ensure the sustainability of the system. Savings points are earned by the member on savings that accumulate prior to exercising the loan option and on savings accumulated during the loan repayment period.

**В озвучку попало:**

> «Сберегательные баллы» — это внутренняя кооперативная валюта. С их помощью JAK управляет вкладами и кредитами, поддерживая ликвидность системы. Баллы начисляются за накопления: например, одна крона, пролежавшая на счету месяц, дает один балл, а одна крона, взятая в кредит на месяц, этот балл «поглощает». Таким образом, система остается сбалансированной. Участники зарабатывают баллы как до получения кредита, так и во время его погашения.

---

### 5. `p0381` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> They are designed to facilitate transactions (i.e., as a medium of exchange), used both as units of account and as savings (i.e., as temporary stores of value), and are particularly well adapted for business and industrial applications and settings. As already seen, the use of interest, especially compound interest, has very precise outcomes that do not necessarily benefi t society at large. However, money can also be archi-tected in other ways.

**В озвучку попало:**

> Они спроектированы для облегчения транзакций, служат расчетными единицами и средством накопления, а также отлично адаптированы для бизнеса и промышленности. Как мы видели, использование процентов, особенно сложных, приводит к результатам, которые не всегда идут на пользу обществу в целом. Тем не менее, деньги можно выстраивать и иначе.

---

### 6. `p0230` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> Smith’s inquiries were set against the background of the development of our modern- day banking system with the formation of central banks in Sweden and En gland, while the earlier discoveries of Newton and his contemporaries ignited the imaginations of the ruling and educated upper class. The Age of Enlightenment’s zeitgeist was one of cool- headed rationalism and empiricism, which stood in stark contrast to the era of dark religious superstition that had preceded it. For example, Newtonian physics made it possible to calculate the distance and velocity of a cannonball being shot out of a cannon and to predict the movement of the heavenly bodies in interstellar space, both with precise meticulous-ness, theoretically down to a fraction of an inch. Consequently, everything had to be mea sured and codifi ed. If it couldn’t be *sensed,* in other words quantifi ed, then it was deemed *nonsense* and duly dismissed.

**В озвучку попало:**

> Исследования Смита проходили на фоне формирования современной банковской системы и создания центральных банков в Швеции и Англии. В то же время открытия Ньютона и его современников будоражили воображение правящей элиты. Дух эпохи Просвещения — холодный рационализм и эмпиризм — резко контрастировал с темными временами религиозных суеверий. Например, ньютоновская физика позволяла с математической точностью рассчитать дистанцию и скорость полета пушечного ядра или предсказать движение небесных тел. В результате все вокруг должно было быть измерено и систематизировано. Если что-то нельзя было «почувствовать» — то есть количественно измерить, — это объявлялось бессмыслицей и отбрасывалось.

---

### 7. `p0425` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> Barter is the direct exchange of goods or ser vices unmediated by any type of money. For example, a boy agreed to cut his neighbor’s lawn. The neighbor had two tickets to an upcoming Van Halen reunion concert he couldn’t use; he also had an earlier version of an iPod lying around. But the tickets were not of interest to the boy, and the used iPod, the neighbor realized, was far more valuable than the boy’s time and effort warranted. Bartering requires matching the needs and resources of both parties involved in the transaction, yet it’s not always possible to line up an equitable exchange of goods or ser vices. So the neighbor may decide to pay the boy in cash rather than bartering, and put the items up for auction on eBay.

**В озвучку попало:**

> Бартер — это прямой обмен товарами или услугами без участия каких-либо денег. Например, мальчик договорился подстричь газон соседу. У соседа были два билета на концерт группы Ван Хален, которыми он не мог воспользоваться, и старый плеер Айпод. Но билеты мальчику были не нужны, а подержанный плеер, как понял сосед, стоил гораздо больше, чем время и усилия мальчика. Бартер требует совпадения потребностей и ресурсов обеих сторон, что не всегда возможно. Поэтому сосед может решить заплатить мальчику наличными, а вещи выставить на аукцион в интернете.

---

### 8. `p0226` — длина озвучки / длина оригинала: 0.75; классы правки: —

**Исходный абзац:**

> No matter whether it’s along the corridors of power, in the boardrooms of major corporations, or sitting at the kitchen table working out a family’s monthly bud get, government policy relating to all fi nancial matters and monetary procedures is determined by the self- styled *science* of economics.

**В озвучку попало:**

> Будь то коридоры власти, залы заседаний крупных корпораций или кухонный стол, где семья планирует свой бюджет, — государственная политика во всех финансовых и денежных вопросах определяется так называемой экономической наукой.

---

### 9. `p0583` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> Additionally, full paychecks for the entire amount of one’s wages, especially from trusted employers, could be readily used as an instrument of payment for goods and ser vices. This is reminiscent of the story in the opening of Chapter 2, where the tourist comes to the inn and puts a $100 bill on the counter, and while he’s investigating the ac-commodations, several townspeople circulate the $100 to pay off their debts. But in this case, the pub own er or local merchant could validate the creditworthiness of the check.

**В озвучку попало:**

> Кроме того, полные зарплатные чеки от надежных работодателей легко использовались для оплаты товаров и услуг. Это напоминает историю из второй главы, где турист оставляет стодолларовую купюру на стойке гостиницы, и пока он осматривает номер, горожане передают эту купюру друг другу, погашая свои долги. В данном случае владелец паба или местный торговец мог сам проверить платежеспособность чека.

---

### 10. `p1343` — длина озвучки / длина оригинала: 0.76; классы правки: —

**Исходный абзац:**

> She explains that contemporary leaders of courage and compassion are operating from a profound space. These leaders are pattern makers, not just problem solvers. They deal with what is not working by creating alternatives. They are able to identify, distinguish, design, and generate responses that integrate the different domains related to the entangled hierarchies of any given situation. They do more than solve complex societal problems at a surface level. They actively address the deeper dimensions of reality. They demonstrate that it is possible to design and implement programs differently: solving problems; synthe-sizing and making sense of the invisible patterns affecting reality, as well as endless incomprehensible bits of information; breaking new ground; and establishing alternatives— ethical and principled action sourcing their inner values and wisdom.

**В озвучку попало:**

> Она объясняет, что современные лидеры, обладающие мужеством и состраданием, действуют из глубокого осознания. Они не просто решают проблемы, они создают новые модели. Они справляются с тем, что не работает, предлагая альтернативы. Такие лидеры способны видеть, различать и создавать решения, которые объединяют разные уровни любой ситуации. Они делают больше, чем просто решают поверхностные социальные проблемы. Они активно работают с глубинными аспектами реальности. Они доказывают, что можно проектировать и внедрять программы иначе: синтезируя невидимые закономерности, пробивая новые пути и создавая этичные альтернативы, основанные на внутренней мудрости.

---

### 11. `p0715` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Furthermore, the technology is a proven one that doesn’t require any new legislation or government approvals, and the necessary software is available in open source. Additionally, the most effective way for governments at all levels to encourage the implementation of the C3 strategy is for them to accept payment of taxes and fees in the C3 currency. This encourages everybody to accept the C3 currency in payment and provides additional income to the government from transactions that otherwise wouldn’t take place. Furthermore, that additional income automatically becomes available in conventional national currency at the maturity of the original invoice. At the end of the pro cess, the government has only to deal with conventional national money, thereby not upsetting any existing procurement policies.

**В озвучку попало:**

> Технология уже проверена на практике. Она не требует принятия новых законов или одобрения правительства, а необходимое программное обеспечение распространяется с открытым исходным кодом. Кроме того, самый эффективный способ для властей поддержать внедрение C3 — это начать принимать налоги и сборы в этой валюте. Это стимулирует всех участников принимать C3 к оплате и приносит государству дополнительный доход от сделок, которые в ином случае могли бы не состояться. В конце процесса этот доход автоматически конвертируется в обычную национальную валюту, поэтому государству не приходится менять существующие правила закупок.

---

### 12. `p0584` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> Economics Professor Antoin E. Murphy of Trinity College Dublin reports, “The nature of the economy greatly facilitated the emergence of this new system. The Republic of Ireland had a population of only three million inhabitants. The small size of the population meant that there was a high degree of personal contact amongst members of the community. Where information was lacking at the personal level, a substitute collective information existed in the form of retail shops numbering around 12,000 and that well- known Irish institution, the public house, 11,000 of which exist in the Republic [which yielded] a pub to population ratio of 1:190.”⁶

**В озвучку попало:**

> Профессор экономики Антуан Мерфи из Тринити-колледжа в Дублине отмечает: «Природа экономики того времени способствовала появлению этой системы. В Республике Ирландия проживало всего три миллиона человек. Из-за малого населения люди были тесно связаны друг с другом. Там, где не хватало личной информации, на помощь приходили двенадцать тысяч розничных магазинов и знаменитые ирландские пабы. Их в республике насчитывалось одиннадцать тысяч, что давало соотношение одного паба на сто девяносто человек».

---

### 13. `p0595` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Here’s an example in very simple terms: A baker who needed fl our and eggs incurs a debit from a local farmer in exchange for these goods; with that credit, the farmer gets hardware from the local supplier for the barn he is repairing, and the baker supplies the local car repair shop own er with baked goods for his family, bringing the baker’s balance back to zero. All these transactions take place without being medi-ated by conventional money.

**В озвучку попало:**

> [curious] Вот простой пример. Пекарь, которому нужны мука и яйца, получает их у местного фермера в долг. Фермер, используя этот кредит, покупает инструменты у местного поставщика для ремонта сарая. А пекарь в свою очередь поставляет выпечку владельцу автомастерской, тем самым обнуляя свой баланс. Все эти сделки проходят без участия обычных денег.

---

### 14. `p1347` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Scholar, phi los o pher, and researcher in human capacities, Jean Houston, muses, “The new myth would be a myth of exchange. It’s not simply the world monetary system with its multitrillion- dollar casino that runs around every day, which is the current mythos. The core of the new mythos is the world Mind— a world Spirit. This is where the ecol ogy of the world spirit can be only partially fi nancial. It has to be the spirit, the culture, the dance, the music, the generosity of people toward each other, and I think this is happening because of the rise of the women to full partnership with men in the whole domain of human affairs with a new emphasis on pro cess rather than on product, on making things grow, cohere, relate. This is already the biggest shift, I think, in human sensibility.”

**В озвучку попало:**

> Ученый, философ и исследователь человеческих возможностей Джин Хьюстон размышляет: «Новым мифом станет миф об обмене. Нынешний миф — это мировая денежная система с ее многотриллионным казино. Ядром нового мифа станет мировой Разум, мировой Дух. Экология этого духа может быть лишь частично финансовой. Она должна включать в себя культуру, танец, музыку и взаимную щедрость. Я думаю, это происходит благодаря тому, что женщины становятся полноправными партнерами мужчин во всех сферах жизни. Это меняет акцент с продукта на процесс, на созидание и взаимосвязи. Думаю, это самый значительный сдвиг в человеческом сознании».

---

### 15. `p1118` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> John Stephen Lansing, a professor at the Santa Fe Institute whose research explores the ecol ogy, common property, and social theories of Bali, as well as integrative modeling of environmental changes, explains that an agrarian system of rice cultivation fl ourished there for almost 1,000 years.¹ Then, in the 1970s, the World Bank insisted, as part of its fi nancial aid package, that the “unsophisticated traditional methods” be replaced with modern techniques and know- how, coupled with the use of chemical fertilizers. The well- documented experiment was a disaster, causing crop failures and massive ecological issues, such as the depletion of large swaths of native coral reefs. It was then decided that the customary agricultural practices could be reintroduced.

**В озвучку попало:**

> Джон Стивен Лэнсинг, профессор Института Санта-Фе, исследующий экологию, общественную собственность и социальные теории Бали, отмечает, что аграрная система выращивания риса процветала там почти тысячу лет. Однако в семидесятые годы двадцатого века Всемирный банк в рамках финансовой помощи настоял на замене «несовершенных традиционных методов» современными технологиями и химическими удобрениями. Этот эксперимент закончился катастрофой: урожаи погибли, а экология острова, включая коралловые рифы, серьезно пострадала. В итоге было решено вернуться к привычным методам ведения сельского хозяйства.

---

### 16. `p1326` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> With the press of a button, the replacement for a broken vacuum cleaner part, for example, will be instantaneous and localized, if not at home, then at the neighborhood print shop. In such a scenario, industrial hubs with their networks of roads and railways that support the distribution of goods will become a thing of the past.

**В озвучку попало:**

> Нажатием кнопки можно будет мгновенно получить деталь для сломанного пылесоса прямо у себя дома или в ближайшей мастерской печати. В таком сценарии промышленные узлы с их сетями дорог и железных дорог, поддерживающими распределение товаров, уйдут в прошлое.

---

### 17. `p0628` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> “The pro cess for getting a loan is very simple,” added Asier Ansorena, Asesor Nacional de Crédito do Instituto Palmas.¹⁹ “For a business, there is no need for a business plan. There’s simply a meeting with a bank offi cer to discuss the idea for the business, and this is followed up by fi nding out about the person’s reputation for reliability in his or her neighborhood. Thereby an assessment is made of the individual’s trustworthiness to repay the loan. The pro cess is much easier still with consumption loans. Someone in need of some short- term money to put food on the table for their family can make their case and walk out of the bank with the money.”

**В озвучку попало:**

> [thoughtful] «Процесс получения кредита очень прост, — добавляет Асьер Ансорена, национальный кредитный консультант института «Palmas». — Бизнесу не нужно составлять бизнес-план. Достаточно встретиться с сотрудником банка, чтобы обсудить идею, а затем банк наводит справки о репутации человека в его районе. Так оценивается надежность заемщика. С потребительскими кредитами всё еще проще. Человеку, которому срочно нужны деньги на еду для семьи, достаточно объяснить ситуацию, и он может сразу уйти из банка с деньгами».

---

### 18. `p0605` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Stodder added, “So when conventional banks are cutting their credit because there’s a big lack of fi nancial confi dence, and banks are essentially closing their doors to small creditors, there’s no question that historically these periods are those in which cooperative currencies spring up. It happened during the Great Depression, and it’s happened again during the current world downturn.”

**В озвучку попало:**

> [curious] Стоддер добавил: «Когда обычные банки сокращают кредитование из-за острого дефицита финансового доверия и фактически закрывают двери для малых заемщиков, кооперативные валюты неизбежно выходят на первый план. Так было во время Великой депрессии, и это повторилось во время нынешнего мирового спада».

---

### 19. `p0937` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> Rather than leaving it derelict, the land was divided into plots mea-sur ing four square meters each, and these plots became available to rent on an annual basis, at the cost of 150 *torekes,* a newly introduced local cooperative currency. Torekes are available only in paper form for this pi lot project, on the request of the participants themselves. One of the reasons is simplicity.

**В озвучку попало:**

> Вместо того чтобы оставлять землю пустовать, её разделили на участки по четыре квадратных метра. Их можно было арендовать на год за сто пятьдесят торекесов — это новая местная кооперативная валюта. Для пилотного проекта участники сами попросили использовать бумажные купюры, в первую очередь ради простоты.

---

### 20. `p0640` — длина озвучки / длина оригинала: 0.79; классы правки: —

**Исходный абзац:**

> From 2002 until 2009, Aurineide worked in her own store, which she was able to build thanks to the support she received from the bank. Five years ago, she embarked on an even more ambitious enterprise; she opened, together with her husband, a DYI building construction ware house. For two years, they had to manage both businesses until they could successfully transition to the construction business.

**В озвучку попало:**

> С 2002 по 2009 год Ауринейди работала в своём магазине, который смогла построить благодаря поддержке банка. Пять лет назад она решилась на более амбициозный проект: вместе с мужем открыла строительный магазин. Два года им приходилось управлять обоими делами, пока они не смогли полностью перейти в строительный бизнес.

---
## Край 2: максимальное раздувание (10 абзацев)

Самое высокое отношение длин — сюда стекается разбиение на короткие фразы и добавленные пояснения.

### 1. `p1009` — длина озвучки / длина оригинала: 1.83; классы правки: —

**Исходный абзац:**

> He explains that by getting involved in community projects such as garbage collection and a variety of renovation projects, people can earn a local currency that, in turn, is good for Internet access. As a *Time* magazine feature noted: “One of the surest signs that you’re in a

**В озвучку попало:**

> Он объясняет, что, участвуя в общественных проектах, таких как сбор мусора или ремонтные работы, люди могут заработать местную валюту, которую затем можно обменять на доступ в интернет. Как отмечал журнал «Тайм»: «Один из самых верных признаков того, что вы находитесь в развивающейся стране, — это мусор у вас под ногами. И это связано не столько с вредными привычками, сколько с тем, что организация вывоза и утилизации отходов для бедного правительства является дорогостоящей задачей с низким приоритетом».

---

### 2. `p0979` — длина озвучки / длина оригинала: 1.62; классы правки: —

**Исходный абзац:**

> Activities are centered around the town’s 100- year- old Miners’ Welfare Hall. The local activities are run by a community nonprofi t or ga-ni za tion, Creation Development Trust, which employs two workers to oversee the TimeBanking. For each hour of ser vice given to the community, a credit of one hour is exchanged. In the fi rst year, 150 people took part; there are now over 1,000 members and 30 groups; 15 new social enterprises have been established, and new learning opportuni-

**В озвучку попало:**

> Вся деятельность сосредоточена вокруг столетнего Зала шахтеров. Местными проектами управляет некоммерческая организация «Криэйшн Девелопмент Траст», которая нанимает двух сотрудников для контроля за тайм-банкингом. За каждый час работы на благо общества начисляется один кредит. В первый год участвовало сто пятьдесят человек, сейчас их уже более тысячи, а также тридцать групп. Создано пятнадцать новых социальных предприятий и открыты новые возможности для обучения. Участники вносят шестьдесят тысяч часов труда в год на нужды своего сообщества. Зал посещают в среднем шестьсот человек в неделю. Вход на мероприятия оплачивается либо временными кредитами, либо обычными деньгами: двухчасовой вечер бинго или киносеанс стоят два кредита, а трехчасовое культурное представление — три.

---

### 3. `p0473` — длина озвучки / длина оригинала: 1.28; классы правки: —

**Исходный абзац:**

> The most frequent cooperative currency system in the world today is LETS, an acronym for “Local Exchange Trading System.” It was invented in the formerly eco nom ical ly stable middle- class town of Court-ney in the Comotz Valley near Vancouver, Canada, in the early 1980s when it was enduring a 40 percent local unemployment rate.

**В озвучку попало:**

> [serious] Самая распространенная в мире система кооперативных валют сегодня — это LETS, что расшифровывается как «Локальная торговая обменная система». Она была придумана в начале восьмидесятых годов в канадском городке Кортни, расположенном в долине Комокс недалеко от Ванкувера. В то время город, который раньше считался экономически стабильным местом для среднего класса, столкнулся с сорокапроцентным уровнем безработицы.

---

### 4. `p0299` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> Debt- based money requires endless growth because borrowers must fi nd additional money to pay back the interest on their debt. For the better- rated debtors (e.g., in normal times, government debt), the interest is simply covered through additional debt, resulting in *compound* *interest:* paying interest on interest. Compound interest implies exponential growth in the long run, something mathematically impossible in a *fi nite* world.

**В озвучку попало:**

> [serious] Денежная система, основанная на долге, требует бесконечного экономического роста. Заемщикам постоянно нужно находить дополнительные средства, чтобы выплачивать проценты по своим обязательствам. Для надежных должников, например, государств в стабильные времена, проценты зачастую просто покрываются за счет новых займов. Так возникает сложный процент: выплата процентов на уже начисленные проценты. В долгосрочной перспективе сложный процент ведет к экспоненциальному росту, что математически невозможно в условиях ограниченного мира.

---

### 5. `p0701` — длина озвучки / длина оригинала: 1.23; классы правки: —

**Исходный абзац:**

> If this prospect isn’t tough enough, Silicon Valley entrepreneur Martin Ford writes about how automation eventually will eliminate most jobs.² Jeremy Rifkin makes a similar case in his insightful book, *The End of* *Work*. MIT economist David Autor predicts that automation will eliminate middle- class jobs, and shows that the trend of demand for mainly high- and low- wage extremes will continue for the foreseeable future.

**В озвучку попало:**

> Если эта перспектива кажется недостаточно суровой, предприниматель из Кремниевой долины Мартин Форд пишет о том, как автоматизация со временем уничтожит большинство профессий. Джереми Рифкин приводит аналогичные доводы в своей глубокой книге «Конец работы». Экономист из Массачусетского технологического института Дэвид Отор предсказывает, что автоматизация вытеснит рабочие места для среднего класса, и показывает, что тенденция к спросу преимущественно на высоко- и низкооплачиваемый труд сохранится в обозримом будущем.

---

### 6. `p0555` — длина озвучки / длина оригинала: 1.22; классы правки: —

**Исходный абзац:**

> One of the strongest objections to issuing currency is that it could create uncontrollable infl ation. Infl ation is commonly defi ned by its outcome— higher prices— rather than its cause, which is simply too much money in circulation chasing too few goods and ser vices.

**В озвучку попало:**

> [serious] Один из главных аргументов против выпуска местных валют заключается в том, что это якобы может вызвать неконтролируемую инфляцию. Однако инфляцию чаще определяют по её последствиям — росту цен, — а не по причине. А причина проста: слишком большое количество денег в обращении при недостаточном количестве товаров и услуг.

---

### 7. `p0519` — длина озвучки / длина оригинала: 1.21; классы правки: —

**Исходный абзац:**

> TimeBanking to create a new form of extended family. It is too early to project cost savings. But a recent study reveals that, as home-based care gets cut by state governments, hospital costs are likely to rise as people put off preventive care or end up rehospitalized due to the lack of transitional care.

**В озвучку попало:**

> [thoughtful] Тайм-банкинг позволяет создать новую форму расширенной семьи. Пока рано говорить о конкретной экономии средств, но недавнее исследование показывает: когда государственные органы сокращают расходы на уход на дому, затраты больниц неизбежно растут. Люди откладывают профилактику или попадают в стационар повторно из-за отсутствия должного ухода после выписки.

---

### 8. `p1093` — длина озвучки / длина оригинала: 1.20; классы правки: year_spelled_out_for_tts_not_a_defect

**Исходный абзац:**

> For example, in 2002, outside one of the big fairs, a couple of men were selling papelitos at a huge discount; you could buy $50 worth of creditos for $1 of offi cial money. They were denounced, and a sympa-thetic judge ordered their arrest but had to release them the next day because counterfeit laws only protect legal tender. Furthermore, they were both employees of one of the large banks that had color copiers to make papelitos at will. To me it was clear that the bank, after reopen-ing, counterfeited the people’s money as a way to destroy their competition and regain their monopoly on issuing money,” adds Sergio Lub.

**В озвучку попало:**

> [sarcastic] «Например, в две тысячи втором году возле одной из крупных ярмарок пара мужчин продавала "папелитос" с огромной скидкой. Можно было купить кредитов на пятьдесят долларов всего за один доллар официальной валюты. Их разоблачили, и сочувствующий судья распорядился об аресте, но на следующий день был вынужден отпустить их, поскольку законы о фальшивомонетничестве защищают только законные платежные средства. Более того, оба они были сотрудниками одного из крупных банков, у которого были цветные копировальные аппараты, чтобы печатать "папелитос" сколько угодно. Для меня было очевидно, что банк после возобновления работы подделывал народные деньги, чтобы уничтожить конкурентов и вернуть себе монополию на эмиссию», — добавляет Серхио Луб.

---

### 9. `p1179` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> This phrase is still used today as a way of saying that money is unaffected by its source or its users.²³ What Jonker invented, by contrast, is a system of money that tracks all its users. The currency’s originator and its users leave an indelible imprint so that subsequent users can express their opinion. It is now possible to have “smelly money,” as a previous user’s reputation may stink!

**В озвучку попало:**

> Эта фраза до сих пор используется, чтобы подчеркнуть: деньги не зависят от их происхождения или тех, кто ими пользовался. Система же, которую предложил Йонкер, напротив, отслеживает всех участников оборота. Создатель валюты и её пользователи оставляют в ней неизгладимый след, позволяя последующим владельцам составить мнение о предыдущих. Теперь вполне можно столкнуться с «дурно пахнущими деньгами», если репутация того, кто ими расплатился, оставляет желать лучшего.

---

### 10. `p0615` — длина озвучки / длина оригинала: 1.19; классы правки: —

**Исходный абзац:**

> “Someone at the local meeting of folks from the neighborhood raised the key question that turned everything on its head. That provocative question was ‘Why are we poor?’ And the response would be that we’re poor because we have no money! But the answer may appear obvious, though that it can’t be true. It has to be something else. So people in the community started doing research and mapped out the consumption patterns of the population of the area. They fi gured out that approximately 1.3 million Brazilian reals ($662,570) at that time circulated within the community. So it’s not a lot of money, but it’s defi nitely some money. The problem was that 80 percent of that currency was quickly leaving the local economy. We’re poor because we lose what we have, and additionally we lose what little savings we have. So neighborhoods are not poor; they become poor. And that realization

**В озвучку попало:**

> Кто-то на местном собрании задал ключевой вопрос, который перевернул всё с ног на голову. Этот провокационный вопрос звучал так: «Почему мы бедные?» Ответ был очевиден: «Мы бедные, потому что у нас нет денег». Но, как оказалось, это было не совсем так. Причина крылась в чем-то другом. Жители района начали проводить исследование и проанализировали структуру потребления местного населения. Они выяснили, что в то время внутри сообщества циркулировало около одного миллиона трехсот тысяч бразильских реалов, что составляло примерно шестьсот шестьдесят две тысячи пятьсот семьдесят долларов. Сумма небольшая, но деньги всё же были. Проблема заключалась в том, что восемьдесят процентов этой валюты стремительно покидали местную экономику. Мы бедные не потому, что у нас ничего нет, а потому, что мы теряем то, что имеем, и лишаемся даже тех скудных сбережений, которые удается накопить. Районы не рождаются бедными, они становятся такими. Это осознание стало искрой, из которой вырос банк «Пальмас», — вспоминает Сегундо, бывший семинарист, ставший банкиром.

---
## Край 3: самые буквальные (10 абзацев)

Максимальное посимвольное совпадение с оригиналом среди прозы, дошедшей до артефакта.

### 1. `p1146` — совпадение символов с оригиналом: 24%; классы правки: —

**Исходный абзац:**

> Dee Hock is the found er and a former CEO of the VISA credit card association. Back in 1968, he convinced Bank of America to give up own ership and control of their BankAmericard credit card licensing program. The new entity was a nonstock membership corporation owned by its member banks. In 1976, its name changed to VISA. This new structure he calls a *chaord*, a word that comprises both the terms *chaos* and *order*.

**В озвучку попало:**

> Ди Хок — основатель и бывший генеральный директор ассоциации кредитных карт VISA. Еще в 1968 году он убедил Bank of America отказаться от владения и контроля над программой лицензирования кредитных карт BankAmericard. Новая структура стала неакционерной корпорацией, принадлежащей банкам-членам. В 1976 году она была переименована в VISA. Эту новую структуру он называет «хаорд» — слово, объединяющее понятия хаоса и порядка.

---

### 2. `p1798` — совпадение символов с оригиналом: 23%; классы правки: —

**Исходный абзац:**

> A special word of thanks to Ed and Deb Shapiro, Frank Baylin, Kimberly Kassner, Nigel Seale, Aureya Magdalen, Jean Houston, Paul Ray, Jan Coleman, and Sally Dunne- Lee. To Michelle Bishop for her diligent assistance with some of the research. Also, to our agents David Nelson and Neil Gudovitz at Waterside Productions for their consummate support and guidance.

**В озвучку попало:**

> [thoughtful] Особая благодарность Эду и Деб Шапиро, Фрэнку Бейлину, Кимберли Касснер, Найджелу Силу, Орее Магдален, Джин Хьюстон, Полу Рэю, Джен Коулман и Салли Данн-Ли. Спасибо Мишель Бишоп за усердную помощь в проведении исследований. Мы также признательны нашим агентам Дэвиду Нельсону и Нилу Гудовицу из Waterside Productions за их неизменную поддержку и советы.

---

### 3. `p0004` — совпадение символов с оригиналом: 22%; классы правки: truncated_sentence

**Исходный абзац:**

> “*Rethinking Money* does a brilliant job of eradicating the concepts and stories that our economists and other professionals in the ﬁ eld hold dear. The authors write that ‘money is our last taboo,’ but they don’t recommend abolishing the ﬁ at zeitgeist. Rather, they wisely call on the various new currencies and other monetary innovations to complement the existing system.” —Nigel Seale, former worldwide Chairman, Earth Day International, and founder of Earth Day Canada

**В озвучку попало:**

> «Книга "Переосмысление денег" блестяще разрушает концепции и мифы, которыми дорожат наши экономисты и другие профессионалы в этой области. Авторы пишут, что "деньги — наше последнее табу", но они не призывают к отмене нынешней системы. Напротив, они мудро предлагают использовать новые валюты и другие финансовые инновации как дополнение к существующему порядку». — Найджел Сил, бывший председатель Earth Day International и основатель Earth Day Canada

---

### 4. `p0922` — совпадение символов с оригиналом: 19%; классы правки: —

**Исходный абзац:**

> Thomas Mayer, former chief economist for Deutsche Bank, made in July 2012 a proposal for Greece that is surprisingly radical for his background. It acknowledges that the great majority of Greeks don’t want to leave the euro and that they don’t agree with the extreme austerity program imposed in Greece.

**В озвучку попало:**

> Томас Майер, бывший главный экономист Deutsche Bank, в июле 2012 года выступил с предложением для Греции, которое выглядит удивительно радикальным для человека его уровня. Он признает, что подавляющее большинство греков не хотят отказываться от евро и не согласны с жесткой программой экономии, навязанной стране.

---

### 5. `p0631` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> In 2006, Banco Pop u lar do Brazil, the largest public bank in the country, became a partner of the Brazilian Network of Community Development Banks (CDB), a guarantor of credit lines based on the criteria from PMNPO (National Program of Oriented Productive Microcredit). The CDB estimates that this microloan program had an impact on the lives of more than 200,000 people. There are currently 78 community banks.

**В озвучку попало:**

> В 2006 году «Banco Popular do Brazil», крупнейший государственный банк страны, стал партнером Бразильской сети общественных банков развития. Он выступил гарантом кредитных линий, основанных на критериях Национальной программы ориентированного продуктивного микрокредитования. По оценкам сети, эта программа микрокредитования повлияла на жизнь более двухсот тысяч человек. В настоящее время в стране работает семьдесят восемь общественных банков.

---

### 6. `p0483` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> The LETS system is now operating in many different parts of the world. Given the highly decentralized nature of the transactions, nobody has been able to tally an accurate number of exchanges, but its spread around the globe testifi es to its success. A partial list of nations in which LETS currently operates includes Argentina, Austria, Belgium, Brazil, Canada, Chile, Colombia, El Salvador, Finland, France, Germany, Hungary, India, Indonesia, Ireland, Israel, Japan, New Zealand, Nigeria, Norway, Poland, South Africa, Switzerland, Thailand, and the United States.

**В озвучку попало:**

> Сегодня система LETS работает во многих частях света. Учитывая крайне децентрализованный характер сделок, никто не смог подсчитать точное количество обменов, но распространение системы по всему миру говорит само за себя. В список стран, где сейчас действует LETS, входят Аргентина, Австрия, Бельгия, Бразилия, Канада, Чили, Колумбия, Сальвадор, Финляндия, Франция, Германия, Венгрия, Индия, Индонезия, Ирландия, Израиль, Япония, Новая Зеландия, Нигерия, Норвегия, Польша, Южная Африка, Швейцария, Таиланд и Соединенные Штаты.

---

### 7. `p0901` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> In the case of Curitiba, the results of using a cooperative currency in purely economic terms are worth noting. From 1975 to 1995, the GDP of the city increased by 75 percent more than the rest of the state of Paraná and by 48 percent more than Brazil’s as a whole. The average Curitibano earned more than three times the country’s minimum wage. If nontraditional monetary gains, such as the exchange of garbage for provisions, are taken into consideration, the real total income for residents was at least 30 percent higher still. The results in human terms— in the renewal of dignity and hope for a better future— are incalculable.⁴

**В озвучку попало:**

> [serious] В случае с Куритибой результаты использования кооперативной валюты в сугубо экономических показателях весьма примечательны. С 1975 по 1995 год валовой внутренний продукт города вырос на 75 процентов больше, чем в остальной части штата Парана, и на 48 процентов больше, чем в целом по Бразилии. Средний житель Куритибы зарабатывал более чем в три раза больше минимальной заработной платы по стране. Если учесть нетрадиционные денежные доходы, например, обмен мусора на продукты, то реальный совокупный доход жителей был еще как минимум на 30 процентов выше. А результаты в человеческом измерении — в восстановлении достоинства и надежды на лучшее будущее — просто невозможно переоценить.

---

### 8. `p0666` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> There has been a solid push in recent years to reach out to other countries internationally. According to Miguel Ganzo, “There are projects underway to establish the JAK model in Germany, Spain, Italy, and Finland. The JAK bank in Denmark was established in 1931 and is totally in de pen dent from us. It started off strongly, then went through a period of decline, and is now on the rise again. There is also interest from Arab countries because our model respects traditional Shari’a principles.”

**В озвучку попало:**

> В последние годы банк активно расширяет свое присутствие на международной арене. По словам Мигеля Ганзо, сейчас ведутся проекты по внедрению модели JAK в Германии, Испании, Италии и Финляндии. Банк JAK в Дании был основан в 1931 году и полностью независим от нас. Он начал свою работу успешно, затем пережил период спада, а сейчас снова находится на подъеме. Также интерес проявляют арабские страны, поскольку наша модель соответствует традиционным принципам шариата.

---

### 9. `p0597` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> Although the value of the WIR is pegged to the Swiss franc (1 WIR = 1 Swiss franc), all debts in WIR have to be settled in WIR. There is no convertibility into national currency. Participants can also borrow— that is, secure lines of credit from the cooperative— in WIR currency at low interest rates ranging from 1 to 1.5 percent. All such loans need to be backed by inventory or other assets.

**В озвучку попало:**

> Хотя курс WIR привязан к швейцарскому франку — один к одному, — все долги в этой валюте должны погашаться только в WIR. Конвертация в национальную валюту не предусмотрена. Участники также могут брать кредиты в WIR через кооператив под низкий процент — от одного до полутора процентов годовых. Все такие займы должны быть обеспечены товарными запасами или другими активами.

---

### 10. `p0682` — совпадение символов с оригиналом: 18%; классы правки: —

**Исходный абзац:**

> At present, there are technology silos that hamper the fl uid and seamless movement of money within the marketplace. Mark Fischer, found er of Inspire Commerce and a recognized e-commerce expert, comments, “In closed networks, users are captured in a specifi c channel.

**В озвучку попало:**

> Сейчас существуют технологические «изоляторы», которые мешают свободному и беспрепятственному движению денег на рынке. Марк Фишер, основатель компании Inspire Commerce и признанный эксперт в области электронной коммерции, отмечает: «В закрытых сетях пользователи оказываются заперты в рамках конкретного канала».

---
## Абзацы, оставшиеся в озвучке на английском (1)

Это то, что слушатель услышит по-английски посреди русской аудиокниги. Цитируется сам артефакт `.tts.txt`.

### 1. `narration#1979` — длина озвучки / длина оригинала: 1.00; классы правки: not_translated

**Исходный абзац:**

> Overcrowding, 164 currency creation, 24, 27– 28; as Overdraft, 39 medium of exchange, 201; of money type, 63; privatization and, 20– 21; Panda, 32– 33 state- owned, 128

**В озвучку попало:**

> Overcrowding, 164 currency creation, 24, 27– 28; as Overdraft, 39 medium of exchange, 201; of money type, 63; privatization and, 20– 21; Panda, 32– 33 state- owned, 128

---
## Пустые и почти пустые абзацы (39)

Исходный абзац длиной ≥ 40 символов, а в озвучке от него осталось < 40 символов (или он не вернулся вовсе).

### 1. `p0218` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> This comes from the science of economics itself.

**В озвучку попало:**

> Он порожден самой экономической наукой.

---

### 2. `p0496` — длина озвучки / длина оригинала: 0.54; классы правки: —

**Исходный абзац:**

> Park TimeBank. *Photo credit*: Zach Lipp.

**В озвучку попало:**

> Фотография Зака Липпа.

---

### 3. `p0537` — длина озвучки / длина оригинала: 0.95; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### The Chiemgauer inspired by Christian

**В озвучку попало:**

> ### Кимгауэр, вдохновленный Кристианом

---

### 4. `p1141` — длина озвучки / длина оригинала: 0.86; классы правки: —

**Исходный абзац:**

> 7. Guaranteed circulation of the currency.

**В озвучку попало:**

> 7. Гарантированное обращение валюты.

---

### 5. `p1195` — длина озвучки / длина оригинала: 0.80; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • a multitude of local cooperative currencies

**В озвучку попало:**

> • массу местных кооперативных валют;

---

### 6. `p1196` — длина озвучки / длина оригинала: 0.93; классы правки: bullet_marker_left_in

**Исходный абзац:**

> • a wide variety of functional currencies

**В озвучку попало:**

> • широкий спектр функциональных валют.

---

### 7. `p1305` — длина озвучки / длина оригинала: 0.90; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> # From Scarcity to Sustainable Abundance

**В озвучку попало:**

> # От дефицита к устойчивому изобилию

---

### 8. `p1486` — длина озвучки / длина оригинала: 0.74; классы правки: —

**Исходный абзац:**

> 8. WIR Annual Report, 2010. www .wir .ch .

**В озвучку попало:**

> 8. Годовой отчет WIR, 2010 год.

---

### 9. `p1488` — длина озвучки / длина оригинала: 0.77; классы правки: —

**Исходный абзац:**

> 10. WIR Annual Report, 2010, 12. www .wir .ch .

**В озвучку попало:**

> 10. Годовой отчет WIR, 2010 год, 12.

---

### 10. `p1598` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> 24. See www .constitutionaltender .com .

**В озвучку попало:**

> 24. См. сайт Constitutional Tender.

---

### 11. `p1605` — длина озвучки / длина оригинала: 0.47; классы правки: —

**Исходный абзац:**

> 3. Donella Meadows’s Web site: www .donellameadows .org .

**В озвучку попало:**

> 3. Веб-сайт Донеллы Медоуз.

---

### 12. `p1614` — длина озвучки / длина оригинала: 0.53; классы правки: —

**Исходный абзац:**

> 12. See www .redicecreations .com /article .php ?id=10159 .

**В озвучку попало:**

> 12. См. сайт Red Ice Creations.

---

### 13. `p1636` — длина озвучки / длина оригинала: 0.44; классы правки: —

**Исходный абзац:**

> Local Economies.” 2012. www .creatingsustainablesocieties .com .

**В озвучку попало:**

> местных экономик». 2012 год.

---

### 14. `p1659` — длина озвучки / длина оригинала: 0.31; классы правки: —

**Исходный абзац:**

> Banking in a Changing Global Financial System.” IE Business School. January 11, 2011. www .ie .edu /business -school /.

**В озвучку попало:**

> Бизнес-школа IE. 11 января 2011 года.

---

### 15. `p1670` — длина озвучки / длина оригинала: 0.18; классы правки: —

**Исходный абзац:**

> *Journal,* May 1, 2012. www .hoover .org /publications /defi ning -ideas /article /116071 .

**В озвучку попало:**

> 1 мая 2012 года.

---

### 16. `p1686` — длина озвучки / длина оригинала: 0.38; классы правки: —

**Исходный абзац:**

> *Came into Being and Why No One Saw It Coming.* New York: Viking, 2007.

**В озвучку попало:**

> Нью-Йорк: Викинг, 2007 год.

---

### 17. `p1715` — длина озвучки / длина оригинала: 0.25; классы правки: year_lost

**Исходный абзац:**

> *New York Times,* November 2, 2011. www .nytimes .com /2011 /11 /03 / education /average -student -loan -debt -grew -by -5 -percent -in -2010 .html .

**В озвучку попало:**

> «Нью-Йорк Таймс», 2 ноября 2011 года.

---

### 18. `p1726` — длина озвучки / длина оригинала: 0.51; классы правки: —

**Исходный абзац:**

> America’s Future.” June 2011. www .mckinsey .com /insights /mgi .

**В озвучку попало:**

> будущее Америки». Июнь 2011 года.

---

### 19. `p1730` — длина озвучки / длина оригинала: 0.17; классы правки: —

**Исходный абзац:**

> 2010. www .bbc .co .uk /news /world -us -canada -18605326 .

**В озвучку попало:**

> 2010 года.

---

### 20. `p1740` — длина озвучки / длина оригинала: 0.81; классы правки: —

**Исходный абзац:**

> *Future.* New York: Riverhead Books, 2005.

**В озвучку попало:**

> Нью-Йорк: Риверхед Букс, 2005 год.

---

### 21. `p1747` — длина озвучки / длина оригинала: 0.10; классы правки: year_lost

**Исходный абзац:**

> 2011. www .abcnews .go .com /Business /income -doubles -top -percent -1979 /story ?id=14817561 .

**В озвучку попало:**

> 2011 года.

---

### 22. `p1755` — длина озвучки / длина оригинала: 0.25; классы правки: —

**Исходный абзац:**

> www .globalissues .org /article /26 /poverty -facts -and -stats #src22 .

**В озвучку попало:**

> Сайт Глобал Ишьюс.

---

### 23. `p1781` — длина озвучки / длина оригинала: 0.24; классы правки: —

**Исходный абзац:**

> www .time .com /time /world /article /0 ,8599 ,1701095 ,00 .html #ixzz1xtg StTME .

**В озвучку попало:**

> Сайт журнала «Тайм».

---

### 24. `p1787` — длина озвучки / длина оригинала: 0.21; классы правки: —

**Исходный абзац:**

> February 16, 2010. http:// reviews .cnet .com /8301 -13970 _7 -10454065 -78 .html #ixzz1K6sXaPmP .

**В озвучку попало:**

> 16 февраля 2010 года.

---

### 25. `p1802` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Abundance: in Curitiba, 142; sustainable,

**В озвучку попало:**

> Изобилие: в Куритибе, 142; устойчивое,

---

### 26. `p1867` — длина озвучки / длина оригинала: 0.93; классы правки: —

**Исходный абзац:**

> Concentration of wealth, 21– 22, 49– 53,

**В озвучку попало:**

> Концентрация богатства, 21–22, 49–53,

---

### 27. `p1870` — длина озвучки / длина оригинала: 0.88; классы правки: —

**Исходный абзац:**

> Conjunto Palmeira, 103– 108, *104*, *105*

**В озвучку попало:**

> Конжунто Палмейра, 103–108, 104, 105

---

### 28. `p1913` — длина озвучки / длина оригинала: 0.41; классы правки: —

**Исходный абзац:**

> Flow network, 32– 33, 61– 63 226–227*n*13; wispos and, 156– 157.

**В озвучку попало:**

> Сеть потоков, 32–33, 61–63

---

### 29. `p1936` — длина озвучки / длина оригинала: 0.50; классы правки: —

**Исходный абзац:**

> Ethics, 48– 49, 221– 222 Euro crisis, 50

**В озвучку попало:**

> Тщетность, двадцать.

---

### 30. `p1964` — длина озвучки / длина оригинала: 0.78; классы правки: —

**Исходный абзац:**

> Infrastructure, 15, 20– 21, 103, 194 227*n*21

**В озвучку попало:**

> Инфраструктура, 15, 20–21, 103, 194

---

### 31. `p1984` — длина озвучки / длина оригинала: 0.28; классы правки: —

**Исходный абзац:**

> Holacracy, 191 165– 166, *166*; in multicurrency world, 55

**В озвучку попало:**

> Холакратия, 191.

---

### 32. `p2037` — длина озвучки / длина оригинала: 0.45; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### Medium of exchange, 57, 58; assumption

**В озвучку попало:**

> ### Средство обмена

---

### 33. `p2041` — длина озвучки / длина оригинала: 0.49; классы правки: —

**Исходный абзац:**

> Mile High Business Alliance (MHBA), 104– 105, 107; Revolving Loan Fund,

**В озвучку попало:**

> Mile High Business Alliance (MHBA).

---

### 34. `p2056` — длина озвучки / длина оригинала: 0.11; классы правки: —

**Исходный абзац:**

> Overcrowding, 164 currency creation, 24, 27– 28; as Overdraft, 39 medium of exchange, 201; of money type, 63; privatization and, 20– 21; Panda, 32– 33 state- owned, 128

**В озвучку попало:**

> Мораль, 48–49, 134.

---

### 35. `p2073` — длина озвучки / длина оригинала: 0.60; классы правки: —

**Исходный абзац:**

> National debt, 42– 43, 70, 145– 147, 227*n*21 Poverty trap, 108

**В озвучку попало:**

> Национальный долг, 42–43, 70, 145–147.

---

### 36. `p2076` — длина озвучки / длина оригинала: 0.49; классы правки: —

**Исходный абзац:**

> National Program of Oriented Productive Principled society, 193– 194

**В озвучку попало:**

> Принципиальное общество, 193–194.

---

### 37. `p2082` — длина озвучки / длина оригинала: 0.29; классы правки: —

**Исходный абзац:**

> Nigeria, 42– 43 Profi t- neutral investment system,

**В озвучку попало:**

> Нигерия, 42–43.

---

### 38. `p2201` — длина озвучки / длина оригинала: 0.93; классы правки: stray_markup_or_ocr_garbage

**Исходный абзац:**

> ### United Nations Environmental Program

**В озвучку попало:**

> ### Программа ООН по окружающей среде

---

### 39. `p2218` — длина озвучки / длина оригинала: 0.33; классы правки: —

**Исходный абзац:**

> Work, 219– 220, 239*n*10 bility (VBSR), 102– 103

**В озвучку попало:**

> Работа, 219–220.

---
