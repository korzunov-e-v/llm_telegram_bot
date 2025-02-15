# PROD
build-prod:
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//')
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//') docker compose -f docker-compose.prod.yml build

up-prod:
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//') docker compose -f docker-compose.prod.yml up --force-recreate -d bot mongo

up-prod-mongo-express:
	TAG=1.0.0 docker compose -f docker-compose.prod.yml up --force-recreate -d mongo-express

down-prod:
	TAG=1.0.0 docker compose -f docker-compose.prod.yml down --remove-orphans bot mongo

down-prod-mongo-express:
	TAG=1.0.0 docker compose -f docker-compose.prod.yml down --remove-orphans mongo-express


# DEV
build-dev:
	COMMIT_SHA=$(shell git rev-parse --short HEAD)
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml build

up-dev:
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml up --force-recreate -d bot mongo
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml up --force-recreate -d bot mongo

up-dev-mongo-express:
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml up --force-recreate -d bot mongo
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml up --force-recreate -d mongo-express

down-dev:
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml down --remove-orphans bot mongo

down-dev-mongo-express:
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml down --remove-orphans mongo-express


# LOCAL
build:
	docker compose -f docker-compose.local.yml build

up:
	docker compose -f docker-compose.local.yml up --force-recreate

down:
	docker compose -f docker-compose.local.yml down --remove-orphans
