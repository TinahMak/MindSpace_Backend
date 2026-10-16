import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mindspace.settings")

app = Celery("mindspace")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "weekly-mood-insights": {
        "task": "wellness.tasks.generate_weekly_insights_all_users",
        # Every Monday at 08:00 server time.
        "schedule": crontab(day_of_week="monday", hour=8, minute=0),
    },
}
