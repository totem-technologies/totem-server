<div align="center">
<h1>Totem Server</h1>
<a href="https://github.com/ambv/black"><img alt="Black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href="https://github.com/totem-technologies/totem-server/actions/workflows/ci.yml"><img alt="GitHub Workflow Status" src="https://img.shields.io/github/actions/workflow/status/totem-technologies/totem-server/ci.yml?color=%2320A920"></a>
<p><em>Guided introspection groups at <a href="https://www.totem.org">totem.org</a></em></p>
</div>

## Basic Commands

- make
- make assets
- make test
- make deploy

### Setting Up

Requirements:

- Docker Compose
- Node.js

Steps:

- Run `make` to bring up the dev environment. You may need to make a blank `.env` file in the root directory.
- Run `make assets` to compile the assets.

### Running Tests

- Run `make test` to run the tests.

## Deployment

- `make deploy` to deploy to the staging server.
- `make deploy-prod` to deploy to the production server.
