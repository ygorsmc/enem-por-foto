# Corretor ENEM — atalhos de dev. `make help` lista os alvos.
# O app roda como aplicação (uvicorn src.main:app), não como pacote instalável;
# por isso o venv é usado direto (.venv/bin/...), sem `activate`.

PY := .venv/bin/python
PIP := .venv/bin/pip
RUFF := .venv/bin/ruff

.DEFAULT_GOAL := help

.PHONY: help setup up dev down logs simulate test lint fmt redis-dev tunnel tunnel-stop clean deploy

# Porta HTTP do app (usada pelo alvo tunnel).
PORT := 8000

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Docker Compose (jeito canônico: app + redis embutido num container) ──────
up: ## Sobe app + redis embutido via docker compose (porta 8000)
	docker compose up --build

down: ## Derruba o docker compose
	docker compose down

logs: ## Segue os logs do container
	docker compose logs -f

# Extrai a public_url de um túnel ngrok já ativo (API local :4040), se houver.
NGROK_EXISTING = curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | head -1 | cut -d'"' -f4

# Grava a URL do túnel em NGROK_URL no .env (espera $$url definida no shell da
# receita). O app NÃO lê essa variável — `Settings` usa extra="ignore", então ela
# só trafega como registro para colar no painel da Meta (webhook do WhatsApp) e
# no setWebhook do Telegram. Delimitador | no sed porque a URL tem barras.
NGROK_SYNC_ENV = \
	if [ ! -f .env ]; then \
		echo "  .env não encontrado — NGROK_URL não registrada."; \
	elif grep -qE '^[[:space:]]*NGROK_URL=' .env; then \
		sed -i -E "s|^[[:space:]]*NGROK_URL=.*|NGROK_URL=$$url|" .env; \
		echo "  NGROK_URL atualizada no .env"; \
	else \
		printf 'NGROK_URL=%s\n' "$$url" >> .env; \
		echo "  NGROK_URL adicionada ao .env"; \
	fi

tunnel: ## Sobe (ou reaproveita) um túnel ngrok PERSISTENTE e grava NGROK_URL no .env
	@url="$$($(NGROK_EXISTING))"; \
	if [ -n "$$url" ]; then \
		echo "Túnel ngrok já ativo: $$url"; \
		$(NGROK_SYNC_ENV); \
		exit 0; \
	fi; \
	command -v ngrok >/dev/null || { echo "ngrok não encontrado — instale e rode 'ngrok config add-authtoken <token>'"; exit 1; }; \
	echo "Iniciando ngrok em background..."; \
	nohup ngrok http $(PORT) >/dev/null 2>&1 & \
	for i in $$(seq 1 30); do \
		url="$$($(NGROK_EXISTING))"; [ -n "$$url" ] && break; sleep 0.3; \
	done; \
	if [ -z "$$url" ]; then \
		echo "ngrok não subiu em ~9s. Rode 'ngrok http $(PORT)' à mão p/ ver o erro (auth, sessão já ativa em outra conta, etc.)."; \
		exit 1; \
	fi; \
	echo "Túnel ngrok ativo: $$url"; \
	$(NGROK_SYNC_ENV)

# Lê o valor de uma chave do .env (uso: $(call ENV_VAL,CHAVE)).
ENV_VAL = sed -nE 's/^$(1)=//p' .env 2>/dev/null | tr -d '"\r' | head -1

webhook-local: ## Aponta o webhook do Telegram para o túnel atual (o passo que a URL nova do ngrok invalida)
	@url="$$($(NGROK_EXISTING))"; \
	if [ -z "$$url" ]; then echo "  Nenhum túnel ativo — rode 'make tunnel' antes."; exit 1; fi; \
	token="$$($(call ENV_VAL,TELEGRAM_BOT_TOKEN))"; \
	if [ -z "$$token" ]; then echo "  TELEGRAM_BOT_TOKEN vazio no .env — setWebhook pulado."; exit 0; fi; \
	secret="$$($(call ENV_VAL,TELEGRAM_WEBHOOK_SECRET))"; \
	resp=$$(curl -sS -m 20 "https://api.telegram.org/bot$$token/setWebhook" \
		--data-urlencode "url=$$url/v1/webhook/telegram" \
		$${secret:+--data-urlencode "secret_token=$$secret"}); \
	case "$$resp" in \
		*'"ok":true'*) echo "  setWebhook OK → $$url/v1/webhook/telegram";; \
		*) echo "  setWebhook FALHOU: $$resp"; exit 1;; \
	esac

tunnel-stop: ## Encerra o túnel ngrok persistente
	@pkill -f 'ngrok http $(PORT)' 2>/dev/null && echo "Túnel encerrado." || echo "Nenhum túnel ativo."

dev: ## Sobe o túnel + app num só comando (grava NGROK_URL no .env); segue os logs. Ctrl+C derruba só o app (túnel fica)
	@$(MAKE) --no-print-directory tunnel
	docker compose up -d --build
	@echo "Aguardando app subir em :$(PORT)..."
	@until curl -sf http://localhost:$(PORT)/health >/dev/null 2>&1; do sleep 0.5; done
	@echo ""
	@echo "App no ar. Registrando o webhook do Telegram no túnel atual:"
	-@$(MAKE) --no-print-directory webhook-local
	@url="$$($(NGROK_EXISTING))"; \
	echo "  WhatsApp (manual, painel da Meta): $$url/v1/webhook/whatsapp"; \
	echo ""
	@echo "Ctrl+C derruba o app; o túnel segue ativo ('make tunnel-stop' p/ encerrá-lo)."
	@trap 'docker compose down' INT TERM; docker compose logs -f

# ── Dev local (venv + redis avulso, pro simulador de terminal) ──────────────
setup: ## Cria o venv e instala deps de dev
	python3.12 -m venv .venv
	$(PIP) install -r requirements-dev.txt

redis-dev: ## Sobe um redis avulso só pro dev sem docker compose
	docker run -d --rm -p 6379:6379 --name corretor-redis-dev redis:7-alpine

simulate: ## Roda o REPL de conversa (OCR + correção reais; precisa do redis-dev)
	$(PY) -m scripts.simulate

# ── Deploy (Azure Container Apps, scale-to-zero) ─────────────────────────────
deploy: ## Deploy scale-to-zero no Azure (precisa de 'az login' + deploy/.env.deploy)
	./deploy/deploy.sh

# ── Qualidade ───────────────────────────────────────────────────────────────
test: ## Roda os testes unitários (puros, sem I/O)
	$(PY) -m pytest tests/unit/

lint: ## Checa lint com ruff
	$(RUFF) check src/ tests/ scripts/

fmt: ## Formata e auto-corrige com ruff
	$(RUFF) check --fix src/ tests/ scripts/
	$(RUFF) format src/ tests/ scripts/

clean: ## Encerra o redis-dev, o túnel ngrok e remove caches
	-pkill -f 'ngrok http $(PORT)' 2>/dev/null || true
	-docker rm -f corretor-redis-dev 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
