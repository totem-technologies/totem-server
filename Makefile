run:
	npm run build
	docker compose -f local.yml up --build

test:
	docker-compose -f local.yml run --rm django coverage run -m pytest
	docker-compose -f local.yml run --rm django coverage report

shell: 
	docker-compose -f local.yml run --rm django bash

migrate:
	./manage makemigrations && ./manage.py migrate