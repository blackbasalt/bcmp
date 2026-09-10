# Стороны — кто вокруг бизнес-центров и что о них знает управляющая компания

## Problem Statement

BCMP holds 699 Сторон and shows them nowhere. `parties/views.py` is the three-line Django
stub; the app has no `urls.py`, is not mounted in `bcmp/urls.py`, and `templates/parties/`
does not exist. Outside the Django admin a Сторона appears only as somebody else's field: a
name in the «Кем выдан» column, a name on the паспорт of a БЦ, a name on an аренда row.

So the questions a сотрудник УК arrives with have no screen to be asked on:

- «Какой у «Центра крепежных систем» расчётный счёт» — nowhere. The `contacts` JSONField on
  `Party` has existed for three stages and is empty in all 699 rows.
- «Кому звонить в ТОО «Альфа» по вентиляции» — nowhere. There is no notion of a person
  inside a company at all.
- «Кого поздравить на этой неделе» — nowhere, and this one is not even a passport question:
  it is the УК's relationship with its арендаторы, and no other system in their stack holds
  it either.
- «Кто из наших арендаторов сидит в Tokyo» — the полка помещений answers it room by room;
  there is no screen that answers it Стороной.

Underneath that sits a harder problem. Every other полка is isolated by организация at a
chokepoint — `visible_to` on `Space`, on `Document`, inherited from the помещение for an
аренда (ADR 0001, 0006, 0018). A Сторона belongs to nobody: `Party` has no `org` column, on
purpose, so that an арендатор nobody has met yet stays findable when an аренда is entered
(`leases/party_choice.py`). The третья полка is the first one whose isolation does not come
for free.

And the source data already knows the answer. `scripts/populate_data/party.csv` carries a
`date_base` column — 637 rows «ТОО «DOWNTOWN MANAGEMENT»», 51 «Asset-Asia ТОО», 11
«ТОО «CO-PROSTRANSTVO»» — and the loader throws it away.

## Solution

**Сторона is split in two.** What the Сторона *is* — название, БИН/ИИН, юрлицо/физлицо,
сфера деятельности — stays one row for the whole system, searchable by anyone entering an
аренда. What an организация *knows about it* — платёжные реквизиты, контактные лица, поводы
— lives in an **учётная карточка** on the pair «Сторона + организация» (ADR 0020).

**Полка Сторон is a полка учётных карточек.** A Сторона is on my shelf because my
организация has a карточка on it, not because it has an аренда or a роль. The rule that
would derive the shelf from связи gives the УК an empty screen while 637 of those Стороны
are its own suppliers: 0 rows in `PartyRole`, 35 аренды, 699 Сторон.

**Поздравления get their own mechanics without entering the паспорт.** A **повод** is a day
of the year, recurring and endless. The personal one — a birthday — is stored: on the
контактное лицо for a юрлицо, on the учётная карточка itself for a физлицо. The professional
one is derived from the сфера деятельности and a shipped calendar of Kazakh professional
holidays, and stored nowhere (ADR 0023, 0027). «Кого поздравить на этой неделе» is a
condition of the отбор, not a screen.

**The line against money moves one step and stops.** Where to pay — банк, БИК, счёт, КБе —
is held, because it is not a величина and does not change with postings. How much was paid
is still not held. Bank licence revocations are not tracked, because there is nothing to
track them from (ADR 0022).

**The right to write is graded by the radius of the act** (ADR 0021, 0028). Enter a Сторона —
yes, the БИН is free. Edit its shared half — only while your организация is the only one with
a карточка on it. Delete the карточка — yes, finally, in two steps. Delete the Сторона — no.

## User Stories

### Что общее и что частное

1. As a сотрудник УК, I want a Сторона to be one row per БИН for the whole system, so that
   the identifier keeps answering «кто это» and an арендатор nobody has met is findable.
2. As a сотрудник УК, I want платёжные реквизиты, контактные лица and поводы to be mine
   alone, so that the phone number I wrote down is not shown to another управляющая компания
   that happens to work with the same юрлицо.
3. As a сотрудник УК, I want сфера деятельности to sit on the Сторона itself, so that one
   public fact does not acquire 637 diverging opinions and the вывод повода keeps working.
4. As a сотрудник УК, I want a Сторона with no карточка of mine to stay out of my полка, so
   that the 62 Стороны loaded from other bases do not fill my screen.

### Полка Сторон

5. As a сотрудник УК, I want a раздел «Стороны» beside «Бизнес-центры», «Документы» and
   «Помещения», so that the question «с кем мы имеем дело» has an address of its own.
6. As a сотрудник УК, I want the rows to carry **Название · БИН/ИИН · Сфера деятельности ·
   Арендует N помещений · Ближайший повод**, so that the shelf answers without opening
   anything.
7. As a сотрудник УК, I want «Арендует N помещений» counted in помещения and never in метры,
   so that a Сторона sitting in a помещение inside another помещение is not counted twice
   (ADR 0015, 0019).
8. As a сотрудник УК handling two clients, I want an «Организация» column, so that I know
   whose shelf I am looking at — and I want it even when the second client has nothing
   loaded, which is exactly when I most need it.
9. As a сотрудник УК, I want the count line «Показано 12 из 637 Сторон», so that a narrowed
   shelf says how much it hid.
10. As a сотрудник УК whose организация has no Стороны at all, I want «Стороны не заведены»
    rather than «ничего не нашлось», so that I am not sent to fix a question that was never
    the problem.

### Отбор

11. As a сотрудник УК, I want to search by название and by БИН in one field, case folded, so
    that «крепеж» and «КРЕПЕЖ» find the same row (ADR 0014).
12. As a сотрудник УК, I want to narrow by сфера деятельности, so that «все наши строители»
    is one click.
13. As a сотрудник УК, I want to narrow by юрлицо / физлицо, so that ИП and ТОО are told
    apart when that matters.
14. As a сотрудник УК, I want a condition «только арендаторы» — those with an аренда in force
    today — so that the shelf separates who pays us from whom we pay.
15. As a сотрудник УК, I want to narrow by БЦ, so that «кто сидит в Tokyo» is answerable
    Стороной. The condition works through an аренда in force today, so поставщики fall out of
    it entirely — which is the honest answer, since a поставщик is tied to no building.
16. As a сотрудник УК, I want a condition «повод: на этой неделе / в этом месяце / в
    ближайшие 90 дней», so that «кого поздравить» is the shelf answering, not a separate
    screen. A free number of days would invite 0 and 3650.
17. As a сотрудник УК, I want the отбор to live in the address, so that a narrowed полка can
    be reloaded, kept in a tab and sent to a colleague, and so that clearing it is the
    address without it.
18. As a сотрудник УК, I want a condition that does not read to narrow the shelf to nothing
    rather than be dropped, so that the screen never states an отбор it did not perform
    (ADR 0014).

### Экран Стороны

19. As a сотрудник УК, I want the Сторона to have its own address and its own screen, so that
    what we know about a контрагент is not a rail of somebody else's page.
20. As a сотрудник УК, I want a header with название, БИН/ИИН, юрлицо/физлицо and сфера
    деятельности, so that identity is settled before anything else is read.
21. As a сотрудник УК, I want the платёжные реквизиты listed with the основной first, so that
    the usual case is answered without unfolding anything.
22. As a сотрудник УК, I want the контактные лица listed with имя, должность, телефон, почта
    and день рождения, so that «кому звонить» and «кого поздравить» are one list.
23. As a сотрудник УК, I want the Сторона's аренды listed — помещение, БЦ, метры, срок — so
    that «где сидит ТОО «Альфа»» is answered from her side of the relationship.
24. As a сотрудник УК, I want those аренды **not** totalled, so that a number inflated by
    nested помещения is never quoted (ADR 0019).
25. As a сотрудник УК, I want the документы where she is «Кем выдан», so that her paper trail
    is reachable from her.
26. As a сотрудник УК, I want **no «Роли» section at all** while `PartyRole` holds zero rows
    and no reader, so that an always-empty block does not teach me that Стороны have no
    роли.

### Платёжные реквизиты

27. As a сотрудник УК, I want several комплекта on one учётная карточка, so that a счёт in
    тенге and a счёт in валюте live together.
28. As a сотрудник УК, I want the old счёт to stay when the bank changes, so that a платёжка
    written the day before yesterday still agrees with the screen.
29. As a сотрудник УК, I want one комплект marked основным, so that the screen knows what to
    show on one line.
30. As a сотрудник УК, I want to pick the банк from a справочник by БИК, so that «Каспи» and
    «Kaspi Bank» are one bank.
31. As a сотрудник УК, I want the справочник to say **nothing** about licences, so that a
    revoked licence is never shown as valid a year from now (ADR 0022).

### Контактные лица и поводы

32. As a сотрудник УК, I want a контактное лицо to belong to my учётная карточка, so that the
    director's mobile number I was given is not shared with anybody else.
33. As a сотрудник УК, I want a контактное лицо **not** to be a Сторона, so that a director
    does not appear in the same list as his own ТОО and is not asked for a БИН.
34. As a сотрудник УК, I want the same human registered as an ИП to be a separate Сторона, so
    that the ИП can end while the person stays.
35. As a сотрудник УК, I want контактные лица only on a юрлицо, so that a физлицо is not made
    its own representative.
36. As a сотрудник УК, I want a физлицо's день рождения on the карточка itself, so that the
    личный повод still exists where there is nobody to hang it on.
37. As a сотрудник УК, I want the профессиональный повод derived from the сфера деятельности
    and never typed in, so that «День строителя» is not three different days at three
    арендаторов of one floor.
38. As a сотрудник УК, I want the праздник stored as a **rule** — «второе воскресенье
    августа» or «число и месяц» — so that no year goes quietly unfilled (ADR 0027).
39. As a сотрудник УК, I want the calendar of профессиональные праздники shipped with the
    system, so that three управляющие компании do not keep three different Дня строителя.

### Заведение, правка, удаление

40. As an администратор организации, I want to enter a Сторона myself, so that a new
    поставщик does not require a call to support.
41. As an администратор организации, I want the БИН/ИИН required on the form, so that «ТОО
    «Альфа»» is not entered twice — all 699 real rows carry one, twelve digits, no gaps and
    no duplicates.
42. As an администратор организации, I want to be told that a Сторона with this БИН already
    exists, so that I do not create a duplicate — accepting that this tells me one bit about
    another client's world and nothing more (ADR 0021).
43. As an администратор организации, I want to edit the shared half only while mine is the
    only карточка on that Сторона, so that renaming «АО «Kaspi Bank»» never changes somebody
    else's screens (ADR 0028).
44. As an администратор организации, I want to maintain my own учётная карточка always, so
    that phones, счета and дни рождения stay current.
45. As an администратор организации, I want to delete the учётная карточка — finally, in two
    steps, the question asked by the application and not by the browser — so that a Сторона
    entered by mistake is undone whole (ADR 0013).
46. As an администратор организации, I want deleting the карточка **not** to delete the
    Сторона, so that a freed БИН does not become a юрлицо without a past.
47. As a сотрудник без флага администратора, I want no forms shown to me at all, so that a
    displayed form refusing my submission does not read as a broken screen.

### Доступ и изоляция

48. As a сотрудник УК, I want a Сторона whose карточка is not mine to answer 404 on her
    address, so that the absence of another client's data is indistinguishable from absence
    (ADR 0006).
49. As a сотрудник УК, I want the search that picks a Сторона on the форма аренды to stay
    system-wide, so that a new арендатор is still findable — the argument in
    `leases/party_choice.py` survives the split unchanged; only its last sentence does not.
50. As a сотрудник УК, I want «Кем выдан» on the document form narrowed to Стороны of my
    учётная карточка, so that a `<select>` of 699 rows becomes a list I can hit (ADR 0020).

### Язык

51. As a developer, I want the screen to say **Стороны** and never «Контрагенты», so that the
    accounting-system word does not drag its meaning — сальдо, взаиморасчёты — onto a passport
    screen. `CONTEXT.md` lists «контрагент» under _Избегать_.
52. As a developer, I want «учётная карточка» to mean the data and «экран» to mean the page,
    so that the two do not slip into each other in prose.
53. As a developer, I want «платёжные реквизиты» and not «реквизиты», so that the block on the
    document screen — which means that document's particulars — keeps its word.

## Implementation Decisions

### No new app: `parties` already is one

ADR 0016 made a раздел a Django app because `templates/shell.html` computes the open раздел
as `request.resolver_match.app_name`. `parties` exists, holds `Party`, `Org`, `OrgMembership`
and `PartyRole`, and simply has no urls yet. It gets `urls.py` with `app_name = "parties"`,
mounted at `parties/` in `bcmp/urls.py`, and a fourth `_sidebar_item.html` in the nav.

Two routes, mirroring `documents`:

- `""` → `PartyListView` (`party_list`) — the полка.
- `"<uuid:pk>/"` → `PartyDetailView` (`party_detail`) — the экран. No организация in the
  address, exactly as a document's address carries no building.

### The models

**`PartyRecord`** — the учётная карточка. FK to `Party` (`related_name="records"`), FK to
`Org`, `UniqueConstraint(fields=["party", "org"])`. Nothing else: it is the pair, and
everything hangs off it. Named `PartyRecord` and not `PartyDossier` because «досье» is listed
under _Избегать_ in the glossary; the screen-word «карточка» is deliberately not in the model
name either.

**`ContactPerson`** — FK to `PartyRecord` (`related_name="contacts"`), `full_name`,
`position` (free text — a справочник of должности would be a dictionary of one client's
habits), `phone`, `email`, `born_on` (nullable date).

**`PaymentDetails`** — FK to `PartyRecord` (`related_name="payment_details"`), FK to
`DictBank`, `account` (IBAN/счёт), `kbe`, `is_primary`. Several per карточка; the основной is
a flag rather than a pointer on the карточка, because the карточка should not have to be
written when a счёт is closed.

`Party` gains `line_of_business` (FK to `DictLineOfBusiness`, nullable) and, for a физлицо,
nothing: the born-on of a физлицо lives on `PartyRecord.born_on`, because it is personal data
and must not be visible to a second организация (ADR 0020, 0023).

`Party.contacts` is **dropped** by migration. It is empty in all 699 rows, and left beside
`ContactPerson` it would collect a second copy of the phone numbers — the second truth this
project keeps refusing. `Party.kind` is **kept and repaired**: the loader maps only «ФЛ» to
`person`, so all 5 ИП are recorded as companies. Unlike `contacts`, `kind` is not empty — it
was merely never asked, and this screen asks it: it decides whether the контактные лица block
exists at all and where the день рождения hangs.

**No ОПФ field** (ADR 0025). It is already the suffix of the name.

### Три справочника

All three follow `DictionaryCommonModel` in the `dictionary` app and ship as fixtures.

- **`DictBank`** — БИК and название, and nothing else. The licence columns of `bank.csv` are
  not carried over (ADR 0022).
- **`DictLineOfBusiness`** — about 25 отрасли, built from the calendar rather than from ОКЭД
  (ADR 0024).
- **`DictProfessionalHoliday`** — FK to `DictLineOfBusiness`, and a rule in two shapes: either
  (`day`, `month`) or (`week_of_month`, `weekday`, `month`). Exactly one filled, enforced by a
  `CheckConstraint`. No year column anywhere (ADR 0027).

### Повод — одно правило, две формы

A module `parties/occasions.py`, the shape `leases/occupancy.py` already has: one rule, handed
out in the two shapes the two screens need.

- `nearest_for_each_record(records, on)` — one query for the whole полка, the way
  `tenants_of_each_room` is one query for the whole полка помещений. Never per row.
- `occasions_of(record, on)` — the list for one экран.

Both fold together the stored личные поводы and the derived профессиональный, resolve the
rule to a date in the year being asked about, and sort by how soon. The derived one is
computed and never written; there is no `Occasion` table.

### Что выносится из `ShelfSearch`

Three pieces, and only three. The отбор bar stays a third handwritten template: the docstring
of `_room_search.html` says why the two existing ones were not merged, and nothing here
weakens it.

1. `asked` — what tells «ничего не нашлось» from «ничего не заведено».
2. The opening of `narrow` — `if not self.is_valid(): return queryset.none()` (ADR 0014).
3. `BuildingChoice`, already shared between three forms, now four.

The first two go to **`bcmp/shelf.py`**, not into a domain app. `BuildingChoice` belongs to
`documents` because it is about a domain field; `asked` and the guard are about what a полка
*is*, and belong to no раздел. Copied a third time they would drift, and drift silently: a
полка that quietly dropped an unreadable condition looks like it is working.

The полка Сторон follows **rooms and not documents** on the empty state: which of the two
messages is shown is decided by the size of the un-narrowed shelf (`whole`), not by whether
anything was asked. A reader whose организация has nothing loaded must not be sent to fix a
question that was never the problem.

### Правки в существующем коде

- `leases/party_choice.py` — the search stays system-wide; only the sentence «Сторона не
  принадлежит никакому клиенту» is rewritten: it is the учётная карточка that belongs to a
  client, not the Сторона.
- `documents/document_edit.py` — `issuer_party` is narrowed to Стороны of the reader's учётная
  карточка, and gains the same search the lease form uses. Its comment said the project had no
  first answer to «чьи это подрядчики»; now it has one.
- `parties/models.py` — a `PartyRecordQuerySet.visible_to(user)` chokepoint of the same shape
  as `SpaceQuerySet.visible_to` and `DocumentQuerySet.visible_to`, and
  `administered_by(user)` beside it. Both shelves' contract holds here too: the chokepoint
  first, `narrow` after it, never instead.

### Наполнение

`scripts/load_real_data.py` fills `PartyRecord` from the `date_base` column: 637 rows to
DownTown Management. The 51 «Asset-Asia ТОО» and 11 «CO-PROSTRANSTVO» rows load as Стороны
**without** a карточка — no such организация exists in the system — and stay findable in the
registry (ADR 0020). Note that Asset-Asia appears as an арендодатель on 14 lease rows, which
is a role on an аренда and does not make it an организация.

Аренды whose арендатор is not in the registry are skipped with a report, not a `print`
(ADR 0026): 235 of 271 rows, all of Tokyo and all of Boston. And the seed goes back to
deleting only its own — `Party.objects.all().delete()` and `Lease.objects.all().delete()`
override the `FILLING_MARK` rule that `fill_leases` was written around.

### Glossary

Five terms were added to `CONTEXT.md` during design — **Учётная карточка**, **Контактное
лицо**, **Платёжные реквизиты**, **Сфера деятельности**, **Повод** — and **Сторона** and
**Полка** were amended. Nine ADRs, 0020–0028, hold the decisions.

## Testing Decisions

A good test here checks what is observable at the HTTP boundary: which Стороны are on the
screen, what a row says, what the count line says, what status code comes back, and what is
left in the database after a refusal. It does not reach into `occasions.py`, the form class or
the query that built the page.

**Three seams, two of them new:**

1. **`parties:party_list`** — rows, columns, the count line, all six conditions, both empty
   states, the reset link, and the isolation. Prior art: `rooms/test_shelf.py` and
   `rooms/test_search.py`, whose `ROW`/`CELL` regexes over `data-room` are reused as they
   stand over `data-party`.
2. **`parties:party_detail`** — the five sections, the absence of a «Роли» section, the
   absence of totals on the аренды, 404 for a Сторона whose карточка is not the reader's, and
   every write: заведение, правка, удаление карточки, and the freeze on the shared half.
   Prior art: `documents/test_document_page.py` and `documents/test_deletion.py`.
3. **`documents:document_detail`** — that «Кем выдан» is now narrowed. One test in the
   existing suite, not a new file.

**Footholds in the markup.** `data-party` on each row, `data-search="parties"`,
`data-count="parties"`, `data-section` on the five blocks, `data-contact` and `data-payment`
on their rows — mirroring `data-room`, `data-document` and `data-lease`.

**No fourth seam.** `occasions.py` gets no tests of its own, exactly as `space_kind`,
`plan_completeness` and `occupancy` have none: it is read by two screens and both check it. A
direct test would be a second account of one rule, and the two would eventually disagree.

**One test that is not about a screen**: that `bcmp/shelf.py` is what all three полки use — by
asserting the behaviour on each of them, not by testing the base class in isolation.

## Out of Scope

- **Деньги.** No начисления, no оплаты, no задолженность, no акты сверки. Where to pay is
  held; how much was paid is not, and the ставка stays a condition of an agreement.
- **Договоры со Сторонами.** No entity for a contract with a поставщик, and no header over
  аренды (ADR 0017 stands).
- **Оживление `PartyRole`.** The model is left exactly as it is — zero rows, no reader, no
  section on the screen. Роли get a stage of their own when something needs them.
- **Заведение Стороны с формы аренды.** The lease form still offers no «Завести Сторону»
  button; the Сторона is entered on her own раздел first.
- **История изменений** — no audit trail of who edited what in a учётная карточка beyond the
  `CommonModel` stamps that every entity already carries.
- **Напоминания.** No email, no push, no digest. «Кого поздравить» is a question asked of the
  shelf, not a message the system sends.
- **Государственные праздники** and any notion of a working day. Only профессиональные, and
  only to derive a повод.
- **Проверка БИН** against any external registry, and any enrichment of a Сторона from one.
- **Слияние дублей.** If two Стороны turn out to be one juridical entity, the fix is in the
  Django admin.
- **Полка аренд.** Still not built; the Сторона's аренды are a section of her экран.
- **Загрузка учётных карточек** from the учётная система. Entry is by hand, once the seed has
  run.

## Further Notes

**The two decisions this stage reopens were both deliberate, and both documented in code
rather than in an ADR.** `leases/party_choice.py` and `documents/document_edit.py` each state
that no narrowing of Стороны by организация exists anywhere in the project, and each reasons
from that. Both were right when written: there was no first answer to «чьи это подрядчики».
The учётная карточка is that answer, and ADR 0020 records the change so that neither comment
is quietly contradicted.

**The номера.** 699 Стороны, of which 637 get a карточка in the seed. 1 организация, 2
членства, both without the administrator flag — so on the data as it stands today nobody can
use any of the forms in this spec from the application. Granting the flag is a Django admin
act by the администратор платформы (ADR 0005) and is a prerequisite for the stage being
usable at all.

**What this stage does not fix, and knows it.** 235 аренды of 271 stay unloaded because 42
арендаторы have a БИН and no name anywhere. Tokyo and Boston therefore have no аренды, and
the condition «только арендаторы» will look thin. Loading them needs one more export from the
УК and changes nothing built here.
