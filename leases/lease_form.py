"""Форма договора аренды: договор и его предметы одной отправкой.

Договор без предмета не договор, а несколько помещений на одном соглашении — не
исключение, а обычный случай: арендатор берёт офис, склад и два машиноместа одним
договором, и заводиться это должно одним действием, а не тремя проходами. Поэтому
форма здесь не одна, а пара — сам договор и формсет его предметов, — и связывает их
`LeaseWriting`: два экрана, заведение и правка, ходят к ней одним и тем же способом.

Проверок своих у формы нет. Пересечение периодов, чужая организация и
неарендопригодное помещение — правила самого договора и его предмета (ADR 0007,
ADR 0009), поэтому админка, эта форма и любой скрипт получают один и тот же отказ
теми же словами. Форме остаётся показать его рядом с полем и вернуть уже введённое:
перенабирать договор целиком из-за одной плохой строки — то, после чего данные
перестают заводить вовсе.

Выбор при этом сужен до того, что пользователь вправе написать: в списке помещений
только арендопригодные тех организаций, которые он ведёт. Это не замена отказам, а
другое их назначение: венткамера и помещение чужого клиента не должны попадать в
список вовсе — второе ещё и назвало бы читателю чужие помещения по именам. Отказ
модели остаётся тем, что ловит скрипт, админку и сотрудника, ведущего две
организации сразу: у него в списке помещения обеих, и назвавший помещение одной в
договоре другой получает отказ, называющий помещение.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from building_passport.models import Space
from parties.models import Org, Party

from . import lease_display
from .models import Lease, LeaseSubject

#: Сколько пустых строк предмета форма нового договора добавляет сверх обязательной
#: первой. Три сверх одной — это «офис, склад и два машиноместа», тот самый договор,
#: ради которого предмет и заводится списком. Потолком это число не является:
#: строку добавляют кнопкой, и формсет принимает столько, сколько прислано.
BLANK_SUBJECT_ROWS = 3

SUBJECT_FIELDS = ("space", "rate", "area_m2")


class SpaceChoiceField(forms.ModelChoiceField):
    """Помещение в выпадающем списке зовётся так же, как в отказе под ним."""

    def label_from_instance(self, space):
        return lease_display.space_chosen(space)


class LeaseForm(forms.ModelForm):
    """Сам договор: организация, арендатор, срок и то, чем он назван на бумаге.

    Организацию называет заводящий, а не выводится она из помещений предмета: у
    договора она своя (ADR 0009), и вывод из предмета — это тот самый выбор между
    утечкой и тихо исчезающей записью, от которого ADR отказался. Выбирать нечего,
    когда ведут одну организацию, — тогда она и стоит в поле одна.
    """

    class Meta:
        model = Lease
        fields = ("org", "tenant", "valid_from", "valid_to", "number", "signed_at",
                  "prolongs")
        widgets = {
            "org": forms.Select(attrs={"class": "select w-full"}),
            "tenant": forms.Select(attrs={"class": "select w-full"}),
            # Дата вводится календарём браузера, и он присылает её по ISO. Формат
            # выписан и на показ: заведённая дата иначе вернулась бы на форму по
            # русскому формату, а поле такой не читает и молча покажет пустоту.
            "valid_from": forms.DateInput(
                attrs={"type": "date", "class": "input w-full"}, format="%Y-%m-%d"
            ),
            "valid_to": forms.DateInput(
                attrs={"type": "date", "class": "input w-full"}, format="%Y-%m-%d"
            ),
            "signed_at": forms.DateInput(
                attrs={"type": "date", "class": "input w-full"}, format="%Y-%m-%d"
            ),
            "number": forms.TextInput(attrs={"class": "input w-full"}),
            # Пролонгируемый договор называется адресом экрана, а не выбирается в
            # списке: продлевают с карточки прежнего договора, и второй способ
            # указать его позволил бы связать два договора, никак друг с другом не
            # связанных.
            "prolongs": forms.HiddenInput(),
        }
        help_texts = {
            # Умолчания у даты нет намеренно, и у окончания тоже: подставленное
            # сегодня приняли бы не глядя, и расторжение записалось бы днём, когда
            # открыли форму, а не днём, когда оно случилось (ADR 0004, ADR 0007).
            "valid_to": "Пусто — «по сей день». Досрочное расторжение закрывает "
                        "период датой, которой оно случилось.",
            "number": "Необязателен: договор заводят раньше, чем держат в руках "
                      "каждую его подробность.",
        }

    #: Даты принимаются и по ISO, и по-русски: первое присылает поле календаря,
    #: второе набирает руками тот, у кого календарь не открылся.
    DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        for named in ("valid_from", "valid_to", "signed_at"):
            self.fields[named].input_formats = self.DATE_FORMATS
        administered = Org.objects.administered_by(user)
        self.fields["org"].queryset = administered
        if len(administered) == 1:
            # Одна организация — не выбор, а данность: пустая строка над ней
            # предлагала бы решение, которого нет.
            self.fields["org"].empty_label = None
        # Арендатором Сторону делает договор и только он (ADR 0008), поэтому здесь
        # все Стороны, а не отобранные по роли: роли «арендатор» у Стороны нет.
        self.fields["tenant"].queryset = Party.objects.order_by("name")
        # Прежний договор — тот же чокпоинт, что и на чтении: связать свой договор
        # с чужим по подставленному в адрес ключу быть не должно возможно (ADR 0009).
        self.fields["prolongs"].queryset = Lease.objects.visible_to(user)


class LeaseSubjectForm(forms.ModelForm):
    """Предмет: помещение со своей ставкой и своей договорной площадью."""

    space = SpaceChoiceField(
        queryset=Space.objects.none(),
        label="Помещение",
        empty_label="— выберите помещение —",
        widget=forms.Select(attrs={"class": "select select-sm w-full"}),
    )

    class Meta:
        model = LeaseSubject
        fields = SUBJECT_FIELDS
        widgets = {
            "rate": forms.NumberInput(
                attrs={"class": "input input-sm w-full", "step": "0.01"}
            ),
            "area_m2": forms.NumberInput(
                attrs={"class": "input input-sm w-full", "step": "0.01"}
            ),
        }
        help_texts = {
            # Договорная площадь — условие соглашения, а не обмер здания: она
            # никуда не пишется поверх площади помещения (ADR 0006).
            "area_m2": "Полезная плюс доля МОП — то, за что платит арендатор, а не "
                       "обмер помещения.",
        }

    def __init__(self, *args, spaces=None, **kwargs):
        super().__init__(*args, **kwargs)
        if spaces is not None:
            self.fields["space"].queryset = spaces


class LeaseSubjectFormSet(BaseInlineFormSet):
    """Предметы проверяются против договора, который в базу ещё не попал.

    Строки валидируются раньше, чем сохранён родитель, и спросить договор по ссылке
    в этот момент нечем — админка вдобавок обнуляет его ключ, пока он не записан.
    Строки бы прошли проверку, а отказ пришёл бы уже из `save()`: пятисоткой вместо
    сообщения у поля. Договор передаётся прямо объектом, тем самым, который держит
    в руках форма, — с уже применёнными правками срока и организации.
    """

    default_error_messages = {
        "too_few_forms": "Договор без предмета не бывает: назовите хотя бы одно помещение.",
    }

    def _construct_form(self, index, **kwargs):
        form = super()._construct_form(index, **kwargs)
        form.instance.lease = self.instance
        return form

    def get_unique_error_message(self, unique_check):
        """Одно помещение дважды в одном договоре — то же правило, сказанное словами.

        Правило здесь не заводится: пара «договор + помещение» уникальна на самой
        модели, и пересечение периодов её не ловит — свой договор из проверки
        исключён, иначе строка спорила бы сама с собой. Переведена только фраза:
        «повторяющееся значение в поле space» называет столбец, а не то, что человек
        сделал. Любая другая будущая уникальность объясняется по-прежнему Django:
        своими словами пересказано ровно то правило, которое здесь и знают.
        """
        if set(unique_check) != {"lease", "space"}:
            return super().get_unique_error_message(unique_check)
        return (
            "Помещение названо в договоре дважды: у одного помещения одна ставка "
            "и одна договорная площадь."
        )

    def get_form_error(self):
        """Та же причина у самой строки: по ней видно, какую из двух правят."""
        return "Это помещение уже названо строкой выше."


def _recorded(lease):
    """Записан ли договор в базу.

    Спрашивается именно это, а не «есть ли у него ключ»: ключ у договора есть с
    рождения — `uuid4` проставляется умолчанием поля, а не базой, — и по ключу
    незаписанный договор неотличим от записанного.
    """
    return not lease._state.adding


def leasable_spaces_for(user, lease):
    """Помещения, которые пользователь вправе назвать предметом этого договора.

    Только арендопригодные и только тех организаций, которые он ведёт: венткамера в
    списке — промах, который дешевле не предлагать, а помещение чужого клиента в нём
    — уже утечка имён (ADR 0009).

    Помещения, уже названные договором, остаются в списке, даже если перестали
    подходить: правка, молча теряющая строку из-за снятой где-то арендопригодности,
    хуже отказа — она ничего не говорит.
    """
    allowed = Space.objects.administered_by(user).filter(is_leasable=True)
    if _recorded(lease):
        allowed = Space.objects.filter(
            Q(pk__in=allowed.values("pk")) | Q(lease_subjects__lease=lease)
        ).distinct()
    return allowed.select_related("building").order_by(
        "building__name", "floor_number", "code"
    )


class LeaseWriting:
    """Договор и его предметы как один путь записи: одна проверка, одно сохранение.

    Обе формы нужны обоим экранам — Список договоров заводит, карточка правит, — и
    порядок их сборки не произволен: предметы строятся против договора с уже
    применёнными правками, потому что их проверка спрашивает у него срок и
    организацию. Собранные наоборот, они сверялись бы с тем сроком, который был до
    правки, и пересечение проехало бы мимо.

    Плата за этот порядок названа и принята: срок договора сверяется с предметами по
    базе, то есть с теми, что были до отправки, — и правка «продлить договор и снять
    с него помещение, которое этому мешает» отказывается по помещению, которого
    после неё не будет. Делается она тогда в два захода, причём отказ прямо говорит,
    какое помещение мешает. Обратный порядок — проверять срок последним — стоил бы
    того, что правка срока в админке падала бы пятисоткой вместо отказа на форме:
    проверка на `clean()` там и стоит ради этого.
    """

    def __init__(self, user, lease=None, data=None, subjects_initial=None):
        self.user = user
        self.lease = Lease() if lease is None else lease
        self.form = LeaseForm(data, instance=self.lease, user=user)
        # Проверка договора — до сборки предметов: она переносит введённое на сам
        # договор, и без неё предметы сверялись бы с тем сроком, который был до
        # правки. Незаполненная форма проверку не проходит и ничем не занята.
        self.lease_is_valid = self.form.is_valid()
        self.subjects = self._subjects(data, subjects_initial)

    @classmethod
    def prolonging(cls, user, prior):
        """Пролонгация — то же заведение, только со ссылкой на прежний (ADR 0007).

        Продлевается то, что и было: арендатор, помещения и договорная площадь
        приходят с прежнего договора. Ставка и даты — нет: при продлении ставка
        почти всегда меняется, и подставленная старая, принятая не глядя, стёрла бы
        ответ на «по какой ставке помещение сдавалось в марте» ровно так же, как
        это сделала бы правка прежнего договора на месте.
        """
        return cls(
            user,
            lease=Lease(prolongs=prior, org=prior.org, tenant=prior.tenant),
            subjects_initial=[
                {"space": subject.space_id, "area_m2": subject.area_m2}
                for subject in prior.subjects.order_by("space__code")
            ],
        )

    @property
    def refused(self):
        """Форма вернулась с отказом — и раскрыта поэтому: спрятанного отказа не видно."""
        return bool(self.form.errors or self.subjects.total_error_count())

    @property
    def prolongs(self):
        """Этой формой продлевают: она пришла заполненной, и складывать её незачем."""
        return self.lease.prolongs_id is not None

    def is_valid(self):
        """Обе формы, а не первая из двух: отказы называются все разом.

        Проверенный по очереди договор показал бы отказ срока, а после его правки —
        отказ строки, о котором в первый раз промолчал.
        """
        subjects_are_valid = self.subjects.is_valid()
        return self.lease_is_valid and subjects_are_valid

    def save(self):
        """Договор с предметами записывается целиком или не записывается вовсе.

        Отказ может прийти и отсюда, а не только из проверки форм: срок сверяется на
        `save()` самого договора, потому что пересечение зависит от двух вещей —
        периода и помещения, — и заводятся они порознь. Пришедший здесь отказ
        показывается на форме, а незаконченная запись откатывается: договор, у
        которого записалась половина предметов, хуже отказа.
        """
        try:
            with transaction.atomic():
                lease = self.form.save()
                self.subjects.instance = lease
                self.subjects.save()
        except ValidationError as refusal:
            self.form.add_error(None, refusal.messages)
            return None
        return lease

    def _subjects(self, data, initial):
        formset = inlineformset_factory(
            Lease,
            LeaseSubject,
            form=LeaseSubjectForm,
            formset=LeaseSubjectFormSet,
            fields=SUBJECT_FIELDS,
            extra=self._blank_rows(initial),
            # Договор без предмета не бывает, и `min_num` сам по себе только рисует
            # строку: без `validate_min` пустой формсет проходит.
            min_num=1,
            validate_min=True,
            can_delete=True,
            # Убирают из договора то, что в нём есть: галочка над пустой строкой
            # предлагала бы убрать ненаписанное.
            can_delete_extra=False,
        )
        return formset(
            data,
            instance=self.form.instance,
            initial=initial,
            prefix="subjects",
            form_kwargs={"spaces": leasable_spaces_for(self.user, self.form.instance)},
        )

    def _blank_rows(self, initial):
        """Сколько пустых строк предложить: пустой договор заводят списком, правят по одной."""
        if initial:
            return len(initial) + 1
        return 1 if _recorded(self.lease) else BLANK_SUBJECT_ROWS
