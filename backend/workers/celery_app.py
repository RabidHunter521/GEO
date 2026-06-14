from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "seenby",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.tasks.scan_tasks",
        "workers.tasks.digest_tasks",
        "workers.tasks.report_tasks",
        "workers.tasks.content_tasks",
        "workers.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Bound task runtime so a hung provider call can't pin a worker forever.
    # A full 4-platform scan (~112 sequential calls) normally finishes in
    # minutes; these leave generous headroom. soft_time_limit raises
    # SoftTimeLimitExceeded (catchable); time_limit is the hard SIGKILL ceiling.
    task_soft_time_limit=1500,  # 25 min
    task_time_limit=1800,       # 30 min
    # Don't let task results accumulate in Redis indefinitely.
    result_expires=86400,       # 24h
    beat_schedule={
        "weekly-digest-monday-9am-utc": {
            "task": "workers.tasks.digest_tasks.send_all_weekly_digests",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
        },
        "daily-report-check-9am-utc": {
            "task": "workers.tasks.report_tasks.check_and_generate_due_reports",
            "schedule": crontab(hour=9, minute=0),
        },
        "daily-data-retention-4am-utc": {
            "task": "workers.tasks.maintenance_tasks.run_data_retention",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
