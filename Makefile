run:
	npm run build
	docker compose -f local.yml up

build:
	docker-compose -f local.yml build

test:
	docker-compose -f local.yml run --rm django coverage run -m pytest
	docker-compose -f local.yml run --rm django coverage report

tasks:
	docker-compose -f local.yml run --rm django python manage.py totem_tasks

shell:
	docker-compose -f local.yml run --rm django bash

dbshell:
	docker-compose -f local.yml exec postgres bash

sqlshell:
	docker-compose -f local.yml exec postgres psql -U debug -d totem

pyshell:
	docker-compose -f local.yml run --rm django ./manage.py shell_plus

deploy:
	git push dokku

deploy-prod:
	git push dokku-prod

assets-watch:
	npm run dev

assets:
	npm run build
	cp -f node_modules/add-to-calendar-button/dist/atcb.js totem/static/js/atcb.min.js

.venv:
	python3 -m venv .venv

install_local: .venv
	source .venv/bin/activate && pip install -Ur requirements/local.txt
	npm install

pipcompile:
	pip-compile --upgrade --output-file requirements/local.txt requirements/local.in
	pip-compile --upgrade --output-file requirements/production.txt requirements/production.in

pipsync:
	pip-sync requirements/local.txt

migrations: ## Create DB migrations in the container
	@docker-compose -f local.yml run django python manage.py makemigrations

migrate: ## Run DB migrations in the container
	@docker-compose -f local.yml run django python manage.py migrate

adddep: pipcompile pipsync build

.PHONY: run test shell migrate deploy assets
