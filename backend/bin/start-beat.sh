#!/bin/sh
# Railway "beat" service — schedules the periodic tasks in celery_app.py
# (weekly digest, daily report check, daily data retention).
set -e
exec celery -A workers.celery_app beat -l info
