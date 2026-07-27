from django.contrib.auth.models import User
from django.db import models


class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True


class DictionaryCommonModel(CommonModel):
    code = models.CharField(max_length=256, unique=True, null=True, blank=True)
    slug = models.CharField(max_length=256, unique=True, null=True, blank=True)
    name = models.CharField(max_length=1024, unique=True)
    short_name = models.CharField(max_length=1024, unique=True)
    sort_order = models.IntegerField(unique=True, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    external_id = models.CharField(max_length=1024, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class DictSpaceType(models.TextChoices):
    PROJECT = "project", "Проект"
    SITE = "site", "Площадка"
    BUILDING = "building", "Здание"
    WING = "wing", "Блок / секция / крыло"
    FLOOR = "floor", "Этаж"
    MEZZANINE = "mezzanine", "Антресоль"
    ROOM = "room", "Помещение"
    SHAFT = "shaft", "Шахта"
    STAIRWELL = "stairwell", "Лестничная клетка"
    ROOF = "roof", "Кровля"
    FACADE = "facade", "Фасад"
    TERRITORY = "territory", "Прилегающая территория"
    PARKING_SPOT = "parking_spot", "Машиноместо"
    VOID = "void", "Проём второго света / атриум"
    OTHER = "other", "Прочее"


class DictServiceRole(models.TextChoices):
    PRIMARY = "primary", "Основное"
    BACKUP = "backup", "Резерв"
    PARTIAL = "partial", "Частичное"


class DictSpaceSubtype(DictionaryCommonModel):
    type = models.TextField(choices=DictSpaceType.choices)
    grp = models.CharField(max_length=256, null=True, blank=True)
    pass

    def __str__(self):
        return f"{self.type} -> {self.name}"


class DictSystem(DictionaryCommonModel):
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    is_leaf = models.BooleanField(null=True, blank=True)
    pass

    def __str__(self):
        return self.name


class DictBuilding(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictRequirementCode(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictAreaKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictSpaceRelationKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictSpaceStatus(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictZoneKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictAssetRelationKind(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictElementCategory(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name


class DictConditionGrade(DictionaryCommonModel):
    pass

    def __str__(self):
        return self.name
