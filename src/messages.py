"""Toda a copy de UX do bot — separada da lógica (padrão do projeto pai).

Dialeto: markdown do WhatsApp (*negrito*, _itálico_) — o TelegramChannel
renderiza o mesmo dialeto e o WhatsAppChannel não o altera (to_whatsapp_markdown
é idempotente para essa sintaxe). Títulos de botão têm teto de 20 chars no
WhatsApp — todos os títulos aqui respeitam isso.
"""

# ── Consentimento (LGPD — alunos são menores de idade) ─────────────────────

# Serviços externos por onde a redação passa: o termo precisa nomeá-los (LGPD — transparência e transferência
# internacional). O handler escolhe a variante pelo CORRECTION_MODE e preenche {llm} com o rótulo do provedor.
LLM_PROVIDER_LABELS = {
    "deepseek": "*DeepSeek* (China)",
    "gemini": "*Gemini* (Google, EUA)",
    "claude": "*Claude* (Anthropic, EUA)",
    "openai": "*ChatGPT* (OpenAI, EUA)",
    "maritaca": "*Sabiá* (Maritaca AI, Brasil)",
}

CONSENT_INTRO = (
    "Olá! 👋 Eu sou o *Corretor ENEM*: corrijo redações no modelo do ENEM, com "
    "nota estimada por competência e dicas de melhoria.\n\n"
    "Antes de começar, preciso do seu aceite:\n"
)
# Quem já aceitou uma versão anterior do termo (o texto mudou: provedor, modo, prazo de guarda etc.).
CONSENT_INTRO_UPDATED = (
    "📄 *O termo de uso mudou* desde o seu último aceite. Para continuar, "
    "preciso que você aceite a versão nova:\n"
)
# {minutos} = FLOW_TTL_SECONDS em minutos (preenchido no handler): o estado da conversa expira no próprio Redis.
_CONSENT_STORAGE = (
    "• Eu descarto a foto logo depois da leitura. Enquanto a correção não "
    "termina, o texto lido fica guardado por até {minutos} minutos num banco de "
    "dados em São Paulo. Depois da correção eu apago tudo: só ficam o registro "
    "do seu aceite e contadores de uso diário. Os serviços externos podem "
    "manter cópias por um tempo, conforme as regras de cada um.\n"
)
_CONSENT_OUTRO = "• Se você tem menos de 18 anos, leia este aviso com um responsável.\n\nVocê aceita?"

# Modo híbrido: a nota vem do modelo de machine learning (sobre as respostas do Jev) e o LLM só escreve o feedback.
# Corpo do termo (sem a saudação): é o que define a versão do aceite (ver flow/handlers.py).
CONSENT_TERMS_HIBRIDO = (
    "• Para corrigir, sua redação passa por três serviços externos: o *Mistral* "
    "(França) lê a foto, o *Jev* (TypeSafe AI, EUA) analisa o texto e o {llm} "
    "escreve os comentários.\n"
    + _CONSENT_STORAGE
    + "• A nota vem de um modelo de aprendizado de máquina treinado com milhares de "
    "redações reais corrigidas, e os comentários são escritos por inteligência "
    "artificial. A nota é uma *estimativa*: não substitui a avaliação oficial.\n"
    + _CONSENT_OUTRO
)

# Modo llm: o próprio LLM dá a nota e escreve o feedback (o Jev não é usado).
CONSENT_TERMS_LLM = (
    "• Para corrigir, sua redação passa por dois serviços externos: o *Mistral* "
    "(França) lê a foto e o {llm} faz a correção.\n"
    + _CONSENT_STORAGE
    + "• A correção é feita por inteligência artificial e a nota é uma "
    "*estimativa*: não substitui a avaliação oficial.\n"
    + _CONSENT_OUTRO
)

# Modo "ambos": o aluno escolhe a cada correção quem dá a nota (o Jev só entra na nota pelo modelo treinado).
CONSENT_TERMS_AMBOS = (
    "• Para corrigir, sua redação passa por serviços externos: o *Mistral* "
    "(França) lê a foto e o {llm} escreve os comentários. Se você escolher a nota "
    "pelo modelo treinado, o *Jev* (TypeSafe AI, EUA) também analisa o texto.\n"
    + _CONSENT_STORAGE
    + "• Você escolhe quem dá a nota: um modelo de aprendizado de máquina treinado "
    "com milhares de redações reais corrigidas, ou a própria inteligência "
    "artificial. Nos dois casos a nota é uma *estimativa*: não substitui a "
    "avaliação oficial.\n"
    + _CONSENT_OUTRO
)

CONSENT_REQUEST_HIBRIDO = CONSENT_INTRO + CONSENT_TERMS_HIBRIDO
CONSENT_REQUEST_LLM = CONSENT_INTRO + CONSENT_TERMS_LLM

CONSENT_BTN_YES = {"id": "consent_yes", "title": "Aceito ✅"}
CONSENT_BTN_NO = {"id": "consent_no", "title": "Não aceito"}

CONSENT_DECLINED = (
    "Tudo bem, respeitado! 🙂 Nenhum dado seu foi guardado.\n\n"
    "Se mudar de ideia, é só mandar qualquer mensagem que eu pergunto de novo."
)

# ── Menu / ajuda ────────────────────────────────────────────────────────────

_THEME_REQUEST = (
    "*Digite o tema* da redação, do jeito que ele aparece na proposta.\n\n"
    "_Exemplo: \"Desafios para a valorização de comunidades e povos "
    "tradicionais no Brasil\"_"
)

# Logo após o aceite do termo o fluxo já começa (uma mensagem a menos que um menu com botão "começar").
WELCOME_START = (
    "Pronto! ✅\n\n"
    "Para corrigir uma redação eu preciso, nessa ordem:\n"
    "1️⃣ O *tema* da redação (digitado)\n"
    "2️⃣ Os *textos motivadores*, se você tiver (opcional)\n"
    "3️⃣ A *foto* da sua redação manuscrita (ou o texto digitado)\n\n"
    "Vamos começar! " + _THEME_REQUEST
)

HELP_MENU = (
    "Eu corrijo redações no modelo do ENEM. 📝\n\n"
    "Como funciona:\n"
    "1️⃣ Você me diz o *tema*\n"
    "2️⃣ Cola os *textos motivadores* (se tiver)\n"
    "3️⃣ Manda a *foto* da redação (ou o texto digitado)\n\n"
    "E eu devolvo a nota estimada (0 a 1000) por competência, com dicas "
    "citando trechos do seu texto.\n\n"
    "_Para recomeçar do zero a qualquer momento: /cancelar_"
)

BTN_START = {"id": "start_correction", "title": "Corrigir redação ✍️"}

# ── Fluxo: tema ─────────────────────────────────────────────────────────────

ASK_THEME = "Vamos lá! ✍️\n\n" + _THEME_REQUEST

THEME_MUST_BE_TEXT = (
    "Nesta etapa eu preciso do tema *digitado como texto*, não em foto. 🙏\n\n"
    "Pode escrever exatamente como está na proposta."
)

THEME_TOO_SHORT = (
    "Hmm, esse tema ficou muito curto. 🤔\n\n"
    "Digite o tema completo da proposta, por favor — ele costuma ser uma "
    "frase inteira."
)

# ── Fluxo: textos motivadores ───────────────────────────────────────────────

ASK_MOTIVATORS = (
    "Tema anotado! ✅\n\n"
    "Agora, se você tiver os *textos motivadores* da proposta, cole eles aqui "
    "(pode mandar em mais de uma mensagem).\n\n"
    "Se não tiver, é só pular."
)

BTN_SKIP_MOTIVATORS = {"id": "skip_motivators", "title": "Pular ⏭️"}
BTN_DONE_MOTIVATORS = {"id": "done_motivators", "title": "Concluir ✅"}

MOTIVATORS_RECEIVED = (
    "Recebido! 📄\n\n"
    "Pode colar mais textos motivadores, ou toque em *Concluir* para ir "
    "para a foto da redação."
)

MOTIVATORS_MUST_BE_TEXT = (
    "Os textos motivadores precisam vir *digitados/colados como texto*, "
    "não em foto. 🙏\n\n"
    "Se não tiver como colar, sem problema: é só pular."
)

# ── Fluxo: foto da redação ──────────────────────────────────────────────────

ASK_ESSAY_PHOTO = (
    "Agora a parte principal: mande a *foto da sua redação*. 📸\n\n"
    "Dicas para a leitura sair perfeita:\n"
    "• Boa iluminação, sem sombra na folha\n"
    "• Folha inteira no enquadramento, sem cortar linhas nem pegar muito "
    "da mesa ao redor\n"
    "• Foto de frente (não inclinada)\n"
    "• Capricha na letra: quanto mais legível, mais fácil a leitura — e "
    "menos ajuste manual depois\n\n"
    "✍️ Sem uma foto boa? Você também pode *digitar ou colar o texto* da "
    "redação aqui, numa mensagem só.\n"
    "⚠️ Escreva exatamente como está na folha, com os mesmos erros: se o "
    "corretor automático do celular consertar palavras, a nota de escrita "
    "(Competência 1) sai mais alta do que seria."
)

ESSAY_OCR_FAILED = (
    "Não consegui ler o texto direito nessa foto. 😕\n\n"
    "Tenta de novo com mais luz e a folha inteira no quadro? Se a letra "
    "estiver muito clara, aproxima um pouco a câmera."
)

ESSAY_AWAITING_PHOTO_REMINDER = (
    "Estou esperando a *foto* da sua redação 📸 ou o *texto completo*, "
    "digitado ou colado numa mensagem só.\n\n"
    "_Se quiser recomeçar (mudar o tema, por exemplo): /cancelar_"
)

OCR_PREVIEW = (
    "Li o seguinte texto na sua foto: 👇\n\n"
    "─────────────\n"
    "{ocr_text}\n"
    "─────────────\n\n"
    "Confere se a leitura está fiel ao que você escreveu.\n"
    "• Se a redação tem *mais de uma foto* (verso, segunda folha), é só "
    "mandar a próxima foto agora.\n"
    "• Se a leitura errou algumas palavras, toque em *Editar texto* para "
    "ajustar você mesmo."
)
# Um modo só: há o botão "Refazer foto". Dois modos: os 3 botões do WhatsApp vão para os modos e "Editar texto".
OCR_REDO_BUTTON_HINT = "\n• Se saiu muito ruim, toque em *Refazer foto*."

OCR_FLAGGED_NOTE = (
    "\n\n⚠️ *Palavras a conferir* — a leitura ficou em dúvida nestas: {words}.\n"
    "_Se alguma saiu diferente da sua folha, toque em *Editar texto* e ajuste "
    "antes de corrigir._"
)

# Muitas palavras incertas = letra difícil / foto ruim no geral: em vez de listar
# dezenas, pede releitura do texto inteiro e mostra só as mais incertas.
OCR_FLAGGED_MANY_NOTE = (
    "\n\n⚠️ *A leitura desta foto ficou difícil* em várias palavras — vale reler o "
    "texto inteiro acima com atenção. Entre as mais incertas: {words}.\n"
    "_Se algo saiu diferente da sua folha, toque em *Editar texto* e ajuste antes "
    "de corrigir._"
)

BTN_CONFIRM_CORRECT = {"id": "confirm_correct", "title": "Corrigir agora ✅"}
# Modo "ambos": um botão por modo (o WhatsApp limita o título a 20 caracteres).
BTN_CORRECT_ML = {"id": "correct_ml", "title": "Modelo treinado 📊"}
BTN_CORRECT_LLM = {"id": "correct_llm", "title": "IA generativa 🤖"}
BTN_EDIT_TEXT = {"id": "edit_text", "title": "Editar texto ✏️"}
BTN_REDO_PHOTO = {"id": "redo_photo", "title": "Refazer foto 🔄"}

ASK_NEXT_PHOTO = "Manda a próxima foto da redação. 📸 (mesmas dicas: luz boa e folha inteira)"

MAX_PHOTOS_REACHED = "Você chegou ao máximo de {max_photos} fotos por redação. 🙂\n\nVou seguir com o texto que já li: {acoes}"
MAX_PHOTOS_ACTIONS_ONE = (
    "toque em *Corrigir agora*, *Editar texto* para ajustar a leitura, ou "
    "*Refazer foto* para começar as fotos de novo."
)
MAX_PHOTOS_ACTIONS_TWO = (
    "escolha nos botões quem dá a nota, toque em *Editar texto* para ajustar a "
    "leitura, ou mande /refazer para começar as fotos de novo."
)

# ── Fluxo: edição manual do texto OCR ───────────────────────────────────────

EDIT_TEXT_INSTRUCTIONS = (
    "Beleza! ✏️ Vou te mandar o texto completo na próxima mensagem.\n\n"
    "1️⃣ Toque e segure a mensagem para *copiar*\n"
    "2️⃣ Cole aqui, ajuste o que a leitura errou e envie o *texto completo* "
    "(não só o trecho corrigido)\n\n"
    "⚠️ Corrija apenas o que saiu diferente da sua folha: a nota só vale se "
    "o texto for exatamente o que você escreveu à mão."
)

EDITED_TEXT_PREVIEW = (
    "Recebi! Seu texto ficou assim: 👇\n\n"
    "─────────────\n"
    "{essay_text}\n"
    "─────────────\n\n"
    "Está fiel ao que você escreveu na folha?\n"
    "{acoes}"
)
EDITED_ACTIONS_ONE = "• Se sim, toque em *Corrigir agora*.\n• Se ainda tem ajuste, toque em *Editar texto* de novo."

EDITED_TEXT_MUST_BE_TEXT = (
    "Nesta etapa eu espero o *texto ajustado* da redação, colado como "
    "texto — não foto. 🙏\n\n"
    "Copie o texto que te mandei, ajuste e envie de volta."
)

EDITED_TEXT_TOO_SHORT = (
    "Esse texto ficou curto demais para ser a redação inteira. 🤔\n\n"
    "Cole o texto *completo* já ajustado (não só o pedaço corrigido) e "
    "envie de novo."
)

# Redação digitada ou colada no lugar da foto (sem OCR): eco para o aluno conferir antes de corrigir.
TYPED_TEXT_PREVIEW = (
    "Recebi o texto da sua redação! 👇\n\n"
    "─────────────\n"
    "{essay_text}\n"
    "─────────────\n\n"
    "Está igual ao que você escreveu na folha, com os mesmos erros?\n"
    "{acoes}"
)
TYPED_ACTIONS_ONE = "• Se sim, toque em *Corrigir agora*.\n• Se precisar ajustar, toque em *Editar texto*."

# Fecho do preview da leitura, que vai junto com os botões (um modo só).
CHOOSE_ACTION = "O que fazemos?"

# Modo "ambos": fecho com a escolha de quem dá a nota (texto aprovado pelo dono). A diferença descrita é a medida:
# corrigindo a mesma redação de novo, o modelo repetiu a nota total em 93% dos casos; a IA sozinha, em 23%.
CHOOSE_MODE = (
    "Quem dá a nota?\n"
    "📊 *Modelo treinado*: aprendeu com milhares de redações corrigidas; a nota "
    "quase não muda se você corrigir de novo.\n"
    "🤖 *IA generativa*: lê e avalia a redação sozinha; a nota pode variar de "
    "uma correção para outra.\n"
    "Nos dois, os comentários são escritos por IA."
)
REDO_COMMAND_HINT = " Se a leitura saiu ruim, mande /refazer."
EDITED_ACTIONS_TWO = "Se ainda tem ajuste, toque em *Editar texto* de novo.\n\n" + CHOOSE_MODE
TYPED_ACTIONS_TWO = "Se precisar ajustar, toque em *Editar texto*.\n\n" + CHOOSE_MODE

CONFIRMING_REMINDER = (
    "Sua redação está pronta para correção. 👇 Escolha uma opção nos botões "
    "acima, ou mande /cancelar para recomeçar."
)

# ── Correção ────────────────────────────────────────────────────────────────

CORRECTING = (
    "Tudo pronto! 🧑‍🏫 Estou corrigindo sua redação nas 5 competências do "
    "ENEM — isso leva um minutinho..."
)

# Sem botão "corrigir outra" depois do feedback: seria mais uma mensagem (o WhatsApp cobra por mensagem).
_FOOTER_NEXT = "_Quer corrigir outra redação (ou uma nova versão desta)? É só mandar /corrigir._"

_FOOTER_IA = (
    "\n\n─────────────\n"
    "_🤖 Correção automática por IA. A nota é uma estimativa: no ENEM oficial, "
    "sua redação é avaliada por dois corretores humanos._\n"
)
# Modo híbrido: a nota é do modelo de machine learning, não do LLM.
_FOOTER_ML = (
    "\n\n─────────────\n"
    "_🤖 Nota calculada por um modelo de machine learning treinado com milhares de "
    "redações reais corrigidas; os comentários são escritos por IA. A nota é uma "
    "estimativa: no ENEM oficial, sua redação é avaliada por dois corretores "
    "humanos._\n"
)
CORRECTION_FOOTER = _FOOTER_IA + _FOOTER_NEXT
CORRECTION_FOOTER_HIBRIDO = _FOOTER_ML + _FOOTER_NEXT

CORRECTION_FAILED = (
    "Tive um problema técnico na hora de corrigir. 😔 Sua redação não foi "
    "perdida — espera um instante e toca de novo no botão de correção."
)

RATE_LIMITED = (
    "Você já usou as suas {limit} correções de hoje. ⏳\n\n"
    "O limite diário existe para o corretor ficar disponível para toda a "
    "escola. Amanhã você pode mandar de novo — aproveita para revisar o "
    "feedback que já recebeu! 💪"
)

PHOTO_LIMIT_REACHED = (
    "Você já mandou {limit} fotos hoje, o máximo do dia. 📸⏳\n\n"
    "Cada foto passa por uma leitura automática que tem custo, por isso o "
    "limite é de {per_essay} fotos para cada correção do dia. Amanhã você "
    "pode mandar de novo!"
)

# ── Diversos ────────────────────────────────────────────────────────────────

CANCELLED = "Correção cancelada. 🗑️ Quando quiser recomeçar, é só mandar /corrigir."

PHOTO_UNEXPECTED = (
    "Recebi sua foto, mas ainda não sei o *tema* da redação. 🙂\n\n"
    "Para a correção sair certa, começamos pelo tema — toca no botão abaixo."
)

UNSUPPORTED_MESSAGE = (
    "Por enquanto eu só trabalho com *texto* e *foto de redação*. 🙂\n\n"
    "Manda /corrigir para começar uma correção!"
)

# ── Alerta de uso (para o dono do bot, não para o aluno) ────────────────────
# Mandado por src/usage_alerts.py ao ADMIN_TELEGRAM_CHAT_ID a cada USAGE_ALERT_EVERY_TOKENS tokens do LLM.

PROVIDER_NAMES = {
    "deepseek": "DeepSeek",
    "gemini": "Gemini",
    "claude": "Claude",
    "openai": "OpenAI",
    "maritaca": "Maritaca",
}

USAGE_ALERT = (
    "📊 *Alerta de uso do Corretor ENEM*\n\n"
    "O {provider} passou de *{milestone} tokens*.\n"
    "Acumulado: {total} tokens em {calls} correções, cerca de US$ {cost}."
)
