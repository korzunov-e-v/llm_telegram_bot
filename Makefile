up-dev:
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml up --force-recreate -d bot mongo

up-prod:
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//') docker compose -f docker-compose.prod.yml up --force-recreate -d bot mongo

build-dev:
	COMMIT_SHA=$(shell git rev-parse --short HEAD)
	COMMIT_SHA=$(shell git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml build

build-prod:
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//')
	TAG=$(shell git describe --contains HEAD | sed -E 's/(^v)//') docker compose -f docker-compose.prod.yml build

build:
	docker compose -f docker-compose.local.yml build

up:
	docker compose -f docker-compose.local.yml up --force-recreate

down:
	docker compose -f docker-compose.local.yml down --remove-orphans
