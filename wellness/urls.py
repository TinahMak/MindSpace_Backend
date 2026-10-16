from django.urls import path

from . import views

urlpatterns = [
    path("insights/", views.insights_view, name="mood_insights"),
    path("insights/report/", views.download_report_view, name="mood_report_download"),
    path("insights/generate-weekly/", views.generate_weekly_insight_now_view, name="generate_weekly_insight"),
]
