.PHONY: up down reset provision run logs ps

# Bring up the whole stack (builds images on first run)
up:
	docker compose up -d --build

# Stop containers (keeps data volumes)
down:
	docker compose down

# Stop and wipe volumes (fresh DB, fresh n8n)
reset:
	docker compose down -v

# Import credentials and workflow into n8n (run once after make up)
provision:
	./scripts/provision.sh

# Trigger the pipeline headlessly in a standalone container, which runs fine
# alongside the live n8n server without a task-broker port clash.
run:
	docker run --rm --network easm_easm_internal -v easm_n8n_data:/home/node/.n8n --env-file .env n8nio/n8n:latest execute --id easm-pipeline

# Tail logs
logs:
	docker compose logs -f --tail=120

ps:
	docker compose ps
