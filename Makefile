# Atalhos do curso. Exemplos:
#   make up STEP=01
#   make load STEP=01 SCRIPT=abertura-vendas VUS=200
#   make gateway CONFIG='{"latencia_ms": 5000}'
#   make diff FROM=01 TO=02

STEP ?= 01
SCRIPT ?= navegacao
ALVO ?= http://ingressa:8000
K6_IMAGE := grafana/k6:0.54.0

STEP_DIR = $(firstword $(wildcard $(STEP)*/))
COMPOSE = docker compose -f $(STEP_DIR)docker-compose.yml
PROJETO = ingressa

.PHONY: help up down logs ps stats load psql gateway cinema estado diff

help: ## Mostra esta ajuda
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Sobe a etapa do zero (banco e simuladores limpos): make up STEP=01
	@test -n "$(STEP_DIR)" || (echo "Etapa '$(STEP)' não encontrada" && exit 1)
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build --wait
	@echo ""
	@echo "  Ingressa:           http://localhost:8000/docs"
	@echo "  Gateway pagamento:  http://localhost:8001/docs"
	@echo "  Sistema do cinema:  http://localhost:8002/docs"
	@echo "  E-mails (Mailpit):  http://localhost:8025"

down: ## Derruba a etapa e apaga os dados
	$(COMPOSE) down -v --remove-orphans

logs: ## Acompanha os logs: make logs [SVC=ingressa]
	$(COMPOSE) logs -f --tail=50 $(SVC)

ps: ## Lista os containers da etapa
	$(COMPOSE) ps

stats: ## Uso de CPU e memória dos containers em tempo real
	docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
		$$(docker ps -q --filter label=com.docker.compose.project=$(PROJETO))

load: ## Roda um teste de carga: make load SCRIPT=abertura-vendas [VUS=100]
	docker run --rm -i --network $(PROJETO)_default --cpus 2 \
		-v $(CURDIR)/shared/load-tests:/scripts:ro \
		-e BASE_URL=$(ALVO) $(if $(VUS),-e VUS=$(VUS)) \
		$(K6_IMAGE) run --quiet /scripts/$(SCRIPT).js || true

psql: ## Abre o psql no banco da etapa
	$(COMPOSE) exec postgres psql -U ingressa

gateway: ## Vê/altera o gateway: make gateway [CONFIG='{"taxa_erro": 0.3}']
	@$(call admin,8001,$(CONFIG))

cinema: ## Vê/altera o cinema: make cinema [CONFIG='{"max_concorrencia": 2}']
	@$(call admin,8002,$(CONFIG))

estado: ## Fila do sistema do cinema e assentos por sessão
	@curl -s localhost:8002/admin/estado; echo

diff: ## Mostra o que mudou entre etapas: make diff FROM=01 TO=02
	@git diff --no-index --color=always -- \
		$(firstword $(wildcard $(FROM)*/)) $(firstword $(wildcard $(TO)*/)) || true

define admin
	if [ -n '$(2)' ]; then \
		curl -s -X PATCH localhost:$(1)/admin/config -H 'Content-Type: application/json' -d '$(2)'; \
	else \
		curl -s localhost:$(1)/admin/config; \
	fi; echo
endef
