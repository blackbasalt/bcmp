"""How a БЦ stands on a form of this section — what it is called and in what order.

Two forms offer buildings: the upload chooses the one a batch is attached to, the search
narrows the shelf to one. Which buildings each may offer is their own business and differs
— the upload offers those the employee may write to, the search those they may see — but
what a building is called and in what order the list stands is one rule for both.

It lives apart from either form because it belongs to neither. Kept beside the upload it
would make a read screen import the batch, the близнецы and the transaction that stores
them, for the sake of a label.
"""

from django import forms


class BuildingChoice(forms.ModelChoiceField):
    """The BCs on offer, named the way they are named everywhere else.

    A space says itself as «man (building)» — the code and the type, which is what a row in
    the admin needs. Whoever is uploading a folder, or looking for one, knows the building
    as «Manhattan», and a list of codes is a list they have to translate every time. The
    code is left for a building with no name at all: it is worse than a name, but it is
    what there is.
    """

    def offer(self, buildings):
        """The buildings this form may offer, in the order the list is read in.

        The order is set here and not by each form: they are the same list to the reader,
        and one of them sorted differently would look like a different set of buildings.
        Set through a method because the set depends on who is asking, which a field
        declared on a class does not yet know.
        """
        self.queryset = buildings.order_by("name", "code")

    def label_from_instance(self, building):
        return building.name or building.code
