# Аренда — кто занимает часть помещения, на какой срок и по какой ставке

## Problem Statement

BCMP holds 583 помещения across five БЦ, 324 of them арендопригодные, and does not know
about a single one of them whether anybody sits there.

The паспорт names parties at the level of the building and stops: `owner_party` is
«Компания системных бизнес технологий ТОО» for all five БЦ, `operator_party` is DownTown
Management ТОО. Below the building nothing names anybody at all. `PartyRole` carries a
`TENANT` value, zero rows, and no caller outside its registration in the Django admin —
the словарь has been promising for three stages that роли are hung on a Сторона separately
and for a period, and nothing has ever hung one.

So the questions a сотрудник УК arrives with have no screen to be asked on:

- «Кто сидит в каб305» — the карточка помещения shows код, наименование, назначение, тип,
  площадь and the place in the tree, and stops there.
- «Что стоит пустым» — 324 арендопригодных помещения, and the only honest answer BCMP can
  give today is that it has no idea.
- «По какой ставке помещение сдавалось в марте» — no срок and no ставка are recorded
  anywhere, so there is not even a wrong answer.
- «Когда кончается аренда на третьем этаже Tokyo» — the same.

And the shape of the data does not fit "one помещение, one арендатор". The УК's own table
reads «каб305: 40 м² — ТОО «Альфа», 60 м² — ИП Петров». There are no walls between those
two, and there will not be. A лобби holds a coffee point of 2 м² and stays a лобби. An
арендатор who took 40 м² in January takes another 20 in June without signing anything new
about the first 40.

This is also the first stage that gives the ИИ-управляющий something to answer with about
today rather than about the building's construction: every earlier stage described what was
built, and none described who is in it.

## Solution

**Аренда** — a flat record of one помещение, one Сторона as арендатор, an **арендуемая
площадь** in metres, a срок from a day to a day, a **ставка**, and a Сторона as
**арендодатель**. A помещение carries as many аренды as it has арендаторы sitting in it,
and their periods overlap freely: a часть is a number of metres, not a piece of the
building, and it has no boundary (ADR 0017).

There is no договор entity. Аренда is always about one помещение; a договор is a piece of
paper that may cover several with one срок, and BCMP does not hold it. The номер договора
is a free field on the аренда and its скан is attached as a документ.

Two screens, both of which already exist, and no new address anywhere:

- **Карточка помещения** on the экран этажа gains a block: «Сдано 210 из 300 м²», the
  действующие аренды underneath, the прошлые behind a fold. The same block carries the
  form: заведение, правка and удаление are submissions to the карточка's own address, so a
  refusal has the карточка to come back onto — the rule the плана upload and the близнец
  already follow (ADR 0005).
- **Полка помещений** gains an «Арендатор» column, a «свободно» condition in the отбор, and
  two more figures on the line under the table.

What the screens say is deliberately narrow. «Сдано ли помещение» is no longer a question
with a yes or a no: the screen prints two numbers and one derived state — **свободное
помещение**, meaning not one действующая аренда. «Сдано целиком» is not introduced, because
it would need a threshold the domain does not have — 299 of 300 м² is not «почти сдано», it
is two numbers, and the screen shows both.

## User Stories

### Что BCMP знает об аренде

1. As a сотрудник УК, I want an аренда to name the помещение, the арендатор, the метры, the
   срок and the ставка, so that «кто сидит в 305 и на каких условиях» is one record.
2. As a сотрудник УК, I want several аренды on one помещение at the same time, so that an
   опенспейс with three арендаторы is expressible without inventing three помещения that
   the building does not have.
3. As a сотрудник УК, I want the арендуемая площадь to be a number of metres and nothing
   more, so that I am not asked to draw a boundary that does not exist.
4. As a сотрудник УК, I want the арендуемая площадь never to be written into the площадь of
   the помещение, so that two арендаторы do not give one помещение two «настоящие» площади.
5. As a сотрудник УК, I want an аренда to name its арендодатель, so that a помещение let by
   the собственник and a помещение let by the УК in its own name are told apart.
6. As a сотрудник УК, I want the арендодатель not to be forced to be the собственник, so
   that доверительное управление is expressible — which is how all five БЦ actually stand.
7. As a сотрудник УК, I want the ставка to be за м² в месяц, so that two аренды of different
   size are comparable without arithmetic.
8. As a сотрудник УК, I want a free «номер договора» field, so that «по договору №17» can be
   written down without BCMP pretending to hold the договор.
9. As a сотрудник УК, I want an аренда to be about exactly one помещение, so that a record
   never claims to cover a building I have to go looking through.
10. As a сотрудник УК, I want a физлицо to be an арендатор as readily as a юрлицо, so that
    an ИП in the стрит-ритейл is not made to register a fictitious ТОО.

### Срок

11. As a сотрудник УК, I want the дата начала to be required, so that no record exists that
    cannot say whether it is in force today.
12. As a сотрудник УК, I want an empty «по» to read «по сей день», so that a бессрочная
    аренда needs no invented end date — the same reading the поэтажный план already gives.
13. As a сотрудник УК, I want both ends included in the период, so that an аренда «с 1 по 31
    марта» is in force on the 31st.
14. As a сотрудник УК, I want to record a досрочный выезд by changing «по» to the actual day,
    so that the screens stop showing an арендатор who has left.
15. As a сотрудник УК, I want a продление на новый срок to be a new аренда rather than a
    moved end date, so that «по какой ставке сдавалось в марте» keeps its answer.
16. As a сотрудник УК, I want the same арендатор to hold two аренды of one помещение at
    once, so that taking another 20 м² in June does not force me to overwrite the first 40.
17. As a сотрудник УК, I want periods on one помещение to overlap without complaint, so that
    the system does not refuse the ordinary case it was built for.
18. As a сотрудник УК, I want an аренда whose «по» precedes its «с» to be refused, so that a
    typo in a date is caught where it is made.

### Карточка помещения: чтение

19. As a сотрудник УК, I want the карточка помещения to say «Сдано 210 из 300 м²», so that I
    see at a glance how much of the помещение is taken.
20. As a сотрудник УК, I want the действующие аренды listed under that line with арендатор,
    метры, срок and ставка, so that «кто здесь сидит» is answered without a second screen.
21. As a сотрудник УК, I want the прошлые аренды behind a fold, so that ten departed
    арендаторы do not bury the one sitting there now.
22. As a сотрудник УК, I want the fold to say how many прошлые there are, so that I know
    whether opening it is worth the click.
23. As a сотрудник УК, I want the аренда block shown on every арендопригодное помещение even
    when it holds no аренды, so that «свободно» reads as an answer rather than as a section
    that failed to load.
24. As a сотрудник УК, I want the block hidden on a МОП or a техническое помещение with no
    аренды, so that a section promising data that does not exist is not put in front of me.
25. As a сотрудник УК, I want the block shown on a МОП that does hold an аренда, so that the
    банкомат in the лобби is visible where it stands.
26. As a сотрудник УК, I want «сдано X из Y м²» absent when the помещение has no площадь, so
    that a gap in the помещение's own data is not dressed up as a ratio.
27. As a сотрудник УК, I want an аренда with no арендуемая площадь shown with a dash and
    counted nowhere, so that a missing metre count is not read as zero metres.
28. As a сотрудник УК, I want the line to say «сдано 210 из 300 м², ещё у 2 аренд площадь не
    заведена», so that the number does not lie by omission.
29. As a сотрудник УК, I want «сдано 340 из 300 м²» printed as it is, so that an
    over-subscribed помещение is a finding I can see rather than a record I could not save.
30. As a сотрудник УК, I want the ставка shown with its unit, so that 4500 is not read as
    the monthly rent for the whole помещение.
31. As a сотрудник УК, I want no итог over the аренды of a floor or a building, so that the
    107 вложенные арендопригодные помещения are not counted twice (ADR 0019).

### Карточка помещения: заведение

32. As an администратор организации, I want a form on the карточка помещения, so that an
    аренда is entered where the помещение is already open in front of me.
33. As a сотрудник УК without the administrator right, I want no form at all, so that I am
    not offered an action that will be refused (ADR 0005).
34. As an администратор организации, I want the form to require only the арендатор and the
    дата начала, so that entering what I know is not blocked by what I do not.
35. As an администратор организации, I want to leave the арендодатель empty, so that the
    same company is not chosen 324 times.
36. As an администратор организации, I want to leave the арендуемая площадь empty, so that
    «весь кабинет, метраж в бумаге не указан» is recordable.
37. As an администратор организации, I want an empty площадь to mean «не заведено» and never
    «всё помещение», so that one empty field does not carry two opposite meanings.
38. As an администратор организации, I want to leave the ставка empty, so that an аренда
    whose бумага is lost is still recorded.
39. As an администратор организации, I want a refusal to come back on the карточка with the
    reason next to the field, so that I can fix it without losing what I typed.
40. As an администратор организации, I want the карточка to redraw with the new аренда on
    it, so that the screen itself is the confirmation.
41. As an администратор организации, I want to enter an аренда on a МОП or a техническое
    помещение, so that the банкомат in the лобби and the вендинг in the коридор are
    recordable (they surface as a находка on the полка, not as a refusal).
42. As an администратор организации of one организация, I want an аренда on another client's
    помещение refused, so that the form is not a way round the isolation (ADR 0001).

### Выбор Стороны

43. As an администратор организации, I want to find the арендатор by typing part of its
    название, so that a register of 699 Сторон is usable.
44. As an администратор организации, I want to find it by БИН/ИИН too, so that two companies
    with similar names are told apart.
45. As an администратор организации, I want the search to fold case, so that «альфа» finds
    «Альфа» (ADR 0014).
46. As an администратор организации, I want «не нашлось — завести Сторону» as a deliberate
    separate step, so that a register of 699 rows does not fill with «ТОО Альфа», «Альфа
    ТОО» and «ТОО «Альфа»».
47. As an администратор организации, I want the same search offered for the арендодатель, so
    that the two fields behave alike.
48. As an администратор организации, I want the search to look across all Стороны rather
    than my own организация's, so that a new арендатор nobody has met is findable — Стороны
    are a system-wide register, and the isolation is on the помещение.

### Правка и удаление

49. As an администратор организации, I want to edit an аренда in place, so that a corrected
    ставка does not need a second record.
50. As an администратор организации, I want to delete an аренда, so that one entered by
    mistake can be removed rather than nulled out.
51. As an администратор организации, I want удаление to be told apart from a съезд, so that
    the departure of an арендатор is a date and not an erasure.
52. As an администратор организации, I want deletion to ask for confirmation, so that a
    mis-click does not lose a record that has no undo.
53. As a сотрудник УК without the administrator right, I want no правка and no удаление
    offered, so that the карточка reads as a screen and not as a form.

### Полка помещений

54. As a сотрудник УК, I want an «Арендатор» column on the полка, so that «кто сидит» is
    answerable across the portfolio and not one помещение at a time.
55. As a сотрудник УК, I want that cell to name the арендатор when there is exactly one, so
    that the common case reads without a click.
56. As a сотрудник УК, I want it to say «3 арендатора» when there are several, so that a
    shared помещение is visible as shared.
57. As a сотрудник УК, I want a dash when there are none, so that emptiness reads as
    «свободно» rather than as missing data.
58. As a сотрудник УК, I want the column to count only действующие аренды, so that the полка
    speaks about today the way every other screen does.
59. As a сотрудник УК, I want a «свободно» condition in the отбор, so that «что стоит
    пустым» is one control rather than 324 карточки.
60. As a сотрудник УК, I want «свободно» to mean an арендопригодное помещение with no
    действующая аренда, so that a МОП is not reported as a leasing opportunity.
61. As a сотрудник УК, I want **no** «сдано» condition, so that the bar does not offer a
    second control that only ever means «не свободно».
62. As a сотрудник УК, I want the «свободно» condition to travel in the address like every
    other condition, so that a narrowed полка stays a link (ADR 0014's screen contract).
63. As a сотрудник УК, I want «свободно N» on the count line as a link that ticks that
    condition, so that the figure leads to the work rather than reporting it.
64. As a сотрудник УК, I want «аренды на неарендопригодных помещениях: N» on that line, so
    that a венткамера let by a slip of the dropdown is findable.
65. As a сотрудник УК, I want «аренд без площади: N» on that line, so that the gap that makes
    «сдано X из Y» incomplete is stated on the screen that holds it.
66. As a сотрудник УК, I want those figures to count what is on screen, so that the line does
    not contradict the table above it.
67. As a сотрудник УК, I want **no** итог under any аренда figure, so that the вложенные
    помещения are not double-counted (ADR 0015, ADR 0019).
68. As a сотрудник УК, I want the полка to stay a finder with no створки for entering an
    аренда, so that the one place аренды are entered stays the карточка помещения.

### Доступ и изоляция

69. As a сотрудник УК, I want to see аренды of my own организация's помещения only, so that
    the аренда obeys the checkpoint every other screen obeys (ADR 0001, ADR 0018).
70. As a сотрудник УК, I want an аренда to carry no организация of its own, so that there is
    one place deciding whose data is shown and not two (ADR 0018).
71. As a сотрудник УК, I want the аренда block to require signing in, so that it is not a way
    round the login.
72. As a сотрудник УК, I want an address naming another client's помещение to answer as it
    does today, so that the аренда adds no new way to ask about other clients' data.

### Язык

73. As a сотрудник УК, I want the screens to say «аренда» and never «договор», so that the
    word is not spent on something BCMP does not hold.
74. As a сотрудник УК, I want «арендуемая площадь» distinguished from «площадь», so that a
    condition of an agreement is not read as a measurement of the building.
75. As a сотрудник УК, I want «свободно» rather than «вакансия», so that the полка and the
    карточка name one state with one word.

## Implementation Decisions

### A new app, `leases`

The model lives in a **new app `leases`** with no urls and no menu item. ADR 0016 made a
раздел a Django app because the sidebar computes the open раздел from
`request.resolver_match.app_name`; аренда gets no раздел, so that argument does not apply
and the app is justified on its own ground — аренда is a subject area with rules of its own,
and `building_passport/models.py` already holds the паспорт, the план, the контур and seven
dictionaries. `rooms` is not an option: its `models.py` carries a comment explaining
precisely why it is empty.

`leases` imports `Space` from `building_passport` the way `documents` and `rooms` do.
`building_passport.views` and `rooms` import the occupancy rule from `leases`; there is no
cycle, because `leases.models` imports only `building_passport.models`, which imports
nothing back.

### The `Lease` model

One row per аренда: помещение (FK to `Space`, `related_name="leases"`), арендатор (FK to
`Party`), арендодатель (FK to `Party`, nullable), арендуемая площадь (nullable decimal),
ставка (nullable decimal), номер договора (nullable char), `valid_from` (required date),
`valid_to` (nullable date). A UUID primary key, like every other entity introduced since
stage 1. **No `org` column** (ADR 0018).

Validation is deliberately thin, and what is *absent* is the decision:

- **No overlap check of any kind.** Overlap is the normal case (ADR 0017).
- **No check that the sum of аренды fits the помещение.** Арендуемая площадь includes a
  share of the МОП by a coefficient; a check would refuse correct data.
- **No check that the помещение is арендопригодное.** The банкомат in the лобби is a real
  аренда; the venткамера let by mistake surfaces as a находка on the полка instead.
- **The period must be a period**: `valid_to` before `valid_from` is refused.
- **The помещение must be visible to the writer**, through the same chokepoint as the
  плана upload (ADR 0005) — an аренда on another client's помещение is refused.

The refusals sit on the model, so the admin, the form and any future script get the same
refusal in the same words. This is the shape the reverted branch used and the one part of it
worth keeping.

### Occupancy is one rule handed out in two shapes

«Сдано X из Y», «действующая на день» and «свободно» are needed by two screens: the карточка
wants them about one `Space`, the полка wants them as a queryset condition. They live in a
single module in `leases`, exposed in both shapes — the pattern `space_kind.py` established
for вид помещения and `plan_completeness.py` for полнота. Two copies of one rule would be
two answers to one question.

«Действующая на день» means `valid_from <= day` and (`valid_to` is null or `valid_to >=
day`); both ends included, an empty end reading «по сей день» — the same arithmetic the
действующий план already uses (ADR 0004).

**Свободное помещение** is `is_leasable` and no действующая аренда. It is counted in
помещения, never in metres (ADR 0019).

### Writes go to the карточка's own address

The аренда form stands on the карточка помещения, and заведение, правка and удаление are
submissions to `building_passport:space_card` — the rule `documents/urls.py` states for the
близнец and `FloorView.post` follows for the plan upload: a form goes to the address of the
screen it stands on, where a refusal has something to come back onto. The карточка is already
an htmx fragment fetched by `hx-get`, so the response to a write is the redrawn карточка and
no redirect is involved. **No new address is added by this stage.**

The Сторона search is a query parameter on that same address rather than an autocomplete
endpoint of its own: `…/card/?tenant_q=аль` redraws the карточка with the matches. This keeps
one address and matches what the словарь already says about отбор — it travels in the
address. Matching folds case through the regular-expression route (ADR 0014).

### `PartyRole.TENANT` is removed

Zero rows, no callers, nothing to migrate. Left in place it invites an арендатор to be
entered beside the аренда — with no metres, no срок and no ставка — and then a помещение is
let by one table and free by another. The other seven roles are untouched, and the словарь's
Сторона entry is rewritten: арендатором и арендодателем Сторону делает аренда, а не роль.

### The скан gets a link type

`DocumentLink.EntityType` gains **«аренда»**, following the rule spec 0003 recorded: the
stage that introduces an entity introduces its link type. Attaching a скан to the помещение
instead would pile every договор of a shared помещение into one heap with nothing to say
which аренда each belongs to. Attaching is not built on any screen in this stage — the type
exists so that the документы stage's привязка has somewhere to point when it is.

### Glossary

Already written into `CONTEXT.md` as part of this stage: **Аренда**, **Арендуемая площадь**,
**Арендодатель**, **Свободное помещение**, **Ставка**. **Арендопригодное помещение** is
reworded from «которое сдаётся» to «которое **может** сдаваться» — with аренды in the system
the old wording becomes false the moment a помещение stands empty. **Сторона** loses
«арендатор» from its list of роли.

### Наполнение

`scripts/load_real_data.py` gains a couple of dozen аренды on Manhattan, deliberately
including the awkward shapes the screens exist for: a помещение with three арендаторы, one
with a sum over its площадь, one аренда with no площадь, one with no ставка, one on a лобби,
and a pair of прошлые аренды so the fold has something behind it. Without them «сдано X из
Y», the находки and the отбор «свободно» cannot be looked at before the УК enters anything.

## Testing Decisions

A good test here checks what is observable at the HTTP boundary and nothing below it: which
помещения and аренды are on the screen, what is written in a row, what the count line says,
what status code comes back, and what is left in the database after a refusal. It does not
reach into the occupancy module, the form class or the query that built the page — those are
free to be rewritten, and a suite that pins them would have to be rewritten with them.

**Two seams, both existing, none new:**

1. **`building_passport:space_card`** — everything about the аренда block: what it shows,
   when it appears at all, the two numbers, the fold, and every write, since заведение,
   правка and удаление are submissions to this same address. Prior art:
   `building_passport/test_space_card.py` for the reads and
   `building_passport/test_plan_upload.py` for the write path, the administrator right and
   what survives a refusal.
2. **`rooms:room_list`** — the «Арендатор» column, the «свободно» condition, the count line
   and the two находки. Prior art: `rooms/test_shelf.py` and `rooms/test_search.py`, whose
   `ROW`/`CELL` regexes over `data-room` are reused as they stand.

**Footholds in the markup.** `data-lease` on each аренда row inside the block, mirroring
`data-room` and `data-document`, so a test names an аренда by its key and reads its text
without parsing the layout. `data-lease-form` on the form itself, mirroring `data-upload`:
it states whether the form is offered at all, which is how the administrator right is
checked.

**No third seam.** The occupancy rule gets no tests of its own, exactly as `space_kind` and
`plan_completeness` have none: it is read by both screens, and both screens check it. A
direct test would be a second account of one rule, and the two would eventually disagree.

**Fixtures.** The организации, the employees, the администратор организации, Manhattan and
its first floor come from the root `conftest.py` unchanged — there must not be a second
definition of one Manhattan. `leases/conftest.py` holds only what аренда needs: a Сторона or
two to be арендаторы, and a factory for an аренда. A помещение with вложенные already exists
in `first_floor` («каб101» inside «каб101вход»), which is what the "occupancy is not
inherited" test is staged on.

**What must be pinned by name**, because it is what a future reader will try to "fix":
overlapping periods on one помещение are accepted; the same арендатор twice on one помещение
is accepted; a sum over the помещение's площадь is accepted and printed; an аренда on a МОП
is accepted and counted as a находка; an аренда with no площадь is excluded from the sum and
counted separately; a помещение with no площадь prints no ratio.

## Out of Scope

- **Слои на плане.** No «занятость» layer, no «сроки» layer, and no choosing a layer by
  address. There is one layer today, hard-wired as `plan_layer.SPACE_KIND`; a second one
  means building the selection first. This is the part the reverted stage swelled on.
- **День в адресе / two time axes.** The screens speak about today. The история is stored
  and readable on the карточка, but no screen answers «как было в марте» by taking a date.
- **Полка аренд and раздел «Стороны».** «Где сидит ТОО «Альфа»» is a real question and it
  gets no screen in this stage. There is no раздел for Стороны at all, and building the
  fourth раздел on a model that has not yet seen a live row is premature.
- **Счёт свободного on the экран этажа and the карточка БЦ.** «Свободно 12 из 47» belongs
  there and is not built here.
- **Money.** No начисления, no оплаты, no задолженность, no НДС. They live in the учётная
  система that runs three юрлица, and a second account of the money would diverge from the
  first at the first payment. The ставка is a condition of the agreement, not a posting.
- **Currency.** Ставки are in тенге; there is no currency field. Add one when a договор in
  another currency actually appears.
- **A договор entity.** No header over the аренды, no grouping of several помещения under
  one срок (ADR 0017). The номер договора field is a note and groups nothing.
- **Attaching a скан to an аренда on a screen.** The link type is added; no upload uses it.
- **Собственник per помещение.** The собственник stays a column on the паспорт of the
  building. Whether помещения of one БЦ can belong to different собственники is a real
  question, and the арендодатель on the аренда makes it moot for this stage.
- **Loading аренды from the учётная система.** Entry is by hand through the form.
- **Any change to the помещение tree**, to контуры, or to `Space.area_m2`.

## Further Notes

**This stage was built once and reverted.** Commits `ee46fe5`…`24bd8fe` (11–13 August 2026)
carried a 461-line spec, a `leases` app with `Lease` and `LeaseSubject`, five ADRs, a
«сроки договоров» layer, a vacancy count, a карточка помещения answering «кто здесь сидит,
на какой срок и по какой ставке», and forms for заведение and расторжение. All of it was
removed by `0e6a161` with the message «Revert main to commit 5daaa7a» and no reason
recorded. The reason was scope.

That design decided the opposite of this one on two points, and it decided them with
arguments worth reading: «частью помещения предмет не бывает — то, что сдаётся отдельно, и
есть отдельное помещение», and periods on one помещение do not overlap. Both are reversed
here, and why is recorded in ADR 0017 so that the next reader who finds them in the history
does not conclude we were careless. What survives from that branch: the visibility
chokepoints and their tests, and the habit of putting refusals on the model. What is dead:
the заголовок-договор, the предмет, the overlap validation, the layer and the two time axes.

**ADR numbering.** The reverted branch used 0006–0010; those numbers were reused by the
документы stage. This stage's ADRs are **0017** (аренда — плоская запись о части
помещения), **0018** (видимость наследуется от помещения) and **0019** (занятость не
выводится из дерева).

**The figures behind the decisions**, for whoever revisits them:

- 583 помещения, 324 арендопригодных, and площадь is entered on **all 324** — so «сдано X
  из Y м²» is computable everywhere it is printed. All 36 помещения with no площадь are
  МОП or технические.
- **107 of the 324** арендопригодных sit inside another арендопригодное, and 43 have
  арендопригодные children. That is a third of the stock, and it is why occupancy is not
  read from the tree and why no итог is printed (ADR 0019).
- 699 Стороны in the register, overwhelmingly suppliers — which is why the арендатор is
  found by search and not chosen from a list.
- 5 лобби and 5 входные группы across the five БЦ — the places an аренда on a
  неарендопригодное помещение is actually expected.
- One организация today (DownTown Management ТОО), owner of none of the buildings: all five
  belong to «Компания системных бизнес технологий ТОО». The арендодатель field exists
  because that gap is already in the data.
