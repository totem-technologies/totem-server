run:
	npm run build
	docker compose -f local.yml up --build

test:
	docker-compose -f local.yml run --rm django coverage run -m pytest
	docker-compose -f local.yml run --rm django coverage report

shell: 
	docker-compose -f local.yml run --rm django bash

migrate:
	./manage.py makemigrations && ./manage.py migrate

deploy:
	git push dokku

deploy-prod:
	git push dokku-prod

assets:
	npm run dev

.venv:
	python3 -m venv .venv

install_local: .venv
	source .venv/bin/activate && pip install -r requirements/local.txt
	npm install

.PHONY: run test shell migrate deploy assets