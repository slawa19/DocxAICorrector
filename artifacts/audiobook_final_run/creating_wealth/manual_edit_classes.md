# Счёт ручной правки после прогона — по классам (creating_wealth)

База: 1494 абзацев итогового narration-артефакта (`.tts.txt`) —
именно то, что человек открыл бы и правил перед отправкой в TTS. Классы
`paragraph_emptied`, `year_*`, `absent_from_artifact`, `literal_empty_placeholder` видны
только по парам «исходник → озвучка» и считаются по 1519 абзацам, отданным модели.
Один абзац может попасть в несколько классов.

| класс | абзацев | доля от абзацев озвучки |
|---|---:|---:|
| `heading_without_terminal_punctuation_not_a_defect` | 68 | 4.6% |
| `year_lost` | 15 | 1.0% |
| `year_spelled_out_for_tts_not_a_defect` | 12 | 0.8% |
| `url_left_in` | 9 | 0.6% |
| `truncated_sentence` | 5 | 0.3% |
| `year_dropped_with_reference_apparatus` | 2 | 0.1% |

## Примеры по классам

### `heading_without_terminal_punctuation_not_a_defect` — 68

**`narration#2`, исходный абзац:**

> —

**в озвучке:**

> РАЗВИТИЕ МЕСТНОЙ ЭКОНОМИКИ С ПОМОЩЬЮ ЛОКАЛЬНЫХ ВАЛЮТ

**`narration#3`, исходный абзац:**

> —

**в озвучке:**

> [serious] Гвендолин Холлсмит и Бернард Лиетар

**`narration#17`, исходный абзац:**

> —

**в озвучке:**

> — Доктор Самир Габбур, Каирский университет, председатель,

---

### `year_lost` — 15

**`p1520`, исходный абзац:**

> Barter Systems, Inc website. [online]. [cited December 28, 2010]. bartersys.com/index.asp. A leader in the commercial barter industry which offers exchange by way of goods and services and no cash. Colin Harrison. *Project Proposal: CyberTroc* — *A Barter System for the* *Information Society*.

**в озвучке:**

> [serious] Веб-сайт компании Barter Systems, Inc. Это один из лидеров в индустрии коммерческого бартера, предлагающий обмен товарами и услугами без использования наличных денег. Колин Харрисон, «Проектное предложение: CyberTroc — бартерная система для информационного общества».

**`p1521`, исходный абзац:**

> [online]. [cited December 28, 2010]. ict- 21.ch/ICT.SATW.CH/IMG/doc/ProjectProposalCyberTroc_c.doc. An article about CyberTroc, a type of internet-based barter system.

**в озвучке:**

> Статья о CyberTroc, разновидности бартерной системы, основанной на использовании интернета.

**`p1527`, исходный абзац:**

> *New Money for Healthy Communities*. [online]. [cited December 28, 2010]. ratical.org/many_worlds/cc/NMfHC/chp12.html. Complementary Currency Resource Center website. [online]. [cited December 28, 2010].

**в озвучке:**

> «Новые деньги для здоровых сообществ». Ресурсный центр альтернативных валют.

---

### `year_spelled_out_for_tts_not_a_defect` — 12

**`p0600`, исходный абзац:**

> A study done by Michael Maranda, an assistant curator of the Art Gallery of York University in Toronto, Canada, on the plight of Canadian artists revealed the underlying truth of the near cliché image of the starving artist. In Canada in 2009, the average income for a visual artist was $20,000 per year, well below the national average for all incomes of $28,850.³ In the United States, the situation is similar. The median income of all artists from 2003–2005 was $34,800, but this figure includes the income from all sources, not just the artwork they are producing. Full-time artists earned a median income of $42,200, fully $10,000 less than the $52,500 median income for other professionals. For the 45% of other artists who do not work full-time all year, their plight is the same as those in Canada, with a median income of $20,000. By contrast, office clerks in the United States earn an ave

**в озвучке:**

> Исследование Майкла Маранды, помощника куратора Художественной галереи Йоркского университета в Торонто, посвященное положению канадских художников, раскрыло суровую правду, стоящую за клише о «голодном художнике». В две тысячи девятом году средний доход канадского художника составлял двадцать тысяч долларов в год, что значительно ниже среднего национального дохода в двадцать восемь тысяч восемьсот пятьдесят долларов. В Соединенных Штатах ситуация похожая. Медианный доход всех художников с две тысячи третьего по две тысячи пятый год составлял тридцать четыре тысячи восемьсот долларов, но эта цифра включает доходы из всех источников, а не только от продажи произведений искусства. Художники, работающие полный день, имели медианный доход сорок две тысячи двести долларов — это на десять тысяч меньше, чем у других профессионалов. Для сорока пяти процентов художников, которые не работают полны

**`p0669`, исходный абзац:**

> As of November 2004 the Kyoto Treaty on climate change has been legally binding for 141 countries.

**в озвучке:**

> [serious] На ноябрь две тысячи четвёртого года Киотский протокол об изменении климата стал юридически обязательным для ста сорока одной страны.

**`p0730`, исходный абзац:**

> In the 1980s the public, and particularly investors, began to pay more attention to where their money was going. The idea of socially responsible investing (although again, not new) took off, spurred largely by the call to end apartheid in South Africa. Wall Street heeded the call, and soon investors could choose *socially responsible* stocks and funds. By 1999, the Dow Jones Sustainability Indices had been created, and the idea of selling “green” was catching on.

**в озвучке:**

> В восьмидесятые годы общественность, и особенно инвесторы, стали внимательнее следить за тем, куда направляются их деньги. Идея социально ответственного инвестирования, хотя и не новая, получила мощный импульс, во многом благодаря призывам положить конец апартеиду в Южной Африке. Уолл-стрит прислушалась к этим требованиям, и вскоре инвесторы получили возможность выбирать социально ответственные акции и фонды. К тысяча девятьсот девяносто девятому году были созданы индексы устойчивого развития Доу-Джонса, и идея «зеленого» бизнеса начала набирать обороты.

---

### `url_left_in` — 9

**`narration#1430`, исходный абзац:**

> —

**в озвучке:**

> [thoughtful] Глобальные общественные инициативы, сайт global-community.org. Валютные решения для более разумного мира, сайт lietaer.com.

**`narration#1440`, исходный абзац:**

> —

**в озвучке:**

> complementarycurrency.org.

**`narration#1448`, исходный абзац:**

> —

**в озвучке:**

> Адрес сайта: mc-sa.org/partners/neighborhood/timedollar.asp.

---

### `truncated_sentence` — 5

**`narration#192`, исходный абзац:**

> —

**в озвучке:**

> Облигации — это долгосрочные долговые обязательства, которые выпускаются всеми уровнями власти для финансирования инфраструктуры: дорог, очистных сооружений, водопроводов, тюрем, библиотек и школ. На федеральном уровне долгосрочный долг также представлен казначейскими нотами со сроком погашения от одного года до десяти лет, казначейскими облигациями со сроком от двадцати до тридцати лет и так называемыми казначейскими ценными бумагами с защитой от инфляции, или

**`narration#440`, исходный абзац:**

> —

**в озвучке:**

> В последние десятилетия авторитетные экономисты начали включать в расчеты стоимость неоплачиваемого домашнего труда, который не учитывается в валовом внутреннем продукте и других стандартных экономических показателях. Тщательные оценки вклада домашнего труда в экономику варьируются от одной четвертой до

**`narration#1071`, исходный абзац:**

> —

**в озвучке:**

> работу сорока волонтеров-молодежников, которые потратили около четырехсот двадцати пяти часов на интервью со ста пятьюдесятью лидерами сообществ;

---

### `year_dropped_with_reference_apparatus` — 2

**`p1074`, исходный абзац:**

> This effort was completed in 1997, and all the input was sent on to a drafting committee that had been created by the Earth Charter Commission in 1996. Professor Rockefeller was appointed by the Commission to chair the drafting committee, and the committee held meetings with groups of experts, including scientists, international lawyers and religious leaders and then circulated numerous drafts back to all the national committees, focal points and organizations in the countries that had engaged in the dialogue for comment. At the Rio +5 Forum in 1997, a benchmark draft of the Earth Charter was released for circulation and comment. In 2000, the Earth Charter Commission came to consensus on the document in a meeting held at the UNESCO Headquarters in Paris. A formal launch of the Earth Charter was held in the Peace Palace in The Hague.

**в озвучке:**

> Эта работа была завершена в 1997 году, а все собранные предложения передали в редакционный комитет, созданный Комиссией по Хартии Земли годом ранее. Профессор Рокфеллер возглавил этот комитет. Эксперты, включая ученых, юристов-международников и религиозных деятелей, проводили встречи и рассылали многочисленные черновики национальным комитетам и организациям для получения комментариев. В 1997 году на форуме «Рио плюс пять» был представлен базовый проект Хартии Земли для широкого обсуждения. В 2000 году Комиссия по Хартии Земли пришла к согласию по тексту документа на встрече в штаб-квартире ЮНЕСКО в Париже. Официальная церемония принятия Хартии Земли состоялась во Дворце мира в Гааге.

**`p1802`, исходный абзац:**

> 9. *History of Money: 1930-1933*. [online]. [cited January 16, 2011]. mindcontagion.org/money/hm1930.html.

**в озвучке:**

> 9. «История денег: 1930–1933». Сайт: mindcontagion.org/money/hm1930.html.

---
