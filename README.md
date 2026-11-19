# Corretor ENEM 📝

<p><a href="https://github.com/ygorsmc/enem-por-foto/actions/workflows/ci.yml"><img src="https://github.com/ygorsmc/enem-por-foto/actions/workflows/ci.yml/badge.svg" alt="CI"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a></p>

Bot multicanal (**WhatsApp + Telegram**) que corrige redações do ENEM a partir de uma **foto do manuscrito**: o aluno informa o tema, cola os textos motivadores (se tiver) e manda a foto — e recebe de volta a nota estimada (0 a 1000) por competência, com feedback pedagógico citando trechos exatos do próprio texto.

## Teste o bot

Ele está no ar no Telegram: **[@asn_corretor_bot](https://t.me/asn_corretor_bot)**. Mande `/start`, aceite o termo e siga os passos: tema, textos motivadores (opcional) e a foto da redação.

- **Limites por conta:** 2 correções e 6 fotos por dia (3 fotos para cada correção).
- **A primeira mensagem pode levar ~45 s:** o bot desliga depois de 10 minutos sem uso e precisa acordar. Depois responde na hora, e cada correção leva cerca de 1 minuto.
- **De onde vem a nota:** de um modelo de machine learning treinado com milhares de redações corrigidas ([modo híbrido](#modo-híbrido-experimental)); o comentário é escrito por IA.
- **Para onde vai a redação:** o Mistral (França) lê a foto, o Jev (TypeSafe AI, EUA) analisa o texto e o DeepSeek (China) escreve o comentário. A foto é descartada logo após a leitura e nada fica guardado depois da correção; esses serviços podem manter cópias conforme as regras de cada um.
- A nota é uma **estimativa**: no ENEM oficial, a redação é avaliada por dois corretores humanos.


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
5. **A correção** vai para um LLM com prompt de corretor especialista baseado na Matriz de Referência do INEP (5 competências, triagem de nota zero, checklist da proposta de intervenção). Volta a nota estimada por competência (0–200 cada; 0–1000 no total) e o feedback citando trechos, formatado para o mensageiro (sem tabelas/`#`). No [modo híbrido](#modo-híbrido-experimental), a nota vem de um modelo de ML e o LLM só escreve o feedback.

### Arquitetura

- **Mono-container**: FastAPI + Redis no MESMO contêiner. O `entrypoint.sh` sobe o `redis-server` (só em `127.0.0.1`, nunca exposto fora do contêiner), espera o PING responder e só então executa o `uvicorn`. Um único deploy, sem Redis gerenciado à parte.
- **Estado 100% em Redis** (sem banco relacional): máquina de estados da conversa (TTL 45 min), consentimento LGPD, rate-limit diário e idempotência de webhook. O AOF em `/data` (volume) sobrevive a restart do contêiner.
- **Réplica única no modo padrão**: como o Redis embutido não é compartilhado entre réplicas, `replicas > 1` fragmentaria rate-limit, consentimento e estado de fluxo (cada réplica veria um Redis diferente). Mantenha 1 réplica (folgado para o tráfego de uma escola). Um backend de despacho plugável (`QUEUE_BACKEND`: `memory` default, ou `azure`) também habilita um deploy alternativo em **scale-to-zero** com Redis externo — ver [Deploy](#deploy-azure-container-apps) abaixo.
- **Correção plugável**: o provedor do LLM troca por env var (`CORRECTION_PROVIDER`: `gemini` | `claude` | `openai` | `deepseek` | `maritaca`; `CORRECTION_MODEL` define o modelo dentro dele — default `deepseek` / `deepseek-flash` (V4.1-Flash), adotado por custo × qualidade), o que permite comparar modelos rápido. O prompt é dividido em bloco estático (matriz, ~6.000 tokens) + bloco dinâmico (tema/motivadores/redação) para aproveitar cache de contexto — explícito no Gemini e no Claude, automático no OpenAI/DeepSeek (a Maritaca não documenta cache; o bloco estático é reenviado sem desconto confirmado).

### Por que mensageria, e não um app de IA

A correção chega pelo canal de **menor atrito**: sem instalar aplicativo, sem criar conta, dentro do mensageiro que o aluno já usa todo dia — inclusive no ambiente escolar, onde ferramentas de IA de uso geral raramente estão disponíveis. E como a entrada é uma *foto do manuscrito* (não texto digitado), o treino continua fiel ao formato real da prova: o aluno escreve à mão, no papel, como no dia do ENEM.

## Modo híbrido (experimental)

No modo padrão (`CORRECTION_MODE=llm`), o LLM dá a nota **e** escreve o feedback. No modo híbrido (`CORRECTION_MODE=hibrido`), a nota vem de um **modelo de ML treinado em 6.475 redações corrigidas**, e o LLM só escreve o feedback, com as notas já fixadas. Foto, OCR, preview e confirmação não mudam.

```
texto confirmado pelo aluno
   ├─► Jev: 1 chamada com {tema, redação} e 71 perguntas objetivas → probabilidades de 0 a 1
   ├─► Python: medidas do texto (contagens, estrutura, relação com o tema) e 6 notas de um TF-IDF
   ▼
ExtraTrees (C1..C5 e total) → calibração → ajuste para C1+…+C5 = total
   ├─► portão de nota zero (regras da Cartilha do INEP)
   ├─► checklist: até 2 pistas por competência, só onde a nota prevista é menor que 160
   ▼
LLM (DeepSeek, raciocínio high): recebe a redação, as notas FIXAS e as pistas → escreve o feedback
```

### O modelo de ML

- **O Jev como sensor, não como corretor.** O Jev (`jev-1.14.0`, da TypeSafe AI) responde perguntas atômicas sobre a redação, como "a proposta tem um agente definido?" ou "o repertório é legitimado?", cada uma com uma probabilidade. Usado direto para dar a nota, ele puxa tudo para o meio da escala (QWK total 0,45). Como entrada de um modelo calibrado, funciona bem.
- **Dados.** Corpus [Essay-BR](https://github.com/lplnufpi/essay-br) (MIT; redações do Brasil Escola com nota por competência) na divisão oficial: treino 4.529 · validação 970 · teste 976. Os modelos foram escolhidos na validação e medidos **uma única vez** no teste. O modelo de produção é retreinado com as 6.475.
- **Entradas (120 colunas):**

  | Grupo | Colunas | O que mede |
  |---|---:|---|
  | Respostas do Jev | 60 | 55 perguntas (a de tipo textual vira 6 colunas, uma por opção) |
  | Combinações das respostas do Jev | 10 | médias e mínimos das notas, incerteza média, "portões" (recorte × fuga × tipo textual) |
  | Medidas determinísticas do texto | 28 | palavras, parágrafos, períodos, tamanhos, pontuação |
  | Estrutura e relação com o tema | 16 | tema na introdução e na conclusão, conectivos no início dos parágrafos, períodos longos, 1ª pessoa, riqueza lexical |
  | Notas previstas por TF-IDF | 6 | um Ridge sobre palavras prevê C1..C5 e o total (por validação cruzada, sem vazamento) |

- **Modelo.** `ExtraTreesRegressor` (300 árvores, profundidade 10, no mínimo 7 redações por folha), um para cada competência e um para o total.
- **Calibração.** Modelos de regressão comprimem as notas para o meio. Um ajuste linear, feito sobre previsões fora da amostra, devolve às notas previstas a média e o desvio-padrão das notas reais.
- **Soma exata.** O total é previsto direto, e as 5 competências são projetadas nos níveis inteiros mais próximos (0, 40, …, 200) cuja soma é exatamente o total. Isso corta o erro médio em ~10 pontos.
- **Nota zero e pistas.** Um portão aplica as regras da Cartilha do INEP (fuga ao tema, texto não dissertativo, carta, identificação, impropério, texto insuficiente etc.) sobre as respostas do Jev; nas 6.475 redações normais, dispara em 0,6%. Um checklist de 38 itens gera pistas para o LLM e é calibrado para não criticar quem escreve bem: não dá pistas em competência com nota prevista de 160 ou mais.
- **71 perguntas enviadas, 55 no modelo.** O registro de perguntas guarda versões antigas e novas de alguns conceitos. O modelo usa uma pergunta por conceito, então nenhum conceito pesa em dobro. O Jev ainda responde as 71 porque as 10 colunas combinadas (como a incerteza média) foram calculadas, no treino, sobre todas as respostas; perguntar menos mudaria essas colunas em produção.

**Resultado no teste oficial** (976 redações que o modelo nunca viu):

| | C1 | C2 | C3 | C4 | C5 | QWK total | RMSE | MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Este modelo** | 0,52 | 0,59 | 0,56 | 0,67 | 0,60 | **0,726** | **125** | **97** |
| Amorim & Veloso (2017), mesmo corpus | 0,39 | 0,46 | 0,40 | 0,38 | 0,34 | 0,49 | 161 | — |
| Fonseca et al. (2018), mesmo corpus | 0,44 | 0,48 | 0,42 | 0,47 | 0,38 | 0,53 | 157 | — |

Os baselines são do artigo do corpus (Marinho, Anchiêta & Moura, *JIDM* 2022, Tabelas XI e XII). Como referência, dois corretores humanos concordam entre si com QWK total de 0,69 (Barbosa & Mauá, PROPOR 2026, em outro conjunto de dados). Em temas que o modelo nunca viu, a queda estimada é pequena (0,676 → 0,669, medida com um Ridge).

**Limitações:**
- **Viés nas pontas:** redações de até 440 pontos são superestimadas em +82 em média, e as de 720 ou mais, subestimadas em −38. É regressão à média (correlação 0,70 com a nota real); calibrar as pontas só troca um erro por outro.
- **O LLM justifica bem qualquer nota que recebe**, inclusive os erros do modelo: o feedback nunca é melhor que a nota que o alimenta.
- **O Essay-BR é texto digitado.** O efeito dos erros de OCR sobre a nota do modelo ainda não foi medido.

### Híbrido × só LLM

Medido nas **mesmas 50 redações**, sorteadas do teste oficial, com o código e o prompt do bot, DeepSeek `deepseek-flash` (V4.1-Flash) com raciocínio `high` nos dois modos. No híbrido, a nota é a do modelo treinado sem essas redações.

| | Só LLM | Híbrido (Jev + modelo + LLM) |
|---|---|---|
| Concordância com a nota real (QWK total) | 0,58 | **0,71** |
| QWK por competência (C1 a C5) | 0,17 · 0,41 · 0,35 · 0,39 · 0,58 | **0,42 · 0,52 · 0,50 · 0,67 · 0,76** |
| Erro médio na nota total (MAE) | 122 pontos | **106** pontos |
| Viés nas redações de 720 ou mais | −111 | **−3** |
| Viés nas redações de até 440 | +102 | +89 |
| Mesma redação corrigida de novo ¹ | nota idêntica em 23%; diferença média de 55 pontos, até 240 | nota idêntica em **93%**; diferença média de **3** pontos, até 40 |
| Tokens de saída do LLM | 10,4 mil | **8,4 mil** |
| Tempo médio do LLM | 59 s | **49 s** |
| Custo por correção, fora do pico ² | US$ 0,0064 | **US$ 0,0056** (com o Jev) |
| Custo por correção, no pico ² | US$ 0,0128 | **US$ 0,0108** (com o Jev) |
| O que precisa | 1 API (LLM) | 2 APIs (Jev e LLM) e o modelo treinado (28 MB) |
| Para onde vai o texto da redação | provedor do LLM | provedor do LLM **e** API do Jev |

¹ Reteste em 30 redações do teste, com o texto digitado (sem foto): o LLM corrigiu cada uma 3 vezes (DeepSeek V4 Flash, raciocínio `max`, antes do V4.1); no híbrido, o Jev respondeu 2 vezes e o modelo deu a nota (versão treinada em 600 redações, com a calibração de produção). Tabela completa e ressalvas na página de métricas, em "O modo híbrido resolve a instabilidade".
² Tabela oficial do `deepseek-flash` e tokens medidos, com 90% da entrada vindo do cache; sem o OCR, igual nos dois modos (US$ 0,004 por foto acima da cota gratuita). O pico é o horário comercial da China, que no Brasil cai no fim da noite e de madrugada; fora dele, o DeepSeek cobra metade.

Como ler a tabela:
- **A diferença na concordância é real:** +0,13 no QWK total, com intervalo de confiança de 95% entre +0,03 e +0,23. A diferença no erro médio (−16 pontos) ainda não é conclusiva com 50 redações: o híbrido errou menos em 20, mais em 11 e empatou em 19 (p = 0,15).
- **Estabilidade:** reenviar a mesma redação quase não muda a nota no híbrido. O modelo é determinístico (as mesmas respostas do Jev dão sempre a mesma nota), e as respostas do Jev mudam pouco entre execuções. No só LLM, 1 em cada 3 redações mudou 80 pontos ou mais só por ser corrigida de novo; no híbrido, nenhuma.
- **Onde o híbrido ganha:** nas notas altas e médias. O LLM puxa as boas redações para baixo (−111 nas de 720 ou mais), e o modelo, não. Nas redações fracas, os dois superestimam.
- **Um falso zero:** a regra de nota zero do híbrido zerou 1 das 50 redações (nota real 400), e ela está incluída. Sem ela, o erro médio do híbrido cai para 100.
- **Custo:** com o mesmo nível de raciocínio, o híbrido sai ~12% mais barato e 10 s mais rápido. Com raciocínio `max` (o padrão do código até 17/11/2026; hoje é `high`), o modo só LLM gera ~19 mil tokens de saída (≈ US$ 0,012 por correção fora do pico) sem ganho de acurácia medido.
- **Feedback:** o LLM respeitou as notas fixas nas 50 redações e nunca mencionou as pistas ao aluno.

### Como ativar

```bash
CORRECTION_MODE=hibrido
JEV_API_KEY=...                 # chave da API do Jev (TypeSafe AI)
CORRECTION_PROVIDER=deepseek
CORRECTION_MODEL=deepseek-flash
CORRECTION_EFFORT=high
```

Os **artefatos do modelo** (`src/correction/hybrid/artifacts/`: o modelo treinado, as perguntas do Jev e os cortes do checklist) **não estão neste repositório nem na imagem Docker**; são gerados pelo script de treino do laboratório, que também fica fora. Sem eles, use o modo padrão (`llm`). Localmente, o `docker-compose` monta a pasta no contêiner, só para leitura. No deploy, o `deploy.sh` envia os arquivos para um contêiner privado do Blob Storage, e o app os baixa por um link SAS só de leitura (ver [deploy/README.md](deploy/README.md)). As versões de `numpy`, `scipy`, `scikit-learn` e `joblib` em `requirements.txt` são fixas porque precisam ser as mesmas do treino.

## Custo e observabilidade

- **Custo em US$ de cada chamada paga** no log estruturado: `cost_usd` em `essay_corrected_openai_compatible_usage` (LLM) e em `jev_answered` (Jev), com os tokens por tipo (em cache, fora do cache, saída, raciocínio). A tabela de preços fica em `src/correction/pricing.py`. O DeepSeek cobra o dobro no horário de pico (dias úteis, 01h–04h e 06h–10h UTC, ou seja, 22h–1h e 3h–7h em Brasília), e o log registra a faixa de cada chamada (`price_window`). Modelos sem tabela registram só os tokens.
- **Langfuse (opcional):** com `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` (o plano Hobby do Langfuse Cloud é gratuito), cada correção vira um trace com uma observação por chamada paga, e o painel soma tokens e custo por dia, modelo e modo. Sem as chaves, o SDK nem é carregado.
- **Travas de custo para o bot aberto ao público:**
  - **Fotos por dia:** `PHOTOS_PER_ESSAY` (3) por correção permitida. Cada foto é uma leitura paga do OCR, e o contador de correção só sobe na confirmação.
  - **Teto de saída do LLM:** `LLM_MAX_OUTPUT_TOKENS` (32 mil, raciocínio incluído; o dobro do máximo medido em 100 correções). Sem ele, uma imagem com instruções para "escrever sem parar" levaria a chamada ao limite da API.
  - **Alerta de uso:** com `ADMIN_TELEGRAM_CHAT_ID`, o bot avisa o dono no Telegram a cada `USAGE_ALERT_EVERY_TOKENS` (1 milhão, ~60 correções) tokens do LLM, com o custo acumulado (`src/usage_alerts.py`). Só contadores agregados, nada do aluno.
  - **Entrada só do Telegram:** no deploy, o app só aceita requisições das faixas de IP de onde o Telegram chama webhooks; ninguém mais consegue acordar a réplica.
- **O Langfuse recebe só números:** modelo, tokens, custo, tempo e o modo de correção; nunca o texto da redação, o tema, o feedback nem identificador do aluno. Ele também usa um provedor de OpenTelemetry próprio, e não o global: com o global, o SDK do Mistral passaria a gerar spans das chamadas de OCR, que levam a foto, e o Langfuse os exportaria. Ver `src/observability.py`.

## LGPD (o público é menor de idade)

- **Consentimento explícito** no primeiro contato, antes de qualquer processamento. O termo nomeia os serviços externos por onde a redação passa e o país de cada um (Mistral, França; Jev, EUA, no modo híbrido; o provedor do LLM), avisa que eles podem manter cópias conforme as regras próprias e pede que menores de 18 leiam com um responsável.
- A **foto é descartada** logo após o OCR; o texto transcrito vive apenas no estado Redis, que **expira em 45 min**. Nada persiste após a correção (não há histórico).
- No **modo híbrido**, o texto da redação (nunca a foto) também é enviado à API do Jev (TypeSafe AI). Confira os termos de tratamento de dados do provedor antes de usar esse modo com alunos.
- O **Langfuse**, se ligado, recebe só números de uso e custo (ver [Custo e observabilidade](#custo-e-observabilidade)).
- O feedback deixa claro que a correção é feita por IA e que a nota é uma **estimativa** (no ENEM oficial são dois corretores humanos).
- Rate-limit diário (`ESSAY_DAILY_LIMIT`, default 2, e `PHOTOS_PER_ESSAY` fotos por correção) — controle de custo do fluxo OCR + LLM.

## Rodando local

Requisitos: Python 3.12, Docker, a chave do OCR (`MISTRAL_API_KEY`) e a do provedor de correção (no padrão, `DEEPSEEK_API_KEY`). O [modo híbrido](#modo-híbrido-experimental) pede também `JEV_API_KEY` e os artefatos do modelo.

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
make dev             # túnel + app + setWebhook do Telegram, tudo num comando
```

O `make dev` faz, nessa ordem: garante o túnel ngrok (reaproveita se já houver um ativo) → grava a URL em `NGROK_URL` no `.env` → sobe o app → registra o túnel como webhook do Telegram. A ordem importa: o `env_file` do compose é lido na *criação* do contêiner, então o túnel precisa existir antes do `up`.

**No plano free do ngrok a URL muda a cada túnel novo**, o que invalida o webhook registrado (o Telegram passa a receber `404` e o bot fica mudo). Por isso o `setWebhook` é refeito automaticamente a cada `make dev` — e `make webhook-local` reaplica sozinho, se precisar. Para o WhatsApp o passo é manual (painel da Meta): a URL fica em `NGROK_URL` no `.env`, pronta para copiar.

> **Atenção:** o bot tem um webhook só. Rodar `make dev` aponta o bot para a sua máquina, então a instância de produção para de receber mensagens até você rodar `make deploy` (que refaz o `setWebhook` para o host da nuvem no passo 4/4).

O túnel fica de pé mesmo depois de Ctrl+C (só o app cai). Para encerrar de vez: `make tunnel-stop`.

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
cp deploy/.env.deploy.example deploy/.env.deploy   # preencha a config de Azure (resource group e região)
az login
make deploy                                        # build da imagem (Docker local) → push pro ghcr.io → bicep → setWebhook do Telegram
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
├── .dockerignore            # imagem enxuta e sem segredos (publicada como pacote público no ghcr.io)
├── Makefile                 # `make help` lista todos os atalhos de dev
├── pyproject.toml            # config de ruff (lint/format) e pytest
├── requirements.txt           # dependências de runtime
├── requirements-dev.txt        # + pytest/ruff (dependências de dev)
├── .env.example                 # todas as env vars documentadas — copiar para .env
│
├── deploy/                        # deploy scale-to-zero (IaC) — ver deploy/README.md
│   ├── main.bicep                    # Storage+fila, Container Apps env, KEDA azure-queue scaler
│   ├── deploy.sh                      # orquestra: build local → push ghcr.io → bicep → setWebhook do Telegram
│   └── .env.deploy.example              # config de Azure (segredos herdados do ../.env)
│
├── src/
│   ├── main.py                    # FastAPI: webhooks (valida → submit_job → 200)
│   ├── tasks.py                     # despacho de job: memory (asyncio.Task) ou azure (Storage Queue + worker)
│   ├── config.py                   # pydantic-settings — todas as env vars
│   ├── observability.py             # Langfuse opcional: tokens e custo por chamada, só números
│   ├── messages.py                  # toda a copy de UX (nenhuma string solta no flow/)
│   ├── prompts.py                    # prompt do corretor ENEM (Matriz do INEP; str.format, nunca f-string)
│   ├── rate_limit.py                  # limites diários por aluno (correções e fotos)
│   ├── usage_alerts.py                # alerta de uso ao dono no Telegram a cada N tokens do LLM
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
│       ├── pricing.py                        # custo em US$ por chamada (DeepSeek com pico/fora do pico; Jev)
│       ├── corrector.py                      # lógica comum de chamada ao provedor
│       ├── interfaces.py                      # contrato ICorrector
│       ├── factory.py                          # get_corrector(provider) — troca via CORRECTION_PROVIDER
│       ├── providers/                           # gemini.py, claude.py, openai_compatible.py (openai/deepseek/maritaca)
│       └── hybrid/                              # CORRECTION_MODE=hibrido — ver "Modo híbrido"
│           ├── jev.py                              # cliente da API do Jev (71 perguntas)
│           ├── features.py, deterministic.py        # medidas do texto, iguais às do treino
│           ├── model.py                              # previsão + calibração (artefatos fora do repo)
│           ├── scoring.py                             # soma exata, portão de nota zero, checklist
│           └── pipeline.py                             # nota do modelo → notas fixas → feedback do LLM
│
├── scripts/
│   └── simulate.py            # REPL de conversa com canal fake — E2E local sem provedor real
│
└── tests/
    └── unit/                     # 144 testes puros — FakeRedis + FakeChannel, sem I/O
```
