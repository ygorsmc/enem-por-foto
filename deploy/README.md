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

### Se este projeto conviver com o ACT Essay Reviewer na mesma assinatura

A cota mensal grátis do Container Apps (180.000 vCPU-s / 360.000 GiB-s / 2M
requisições) é **por assinatura**, compartilhada entre todos os Container Apps
dela — não uma cota extra por app. Para o volume de uso pessoal de cada
projeto, a soma dos dois continua bem dentro do grátis. Use `RESOURCE_GROUP`/
`ACR_NAME` diferentes dos do outro projeto (ACR é nome único global) — ver
`.env.deploy.example`.

---

## Deploy automático (recomendado)

**1. Redis externo (Upstash — free tier, ~US$0)**

Crie um banco em <https://upstash.com> → Redis → copie a connection string TLS
(`rediss://default:<senha>@<host>:<porta>`). É a única coisa fora do Azure.

> **Dividindo o banco com o projeto irmão (ACT).** O free tier do Upstash só
> permite **um banco por vez**, então os dois bots dividem o mesmo Redis. Para
> não colidir estado (os dois usam o canal `telegram`, e o `chat_id` é o mesmo
> por usuário nos dois bots), este projeto usa **`REDIS_NAMESPACE=enem`** —
> todas as chaves ganham o prefixo `enem:`, enquanto o ACT roda sem prefixo. Já
> está setado no `.env`; o `deploy.sh` o repassa ao contêiner. O volume somado
> cabe no limite de 10k comandos/dia com folga.

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
> ocioso; o tempo ativo cabe na cota grátis mensal (compartilhada com outros
> Container Apps da mesma assinatura, se houver). A fila custa frações de
> centavo.

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
| Container Apps Environment | Ambiente gerenciado do app |
| Container App (`minReplicas=0`, `maxReplicas=1`) | O app: uvicorn (webhook) + worker (drena a fila) |

Parâmetros úteis do `main.bicep` (todos com default sensato): `appName`, `cpu`
(`0.5`), `memory` (`1.0Gi`), `queueVisibilityTimeout` (`300`), `queuePollInterval`
(`3`), `correctionProvider/Model/Effort`. Segredos entram como parâmetros
`@secure()` (o `deploy.sh` os passa a partir do `.env.deploy`) e viram secrets do
Container App, referenciados por `secretRef` nas env vars.
