This is the API and Website for totem.org, a nonprofit that provides moderated support groups on various topics. There is also a Flutter app that uses the /mobile/ api endpoints, which is not in this codebase.

It's a standard Django app that runs in a Docker container in production and in development. It uses Postgres for the database. All the common management commands are located in the Makefile at the root, look there before trying to run any commands. For example, don't run pytest directly (this will fail, tests need to run in Docker), use `make test` to run all tests.

Django development notes:

- Use function-based views, no class views, unless it significantly simplifies the code.
- Always have Django generate migrations. You can edit the migration later if needed.
- Use Python type annotations and try to structure code so that types are effective


Javascript notes:

The front end code is in the /assets folder. The front end uses a generated OpenAPI schema (from Django Ninja) to render mini apps (via custom elements) on various MPA-style pages.

Use tailwind and SolidJS
