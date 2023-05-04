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

.PHONY: run test shell migrate deploy assets