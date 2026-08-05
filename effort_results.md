# CORRECTION_EFFORT do DeepSeek V4 Flash 0731 — comparação pareada

Amostra held-out seed 7, **as mesmas 29 redações em todos os níveis**. Só o `reasoning_effort` muda: mesmo prompt de produção, mesmo modelo, mesma amostra.

> A comparação de effort que estava na documentação (`max` vs `high`) foi medida na versão **anterior** do modelo e nunca refeita. Esta substitui aquela.

## Agregado

| Effort | MAE | Viés | RMSE | QWK médio | QWK total | Spearman | Slope |
|---|---|---|---|---|---|---|---|
| `low` | 146.2 | -49.7 | 165.1 | 0.351 | 0.547 | 0.638 | 0.45 |
| `medium` | 137.9 | -29.0 | 163.7 | 0.346 | 0.546 | 0.655 | 0.47 |
| `high` | 144.1 | -14.5 | 165.5 | 0.297 | 0.505 | 0.608 | 0.39 |
| `max` **(produção)** | 142.1 | -29.0 | 164.9 | 0.345 | 0.546 | 0.676 | 0.45 |

## Pareado contra `max` (teste de sinal)

| Effort | Vitórias | Derrotas | Empates | p | Δ MAE |
|---|---|---|---|---|---|
| `low` | 10 | 14 | 5 | 0.541 | +4.1 |
| `medium` | 15 | 9 | 5 | 0.307 | -4.1 |
| `high` | 12 | 10 | 7 | 0.832 | +2.1 |

## Viés por faixa de nota real

| Effort | Baixa (≤440) | Média (480–680) | Alta (≥720) |
|---|---|---|---|
| `low` | +91.4 (n=7) | -28.0 (n=10) | -150.0 (n=12) |
| `medium` | +117.1 (n=7) | -36.0 (n=10) | -108.3 (n=12) |
| `high` | +165.7 (n=7) | -16.0 (n=10) | -118.3 (n=12) |
| `max` | +91.4 (n=7) | -4.0 (n=10) | -120.0 (n=12) |

## Conformidade de formato

Os dois defeitos achados em 2026-08-04. Se o raciocínio mais curto degradar o formato, aparece aqui — é custo escondido que o MAE não mostra.

| Effort | Respostas com 2 blocos de nota | Competências fora da escala de 40 |
|---|---|---|
| `low` | 0 | 2/145 (1%) |
| `medium` | 0 | 4/150 (3%) |
| `high` | 0 | 1/150 (1%) |
| `max` | 1 | 4/150 (3%) |

## Por competência (MAE em pontos)

| Effort | C1 | C2 | C3 | C4 | C5 |
|---|---|---|---|---|---|
| `low` | 49.7 | 24.8 | 35.9 | 40.0 | 41.4 |
| `medium` | 42.8 | 30.3 | 34.5 | 41.4 | 48.3 |
| `high` | 44.1 | 27.6 | 37.2 | 42.8 | 46.9 |
| `max` | 44.1 | 30.3 | 37.2 | 42.8 | 42.8 |
