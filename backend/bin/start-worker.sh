#!/bin/sh
# Railway "worker" service. Migrations are applied by the api service.
#
# -B runs the beat scheduler (digest, report check, retention, stale-scan
# reaper in celery_app.py) inside this process, so there is no separate "beat"
# service. Run exactly ONE replica of this service: every replica would run its
# own scheduler and fire each periodic task once per replica.
#
# CELERY_CONCURRENCY defaults to 1 (a prefork child costs ~100+ MB of RAM and
# the periodic tasks are tiny). Raise it on Railway if scans queue up behind
# each other. Tasks run one at a time at 1, so the 15-minute reaper waits
# behind a running scan instead of overlapping it.
set -e
exec celery -A workers.celery_app worker -B -l info --concurrency="${CELERY_CONCURRENCY:-1}"
