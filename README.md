# Corretor ENEM 📝

<p><a href="https://github.com/ygorsmc/enem-por-foto/actions/workflows/ci.yml"><img src="https://github.com/ygorsmc/enem-por-foto/actions/workflows/ci.yml/badge.svg" alt="CI"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a></p>

Bot multicanal (**WhatsApp + Telegram**) que corrige redações do ENEM a partir de uma **foto do manuscrito**: o aluno informa o tema, cola os textos motivadores (se tiver) e manda a foto — e recebe de volta a nota estimada (0 a 1000) por competência, com feedback pedagógico citando trechos exatos do próprio texto.


## Como funciona

Toda a correção acontece dentro de uma conversa de WhatsApp ou Telegram, a partir de uma **foto do manuscrito** — o aluno não sai do mensageiro:

```
Aluno                    Bot
  │  /corrigir            │
  │◀── "digite o tema" ───┤   tema e motivadores: SÓ texto digitado
  │  tema (texto)         │   (OCR é reservado para a redação)
  │◀── "textos motivad.?"─┤
  │  textos / Pular       │
  │◀── "manda a foto" ────┤
  │  📷 foto da redação   │──▶ download (background) → Mistral OCR
  │◀── preview do OCR ────┤   foto descartada; só o texto segue
  │  [Editar texto]       │   opcional: aluno cola o texto ajustado
  │◀── eco p/ confirmar ──┤   (letra difícil → OCR imperfeito)
  │  [Corrigir agora]     │──▶ LLM + matriz de correção do ENEM
  │◀── nota + feedback ───┤   5 competências, trechos citados
```

### O fluxo, etapa por etapa

1. **Tema e textos motivadores** entram como texto digitado (o OCR fica reservado para a redação); os motivadores são opcionais.
2. **A foto da redação** (até 3 imagens, frente/verso) chega ao webhook, que apenas valida, responde `200` em <200 ms (SLA da Meta) e despacha o trabalho pesado — download da mídia, OCR e LLM — para uma task asyncio. Nunca no handler HTTP.
3. **O OCR** (Mistral `mistral-ocr-latest`) transcreve só a foto da redação. Em seguida a **foto é descartada**: apenas o texto segue adiante.
4. **Preview e edição manual**: o aluno vê a transcrição com as palavras de baixa confiança destacadas e pode ajustar o que a letra difícil fez o OCR errar; o bot ecoa a versão final para confirmação antes de corrigir.
5. **A correção** vai para um LLM com prompt de corretor especialista baseado na Matriz de Referência do INEP (5 competências, triagem de nota zero, checklist da proposta de intervenção). Volta a nota estimada por competência (0–200 cada; 0–1000 no total) e o feedback citando trechos, formatado para o mensageiro (sem tabelas/`#`).

### Arquitetura

- **Mono-container**: FastAPI + Redis no MESMO contêiner. O `entrypoint.sh` sobe o `redis-server` (só em `127.0.0.1`, nunca exposto fora do contêiner), espera o PING responder e só então executa o `uvicorn`. Um único deploy, sem Redis gerenciado à parte.
- **Estado 100% em Redis** (sem banco relacional): máquina de estados da conversa (TTL 45 min), consentimento LGPD, rate-limit diário e idempotência de webhook. O AOF em `/data` (volume) sobrevive a restart do contêiner.
- **Réplica única no modo padrão**: como o Redis embutido não é compartilhado entre réplicas, `replicas > 1` fragmentaria rate-limit, consentimento e estado de fluxo (cada réplica veria um Redis diferente). Mantenha 1 réplica (folgado para o tráfego de uma escola). Um backend de despacho plugável (`QUEUE_BACKEND`: `memory` default, ou `azure`) também habilita um deploy alternativo em **scale-to-zero** com Redis externo — ver [Deploy](#deploy-azure-container-apps) abaixo.
- **Correção plugável**: o provedor do LLM troca por env var (`CORRECTION_PROVIDER`: `gemini` | `claude` | `openai` | `deepseek` | `maritaca`; `CORRECTION_MODEL` define o modelo dentro dele — default `deepseek` / `deepseek-v4-flash`, adotado por custo × qualidade), o que permite comparar modelos rápido. O prompt é dividido em bloco estático (matriz, ~6.000 tokens) + bloco dinâmico (tema/motivadores/redação) para aproveitar cache de contexto — explícito no Gemini e no Claude, automático no OpenAI/DeepSeek (a Maritaca não documenta cache; o bloco estático é reenviado sem desconto confirmado).

### Por que mensageria, e não um app de IA

WhatsApp e Telegram costumam continuar acessíveis em redes escolares que bloqueiam ChatGPT/Gemini/Claude — a correção chega por um canal que já não é bloqueado. E como a entrada é uma *foto do manuscrito* (não texto digitado), o treino continua fiel ao formato real da prova: o aluno escreve à mão, no papel, como no dia do ENEM.

## LGPD (o público é menor de idade)

- **Consentimento explícito** no primeiro contato, antes de qualquer processamento.
- A **foto é descartada** logo após o OCR; o texto transcrito vive apenas no estado Redis, que **expira em 45 min**. Nada persiste após a correção (não há histórico).
- O feedback deixa claro que a correção é feita por IA e que a nota é uma **estimativa** (no ENEM oficial são dois corretores humanos).
- Rate-limit diário (`ESSAY_DAILY_LIMIT`, default 2) — controle de custo do fluxo OCR + LLM.

## Rodando local

Requisitos: Python 3.12, Docker, chaves `MISTRAL_API_KEY` e `GOOGLE_API_KEY`.

O `Makefile` embrulha os comandos multi-passo (`make help` lista tudo). O único passo manual é preencher as chaves:

```bash
cp .env.example .env       # preencha as chaves
make up                    # 1 único contêiner: app + redis embutido, porta 8000
```

Sem provedor de mensageria configurado, teste o fluxo completo pelo **simulador de terminal** (OCR e correção reais). Como o Redis normalmente vive dentro da imagem, para rodar o simulador FORA do Docker suba um Redis solto só para o dev:

```bash
make setup                 # cria o venv e instala deps de dev (só na 1ª vez)
make redis-dev             # redis avulso, só para dev sem Docker Compose
make simulate
# 👤 > /corrigir
# 👤 > Desafios para a valorização de comunidades tradicionais no Brasil
# 👤 > btn skip_motivators
# 👤 > foto /caminho/para/redacao.jpg
# 👤 > btn confirm_correct
```

### Testes e lint

```bash
make test                  # puros, sem I/O (Redis fake, LLM/OCR mockados)
make lint                  # ruff check; `make fmt` para auto-corrigir e formatar
```

## Conectando os canais

> **Telegram é o canal recomendado.** A partir de **01/10/2026**, o WhatsApp Business Platform passa a cobrar por mensagem de serviço (a categoria de conversa que este bot usa) — o Telegram Bot API continua gratuito. Para manter o custo operacional no menor patamar possível, prefira o Telegram como canal principal; o WhatsApp fica como opção para quem já opera nesse canal e absorve o custo por mensagem.

O teste real mais barato é o **Telegram** (token grátis no @BotFather) com um túnel local:

```bash
make dev             # sobe o app + túnel ngrok persistente, imprime a URL pública
curl "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -d "url=https://SEU-TUNEL/v1/webhook/telegram" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"      # OBRIGATÓRIO em produção
```

O túnel do `make dev` fica de pé mesmo depois de Ctrl+C (só o app cai) — reiniciar o app com `make dev` de novo reaproveita a mesma URL, sem precisar refazer o `setWebhook`. Para encerrar o túnel de vez: `make tunnel-stop`.

**WhatsApp** (Meta Cloud API): crie um app no Meta for Developers, aponte o webhook para `https://SEU-HOST/v1/webhook/whatsapp` usando o `META_VERIFY_TOKEN` do `.env`, e preencha `PHONE_NUMBER_ID`, `WHATSAPP_TOKEN` e `META_APP_SECRET`.

> Em produção, `ENVIRONMENT` ≠ `local` liga a verificação de assinatura: HMAC SHA-256 (`X-Hub-Signature-256`) no WhatsApp e secret token no Telegram.

## Deploy (Azure Container Apps)

O docker-compose é a forma canônica de rodar localmente; para produção o alvo é o Azure Container Apps, em dois modos:

### Simples (`minReplicas=1`) — sempre no ar

- **1 único Container App** (imagem deste Dockerfile — Redis já embutido, sem Azure Cache for Redis nem serviço separado).
- `minReplicas=1` **e** `maxReplicas=1` (fixo, não escala) — o Redis embutido não é compartilhável entre réplicas; ver nota acima. Para o volume de uma escola isso é folgado.
- Monte um **Azure Files** em `/data` (mesmo mount point da `VOLUME` do Dockerfile) para o AOF do Redis sobreviver a um redeploy/restart do contêiner.
- Segredos (tokens, chaves) via Key Vault/secret refs — nunca env var em texto plano no manifesto.

### Scale-to-zero (`minReplicas=0`) — só paga enquanto corrige

Para volume pessoal/baixo, `QUEUE_BACKEND=azure` desacopla receber a mensagem (webhook) de processá-la (OCR + LLM) via uma **Azure Storage Queue**, drenada por um worker no mesmo contêiner. Uma regra de escala KEDA **azure-queue** mantém uma réplica viva só enquanto a fila tem mensagem — tempo ocioso é cobrado **zero**, e o tempo ativo para volume pessoal cabe na cota mensal gratuita do Container Apps (que é **por assinatura**, não por app). Trade-offs: exige **Redis externo** (o embutido morre ao escalar pra zero — o free tier do Upstash cobre), um atraso de cold-start na primeira mensagem após ociosidade (ok no Telegram, arriscado pro SLA de 200ms do WhatsApp) e reprocessamento raro se o contêiner cair no meio de um job.

O deploy é um comando só, com um template Bicep (Infraestrutura como Código — `deploy/main.bicep`):

```bash
cp deploy/.env.deploy.example deploy/.env.deploy   # preencha a config de Azure (RG, região, nome do ACR)
az login
make deploy                                        # build da imagem na nuvem → bicep → setWebhook do Telegram, tudo automático
```

Guia completo (setup do Upstash, o que o Bicep provisiona, alternativa passo a passo): [deploy/README.md](deploy/README.md).

## Estrutura

Só o que é essencial para rodar, testar e fazer deploy do bot. O portal de
documentação renderizado fica em `docs/index.html`; a fonte que o gera e os
scripts de laboratório não fazem parte deste repositório.

```
.
├── Dockerfile              # imagem única: app + redis embutido (ver entrypoint.sh)
├── docker-compose.yml      # `make up` — forma canônica de rodar (app + redis)
├── entrypoint.sh           # sobe redis-server (127.0.0.1, pulado se REDIS_URL externo) → uvicorn
├── .dockerignore            # mantém enxuto o contexto de build na nuvem (az acr build)
├── Makefile                 # `make help` lista todos os atalhos de dev
├── pyproject.toml            # config de ruff (lint/format) e pytest
├── requirements.txt           # dependências de runtime
├── requirements-dev.txt        # + pytest/ruff (dependências de dev)
├── .env.example                 # todas as env vars documentadas — copiar para .env
│
├── deploy/                        # deploy scale-to-zero (IaC) — ver deploy/README.md
│   ├── main.bicep                    # Storage+fila, Container Apps env, KEDA azure-queue scaler
│   ├── deploy.sh                      # orquestra: build na nuvem → bicep → setWebhook do Telegram
│   └── .env.deploy.example              # config de Azure (segredos herdados do ../.env)
│
├── src/
│   ├── main.py                    # FastAPI: webhooks (valida → submit_job → 200)
│   ├── tasks.py                     # despacho de job: memory (asyncio.Task) ou azure (Storage Queue + worker)
│   ├── config.py                   # pydantic-settings — todas as env vars
│   ├── messages.py                  # toda a copy de UX (nenhuma string solta no flow/)
│   ├── prompts.py                    # prompt do corretor ENEM (Matriz do INEP; str.format, nunca f-string)
│   ├── rate_limit.py                  # limite diário de correções por aluno
│   ├── redis_client.py                 # conexão + idempotência de webhook
│   │
│   ├── channels/                        # IMessagingChannel — canais plugáveis
│   │   ├── interfaces.py                   # contrato agnóstico (InboundMessage, IMessagingChannel)
│   │   ├── factory.py                       # get_channel(name) — troca via CHANNEL_BACKEND
│   │   ├── whatsapp.py                       # WhatsApp Cloud API (Meta)
│   │   ├── telegram.py                        # Telegram Bot API
│   │   ├── markdown.py                         # *negrito*/_itálico_ → formato de cada canal
│   │   └── text_utils.py                        # chunking de mensagem longa
│   │
│   ├── flow/                             # máquina de estados da conversa (Redis)
│   │   ├── states.py                        # FlowState, FlowData, load/save/clear
│   │   └── handlers.py                       # um handler por estado do fluxo
│   │
│   └── correction/                       # OCR + correção por LLM
│       ├── ocr.py                           # Mistral OCR + palavras de baixa confiança
│       ├── corrector.py                      # lógica comum de chamada ao provedor
│       ├── interfaces.py                      # contrato ICorrector
│       ├── factory.py                          # get_corrector(provider) — troca via CORRECTION_PROVIDER
│       └── providers/                           # gemini.py, claude.py, openai_compatible.py (openai/deepseek/maritaca)
│
├── scripts/
│   └── simulate.py            # REPL de conversa com canal fake — E2E local sem provedor real
│
└── tests/
    └── unit/                     # 59 testes puros — FakeRedis + FakeChannel, sem I/O
```
