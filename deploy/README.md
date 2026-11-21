# Deploy scale-to-zero no Azure Container Apps

Deploy **`minReplicas=0` + fila + KEDA** — o contêiner só roda (e só é cobrado)
enquanto há uma redação para corrigir. Para o deploy simples (`minReplicas=1`,
Redis embutido, sem fila), rode a imagem padrão com `QUEUE_BACKEND=memory` e pule
este guia.

Este diretório é **Infraestrutura como Código** — o deploy inteiro é um comando:

```
deploy/
├── main.bicep            # toda a infra (Storage+fila, env, Container App, KEDA)
├── deploy.sh             # orquestra: build da imagem → bicep → (híbrido) artefatos no Blob → setWebhook
└── .env.deploy.example   # copie p/ .env.deploy e preencha (gitignorado)
```

## Por que essa arquitetura

O handler do webhook responde `200` em <200ms e **enfileira** o trabalho; um
worker (dentro do mesmo contêiner, iniciado no lifespan da app) drena a fila e
faz OCR + LLM — até `QUEUE_MAX_CONCURRENCY` mensagens em paralelo (padrão 8), para
a correção de um aluno não travar a conversa dos outros. A fila é durável, então a carga pendente fica **visível para o
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
- **`maxReplicas=1`.** Uma réplica basta para o volume atual: dentro dela o
  worker já processa várias mensagens em paralelo.

### Container Apps Environment

Por padrão, o `main.bicep` cria seu próprio Container Apps Environment (+ Log
Analytics workspace). Se preferir apontar para um Environment já existente na
mesma região — por exemplo, porque sua assinatura limita quantos Environments
podem existir por região —, defina `existingEnvironmentId` (parâmetro do
Bicep) com o resource ID dele; o `deploy.sh` também tenta descobrir um
automaticamente se `EXISTING_ENV_ID` não estiver fixado no `.env.deploy`.

O Environment precisa ser do tipo **padrão**: o modo **Express** do Container
Apps não aceita regras de escala customizadas (KEDA), e a regra `azure-queue` é o
que mantém a réplica viva enquanto há redação na fila. A descoberta automática
ignora Environments Express, e um `EXISTING_ENV_ID` Express é recusado antes do
Bicep. Ao criar um Environment, o `main.bicep` declara o tipo explicitamente
(`environmentMode: 'WorkloadProfiles'`, só com o perfil Consumption, sem custo
fixo): sem o campo, a plataforma cria um Express. Hoje ele só existe na API
preview, por isso esse recurso usa a versão `2026-03-02-preview`.

As cotas também são separadas: um Environment Express na região não ocupa
a vaga de um padrão (confira com `az containerapp list-usages -l <região>`,
linha `ManagedEnvironmentCount`).

---

## Deploy automático (recomendado)

**1. Redis externo (Upstash — free tier, ~US$0)**

Crie um banco em <https://upstash.com> → Redis → copie a connection string TLS
(`rediss://default:<senha>@<host>:<porta>`). É a única coisa fora do Azure.

> O Upstash apaga bancos do plano gratuito que ficam muito tempo sem uso. O
> `deploy.sh` confere se o host do `REDIS_URL` resolve no DNS e para antes de
> publicar, em vez de o app quebrar na primeira mensagem do aluno. Dica: deixe o
> `REDIS_URL` do Upstash no `deploy/.env.deploy` (ele tem precedência) e, no
> `.env` da raiz, `redis://localhost:6379/0` para o `make dev` usar o Redis embutido.

> Opcionalmente, `REDIS_NAMESPACE` (env var) aplica um prefixo a todas as
> chaves Redis — útil se este banco for compartilhado entre múltiplos
> ambientes/deploys, evitando colisão de chave entre eles. Vazio (padrão) =
> sem prefixo.

**2. Preencha a config**

Os **segredos do app** (REDIS_URL, TELEGRAM_BOT_TOKEN, MISTRAL_API_KEY,
DEEPSEEK_API_KEY, …) são **herdados do `.env` da raiz** — o `deploy.sh` carrega
ele automaticamente. Você só precisa da config de **Azure**. O Langfuse (opcional) também vem do `.env`: com `LANGFUSE_PUBLIC_KEY` e
`LANGFUSE_SECRET_KEY` preenchidas, viram segredos do Container App; vazias, o
Langfuse fica desligado.

```bash
cp deploy/.env.deploy.example deploy/.env.deploy
# edite deploy/.env.deploy: só RESOURCE_GROUP e LOCATION. O dono da imagem no
# GHCR é deduzido do `git remote origin` (ou defina GHCR_OWNER).
# Segredos só entram aqui se quiser um valor DIFERENTE do .env em produção.
```

**3. Login no GitHub Container Registry (uma vez)**

A imagem é construída com o **Docker local** e publicada como **pacote público**
no `ghcr.io` — grátis, ao contrário do Azure Container Registry Basic, que cobra
uma diária fixa (~US$ 5/mês) mesmo parado. Publicar a imagem não expõe nada: o
`.dockerignore` deixa de fora `.env`, `_local/` e afins, e os segredos entram como
secrets do Container App. O push exige um token com o escopo `write:packages`:

```bash
gh auth refresh -h github.com -s write:packages
gh auth token | docker login ghcr.io -u <seu-usuario> --password-stdin
```

**4. Rode**

```bash
az login          # assinatura de estudante
make deploy       # atalho para ./deploy/deploy.sh
```

O script cria o resource group, builda a imagem localmente, envia para o
`ghcr.io/<dono>/enem-reviewer` com uma tag nova por deploy (data + commit, para o
Container App sempre subir uma revisão nova), aplica o `main.bicep` e registra o
webhook do Telegram. Ao fim ele imprime a URL do app, a imagem e o comando de logs.

> **Modo híbrido (`CORRECTION_MODE=hibrido` no `.env`):** o script exige o
> `JEV_API_KEY` e os 4 artefatos do modelo em `src/correction/hybrid/artifacts/`
> (gerados no laboratório). O modelo **nunca vai na imagem**, que é pública: o
> `.dockerignore` exclui a pasta, e o script confere a imagem antes do push. Depois
> do Bicep, ele envia os arquivos para o contêiner **privado** `hybrid-artifacts`
> do Storage Account. O app baixa por um link SAS só de leitura (secret
> `HYBRID_ARTIFACTS_URL`, validade de 2 anos, renovado a cada deploy): ao iniciar
> e, se ainda não houver, antes da primeira correção híbrida. A revisão nova sobe
> antes do upload, então numa troca de modelo ela pegaria os arquivos antigos: se
> houver réplica no ar, o script a reinicia depois do upload.

> **Primeira publicação:** o GitHub cria o pacote como **privado**, e o Container
> App não conseguiria baixá-lo sem credenciais. O script confere isso como um
> cliente anônimo e, se estiver privado, para com o link para trocar a
> visibilidade (só dá pela web: *Package settings → Change visibility → Public*).
> Depois é só rodar `make deploy` de novo.

> **Sanidade de custo:** o Bicep fixa `minReplicas=0`. Compute em US$0 quando
> ocioso; o tempo ativo cabe na cota grátis mensal (por assinatura Azure). A
> fila custa frações de centavo, e a imagem no GHCR público, nada.

> **Migrando de um deploy antigo com ACR:** versões anteriores deste script
> criavam um Azure Container Registry no resource group. O `deploy.sh` avisa se
> ainda existir um e mostra o comando para apagá-lo
> (`az acr delete -n <nome> -g <RG> --yes`) — rode depois de conferir que o app
> subiu com a imagem do GHCR. A variável `ACR_NAME` do `.env.deploy` deixou de ser
> usada.

### WhatsApp (opcional)

Com `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `META_APP_SECRET` e `META_VERIFY_TOKEN` no `.env`, o deploy liga o canal na
nuvem. Como a entrada HTTP só aceita IPs liberados, o `deploy.sh` busca a cada deploy as faixas IPv4 da Meta
(AS32934, via RIPEstat), junta as vizinhas e as libera junto com as do Telegram. A Meta pode mudar essas faixas: se o
WhatsApp parar de receber mensagens, rode o deploy de novo (a Meta também avisa por e-mail quando as entregas do
webhook falham).

O callback é configurado uma vez no painel da Meta (app → WhatsApp → Configuração → Webhook):
`https://<app>/v1/webhook/whatsapp`, com o `META_VERIFY_TOKEN` e o campo `messages` assinado. Acorde o app antes
(uma mensagem ao bot do Telegram), porque a validação da Meta não espera o cold start. Só existe um callback por app
da Meta: apontá-lo para o Azure tira o teste local pelo ngrok do ar.

## Verificação

```bash
az containerapp logs show -n enem-reviewer -g <RG> --follow
```

- Boot deve logar `queue_worker_started`; fim de cada correção, `essay_flow_completed`.
- Sem tráfego por alguns minutos → réplica cai para 0
  (`az containerapp replica list -n enem-reviewer -g <RG>`).
- Primeira mensagem após ociosidade → cold-start de ~45 s (a imagem é baixada de novo
  do GHCR a cada acordar); a réplica só desliga após 10 min ocioso (`cooldownSeconds`).
- A entrada HTTP só aceita as faixas de IP do Telegram (`ingressAllowedCidrs`): um
  `curl` no `/health` a partir da sua máquina recebe **403** — é o esperado. Para
  conferir a saúde, use `az containerapp revision list` e os logs.

---

## Referência: o que o Bicep provisiona

| Recurso | Papel |
|---|---|
| Storage Account + fila `essay-jobs` | Fila durável de jobs (KEDA lê o tamanho dela) |
| Contêiner de Blob `hybrid-artifacts` (privado) | Modelo do modo híbrido; o app lê por link SAS só de leitura |
| Log Analytics workspace | Logs do Container App |
| Container Apps Environment | Ambiente gerenciado do app (criado por padrão; opcionalmente reaproveita um existente — ver `existingEnvironmentId`) |
| Container App (`minReplicas=0`, `maxReplicas=1`) | O app: uvicorn (webhook) + worker (drena a fila) |

Parâmetros úteis do `main.bicep` (todos com default sensato): `appName`, `cpu`
(`0.5`), `memory` (`1.0Gi`), `queueVisibilityTimeout` (`300`), `queuePollInterval`
(`3`), `correctionProvider/Model/Effort`, `correctionMode` (`llm` ou `hibrido`). Segredos entram como parâmetros
`@secure()` (o `deploy.sh` os passa a partir do `.env.deploy`) e viram secrets do
Container App, referenciados por `secretRef` nas env vars.
