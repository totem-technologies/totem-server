MAKEFLAGS += -j4
.PHONY: *

RUN_DJANGO = docker compose -f local.yml run --rm --remove-orphans django

run: up assets-watch livereload

# COMPOSE_MENU=0: compose's interactive menu puts the tty in raw mode and
# swallows Ctrl-C, so the other `make run` jobs never get the SIGINT.
up:
	COMPOSE_MENU=0 docker compose -f local.yml up --remove-orphans

build:
	docker compose -f local.yml build

build-prod:
	docker build -t totem-prod -f compose/production/django/Dockerfile .

test: test-python test-js pre-commit

pre-commit:
	pre-commit run --all-files

test-js:
	bun run test:ci

lint:
	bun run lint

format:
	bun run format

test-python:
	@${RUN_DJANGO} coverage run -m pytest -n auto

tasks:
	@${RUN_DJANGO} python manage.py totem_tasks

shell:
	@${RUN_DJANGO} bash

dbshell:
	docker compose -f local.yml exec postgres bash

sqlshell:
	docker compose -f local.yml exec postgres psql -U debug -d totem

pyshell:
	@${RUN_DJANGO} ./manage.py shell_plus

deploy:
	git push dokku

deploy-prod:
	git push dokku-prod

# atcb builds once up front: it only changes when the dependency does.
# vite watches JS sources and (via the tailwind plugin) the templates.
assets-watch:
	bun run build:atcb
	bun run dev

livereload:
	bun run livereload

assets:
	bun run build

install_local:
	uv sync --frozen
	bun install

fixtures:
	@${RUN_DJANGO} python manage.py load_dev_data

migrations: ## Create DB migrations in the container
	@${RUN_DJANGO} python manage.py makemigrations

migrate: ## Run DB migrations in the container
	@${RUN_DJANGO} python manage.py migrate

generate_api_models:
	@${RUN_DJANGO} python manage.py export_openapi_schema --api totem.api.api.api > openapi.json
	@bun run openapi-ts

updatedep:
	uv sync -U
	$(MAKE) build

syncdeps:
	uv sync
	$(MAKE) build
