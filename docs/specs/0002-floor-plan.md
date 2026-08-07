# Stage 2 — Поэтажный план (план этажа с контурами помещений)

## Problem Statement

Stage 1 made the паспорт здания readable, but it stopped at the front door. Manhattan has
five этажей and 82 помещения in BCMP; a сотрудник УК can see that the building exists, its
класс, its площадь and who owns it, and nothing whatsoever about what is inside it. The
82 помещения are reachable only through Django admin, as rows in a table, in an order that
carries no meaning.

Помещения are inherently spatial, and a list destroys the one property that makes them
answerable. «Какие кабинеты выходят на южную сторону», «что находится рядом с ИТП»,
«сколько площади третьего этажа мы вообще сдаём» are all questions a сотрудник УК asks
constantly and none of them survive translation into a table. The УК has поэтажные планы —
as drawings, in a project folder, disconnected from every fact BCMP holds about the rooms
they depict.

There is a second problem underneath the first. Of the 82 помещения, 35 have no recorded
площадь, коридоры and лифтовые холлы are largely not modelled at all, and the children of
`man-f1` sum to 170 м² against a floor of 561. Nobody knows this, because a list of rows
gives no way to notice an absence. The floor is 70% unaccounted for and the data looks
complete.

## Solution

An экран поэтажного плана under each Карточка БЦ: the space tree from the этаж down to its
leaves on the left, the SVG план этажа in the centre with each помещение outlined and
filled translucently, and a карточка помещения in a right rail. Дерево and план are two
views of one selection — clicking a контур highlights its node, clicking a node highlights
its контур — so the помещения that have no контур yet remain reachable, which is precisely
the set that matters most.

The план is uploaded by an администратор организации as an SVG whose paths carry the
`Space.code` of the помещение they outline. On upload the file is parsed and its contours
become data: from that point the план is not a picture of помещения, it is the помещения,
drawn. Colouring is driven by a слой — for this stage, тип помещения — so that арендопригодные,
МОП and технические помещения are distinguishable at a glance and долги арендаторов or
неисправности систем can later be added as new слои rather than as a new screen.

Every план belongs to a period. After a перепланировка the previous план is kept and the
new one takes effect from the date the УК states, so the building's spatial history is not
overwritten by whoever happens to upload a drawing.

And the screen counts what it could not draw. «Нанесено 47 из 82 помещений» turns the план
into the sharpest instrument the project has for finding what has not been entered yet —
the spatial equivalent of stage 1's «— нет данных».

## User Stories

### Навигация

1. As a сотрудник УК, I want an Этажи section on the Карточка БЦ, so that I can get from a
   building to what is inside it without a separate menu.
2. As a сотрудник УК, I want to open a floor from that section, so that reaching a план
   takes one click from the паспорт.
3. As a сотрудник УК, I want a floor switcher on the план screen, so that I can move
   between five этажей without going back to the Карточка БЦ each time.
4. As a сотрудник УК, I want to return to the Карточка БЦ from any floor, so that I can
   move between the паспорт and its interior freely.
5. As a сотрудник УК, I want the floor switcher to show which этажи have a план, so that I
   do not click through floors hoping to find a drawing.
6. As a сотрудник УК, I want a bookmarkable address for a floor, so that I can send a
   colleague the exact план I am looking at.

### План и дерево

7. As a сотрудник УК, I want the space tree from the этаж down to its leaves on the left of
   the screen, so that I can see every помещение including those not drawn on the план.
8. As a сотрудник УК, I want nested помещения shown as nested in the tree, so that I can
   see that «каб101» sits under «каб101вход».
9. As a сотрудник УК, I want the план этажа rendered in the centre of the screen, so that
   the drawing gets the space it needs to be readable.
10. As a сотрудник УК, I want each помещение outlined on the план following its actual
    contour, so that I recognise the floor rather than a diagram of it.
11. As a сотрудник УК, I want контуры filled translucently over the drawing, so that the
    underlying план stays legible through the colour.
12. As a сотрудник УК, I want clicking a контур to select that помещение, so that I can
    interrogate the план by pointing at it.
13. As a сотрудник УК, I want clicking a node in the tree to highlight its контур on the
    план, so that I can find a помещение I know by name.
14. As a сотрудник УК, I want selecting a контур to highlight its node in the tree, so that
    I can see where a помещение sits in the hierarchy.
15. As a сотрудник УК, I want to select a помещение that has no контур from the tree, so
    that помещения missing from the план are still usable.
16. As a сотрудник УК, I want помещения with no контур marked in the tree, so that I can
    see at a glance what has not been drawn.
17. As a сотрудник УК, I want to hover a контур and see the помещение's name, so that I can
    scan a floor without clicking through it.
18. As an инженер УК, I want лестничные клетки, лифтовые шахты and проёмы второго света
    outlined on the план without a fill, so that the drawing has no unexplained gaps.
19. As a сотрудник УК, I want контуры never to overlap each other, so that a click always
    resolves to one помещение.
20. As a сотрудник УК, I want a помещение that only groups other помещения to have no
    контур of its own, so that the уборная does not sit on top of its own кабины.

### Слой

21. As a сотрудник УК, I want контуры coloured by тип помещения, so that I can see what is
    rentable, what is common and what is technical without reading any labels.
22. As a сотрудник УК, I want a legend for the colouring, so that I do not have to guess
    what a colour means.
23. As a сотрудник УК, I want арендопригодные помещения in one colour, so that I can judge
    the sellable area of a floor at a glance.
24. As an инженер УК, I want технические помещения in their own colour, so that I can find
    ИТП, венткамеры and электрощитовые on the floor immediately.
25. As a сотрудник УК, I want МОП in their own colour, so that I can tell the coridors and
    лифтовые холлы apart from what is leased.
26. As a сотрудник УК, I want the colouring rule stated as a слой, so that долги арендаторов
    or неисправности систем can later be shown on the same план.

### Карточка помещения

27. As a сотрудник УК, I want the selected помещение shown in a right rail, so that reading
    about a помещение does not cost me the план.
28. As a сотрудник УК, I want the карточка to show код, наименование, подтип, тип помещения
    and площадь, so that I have the facts BCMP holds about that помещение.
29. As a сотрудник УК, I want a missing площадь written as «— нет данных», so that I never
    read a blank as a zero.
30. As a сотрудник УК, I want the карточка to show where the помещение sits in the tree, so
    that I know what it is part of.
31. As a сотрудник УК, I want the parent and children in the карточка to be clickable, so
    that I can walk the hierarchy without leaving the план.
32. As a сотрудник УК, I want the план to stay visible while the карточка is open, so that
    I keep the spatial context that brought me there.
33. As a сотрудник УК, I want to close the карточка, so that the план can have the full
    width when I am scanning the floor.
34. As a сотрудник УК, I want the ИИ-управляющий panel to open over the карточка rather than
    fight it for the same edge, so that I can have both open at once.

### Полнота данных

35. As a сотрудник УК, I want the screen to state how many помещения are drawn out of how
    many exist, so that I know how much of this floor is still missing from the план.
36. As a сотрудник УК, I want the план to show only what has been entered, with no invented
    contour for the remainder, so that I am never shown a shape nobody measured.
37. As a разработчик, I want a path in the uploaded SVG matching no помещение reported on
    the screen, so that an id typo is visible rather than silently dropped.

### Загрузка плана

38. As an администратор организации, I want to upload an SVG план for a floor from the
    application, so that maintaining our own buildings does not require Django admin.
39. As an администратор организации, I want the помещения' контуры taken from the file I
    upload, so that I do not have to enter geometry by hand.
40. As an администратор организации, I want to state the date the планировка took effect,
    so that the план records when the building changed rather than when I got round to
    uploading it.
41. As an администратор организации, I want an upload whose period overlaps an existing план
    for that floor to be rejected with an explanation, so that a floor never has two
    действующих плана at once.
42. As an администратор организации, I want an upload with unmatched paths to succeed
    anyway, with the problems reported, so that I am not blocked from loading a план until
    the space tree is perfect.
43. As an администратор организации, I want a file that is not a usable SVG to be rejected
    with a reason, so that I can fix the export rather than wonder why the план is blank.
44. As a сотрудник УК, I want a new план to replace the old one on screen automatically, so
    that I always see the current state of the floor.
45. As a сотрудник УК without administrator rights, I want no upload control shown to me, so
    that I am not offered an action I cannot take.

### Доступ и изоляция

46. As a сотрудник УК, I want the план screen for a БЦ outside my организации to behave
    exactly like a building that does not exist, so that the response cannot confirm
    another client's data.
47. As a сотрудник УК, I want the SVG file itself to be unreachable for a БЦ outside my
    организации, so that a leaked or guessed file address does not hand over another
    client's floor plan.
48. As an anonymous visitor, I want to be redirected to login when requesting a план or its
    file, so that nothing about our clients' buildings is visible without a session.
49. As an администратор платформы, I want to grant and revoke administrator rights per
    организация from Django admin, so that a сотрудник can administer one client while
    remaining an ordinary user of another.
50. As a разработчик holding a superuser account, I want to see every организация's планы,
    so that I can reproduce a client's problem without granting myself their membership.

### Пустые состояния

51. As a сотрудник УК, I want a floor with помещения but no план to show the tree alone with
    an explanation, so that a missing drawing reads as "not loaded yet" rather than as a
    broken screen.
52. As a сотрудник УК, I want a БЦ with no помещения at all to keep the existing «не
    загружено» treatment on its Карточка БЦ, so that the four empty buildings behave as
    they already do.
53. As an администратор организации, I want the upload offered on an empty floor, so that
    the empty state is where I fix it.

### История

54. As a сотрудник УК, I want the план that is in force today to be the one I see, so that I
    never plan work against a superseded drawing.
55. As a сотрудник УК, I want a план superseded by a перепланировка to be kept rather than
    deleted, so that the building's spatial history survives.
56. As a сотрудник УК, I want a superseded план to keep the контуры it was drawn with, so
    that an old план is never rendered with today's помещения.

## Implementation Decisions

### Domain model

- **План этажа** is its own entity: the SVG file, the `Space` of type `floor` it belongs to,
  and a validity period. It is deliberately **not** a `Document` — a `Document` in this model
  is evidence, carrying `doc_no`, `issued_at`, `issuer_party` and `revision`, while a план is
  a coordinate system that помещения are positioned in. It is also **not** a field on `Space`.
- **Контур** belongs to the pair (план, помещение), not to the помещение. This is recorded in
  **ADR 0003** and is the decision the whole stage turns on: a помещение has no shape of its
  own, only a shape on a given план. A superseded план therefore carries the контуры it was
  drawn with.
- Контур geometry is **path data in a text column**, not a file. A контур is a few hundred
  bytes of geometry; as files, "does this контур share the floor's `viewBox`" would be
  unenforceable and one floor would cost 82 fetches.
- A `Space` of **any type** under the floor may carry a контур — `room`, `stairwell`, `shaft`,
  `void`. The rule for whether it does is occupancy: **a Space that occupies floor area of its
  own gets a контур; a Space that is only the sum of its children does not.** The eight
  уборные, which contain their кабины, get no контур; the eleven grouping parents such as
  «каб101вход», which are real rooms adjacent to their children, keep theirs. Non-overlap then
  holds by construction rather than by discipline.
- **Слой** is a named concept: a rule mapping each контур to a fill colour, a legend entry and
  a tooltip line, computed server-side. Stage 2 ships exactly one — тип помещения — derived
  from `is_leasable` / `is_common`, which are populated on all 82 помещения. `void`, `shaft`
  and `stairwell` render as a neutral outline with no fill and no legend entry.
- The four terms are defined in the project glossary: **Поэтажный план**, **Контур**, **Слой**,
  and a rewritten **Помещение** stating that the tree link means either containment or
  grouping, with occupied area as the discriminator.

### Upload and parsing

- The SVG is authored externally with `id` attributes equal to `Space.code`, and **parsed on
  upload** into контур rows. One action produces the file and its whole contour set, from one
  source, in one coordinate space — which is the only thing that keeps a план and its контуры
  from drifting, given that they are versioned together.
- The parse is **atomic with the план**: either the план and its контуры are created together
  or neither is.
- **Unmatched path** (an `id` with no помещение on this floor) and **missing контур** (a
  помещение on this floor with no path) are both **reported, not fatal**. Rejecting the upload
  would mean a план cannot be loaded until the space tree is perfect, and the план is the
  instrument for discovering that it is not.
- A file that cannot be parsed as SVG, or that carries no `viewBox`, is rejected with a reason.
- The uploader supplies the date the планировка took effect. An upload whose period overlaps an
  existing план for that floor is rejected. Automatic closure as of the upload date is
  explicitly rejected: it records a перепланировка as having happened on an administrative day,
  the same class of invented fact as the `year_built = 1900` that stage 1 migrated away.

### Storage and access control

- The SVG is a `FileField` in a **protected media location**, served by a Django view that
  passes through the **same scoped-queryset chokepoint** as every other read path. There is
  **no nginx `/media/` location** — serving the file directly from nginx would hand another
  client's floor plan to anyone with the address, which is exactly the leak ADR 0001 exists to
  prevent.
- The media directory is a persisted bind mount alongside the SQLite database, so a redeploy
  does not discard uploaded планы. `deploy.sh` and the compose file gain the mount; the nginx
  vhost does not gain a location.
- Upload rights come from a new **`is_admin` flag on `OrgMembership`**, not from Django's global
  `is_staff`. Administrator-ness is per-организация — a сотрудник may administer client A while
  remaining an ordinary user of client B — which a global flag cannot express. This is ADR
  0001's argument applied unchanged. That all ten current users happen to be `is_staff` is an
  accident of seeding, not a decision to build on.
- This is the **first write path outside Django admin** in the project. It is deliberately a
  single form and nothing more.

### Screens and routing

- One new route, the floor: `/bc/<uuid>/floor/<uuid>/`. Карточка БЦ gains an **Этажи** section.
- Layout is **tree left, план centre, карточка right**. Дерево and план are two views of one
  selection, highlighting in both directions — this is what earns the tree its width instead of
  making it duplicate navigation, and it is the only way to reach the 35 помещения that have no
  контур and therefore cannot be clicked.
- The карточка помещения is a **rail in the page layout**, not an overlay. The ИИ-управляющий
  panel stays an overlay floating above everything including the rail, so the two stop competing
  for the right edge.
- The карточка shows код, наименование, подтип, тип помещения, площадь and position in the tree,
  with parent and children as links that move the rail. **No sections for документы or системы** —
  those tables are empty, and an empty accordion promising data that has no table is worse than
  its absence.
- **Coverage is counted in помещения, not м²**: «нанесено 47 из 82 помещений». A metric count
  would need the план's scale, which nothing declares, and would be wrong anyway for the 35
  помещения with no `area_m2`. No scale field is added on a guess.
- No synthetic «прочее» контур is drawn for the uncovered remainder of a floor. `man-f1` is 561 м²
  against 170 м² of modelled children; the gap is the finding, and inventing a polygon to fill it
  would be the `-1 м²` mistake in a new medium.
- Server-rendered Django templates, Tailwind + daisyUI, HTMX for the rail and Alpine for local
  interaction — the stage 1 stack unchanged. No API endpoints; DRF stays installed and unused.
- Interface language is Russian throughout, using the glossary terms.

### Explicitly not changed

- **The ИИ-управляющий panel is untouched** and continues to return its fixed reply. Stage 1
  shipped a shell to avoid designing retrieval before knowing the answering scope, and that has
  not changed; this stage creates the data the assistant will later read.
- **`Space.valid_from` / `valid_to` stay unused and keep their meaning** — when the помещение
  itself existed. Versioning `Space` rows was considered and rejected in ADR 0003: it would force
  every existing and future reference (`SpaceArea`, `SpaceRequirement`, `DocumentLink`,
  `SystemServesSpace`, any lease) to choose a version.

## Testing Decisions

### What makes a good test here

Tests exercise what a user can observe over HTTP: which планы render, what status code a file
request returns, which помещения the screen reports as drawn. They do not assert markup, CSS
classes, colour values or heading text — those change on every design pass and prove nothing.
This continues the seam stage 1 established rather than adding to it.

### Seams

**The HTTP boundary remains the primary seam**, via `pytest-django`'s client against named URLs,
authenticated as users with known `OrgMembership` rows — the same pattern as stage 1's suite.

**One new unit seam: the SVG parser.** It earns its own seam because its interesting cases are
malformed and adversarial inputs — missing `viewBox`, unmatched `id`, duplicate `id`, no paths at
all — which are painful to express as file uploads and would make the HTTP suite a file-fixture
factory. Stage 1's rule against extra seams was aimed at a one-shot data migration; this is
permanent code with a genuinely different failure surface.

Nothing else gets a seam. Контур rendering, слой colouring and rail behaviour are all observed
through the floor screen's response.

### Coverage

- **Tenancy on the screen** — a user in one организация requesting another's floor gets 404,
  matching stage 1's behaviour for a БЦ.
- **Tenancy on the file** — the SVG of another организация's план returns 404 through the serving
  view. This is the test this stage exists to not get wrong: a protected file served past the
  chokepoint is precisely the leak ADR 0001 was written against.
- **Anonymous access** — both the floor screen and the file redirect to login.
- **Superuser bypass** — a superuser reaches any организация's план.
- **Upload authorisation** — a member without `is_admin` cannot upload; one with it can.
- **Period overlap** — an upload overlapping an existing план for that floor is rejected and
  leaves the existing план in force.
- **Validity** — after uploading a план effective from a later date, the floor screen renders the
  план in force for today, and the superseded план keeps its own контуры.
- **Parse outcomes (unit)** — an unmatched `id` is reported rather than dropped; a помещение with
  no path counts into «не нанесено»; a file without a `viewBox` is rejected; a valid file yields
  one контур per matched path.
- **Atomicity** — a parse failure leaves no план and no контуры behind.
- **Smoke** — 200 from the floor screen with a план, and from a floor with помещения but no план.

### Deliberately untested

Bidirectional highlighting between дерево and план is client-side behaviour with no HTTP
observable; testing it would mean introducing a browser-driving seam for one interaction. Contour
non-overlap is not asserted against uploaded files — it is a property of how the SVG was authored,
and enforcing it would require polygon intersection maths that this stage has no other use for.

## Out of Scope

- **A контур editor.** Geometry is authored in an external SVG tool and imported. Building a
  tracing UI is a CAD problem, not this project's.
- **Scale and metric area from контуры.** The план declares no scale; coverage is counted in
  помещения. Adding a scale field would be guessing at what the УК's exports contain.
- **Слои beyond тип помещения.** Долги арендаторов, сроки договоров, обращения and неисправности
  систем all need tables that do not exist — there is no lease model, no debt, no ticket, and
  `BuildingSystem` is empty. Each arrives later as a new слой.
- **The ИИ-управляющий reading планы or слои.** The panel keeps its fixed reply.
- **Карточка помещения as its own page.** The rail carries everything `Space` holds; a dedicated
  screen waits until документы and системы have data.
- **Планы for the four БЦ with no interior.** They have no этажи to attach a план to and keep the
  stage 1 «не загружено» treatment.
- **Editing помещения.** The space tree stays read-only; Django admin remains the write path for
  everything except the план upload.
- **Multi-floor spaces.** The лифтовая шахта is recorded once, on floor 1, though it physically
  pierces all five. The (план, помещение) contour model can represent it on every floor; entering
  the missing rows is data work, not this stage's.
- **Поэтажные планы as PDF or raster.** SVG only — the import depends on paths carrying ids.
- **Search and filtering** on the floor screen.
- **Migrating from SQLite to PostgreSQL**, unchanged from stage 1.

## Further Notes

The state of the data this ships against, which shaped several decisions above:

- **Only Manhattan has an interior** — five этажи, 82 помещения. The other four БЦ have a паспорт
  and nothing inside, so this feature has exactly one building to prove itself on.
- **35 of 82 помещения have no `area_m2`**, and direct children of `man-f1` sum to 170 м² against
  a floor of 561. Коридоры and лифтовые холлы are largely unmodelled. This is why coverage is
  counted in помещения and why no «прочее» контур is drawn.
- **The `parent` FK carries two different relations.** Eleven nestings are grouping — «каб101вход»
  at 6.55 м² parents 30.09 м² of children, «Каб406» at 36.38 м² parents 99.63 м² — where the child
  is larger than the parent and the rooms are adjacent. Eight are containment: «УборнаяЖен» over
  its two кабины, on four floors, doubled for мужская. `CONTEXT.md` previously defined only the
  containment reading; it has been rewritten to state both, with occupied area as the discriminator.
- **`Space.valid_from` / `valid_to` are set on 0 of 105 rows.** The versioning columns exist but
  nothing versions, which is part of why ADR 0003 declined to build план history on top of them.

The modelling gaps stage 1 recorded remain open and untouched here: `BuildingSystem.building` is a
single FK and cannot express a system serving several БЦ, and `Asset` still does not exist behind
`AssetLink`, `AssetServesZone` and `AssetServesSpace`. Neither blocks this stage; both must be
resolved before real инженерные системы are loaded.

The decision this stage turns on is recorded in **ADR 0003** (контур принадлежит плану, а не
помещению); tenancy follows **ADR 0001** and the CSS build follows **ADR 0002**. The vocabulary
used throughout is defined in the project glossary.
