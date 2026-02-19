# define an alias for the specific python version used in this file.
FROM python:3.13-slim-trixie AS python

# Python build stage
FROM python AS python-build-stage

ARG BUILD_ENVIRONMENT=production

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
    # dependencies for building Python packages
    build-essential \
    # dynimg dependencies
    libexpat1-dev

RUN pip install uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv venv

# Requirements are installed here to ensure they will be cached.
COPY ./pyproject.toml .
COPY ./uv.lock .

# Install dependencies.
RUN uv sync --no-dev --frozen

FROM oven/bun:1 AS js-build-stage

WORKDIR /app

COPY package.json .
COPY bun.lock .
RUN bun install --frozen-lockfile

COPY . .
COPY assets ./assets
RUN bun run build

# Python 'run' stage
FROM python AS python-run-stage

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BUILD_ENV=${BUILD_ENVIRONMENT}
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR ${APP_HOME}

RUN addgroup --system django \
    && adduser --system --home /home/django --ingroup django django

# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    # Translations dependencies
    gettext \
    # dynimg runtime dependencies
    libexpat1 \
    fontconfig \
    ca-certificates \
    # cleaning up unused files
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# All absolute dir copies ignore workdir instruction.
COPY --from=python-build-stage /opt/venv /opt/venv

COPY --chown=django:django ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY --chown=django:django ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

COPY --chown=django:django ./compose/production/django/predeploy /predeploy
RUN sed -i 's/\r$//g' /predeploy
RUN chmod +x /predeploy

# copy application code to WORKDIR
COPY --chown=django:django . ${APP_HOME}
COPY --chown=django:django --from=js-build-stage /app/totem/static/js/bundles /app/totem/static/js/bundles

# Register app fonts with fontconfig for dynimg
RUN ln -s /app/totem/static/fonts /usr/local/share/fonts/totem && fc-cache -f

# make django owner of the WORKDIR directory as well.
RUN chown django:django ${APP_HOME}

USER django

# Define the default command.
CMD ["/start"]

ENTRYPOINT ["/entrypoint"]
