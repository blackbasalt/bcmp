"""No models. The полка помещений shows `Space` of type `room`, and `Space` lives in
`building_passport` — this app imports it, exactly as `documents` does.

An app without models looks like an oversight, so the reason stands here as well as in
ADR 0016: a раздел of the menu is a Django app. Which раздел is open is worked out once for
the whole menu as `request.resolver_match.app_name` (`templates/shell.html`), so an app is
what the highlight holds on to. Put the полка inside `building_passport` and a reader
standing on «Помещения» sees «Бизнес-центры» lit up, while the third item never lights at
all — and not one test about the полка itself would fail.

`rooms` and not `spaces`: the полка shows помещения alone, while `Space` also holds the
проект, the площадка, the здание, the этаж and the шахта. The word is already bound in the
code — `DictSpaceType.ROOM = "room", "Помещение"`.
"""
