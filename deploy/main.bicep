// Infra scale-to-zero do Corretor ENEM no Azure Container Apps.
//
// Provisiona: Storage Account + fila (essay-jobs), Container Apps Environment
// (+ Log Analytics) e o Container App com minReplicas=0 + regra KEDA
// azure-queue. O contêiner só roda (e só é cobrado) enquanto há redação na fila.
//
// NÃO provisiona o Redis: o modo scale-to-zero exige um Redis EXTERNO (o
// embutido morre ao escalar pra 0). Use Upstash (free tier) e passe a URL em
// `redisUrl`. Azure Cache for Redis não é free (~US$16/mês) e mataria a
// economia — por isso fica de fora de propósito. Ver deploy/README.md.
//
// Deploy: use deploy/deploy.sh (build da imagem + este template + setWebhook).

@description('Região dos recursos.')
param location string = resourceGroup().location

@description('Nome do Container App (e prefixo dos recursos auxiliares).')
param appName string = 'enem-reviewer'

@description('Nome da Storage Account (3-24, minúsculas/dígitos, único global).')
param storageAccountName string = toLower('enem${uniqueString(resourceGroup().id)}')

@description('''Resource ID de um Container Apps Environment já existente, para reaproveitar em
vez de criar um novo (opcional). Deixe em branco para o template criar seu próprio
Environment (comportamento padrão). Preencha se sua assinatura limita o número de
Environments por região (algumas assinaturas de avaliação/estudante permitem só 1) e
você já possui um na região de destino. Obtenha o ID com:
az containerapp env list --query "[].id" -o tsv''')
param existingEnvironmentId string = ''

@description('Nome da fila de jobs (deve casar com ESSAY_QUEUE_NAME no app).')
param queueName string = 'essay-jobs'

@description('Prefixo opcional aplicado a todas as chaves Redis. Útil se este banco Redis for compartilhado entre múltiplos ambientes/deploys, evitando colisão de chave entre eles.')
param redisNamespace string = ''

@description('Imagem do contêiner (ex.: ghcr.io/<dono>/enem-reviewer:<tag>).')
param containerImage string

// ── Registry privado (opcional). Em branco = imagem pública (padrão do       ──
// ── deploy.sh: pacote público no GHCR, sem credenciais e sem custo).         ──
param registryServer string = ''
param registryUsername string = ''
@secure()
param registryPassword string = ''

// ── Segredos de runtime ──────────────────────────────────────────────────────
@description('URL do Redis externo (Upstash), rediss://default:<senha>@<host>:<porta>.')
@secure()
param redisUrl string

@secure()
param telegramBotToken string
@secure()
param telegramWebhookSecret string = ''
@description('Chat do Telegram do dono do bot: recebe o alerta de uso a cada usageAlertEveryTokens tokens do LLM. Vazio = sem alerta.')
param adminTelegramChatId string = ''
param usageAlertEveryTokens int = 1000000
@description('Únicas origens aceitas na entrada HTTP do app. Padrão: as faixas de onde o Telegram chama webhooks (core.telegram.org/bots/webhooks; o Telegram avisa que podem mudar). Sem elas, qualquer um que descobrisse a URL podia manter a réplica acordada (custo de compute). Lista vazia (e metaAllowedCidrs vazia) = aberto a todos.')
param ingressAllowedCidrs array = [
  '149.154.160.0/20'
  '91.108.4.0/22'
]
@description('Faixas IPv4 da Meta (AS32934), somadas às do Telegram quando o WhatsApp está ligado. O deploy.sh as busca a cada deploy (RIPEstat) e junta as vizinhas; a Meta não publica uma lista fixa só de webhooks.')
param metaAllowedCidrs array = []

// WhatsApp Cloud API (opcional): sem o token, o canal fica desligado na nuvem.
@secure()
param whatsappToken string = ''
@secure()
param metaAppSecret string = ''
@secure()
param metaVerifyToken string = ''
param phoneNumberId string = ''
param whatsappApiUrl string = 'https://graph.facebook.com/v25.0'
@secure()
param mistralApiKey string

// Provedor de correção plugável — só a chave do provedor escolhido é obrigatória;
// as demais podem ficar em branco (não viram secret/env se vazias).
param correctionProvider string = 'deepseek'
param correctionModel string = 'deepseek-flash'
param correctionEffort string = 'high'
// Modo da correção: 'llm' (o LLM dá a nota), 'hibrido' (a nota vem do modelo calibrado sobre as respostas do
// Jev e o LLM só escreve o feedback — README, "Modo híbrido") ou 'ambos' (o aluno escolhe a cada correção). O híbrido
// e o 'ambos' exigem JEV_API_KEY e os artefatos do modelo.
@allowed([ 'llm', 'hibrido', 'ambos' ])
param correctionMode string = 'llm'
param jevModel string = 'jev-1.14.0'
@secure()
param jevApiKey string = ''
// Validade do link SAS (só leitura) dos artefatos do modelo; renovado a cada deploy.
param artifactsSasExpiry string = dateTimeAdd(utcNow(), 'P2Y')
@secure()
param deepseekApiKey string = ''
@secure()
param googleApiKey string = ''
@secure()
param anthropicApiKey string = ''
@secure()
param openaiApiKey string = ''
@secure()
param maritacaApiKey string = ''

// Observabilidade de custo (opcional): sem as duas chaves, o Langfuse fica desligado.
@secure()
param langfusePublicKey string = ''
@secure()
param langfuseSecretKey string = ''
param langfuseHost string = 'https://cloud.langfuse.com'

// ── Escala / recursos ────────────────────────────────────────────────────────
@description('0 = scale-to-zero (o ponto de toda a economia). Só suba se souber o porquê.')
param minReplicas int = 0
@description('1 para volume pessoal/escolar moderado — evita múltiplos workers concorrentes.')
param maxReplicas int = 1
@description('Segundos ocioso (sem requisição e com a fila vazia) até escalar a zero. 600 cobre o aluno conferindo a prévia do OCR antes de confirmar: com o padrão da plataforma (300), quem demorava mais de 5 min pagava um novo cold start (~45 s, a imagem é baixada de novo do GHCR) antes da correção. Custo: ~5 min a mais de réplica por sessão, dentro da cota grátis mensal.')
param cooldownSeconds int = 600
param cpu string = '0.5'
param memory string = '1.0Gi'
param queueVisibilityTimeout int = 300
param queuePollInterval int = 3

// ── Storage + fila ───────────────────────────────────────────────────────────
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource essayQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: queueName
}

// Artefatos do modo híbrido (modelo treinado, perguntas do Jev, checklist): contêiner PRIVADO no Blob — fora
// da imagem, que é pública no GHCR. O deploy.sh envia os arquivos; o app baixa por um link SAS só de leitura.
var artifactsContainerName = 'hybrid-artifacts'

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource artifactsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: artifactsContainerName
  properties: {
    publicAccess: 'None'
  }
}

var artifactsSas = storageAccount.listServiceSas('2023-01-01', {
  canonicalizedResource: '/blob/${storageAccount.name}/${artifactsContainerName}'
  signedResource: 'c'
  signedPermission: 'r'
  signedProtocol: 'https'
  signedExpiry: artifactsSasExpiry
}).serviceSasToken
var artifactsUrl = 'https://${storageAccount.name}.blob.${environment().suffixes.storage}/${artifactsContainer.name}?${artifactsSas}'

var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

// ── Observabilidade / Container Apps Environment ────────────────────────────
// Cria um Environment (+ Log Analytics) próprio, a menos que existingEnvironmentId
// já aponte para um (ver descrição do parâmetro acima).
var createEnvironment = empty(existingEnvironmentId)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = if (createEnvironment) {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Tipo do Environment EXPLÍCITO: sem `environmentMode`, a plataforma passou a criar Environments
// "Express", que não aceitam regra de escala customizada (KEDA) — e a regra azure-queue abaixo é
// essencial (mantém a réplica viva enquanto há redação na fila). Hoje o campo só existe na API
// preview; nas GA ele é ignorado e o Environment nasce Express. "WorkloadProfiles" com só o perfil
// Consumption = cobrança por consumo, sem custo fixo (perfis dedicados é que cobram por hora).
#disable-next-line BCP081
resource newEnvironment 'Microsoft.App/managedEnvironments@2026-03-02-preview' = if (createEnvironment) {
  name: '${appName}-env'
  location: location
  properties: {
    #disable-next-line BCP037
    environmentMode: 'WorkloadProfiles'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var environmentId = createEnvironment ? newEnvironment.id : existingEnvironmentId

// ── Secrets / env / registries (montados condicionalmente) ───────────────────
var baseSecrets = [
  {
    name: 'redis-url'
    value: redisUrl
  }
  {
    name: 'queue-connection'
    value: storageConnectionString
  }
  {
    name: 'telegram-bot-token'
    value: telegramBotToken
  }
  {
    name: 'telegram-webhook-secret'
    value: empty(telegramWebhookSecret) ? 'unset' : telegramWebhookSecret
  }
  {
    name: 'mistral-api-key'
    value: mistralApiKey
  }
]
var registrySecret = empty(registryPassword) ? [] : [
  {
    name: 'registry-password'
    value: registryPassword
  }
]
var providerSecrets = concat(
  empty(deepseekApiKey) ? [] : [ { name: 'deepseek-api-key', value: deepseekApiKey } ],
  empty(googleApiKey) ? [] : [ { name: 'google-api-key', value: googleApiKey } ],
  empty(anthropicApiKey) ? [] : [ { name: 'anthropic-api-key', value: anthropicApiKey } ],
  empty(openaiApiKey) ? [] : [ { name: 'openai-api-key', value: openaiApiKey } ],
  empty(maritacaApiKey) ? [] : [ { name: 'maritaca-api-key', value: maritacaApiKey } ],
  empty(langfusePublicKey) ? [] : [ { name: 'langfuse-public-key', value: langfusePublicKey } ],
  empty(langfuseSecretKey) ? [] : [ { name: 'langfuse-secret-key', value: langfuseSecretKey } ],
  empty(jevApiKey) ? [] : [ { name: 'jev-api-key', value: jevApiKey } ],
  correctionMode != 'llm' ? [ { name: 'hybrid-artifacts-url', value: artifactsUrl } ] : []
)
var whatsappOn = !empty(whatsappToken)
var whatsappSecrets = whatsappOn ? [
  { name: 'whatsapp-token', value: whatsappToken }
  { name: 'meta-app-secret', value: metaAppSecret }
  { name: 'meta-verify-token', value: metaVerifyToken }
] : []
var allSecrets = concat(baseSecrets, registrySecret, providerSecrets, whatsappSecrets)

var registries = empty(registryServer) ? [] : [
  {
    server: registryServer
    username: registryUsername
    passwordSecretRef: 'registry-password'
  }
]

var baseEnv = [
  { name: 'QUEUE_BACKEND', value: 'azure' }
  { name: 'ESSAY_QUEUE_NAME', value: queueName }
  { name: 'QUEUE_VISIBILITY_TIMEOUT', value: string(queueVisibilityTimeout) }
  { name: 'QUEUE_POLL_INTERVAL', value: string(queuePollInterval) }
  { name: 'ENVIRONMENT', value: 'production' }
  { name: 'CHANNEL_BACKEND', value: 'telegram' }
  { name: 'REDIS_NAMESPACE', value: redisNamespace }
  { name: 'CORRECTION_PROVIDER', value: correctionProvider }
  { name: 'CORRECTION_MODEL', value: correctionModel }
  { name: 'CORRECTION_EFFORT', value: correctionEffort }
  { name: 'CORRECTION_MODE', value: correctionMode }
  { name: 'JEV_MODEL', value: jevModel }
  { name: 'ADMIN_TELEGRAM_CHAT_ID', value: adminTelegramChatId }
  { name: 'USAGE_ALERT_EVERY_TOKENS', value: string(usageAlertEveryTokens) }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'queue-connection' }
  { name: 'TELEGRAM_BOT_TOKEN', secretRef: 'telegram-bot-token' }
  { name: 'MISTRAL_API_KEY', secretRef: 'mistral-api-key' }
]
var webhookSecretEnv = empty(telegramWebhookSecret) ? [] : [
  { name: 'TELEGRAM_WEBHOOK_SECRET', secretRef: 'telegram-webhook-secret' }
]
var providerEnv = concat(
  empty(deepseekApiKey) ? [] : [ { name: 'DEEPSEEK_API_KEY', secretRef: 'deepseek-api-key' } ],
  empty(googleApiKey) ? [] : [ { name: 'GOOGLE_API_KEY', secretRef: 'google-api-key' } ],
  empty(anthropicApiKey) ? [] : [ { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' } ],
  empty(openaiApiKey) ? [] : [ { name: 'OPENAI_API_KEY', secretRef: 'openai-api-key' } ],
  empty(maritacaApiKey) ? [] : [ { name: 'MARITACA_API_KEY', secretRef: 'maritaca-api-key' } ],
  empty(langfusePublicKey) ? [] : [ { name: 'LANGFUSE_PUBLIC_KEY', secretRef: 'langfuse-public-key' } ],
  empty(langfuseSecretKey) ? [] : [ { name: 'LANGFUSE_SECRET_KEY', secretRef: 'langfuse-secret-key' } ],
  [ { name: 'LANGFUSE_HOST', value: langfuseHost } ],
  empty(jevApiKey) ? [] : [ { name: 'JEV_API_KEY', secretRef: 'jev-api-key' } ],
  correctionMode != 'llm' ? [ { name: 'HYBRID_ARTIFACTS_URL', secretRef: 'hybrid-artifacts-url' } ] : []
)
var whatsappEnv = whatsappOn ? [
  { name: 'WHATSAPP_TOKEN', secretRef: 'whatsapp-token' }
  { name: 'META_APP_SECRET', secretRef: 'meta-app-secret' }
  { name: 'META_VERIFY_TOKEN', secretRef: 'meta-verify-token' }
  { name: 'PHONE_NUMBER_ID', value: phoneNumberId }
  { name: 'WHATSAPP_API_URL', value: whatsappApiUrl }
] : []
var allEnv = concat(baseEnv, webhookSecretEnv, providerEnv, whatsappEnv)

// ── Container App ────────────────────────────────────────────────────────────
// API 2025-01-01: GA que já aceita scale.cooldownPeriod (a 2024-03-01 não aceita).
resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        // Com ao menos uma regra Allow, toda origem fora da lista é recusada pela plataforma (antes do app).
        ipSecurityRestrictions: [
          for (cidr, i) in concat(ingressAllowedCidrs, metaAllowedCidrs): {
            name: 'permitido-${i}'
            ipAddressRange: cidr
            action: 'Allow'
          }
        ]
      }
      secrets: allSecrets
      registries: registries
    }
    template: {
      containers: [
        {
          name: appName
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: allEnv
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        cooldownPeriod: cooldownSeconds
        rules: [
          {
            // Acorda o contêiner do 0 quando chega o webhook (cold-start).
            name: 'http-wake'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
          {
            // Mantém 1 réplica viva enquanto houver job na fila; volta a 0 ao esvaziar.
            name: 'essay-queue'
            custom: {
              type: 'azure-queue'
              metadata: {
                accountName: storageAccount.name
                queueName: queueName
                queueLength: '1'
              }
              auth: [
                {
                  secretRef: 'queue-connection'
                  triggerParameter: 'connection'
                }
              ]
            }
          }
        ]
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output storageAccountNameOut string = storageAccount.name
output artifactsContainerOut string = artifactsContainer.name
