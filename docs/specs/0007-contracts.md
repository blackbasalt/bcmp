# Договоры — какие у нас обязательства и когда они кончаются

## Problem Statement

BCMP holds 699 Стороны, gives 637 of them a учётная карточка, and knows about not one of
them what we owe them or they owe us, or until when.

The source export says plainly what these Стороны are. `scripts/populate_data/party.csv`
carries a `role` column whose value is `Поставщики` on **698 of the 699 rows** — the file is
a supplier registry — and `load_real_data.load_parties()` reads `inn_bin`, `type`,
`clean_name` and `date_base` and throws `role` away without a word. This is the same shape as
the `date_base` discovery that drove the Стороны stage: a column in the real data that
already answers the question the next stage is about.

So the questions a сотрудник УК arrives with have no screen:

- «Какие договоры кончаются в этом квартале» — nowhere. `Document.valid_until` exists and is
  inert; its own comment reads «no one has ordered a register of deadlines yet».
- «По какому договору сидит ТОО «Альфа» и до какого числа» — nowhere. `Lease.contract_no` is
  free text, filled on 18 fictional rows and on none of the 36 real ones.
- «Что мы вообще подписали с этим поставщиком» — nowhere. 637 поставщики, and `PartyRole`
  holds zero rows.
- «Какой договор продлевается сам, а какой надо перезаключать» — no field, no notion.

Underneath sits a contradiction the project has carried since August. `CONTEXT.md` said both
«договор аренды — сущность со своим предметом» (in **Документ**) and «BCMP договоров не
заводит» (in **Аренда**) — residue of a stage that was built, shipped and reverted whole by
`0e6a161`, with #22 closed as not planned and the reason recorded only later: scope.

## Solution

**Договор — это документ вида «Договор» с таблицей условий сбоку** (ADR 0030). `Document`
already carries номер, дату, срок, файл and организацию, and the полка документов already has
отбор, поиск, изоляцию and пакетную загрузку. A second entity beside it would keep a second
номер, a second дата and a second скан, and they would part.

**Вид хранится, род выводится.** Five виды — **Аренда помещений**, **Доп услуги**,
**Эксплуатация**, **Капитальные работы**, **Поставка ТМЦ** — and род (доходный / расходный)
is derived from вид, never stored, because every вид stands on one side. One subject on two
sides is two виды: клининг sold to a tenant is Доп услуги, клининг bought from a подрядчик is
Эксплуатация.

**Бухгалтерских слов на экране нет.** OPEX and CAPEX are words that exist to be summed, and
BCMP holds no sums. «Эксплуатация» survives because it is the УК's own facility word;
«Капитальные вложения» becomes **Капитальные работы**. The same refusal that keeps
«Контрагент» off the полка Сторон.

**Срок в трёх состояниях, и автопролонгация сказана вслух** (ADR 0031). A shelf that answers
«когда кончается» cannot let one empty date mean both «бессрочный» and «никто не завёл» — the
second would hide a договор expiring next month. Автопролонгация changes what a row says, not
whether it appears.

**Аренда может висеть на договоре, но не обязана** (ADR 0032). ADR 0017 is reversed in half:
the договор-сущность exists now. Its other half stands — часть помещения is a number of
metres. Nothing moves up to the заголовок: арендатор, арендодатель and срок stay on the
аренда, because an аренда without a договор must remain a complete record, and today all 36
of them are exactly that.

**Расходный договор здания не называет** (ADR 0033). A договор аренды reaches its БЦ through
its аренды; эксплуатация, капитальные работы and поставка ТМЦ reach nothing and are not made
to pretend. «Обязательства по этому зданию» answers for аренда only, and the полка says so by
dropping расходные out of the БЦ condition entirely.

**Трудовых договоров нет** (ADR 0029). A сотрудник is not a Сторона, `OrgMembership` already
holds the staff, and a трудовой договор is pay — over the line BCMP has held since «Ставка».

## User Stories

### Полка договоров

1. As a сотрудник УК, I want a раздел «Договоры» beside «Бизнес-центры», «Документы»,
   «Помещения» and «Стороны», so that «что мы подписали и до каких пор» has an address.
2. As a сотрудник УК, I want the rows to carry **Название · Номер · Вид · Контрагент ·
   Кончается**, so that the shelf answers without opening anything.
3. As a сотрудник УК, I want «Кончается» to say «бессрочный» where that is the case and
   «срок не заведён» where it is not, so that an empty cell never means two things.
4. As a сотрудник УК, I want a row on автопролонгации to say «продлевается автоматически»,
   so that I am not sent to renegotiate a договор that renews itself.
5. As a сотрудник УК, I want the count line «Показано 12 из 340 договоров», so that a
   narrowed shelf says how much it hid.
6. As a сотрудник УК, I want «вид не заведён у N» and «срок не заведён у N» on that line, so
   that a batch of scans nobody has classified is a number and not a silence.
7. As a сотрудник УК whose организация has no договоры at all, I want «Договоры не заведены»
   rather than «ничего не нашлось», so that I am not sent to fix a question that was never
   the problem.
8. As a сотрудник УК, I want договоры to keep appearing on the полка документов as well, so
   that «Показано 12 из 637 документов» does not lie about the table it counts.

### Отбор

9. As a сотрудник УК, I want to search by название and номер договора in one field, case
   folded, so that «АР-2026» and «ар-2026» find the same row (ADR 0014).
10. As a сотрудник УК, I want to narrow by вид, so that «все наши договоры эксплуатации» is
    one click.
11. As a сотрудник УК, I want to narrow by род, so that доходные and расходные are told apart
    without picking виды one by one.
12. As a сотрудник УК, I want to narrow by контрагент, so that «что у нас с ТОО «Альфа»» is
    answered from the shelf.
13. As a сотрудник УК, I want a condition «кончается: на этой неделе / в этом месяце / в
    ближайшие 90 дней», so that the register of deadlines is the shelf answering. A free
    number of days would invite 0 and 3650.
14. As a сотрудник УК, I want бессрочные and договоры без срока left out of that condition and
    counted on the count line, so that the отбор never claims to have weighed what it could
    not read.
15. As a сотрудник УК, I want to narrow by БЦ and to be told that this narrows to договоры
    аренды, so that the absence of расходные is an answer rather than a bug (ADR 0033).
16. As a сотрудник УК, I want the отбор in the address, so that a narrowed полка is a link.
17. As a сотрудник УК, I want a condition that does not read to narrow the shelf to nothing
    rather than be dropped (ADR 0014).

### Экран договора

18. As a сотрудник УК, I want the договор to have its own address and screen, so that an
    obligation is not read as a rail on a page about a file.
19. As a сотрудник УК, I want a header with название, номер, вид, род, контрагент and срок,
    so that what we signed and until when is settled before anything else is read.
20. As a сотрудник УК, I want a link to the документ itself, so that the скан, its близнец and
    its связи are one click away and not duplicated here.
21. As a сотрудник УК reading a договор аренды, I want its аренды listed — помещение, БЦ,
    арендуемая площадь, ставка, срок — so that «что входит в договор» is answered from the
    договор's side.
22. As a сотрудник УК, I want those аренды **not** totalled, so that a number inflated by
    nested помещения is never quoted (ADR 0015, ADR 0019).
23. As a сотрудник УК reading a расходный договор, I want **no аренды block at all** rather
    than an empty one, so that an always-empty section does not teach me that договоры
    эксплуатации have аренды nobody entered.
24. As a сотрудник УК, I want no «сумма договора» anywhere, so that the money line stays where
    eight ADRs have kept it.

### Заведение, правка, удаление

25. As an администратор организации, I want to enter a договор — its документ and its условия
    in one form — so that a new supplier agreement does not require Django admin.
26. As an администратор организации, I want to attach аренды to a договор аренды and detach
    them, so that «по какому договору сидит ТОО «Альфа»» becomes answerable as I go.
27. As an администратор организации, I want the арендатор of an аренда and the контрагент of
    its договор to be refused when they differ, so that one fact does not acquire two records.
28. As an администратор организации, I want аренды refused on a договор of any вид but
    «Аренда помещений», so that a lease under a поставка ТМЦ is caught at entry.
29. As an администратор организации, I want аренды refused on a договор of another
    организация, so that изоляция has one answer and not two (ADR 0018).
30. As an администратор организации, I want no check that an аренда lies inside its договор's
    срок, so that автопролонгация and an early departure both stay recordable (ADR 0031).
31. As an администратор организации, I want to delete a договор in two steps, asked by the
    application and not by the browser (ADR 0013).
32. As an администратор организации, I want deleting a договор to leave its аренды standing,
    so that a rent history is not destroyed with a scan (ADR 0034).
33. As an администратор организации, I want the document's вид refused from changing while its
    условия are filled, so that a контрагент and a срок somebody typed are not silently
    orphaned (ADR 0035).
34. As a сотрудник без флага администратора, I want no forms shown to me at all.

### Доступ и изоляция

35. As a сотрудник УК, I want a договор of another организация to answer 404 on its address,
    so that absence of another client's data is indistinguishable from absence (ADR 0006).
36. As a сотрудник УК, I want the isolation to come from `Document.org` and from nowhere else,
    so that there is one chokepoint and not a second to drift from it.

### Полка помещений

37. As a сотрудник УК, I want «аренд без договора: N» on the count line of the полка
    помещений, beside «аренды на неарендопригодных» and «аренд без площади», so that the gap
    left by an optional link is stated on the screen that holds the аренды.

### Язык

38. As a developer, I want «Капитальные работы» and never «CAPEX» or «Капитальные вложения»,
    and never «OPEX», so that words that exist to be summed do not arrive on a screen that
    sums nothing.
39. As a developer, I want «договор» to mean the obligation and «документ» the paper, so that
    the two do not slip into each other in prose when they are one row.

## Implementation Decisions

### Раздел без моделей: `contracts` follows `rooms`

ADR 0016 makes a раздел a Django app because `templates/shell.html` computes the open раздел
as `request.resolver_match.app_name`. The `rooms` app has **no models at all** — it is a
раздел over `building_passport.Space`. `contracts` is the same: `urls.py` with
`app_name = "contracts"`, views and templates over rows the `documents` app owns, mounted at
`contracts/` and given a fifth `_sidebar_item.html`.

Two routes:

- `""` → `ContractListView` (`contract_list`) — полка.
- `"<uuid:pk>/"` → `ContractDetailView` (`contract_detail`) — экран.

**The договор gets its own screen rather than a block on the document screen.** This is the
one decision here taken rather than asked, and it is the symmetric twin of a decision that was
asked: договоры stay on the полка документов *and* get their own полка, so they keep the
document screen *and* get their own. The two answer different questions — the document screen
answers «что это за бумага» (реквизиты, близнец, связи, файл), the договор screen answers
«какое обязательство и до каких пор». Each links to the other, as issue #41 links a Карточка
БЦ to its documents. Overturn this and the аренды block moves onto `document_detail`.

### The model

**`ContractTerms`** lives in the `documents` app, beside `DocumentTwin`, `TwinImage` and
`DocumentLink` — every other one-to-one satellite of `Document` is there, and a migration
touching both tables stays in one app.

- `document` — `OneToOneField(Document, related_name="terms")`.
- `counterparty` — FK to `Party`, the other side. Our own side is `Document.org` and needs no
  field. Not `issuer_party`: «Кем выдан» about a договор is meaningless, and the narrowing
  shipped in `143c6fa` was written for issuers.
- `kind` — the вид, one of five, **nullable** (ADR 0035).
- `is_perpetual` — бессрочный, beside `Document.valid_until` (ADR 0031).
- `auto_prolongs` — автопролонгация.

A row is created for **every** `Document` of kind `contract`, filled or not. There is **no
per-вид table**: five would be five guesses at fields no screen reads, and the schema already
carries that mistake — `DocumentLink.EntityType` ships ten values of which
`building_element`, `asset`, `element_survey` and `element_repair` point at tables that have
never existed. A per-вид table arrives when a вид has a field with a reader.

**Род is a function, not a column** — `parties/occasions.py` is the shape: one rule handed out
in the shapes the screens need. `contracts/genus.py`, `space_kind.py`'s sibling.

**`Lease` gains `contract`** — `ForeignKey(Document, null=True, blank=True,
on_delete=models.SET_NULL, related_name="leases")` — and **loses `contract_no`** by migration.
The free field was a note while nothing held the договор; beside a real link it is a second
truth about which paper an аренда belongs to. Its only values are the 18 fictional ones.

Three refusals on `Lease.save()`, beside `refuse_a_period_that_ends_before_it_begins`:

- the договор's `org` must be the помещение's `org` (ADR 0018 — one answer to «чья аренда»);
- the договор's вид must be «Аренда помещений»;
- the аренда's `tenant` must be the договор's `counterparty`.

And one refusal on `Document.save()`: `kind` may not leave `contract` while `terms` is filled.

There is deliberately **no** check that an аренда lies inside its договор's срок: an
auto-prolonging договор outlives its stated end, and a tenant leaving one помещение of four
ends early. Both directions are correct data.

### Что переиспользуется

`bcmp/shelf.py` — `asked` and the `if not self.is_valid(): return queryset.none()` guard, in
place since the Стороны stage. `BuildingChoice` from `documents`, now a fifth form. The отбор
bar is a fourth handwritten template, for the reason `_room_search.html` documents.

Isolation is `Document.org` and nothing else — `DocumentQuerySet.visible_to` already exists and
already does it (ADR 0006). The chokepoint first, `narrow` after it, never instead.

### Наполнение

`load_real_data` enters **no договор at all**. There is nothing to enter: `lease_data.csv` has
no contract-number column, and the 637 поставщики carry no contract data anywhere. Inventing
one against a real поставщик is the lie `fill_leases` already refuses in its docstring — «сделать
«Центр крепежных систем ТОО» арендатором значило бы положить в данные ложь».

`fill_leases` turns its 18 existing `contract_no` values into договоры вида «Аренда помещений»
and links its leases to them; a new `fill_contracts` invents **both the Сторона and the
договор** for the расходная half, so the shelf can be seen working without a single real
поставщик being credited with a contract nobody signed.

The honest fix is the УК's own contract register as a source file. That is the next stage, and
it is named here so that the filler is never mistaken for it.

## Testing Decisions

What is observable at the HTTP boundary: which договоры are on the screen, what a row says,
what the count line says, what status code comes back, and what is left in the database after a
refusal. Not `genus.py`, not the form class, not the query.

**Five seams, two of them new:**

1. **`contracts:contract_list`** — rows, columns, the count line and both its findings, all six
   conditions, both empty states, the reset link, isolation. Prior art: `parties/test_shelf.py`,
   `parties/test_search.py`.
2. **`contracts:contract_detail`** — the header, the link to the документ, the аренды block and
   its absence on a расходный договор, the absence of totals, 404 across организации, and every
   write. Prior art: `documents/test_document_page.py`, `documents/test_deletion.py`.
3. **`leases`** — the three refusals, and that deleting a договор leaves its аренды standing
   with a null link. In the existing suite.
4. **`documents:document_detail`** — the kind-change refusal, and that a договор still appears
   on the полка документов. In the existing suite.
5. **`rooms`** — «аренд без договора: N» on the count line. In the existing suite.

**Footholds:** `data-contract` on each row, `data-search="contracts"`,
`data-count="contracts"`, `data-section` on the header and аренды blocks — mirroring
`data-room`, `data-document`, `data-lease`, `data-party`.

**No seam for `genus.py`**, exactly as `space_kind`, `plan_completeness` and `occupancy` have
none: it is read by two screens and both check it.

## Out of Scope

- **Суммы.** No сумма договора, no начисления, no оплаты, no задолженность. Where to pay is
  held (ADR 0022); how much was paid is not, and this stage does not move that line.
- **Трудовые договоры** and any HR (ADR 0029).
- **Бронирование конференц-залов.** Hourly and per-event booking is not an аренда «с какого дня
  по какой» and not a договор; it is its own stage with its own word.
- **Привязка расходных договоров к БЦ** (ADR 0033), and with it «обязательства по этому
  зданию» for four of five виды.
- **Оживление `PartyRole`** — still zero rows, still no reader, still no section.
- **Несколько контрагентов на одном договоре.** One counterparty; a three-sided agreement is
  entered as the paper it mostly is.
- **Своя таблица под вид договора** — until a вид has a field with a reader (ADR 0030).
- **Напоминания.** No email, no push, no digest. «Что кончается» is asked of the shelf.
- **Пролонгация как действие.** `auto_prolongs` records a condition; renewing a договор by hand
  is entering the next one, the way продление is a new аренда (ADR 0017).
- **История изменений** beyond the `CommonModel` stamps.
- **Загрузка реестра договоров** from the учётная система.

## Further Notes

**This is the second time the проект has built a договор.** The first, `ee46fe5`…`24bd8fe`
(11–13 August 2026), made it an entity — `Lease` as the заголовок with `LeaseSubject` beneath —
and `0e6a161` deleted all of it, 6 495 lines, two days later. ADR 0017 recorded the rejection
as scoped: «Отвергнуто **в этом этапе**», and its `## История` section was written so the next
reader would not conclude the reverted branch was careless.

This design is not that one returning. There the договор was a new entity with its own `org`
and its own предмет, and periods could not overlap. Here it is a `Document`, `org` comes free
from ADR 0006, the аренда stays flat, the link is optional in both directions, and the предмет
is the аренды themselves. The weight that killed it twice — a заголовок you must create before
you can seat a tenant — is exactly what «необязательна» removes.

**ADR 0018 predicted this.** It recorded that the reverted design gave the договор its own
`org` because a договор names several помещения possibly in different БЦ, and closed:
«С плоской аренды этот довод снят вместе с заголовком (ADR 0017), **а не отвергнут**.» The
заголовок is back and the довод with it — and it is already answered, because a договор is a
`Document` and `Document.org` has been mandatory since ADR 0006.

**The glossary contradiction is closed.** `CONTEXT.md` had carried both «договор аренды —
сущность со своим предметом» and «BCMP договоров не заводит» since the revert. Both sentences
are now gone, replaced by entries that agree.

**Seven ADRs, 0029–0035, hold the decisions**, and four terms — **Договор**, **Вид договора**,
**Бессрочный договор**, **Автопролонгация** — were added to `CONTEXT.md` during the design,
with **Документ** and **Аренда** amended.

**Числа.** 699 Сторон, 698 of them marked `Поставщики` in a column the loader discards; 637 with
a учётная карточка; 36 аренды, none with a contract number; 41 of 271 source lease rows with no
end date; 0 договоры on the day this ships from real data.
