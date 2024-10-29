run:
	./node_modules/.bin/concurrently "docker compose -f local.yml up --remove-orphans" "npm run dev"

build:
	docker compose -f local.yml build

build-prod:
	docker build -t totem-prod -f compose/production/django/Dockerfile .

test:
	docker compose -f local.yml run --rm django coverage run -m pytest -n auto

tasks:
	docker compose -f local.yml run --rm django python manage.py totem_tasks

shell:
	docker compose -f local.yml run --rm django bash

dbshell:
	docker compose -f local.yml exec postgres bash

sqlshell:
	docker compose -f local.yml exec postgres psql -U debug -d totem

pyshell:
	docker compose -f local.yml run --rm django ./manage.py shell_plus

deploy:
	git push dokku

deploy-prod:
	git push dokku-prod

assets-watch:
	npm run dev

assets:
	npm run build

.venv:
	python3 -m venv .venv

install_local: .venv
	source .venv/bin/activate && uv sync --frozen
	npm install

fixtures:
	docker compose -f local.yml run --rm django python manage.py load_dev_data

migrations: ## Create DB migrations in the container
	@docker compose -f local.yml run django python manage.py makemigrations

migrate: ## Run DB migrations in the container
	@docker compose -f local.yml run django python manage.py migrate

generate_api_models:
	@docker compose -f local.yml run django python manage.py export_openapi_schema --api totem.api.api.api > openapi.json
	@npm run openapi-ts

updatedep:
	uv sync

.PHONY: run test shell migrate deploy assets
