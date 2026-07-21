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

@description('Imagem do contêiner (ex.: myacr.azurecr.io/enem-reviewer:latest).')
param containerImage string

// ── Registry privado (ACR). Deixe em branco para imagem pública. ─────────────
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
@secure()
param mistralApiKey string

// Provedor de correção plugável — só a chave do provedor escolhido é obrigatória;
// as demais podem ficar em branco (não viram secret/env se vazias).
param correctionProvider string = 'deepseek'
param correctionModel string = 'deepseek-v4-flash'
param correctionEffort string = 'max'
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

// ── Escala / recursos ────────────────────────────────────────────────────────
@description('0 = scale-to-zero (o ponto de toda a economia). Só suba se souber o porquê.')
param minReplicas int = 0
@description('1 para volume pessoal/escolar moderado — evita múltiplos workers concorrentes.')
param maxReplicas int = 1
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

resource newEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = if (createEnvironment) {
  name: '${appName}-env'
  location: location
  properties: {
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
  empty(maritacaApiKey) ? [] : [ { name: 'maritaca-api-key', value: maritacaApiKey } ]
)
var allSecrets = concat(baseSecrets, registrySecret, providerSecrets)

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
  empty(maritacaApiKey) ? [] : [ { name: 'MARITACA_API_KEY', secretRef: 'maritaca-api-key' } ]
)
var allEnv = concat(baseEnv, webhookSecretEnv, providerEnv)

// ── Container App ────────────────────────────────────────────────────────────
resource app 'Microsoft.App/containerApps@2024-03-01' = {
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
