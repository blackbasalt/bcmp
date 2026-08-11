# Stage 3 — Аренда (договоры, вакансия и слой «сроки договоров»)

## Problem Statement

Stage 2 made the inside of a building visible: 82 помещения of Manhattan are drawn, coloured by
тип помещения, and the screen states what it could not draw. 44 of those помещения are marked
`is_leasable` — 1528.92 м² that exist to be rented — and BCMP holds **nothing whatsoever** about
whether any of them are.

The numbers are stark. There are 699 Стороны in the database and every one of them is a
поставщик; `party.csv` labels all 699 «Поставщики». `PartyRole` — the model that was supposed to
say who is a tenant — holds **0 rows** and is referenced nowhere outside its admin registration.
There is no lease table, no rate, no term, no tenant. A сотрудник УК can see that помещение 301
is арендопригодное and cannot see that it has been empty for eight months, or that the договор
on 305 expires in six weeks.

This is not a reporting gap, it is the central question of the business. «Сколько у нас свободно»
and «что освобождается к январю» are what the собственник asks the управляющая компания, and
today BCMP cannot form the question, let alone answer it. The слой mechanism built in stage 2 was
explicitly designed so that долги арендаторов and сроки договоров could arrive as new слои on the
same план — and both of them need a договор that does not exist.

There is a second problem, quieter. The glossary states that Сторона's roles «навешиваются
отдельно и на период», including арендатор. The code says otherwise: `BuildingPassport` nails
four roles down as columns (`owner_party`, `operator_party`, `designer_party`, `builder_party`)
with no period at all, and `PartyRole` is dead. Аренда is the first feature that cannot route
around this.

## Solution

**Договор аренды** becomes an entity of its own — tenant, term, and a **предмет** naming several
помещения, each with its own ставка and its договорная площадь. It is deliberately not a
`Document`: the scan is filed against it, but the facts live on the договор, because a слой that
colours by term and a counter that sums vacancy are queries over dates and spaces, not over a
JSON blob inside an attachment. This is the same move stage 2 made when it parsed the SVG into
контуры instead of keeping a picture (**ADR 0006**).

Time is governed exactly as планы are. Periods include both ends, an empty end reads «по сей
день», and two договоры may not cover one помещение on the same day — «сдано ли оно сегодня» must
have one answer. Расторжение closes the period with the date a human states; пролонгация is a
**new** договор linked to the old one, because renewal changes the rate and editing in place
destroys the answer to «по какой ставке помещение сдавалось в марте» (**ADR 0007**).

Арендатором a Сторона is made by the договор and by nothing else; `PartyRole.tenant` is removed
so that nobody enters a tenant past the договор and its overlap check (**ADR 0008**). And unlike
поэтажный план, a договор carries its own `org`: it names помещения across several зданий, so
visibility cannot be derived from one parent without choosing between a leak and a silent
disappearance (**ADR 0009**).

The screen work is small because stage 2 built the frame. A second **слой — «сроки договоров»**
paints свободно / действует / истекает over the same контуры. The floor screen and the Карточка
БЦ gain a vacancy count — «свободно 12 из 44 помещений, 387 из 1529 м²» — and, next to it, the
honest line saying how many договоры it stands on, so that today's empty answer reads as empty
rather than as a fully vacant building. The карточка помещения gains арендатор, срок and ставка.
A **Список договоров** appears as a screen of its own, with the form on it, because a договор
belongs to no building and has nowhere else to live.

Money stops at the door. Ставка is a condition of the договор; начисления, оплаты and
задолженность belong to the accounting system that runs three legal entities, and BCMP does not
keep a second version of them. The fourth слой the glossary promises — долги арендаторов — is not
paid by this stage.

## User Stories

### Договор и предмет

1. As a сотрудник УК, I want a договор аренды to name several помещения at once, so that a tenant
   renting an office, a warehouse and two parking spots is one договор as it is on paper.
2. As a сотрудник УК, I want each предмет to carry its own ставка, so that an office and a
   warehouse under one договор are not forced to the same rate.
3. As a сотрудник УК, I want each предмет to carry the площадь written in the договор, so that I
   can see what the tenant is actually billed for.
4. As a сотрудник УК, I want the договорная площадь kept separate from the помещение's площадь,
   so that a coefficient for МОП never becomes a physical fact about the building.
5. As a сотрудник УК, I want a договор to name помещения in more than one БЦ, so that a tenant
   with an office in Manhattan and a warehouse in Boston is not split into two records.
6. As a сотрудник УК, I want a договор naming a помещение of another организация to be rejected,
   so that a mistyped selection cannot cross a client boundary.
7. As a сотрудник УК, I want a помещение that is not арендопригодное to be refusable as предмет,
   so that a венткамера is not accidentally leased.

### Арендатор

8. As a сотрудник УК, I want the арендатор to be an existing Сторона, so that the same legal
   entity is not entered twice.
9. As a сотрудник УК, I want to see which Сторона rents a помещение from its карточка, so that I
   can go from a point on the план to a counterparty.
10. As a сотрудник УК, I want a Сторона to be арендатор only by virtue of a договор, so that
    «кто здесь арендатор» has exactly one answer.

### Сроки и история

11. As a сотрудник УК, I want a договор to have a start date and an optional end date, so that a
    бессрочный договор is representable without inventing an end.
12. As a сотрудник УК, I want an empty end date to read «по сей день», so that an open-ended
    договор is treated as in force rather than as never in force.
13. As a сотрудник УК, I want a договор overlapping an existing one on the same помещение to be
    rejected with an explanation, so that a помещение is never let twice for one day.
14. As a сотрудник УК, I want the rejection to name the помещение and the договор it conflicts
    with, so that I can find the record rather than guess.
15. As an администратор организации, I want to record досрочное расторжение with the date it
    actually happened, so that the договор does not appear to have ended on the day I opened the
    form.
16. As a сотрудник УК, I want пролонгация to create a new договор linked to the previous one, so
    that the rate history of a помещение survives.
17. As a сотрудник УК, I want an ended договор to be kept rather than deleted, so that «кто сидел
    здесь в прошлом году» has an answer.

### Слой «сроки договоров»

18. As a сотрудник УК, I want a слой that colours контуры by lease term, so that I can read the
    commercial state of a floor from the same drawing I read its layout from.
19. As a сотрудник УК, I want свободные помещения in their own colour, so that vacancy is visible
    spatially and not only as a number.
20. As a сотрудник УК, I want помещения whose договор expires within 90 days in their own colour,
    so that renewals surface before the tenant raises them.
21. As a сотрудник УК, I want МОП, технические помещения, шахты, лестничные клетки and проёмы
    outlined without fill on this слой, so that the drawing has no unexplained gaps and no
    помещение is coloured by a question it cannot answer.
22. As a сотрудник УК, I want to switch between тип помещения and сроки договоров, so that one
    план answers two different questions.
23. As a сотрудник УК, I want тип помещения to be the слой I get by default, so that the screen
    opens on the view computed from data that exists for every помещение.
24. As a сотрудник УК, I want the chosen слой in the address, so that I can send a colleague the
    exact view I am looking at.
25. As a сотрудник УК, I want a legend for this слой too, so that I never have to guess what a
    colour means.

### Вакансия

26. As a сотрудник УК, I want the floor screen to state how many арендопригодных помещений are
    free out of how many exist, so that I can judge a floor without counting contours.
27. As a сотрудник УК, I want the same count in м², so that I can answer «сколько метров
    простаивает» without a calculator.
28. As a сотрудник УК, I want vacancy м² taken from the паспорт's own обмер rather than from
    договоры, so that the number does not change with the coefficient in somebody's contract.
29. As a сотрудник УК, I want the same vacancy figure for the whole БЦ on its Карточка, so that I
    do not have to add five floors in my head.
30. As a сотрудник УК, I want the screen to say how many договоров it stands on, so that a
    building with no договоры reads as «не заведено» rather than as fully vacant.
31. As a сотрудник УК, I want to name the date the vacancy is computed for, so that I can ask
    what will be free in January.
32. As a сотрудник УК, I want the chosen date in the address, so that «третий этаж, сроки, на 1
    января» is a link I can send.
33. As a сотрудник УК, I want to be told when the chosen date falls outside the период of the
    план on screen, so that I am not shown today's drawing with a future tenant silently.

### Ведение договоров

34. As an администратор организации, I want a Список договоров screen, so that a договор that
    belongs to no building still has a place to be found.
35. As an администратор организации, I want to create a договор from that screen, so that
    maintaining leases does not require Django admin.
36. As an администратор организации, I want to add several помещения to one договор in the form,
    so that entering a real договор is one action.
37. As an администратор организации, I want to correct a договор I entered wrongly, so that a
    typo does not require a platform administrator.
38. As an администратор организации, I want to delete a договор entered by mistake, so that an
    input error does not become part of the building's history.
39. As a сотрудник УК without administrator rights, I want no create, edit or delete controls
    shown to me, so that I am not offered actions I cannot take.
40. As an администратор организации, I want the номер, дата подписания and ставка to be optional,
    so that I can enter a договор I hold before I hold every detail of it.

### Доступ и изоляция

41. As a сотрудник УК, I want договоры of another организация to be invisible to me, so that the
    isolation ADR 0001 established covers leases too.
42. As a сотрудник УК, I want a договор of another организация to behave exactly like a договор
    that does not exist, so that the response cannot confirm another client's data.
43. As an anonymous visitor, I want to be redirected to login when requesting any lease screen,
    so that nothing about our clients' tenants is visible without a session.
44. As a разработчик holding a superuser account, I want to see every организация's договоры, so
    that I can reproduce a client's problem without granting myself their membership.

### Пустые состояния

45. As a сотрудник УК, I want a floor with no договоры at all to say so, so that «свободно 44 из
    44» is never read as a measured fact.
46. As a сотрудник УК, I want the Список договоров to explain itself when empty, so that a new
    client sees where to start rather than a blank table.
47. As a сотрудник УК, I want a помещение with no договор to say «— нет данных» in its карточка
    rather than showing an empty tenant row, so that absence reads as absence.
48. As a сотрудник УК, I want the four БЦ with no interior to keep their existing «не загружено»
    treatment, so that nothing about this stage changes what they already do.

## Implementation Decisions

### Domain model

- **Договор аренды** is its own entity: `org`, арендатор (FK to `Party`), период
  (`valid_from` / `valid_to`), optional номер and дата подписания, and an optional link to the
  договор it prolongs. It is **not** a `Document` — see **ADR 0006**. `DocumentLink.EntityType`
  gains a lease member so the scan can be filed against it; it has none today.
- **Предмет договора** is the join: (договор, помещение) with its own ставка and договорная
  площадь. A договор has one or more. Both money fields are optional.
- A предмет may name **only an арендопригодное помещение** of the договор's own организация.
  Cross-организация предмет is rejected — **ADR 0009**.
- **Nested арендопригодные помещения are independent.** 17 of the 44 sit inside another
  арендопригодное, and letting the parent does **not** let the children. The hierarchy carries
  two different relations (containment and grouping, per the glossary), and a rule that reads
  occupancy out of the tree would be right for one of them and silently wrong for the other. The
  cost is accepted: a тамбур and the office behind it can be let to different tenants and the
  system will not object. That is an allowable foolishness, not corrupted data.
- **Арендатор lives on the договор**, and `PartyRole.tenant` is removed from choices — **ADR
  0008**. `PartyRole` holds 0 rows, so nothing is migrated. The rest of `PartyRole` is left
  exactly as it is.
- **Ставка and договорная площадь never write to `Space.area_m2` or `SpaceArea`.**
  `SpaceArea.Source.LEASE` stays in place and stays unwritten by any automatic path; it remains
  for the manual case where no обмер exists at all.
- The terms are defined in the glossary: **Договор аренды**, **Предмет договора**, **Сданное
  помещение**, **Свободное помещение**, **Пролонгация**, **Ставка**, a rewritten
  **Арендопригодное помещение** (property of the помещение, not its current state) and a
  rewritten **Сторона** (no tenant role of its own).

### Периоды и правила

- Periods **include both ends**; an empty `valid_to` means «по сей день». Identical to `FloorPlan`
  and for the identical reason — **ADR 0004**, extended in **ADR 0007**.
- **Overlap is checked per помещение, not per договор**: a договор on three помещения may conflict
  on exactly one of them, and the rejection names which.
- The check lives **on the model**, not on the form, so admin, the new form and any script hit the
  same refusal. SQLite cannot express range exclusion; on PostgreSQL a constraint is added under
  it, not instead of it. Same reasoning as ADR 0004, unchanged.
- **Пролонгация is a new договор** carrying a FK to its predecessor. Nothing computes the chain's
  total duration in this stage.
- **Расторжение** sets `valid_to` to a date the user states. It is never derived from the day the
  form was opened — the invented-fact argument from ADR 0004.
- Required: арендатор, дата начала, at least one предмет. Номер, дата подписания, ставка and
  договорная площадь are all optional and render as «— нет данных», per stage 1.

### Слой «сроки договоров»

- `SpaceTypeLayer` today exposes `paint_of(space)`, which sees **only the помещение**. The lease
  слой needs a date and the договоры in force on it, so the layer protocol widens: a слой is
  constructed with what it needs and then answers `apply(contours)`. `SpaceTypeLayer` keeps its
  behaviour. This is the expected cost of the second слой, not a defect in the first.
- Three paints: **Свободно**, **Действует**, **Истекает** (в течение 90 дней). МОП, технические,
  `void`, `shaft` and `stairwell` are **outside the слой** — outline, no fill, no legend entry —
  exactly as `void`/`shaft`/`stairwell` already are on the тип слой. A МОП has no lease state and
  colouring it would answer a question it was never asked.
- **90 days is a named constant with its reason in a comment**: renewal negotiations in commercial
  leasing start about a quarter out. Undocumented, the next reader changes it to 30 for no reason.
- **No fourth «неизвестно» colour.** `plan_layer.py` already settled this: a colour speaks about
  the building, not about the completeness of the data. The completeness statement lives beside
  the count instead, exactly as stage 2's «нанесено 47 из 82» does.
- Слой by default is **тип помещения**, computed from data present on every помещение. Opening on
  сроки would greet the user with 44 помещения painted «свободно» on the strength of zero
  договоров.
- Слой and date are **address parameters**. Remembering the user's last choice is rejected: it is
  invisible state that makes two people looking at «the same screen» see different things.

### Вакансия

- Counted **in помещения and in м²**: «свободно 12 из 44 помещений, 387 из 1529 м²». Stage 2
  forbade м² for coverage because 35 помещения have no `area_m2` and the план declares no scale.
  Neither objection applies here: **all 44 арендопригодных помещения have an area**, and vacancy
  is computed from `Space.area_m2`, not from the план.
- **Double counting does not arise.** All 11 арендопригодных parents that contain another
  арендопригодное have their own non-zero area — they are grouping parents in the sense stage 2's
  spec recorded, and their area is their own part of the floor. Every containment case (the eight
  уборные, area 0.0, кабины inside) is МОП and never enters the count.
- м² come from the **паспорт's обмер**, never from договорная площадь. The two differ on purpose —
  ADR 0006.
- Shown on the **floor screen** beside «нанесено N из M», and on the **Карточка БЦ** for the whole
  building. Not on the Список БЦ: four of the five БЦ have no interior at all, and the column
  would be a column of dashes.
- Beside the count, **the number of договоров it stands on**. With zero договоры the floor reads
  «свободно 44 из 44 — договоров не заведено ни одного».
- Vacancy is computed **as of a date**, today by default. Where the chosen date falls outside the
  период of the план being rendered, the screen says so. The план on screen is always the план in
  force **today**; the two time axes are not merged, and mixing them silently would produce a
  drawing from one period with tenants from another.

### Screens and routing

- Two new routes: `/leases/` (Список договоров, with the form) and `/leases/<uuid>/` (карточка
  договора). The договор belongs to no БЦ (ADR 0009), so it is not nested under one.
- The floor route gains `?layer=` and `?date=`.
- **Карточка помещения** gains арендатор, срок and ставка with a link to the договор, or «— нет
  данных». No new sections for документы or системы — those tables are still empty.
- **Карточка БЦ** gains the vacancy figure. The Этажи section is unchanged.
- Server-rendered Django templates, Tailwind + daisyUI, HTMX and Alpine — the stage 1/2 stack
  unchanged. No API endpoints. Interface language is Russian, using glossary terms.

### Access control

- **A third chokepoint** beside `visible_to` and `administered_by`, built on the same pattern:
  filtering in one place, not in each view. Договоры are scoped by their own `org` — **ADR 0009**,
  which records why this deviates from `FloorPlan` having no `org`.
- Write rights come from **`OrgMembership.is_admin`**, the flag introduced in ADR 0005. Create,
  edit and delete are all administrator actions; nothing new is invented for leases.
- Another организация's договор returns **404**, matching how a БЦ outside the организация already
  behaves.
- Delete is a real delete. Аннулирование as a separate state is rejected: a расторгнутый договор
  is a fact of the building's history and must stay (ADR 0007), while a typo is not a fact at all,
  and keeping it would pollute exactly the history that ADR forbids editing in place. `CommonModel`
  already records who touched a row and when.

### Seed data

- Ten fictional арендаторы are added as a **new seeding file beside `party.csv`**, clearly marked
  as наполнение. The existing 699 Стороны are **not** relabelled: «Центр крепежных систем ТОО» is a
  real supplier from a real counterparty list, and making it a tenant would put a lie into data
  somebody will later read as true.
- Their договоры spread across Manhattan's арендопригодные помещения so that all three paints
  appear: several in force, one or two expiring inside 90 days, one already ended, and a number of
  помещения deliberately left free.

### Explicitly not changed

- **The ИИ-управляющий panel is untouched** and keeps its fixed reply, as through stages 1 and 2.
- **`Space.valid_from` / `valid_to` stay unused.** Versioning помещения was rejected in ADR 0003
  and a lease is exactly one of the references that rejection was protecting.
- **`PartyRole` beyond the removed `tenant` choice**, and the four party columns on
  `BuildingPassport`, are left as they are. The glossary/code divergence on owner and operator
  roles remains open; this stage neither fixes nor worsens it.
- **Stage 2's слой «тип помещения»** keeps its behaviour and stays the default.

## Testing Decisions

### What makes a good test here

Tests exercise what a user can observe over HTTP: which договоры a user can reach, what the
vacancy count says, whether an overlapping договор is refused. They do not assert markup, CSS
classes or colour values — those change on every design pass and prove nothing. This continues
the seam stages 1 and 2 established rather than adding to it.

### Seams

**This stage adds no seam.** The HTTP boundary carries all of it, via `pytest-django`'s client
against named URLs, authenticated as users with known `OrgMembership` rows.

Both candidates for a unit seam were considered and rejected. **The overlap rule** and **the
vacancy computation** are pure functions of dates and rows, and calling them directly would
shorten the arrange step of perhaps a dozen tests. That is the test author's convenience, not a
property of the behaviour: vacancy exists only as a line on a screen, and a refusal exists only
as a response to a form, so both are fully observable from outside. The precedent that might
seem to license a second seam does not transfer. Stage 2 gave the SVG parser its own seam
because its interesting cases are malformed and adversarial **files** — a missing `viewBox`, a
duplicate `id` — and expressing those as uploads would have turned the HTTP suite into a
file-fixture factory. Аренда has no file, no parse and no adversarial input; it has dates. The
слой gets no seam either, exactly as stage 2's слой does not.

The cost is accepted and named: a boundary case such as «договор starting on the day another
ends» arranges two договоры through fixtures rather than one function call, and a failure reads
«the screen said the wrong thing» rather than «the function returned the wrong thing». For a
dozen tests that is worth keeping the project at one seam.

### Prior art

The suite to imitate already exists — 2872 lines of it, almost entirely over HTTP:

- **`test_plan_upload.py`** is the closest model for the договор form: authorisation by
  `is_admin`, direct POST by a member without the flag, rejection with an explanation, and the
  rejected form re-rendered. The lease form's tests are the same shapes with different fields.
- **`test_floor_plan.py`** is the model for the слой and for anything read off the floor screen,
  including its treatment of what is and is not drawn.
- **`test_scoping.py`** and the tenancy tests in `test_bc_detail.py` are the model for 404
  rather than 403, for the superuser bypass and for the anonymous redirect.
- **`conftest.py`** already provides everything the fixtures need: `make_org`, `downtown`,
  `central` (the second client, which exists for isolation tests), `member`, `manhattan`,
  `make_floor`, `make_space`, `first_floor`. It gains factories for Сторона, договор and
  предмет; nothing existing changes.
- Test names are **sentences**, as throughout the suite — `test_the_file_of_another_organisations
  _plan_is_missing_rather_than_forbidden` is the register.

### Coverage

- **Overlap** — a договор starting on the day another ends is rejected; an open-ended договор
  blocks everything after its start; a договор conflicting on one помещение of three is rejected
  and names that помещение; non-overlapping договоры on the same помещение are accepted. Driven
  through the form, so the model rule and the path that reaches it are proven together.
- **Vacancy** — with no договоры the floor reports all 44 free; a договор in force removes its
  помещения from the count; a договор that ended yesterday does not; a future `?date=` moves a
  помещение from сдано to свободно; nested арендопригодные are counted independently and м² are
  not double counted. Read off the floor screen, where the figures are text.
- **Vacancy agreement** — the floor and the Карточка БЦ report figures that add up, and both
  state the number of договоров they stand on.
- **Date outside the план's период** — the floor screen says so rather than rendering silently.
- **Слой** — the floor screen with `?layer=` renders the lease слой; МОП and технические помещения
  receive no fill on it; the default without the parameter is тип помещения.
- **Tenancy** — a user of one организация gets 404 for another's договор and does not see it in
  the Список договоров; a superuser reaches every организация's договоры; anonymous requests
  redirect to login.
- **Cross-организация предмет** — a договор naming a помещение of another организация is rejected.
- **Write authorisation** — a member without `is_admin` can neither create, edit nor delete; one
  with it can do all three.
- **Optional fields** — a договор with no номер, no дата подписания and no ставка saves, and the
  карточка помещения renders «— нет данных» for the rate.
- **Пролонгация** — a new договор linked to a prior one saves without overlapping it, and the
  prior one remains readable with its own ставка.
- **Smoke** — 200 from the Список договоров, from a договор card, and from a floor with договоры.

### Deliberately untested

Слой colour values are not asserted, per stage 2 — only which помещения the слой places in which
band, and which it leaves outside itself. The 90-day threshold is asserted at its boundary as a
change in that band, not as a colour on a page. Пролонгация chains are not walked transitively:
nothing in this stage computes over a chain, so there is nothing to assert. Client-side behaviour
— switching слой without a reload, the date control — is untested for the same reason stage 2 left
bidirectional highlighting untested: it has no HTTP observable, and testing it would mean adding a
browser-driving seam for one interaction.

## Out of Scope

- **Слой «долги арендаторов».** It needs начисления and оплаты, which ADR 0006 places outside
  BCMP. Of the four слои the glossary promises, this stage pays the second.
- **Начисления, оплаты, задолженность, акты сверки, счета.** The accounting system runs three
  legal entities and remains the single source of truth for money.
- **Импорт договоров из учётной системы.** No integration exists, and building one for the предмет
  alone costs more than the form.
- **Субаренда.** A subtenant is a relation between the арендатор and a third party, not a second
  договор on the помещение. If it is ever needed, it sits on top of the договор and the overlap
  rule does not obstruct it.
- **Почасовая аренда переговорных.** A service, not a lease; BCMP has no notion of it.
- **Экран арендатора** — everything a Сторона rents across all зданий. It is a second view of the
  Список договоров filtered by Сторона, and cheaper to add once the list exists.
- **Vacancy on the Список БЦ.** Four of five БЦ have no interior; the column would be dashes.
- **Слияние и деление помещений.** BCMP has no operation for it at all, and a договор on a
  помещение that genuinely disappears will dangle. Building space merging for the sake of leases
  is the wrong order; the gap is recorded, not closed.
- **Машиноместа.** `DictSpaceType.PARKING_SPOT` exists and **0 rows use it**. The model supports
  them as предмет the moment any are entered; none are.
- **Editing помещения** — the space tree stays read-only, unchanged from stage 2.
- **Договорная площадь filling `SpaceArea`.** Explicitly rejected in ADR 0006.
- **Migrating from SQLite to PostgreSQL**, unchanged from stages 1 and 2.

## Further Notes

The state of the data this ships against:

- **44 of 82 помещения are `is_leasable`, totalling 1528.92 м².** Every one of them has both an
  `area_m2` and a контур — 0 exceptions on either count. The 35 помещения with no площадь and the
  7 with no контур are all МОП or технические, and none of them enters vacancy.
- **17 of the 44 sit inside another арендопригодное**, under 11 parents. All 11 have their own
  non-zero area, so all 11 are grouping parents and summing areas does not double count. Stage 2's
  spec recorded the same split for the floor as a whole (eleven grouping, eight containment); the
  containment cases are the уборные, which are МОП.
- **699 Стороны, all поставщики**, across three `date_base` values — `DOWNTOWN MANAGEMENT` (637),
  `Asset-Asia` (51), `CO-PROSTRANSTVO` (11). Not one tenant among them.
- **`PartyRole`: 0 rows**, referenced only by its admin registration.
- **`Document`: 0 rows; `SpaceArea`: 0 rows; `SpaceCodeHistory`: 0 rows.**
- **Only Manhattan has an interior.** Boston, Dubai, Geneva and Tokyo have a паспорт and nothing
  inside, so this stage, like stage 2, has exactly one building to prove itself on.

A defect found while specifying this stage and filed separately: **`scripts/populate_data/
area_kind.csv` contains buildings** (`Downtown Manhattan`, `Downtown Boston`, …) instead of kinds
of area, which is why `DictAreaKind` is empty and `SpaceArea` has never been populated. It does not
block this stage — nothing here writes `SpaceArea` — but it needs fixing before any обмер data is
loaded.

The modelling gaps stage 1 and 2 recorded remain open: `BuildingSystem.building` is a single FK and
cannot express a system serving several БЦ, and `Asset` still does not exist behind `AssetLink`,
`AssetServesZone` and `AssetServesSpace`.

The decisions this stage turns on are **ADR 0006** (договор — сущность, а не документ; деньги вне
BCMP), **ADR 0007** (периоды не пересекаются, пролонгация — новый договор), **ADR 0008** (арендатор
живёт на договоре) and **ADR 0009** (у договора есть своя организация). Tenancy follows **ADR 0001**
and **ADR 0005**; the план this stage colours follows **ADR 0003** and **ADR 0004**. The vocabulary
is defined in the project glossary.
