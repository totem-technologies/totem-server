# define an alias for the specfic python version used in this file.
FROM python:3.12-slim-bookworm AS python

# Python build stage
FROM python AS python-build-stage

ARG BUILD_ENVIRONMENT=local

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg2 dependencies
  libpq-dev

RUN pip install uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv venv

# Requirements are installed here to ensure they will be cached.
COPY ./pyproject.toml .
COPY ./uv.lock .

# Install dependencies.
RUN uv sync --frozen

FROM node:22 AS node-build-stage

WORKDIR /app

COPY . .
RUN npm install

COPY assets ./assets
RUN npm run build

# Python 'run' stage
FROM python AS python-run-stage

ARG BUILD_ENVIRONMENT=local
ARG APP_HOME=/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BUILD_ENV=${BUILD_ENVIRONMENT}
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR ${APP_HOME}

# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg2 dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# All absolute dir copies ignore workdir instruction.
COPY --from=python-build-stage /opt/venv /opt/venv

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

# copy application code to WORKDIR
COPY . ${APP_HOME}
COPY --from=node-build-stage /app/totem/static/js/bundles /app/totem/static/js/bundles

# Define the default command.
CMD ["/start"]

ENTRYPOINT ["/entrypoint"]
