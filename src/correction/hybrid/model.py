"""Previsão da nota pelo modelo treinado (ExtraTrees + meta-features TF-IDF + calibração match_sd).

Mesma sequência do laboratório (`fit_raw` + `calibrate` em `_local/scripts/jev_v4_context.py`): previsão
contínua por competência (pontos/40) e do total, calibração afim `a + b·x` ajustada fora da amostra, e
reconciliação inteira com soma exata (`scoring.reconcile_qp`).
"""

import math

from src.correction.hybrid import artifacts
from src.correction.hybrid.scoring import reconcile_qp


def predict_levels(feats: dict[str, float], redacao: str) -> list[int]:
    """→ níveis 0..5 de C1..C5 (nota = nível × 40), com C1+…+C5 = total previsto."""
    import numpy as np  # tardio: só o modo híbrido precisa

    m = artifacts.model()
    x = [float(feats.get(c, math.nan)) for c in m["cols"]]
    xt = m["tfidf_vectorizer"].transform([redacao])
    tf = [float(r.predict(xt)[0]) for r in m["tfidf_ridges"]]
    row = np.array([x + tf], dtype=float)
    c_hat = [
        a + b * (float(est.predict(row)[0]) / 40.0) for (a, b), est in zip(m["cal_comps"], m["et_comps"])
    ]
    a, b = m["cal_total"]
    total_lvl = round(a + b * (float(m["et_total"].predict(row)[0]) / 40.0))
    return reconcile_qp(c_hat, min(25, max(0, total_lvl)))
