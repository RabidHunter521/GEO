#!/bin/sh
# Railway "worker" service. Migrations are applied by the api service.
set -e
exec celery -A workers.celery_app worker -l info --concurrency=2
