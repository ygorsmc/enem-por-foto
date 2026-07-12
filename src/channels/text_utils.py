"""Chunking de texto longo em mensagens seguras — compartilhado entre canais.

Por que existe: WhatsApp e Telegram têm o mesmo teto prático (~4096 chars) por
mensagem de texto, mas reagem diferente ao estourar: o Telegram REJEITA com 400
("message is too long"), o WhatsApp aceita mas o cliente trunca de forma
imprevisível. Por isso nenhum canal pode confiar em mandar texto arbitrário
num `send_text` só — o texto é dividido em pedaços que cabem, preferindo
cortar em parágrafo > linha > espaço (nunca no meio de uma palavra se der
para evitar).
"""


def chunk_text(text: str, max_length: int) -> list[str]:
    """Divide `text` em pedaços de até `max_length` caracteres cada."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        split_idx = text.rfind("\n\n", 0, max_length)
        if split_idx == -1:
            split_idx = text.rfind("\n", 0, max_length)
            if split_idx == -1:
                split_idx = text.rfind(" ", 0, max_length)
                if split_idx == -1:
                    split_idx = max_length

        chunks.append(text[:split_idx].strip())
        text = text[split_idx:].strip()

    return chunks
