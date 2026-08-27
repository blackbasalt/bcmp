"""
URL configuration for bcmp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from authentication import views as login_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("login/", login_views.LoginView.as_view(), name="login"),
    path("logout/", login_views.LogoutView.as_view(), name="logout"),
    path("assistant/", include("assistant.urls")),
    # The documents section sits beside the passports rather than inside them: it is
    # reached without opening a building, and it needs its own namespace partly so that
    # the menu can tell one section from the other.
    path("documents/", include("documents.urls")),
    # The помещения section, beside the passports rather than inside them: it spans every
    # БЦ and every этаж at once, and it needs its own namespace so that the menu highlights
    # «Помещения» rather than «Бизнес-центры» while the reader stands on it (ADR 0016).
    path("rooms/", include("rooms.urls")),
    path("", include("building_passport.urls")),
]
