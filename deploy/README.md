# Deploy scale-to-zero no Azure Container Apps

Deploy **`minReplicas=0` + fila + KEDA** — o contêiner só roda (e só é cobrado)
enquanto há uma redação para corrigir. Para o deploy simples (`minReplicas=1`,
Redis embutido, sem fila), rode a imagem padrão com `QUEUE_BACKEND=memory` e pule
este guia.

Este diretório é **Infraestrutura como Código** — o deploy inteiro é um comando:

```
deploy/
├── main.bicep            # toda a infra (Storage+fila, env, Container App, KEDA)
├── deploy.sh             # orquestra: build da imagem → bicep → setWebhook
└── .env.deploy.example   # copie p/ .env.deploy e preencha (gitignorado)
```

## Por que essa arquitetura

O handler do webhook responde `200` em <200ms e **enfileira** o trabalho; um
worker (dentro do mesmo contêiner, iniciado no lifespan da app) drena a fila e
faz OCR + LLM. A fila é durável, então a carga pendente fica **visível para o
autoscaler** — coisa que uma `asyncio.Task` em memória não é. Isso permite:

- **Réplica em 0 quando ocioso** → cobrança de compute **zero** (doc oficial:
  *"When a revision is scaled to zero replicas, no resource consumption charges
  are incurred"*). O pouco de tempo ativo cabe na cota grátis mensal.
- **Cold-start no webhook**: a regra de escala HTTP acorda o contêiner (alguns
  segundos — tolerável no Telegram, arriscado no WhatsApp pelo SLA de 200ms).
- **KEDA azure-queue scaler**: mantém 1 réplica viva enquanto a fila tem
  mensagem; volta a 0 quando esvazia (após o `cooldownPeriod`, ~300s).

### Trade-offs que você aceita

- **Redis externo é obrigatório.** O embutido morre quando a réplica dorme,
  levando o estado da conversa multi-turno junto. Use Upstash (free tier). Por
  isso o Bicep **não** provisiona Redis (Azure Cache for Redis não é free, ~US$16/mês).
- **Reentrega rara em crash.** A mensagem só sai da fila DEPOIS de processada; se
  o contêiner morrer no meio, ela reaparece após o `QUEUE_VISIBILITY_TIMEOUT` e
  reprocessa (OCR/LLM em dobro). Raro e aceitável para uso pessoal/escolar.
- **`maxReplicas=1`.** Evita workers concorrentes; ample para o volume atual.

### Container Apps Environment

Por padrão, o `main.bicep` cria seu próprio Container Apps Environment (+ Log
Analytics workspace). Se preferir apontar para um Environment já existente na
mesma região — por exemplo, porque sua assinatura limita quantos Environments
podem existir por região —, defina `existingEnvironmentId` (parâmetro do
Bicep) com o resource ID dele; o `deploy.sh` também tenta descobrir um
automaticamente se `EXISTING_ENV_ID` não estiver fixado no `.env.deploy`.

---

## Deploy automático (recomendado)

**1. Redis externo (Upstash — free tier, ~US$0)**

Crie um banco em <https://upstash.com> → Redis → copie a connection string TLS
(`rediss://default:<senha>@<host>:<porta>`). É a única coisa fora do Azure.

> Opcionalmente, `REDIS_NAMESPACE` (env var) aplica um prefixo a todas as
> chaves Redis — útil se este banco for compartilhado entre múltiplos
> ambientes/deploys, evitando colisão de chave entre eles. Vazio (padrão) =
> sem prefixo.

**2. Preencha a config**

Os **segredos do app** (REDIS_URL, TELEGRAM_BOT_TOKEN, MISTRAL_API_KEY,
DEEPSEEK_API_KEY, …) são **herdados do `.env` da raiz** — o `deploy.sh` carrega
ele automaticamente. Você só precisa da config de **Azure**:

```bash
cp deploy/.env.deploy.example deploy/.env.deploy
# edite deploy/.env.deploy: só RESOURCE_GROUP, LOCATION e ACR_NAME (único global).
# Segredos só entram aqui se quiser um valor DIFERENTE do .env em produção.
```

**3. Rode**

```bash
az login          # assinatura de estudante
make deploy       # atalho para ./deploy/deploy.sh
```

O script cria o resource group, builda a imagem **na nuvem** (`az acr build` — não
precisa de Docker local), aplica o `main.bicep` e registra o webhook do Telegram.
É idempotente: rodar de novo atualiza só o que mudou. Ao fim ele imprime a URL do
app e o comando de logs.

> **Sanidade de custo:** o Bicep fixa `minReplicas=0`. Compute em US$0 quando
> ocioso; o tempo ativo cabe na cota grátis mensal (por assinatura Azure). A
> fila custa frações de centavo.

## Verificação

```bash
az containerapp logs show -n enem-reviewer -g <RG> --follow
```

- Boot deve logar `queue_worker_started`; fim de cada correção, `essay_flow_completed`.
- Sem tráfego por alguns minutos → réplica cai para 0
  (`az containerapp replica list -n enem-reviewer -g <RG>`).
- Primeira mensagem após ociosidade → cold-start de alguns segundos (esperado).

---

## Referência: o que o Bicep provisiona

| Recurso | Papel |
|---|---|
| Storage Account + fila `essay-jobs` | Fila durável de jobs (KEDA lê o tamanho dela) |
| Log Analytics workspace | Logs do Container App |
| Container Apps Environment | Ambiente gerenciado do app (criado por padrão; opcionalmente reaproveita um existente — ver `existingEnvironmentId`) |
| Container App (`minReplicas=0`, `maxReplicas=1`) | O app: uvicorn (webhook) + worker (drena a fila) |

Parâmetros úteis do `main.bicep` (todos com default sensato): `appName`, `cpu`
(`0.5`), `memory` (`1.0Gi`), `queueVisibilityTimeout` (`300`), `queuePollInterval`
(`3`), `correctionProvider/Model/Effort`. Segredos entram como parâmetros
`@secure()` (o `deploy.sh` os passa a partir do `.env.deploy`) e viram secrets do
Container App, referenciados por `secretRef` nas env vars.
