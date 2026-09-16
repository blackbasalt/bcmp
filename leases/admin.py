from django.contrib import admin

from .models import Lease


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    """Until the карточка помещения carries the form, this is where an аренда is entered.

    The refusal it shows is the model's own: «по» раньше «с» is rejected here in the same
    words a form and a script get, because the rule sits on the model and not on this page.
    """

    list_display = ("space", "tenant", "area_m2", "rate", "valid_from", "valid_to")
    list_filter = ("space__building",)
    search_fields = ("space__code", "space__name", "tenant__name", "contract__title")
    # A помещение is picked out of some six hundred, a Сторона out of the registry of the
    # whole system and a договор out of the организация's documents: all of them are
    # searched for rather than scrolled to.
    autocomplete_fields = ("space", "tenant", "landlord", "contract")
