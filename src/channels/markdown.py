"""Adapta markdown estilo-CommonMark (o que o LLM emite) para o dialeto do
WhatsApp — sem quebrar a copy que JÁ usa markdown do WhatsApp.

Por que existe: o gerador (LLM) emite CommonMark — `**negrito**`, `*itálico*`,
títulos `#`, tabelas `| a | b |`. O WhatsApp usa outro dialeto: `*negrito*`,
`_itálico_`, e NÃO renderiza títulos nem tabelas. Sem adaptação, `**x**` chega
com asteriscos sobrando, `#`/`##` aparecem crus e tabelas viram um borrão de
barras (confirmado em teste de fumaça).

O que fazemos:
  - `**b**`/`__b__` → `*b*` (negrito do WA);
  - títulos `#..######` → linha em negrito;
  - links `[t](u)` → `t (u)` (o WA não renderiza link markdown, mas auto-linka
    URLs cruas);
  - tabelas → bloco monospace ``` com colunas alinhadas por padding (o WA usa
    fonte de largura fixa em ```, então as colunas batem — fica copiável).

Regra de ouro (segurança): NÃO tocamos em `*x*`/`_x_` simples nem em código
`` `x` ``. No WhatsApp `*x*`=negrito e `_x_`=itálico — a MESMA sintaxe da copy do
projeto (messages.py) e do Telegram legacy; mexer neles quebraria mensagens já
corretas. Função pura e idempotente.
"""

import re

# Negrito CommonMark (** ou __) → negrito do WhatsApp (*). DOTALL para abranger
# trechos com quebra de linha; não-guloso para não engolir o resto da mensagem.
_BOLD_DOUBLE_STAR = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_DOUBLE_USCORE = re.compile(r"__(.+?)__", re.DOTALL)

# Título de linha (#..######) → linha em negrito do WhatsApp.
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# Link markdown [texto](url) → "texto (url)".
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

# Linha separadora de tabela (|---|:--:|---|): só barras, hífens, dois-pontos.
# Casada por linha (já com .strip()), por isso sem MULTILINE.
_SEP_LINE = re.compile(r"^\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?$")

_EXTRA_BLANKS = re.compile(r"\n{3,}")


def to_whatsapp_markdown(text: str) -> str:
    """Converte markdown CommonMark do LLM para o dialeto do WhatsApp.

    Seguro para texto que já está no dialeto WA (idempotente). Só toca no que o
    WhatsApp renderiza errado; `*x*`/`_x_` simples e código `` `x` `` ficam como
    estão.
    """
    if not text:
        return text

    text = _MD_LINK.sub(r"\1 (\2)", text)
    text = _BOLD_DOUBLE_STAR.sub(r"*\1*", text)
    text = _BOLD_DOUBLE_USCORE.sub(r"*\1*", text)
    text = _HEADING.sub(r"*\1*", text)
    text = _tables_to_monospace(text)
    text = _EXTRA_BLANKS.sub("\n\n", text)
    return text


def _split_row(line: str) -> list[str]:
    """Quebra uma linha de tabela em células, descartando as barras das bordas."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_monospace_table(header: list[str], rows: list[list[str]]) -> str:
    """Renderiza a tabela como bloco ``` com colunas alinhadas (ljust por largura
    da coluna). O WhatsApp mostra ``` em fonte fixa, então as colunas batem."""
    ncols = len(header)
    norm = [header] + [(r + [""] * ncols)[:ncols] for r in rows]
    widths = [max(len(row[c]) for row in norm) for c in range(ncols)]
    lines = [
        " | ".join(cell.ljust(widths[c]) for c, cell in enumerate(row)).rstrip()
        for row in norm
    ]
    return "```\n" + "\n".join(lines) + "\n```"


def _tables_to_monospace(text: str) -> str:
    """Acha blocos de tabela markdown (cabeçalho + separador + linhas) e os troca
    por um bloco monospace alinhado. Linhas com `|` que NÃO formam tabela (sem o
    separador na 2ª linha) ficam intactas."""
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if i + 1 < n and "|" in lines[i] and _SEP_LINE.match(lines[i + 1].strip()):
            header = _split_row(lines[i])
            j = i + 2
            rows: list[list[str]] = []
            while j < n and "|" in lines[j] and not _SEP_LINE.match(lines[j].strip()):
                rows.append(_split_row(lines[j]))
                j += 1
            out.append(_render_monospace_table(header, rows))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
