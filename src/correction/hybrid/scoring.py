"""Regras puras do fluxo híbrido (sem numpy, sem I/O): reconciliação das notas, portão de nota zero e checklist.

Portadas do laboratório e calibradas lá (ver `_local/RELATORIO_JEV.md`, §2.4–2.6):
  - `reconcile_qp`: `_local/scripts/jev_reconcile_lab.py` (projeção inteira exata, soma C1..C5 = total);
  - portão: `_local/scripts/jev_v4_gate.py` (regras da Cartilha do INEP; impropério e carta zeram por decisão do
    dono);
  - checklist: `_local/scripts/jev_v4_feedback_filtro.py` (corte p95 das boas + filtro estrito).
"""

COMPS = ["C1", "C2", "C3", "C4", "C5"]
MIN_PALAVRAS = 70  # proxy de "até 7 linhas"; em produção o ideal é contar as linhas da folha no OCR
MAX_PISTAS_POR_COMP = 2
C5_ELEMENTOS = {
    "c5_agente_presente": "agente",
    "c5_acao": "ação",
    "c5_modo_meio": "modo/meio",
    "c5_efeito": "efeito",
    "c5_detalhamento": "detalhamento",
}


# ── Notas ────────────────────────────────────────────────────────────────────


def reconcile_qp(c_hat: list[float], total_lvl: int) -> list[int]:
    """Níveis inteiros 0..5 mais próximos de `c_hat` (mínimos quadrados) com soma exata `total_lvl` (0..25).

    Como (k − c)² é convexa e separável, começar no arredondamento e dar passos unitários de menor custo é
    exato no ótimo global.
    """
    out = [min(5, max(0, round(c))) for c in c_hat]
    t = min(25, max(0, int(total_lvl)))
    while sum(out) < t:
        cands = [(2.0 * (out[j] - c_hat[j]) + 1.0, j) for j in range(5) if out[j] < 5]
        if not cands:
            break
        out[min(cands)[1]] += 1
    while sum(out) > t:
        cands = [(2.0 * (c_hat[j] - out[j]) + 1.0, j) for j in range(5) if out[j] > 0]
        if not cands:
            break
        out[min(cands)[1]] -= 1
    return out


# ── Portão de nota zero ──────────────────────────────────────────────────────


def _choice(a: dict) -> tuple[str, float]:
    c = a["triagem_tipo_textual"]
    return c["choice"], float(c["probabilities"][c["choice"]])


# (motivo mostrado ao LLM, condição) — ordem = prioridade quando mais de uma dispara
ZERO_RULES = [
    ("Fuga total ao tema", lambda a, w: a["tema_assunto_ref"] < 0.5),
    (
        "Não atende ao tipo dissertativo-argumentativo",
        lambda a, w: a["c2_tipo_dissertativo_argumentativo"] < 0.5,
    ),
    ("Texto não está em prosa (versos, lista ou tópicos)", lambda a, w: a["triagem_prosa"] < 0.5),
    (
        "Texto em formato narrativo, de poema ou de lista",
        lambda a, w: _choice(a)[0] in ("narrativo", "poema", "lista") and _choice(a)[1] >= 0.5,
    ),
    ("Formato de carta", lambda a, w: _choice(a)[0] == "carta" and _choice(a)[1] >= 0.5),
    ("Parte deliberadamente desconectada do tema", lambda a, w: a["triagem_trechos_relacionados"] < 0.3),
    ("Identificação do autor no texto", lambda a, w: a["triagem_identificacao_v3"] >= 0.7),
    ("Impropério (xingamento ou palavrão)", lambda a, w: a["triagem_improperio"] >= 0.9),
    ("Texto em língua estrangeira", lambda a, w: a["triagem_lingua_estrangeira"] >= 0.5),
    (f"Texto insuficiente (menos de {MIN_PALAVRAS} palavras)", lambda a, w: w < MIN_PALAVRAS),
]

# Não zeram: viram aviso para o LLM (ou C5 = 0, no caso de direitos humanos)
WARNING_RULES = [
    (
        "Trechos possivelmente ilegíveis (pode ser erro de leitura da foto)",
        lambda a: a["triagem_ininteligivel"] >= 0.5,
    ),
    (
        "Tangenciamento: trata do assunto, mas não do recorte do tema",
        lambda a: a["tema_assunto_ref"] >= 0.5 and a["tema_e_emb"] < 0.5,
    ),
    ("Sem tese explícita", lambda a: a["c2_tese_explicita"] < 0.5),
    ("Sem proposta de intervenção", lambda a: a["c5_tem_proposta"] < 0.3),
]
DH_WARNING = "Desrespeito aos direitos humanos na proposta (C5 = 0)"


def evaluate_gate(answers: dict, n_words: int) -> tuple[str | None, list[str], bool]:
    """→ (motivo de zero ou None, avisos, desrespeito aos direitos humanos)."""
    zero = next((motivo for motivo, fn in ZERO_RULES if fn(answers, n_words)), None)
    avisos = [msg for msg, fn in WARNING_RULES if fn(answers)]
    dh = answers["c5_viola_direitos_humanos"] >= 0.5
    if dh:
        avisos.append(DH_WARNING)
    return zero, avisos, dh


# ── Checklist e pistas para o LLM ────────────────────────────────────────────


def checklist_hits(answers: dict, levels: list[int], items: dict) -> dict[str, list[str]]:
    """Até 2 pistas por competência, pela maior margem; nenhuma onde a nota prevista é ≥ 160 (filtro estrito)."""
    margens = []
    for q, it in items.items():
        m = (-it["sign"] * float(answers[q])) - it["thr"]
        if m > 0:
            margens.append((m, q))
    out: dict[str, list[str]] = {c: [] for c in COMPS}
    for _, q in sorted(margens, reverse=True):
        comp = items[q]["comp"]
        if levels[COMPS.index(comp)] <= 3 and len(out[comp]) < MAX_PISTAS_POR_COMP:
            out[comp].append(items[q]["msg"])
    return out


def _leitura(p: float) -> str:
    return "provavelmente presente" if p >= 0.7 else ("provavelmente ausente" if p <= 0.3 else "duvidoso")


def pistas_text(hits: dict[str, list[str]], answers: dict, avisos: list[str]) -> str:
    linhas = [f"{c}: " + (" | ".join(hits[c]) if hits[c] else "sem pistas.") for c in COMPS]
    linhas.append(
        "Elementos da proposta (C5), leitura automática: "
        + "; ".join(f"{nome}: {_leitura(float(answers[q]))}" for q, nome in C5_ELEMENTOS.items())
        + "."
    )
    linhas.append("Avisos: " + ("; ".join(avisos) if avisos else "nenhum."))
    return "\n".join(linhas)
