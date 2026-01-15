<div align="center">
<h1>Totem Server</h1>
<a href="https://github.com/ambv/black"><img alt="Black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href="https://github.com/totem-technologies/totem-server/actions/workflows/ci.yml"><img alt="GitHub Workflow Status" src="https://img.shields.io/github/actions/workflow/status/totem-technologies/totem-server/ci.yml?color=%2320A920"></a>
<p><em>Guided introspection groups at <a href="https://www.totem.org">totem.org</a></em></p>
</div>

## Basic Commands

- `make install_local` - Install Python (via uv) and JS dependencies for local tooling (linting, type checking, etc.)
- `make` - Start the dev environment (Docker, asset watching, livereload)
- `make assets` - Build frontend assets (Tailwind CSS, JS bundles)
- `make test` - Run Python and JS test suites
- `make deploy` - Deploy to staging server

### Setting Up

Requirements:

- Docker Compose
- [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/)

Steps:

- Run `make install_local` to install dependencies.
- Run `make` to bring up the dev environment. You may need to create a blank `.env` file in the root directory.
- Run `make assets` to compile the assets.

### Running Tests

- Run `make test` to run the tests.

## Deployment

- `make deploy` to deploy to the staging server.
- `make deploy-prod` to deploy to the production server.

## Deployment notes

- Totem used `dokku` for deployment. The `Dockerfile` is used to build the image.
  - Configure `dokku` to use the production Dockerfile: `dokku builder:set totem selected dockerfile` and `dokku builder-dockerfile:set totem dockerfile-path compose/production/django/Dockerfile`.

## Restore DB from backup

- Download backup locally
- Take app offline: `dokku ps:stop totem`
- `scp` backup into VM home folder
- `tar -xf backup.tgz`
- `docker cp backup/export dokku.postgres.totemdb:/tmp/export`
- `docker exec -i dokku.postgres.totemdb bash`

To do a full wipe and restore:
- `dropdb -U postgres totemdb`
- `createdb -U postgres -T template0 totemdb`
- `pg_restore -U postgres -d totemdb < /tmp/export`
- Then redeploy or `dokku ps:start totem`
