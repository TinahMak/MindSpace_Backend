from django.apps import AppConfig


class ApiConfig(AppConfig):
    """REST API used by the MindSpace_Mobile Expo app.

    Everything here is a thin JSON layer over the existing apps (accounts,
    wellness, aichat, core). No business logic is duplicated: crisis
    detection, Gemini replies, mood analysis, PDF reports and weekly
    insights all call the same functions the website uses, and read and
    write the same Supabase tables.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "Mobile API"
