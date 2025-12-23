MAKEFLAGS += -j4
.PHONY: *

RUN_DJANGO = docker compose -f local.yml run --rm --remove-orphans django

run: up assets-watch livereload

up:
	docker compose -f local.yml up --remove-orphans

build:
	docker compose -f local.yml build

build-prod:
	docker build -t totem-prod -f compose/production/django/Dockerfile .

test: test-python test-js

test-js:
	bun run test:ci

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

assets-watch:
	watchexec -e js,jsx,ts,tsx,css,html bun run dev

livereload:
	bun run livereload

assets:
	bun run build

.venv:
	python3 -m venv .venv

install_local: .venv
	source .venv/bin/activate && uv sync --frozen
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
