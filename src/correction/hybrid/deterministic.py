"""Features determinísticas da redação (Python puro): tamanho, pontuação, conectivos, repetição, parágrafos.

Cópia fiel de `_local/scripts/feature_deterministic.py` (laboratório), que gerou as colunas `det_*` usadas no
treino do modelo do fluxo híbrido. NÃO altere a lógica sem retreinar o modelo
(`_local/scripts/jev_v4_export.py`): qualquer diferença aqui vira diferença de feature entre treino e produção.
"""

import re
import statistics
import unicodedata

# Conectivos e operadores argumentativos comuns em redação do Enem, agrupados por
# relação lógica. Lista fechada de propósito: o valor da feature é ser
# reproduzível, não exaustiva. Multi-palavra vem antes na busca por ser mais
# específico (ex.: "no entanto" não deve casar só como "no").
CONECTIVOS = {
    "adicao": [
        "além disso",
        "ademais",
        "outrossim",
        "não obstante isso",
        "bem como",
        "também",
        "igualmente",
        "inclusive",
    ],
    "oposicao": [
        "contudo",
        "entretanto",
        "todavia",
        "no entanto",
        "porém",
        "mas",
        "apesar de",
        "embora",
        "ainda que",
        "por outro lado",
        "em contrapartida",
        "conquanto",
    ],
    "causa": [
        "porque",
        "uma vez que",
        "visto que",
        "já que",
        "dado que",
        "posto que",
        "pois",
        "por conta de",
        "em virtude de",
        "devido a",
    ],
    "consequencia": [
        "portanto",
        "logo",
        "por conseguinte",
        "assim",
        "dessa forma",
        "desse modo",
        "de modo que",
        "por isso",
        "consequentemente",
        "então",
    ],
    "conformidade": [
        "conforme",
        "segundo",
        "de acordo com",
        "consoante",
        "assim como",
        "nesse sentido",
        "sob tal ótica",
        "nessa lógica",
    ],
    "finalidade": ["a fim de", "para que", "com o intuito de", "com o objetivo de", "com a finalidade de"],
    "conclusao": [
        "em suma",
        "portanto",
        "enfim",
        "em síntese",
        "dessa maneira",
        "diante disso",
        "por fim",
        "concluindo",
    ],
    "exemplificacao": ["por exemplo", "a exemplo de", "como é o caso de", "isto é", "ou seja"],
    "tempo": [
        "atualmente",
        "hodiernamente",
        "outrora",
        "posteriormente",
        "primeiramente",
        "em primeira análise",
        "em segunda análise",
    ],
}
TODOS_CONECTIVOS = sorted({c for v in CONECTIVOS.values() for c in v}, key=len, reverse=True)

# Palavras funcionais — excluídas da checagem de repetição, senão "de"/"que"
# dominariam a contagem e a feature não mediria nada.
STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "pelo",
    "pela",
    "para",
    "com",
    "sem",
    "sob",
    "sobre",
    "entre",
    "e",
    "ou",
    "mas",
    "que",
    "se",
    "ao",
    "aos",
    "à",
    "às",
    "é",
    "ser",
    "sao",
    "são",
    "foi",
    "era",
    "seu",
    "sua",
    "seus",
    "suas",
    "este",
    "esta",
    "esse",
    "essa",
    "isso",
    "aquele",
    "aquela",
    "não",
    "mais",
    "muito",
    "como",
    "quando",
    "onde",
    "já",
    "também",
    "há",
    "ter",
    "tem",
    "the",
    "seja",
    "pode",
    "ainda",
    "dessa",
    "desse",
    "nesse",
    "nessa",
    "qual",
    "sendo",
}

PALAVRA_RE = re.compile(r"[a-záàâãéêíóôõúüç]+", re.I)


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _periodos(texto: str) -> list[str]:
    """Quebra em períodos por pontuação final. Aproximação — abreviação com
    ponto conta como fim de período. Aceitável: é uma feature de superfície e o
    erro é o mesmo em todas as redações."""
    return [p.strip() for p in re.split(r"[.!?]+", texto) if p.strip()]


def extrai(texto: str) -> dict[str, float]:
    paragrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    periodos = _periodos(texto)
    palavras = PALAVRA_RE.findall(texto)
    baixo = [p.lower() for p in palavras]
    conteudo = [p for p in baixo if p not in STOPWORDS and len(p) > 3]
    por_periodo = [len(PALAVRA_RE.findall(p)) for p in periodos] or [0]
    por_paragrafo = [len(PALAVRA_RE.findall(p)) for p in paragrafos] or [0]

    texto_norm = _sem_acento(texto)
    achados, restante = [], texto_norm
    for c in TODOS_CONECTIVOS:
        alvo = _sem_acento(c)
        n = len(re.findall(r"\b" + re.escape(alvo) + r"\b", restante))
        if n:
            achados += [c] * n
            restante = re.sub(r"\b" + re.escape(alvo) + r"\b", " ", restante)

    inicios = 0
    for p in paragrafos:
        cabeca = _sem_acento(" ".join(PALAVRA_RE.findall(p)[:4]))
        if any(re.match(r"\b" + re.escape(_sem_acento(c)) + r"\b", cabeca) for c in TODOS_CONECTIVOS):
            inicios += 1

    # Repetição dentro de janela: mesma palavra de conteúdo reaparecendo perto.
    # É o defeito que o §8.2 nomeia, contado de forma reproduzível.
    rep_50 = sum(1 for i, w in enumerate(conteudo) if w in conteudo[max(0, i - 50) : i])
    rep_20 = sum(1 for i, w in enumerate(conteudo) if w in conteudo[max(0, i - 20) : i])

    # Repetição INTRA-PARÁGRAFO. A janela fixa acima deu ρ parcial -0,076 contra
    # C4 (medido em 2026-08-05): ela atravessa fronteira de parágrafo, e repetir
    # o termo-chave ao abrir um parágrafo novo é retomada legítima, não defeito.
    rep_intra = 0
    for p in paragrafos:
        pal_p = [w.lower() for w in PALAVRA_RE.findall(p)]
        cont_p = [w for w in pal_p if w not in STOPWORDS and len(w) > 3]
        rep_intra += sum(1 for i, w in enumerate(cont_p) if w in cont_p[max(0, i - 30) : i])

    # Parágrafo frasal e monobloco: a matriz nomeia os dois (§5.1 e §8.2) e ambos
    # são contáveis. Estavam no codebook do LLM sem motivo — aqui saem de graça
    # e com ρ = 1,0.
    frasais = sum(1 for p in paragrafos if len(_periodos(p)) <= 1)

    return {
        "det_n_palavras": len(palavras),
        "det_n_paragrafos": len(paragrafos),
        "det_n_periodos": len(periodos),
        "det_palavras_por_periodo_media": round(statistics.fmean(por_periodo), 2),
        "det_palavras_por_periodo_desvio": round(statistics.pstdev(por_periodo), 2)
        if len(por_periodo) > 1
        else 0.0,
        "det_periodo_mais_longo": max(por_periodo),
        "det_paragrafo_menor": min(por_paragrafo),
        "det_paragrafo_maior": max(por_paragrafo),
        "det_n_virgulas": texto.count(","),
        "det_n_ponto_e_virgula": texto.count(";"),
        "det_n_dois_pontos": texto.count(":"),
        "det_n_aspas": texto.count('"') + texto.count("“") + texto.count("”"),
        "det_conectivos_total": len(achados),
        "det_conectivos_distintos": len(set(achados)),
        "det_conectivos_relacoes_distintas": len(
            {r for r, lst in CONECTIVOS.items() if any(c in achados for c in lst)}
        ),
        "det_type_token_ratio": round(len(set(baixo)) / len(baixo), 4) if baixo else 0.0,
        # `det_palavras_distintas` saiu: ρ +0,955 com `det_n_palavras` (medido em
        # 400 redações). Mesma informação, coluna a mais.
        # `det_paragrafos_com_operador_inicial` saiu em favor da proporção abaixo:
        # ρ +0,971 entre as duas, e a proporção resiste melhor ao controle por
        # tamanho (ρ parcial +0,359 contra +0,277 da contagem).
        "det_repeticao_janela_20": rep_20,
        "det_repeticao_janela_50": rep_50,
        "det_repeticao_intra_paragrafo": rep_intra,
        "det_tamanho_medio_palavra": round(statistics.fmean(len(p) for p in palavras), 2)
        if palavras
        else 0.0,
        "det_prop_palavras_longas": round(sum(1 for p in palavras if len(p) >= 10) / len(palavras), 4)
        if palavras
        else 0.0,
        # --- Estrutura de parágrafo (§5.1, §8.2) ---
        "det_paragrafos_frasais": frasais,
        "det_monobloco": 1 if len(paragrafos) <= 1 else 0,
        "det_periodos_por_paragrafo": round(len(periodos) / len(paragrafos), 2) if paragrafos else 0.0,
        # --- Normalizadas por tamanho ---
        # Medido em 2026-08-05: no bruto, quase toda feature vira proxy de
        # comprimento (palavras_distintas cai de ρ +0,455 para +0,114 em C4 quando
        # se controla o tamanho). Dar a razão pronta evita que um modelo linear
        # precise inventá-la — gradient boosting acharia sozinho, linear não.
        "det_conectivos_por_100": round(100 * len(achados) / len(palavras), 3) if palavras else 0.0,
        "det_conectivos_diversidade": round(len(set(achados)) / len(achados), 4) if achados else 0.0,
        "det_prop_paragrafos_com_operador": round(inicios / len(paragrafos), 4) if paragrafos else 0.0,
        "det_repeticao_intra_por_100": round(100 * rep_intra / len(palavras), 3) if palavras else 0.0,
    }
