from django.urls import path

from . import views

urlpatterns = [
    path("", views.index_view, name="index"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("help/", views.get_help_view, name="get_help"),
]
