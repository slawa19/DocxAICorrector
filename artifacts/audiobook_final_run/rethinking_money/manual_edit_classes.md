# Счёт ручной правки после прогона — по классам (rethinking_money)

База: 1734 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1736 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 92 | 5.3% |
| `truncated_sentence` | 34 | 2.0% |
| `year_spelled_out_for_tts_not_a_defect` | 10 | 0.6% |
| `url_left_in` | 3 | 0.2% |
| `year_dropped_with_reference_apparatus` | 2 | 0.1% |
| `isbn_left_in` | 1 | 0.1% |
| `footnote_marker_left_in` | 1 | 0.1% |
| `not_translated` | 1 | 0.1% |
| `absent_from_artifact` | 1 | 0.1% |
| `year_lost` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 92

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

### `truncated_sentence` — 34

**`narration#1`, исходный абзац:**

> —

**в озвучке:**

> «Вы даже не представляете, что такое деньги на самом деле. Прочитайте эту книгу, чтобы узнать, как простая смена нашей денежной системы может привести к более устойчивому и мирному обществу». — Юрриан Камп, главный редактор журнала The Intelligent Optimist

**`narration#3`, исходный абзац:**

> —

**в озвучке:**

> «Книга "Переосмысление денег" блестяще справляется с задачей разрушения стереотипов, которые так дороги нашим экономистам и другим профессионалам в этой области. Авторы пишут, что "деньги — это наше последнее табу", но они не призывают к отмене фиатных валют. Напротив, они мудро предлагают использовать новые валюты и другие денежные инновации как дополнение к существующей системе». — Найджел Сил, бывший председатель Earth Day International и основатель Earth Day Canada

**`narration#5`, исходный абзац:**

> —

**в озвучке:**

> Что еще важнее, авторы предлагают стратегию движения вперед. Они описывают решения, которые не просто переосмысливают деньги, но и возвращают ценность человеку, долгосрочному планированию и нашей планете». — Джорджия Келли, исполнительный директор Praxis Peace Institute

---

### `year_spelled_out_for_tts_not_a_defect` — 10

**`p0206`, исходный абзац:**

> By the late 17th century, the need to fi nance wars gave further impetus to the money- creating mechanism. A special relationship began between the emerging private banking systems and governments. The oldest surviving agreement of this type can be traced back to 1668, with the license of the Swedish Bank of the Estates of the Realm (the name was changed in 1867 to *Riksbank,* as the Swedish Central Bank is still known). The agreement gave the power of emission of paper money to a private bank, the Bank of the Estates of the Realm, when the crown urgently needed money to fund a war against Denmark. The same situation took place in Britain a generation later with the founding of the Bank of En gland (1688), to which the monopoly of emission of paper money was assigned by King William of Orange in 1694, when he needed 1.2 million pounds for a war against the French. From En gland, this pra

**в озвучке:**

> К концу семнадцатого века необходимость финансировать войны дала новый толчок механизмам создания денег. Между частными банками и правительствами возникли особые отношения. Старейшее из сохранившихся соглашений такого рода датируется тысяча шестьсот шестьдесят восьмым годом, когда была выдана лицензия Шведскому банку сословий, который сегодня известен как Риксбанк. Правительству срочно нужны были деньги на войну против Дании, и оно передало право выпуска бумажных денег частному банку. Поколение спустя аналогичная ситуация произошла в Британии. В тысяча шестьсот девяносто четвертом году король Вильгельм Оранский передал монополию на выпуск бумажных денег Банку Англии, чтобы получить один миллион двести тысяч фунтов на войну с Францией. Из Англии эта практика распространилась по всему миру. В Соединенных Штатах эта же схема — когда правительство признает банковские долговые обязательства з

**`p0208`, исходный абзац:**

> During the latter days of the gold standard, the actual gold reserves of the Bank of En gland, for example, were treated as a state secret because the amount of gold backing for the British pound was much lower than publicly admitted.⁴ The last vestiges of the gold standard in the United States were removed by President Nixon in August 1971, when he offi cially stopped any convertibility between the U.S. dollar and gold, even for central banks, thereby severing the last link between a physical commodity and the money system. Their values were severed and divorced from each other.

**в озвучке:**

> На закате золотого стандарта реальные золотые запасы Банка Англии, например, были государственной тайной, поскольку объем золотого обеспечения британского фунта был гораздо ниже официально заявленного. Последние остатки золотого стандарта в Соединенных Штатах были отменены президентом Никсоном в августе тысяча девятьсот семьдесят первого года. Он официально прекратил конвертацию доллара в золото даже для центральных банков, разорвав последнюю связь между физическим товаром и денежной системой. Их ценности оказались окончательно разделены.

**`p0499`, исходный абзац:**

> Lisa Conlan is CEO of TimeBanks USA, which has a nationwide count of some 286 systems. “The fi rst thing that drew me to time dollars was that I was overseeing a family- run advocacy or ga ni za tion in Rhode Island. So part of the support network is unique in that the families with children with behavioral health issues were helping one another. This type of help touched on child welfare, juvenile justice with kids with high levels of behavioral issues, and mental health needs. Two things struck me, however. One, what would happen if we couldn’t fi nd the funding we needed? And how do we really tap into the families’ energy and creativity to truly support one another? In my search, I stumbled on time dollars in 2007.”⁷ Using time as a unit of account, the families are able to arrange a variety of ser vices and all- important social events. Conlan continues:

**в озвучке:**

> Лиза Конлан — генеральный директор организации TimeBanks USA, которая насчитывает около двухсот восьмидесяти шести отделений по всей стране. «Первое, что меня привлекло в тайм-долларах, — это работа в семейной правозащитной организации в Род-Айленде. Наша сеть поддержки была уникальна тем, что семьи, воспитывающие детей с особенностями поведения, помогали друг другу. Эта помощь затрагивала вопросы защиты детей, ювенальной юстиции и психического здоровья. Однако меня поразили две вещи. Во-первых, что будет, если мы не найдем необходимое финансирование? И во-вторых, как нам по-настоящему использовать энергию и творческий потенциал семей, чтобы они могли поддерживать друг друга? В поисках ответов в две тысячи седьмом году я наткнулась на идею тайм-долларов». Используя время как единицу учета, семьи смогли организовать множество услуг и важных социальных мероприятий. Конлан продолжает:

---

### `url_left_in` — 3

**`narration#31`, исходный абзац:**

> —

**в озвучке:**

> Заказы от книжных магазинов и оптовых компаний США: пожалуйста, обращайтесь в службу «Ингрэм Паблишер Сервисиз» по телефону 800-509-4887, факсу 800-838-1149 или по электронной почте customer.service@ingrampublisherservices.com. Подробности об электронном заказе можно найти на сайте

**`narration#1730`, исходный абзац:**

> —

**в озвучке:**

> [serious] Книги издательства «Берретт-Кёлер» можно приобрести со скидкой при заказе от десяти экземпляров. Пожалуйста, позвоните нам по бесплатному номеру восемьсот, девятьсот двадцать девять, двадцать девять, двадцать девять или напишите на электронную почту bkp.orders@aidcvt.com.

**`narration#1732`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] BKcommunity.com — это виртуальная площадка, где люди со всего мира могут встретить единомышленников и вместе работать над созданием мира, который будет комфортен для всех.

---

### `year_dropped_with_reference_apparatus` — 2

**`p0888`, исходный абзац:**

> Lerner adds, “When I was a governor, from 1994 to 1998 and again from 1998 to 2002, originally we wanted to avoid loans, as in the case of Argentina and the $800 million World Bank loan they took out to clean their bays. We decided that it’s not only a question of money but also a question of mentality. It’s not only a question of public works but also it’s how to successfully stimulate a learning pro cess. So we didn’t have the money to clean our bays. So instead we made agreements with our fi sherman. When they catch the fi sh, the fi sh belong to them. When the days weren’t good for fi shing, they catch garbage, we pay for the garbage with our tokens. The more garbage they fi shed, the cleaner the bay became; the cleaner the bay became, the more fi sh they could catch. It’s a win- win solution.”

**в озвучке:**

> Лернер добавляет: «Когда я был губернатором с 1994 по 2002 год, мы изначально хотели избежать кредитов, как это было в случае с Аргентиной, которая взяла у Всемирного банка 800 миллионов долларов на очистку своих заливов. Мы решили, что дело не только в деньгах, но и в менталитете. Важно не только строить объекты, но и успешно стимулировать процесс обучения. У нас не было денег на очистку заливов, поэтому мы договорились с рыбаками. Рыба, которую они ловят, остается им. А когда рыбалка была неудачной, они собирали мусор, и мы платили за него талонами. Чем больше мусора они вылавливали, тем чище становился залив, а чем чище был залив, тем больше рыбы они могли поймать. Это беспроигрышная ситуация».

**`p2238`, исходный абзац:**

> 1999. During this period, Bernard was appointed president of the elec- tronic payment system in Belgium, considered the most inclusive and cost- effective payment system in the world. In 1987, Bernard left the Central Bank and cofounded one of the fi rst large- scale off- shore cur- rency trading funds. During his three- year tenure as its general man- ager and currency trader, from 1987 to mid- 1991, the largest of these funds (Gaia Hedge II) was rated by the Micropal survey as the top performer among 75 currency hedge funds and among all 1,800 off- shore funds worldwide. In 1990, *Business Week* named Bernard “the world’s top trader.”

**в озвучке:**

> В тот же период Бернар был назначен президентом системы электронных платежей в Бельгии, которая считалась самой инклюзивной и экономически эффективной в мире. В 1987 году он покинул Центральный банк и стал соучредителем одного из первых крупных офшорных фондов валютной торговли. За три года его работы в качестве генерального менеджера и валютного трейдера, с 1987 по середину 1991 года, крупнейший из этих фондов — Gaia Hedge II — был признан рейтинговым агентством Micropal лучшим среди 75 валютных хедж-фондов и всех 1800 офшорных фондов мира. В 1990 году журнал Business Week назвал Бернара «лучшим трейдером в мире».

---

### `isbn_left_in` — 1

**`narration#34`, исходный абзац:**

> —

**в озвучке:**

> ISBN печатного издания в твердом переплете: 978-1-60994-296-0. ISBN электронной книги в формате PDF: 978-1-60994-297-7. ISBN электронной книги в формате IDPF: 978-1-60994-298-4. Год издания: 2013. Дизайнер обложки: Николь Хейворд. Иллюстрации на обложке: коллаж из изображений © iStock/perets, iStock/Джеймс Ли и Николь Хейворд.

---

### `footnote_marker_left_in` — 1

**`narration#206`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Важно понимать, что и математический аппарат, и многие предположения, заложенные в экономическую теорию, были фундаментально ошибочны. Физика того времени исходила из того, что все системы являются закрытыми и статичными, поддерживая ньютоновский взгляд на космос как на идеально упорядоченный механизм. В своей книге «Происхождение богатства» Эрик Бейнхакер подробно описывает заблуждения теории равновесия, используемой в традиционной экономике. Он заключает, что готовность экономистов жертвовать реализмом ради математической предсказуемости задала шаблон, которому они следовали весь следующий век. Аккуратная картина Вселенной по Ньютону была разрушена спустя 200 лет Эйнштейном и его знаменитым уравнением E = mc². Энергия и материя оказались в изысканном танце взаимопревращений. Границы реальности расширились. Но революция только начиналась. Ньютоновская механика, правившая ве

---

### `not_translated` — 1

**`narration#1450`, исходный абзац:**

> —

**в озвучке:**

> International Architecture Exhibition, 85 131 International Monetary Fund (IMF), 144, Hate group, 182 182, 184 Health care, 14, 16; free clinic, 162– 165; International reserve currency, 57– 58 in Mae Hong Son, 205 Internet: community, 57– 58; technologies,

---

### `absent_from_artifact` — 1

**`p0021`, исходный абзац:**

> RETHINKING MONEY

**в озвучке:**

> None

---

### `year_lost` — 1

**`p0419`, исходный абзац:**

> The practice of dual currency systems is not new. Cooperative currencies have been in wide usage throughout most of history. In Western Eu rope, for example, they have been used without interruption for hundreds of years, from roughly 800 ad to around 1800 ad.⁷

**в озвучке:**

> Практика использования двух валют одновременно не нова. Кооперативные валюты широко применялись на протяжении большей части истории. Например, в Западной Европе они непрерывно использовались сотни лет — примерно с восьмисотого по тысяча восьмисотый год нашей эры.

---
