# Totem Server

[![Black code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

## Basic Commands

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
