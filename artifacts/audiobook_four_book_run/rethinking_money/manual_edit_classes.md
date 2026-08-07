# Счёт ручной правки после прогона — по классам (rethinking_money)

База: 2187 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 2187 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 119 | 5.4% |
| `truncated_sentence` | 40 | 1.8% |
| `year_spelled_out_for_tts_not_a_defect` | 21 | 1.0% |
| `year_lost` | 8 | 0.4% |
| `url_left_in` | 4 | 0.2% |
| `year_dropped_with_reference_apparatus` | 3 | 0.1% |
| `isbn_left_in` | 1 | 0.0% |
| `footnote_marker_left_in` | 1 | 0.0% |
| `not_translated` | 1 | 0.0% |
| `absent_from_artifact` | 1 | 0.0% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 119

**`narration#10`, исходный абзац:**

> —

**в озвучке:**

> — Тачи Киучи, председатель E-Square Inc. и Future 500

**`narration#21`, исходный абзац:**

> —

**в озвучке:**

> [serious] КАК НОВЫЕ ВАЛЮТЫ ПРЕВРАЩАЮТ ДЕФИЦИТ В

**`narration#56`, исходный абзац:**

> —

**в озвучке:**

> ОТ ДЕФИЦИТА К ПРОЦВЕТАНИЮ ЗА ОДНО ПОКОЛЕНИЕ

---

### `truncated_sentence` — 40

**`narration#3`, исходный абзац:**

> —

**в озвучке:**

> «Книга "Переосмысление денег" блестяще разрушает концепции и мифы, которыми дорожат наши экономисты и другие профессионалы в этой области. Авторы пишут, что "деньги — наше последнее табу", но они не призывают к отмене нынешней системы. Напротив, они мудро предлагают использовать новые валюты и другие финансовые инновации как дополнение к существующему порядку». — Найджел Сил, бывший председатель Earth Day International и основатель Earth Day Canada

**`narration#5`, исходный абзац:**

> —

**в озвучке:**

> Что еще важнее, авторы предлагают стратегический путь вперед. Их решения не просто переосмысливают деньги, они заново оценивают значимость человека, долгосрочного планирования и нашей планеты». — Джорджия Келли, исполнительный директор Praxis Peace Institute

**`narration#6`, исходный абзац:**

> —

**в озвучке:**

> «В условиях хаоса, порожденного сегодняшними кризисами, мало кто может предложить жизнеспособные решения, которые служат не только местным сообществам, но и всей мировой экономике. Бернар Лиетар и Джеки Данн — именно такая удивительная сила добра». — Мариана Бозесан, доктор наук, интегральный инвестор и автор книги «Становление

---

### `year_spelled_out_for_tts_not_a_defect` — 21

**`p0206`, исходный абзац:**

> By the late 17th century, the need to fi nance wars gave further impetus to the money- creating mechanism. A special relationship began between the emerging private banking systems and governments. The oldest surviving agreement of this type can be traced back to 1668, with the license of the Swedish Bank of the Estates of the Realm (the name was changed in 1867 to *Riksbank,* as the Swedish Central Bank is still known). The agreement gave the power of emission of paper money to a private bank, the Bank of the Estates of the Realm, when the crown urgently needed money to fund a war against Denmark. The same situation took place in Britain a generation later with the founding of the Bank of En gland (1688), to which the monopoly of emission of paper money was assigned by King William of Orange in 1694, when he needed 1.2 million pounds for a war against the French. From En gland, this pra

**в озвучке:**

> К концу семнадцатого века необходимость финансировать войны дала новый толчок механизму создания денег. Начали складываться особые отношения между возникающими частными банковскими системами и правительствами. Старейшее из сохранившихся соглашений такого рода датируется тысяча шестьсот шестьдесят восьмым годом, когда была выдана лицензия Шведскому банку сословий, который сегодня известен как Риксбанк. Это соглашение передало право выпуска бумажных денег частному банку, так как короне срочно требовались средства на войну со Швецией. Поколение спустя в Британии произошла похожая ситуация: в тысяча шестьсот девяносто четвертом году король Вильгельм Оранский предоставил монополию на выпуск бумажных денег Банку Англии, когда ему понадобилось один и два десятых миллиона фунтов для войны с Францией. Из Англии эта практика распространилась по всему миру. В Соединенных Штатах эта же сделка — когд

**`p0208`, исходный абзац:**

> During the latter days of the gold standard, the actual gold reserves of the Bank of En gland, for example, were treated as a state secret because the amount of gold backing for the British pound was much lower than publicly admitted.⁴ The last vestiges of the gold standard in the United States were removed by President Nixon in August 1971, when he offi cially stopped any convertibility between the U.S. dollar and gold, even for central banks, thereby severing the last link between a physical commodity and the money system. Their values were severed and divorced from each other.

**в озвучке:**

> На закате золотого стандарта реальные золотые резервы, например, Банка Англии, считались государственной тайной. Все потому, что объем золотого обеспечения британского фунта был гораздо меньше, чем официально заявлялось. Последние остатки золотого стандарта в Соединенных Штатах были ликвидированы президентом Никсоном в августе тысяча девятьсот семьдесят первого года. Он официально прекратил конвертацию доллара в золото даже для центральных банков, тем самым разорвав последнюю связь между физическим товаром и денежной системой. Их ценности оказались окончательно разделены.

**`p0499`, исходный абзац:**

> Lisa Conlan is CEO of TimeBanks USA, which has a nationwide count of some 286 systems. “The fi rst thing that drew me to time dollars was that I was overseeing a family- run advocacy or ga ni za tion in Rhode Island. So part of the support network is unique in that the families with children with behavioral health issues were helping one another. This type of help touched on child welfare, juvenile justice with kids with high levels of behavioral issues, and mental health needs. Two things struck me, however. One, what would happen if we couldn’t fi nd the funding we needed? And how do we really tap into the families’ energy and creativity to truly support one another? In my search, I stumbled on time dollars in 2007.”⁷ Using time as a unit of account, the families are able to arrange a variety of ser vices and all- important social events. Conlan continues:

**в озвучке:**

> Лиза Конлан — генеральный директор организации TimeBanks USA, которая объединяет около двухсот восьмидесяти шести систем по всей стране. «Первое, что меня привлекло в тайм-долларах, — это мой опыт управления семейной правозащитной организацией в Род-Айленде. Наша сеть поддержки была уникальна тем, что семьи, воспитывающие детей с особенностями поведения, помогали друг другу. Эта помощь затрагивала вопросы защиты детей, ювенальной юстиции и психического здоровья. Однако меня поразили две вещи. Во-первых, что будет, если мы не найдем необходимое финансирование? И как нам по-настоящему использовать энергию и творческий потенциал самих семей, чтобы они могли поддерживать друг друга? В поисках ответов в две тысячи седьмом году я наткнулась на концепцию тайм-долларов». Используя время как единицу учета, семьи смогли организовать множество услуг и важных социальных мероприятий. Конлан продолжае

---

### `year_lost` — 8

**`p0419`, исходный абзац:**

> The practice of dual currency systems is not new. Cooperative currencies have been in wide usage throughout most of history. In Western Eu rope, for example, they have been used without interruption for hundreds of years, from roughly 800 ad to around 1800 ad.⁷

**в озвучке:**

> Практика использования двойных валютных систем не нова. Кооперативные валюты широко применялись на протяжении большей части истории. Например, в Западной Европе они непрерывно использовались сотни лет — примерно с восьмисотого по тысяча восьмисотый год нашей эры.

**`p1361`, исходный абзац:**

> 3. www.imf.org/external/pubs/ft/wp/2012/wp12202.pdf and www.telegraph.co.uk / fi nance/comment/9623863/IMFs-epic-plan-to-conjure-away-debt-and- deth rone -bankers.html.

**в озвучке:**

> 3. Ссылки на официальные документы МВФ и статью в газете «Телеграф» о плане МВФ по избавлению от долгов и отстранению банкиров от власти.

**`p1383`, исходный абзац:**

> 19. The female participants range from primarily school- aged girls to house wives. *Enk*o ((cid:6600)(cid:1144)) means “compensated dating” and is a practice that originated in Japan, where older men give money and/or luxury gifts. See www .chinahush .com /2011 /11 /24 /young -compensated -dating -girls -in -shanghai /. Also, an anonymous girl posted on San Francisco’s Craigslist site that she will offer herself to get tickets to Coachel la. See http:// elitedaily .com /elite /2012 /girl -offer -sex -coachella -tickets /.

**в озвучке:**

> 20. Женщины-участницы варьируются от школьниц до домохозяек. «Энко» означает «оплачиваемые свидания» — практика, возникшая в Японии, где пожилые мужчины дают деньги или роскошные подарки. См. сайт ChinaHush. Также анонимная девушка разместила на сайте Craigslist в Сан-Франциско объявление о том, что она готова предложить себя в обмен на билеты на фестиваль Коачелла. См. сайт Elite Daily.

---

### `url_left_in` — 4

**`narration#31`, исходный абзац:**

> —

**в озвучке:**

> Заказы от американских книжных магазинов и оптовых компаний: пожалуйста, свяжитесь с Ingram Publisher Services по телефону (800) 509-4887, по факсу (800) 838-1149 или по электронной почте customer.service@ingrampublisherservices.com. Подробную информацию об электронных заказах можно найти на сайте ingrampublisherservices.com.

**`narration#1372`, исходный абзац:**

> —

**в озвучке:**

> См. материалы Международного валютного фонда по адресу imf.org и статью в газете «Телеграф» об эпическом плане МВФ по избавлению от долгов и ограничению власти банкиров.

**`narration#2183`, исходный абзац:**

> —

**в озвучке:**

> [serious] Книги издательства «Берретт-Кёлер» можно приобрести со скидкой при заказе от десяти экземпляров. Пожалуйста, позвоните нам по бесплатному номеру 8-800-929-2929 или напишите на электронную почту bkp.orders@aidcvt.com.

---

### `year_dropped_with_reference_apparatus` — 3

**`p0888`, исходный абзац:**

> Lerner adds, “When I was a governor, from 1994 to 1998 and again from 1998 to 2002, originally we wanted to avoid loans, as in the case of Argentina and the $800 million World Bank loan they took out to clean their bays. We decided that it’s not only a question of money but also a question of mentality. It’s not only a question of public works but also it’s how to successfully stimulate a learning pro cess. So we didn’t have the money to clean our bays. So instead we made agreements with our fi sherman. When they catch the fi sh, the fi sh belong to them. When the days weren’t good for fi shing, they catch garbage, we pay for the garbage with our tokens. The more garbage they fi shed, the cleaner the bay became; the cleaner the bay became, the more fi sh they could catch. It’s a win- win solution.”

**в озвучке:**

> Лернер добавляет: «Когда я был губернатором с 1994 по 2002 год, мы изначально хотели избежать кредитов. Вспомните Аргентину, которая взяла у Всемирного банка 800 миллионов долларов на очистку своих заливов. Мы решили, что дело не только в деньгах, но и в менталитете. Это не просто вопрос общественных работ, это вопрос того, как успешно стимулировать процесс обучения. У нас не было денег на очистку заливов, поэтому мы договорились с рыбаками. Пойманная рыба оставалась у них. А в дни, когда рыбалка была неудачной, они собирали мусор, и мы платили за него жетонами. Чем больше мусора они вылавливали, тем чище становился залив, а чем чище был залив, тем больше рыбы они могли поймать. Это решение, в котором выигрывают все».

**`p1384`, исходный абзац:**

> 20. “Policymakers, cognizant that 44 states project bud get shortfalls in 2012, were exploring ways to let these states declare bankruptcy” in “States Most Likely to Go Bankrupt,” Daily Beast, January 26, 2011. www .thedailybeast .com /articles /2011 /01 /26 /states -most -likely -to -go -bankrupt .html. Also, see “50 States in Debt,” Daily Beast Business Section. www .thedailybeast .com /galleries /2010 /06 /14 /50 -states -in -debt .html .

**в озвучке:**

> [serious] 20. В статье «Штаты, наиболее близкие к банкротству», опубликованной в «Дейли Бист» 26 января 2011 года, отмечалось: «Политики, осознавая, что 44 штата прогнозируют дефицит бюджета в 2012 году, изучают способы, позволяющие этим штатам объявить о банкротстве». Также см. раздел «50 штатов в долгах» в бизнес-рубрике «Дейли Бист».

**`p2238`, исходный абзац:**

> 1999. During this period, Bernard was appointed president of the elec- tronic payment system in Belgium, considered the most inclusive and cost- effective payment system in the world. In 1987, Bernard left the Central Bank and cofounded one of the fi rst large- scale off- shore cur- rency trading funds. During his three- year tenure as its general man- ager and currency trader, from 1987 to mid- 1991, the largest of these funds (Gaia Hedge II) was rated by the Micropal survey as the top performer among 75 currency hedge funds and among all 1,800 off- shore funds worldwide. In 1990, *Business Week* named Bernard “the world’s top trader.”

**в озвучке:**

> В этот период Бернар был назначен президентом системы электронных платежей в Бельгии, которая считалась самой инклюзивной и экономически эффективной платежной системой в мире. В 1987 году Бернар покинул Центральный банк и стал соучредителем одного из первых крупных офшорных фондов валютной торговли. За три года его работы в качестве генерального менеджера и валютного трейдера, с 1987 по середину 1991 года, крупнейший из этих фондов, «Гайя Хедж 2», был признан по результатам исследования «Микропал» лучшим среди 75 валютных хедж-фондов и всех 1800 офшорных фондов по всему миру. В 1990 году журнал «Бизнес Уик» назвал Бернара лучшим трейдером в мире.

---

### `isbn_left_in` — 1

**`narration#34`, исходный абзац:**

> —

**в озвучке:**

> ISBN печатного издания в твердом переплете: 978-1-60994-296-0. ISBN электронной книги в формате PDF: 978-1-60994-297-7. ISBN электронной книги в формате IDPF: 978-1-60994-298-4. Год издания: 2013. Дизайнер обложки: Николь Хейворд. Иллюстрация на обложке: коллаж из изображений © iStock/perets, iStock/James Lee и Николь Хейворд.

---

### `footnote_marker_left_in` — 1

**`narration#206`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Критически важно понимать, что как используемая математика, так и многие предположения, положенные в основу экономической теории, были фундаментально ошибочны. Физика того времени исходила из того, что все системы закрыты и статичны, поддерживая ньютоновский взгляд на космос как на идеально упорядоченную структуру. В своей книге «Происхождение богатства» Эрик Бейнхакер подробно описывает заблуждения теории равновесия, используемой в традиционной экономике. Он приходит к выводу, что готовность экономистов жертвовать реализмом ради математической предсказуемости задала шаблон, которому они следовали весь следующий век. Аккуратная картина вселенной Ньютона была разрушена спустя 200 лет Эйнштейном с его знаменитым уравнением E = mc². Энергия и материя оказались в изысканном танце взаимозаменяемости. Внезапно границы реальности изменились и расширились. Но революция только начина

---

### `not_translated` — 1

**`narration#1979`, исходный абзац:**

> —

**в озвучке:**

> Overcrowding, 164 currency creation, 24, 27– 28; as Overdraft, 39 medium of exchange, 201; of money type, 63; privatization and, 20– 21; Panda, 32– 33 state- owned, 128

---

### `absent_from_artifact` — 1

**`p0021`, исходный абзац:**

> RETHINKING MONEY

**в озвучке:**

> None

---

## Новый класс, которого не было в таксономии 2026-08-04: `back_matter_narrated`

На Money & Sustainability этот дефект увидеть было нельзя — там аппарат книги
выбрасывался целиком, поэтому в классах первого прогона его нет. На корпусе из четырёх
книг он виден, поэтому считается здесь.

**Как считается.** По списку блоков продакшена (`blocks.json`) ищется ПЕРВЫЙ блок,
чей заголовок называет аппарат книги (`Notes` / `Index` / `Bibliography` / `References` /
`Endnotes`). Всё от этого блока и до конца документа считается аппаратом. Затем по парам
«исходник → озвучка» считается, сколько из этих абзацев ДОШЛО до артефакта озвучки.
`Acknowledgements` и «Об авторе» аппаратом НЕ считаются: это авторская проза, её могут
хотеть услышать.

- граница: блок `250` — `## **INDEX**`
- блоков аппарата: 55, из них исключено из озвучки: 1
- **абзацев аппарата, попавших в озвучку: 461**
- **символов: 38479**

Примеры (цитаты из артефакта):

**`p1801`:**

> ## Предметный указатель

**`p1802`:**

> Изобилие: в Куритибе, 142; устойчивое,

**`p1803`:**

> Банджар, 187–190
