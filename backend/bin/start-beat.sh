#!/bin/sh
# Standalone scheduler for the periodic tasks in celery_app.py. NOT used in
# production: bin/start-worker.sh runs the scheduler itself (-B). Never run this
# alongside that worker, or every periodic task (including the weekly digest
# email) fires twice. Kept only so the old separate "beat" service can be
# restored by pointing it at this script and dropping -B from the worker.
set -e
exec celery -A workers.celery_app beat -l info
