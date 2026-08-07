# Счёт ручной правки после прогона — по классам (creating_wealth)

База: 1499 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1519 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 73 | 4.9% |
| `year_spelled_out_for_tts_not_a_defect` | 20 | 1.3% |
| `year_lost` | 15 | 1.0% |
| `url_left_in` | 9 | 0.6% |
| `truncated_sentence` | 7 | 0.5% |
| `year_dropped_with_reference_apparatus` | 2 | 0.1% |
| `not_translated` | 1 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 73

**`narration#2`, исходный абзац:**

> —

**в озвучке:**

> РАЗВИТИЕ МЕСТНОЙ ЭКОНОМИКИ С ПОМОЩЬЮ ЛОКАЛЬНЫХ ВАЛЮТ

**`narration#3`, исходный абзац:**

> —

**в озвучке:**

> [serious] Гвендолин Холлсмит и Бернард Лиетар

**`narration#15`, исходный абзац:**

> —

**в озвучке:**

> — Эдгар С. Кан, доктор философии, доктор права, стипендиат фонда «Ашока»,

---

### `year_spelled_out_for_tts_not_a_defect` — 20

**`p0082`, исходный абзац:**

> Perhaps more than anyone, Gwendolyn’s parents and family are also worth mentioning. Wesley and Joan Hall set amazing examples of principled, intelligent people who worked hard for what they believe. Joan died in 2007, but Wesley continues to be very interested in and supportive of Gwendolyn’s work (even if he does refer to all these complementary currencies as “funny money”).

**в озвучке:**

> Нельзя не упомянуть родителей и семью Гвендолин. Уэсли и Джоан Холл стали для неё примером принципиальных и умных людей, которые упорно трудились ради своих убеждений. Джоан ушла из жизни в две тысячи седьмом году, но Уэсли продолжает живо интересоваться работой Гвендолин и поддерживает её, даже если в шутку называет все эти дополнительные валюты «игрушечными деньгами».

**`p0086`, исходный абзац:**

> Other editing assistance from Gina Ottoboni came at a critical time when my schedule was very demanding and I needed help pulling the last pieces together. Finally, I’m grateful to the Balaton Group and Dennis Meadows, who saw the importance of what we were talking about and scheduled the 2010 meeting in Iceland. That gave us a reason to travel there and meet with all the activists who were trying to put that country back on its feet. They also were an inspiration, and we wish them the best as the country struggles with real economic challenges.

**в озвучке:**

> Джина Оттобони оказала помощь в редактировании в критический момент, когда мой график был крайне плотным и мне требовалась поддержка, чтобы собрать воедино последние фрагменты. Наконец, я благодарна «Балатон Груп» и Деннису Медоузу. Они осознали важность того, о чём мы говорили, и организовали встречу в Исландии в две тысячи десятом году. Это дало нам повод поехать туда и встретиться со всеми активистами, которые пытались поставить страну на ноги. Они тоже стали для нас источником вдохновения, и мы желаем им всего наилучшего в борьбе с реальными экономическими вызовами.

**`p0541`, исходный абзац:**

> Today in North America, education makes a big financial impact on later earnings. As of the 2000 US census, those adults over 18 who had a high school diploma earned an average of $27,915 per year. Adults with bachelor ’s degrees earned an average of $51,206, while those with an advanced degree earned $74,602. Individuals who did not have a high school diploma only earned $18,734.² Only four states reported that over 90% of their young people earned a diploma. The Northeast region of the country had the highest number of college graduates — 30% of the population — whereas in the South the number of high school graduates dwindled to 25%.³

**в озвучке:**

> [serious] В современной Северной Америке образование оказывает огромное влияние на будущие доходы. По данным переписи населения США за две тысячи год, взрослые старше восемнадцати лет с дипломом средней школы зарабатывали в среднем около двадцати восьми тысяч долларов в год. Люди со степенью бакалавра получали в среднем пятьдесят одну тысячу, а с ученой степенью — почти семьдесят пять тысяч долларов. Те же, у кого не было даже школьного аттестата, зарабатывали менее девятнадцати тысяч. Лишь четыре штата сообщили, что более девяноста процентов их молодежи получили дипломы. В северо-восточном регионе страны было больше всего выпускников колледжей — тридцать процентов населения, тогда как на юге число выпускников школ снижалось до двадцати пяти процентов.

---

### `year_lost` — 15

**`p1520`, исходный абзац:**

> Barter Systems, Inc website. [online]. [cited December 28, 2010]. bartersys.com/index.asp. A leader in the commercial barter industry which offers exchange by way of goods and services and no cash. Colin Harrison. *Project Proposal: CyberTroc* — *A Barter System for the* *Information Society*.

**в озвучке:**

> [serious] Веб-сайт компании Barter Systems, Inc. Это один из лидеров в сфере коммерческого бартера, предлагающий обмен товарами и услугами без использования наличных денег. Колин Харрисон, «Проектное предложение: CyberTroc — бартерная система для информационного общества».

**`p1521`, исходный абзац:**

> [online]. [cited December 28, 2010]. ict- 21.ch/ICT.SATW.CH/IMG/doc/ProjectProposalCyberTroc_c.doc. An article about CyberTroc, a type of internet-based barter system.

**в озвучке:**

> Статья о CyberTroc — разновидности бартерной системы, работающей через интернет.

**`p1527`, исходный абзац:**

> *New Money for Healthy Communities*. [online]. [cited December 28, 2010]. ratical.org/many_worlds/cc/NMfHC/chp12.html. Complementary Currency Resource Center website. [online]. [cited December 28, 2010].

**в озвучке:**

> «Новые деньги для здоровых сообществ». Ресурсный центр взаимодополняющих валют.

---

### `url_left_in` — 9

**`narration#1434`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Ресурсы Глобальных общественных инициатив доступны на сайте global-community.org. Информация о валютных решениях для более разумного мира представлена на сайте lietaer.com.

**`narration#1444`, исходный абзац:**

> —

**в озвучке:**

> complementarycurrency.org.

**`narration#1452`, исходный абзац:**

> —

**в озвучке:**

> Адрес сайта: mc-sa.org/partners/neighborhood/timedollar.asp.

---

### `truncated_sentence` — 7

**`narration#715`, исходный абзац:**

> —

**в озвучке:**

> Показательный пример того, как лекарства заменяют здравый смысл, — количество детей в Соединенных Штатах, регулярно принимающих риталин. Это амфетамин, который назначают при гиперактивности и дефиците внимания, хотя существует прямая связь между таким поведением и пищей, перегруженной сахаром, химикатами и искусственными красителями. Научные данные подтверждают: поведение детей улучшается, если исключить из рациона искусственные красители, и ухудшается, если их добавить. Об этом говорит

**`narration#918`, исходный абзац:**

> —

**в озвучке:**

> Городские власти начали сотрудничать с Институтом устойчивых сообществ и получили финансирование от Агентства по охране окружающей среды США

**`narration#1074`, исходный абзац:**

> —

**в озвучке:**

> работу более сорока молодежных волонтеров, которые потратили около четырехсот двадцати пяти часов на интервью со ста пятьюдесятью лидерами местных сообществ;

---

### `year_dropped_with_reference_apparatus` — 2

**`p1074`, исходный абзац:**

> This effort was completed in 1997, and all the input was sent on to a drafting committee that had been created by the Earth Charter Commission in 1996. Professor Rockefeller was appointed by the Commission to chair the drafting committee, and the committee held meetings with groups of experts, including scientists, international lawyers and religious leaders and then circulated numerous drafts back to all the national committees, focal points and organizations in the countries that had engaged in the dialogue for comment. At the Rio +5 Forum in 1997, a benchmark draft of the Earth Charter was released for circulation and comment. In 2000, the Earth Charter Commission came to consensus on the document in a meeting held at the UNESCO Headquarters in Paris. A formal launch of the Earth Charter was held in the Peace Palace in The Hague.

**в озвучке:**

> Эта работа была завершена в 1997 году, а все собранные предложения передали в редакционный комитет, сформированный Комиссией Хартии Земли годом ранее. Профессор Рокфеллер возглавил этот комитет. Эксперты, включая ученых, юристов-международников и религиозных деятелей, проводили встречи и рассылали многочисленные черновики национальным комитетам и организациям для обсуждения. В 1997 году на форуме «Рио плюс пять» был представлен базовый проект Хартии Земли для широкого ознакомления. В 2000 году Комиссия достигла консенсуса по тексту документа на встрече в штаб-квартире ЮНЕСКО в Париже. Официальная церемония запуска Хартии Земли состоялась во Дворце мира в Гааге.

**`p1802`, исходный абзац:**

> 9. *History of Money: 1930-1933*. [online]. [cited January 16, 2011]. mindcontagion.org/money/hm1930.html.

**в озвучке:**

> 9. История денег: 1930–1933 годы. Сайт: mindcontagion.org/money/hm1930.html.

---

### `not_translated` — 1

**`narration#1481`, исходный абзац:**

> —

**в озвучке:**

> Сайт: magic-city-news.com/Community5/KatahdinTimeDollarExchange_38833883.shtml.

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

- граница: блок `416` — `### Notes`
- блоков аппарата: 27, из них исключено из озвучки: 19
- **абзацев аппарата, попавших в озвучку: 34**
- **символов: 7488**

Примеры (цитаты из артефакта):

**`p1791`:**

> ### Приложение

**`p1792`:**

> 1. Именно сторонник хартализма Георг Фридрих Кнапп определил деньги как всё, что правительство объявляет приемлемым для уплаты налогов. См. работы Георга Фридриха Кнаппа «Государственная теория денег» (1924) и Л. Рэндалла Рэя «Понимание современных денег: ключ к полной занятости и ценовой стабильнос

**`p1793`:**

> 2. Тем не менее, существуют исключения, хотя в современном мире они, как правило, носят временный характер. Например, в России после краха рубля в 1998 году правительство принимало от корпораций товары и сырье в счет уплаты налогов.
