# backend/Dockerfile
# Single image shared by all Railway services (api, worker, beat).
# Each service overrides the start command — see bin/start-*.sh.
FROM python:3.12-slim

# System libs required by WeasyPrint (PDF report generation) + psycopg2 build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main --no-interaction --no-ansi

COPY . .

RUN chmod +x bin/*.sh

EXPOSE 8000

CMD ["bin/start-web.sh"]
