"""Toda a copy de UX do bot — separada da lógica (padrão do projeto pai).

Dialeto: markdown do WhatsApp (*negrito*, _itálico_) — o TelegramChannel
renderiza o mesmo dialeto e o WhatsAppChannel não o altera (to_whatsapp_markdown
é idempotente para essa sintaxe). Títulos de botão têm teto de 20 chars no
WhatsApp — todos os títulos aqui respeitam isso.
"""

# ── Consentimento (LGPD — alunos são menores de idade) ─────────────────────

CONSENT_REQUEST = (
    "Olá! 👋 Eu sou o *Corretor ENEM*, um assistente que corrige redações "
    "no modelo do ENEM, com nota estimada por competência e dicas de melhoria.\n\n"
    "Antes de começar, preciso do seu aceite:\n"
    "• Vou processar o *texto da sua redação* e o *tema* que você enviar, "
    "apenas para gerar a correção.\n"
    "• A foto é descartada logo após a leitura — *nada fica guardado* depois "
    "da correção (só um contador de uso diário).\n"
    "• A correção é feita por inteligência artificial e a nota é uma "
    "*estimativa* — não substitui a avaliação oficial.\n\n"
    "Você aceita?"
)

CONSENT_BTN_YES = {"id": "consent_yes", "title": "Aceito ✅"}
CONSENT_BTN_NO = {"id": "consent_no", "title": "Não aceito"}

CONSENT_DECLINED = (
    "Tudo bem, respeitado! 🙂 Nenhum dado seu foi guardado.\n\n"
    "Se mudar de ideia, é só mandar qualquer mensagem que eu pergunto de novo."
)

# ── Menu / ajuda ────────────────────────────────────────────────────────────

WELCOME_MENU = (
    "Pronto! ✅\n\n"
    "Para corrigir uma redação eu preciso, nessa ordem:\n"
    "1️⃣ O *tema* da redação (digitado)\n"
    "2️⃣ Os *textos motivadores*, se você tiver (opcional)\n"
    "3️⃣ A *foto* da sua redação manuscrita\n\n"
    "Vamos começar?"
)

HELP_MENU = (
    "Eu corrijo redações no modelo do ENEM. 📝\n\n"
    "Como funciona:\n"
    "1️⃣ Você me diz o *tema*\n"
    "2️⃣ Cola os *textos motivadores* (se tiver)\n"
    "3️⃣ Manda a *foto* da redação\n\n"
    "E eu devolvo a nota estimada (0 a 1000) por competência, com dicas "
    "citando trechos do seu texto.\n\n"
    "_Para recomeçar do zero a qualquer momento: /cancelar_"
)

BTN_START = {"id": "start_correction", "title": "Corrigir redação ✍️"}

# ── Fluxo: tema ─────────────────────────────────────────────────────────────

ASK_THEME = (
    "Vamos lá! ✍️\n\n"
    "*Digite o tema* da redação, do jeito que ele aparece na proposta.\n\n"
    "_Exemplo: \"Desafios para a valorização de comunidades e povos "
    "tradicionais no Brasil\"_"
)

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
    "menos ajuste manual depois"
)

ESSAY_PROCESSING = "Foto recebida! 🔍 Estou lendo o seu texto, um instante..."

ESSAY_OCR_FAILED = (
    "Não consegui ler o texto direito nessa foto. 😕\n\n"
    "Tenta de novo com mais luz e a folha inteira no quadro? Se a letra "
    "estiver muito clara, aproxima um pouco a câmera."
)

ESSAY_AWAITING_PHOTO_REMINDER = (
    "Estou esperando a *foto* da sua redação. 📸\n\n"
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
    "ajustar você mesmo.\n"
    "• Se saiu muito ruim, toque em *Refazer foto*."
)

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
BTN_EDIT_TEXT = {"id": "edit_text", "title": "Editar texto ✏️"}
BTN_REDO_PHOTO = {"id": "redo_photo", "title": "Refazer foto 🔄"}

ASK_NEXT_PHOTO = "Manda a próxima foto da redação. 📸 (mesmas dicas: luz boa e folha inteira)"

MAX_PHOTOS_REACHED = (
    "Você chegou ao máximo de {max_photos} fotos por redação. 🙂\n\n"
    "Vou seguir com o texto que já li — toque em *Corrigir agora*, "
    "*Editar texto* para ajustar a leitura, ou *Refazer foto* para começar "
    "as fotos de novo."
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
    "• Se sim, toque em *Corrigir agora*.\n"
    "• Se ainda tem ajuste, toque em *Editar texto* de novo."
)

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

CONFIRMING_REMINDER = (
    "Sua redação está pronta para correção. 👇 Escolha uma opção nos botões "
    "acima, ou mande /cancelar para recomeçar."
)

# ── Correção ────────────────────────────────────────────────────────────────

CORRECTING = (
    "Tudo pronto! 🧑‍🏫 Estou corrigindo sua redação nas 5 competências do "
    "ENEM — isso leva um minutinho..."
)

CORRECTION_FOOTER = (
    "\n\n─────────────\n"
    "_🤖 Correção automática por IA. A nota é uma estimativa: no ENEM oficial, "
    "sua redação é avaliada por dois corretores humanos._\n"
    "_Quer corrigir outra redação (ou uma nova versão desta)? É só tocar no "
    "botão ou mandar /corrigir._"
)

CORRECTION_FAILED = (
    "Tive um problema técnico na hora de corrigir. 😔 Sua redação não foi "
    "perdida — espera um instante e toca em *Corrigir agora* de novo."
)

RATE_LIMITED = (
    "Você já usou as suas {limit} correções de hoje. ⏳\n\n"
    "O limite diário existe para o corretor ficar disponível para toda a "
    "escola. Amanhã você pode mandar de novo — aproveita para revisar o "
    "feedback que já recebeu! 💪"
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
