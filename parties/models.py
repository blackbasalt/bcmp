import uuid

from django.contrib.auth.models import User
from django.db import models

# Create your models here.
class CommonModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                                   editable=False, related_name='+')

    class Meta:
        abstract = True


class Party(CommonModel):
    """Any party: a legal entity or a natural person. Once for the whole system."""
    class Kind(models.TextChoices):
        COMPANY = "company", "Организация"
        PERSON = "person", "Физлицо"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=255)
    bin_iin = models.CharField(unique=True, max_length=32, blank=True, null=True)
    contacts = models.JSONField(default=dict, blank=True, db_default={})
    external_id = models.CharField(max_length=1024, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class OrgQuerySet(models.QuerySet):
    def administered_by(self, user):
        """The organisations whose data the user may maintain — the write checkpoint (ADR 0005).

        The question lives here, where the right itself does: administratorship belongs to
        the pair "employee + organisation", and everything written is written into some
        organisation's data. Spaces and documents ask this one place rather than each
        assembling the same filter over memberships — two of them would be two answers to
        one question, and the second one to drift would let a reader write.

        A superuser administers everything for the same reason they see everything: they
        already write through the Django admin, so a ban here would close nothing.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(pk__in=user.memberships.filter(is_admin=True).values("org_id"))

    def handled_by(self, user):
        """The organisations the reader handles — a question about them, not about data.

        It disposes of no permissions and selects no rows: whose data to show is decided by
        the chokepoints (ADR 0001, ADR 0006), and what is worked out here is only whether a
        screen needs an «Организация» column at all. One employee handling two clients asks
        "whose is this" of every row; one handling a single client would get a column
        repeating one word down the whole table.

        It is asked about the reader and not about what is shown, so the column holds on
        even when the second client has nothing loaded yet — which is exactly when whoever
        handles two of them most needs to know whose shelf they are looking at.

        A superuser reads on everyone's behalf, so all the organisations are theirs.
        """
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(pk__in=user.memberships.values("org_id"))


class Org(CommonModel):
    """A tenant of the platform. A thin layer over Party, not a duplicate."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.OneToOneField(Party, on_delete=models.PROTECT, related_name="tenancy")
    plan = models.CharField(max_length=32, blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True, db_default={})
    is_active = models.BooleanField(default=True, db_default=True)

    objects = OrgQuerySet.as_manager()

    @property
    def name(self):
        return self.party.name

    def __str__(self):
        return self.name


class OrgMembership(CommonModel):
    """A user's access to an organisation. One employee may belong to several."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    #: The right to maintain this organisation's data from the application, not merely to
    #: read it. It sits on the membership rather than on the user: being an administrator
    #: belongs to the pair "employee + organisation", and an employee who maintains one
    #: client stays an ordinary reader for another. A global `is_staff` does not express
    #: that — the same argument as for the isolation by organisation itself (ADR 0001,
    #: ADR 0005).
    is_admin = models.BooleanField(
        default=False, db_default=False, verbose_name="администратор организации"
    )

    class Meta:
        db_table = "org_membership"
        verbose_name = "членство в организации"
        verbose_name_plural = "членства в организациях"
        constraints = [
            models.UniqueConstraint(fields=["user", "org"], name="org_membership_uq"),
        ]

    def __str__(self):
        return f"{self.user} → {self.org}"


class PartyRole(CommonModel):
    """A party's role in a particular context and over a particular period."""
    class Role(models.TextChoices):
        OWNER = "owner", "Собственник"
        OPERATOR = "operator", "Управляющая компания"
        CONTRACTOR = "contractor", "Подрядчик"
        SUPPLIER = "supplier", "Поставщик"
        EXPERT = "expert", "Эксперт"
        DESIGNER = "designer", "Проектировщик"
        BUILDER = "builder", "Подрядчик СМР"

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=32, choices=Role.choices)
    scope_type = models.CharField(max_length=32, blank=True, null=True)  # space|zone|building_system|org
    scope_id = models.UUIDField(blank=True, null=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)

    class Meta:
        db_table = "party_role"
