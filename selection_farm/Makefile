COMPOSE = docker compose -f docker/docker-compose.yml --env-file docker/.env

.PHONY: up down logs ps test selector bereiter trainer backup

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

test:
	pytest

selector:
	./scripts/run_selector.sh

bereiter:
	./scripts/run_bereiter.sh

trainer:
	./scripts/run_trainer.sh

backup:
	./scripts/backup_studbook.sh
