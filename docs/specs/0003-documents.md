# Stage 3 — Документы (раздел документов и близнецы для ИИ-управляющего)

## Problem Statement

Stage 1 made the паспорт здания readable and stage 2 opened the building up, but everything
BCMP holds is structured data someone typed into a form. The bumaga that the structured data
came *from* — акты, сертификаты, протоколы замеров, разрешения, исполнительная документация —
is not in the system at all.

`Document` and `DocumentLink` have existed since the first migrations and hold **zero rows**.
Nothing has ever exercised them, and the schema records assumptions nobody has tested: `file_uri`
is a `TextField` while `FloorPlan` stores its чертёж in a `FileField` under a protected media
location, so the project carries two incompatible stories about where an uploaded file lives.
Four of the nine `DocumentLink.EntityType` values — `asset`, `building_element`,
`element_survey`, `element_repair` — point at tables that do not exist. `building_system` points
at a table with an integer primary key while `entity_id` is a `UUIDField`, so that link cannot be
formed at all. The polymorphic admin mixins default `entity_type` to the model's `db_table`
(`building_passport_space`), which is never one of the declared choices.

Meanwhile the УК has **hundreds of digital documents and more**, laid out as a folder tree by
building. They are reachable by whoever knows the network path and by nobody else. There is no
answer to "покажите бумаги по Manhattan" and no answer to "есть ли у нас вообще акт на это".

There is a second problem behind the first. The ИИ-управляющий — the reason the whole platform
exists — answers every question with `CANNED_REPLY` and has nothing to read but structured
fields. The knowledge that actually answers a manager's questions is prose locked inside scanned
PDFs. Before an assistant can read those documents, they have to be *in* the system, and a
machine-readable rendition of each has to have somewhere to live.

## Solution

A **Документы** section — a second item in the sidebar next to Бизнес-центры, and the first
screen in the project that is not reached through a building.

It is a table of every документ visible to the signed-in сотрудник: вид, название, номер, дата
выдачи, кем выдан, and whether the документ has a близнец. An администратор организации uploads
**in batches** — hundreds of files in one submission, with вид документа and, optionally, the БЦ
chosen once for the whole batch. Files land in the same protected media location as поэтажные
планы and are served by a view through the same chokepoint, so a scanned договор cannot be
fetched by guessing an address.

Each документ has a slot for a **близнец**: its content rendered to markdown for the
ИИ-управляющий to read, together with the images extracted from it. BCMP **stores** близнецы and
does not produce them — it has no PDF parser, no OCR and no markdown library, and acquiring them
is a different stage's problem. The slot exists now because the alternative is a second pass over
the same pile of hundreds of files later.

And the screen counts what it has not got: **«близнец есть у 12 из 340 документов»**, plus how
many документы are attached to no БЦ. This is the stage-2 trick — «нанесено 47 из 82» — applied
to a shelf that starts empty. A storage stage has no other way to be checked, and an honest
«0 из 340» is a true statement about an empty shelf.

## User Stories

### Навигация

1. As a сотрудник УК, I want a Документы item in the sidebar, so that documents are reachable
   without going through a building first.
2. As a сотрудник УК, I want the Документы item highlighted while I am anywhere in that section,
   so that I can see where I am.
3. As a сотрудник УК, I want the Бизнес-центры item to stay highlighted while I am inside a
   building, so that adding a second section does not break the first.
4. As a сотрудник УК, I want a link from a Карточка БЦ to the документы of that building, so
   that «что у нас по Manhattan» has an answer.
5. As a сотрудник УК, I want that link to open the документы section already filtered to the
   building, so that I do not have to filter it myself.
6. As a сотрудник УК, I want to see from the filtered view which building I am looking at, so
   that I do not mistake a filtered list for the whole shelf.
7. As a сотрудник УК, I want to clear the building filter from within the section, so that I can
   get back to everything without navigating away.

### Таблица документов

8. As a сотрудник УК, I want a table of all документы of my организация, so that I can see what
   the УК holds in one place.
9. As a сотрудник УК, I want each row to show вид документа, so that акты and сертификаты are
   distinguishable at a glance.
10. As a сотрудник УК, I want each row to show название, so that I can recognise a документ
    without opening it.
11. As a сотрудник УК, I want each row to show номер and дата выдачи, so that I can tell two
    similar акты apart.
12. As a сотрудник УК, I want each row to show кем выдан, so that I can find everything issued by
    one подрядчик.
13. As a сотрудник УК, I want fields that were never filled in to read «— нет данных», so that an
    empty field is visibly empty rather than ambiguous.
14. As a сотрудник УК, I want the newest uploads at the top, so that a batch I just uploaded is
    where I am looking.
15. As a сотрудник УК, I want to search by название and номер, so that I can find a документ I
    know the name of.
16. As a сотрудник УК, I want to filter by вид документа, so that I can see all сертификаты at
    once.
17. As a сотрудник УК, I want to filter by БЦ, so that I can see the documents of one building.
18. As a сотрудник УК, I want to open a документ's own page from its row, so that I can see
    everything recorded about it.
19. As a сотрудник УК, I want to download the original file from the документ, so that I can read
    the actual scan.
20. As a сотрудник УК, I want the table to state how many документы it is showing, so that a
    filter that matched nothing is distinguishable from an empty shelf.

### Пакетная загрузка

21. As an администратор организации, I want to upload many files in one submission, so that
    moving hundreds of documents does not take hundreds of submissions.
22. As an администратор организации, I want to choose вид документа once for the whole batch, so
    that I am not asked the same question two hundred times.
23. As an администратор организации, I want to choose the БЦ once for the whole batch, so that a
    folder of one building's documents lands attached to that building.
24. As an администратор организации, I want to leave the БЦ unset, so that the устав and the
    лицензия, which belong to no building, can still be uploaded.
25. As an администратор организации, I want the название taken from the file name, so that I do
    not have to type a name for each of two hundred files.
26. As an администратор организации, I want to leave номер, дата выдачи and кем выдан empty at
    upload, so that a bulk transfer is not blocked by facts only the scan knows.
27. As an администратор организации, I want to fill those fields in later from the документ's
    page, so that a batch can be enriched over time.
28. As an администратор организации, I want the good files in a batch to be saved even when some
    are rejected, so that one bad file does not force me to re-upload ninety-nine good ones.
29. As an администратор организации, I want the rejected files listed by name with the reason, so
    that I know exactly what to fix.
30. As an администратор организации, I want a file whose content is already stored to be reported
    as a duplicate rather than rejected as an error, so that overlapping folders do not look like
    failures.
31. As an администратор организации, I want the duplicate report to name the документ the file is
    already stored as, so that I can go and look at it.
32. As an администратор организации, I want a file of an unaccepted format to be refused with its
    format named, so that I understand why.
33. As an администратор организации, I want an oversized file refused with the limit stated, so
    that I know what the limit is.
34. As an администратор организации, I want a batch larger than the per-submission limit refused
    before anything is stored, so that I split it rather than discovering a partial upload.
35. As an администратор организации, I want to see how many files were stored after a batch, so
    that I can reconcile against the folder I uploaded.

### Близнец

36. As an администратор организации, I want to attach a маркдаун-близнец to a документ, so that
    the ИИ-управляющий has something it can read.
37. As an администратор организации, I want to attach близнецы as part of a batch, matched to
    their документы by file name, so that a converted folder can be loaded in one go.
38. As an администратор организации, I want to attach a близнец to a single документ from its
    page, so that a one-off conversion does not require a batch.
39. As an администратор организации, I want to attach the images the близнец refers to, so that
    the схемы inside a документ are not lost.
40. As an администратор организации, I want an image reference in the близнец that has no
    matching image reported, so that I know the близнец is incomplete.
41. As a сотрудник УК, I want to see on the документ that it has no близнец, so that a document
    the ИИ-управляющий cannot read is identifiable.
42. As an администратор организации, I want to replace a близнец, so that a better conversion can
    supersede a worse one.
43. As an администратор организации, I want replacing a близнец to discard the previous images,
    so that the store does not accumulate orphans from earlier conversions.
44. As an администратор организации, I want to remove a близнец without touching the документ, so
    that a bad conversion can be withdrawn while the original scan stays.
45. As a сотрудник УК, I want to download a близнец, so that I can check what the
    ИИ-управляющий would be reading.

### Доступ и изоляция

46. As a сотрудник УК, I want to see only the документы of my организация, so that another
    client's papers never appear in my list.
47. As a сотрудник УК of two организации, I want each организация's документы shown under that
    организация, so that the two clients stay separate.
48. As a сотрудник УК without the administrator flag, I want to read the section and open files,
    so that a shelf I may not write to is still a shelf I can use.
49. As a сотрудник УК without the administrator flag, I want no upload form offered, so that I am
    not invited to do something that will be refused.
50. As an администратор организации, I want the upload form on the section screen, so that
    uploading does not require the Django admin.
51. As an администратор of one организация, I want to remain an ordinary reader of another, so
    that administering client A grants nothing over client B.
52. As a сотрудник УК, I want a request for another организация's file to be missing rather than
    forbidden, so that the address does not confirm that the document exists.
53. As an anonymous visitor, I want a request for the section or a file to send me to the login
    screen, so that nothing leaks before I sign in.
54. As a сотрудник УК, I want files served through the application rather than from a guessable
    address, so that a scanned договор cannot be fetched by anyone who guesses a URL.
55. As a сотрудник УК, I want documents served so that they cannot execute in the browser as part
    of the site, so that an uploaded file cannot act as a page.

### Удаление

56. As an администратор организации, I want to delete a документ, so that a mistaken upload can
    be undone.
57. As an администратор организации, I want deleting a документ to take its близнец, its images
    and its stored files with it, so that nothing is left behind.
58. As a сотрудник УК without the administrator flag, I want deletion not offered, so that the
    shelf is not editable by readers.
59. As an администратор организации, I want to be asked to confirm before a deletion, so that a
    misclick does not destroy an upload.

### Пустые состояния и находки

60. As a сотрудник УК, I want an empty section to say so plainly, so that I can tell "nothing
    uploaded yet" from "something is broken".
61. As an администратор организации opening an empty section, I want the upload form to be the
    thing I see, so that the empty state is where the absence is noticed.
62. As a сотрудник УК, I want the section to state how many документы have a близнец out of how
    many exist, so that I can see how much of the shelf the ИИ-управляющий can read.
63. As a сотрудник УК, I want that count to read «0 из 340» when no близнецы exist, so that the
    absence is stated rather than hidden.
64. As a сотрудник УК, I want the section to state how many документы are attached to no БЦ, so
    that documents nobody assigned are findable.
65. As a сотрудник УК, I want to open exactly the документы behind either count, so that a number
    leads to the work rather than just reporting it.

## Implementation Decisions

### Domain model

- **Документ** is added to the glossary as *a file attached to an entity of the паспорт*, with
  the discriminator stated explicitly: **nothing is computed from a документ**. Anything that
  carries state of its own is an entity, and a документ is attached to it. This is why a договор
  аренды is an entity with its own предмет rather than a документ of вид `contract`, and why a
  поэтажный план is not a документ: план shows, документ attests.
- **Близнец** is added to the glossary as *the content of a документ rendered to markdown for
  machine reading, together with the images extracted from it*. There is at most one per
  документ, and having none is the ordinary state.
- A близнец is a **separate entity, one-to-one with the документ**, with images as its child
  rows — not fields on `Document`. A близнец is replaced whole, together with its images, while
  the документ does not change; as a row, replacement is a delete and an insert and the images
  follow by cascade. As fields, the images would need manual cleanup and the first missed cleanup
  leaves orphans in the store. Recorded in **ADR 0007**.
- `Document.org` becomes **mandatory** and `Document` gains its own scoped-queryset chokepoint.
  This deliberately diverges from `FloorPlan`, which has no `org` and inherits visibility from
  its этаж. A документ may have several link targets or none, and Стороны are a system-wide
  register — 699 of them against one организация — so inheriting visibility would show a
  tenant's договор to every client that can see that Сторона, and would hide an unlinked документ
  from everyone. Recorded in **ADR 0006**; the ADR exists so that the next developer does not
  "unify" documents with планы and reopen the leak.
- All **fourteen** values of `Document.Kind` are kept. The list is closed and drawn from real
  nomenclature; a spare value costs nothing while a missing one sends everything to `other`.
  `contract` now means *a scan of a договор*, not the договор itself.
- `page_count` is **removed**. It requires parsing a PDF to produce a number nobody asked for,
  and as an always-empty column it would misrepresent itself as a fact the system knows.
- `file_uri` as a `TextField` is **replaced by a `FileField`**. `file_hash` is kept and computed
  on upload; at the scale of this transfer it pays for itself immediately by catching the same
  scan uploaded from two folders.
- `valid_until` and `revision` are kept as **fields with no behaviour** — filled in, displayed,
  triggering nothing. The партиальный index on `valid_until` stays: it costs nothing and will be
  wanted when a реестр сроков is actually commissioned. No superseded-by relation between
  документы is built: with zero документы stored, any shape for it is a guess.

### Привязка

- `DocumentLink` is used with **exactly one** `entity_type` — `space`, pointing at a БЦ. The
  other eight are left untouched; the stage that introduces an entity introduces its link type,
  which is the pattern the reverted lease branch already followed when it added its own.
- A привязка is **optional and may be plural**. The uniqueness constraint already sits on
  (документ, тип, сущность) rather than on the документ, so nothing in the schema resists this.
  Making it mandatory would force the устав and a подрядчик contract covering every object to be
  filed under an arbitrary building.
- `DocumentLink.role` is kept but **defaulted and not asked for** at upload. The five roles —
  основной / основание / подтверждение / справочно / устаревший — describe a документ as
  evidence, which serves a purpose this stage does not have; the person moving a folder of scans
  cannot be expected to choose between them. If in six months every привязка is *основной*, the
  roles were premature and the data will say so.
- Batch upload **does not parse file paths**. The БЦ is chosen once per submission from a list.
  The "contract in the name" trick works for планы because we tell the author to put `Space.code`
  in the path `id`; the УК's folders predate BCMP and match neither `code` (`man`) nor `name`
  (`Manhattan`). Recorded in **ADR 0008**.

### Хранение и доступ

- Files are stored in the **same protected media location** as поэтажные планы, with `MEDIA_URL`
  left unset, and served by views that pass through the документ chokepoint. This covers the
  original file, the близнец and each of its images. No nginx `/media/` location is added.
- Images of a близнец are addressed **by name, not by URL**. The markdown refers to
  `![](p3-img1.png)`; resolution against the stored images happens at upload, and whoever later
  displays a близнец to a human is responsible for turning names into addresses. The
  ИИ-управляющий, which reads text, needs nothing here.
- Files are served with the same sandboxing headers already applied to план files, so an
  uploaded file cannot act as part of the site.
- Write rights come from the existing **`is_admin` flag on `OrgMembership`** and the
  `administered_by` chokepoint introduced for план upload in ADR 0005. No new permission
  mechanism. The difference from планы is only *where* the form stands: планы are uploaded from
  the экран этажа, документы from the документы section.
- Deletion is available to the администратор организации, removes the документ together with its
  близнец, images and stored files, and is confirmed first. **No soft delete**: no entity in this
  project has one, and introducing it here would create two different lifecycles.

### Пакетная загрузка

- One submission carries **files, вид документа and, optionally, БЦ**. Название comes from the
  file name; номер, дата выдачи, кем выдан, срок and ревизия stay empty and are edited later.
- The batch is **partial-success**: good files are stored, rejected ones are listed by name with
  a reason. All-or-nothing would mean re-uploading ninety-nine good files because of one bad one.
- A **`file_hash` match is a message, not an error** — "этот файл уже загружен как …". When an
  archive with overlapping folders is transferred, duplicates are the norm.
- Accepted formats are **PDF and images** (JPEG, PNG), with a per-file limit of **50 MB** and a
  per-submission limit of **200 files**. The submission limit is checked before anything is
  stored, so an oversized batch is split rather than half-applied.
- Близнецы may arrive in the same batch and are matched to their документы **by file name**
  (`akt-2024-03.pdf` ↔ `akt-2024-03.md`), with images matched to the близнец that references
  them. A близнец whose документ is not in the batch is reported, not stored.
- The близнец's image references are **parsed on upload** and unresolved ones are recorded and
  displayed — the same treatment `unmatched_ids` gets on a поэтажный план. A близнец must be
  complete: one broken reference means the model reads the документ without its схема and never
  learns that it did.

### Экраны и адреса

- A new URL namespace under `/documents/`, so that the sidebar highlight can distinguish the two
  sections. The highlight condition in the shell template currently hardcodes the building
  passport namespace and is generalised to cover both.
- The section screen carries the table, the filters, the two counts and — for an администратор —
  the upload form. A документ has its own page for its fields, its file, its близнец and its
  привязки.
- The Карточка БЦ gains **a link**, not a table. A second table on the building card would bring
  its own sorting, its own empty state and its own pagination for a question the section already
  answers.
- Markup contract, in the manner already established for планы: `data-document` on a table row,
  `data-twin` on the близнец indicator, `data-upload` on the upload form, `data-unmatched` on an
  unresolved image reference. These are the handles the tests read.

### Explicitly not changed

- `FloorPlan` keeps its own storage and its own visibility rule. The divergence is deliberate and
  documented rather than harmonised.
- `BuildingSystem` keeps its integer primary key. Changing the key of an empty table is cheap,
  but choosing its shape belongs to the stage that models инженерные системы, not to this one.
- The `assistant` app is untouched. Nothing in this stage makes the ИИ-управляющий read anything;
  it stocks the shelf the reader will later use.
- The eight unused `EntityType` values, the polymorphic admin mixins and their `db_table` default
  are left as they are.

## Testing Decisions

### What makes a good test here

A test states what a сотрудник can observe: what the screen says, what status a request gets,
what survives in the database after a rejection, and what another организация cannot see. It does
not reach into how a batch is iterated, how a hash is computed or how a form is assembled.
Counts are asserted as the sentence the screen prints, not as an internal number.

### Seams

**One seam: the HTTP boundary.** Tests sign in as a user with known membership and drive the
section with the test client, exactly as the существующие screen tests do. This covers the table
and its empty state, both counts, batch upload including partial rejection, the file-size and
batch-size limits, the duplicate-hash message, file serving through the chokepoint, the absence
of the form for a non-administrator, deletion, the link from the Карточка БЦ, and client
isolation.

**No second seam below HTTP.** The project has exactly one — SVG parsing — and it is justified in
its own docstring by the fact that the interesting cases there are corrupt and hostile files.
Extracting `![](…)` references from markdown is a regular expression whose interesting cases (a
reference with no image, an image with no reference, repeated names) are expressible through a
batch upload without turning the suite into a fixture factory. If that parse later grows real
failure modes, the precedent for splitting it out is already written down.

**One fixture change.** The организация-administrator fixture currently lives inside the план
upload tests and is needed here too; it moves to the root `conftest.py`, for the same reason
`manhattan` lives there — two definitions of the same thing drift apart. The existing `downtown`,
`central`, `member` and `manhattan` fixtures are reused unchanged.

### Prior art

- Screen behaviour and markup contracts: the поэтажный план tests, which read `data-*` handles
  rather than markup structure.
- Upload, permissions and rejection: the план upload tests — form presence for an administrator,
  absence for a reader, status codes, and what remains in the database after a refusal.
- Client isolation: the scoping tests, and the plan tests asserting that another организация's
  file is missing rather than forbidden.

### Coverage

Each user story above is reachable from the HTTP seam. Particular attention to: a batch where one
file of many is rejected; a batch that exceeds the submission limit and stores nothing; a
duplicate hash reported without failing the batch; a близнец matched by name and one that matches
nothing; an unresolved image reference surfacing on screen; replacing a близнец discarding the
previous images; both counts stated when their value is zero; and every read path attempted by a
member of another организация.

### Deliberately untested

The exact wording of rejection messages, the ordering of the rejected-file list, and the
appearance of the table. Whether a PDF is genuinely a PDF beyond its declared format — this stage
does not parse documents.

## Out of Scope

- **Producing близнецы.** No PDF parsing, no OCR, no conversion of any kind. BCMP stores what it
  is given.
- **Reading близнецы.** The ИИ-управляющий keeps its canned reply; wiring it to documents is a
  later stage.
- **Full-text search** over document content. Search is by название and номер only.
- **A реестр сроков.** `valid_until` is stored and displayed and triggers nothing — no expiry
  screen, no warnings, no counts of what is overdue.
- **Evidence roles.** Роли привязки are stored with a default and not surfaced.
- **Versioning** of документы or близнецы. One близнец per документ, replaced in place.
- **Attaching документы to помещения, Стороны, зоны, инженерные системы or требования.** Only to
  a БЦ, and only chosen per batch.
- **Fixing `BuildingSystem`'s primary key** so that documents could later attach to systems.
- **ZIP upload and any interpretation of folder structure.**
- **Office formats** (DOCX, XLSX) — not accepted until it is known that the archive contains them.
- **Soft deletion, audit trail of who downloaded what, and sharing documents between организации.**

## Further Notes

The risk this stage carries is stated openly: it is checked by a count of близнецы, and today
nothing in the project can produce one. If none is ever attached, the screen will honestly read
«0 из 340». That is a true statement about an empty shelf, and it is still a better instrument
than a stage that reports nothing at all — the same instrument as «нанесено 47 из 82», which was
the sharpest thing stage 2 produced.

The three decisions this stage turns on are recorded as ADR 0006 (visibility by the документ's
own организация), ADR 0007 (близнец stored but not produced) and ADR 0008 (batch upload does not
parse paths). Each was chosen against a plausible alternative, and each will look wrong to a
reader who does not know why.

Numbering note: the reverted lease branch used ADR numbers 0006–0010. Those files are not in the
tree; the numbers are reused.
