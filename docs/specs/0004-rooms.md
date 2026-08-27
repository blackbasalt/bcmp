# Полка помещений — раздел «Помещения» с отбором

## Problem Statement

BCMP holds 583 помещения across five БЦ, and there is no way to look at them. Every
помещение is reachable only by walking down: Бизнес-центры → Карточка БЦ → этаж → дерево
на экране этажа. That descent answers "what is on this floor" and nothing else.

The questions a сотрудник УК actually arrives with cross buildings and cross floors.
«Где каб101» — they know the number, not the building. «Покажи все санузлы» — an engineer
planning a round. «Какие офисы больше 100 м² свободны под нарезку» — a leasing question
that today means opening five БЦ, thirty-four этажей and reading trees. «У каких помещений
не заведена площадь» — an audit question with no screen at all, though the answer is 36
помещений and every one of them is МОП or техническое.

There is no second way in, either. The Django admin lists `Space` with a `list_filter` on
type, floor_number, subtype and the two flags, but it is the platform administrator's tool:
it shows all clients' data, speaks in field names («Подтип», `is_common`), lists проекты,
площадки, шахты and этажи alongside помещения, and is not a screen a сотрудник УК is given.

Meanwhile the vocabulary itself has drifted. `Space.type` is «тип» — проект, площадка,
здание, этаж, помещение. The план's layer calls the арендопригодное/МОП/техническое split
«Тип помещения» too, for a completely different question. The space card labels `subtype`
with the storage word «Подтип». Three axes, and two of them are fighting over one word.

## Solution

A **полка помещений** — a third раздел in the sidebar next to Бизнес-центры and Документы,
built the way the полка документов is built: a flat table of every помещение the reader may
see, narrowed by an **отбор** whose conditions travel in the address.

It is a finder, not a form. Nothing is created, edited or deleted on it. A row leads to the
экран этажа with that помещение's card already open — the полка answers «которое», the
экран этажа answers «где».

It also counts what it has not got. Under the table: **«Показано 47 из 583 помещений ·
площадь не заведена у 5»**, the second figure a link that narrows the полка to exactly those
помещения. This is the stage-2 «нанесено 47 из 82» trick and the stage-3 «близнец есть у 12
из 340» trick, applied to a полка that is full rather than empty — the gap here is not
missing rows but missing fields in the rows that exist.

And it settles the vocabulary, because the отбор has to put three classifying conditions
side by side and cannot do it while two of them are called «тип»: **тип** is `Space.type`,
**вид** is арендопригодное/МОП/техническое, **назначение** is `subtype`.

## User Stories

### Раздел и навигация

1. As a сотрудник УК, I want a «Помещения» item in the sidebar, so that помещения are
   reachable without walking down through a БЦ and an этаж first.
2. As a сотрудник УК, I want the «Помещения» item highlighted while I am anywhere in that
   раздел, so that I can see where I am.
3. As a сотрудник УК, I want «Бизнес-центры» *not* highlighted while I am on the полка
   помещений, so that the menu names one open раздел rather than two.
4. As a сотрудник УК, I want the полка to open with no отбор and show every помещение I may
   see, so that the screen starts by telling me how much there is.

### Таблица

5. As a сотрудник УК, I want a row per помещение with its код, название, БЦ, этаж, «внутри»,
   вид, назначение and площадь, so that I can judge a помещение without opening it.
6. As a сотрудник УК, I want вложенные помещения shown as rows of their own, so that a кабина
   inside a санузел can be found on the same полка as an office.
7. As a сотрудник УК, I want a «Внутри» column naming the помещение a row sits inside, so
   that a flat table admits it расплело a tree and I can tell a кабина from a кабинет.
8. As a сотрудник УК, I want the «Внутри» cell empty for a помещение lying directly on an
   этаж, so that emptiness reads as "on the floor" rather than as missing data.
9. As a сотрудник УК, I want the rows ordered БЦ → этаж → код, so that reading the полка
   top to bottom walks the portfolio the way I would walk it.
10. As a сотрудник УК, I want **no** итог under the площадь column, so that I am not handed
    a number that double-counts вложенные помещения (ADR 0015).
11. As a сотрудник УК, I want a помещение with no площадь to show a dash rather than a zero,
    so that "не заведено" is not read as "нулевая площадь".
12. As a сотрудник УК handling more than one организация, I want an «Организация» column, so
    that two clients' помещения are not mixed up in one table.
13. As a сотрудник УК of a single организация, I want **no** «Организация» column, so that a
    column repeating one word 583 times does not take the width.
14. As a сотрудник УК, I want the whole полка rendered at once with no pagination, so that
    the browser's own find works across every row and a shared link loses nothing.

### Отбор

15. As a сотрудник УК, I want to search помещения by название, so that «каб101» finds the
    room whose number I was given.
16. As a сотрудник УК, I want the search to fold case, so that «итп» finds «ИТП» — every
    название here is Russian (ADR 0014).
17. As a сотрудник УК, I want the search to match a substring, so that «101» finds
    «каб101», «каб101вход» and «каб101вправо» together, since they are one кабинет's parts.
18. As an администратор организации, I want the search to match код as well as название, so
    that a path id left in `unmatched_ids` by a план can be looked up.
19. As a сотрудник УК, I want the search bar to say «Название или код», so that I know код
    is searched without having to guess.
20. As a сотрудник УК, I want the search to reach no further than название and код, so that
    typing a word does not return every помещение whose назначение happens to contain it.
21. As a сотрудник УК, I want to narrow by БЦ, so that «покажи всё по Tokyo» is one control.
22. As a сотрудник УК, I want the БЦ list to offer my own БЦ only, so that the control does
    not name another client's building (ADR 0006).
23. As a сотрудник УК, I want to narrow by вид — арендопригодное, МОП, техническое — so that
    the leasing question and the engineering question are each one click.
24. As a сотрудник УК, I want to narrow by назначение, so that «покажи все санузлы» is one
    control.
25. As a сотрудник УК, I want to narrow by этаж, so that «всё на третьем» works, and across
    all БЦ it means the third floors of all of them.
26. As a сотрудник УК, I want to narrow by площадь от and до, so that «офисы больше 100 м²»
    is askable.
27. As a сотрудник УК, I want «площадь не заведена» as a condition of its own, so that the
    audit question is asked from the same полка as everything else.
28. As a сотрудник УК, I want «вид не заведён» as a condition of its own, so that помещения
    nobody has classified can be found before they quietly count as технические.
29. As a сотрудник УК, I want the conditions to compose, so that «санузлы Tokyo на третьем
    этаже» is one отбор and not three screens.
30. As a сотрудник УК, I want the отбор in the address, so that a narrowed полка is a link I
    can reload, keep in a tab and send to a colleague.
31. As a сотрудник УК, I want the отбор cleared by the same address without it, so that
    getting back to the whole полка needs no reset button.
32. As a сотрудник УК, I want the bar to hold what I asked after the page comes back, so
    that I can change one condition without retyping the others.
33. As a сотрудник УК, I want a condition that did not read to narrow the полка to nothing
    and say so, so that the screen never claims an отбор it did not perform.
34. As a сотрудник УК, I want **no** «статус» condition, so that the bar does not offer a
    control that can only ever answer «ничего не нашлось».

### Счёт и пустые состояния

35. As a сотрудник УК, I want a line under the table saying «Показано N из 583 помещений»,
    so that I know how much of the полка the отбор left.
36. As a сотрудник УК, I want that line to also say «площадь не заведена у M», so that the
    gap in the data is stated on the screen that holds the data.
37. As a сотрудник УК, I want M to count only what is on screen, so that the line does not
    contradict the table above it.
38. As a сотрудник УК, I want «из 583» to refer to the whole полка, so that a narrowed
    screen still tells me the size of what I narrowed.
39. As a сотрудник УК, I want the «площадь не заведена у M» figure to be a link that ticks
    that condition, so that the audit is one click from the finder.
40. As a сотрудник УК, I want «ничего не нашлось» when an отбор matched nothing, so that I
    am sent to change the question.
41. As a сотрудник УК, I want «Помещения не заведены — их заводит администратор платформы»
    on a полка with no rows at all, so that I am told who acts rather than handed a link I
    cannot use.
42. As a сотрудник УК, I want the bar still standing on a полка an отбор emptied, so that I
    can widen the question I just narrowed.

### Из полки — на этаж

43. As a сотрудник УК, I want a row to lead to the экран этажа with that помещение's card
    open, so that having found «которое» I immediately see «где».
44. As a сотрудник УК, I want the план on that screen to show as it always does, so that
    arriving from the полка and arriving from the tree land me on the same screen.
45. As a сотрудник УК, I want an address naming a помещение of another client, or one that
    does not exist, to answer as if no помещение were named, so that the address does not
    become a way to ask about other clients' data.

### Язык

46. As a сотрудник УК, I want the план's layer called «Вид помещения», so that the колонка
    on the полка and the legend beside the план name the same thing the same way.
47. As a сотрудник УК, I want the space card to say «Назначение» rather than «Подтип», so
    that a storage word is not put in front of a reader.

### Доступ и изоляция

48. As a сотрудник УК, I want to see помещения of my own организации only, so that the полка
    obeys the same checkpoint as every other screen (ADR 0001).
49. As a сотрудник УК, I want the полка to require signing in, so that it is not a way round
    the login every other screen requires.
50. As a сотрудник УК, I want no створки for creating, editing or deleting a помещение, so
    that the полка is understood as a finder and nothing else.

## Implementation Decisions

### A раздел is a Django app

The полка lives in a **new app `rooms`**, `app_name = "rooms"`, mounted at `/rooms/`, with
an empty `models.py` — it imports `Space` from `building_passport` exactly as `documents`
does. The sidebar's open раздел is computed as `request.resolver_match.app_name`, so a
раздел is an app; putting the полка inside `building_passport` would highlight
«Бизнес-центры» while the reader stands on «Помещения». Named `rooms` rather than `spaces`:
the полка shows помещения only, and `DictSpaceType.ROOM` already binds помещение to *room*.
Recorded as ADR 0016.

### What is on the полка

`Space` of `type=room`, through `Space.objects.visible_to(user)` and nothing else — the
полка narrows what the checkpoint hands it and never selects rows itself. Every помещение
is a row, including the 218 that sit inside another помещение; the tree is not reconstructed
and not indented. `building_id` is set on every помещение, so the БЦ condition is a column
comparison and not an ancestor walk.

### Вид is extracted, not duplicated

The rule that turns `is_leasable` / `is_common` into арендопригодное / МОП / техническое
already exists in `plan_layer.SpaceTypeLayer.paint_of` and is pinned by two named tests:
a contradictory pair reads as арендопригодное, and an unset flag means "no", so техническое
is the remainder. The полка needs the same rule as a queryset condition rather than as a
`Paint`.

It moves to a new module **`building_passport/space_kind.py`**, exposing the вид of a
помещение and a condition per вид. `plan_layer` imports it and keeps the colours, the legend
captions and the ordering of the legend — those are the план's, not the rule's. The полка
imports it for the вид condition. Neither screen restates the rule.

### The отбор

One form holding every condition, in the shape of `documents/shelf_search.py`: bound even
to an empty address, valid before it narrows, narrowing what it is handed. Conditions:

- **поиск** — `название` or `код` containing the text, `iregex` over `re.escape` and not
  `icontains`, for the reason ADR 0014 gives: SQLite's `LIKE` folds case for ASCII alone and
  every название here is Russian. Placeholder «Название или код».
- **БЦ** — the reader's own БЦ only, via `Space.objects.buildings_visible_to`, reusing the
  documents section's building widget.
- **вид** — three choices, computed through `space_kind`; empty choice «Любой вид».
- **назначение** — `DictSpaceSubtype` scoped to `type=room`; empty choice «Любое назначение».
- **этаж** — `floor_number`, an integer. Across БЦ it means that floor of every building,
  which is the right reading for a полка that spans the portfolio.
- **площадь от / до** — a range over `area_m2`.
- **площадь не заведена** — a checkbox, `area_m2 IS NULL`.
- **вид не заведён** — a checkbox, both flags unset. Not a fourth value in the вид select:
  вид still answers three things and only three, and this is a statement about the record
  rather than about the building — which is why `plan_layer` may go on refusing a fourth
  colour while the полка offers the condition.

There is deliberately **no статус condition**: `status` is filled on 0 of 583 помещения.

A condition that does not read narrows the полка to nothing rather than being dropped, and
the screen says which condition it was. A БЦ that does not exist and a БЦ belonging to
another client give one wording, because telling them apart would tell this reader what the
other one has (ADR 0006).

### The table

Columns: Код, Название, БЦ, Этаж, Внутри, Вид, Назначение, Площадь — plus Организация when
the reader has more than one, on the same condition `documents` uses. Order БЦ → этаж → код,
fixed; no click-to-sort in this spec. `Внутри` names `parent` when the parent is a помещение
and is empty when it is an этаж. No итог under Площадь, for the reason ADR 0015 gives.
No pagination, matching the полка документов, which sets no `paginate_by`.

### The count line

Beneath the table, as on the полка документов: «Показано N из 583 помещений · площадь не
заведена у M». Everything after «Показано» describes what is on screen; only «из 583» refers
to the whole полка. M is a link that sets the «площадь не заведена» condition while keeping
the rest of the отбор. Portfolio-wide plan completeness is **not** on this line: that count
belongs to the экран этажа, computed against the план in force per floor, and a second place
computing it would drift from the first.

### From a row to the этаж

A row links to the экран этажа with the помещение named in the address —
`bc/<uuid>/floor/<uuid>/?space=<uuid>` — and `FloorView` opens that помещение's card. A
помещение that is not visible, does not exist, or does not lie on that этаж is treated as if
none were named: the screen renders as it does today. The card is not given a second home on
the полка; it is the rail of the экран этажа and its worth is the план beside it.

### Vocabulary

Three axes, three words, fixed here and in `CONTEXT.md`: **тип** = `Space.type`, **вид** =
арендопригодное/МОП/техническое, **назначение** = `subtype`. Consequently:
`plan_layer` title «Тип помещения» → «Вид помещения»; space card «Подтип» → «Назначение»;
space card «Тип помещения» → «Тип», since it renders `Space.type` and reads «Тип помещения:
Помещение» today.

### Explicitly not changed

- No migration. `is_leasable` / `is_common` stay two nullable booleans and вид stays derived;
  `status` stays unfilled rather than being removed.
- The Django admin is untouched.
- The space card gains no вид row — the план shows вид by colour right beside it.
- `plan_layer`'s refusal of a fourth colour for "вид не заведён" stands.

## Testing Decisions

### What makes a good test here

A test asks the полка a question the way a reader asks it — through the address — and checks
what came back: which помещения, in what order, what is written in the row, what the count
line says, and what the bar holds afterwards. It reads the markup through stable footholds,
never through classes or wording that is free to change. It does not reach into the form, the
queryset or `space_kind`: those are how the answer is produced, and a test that names them
passes while the screen is wrong.

### Seams

**One new seam: the HTTP boundary of `/rooms/`.** The отбор travels in the query string and
the answer is read out of the markup. Footholds: `data-room` on a table row, mirroring
`data-document` on the полка документов; `data-search` on the bar; the count line normalised
through the same whitespace fold the documents tests use. Helpers `rooms_on(page)` — the keys
top to bottom, so the fixed order is asserted rather than assumed — and `rows_on(page)` for
the text of each row live in `rooms/test_shelf.py`, which the отбор tests import from: the
same `test_section.py` / `test_search.py` split the documents section already uses.

**Everything else lands on seams that exist:**

- Sidebar highlight → root `test_shell.py`, which already reads `data-section` and
  `aria-current` across all items. That is where ADR 0016's claim is tested.
- `?space=` on the экран этажа → `building_passport/test_floor.py` and `test_space_card.py`,
  the same HTTP boundary they use now.
- The вид rule → stays in `building_passport/test_floor_plan.py`, asserted through the план
  by `painted_on` and `legend_on`, unchanged by the extraction.

**`space_kind.py` gets no tests of its own.** `plan_layer` has none today either: both callers
assert the rule through their own screens, and a third seam on a shared rule is how tests go
on passing while the two screens disagree.

**One fixture change**: root `conftest.make_space` currently takes `parent, code, name, type`
and must grow `**fields`, so a помещение can be staged with `area_m2`, the two flags and a
`subtype`. It belongs in the root conftest because `first_floor` is shared and there must not
be two definitions of one Manhattan.

### Prior art

`documents/test_search.py` is the closest — the отбор, its conditions, composition, clearing,
the bar holding its state, unreadable conditions, the count following the отбор, both empty
states, and isolation asserted of the conditions themselves. `documents/test_section.py` for
the table helpers. `building_passport/test_floor_plan.py` for reading a screen through
`data-` footholds.

### Coverage

Every condition alone; the conditions composing; case folding for Russian; the search
reaching no further than название and код; ordering; the «Внутри» column filled and empty;
no итог under площадь; the org column present and absent; the count line's two figures and
the link on the second; both empty states told apart; the bar standing on a полка an отбор
emptied; a row leading to the экран этажа with the card open; an unknown or other client's
`?space=` treated as unnamed; and isolation — another client's помещение unreachable by
search, by БЦ and by direct address.

### Deliberately untested

The colour of the sidebar highlight, the wording of column headings other than «Вид» (which
is now vocabulary, not decoration), and the layer's title string — the legend is asserted by
its `data-legend` keys, which the rename does not touch.

## Out of Scope

- **Editing помещения.** The полка is read-only. Bulk data entry for the 36 помещения with no
  площадь and the 583 with no статус is a different feature with a write checkpoint, per-field
  validation and an undo story.
- **Click-to-sort.** The площадь range condition covers the one question a площадь sort was
  for; sorting has to travel in the address and can be added once it is clear which column
  people keep wanting to click.
- **Pagination.** Revisited when помещения reach five figures — and then it is a decision
  about storage, as ADR 0014 says about the search.
- **Помещения of other types.** Шахты, лестничные клетки, кровли, площадки and машиноместа
  stay off the полка; whether they are помещения in the language is a separate question.
- **A статус condition**, until `status` is filled by something.
- **A вид row on the space card.**
- **Portfolio-wide plan completeness.** That count stays on the экран этажа.
- **Any schema change.**

## Further Notes

The площадь figures behind ADR 0015, for whoever revisits it: of the 100 помещения with
вложенные, 73 have a площадь at least as large as the sum of their children — объединяющие,
where a sum would be right; 19 have less — содержащие, where a sum double-counts 53
помещения; and 8 have no площадь at all, so the link cannot be read either way.

The площадь gap is narrower than «547 из 583» suggests: арендопригодные are 324 of 324
complete, and every one of the 36 gaps is a МОП or a техническое помещение.

Today's data has no помещение with unset flags, so the «вид не заведён» condition matches
nothing on the current database. It is built now because the first half-classified building
loaded into the system is the moment someone needs it, and by then the помещения will be
quietly counted as технические.
