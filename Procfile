web: gunicorn config.asgi --workers 2 --bind 0.0.0.0:$PORT --worker-class uvicorn.workers.UvicornWorker
release: python manage.py migrate