"""How the раздел «Стороны» reads on screen: how much of the полка is shown, what a Сторона
rents, what she is — юрлицо or физлицо — when her поводы fall, and what is said to whoever has
just entered a Сторона somebody had entered before them.

Everything the раздел says in words reads through this one file. The полка names the ближайший
повод in a column and the экран lists them all, and a повод written out in two places would
eventually read as two different поводы on two screens of one раздел. Заведение says nothing
about a повод, and stands here for the other half of the same reason: «Юрлицо» in the отказ and
«Юрлицо» in the шапке are one word, and a form that spelled its own would be the second place
to be corrected when the word changes.

What is written out here is a phrase rather than a figure put beside a table. «Показано 12 из
637 Сторон» answers a question; «12 / 637» is a quantity the reader has to guess at — the same
device as «Показано 47 из 583 помещений» beneath the полка помещений and «нанесено 47 из 82»
beneath a план.

Agreement with the numeral is worked out here rather than assembled in the markup: «из 1
Сторон» reads as a glitch on the screen, not as a single Сторона. Two numerals stand in this
раздел and they take two different rules — one is governed by «из» and one is not — so
neither is the other's rule with the words swapped, and each says so where it is written.
"""

from typing import TYPE_CHECKING

from django.contrib import messages

from building_passport.passport_display import NBSP

from .models import Party
from .occasions import Occasion

if TYPE_CHECKING:
    # Под `TYPE_CHECKING`, потому что импорт кольцевой: форма заведения берёт отсюда `KINDS`,
    # чтобы юрлицо называлось на ней тем же словом, что и на обоих экранах раздела.
    from .party_entry import Entered

#: Сторона, не арендующая ни одного помещения: a bare dash, and deliberately not
#: `or_missing`'s «— нет данных». 637 of the 699 Стороны are поставщики who rent nothing at
#: all, and that is an answer rather than a gap in the record — «нет данных» would report
#: what BCMP knows as what it does not. The same reading `lease_display.NOBODY` gives the
#: empty «Арендатор» cell, spelled out here because it is a different question: there nobody
#: sits in the помещение, here the Сторона sits nowhere.
NOTHING = "—"


def parties_shown(shown: int, whole: int) -> str:
    """«Показано 12 из 637 Сторон» — how much of the полка the отбор left standing.

    Two numbers and not one: a narrowed полка must still say the size of what was narrowed,
    or the reader is left holding 12 with nothing to compare it against.

    The noun agrees with the second number, not the first: it is «из 637» that governs it.
    The predicate stays «Показано» throughout — the subject is «12 из 637», a part of
    something, and a part is neuter however small it is.

    «из» takes the genitive, so there are two forms here and not three — «из 1 Стороны», «из
    2 Сторон», «из 5 Сторон». It is the rule `room_display.rooms_shown` follows and not the
    one `agreeing_with` states below; it is spelled out here rather than asked of that one
    because the two are different rules and not one rule with different words — whoever
    unified them would have to invent a fourth form for a case that has three.

    The rows are counted and named Сторонами though the полка is a полка учётных карточек: a
    Сторона two of the reader's clients both know is two rows, and the line describes what is
    on the screen. A count that saw one Сторона there would contradict the table above it.
    """
    parties = "Стороны" if whole % 10 == 1 and whole % 100 != 11 else "Сторон"
    return f"Показано {shown} из {whole}{NBSP}{parties}"


def agreeing_with(count: int, one: str, few: str, many: str) -> str:
    """Форма слова при числе: 1 повод, 2 повода, 5 поводов.

    Одиннадцать — не «одиннадцать повод»: вторая цифра числа отменяет первую, поэтому десятки
    проверяются прежде единиц.

    Написано здесь, а не взято у документов, по тому же доводу, по какому здесь написана
    запись даты: у Стороны и у документа общая одна лишь грамматика, и импорт между двумя
    разделами ради семи строк первым покажется лишним, когда любой из двух тронется с места.
    Правило `parties_shown` этим не пользуется и пользоваться не может: там числительным
    правит «из», родительный падеж, и трёх форм не бывает — две.
    """
    if 11 <= count % 100 <= 14:
        return many
    ones = count % 10
    if ones == 1:
        return one
    if 2 <= ones <= 4:
        return few
    return many


def rooms_rented(count: int) -> str:
    """«5 помещений» — what one row says under «Арендует», or a dash where nothing is rented.

    Counted in помещениях and never in метрах: a Сторона sitting in a помещение inside
    another помещение would be counted twice by an unknown amount, because nothing in a row
    tells that nesting from the other one (ADR 0015, ADR 0019). A помещение cannot be counted
    twice — it is one row of the полка помещений and one помещение here.

    Three forms and not two, because this numeral governs a nominative: it is `agreeing_with`
    above, and not `parties_shown`'s rule above it, where «из» takes the genitive and the forms
    collapse to two. Whoever unifies the two will break this one without breaking the other.

    The phrase the ticket reads by — «Арендует 5 помещений» — is the heading and the cell
    together, as «Арендатор» and «3 арендатора» already are on the полка помещений: the
    column says what is being counted once, at the top, rather than in every row.
    """
    if not count:
        return NOTHING
    return f"{count}{NBSP}{agreeing_with(count, 'помещение', 'помещения', 'помещений')}"


#: Как называется род Стороны на экране: юрлицо и физлицо, и ни одного третьего слова.
#:
#: Не `get_kind_display()`, хотя выбор и заведён на модели: там юрлицо названо
#: «Организация», а на этих экранах «Организация» — арендатор платформы, чья карточка перед
#: читателем (`CONTEXT.md`). Одно слово в двух значениях на одном экране прочитают в том,
#: которое стоит рядом, — и шапка сказала бы, что ТОО «Альфа» есть клиент BCMP. Слово меняется
#: здесь, а не в `choices`, потому что в админке рядом с «Физлицо» стоит и «Организация»
#: понятная: там оно значит ровно то, что значит, и переписывать его нечем.
KINDS = {
    Party.Kind.COMPANY: "Юрлицо",
    Party.Kind.PERSON: "Физлицо",
}


def day(value) -> str | None:
    """Дата, как её читают в этом разделе: 14.03.1980.

    Написана здесь, а не взята у документов, по тому же доводу, по какому согласование
    числительного написано здесь дважды: у Стороны и у документа общая одна лишь запись даты,
    и импорт между двумя разделами ради одной строки первым покажется лишним, когда любой из
    двух тронется с места. Что действительно важно — чтобы день рождения в шапке и день
    рождения в строке контактного лица были написаны одинаково, а это одно правило и есть.

    Незаполненная дата остаётся None: прочерк над ней — дело `or_missing`, одним правилом на
    весь проект.
    """
    return f"{value:%d.%m.%Y}" if value else None


def bank_said(bank) -> str:
    """«АО "Kaspi Bank" · CASPKZKA» — банк, как он назван в разделе: название и БИК.

    Одно написание на строку заведённого комплекта и на список, из которого банк выбирают.
    БИК в обоих не украшение: «Каспи» и «Kaspi Bank» одним банком делает он, а не написание
    названия (ADR 0022), и список, называющий одно лишь название, отправил бы выбирать по
    тому самому, что различает написания вместо банков.

    Банк без БИК — сорок три ликвидированных из семидесяти шести — назван одним названием, а
    не названием с прочерком: пустой БИК значит «этим БИК уже никто не платит», и прочерк за
    точкой читался бы как пробел в записи. Про лицензию не сказано ничего ни там, ни там.
    """
    return f"{bank.name}{NBSP}· {bank.code}" if bank.code else bank.name


def kind_said(party) -> str | None:
    """«Юрлицо» или «Физлицо» — то, чем Сторона названа в шапке своего экрана.

    Пустое значение остаётся пустым: род заведён не у всякой из 699 Сторон, а прочерк
    ставит `or_missing` — одним правилом на весь проект.
    """
    return KINDS.get(party.kind)


def occasion_said(occasion: Occasion) -> str:
    """«09.08.2026 · День строителя» — один повод, как его читают на обоих экранах.

    Одно написание на колонку полки и на строку шапки: полка называет ближайший повод, экран
    перечисляет все, и повод, написанный на двух экранах по-разному, читался бы как два
    разных повода.

    Дата первой, а название за ней: список читают сверху вниз глазом, ищущим, к чему готовиться
    раньше, — название отвечает на вопрос, который дата уже подняла. Год печатается, хотя
    повод и годовой: спрошенный в декабре ближайший приходится на январь следующего, и «05.01»
    промолчало бы ровно о том, что читателю и нужно.

    Чей повод — после тире и только там, где он чей-то: у профессионального человека за ним
    нет, а у дня рождения физлица он не нужен — её имя уже стоит в шапке.
    """
    whose = f" — {occasion.whose}" if occasion.whose else ""
    return f"{day(occasion.on)}{NBSP}· {occasion.name}{whose}"


def nearest_occasion(occasion: Occasion | None) -> str:
    """What one row of the полка says under «Ближайший повод» — a повод, or a bare dash.

    Only the empty case is decided here; how a повод itself is written is `occasion_said`'s,
    because the экран Стороны writes it the same way and two accounts of it would read as two
    different поводы.

    `NOTHING` rather than `or_missing`'s «нет данных», for the reason the «Арендует» cell
    beside it uses it: 637 of the 699 Стороны are поставщики nobody has written a день
    рождения for, and that is an answer rather than a gap in the record.
    """
    return NOTHING if occasion is None else occasion_said(occasion)


def entry_said(entered: "Entered") -> tuple[int, str] | None:
    """Что сказано после отправки формы заведения — или ничего, потому что сказать нечего.

    Заведённая Сторона словами не подтверждается: следом открывается её экран, и
    перезагруженный экран и есть подтверждение — та же договорённость, по какой
    перезагруженная полка подтверждает загруженную пачку (ADR 0005). Словами говорится ровно
    то, чего на экране не прочесть.

    Занятый БИН как раз из этого: администратор набрал название, род и сферу, а увидит чужие,
    потому что общая половина осталась как была (ADR 0028), — и, не сказав ему почему, экран
    выглядел бы так, будто набранное потеряли. Сказанного при этом ровно один бит: что Сторона
    с этим БИН уже заведена. Ни кем, ни с каких пор, ни что о ней записано, — и потому обе
    фразы называют одну лишь Сторону (ADR 0021).

    Две фразы, а не одна: карточка, которой не было, и карточка, которая была, — два разных
    исхода одной отправки, и «уже заведена» о Стороне, стоящей на моей же полке, отправило бы
    администратора искать, кто её завёл, вместо того чтобы дочитать до конца.
    """
    if entered.party_entered:
        return None
    if entered.record_entered:
        return messages.INFO, (
            "Сторона с этим БИН/ИИН уже заведена. Учётная карточка на неё добавлена, "
            "а название, род и сфера деятельности остались как были."
        )
    return messages.INFO, "Сторона с этим БИН/ИИН уже заведена и стоит на вашей полке."


def payment_details_taken(count: int) -> str:
    """«2 комплекта платёжных реквизитов» — что уносит удаление учётной карточки.

    Комплектами, а не счетами: счёт в тенге и счёт в валюте живут в одном комплекте с банком
    и КБе, и «2 счёта» назвало бы не то, что будет уничтожено.
    """
    sets = agreeing_with(count, "комплект", "комплекта", "комплектов")
    return f"{count}{NBSP}{sets} платёжных реквизитов"


def contacts_taken(count: int) -> str:
    """«3 контактных лица» — люди внутри Стороны, уходящие вместе с карточкой.

    Уходят они, а не Сторона и не сами люди: контактное лицо живёт в учётной карточке и
    нигде больше, и второй управляющей компании, знакомой с тем же юрлицом, его никогда не
    показывали (ADR 0020).
    """
    people = agreeing_with(count, "контактное лицо", "контактных лица", "контактных лиц")
    return f"{count}{NBSP}{people}"


def occasions_taken(count: int) -> str:
    """«4 повода» — дни рождения, которых после удаления карточки не останется нигде.

    Считаются хранимые, и только они: профессиональный праздник выводится из сферы
    деятельности Стороны, а Сторона остаётся в реестре (ADR 0023, ADR 0028) — названный
    уничтоженным, он пообещал бы разрушение, которого не произойдёт. Что именно сюда входит,
    решает `occasions.stored_occasions_of`, где записан и этот довод.
    """
    return f"{count}{NBSP}{agreeing_with(count, 'повод', 'повода', 'поводов')}"


def record_deleted(name: str, taken) -> str:
    """Что сказано после удаления карточки — на полке, куда попадает читатель.

    Сторона названа, потому что экран, с которого удаляли, ушёл вместе с карточкой: полка
    выглядит почти как прежде, одной строкой короче, и ничто на ней не говорит, какой именно
    строки не стало.

    Что ушло, говорится снова, а не оставляется вопросу: вопрос — это экран до, и одно
    «удалена» оставило бы удалившего гадать, лежат ли ещё где-нибудь его контактные лица. Тот
    же список, что держал вопрос, слово в слово: собранный здесь во второй раз, он был бы
    вторым изложением того, что уносит удаление, и однажды обещание разошлось бы с отчётом.

    И сказано, что Сторона осталась: удаляют карточку, а строка реестра остаётся, потому что
    освобождённый БИН дал бы второй организации юрлицо без прошлого (ADR 0028). Прочитавший
    «удалена» и не прочитавший этого пошёл бы заводить её заново.
    """
    deleted = f"Учётная карточка на «{name}» удалена."
    if taken:
        deleted = f"{deleted} Вместе с ней удалены: {', '.join(one.said for one in taken)}."
    return f"{deleted} Сама Сторона осталась в реестре."
