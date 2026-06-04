# backend/workers/celery_app.py
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "seenby",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks.scan_tasks", "workers.tasks.digest_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "weekly-digest-monday-9am-utc": {
            "task": "workers.tasks.digest_tasks.send_all_weekly_digests",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
        },
    },
)
