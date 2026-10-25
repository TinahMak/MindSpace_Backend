from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/", views.users, name="users"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/<str:action>/", views.user_action, name="user_action"),
    path("admins/", views.admins, name="admins"),
    path("ratings/", views.ratings, name="ratings"),
    path("audit/", views.audit, name="audit"),
    path("backups/", views.backups, name="backups"),
    path("backups/run/", views.backup_run, name="backup_run"),
    path("reports/", views.reports_page, name="reports"),
    path("reports/<str:kind>.<str:fmt>", views.report_file, name="report_file"),
    path("professionals/", views.professionals, name="professionals"),
    path("professionals/add/", views.professional_add, name="professional_add"),
    path("professionals/<int:pk>/", views.professional_detail, name="professional_detail"),
    path("professionals/<int:pk>/<str:action>/", views.professional_action, name="professional_action"),
    path("professionals/documents/<int:doc_pk>/", views.professional_document, name="professional_document"),
]
