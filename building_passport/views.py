from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import *

MODULE_NAME = "building_passport"


class HomeView(LoginRequiredMixin, View):
    template_name = "building_passport/building/index.html"

    def get(self, request):
        context = {
            "buildings":Space.objects.filter(type="building"),
        }
        return render(request, self.template_name, context)
