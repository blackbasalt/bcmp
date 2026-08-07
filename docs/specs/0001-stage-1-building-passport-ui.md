# Stage 1 — Building passport UI (Список БЦ + Карточка БЦ)

## Problem Statement

BCMP holds the паспорт здания for five БЦ managed by DownTown Management ТОО, plus 105
spaces, 699 стороны and the dictionaries behind them — and there is no way to look at any
of it. The templates directory is empty, so the login page raises an error and the site
cannot be entered at all; the only access to the data is Django admin, which shows raw
tables rather than a паспорт, exposes every БЦ to every logged-in user regardless of which
организация they work for, and prints placeholder values such as `-1` and `1900` as if
they were real measurements.

A сотрудник УК who wants to answer "what do we actually know about this building?" today
has to read the database. Before BCMP can become the ИИ-управляющий it is the first stage
of, a human has to be able to see — and trust — the same data the assistant will later
answer from.

## Solution

A small, read-only web interface over the data that already exists: log in, see the
бизнес-центры you have access to, open one, and read its паспорт здания.

Two screens. **Список БЦ** shows one card per building — name, address, класс, year,
общая площадь — and marks the buildings whose interior spaces have not been loaded, so an
empty building reads as "not loaded yet" rather than as a broken page. **Карточка БЦ**
shows the паспорт grouped into readable sections, with every known field present and
missing ones written out as «— нет данных», so the screen doubles as the list of what
still needs collecting.

Everything a user sees is scoped to their организация from the first query, and the
placeholder values in the data are cleaned up so that no screen ever shows a negative
area. A collapsed slide-over panel for the ИИ-управляющий ships alongside — wired end to
end but answering with a fixed reply — so that stage 2 changes an answer, not a layout.

## User Stories

### Access and tenancy

1. As a сотрудник УК, I want to log in with my username and password, so that I can reach
   the building data at all.
2. As a сотрудник УК, I want to be sent to the Список БЦ immediately after logging in, so
   that I start at the data rather than at a landing page.
3. As a сотрудник УК, I want to be redirected to the login page when I request any screen
   while logged out, so that nothing about our clients' buildings is visible to an
   anonymous visitor.
4. As a сотрудник УК, I want a clear message when my credentials are wrong, so that I know
   to retry rather than assume the site is down.
5. As a сотрудник УК, I want to log out from any screen, so that I can leave a shared
   workstation safely.
6. As a сотрудник УК, I want to see only the бизнес-центры belonging to организации I am a
   member of, so that I never see another client's portfolio.
7. As a сотрудник УК working for two clients, I want membership in more than one
   организация under a single login, so that I do not need a second account.
8. As a сотрудник УК, I want a request for a БЦ outside my организации to behave exactly
   like a request for a building that does not exist, so that the response cannot be used
   to confirm another client's data is present.
9. As a newly created user with no access assigned yet, I want an empty list with an
   explanation pointing me at the administrator, so that I do not think the system is
   broken.
10. As a разработчик holding a superuser account, I want to see every организация's data,
    so that I can reproduce a client's problem without granting myself their membership.
11. As an администратор платформы, I want to grant and revoke a user's access to an
    организация from Django admin, so that onboarding does not require a developer.

### Список БЦ

12. As a сотрудник УК, I want a card for each бизнес-центр I have access to, so that I can
    see the whole portfolio at a glance.
13. As a сотрудник УК, I want each card to show наименование, адрес, класс, год постройки
    and общая площадь, so that I can tell the buildings apart without opening them.
14. As a сотрудник УК, I want a card whose паспорт lacks a value to show «— нет данных» in
    that place, so that the card never shows a blank I might read as zero.
15. As a сотрудник УК, I want a badge on any БЦ whose помещения have not been loaded, so
    that I can tell an empty building apart from a rendering failure.
16. As a сотрудник УК, I want to open a бизнес-центр by clicking its card, so that I do not
    have to find it in a menu.
17. As a сотрудник УК, I want the list to work on a laptop screen without horizontal
    scrolling, so that I can use it in a meeting.

### Карточка БЦ

18. As a сотрудник УК, I want the паспорт split into Идентификация, Характеристики,
    Конструктив и безопасность, and Стороны, so that I can find a field without reading
    the whole page.
19. As a сотрудник УК, I want to see адрес, кадастровый номер, инвентарный номер and
    назначение together, so that I can match this building against an external registry.
20. As a сотрудник УК, I want to see площади, этажность, объём, год постройки and класс
    together, so that I can answer the questions a tenant or valuer asks most often.
21. As a инженер УК, I want to see материал стен, конструктивная схема, степень
    огнестойкости, пожарные классы, сейсмичность and энергокласс together, so that I can
    check the building against a norm without opening the paper паспорт.
22. As a сотрудник УК, I want to see собственник, управляющая компания, проектировщик and
    подрядчик by name, so that I know who to contact about this building.
23. As a сотрудник УК, I want every field in a section shown even when it is empty, marked
    «— нет данных», so that the screen tells me what still has to be collected.
24. As a сотрудник УК, I want a section hidden when it is entirely empty, so that a
    sparsely filled паспорт does not become a wall of dashes.
25. As a сотрудник УК, I want этажность rendered exactly as recorded — including forms like
    «4+тех.этаж» — so that I read what the technical паспорт actually says.
26. As a сотрудник УК, I want residential fields such as количество квартир and жилая
    площадь kept off the screen, so that a commercial паспорт is not padded with lines that
    never apply.
27. As a сотрудник УК, I want to return to the Список БЦ from any паспорт, so that I can
    move between buildings quickly.

### Data quality

28. As a сотрудник УК, I want a building with no recorded общая площадь to say «— нет
    данных» rather than «-1 м²», so that I am never shown a placeholder as a measurement.
29. As a сотрудник УК, I want a building with no recorded год постройки to say «— нет
    данных» rather than «1900», so that I do not plan work around an invented date.
30. As a разработчик, I want the placeholder values removed from the database rather than
    hidden in the templates, so that every later consumer — including the ИИ-управляющий —
    reads absence as absence.
31. As a разработчик, I want a бизнес-центр larger than 10 000 м² to save without error, so
    that loading a real portfolio does not fail on the field definition.

### ИИ-управляющий (shell only)

32. As a сотрудник УК, I want a button that opens the ИИ-управляющий panel over the current
    screen, so that asking a question does not cost me the page I am reading.
33. As a сотрудник УК, I want the panel closed by default, so that the паспорт keeps the
    full width of the screen.
34. As a сотрудник УК, I want my sent message and the reply to appear in the panel without
    a page reload, so that the interaction feels like a conversation.
35. As a сотрудник УК, I want my messages to still be there after I navigate to another БЦ,
    so that the panel behaves like a conversation rather than a form.
36. As a разработчик, I want the panel wired end to end against a fixed reply, so that
    stage 2 replaces the answer without redesigning the interface.

### Operations

37. As a разработчик, I want the container to start successfully with the compiled CSS in
    place, so that a deploy produces a styled site rather than an unstyled one.
38. As a разработчик, I want the CSS built during the image build, so that nobody can ship
    a stale stylesheet by forgetting to rebuild it.

## Implementation Decisions

### Scope shape

- Stage 1 is **read-only**. All create/update/delete stays in Django admin. No forms ship
  beyond login.
- Two screens plus the authentication shell: **Список БЦ**, **Карточка БЦ**, login page,
  base layout with navigation and a messages area.
- No DRF endpoints. `djangorestframework`, `drf-spectacular` and `django-filter` are
  installed but stay unused — the ИИ-управляющий panel talks to a plain Django view.
  Designing an API before knowing what the assistant asks for means designing it twice.

### Domain mapping

- A **БЦ** is a `Space` of type `building`; the **Проект** is the `Space` of type
  `project` that groups them; the **Площадка** is the `site` between them. Only БЦ appear
  in navigation — навигация is flat. Проект is shown as a label, not as a level to click
  through, and Площадка does not appear at all in stage 1 (it stays in the model as a real
  object with its own rights and boundaries).
- The **паспорт здания** is `BuildingPassport`, one per БЦ via its one-to-one link to
  `Space`.
- Buildings with no child spaces are a normal state, not an error: four of the five current
  БЦ have a паспорт and no interior.

### Tenancy (per ADR 0001)

- A new **`OrgMembership`** model joins `User` to `Org` many-to-many, replacing the absent
  user→organisation link. A user may belong to several организации.
- All read paths pass through **one scoped-queryset chokepoint** rather than per-view
  filtering. Views ask for "the spaces this request's user may see"; they do not compose
  organisation filters themselves.
- `is_superuser` **bypasses** the scoping entirely.
- A user with no membership sees an empty list and an explanatory message — never a 403,
  and never unscoped data.
- A БЦ outside the user's организации returns **404**, not 403.
- A data migration creates the `Org` over the existing `DownTown Management ТОО` Party
  (БИН 180540035878, already the `operator_party` on all five паспорта), assigns it to all
  105 spaces, and grants membership to the existing 10 users.

### Data migrations

- Placeholder values become NULL: `-1` on `total_area`, `building_footprint`,
  `building_volume`; `''` on `number_of_floors`; `-1` on `apartments_number` for all five
  паспорта. `year_built = 1900` becomes NULL **only where `total_area` was `-1`**, so a
  genuinely old building is not caught by a later re-run.
- `total_area` and `building_footprint` widen from `max_digits=6` to `max_digits=12`,
  matching `Space.area_m2`. The current definition caps area at 9 999,99 м², which any real
  бизнес-центр will exceed.
- `number_of_floors` **stays text**. The технический паспорт records forms like
  «4+тех.этаж» that an integer cannot hold, and the structured `floors_above` /
  `floors_below` fields are NULL everywhere. It is displayed verbatim, not parsed.
- Residential columns are **hidden in the template, not dropped**. The source form (Ф-2)
  contains them; removing columns is the irreversible direction.

### Presentation

- Server-rendered Django templates in the root templates directory (the configured
  `TEMPLATE_DIR`), not per-app template directories — one `base.html`, one location.
- **Tailwind + daisyUI** for styling, single light theme, no dark mode toggle. **HTMX** for
  the ИИ-управляющий panel; **Alpine.js** for local interactions such as opening and
  closing it. No `django-crispy-forms` — a form library plus a template pack to style two
  login inputs is a dependency with no current benefit.
- CSS is compiled by a **Node stage in a multi-stage Docker build** whose output is copied
  into the Python runtime image (ADR 0002). The runtime image keeps no Node.
- `STATIC_ROOT` must be set — it is currently commented out while the entrypoint runs
  `collectstatic`, so the container cannot start today.
- Missing values render as a single shared convention, «— нет данных», applied wherever a
  паспорт field is NULL.
- The list is cards, not a table. No search and no filters at five buildings.
- Interface language is Russian throughout, using the terms in the glossary.

### Routing and configuration

- The building passport app declares `app_name = "building_passport"`, and the project URL
  configuration includes it **without** an overriding `namespace` argument — today the app
  declares `bp` while the include declares `building_passport`.
- The duplicate route registered twice under the same path (as both `home` and `board`)
  collapses to one.
- Routes: `/` → Список БЦ, `/bc/<uuid>/` → Карточка БЦ.
- `LOGIN_REDIRECT_URL` points at the Список БЦ. It currently points at the login page
  itself.

### ИИ-управляющий panel

- A floating button opens a slide-over. The panel is not a persistent rail — the паспорт
  keeps full width.
- Messages POST to a plain Django view over HTMX, which returns a fixed reply and appends
  it to the conversation.
- History lives in **`request.session`** — no `Conversation` or `Message` model. Session
  storage proves the behaviour that matters (context surviving navigation between БЦ)
  without committing to what a conversation is scoped to before that is known.

## Testing Decisions

### What makes a good test here

Tests exercise what a user can observe over HTTP: which buildings appear, what status code
comes back, whether a message survives navigation. They do not assert markup, CSS classes,
or the text of headings — those change on every design pass and prove nothing. They do not
call the scoped queryset, instantiate view classes, or import template tags; behaviour is
verified through requests, so that a refactor below the URL layer does not rewrite the
suite.

### Seam

**One seam: the HTTP boundary**, via `pytest-django`'s test client against named URLs,
authenticated as a user with known `OrgMembership` rows. There is no prior art — the repo
currently contains no tests at all — so this establishes the pattern for everything that
follows. `pytest-django` is already a dev dependency.

### Coverage

- **Org isolation** — a user in one организация does not see another's БЦ in the list, and
  requesting it directly returns 404. This is the test the tenancy work exists for; it
  covers both screens.
- **Superuser bypass** — a superuser sees all five БЦ.
- **No membership** — a logged-in user with no `OrgMembership` gets 200 and an empty list,
  not 403 and not unscoped data.
- **Authentication** — an anonymous request to either screen redirects to login; valid
  credentials land on the Список БЦ.
- **Smoke** — 200 from Список БЦ and Карточка БЦ. Rendering the templates is the point:
  this catches template syntax errors and missing context variables without asserting
  content.
- **ИИ-управляющий panel** — a POST returns the canned reply, and a second POST shows the
  first message still present, proving session-backed history.

### Deliberately untested

The data migration is verified by inspecting the five паспорта after it runs, not by an
automated test. Adding a second seam — extracting the transformation into a separately
callable function purely so it can be unit-tested — was considered and rejected: the rule
is conditional on a single field across five rows in a one-shot migration, and the seam
would outlive the code it protects.

## Out of Scope

- **Дерево помещений and Карточка помещения.** The 82 помещения under Manhattan have no
  presence in stage 1 beyond the "not loaded" badge distinguishing buildings that have
  them. Deferred to stage 2, where the тип помещения breakdown (арендопригодные / МОП /
  технические) becomes meaningful.
- **Поэтажный план.** No plan images exist.
- **Документы.** The document tables are empty.
- **Дашборд.** `Space.status`, `SpaceArea` and `SpaceRequirement` are all empty; an
  aggregate screen would render zeros.
- **Editing anything.** Django admin remains the only write path.
- **A public or internal API.**
- **A real ИИ-управляющий.** Retrieval design, model choice and prompt work are stage 2;
  stage 1 ships the shell and a fixed reply.
- **An organisation switcher UI.** Membership is granted in admin; scoping applies to all
  of a user's организации at once.
- **Dark mode, theming, branding.**
- **Search and filtering** on the Список БЦ.
- **Migrating from SQLite to PostgreSQL.** `psycopg` is installed and unused; the deploy
  runs SQLite on a persisted mount.

## Further Notes

Two modelling gaps were identified during design and deliberately left open, because
neither blocks stage 1 and both need data that does not exist yet:

- **A system serving several БЦ cannot be represented.** `BuildingSystem.building` is a
  single foreign key, but a Проект is defined as combining systems that serve several
  buildings and площадки. Pointing `building` at the проект `Space` would make the field
  mean two different things. This needs resolving **before** real инженерные системы are
  loaded — the tables are currently empty.
- **`Asset` does not exist.** `AssetLink`, `AssetServesZone` and `AssetServesSpace` each
  carry a bare `asset_id` UUID with no foreign key, and `DictElementCategory` /
  `DictConditionGrade` are empty dictionaries waiting on a конструктив model
  (`BuildingElement`) and its surveys and repairs, which `DocumentLink` already enumerates
  as linkable entity types. Assets are owned by BCMP, not an external registry, so this is
  work this project has to do.

The `site` layer is retained deliberately. It contributes nothing to stage 1 navigation —
five площадки each holding exactly one building — but a площадка is a real объект
недвижимости with its own rights and boundaries and can hold more than one building, so
collapsing the layer is a one-way door.

The related decisions are recorded in ADR 0001 (tenant scoping) and ADR 0002 (CSS build
pipeline); the vocabulary used throughout this spec is defined in the project glossary.
