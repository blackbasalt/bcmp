from django.urls import path

from . import views

app_name = "bp"
urlpatterns = [
    path("bp/", views.HomeView.as_view(), name="home"),
    path("bp/", views.HomeView.as_view(), name="board"),
]
