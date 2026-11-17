"""Features do modelo do fluxo híbrido a partir do texto e das respostas do Jev (Python puro).

Porte de `extract_engineered` (`_local/scripts/jev_strategies_lab.py`) e de `jev_features`
(`_local/scripts/jev_v4_full.py`) — os mesmos nomes de coluna usados no treino. NÃO altere a lógica sem retreinar
o modelo (`_local/scripts/jev_v4_export.py`).

O texto do OCR chega como tabela markdown com número de linha (`|  1 | texto  |`), hifenização no fim da linha
e sem marca de parágrafo. `normalize_ocr_text` reconstrói o texto corrido SÓ para o modelo e para o Jev — o
preview do aluno continua sendo a transcrição fiel (invariante 5 do AGENTS.md).
"""

import math
import re
import statistics

from src.correction.hybrid.deterministic import CONECTIVOS, STOPWORDS, _periodos, _sem_acento, extrai

PALAVRA_RE = re.compile(r"[a-záàâãéêíóôõúüç]+", re.I)
MISS_SPACE_RE = re.compile(r"[,.;:!?][A-Za-zÀ-ú]")
LOWER_DOT_RE = re.compile(r"\.\s+[a-zà-ú]")
FIRST_PERSON = {
    "eu",
    "meu",
    "minha",
    "meus",
    "minhas",
    "comigo",
    "acho",
    "penso",
    "acredito",
    "concordo",
    "discordo",
}
CONC_OPS = sorted(
    {_sem_acento(c) for grp in ("conclusao", "consequencia", "oposicao") for c in CONECTIVOS[grp]},
    key=len,
    reverse=True,
)
ALL_OPS = sorted({_sem_acento(c) for lst in CONECTIVOS.values() for c in lst}, key=len, reverse=True)

_LINHA_TABELA = re.compile(r"^\s*\|\s*\d+\s*\|(.*)\|\s*$")
_SEPARADOR_TABELA = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
# Linha que fecha parágrafo: termina em pontuação final e é bem mais curta que a linha típica da folha.
_FRACAO_LINHA_CURTA = 0.8


# ── Texto ────────────────────────────────────────────────────────────────────


def normalize_ocr_text(texto: str) -> str:
    """Tabela do OCR → texto corrido com parágrafos (`\\n`). Texto que não é tabela só tem espaços normalizados."""
    linhas = []
    tabela = False
    for bruta in texto.splitlines():
        m = _LINHA_TABELA.match(bruta)
        if m:
            tabela = True
            linhas.append(m.group(1).strip())
        elif _SEPARADOR_TABELA.match(bruta):
            continue
        elif not tabela:
            linhas.append(bruta.strip())
    if not tabela:
        paras = [re.sub(r"[ \t]+", " ", p).strip() for p in "\n".join(linhas).split("\n")]
        return "\n".join(p for p in paras if p)

    linhas = [ln for ln in linhas if ln]
    if not linhas:
        return ""
    tipico = statistics.median(len(ln) for ln in linhas)
    paragrafos: list[str] = []
    atual = ""
    for i, ln in enumerate(linhas):
        if atual.endswith("-"):  # hifenização: "po-" + "vos" → "povos"
            atual = atual[:-1] + ln
        else:
            atual = f"{atual} {ln}".strip()
        ultima = i == len(linhas) - 1
        fecha = ln.endswith((".", "!", "?", ":")) and len(ln) < _FRACAO_LINHA_CURTA * tipico
        if fecha or ultima:
            paragrafos.append(re.sub(r"\s+", " ", atual).strip())
            atual = ""
    return "\n".join(p for p in paragrafos if p)


def word_count(texto: str) -> int:
    return len(texto.split())


# ── Respostas do Jev ─────────────────────────────────────────────────────────


def jev_features(answers: dict) -> dict[str, float]:
    """Respostas cruas → colunas `jev_*` (Choice vira uma coluna `jev_tipo_<opção>` por opção)."""
    out: dict[str, float] = {}
    for k, v in answers.items():
        if isinstance(v, dict):
            for opt, p in v["probabilities"].items():
                out[f"jev_tipo_{opt}"] = float(p)
        else:
            out[f"jev_{k}"] = float(v)
    # Nome antigo que o JEV_DOM usa (a pergunta foi renomeada na v3) — ver `with_alias` no laboratório.
    out.setdefault("jev_c2_repertorio_externo", out.get("jev_c2_repertorio_presente", 0.0))
    return out


# ── Features de estrutura, tema e combinações do Jev ─────────────────────────


def _tokens(texto: str) -> list[str]:
    return PALAVRA_RE.findall(_sem_acento(texto))


def _content_stems(tokens: list[str]) -> list[str]:
    return [t[:5] for t in tokens if t not in STOPWORDS and len(t) > 3]


def _starts_with_op(para: str, ops: list[str]) -> float:
    head = " ".join(_tokens(para)[:4])
    return 1.0 if any(re.match(r"\b" + re.escape(op) + r"\b", head) for op in ops) else 0.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _pstd(xs: list[float]) -> float:
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def engineered(tema: str, redacao: str, det: dict[str, float], jv: dict[str, float]) -> dict[str, float]:
    """PROMPT_STRUCT (sem motivadores) + JEV_DOM, com os mesmos nomes do treino."""
    words = max(det.get("det_n_palavras", 0.0), 1.0)
    periods = max(det.get("det_n_periodos", 0.0), 1.0)
    tema_stems = list(dict.fromkeys(_content_stems(_tokens(tema))))
    essay_toks = _tokens(redacao)
    paras = [p.strip() for p in redacao.split("\n") if p.strip()] or [redacao]

    def stem_cov(bloco: str) -> float:
        if not tema_stems:
            return 0.0
        st_set = set(_content_stems(_tokens(bloco)))
        return sum(1 for ts in tema_stems if ts in st_set) / len(tema_stems)

    essay_content = _content_stems(essay_toks)
    para_w = [len(_tokens(p)) for p in paras]
    body_w = para_w[1:-1] if len(para_w) > 2 else para_w
    body_ops = [_starts_with_op(p, ALL_OPS) for p in paras[1:-1]]
    per_lens = [len(_tokens(p)) for p in _periodos(redacao)] or [0]
    uniq_cnt: dict[str, int] = {}
    for s in essay_content:
        uniq_cnt[s] = uniq_cnt.get(s, 0) + 1
    hapax = sum(1 for v in uniq_cnt.values() if v == 1) / max(len(essay_content), 1)
    fp_count = sum(1 for t in essay_toks if t in FIRST_PERSON)

    feats = {
        "eng_tema_cov_all": stem_cov(redacao),
        "eng_tema_cov_intro": stem_cov(paras[0]),
        "eng_tema_cov_conc": stem_cov(paras[-1]),
        "eng_intro_words": float(para_w[0]),
        "eng_conc_words": float(para_w[-1]),
        "eng_body_words_mean": float(_mean(body_w)),
        "eng_para_balance": float(min(para_w)) / max(max(para_w), 1),
        "eng_para_cv": float(_pstd(para_w)) / max(float(_mean(para_w)), 1.0),
        "eng_conc_has_op": _starts_with_op(paras[-1], CONC_OPS),
        "eng_body_op_rate": float(_mean(body_ops)) if body_ops else 0.0,
        "eng_runon_rate": sum(1 for x in per_lens if x > 40) / len(per_lens),
        "eng_frag_rate": sum(1 for x in per_lens if x <= 5) / len(per_lens),
        "eng_miss_space_100": len(MISS_SPACE_RE.findall(redacao)) / words * 100.0,
        "eng_lower_dot_rate": len(LOWER_DOT_RE.findall(redacao)) / periods,
        "eng_first_person_100": fp_count / words * 100.0,
        "eng_hapax_ratio": hapax,
    }

    sc = [jv[f"jev_score_c{i}"] for i in range(1, 6)]
    rec = jv["jev_c2_aborda_recorte_completo"]
    c2_gate = rec * (1.0 - jv["jev_triagem_fuga_total"]) * jv["jev_c2_tipo_dissertativo_argumentativo"]
    ag, ac, md, ef = (jv[f"jev_c5_{k}"] for k in ("agente_especifico", "acao", "modo_meio", "efeito"))
    noul_vals = [v for k, v in jv.items() if k.startswith("jev_") and 0.0 <= v <= 1.0 and "score_" not in k]
    feats.update(
        {
            "eng_jev_mean": float(_mean(sc)),
            "eng_jev_min": float(min(sc)),
            "eng_jev_std": float(_pstd(sc)),
            "eng_jev_unc": float(_mean([4.0 * p * (1.0 - p) for p in noul_vals])),
            "eng_jev_c2_gate": c2_gate,
            "eng_jev_sc2_gated": jv["jev_score_c2"] * rec,
            "eng_jev_sc3_gated": jv["jev_score_c3"] * rec,
            "eng_jev_sc5_gated": jv["jev_score_c5"] * rec,
            "eng_jev_c5_soft": jv["jev_c5_tem_proposta"]
            * (ag + ac + md + ef + (ag * ac * md * ef) * jv["jev_c5_detalhamento"]),
            "eng_jev_c2_rep_chain": jv["jev_c2_repertorio_externo"]
            + jv["jev_c2_repertorio_legitimado"]
            + jv["jev_c2_repertorio_produtivo"],
        }
    )
    return feats


def all_features(tema: str, redacao: str, answers: dict) -> dict[str, float]:
    """Todas as colunas que o modelo pode pedir (o artefato define quais e em que ordem)."""
    det = {k: float(v) for k, v in extrai(redacao).items()}
    jv = jev_features(answers)
    return {**det, **jv, **engineered(tema, redacao, det, jv)}
