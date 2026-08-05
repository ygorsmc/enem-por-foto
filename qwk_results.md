# QWK — Quadratic Weighted Kappa contra o Essay-BR

Métrica padrão da literatura de Automatic Essay Scoring (herdada da competição ASAP e usada nos papers do próprio Essay-BR). Calculada **offline** sobre as respostas já salvas em disco pelas corridas de avaliação — nenhuma chamada de API nova, então os números se referem exatamente às mesmas execuções que produziram os MAEs já publicados.

Escala: cada competência do ENEM tem 6 níveis (0/40/80/120/160/200). QWK penaliza o erro pelo quadrado da distância entre níveis e desconta a concordância esperada por acaso. 1 = perfeito, 0 = nível do acaso.

IC de 95% por bootstrap percentil (10000 reamostragens das redações, seed 1).

> **Leia o intervalo de confiança antes do ponto estimado.** Com n=30 ele é largo — essa é justamente a evidência de que a amostra atual é piloto, não resultado fechado.

### DeepSeek versão antiga · seed 42

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.405** | [0.122, 0.619] | 38% | 86% | 30.3 | 40.68 |
| C2 | **0.621** | [0.346, 0.784] | 41% | 90% | 27.6 | 37.87 |
| C3 | **0.510** | [0.136, 0.726] | 34% | 79% | 35.9 | 48.14 |
| C4 | **0.519** | [0.281, 0.709] | 45% | 86% | 29.0 | 42.67 |
| C5 | **0.424** | [0.026, 0.702] | 31% | 69% | 45.5 | 61.70 |

- **QWK médio das 5 competências**: **0.496**
- QWK do total (0–1000 em 26 níveis): 0.663 — IC 95% [0.402, 0.797]
- **RMSE do total**: 162.40 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.613 · MAE do total: 132.4 · viés: -2.8
- n = 29 redações
- Descartes: 1 sem parse · 0 sem par no corpus · 0 notas de competência fora da escala de 40 (arredondadas)

### DeepSeek 0731 · seed 42

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.290** | [0.044, 0.504] | 31% | 79% | 35.9 | 45.79 |
| C2 | **0.482** | [0.202, 0.661] | 38% | 93% | 27.6 | 36.39 |
| C3 | **0.511** | [0.178, 0.708] | 38% | 83% | 31.7 | 42.67 |
| C4 | **0.585** | [0.425, 0.676] | 34% | 90% | 30.3 | 39.30 |
| C5 | **0.463** | [-0.038, 0.788] | 41% | 86% | 34.5 | 53.05 |

- **QWK médio das 5 competências**: **0.466**
- QWK do total (0–1000 em 26 níveis): 0.604 — IC 95% [0.377, 0.739]
- **RMSE do total**: 157.57 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.648 · MAE do total: 135.2 · viés: -13.8
- n = 29 redações
- Descartes: 1 sem parse · 0 sem par no corpus · 0 notas de competência fora da escala de 40 (arredondadas)

### DeepSeek 0731 · held-out seed 7

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.272** | [0.116, 0.424] | 10% | 80% | 44.0 | 48.99 |
| C2 | **0.316** | [0.005, 0.574] | 40% | 83% | 32.0 | 45.02 |
| C3 | **0.372** | [0.203, 0.545] | 33% | 77% | 37.3 | 49.53 |
| C4 | **0.343** | [0.136, 0.502] | 27% | 63% | 44.0 | 54.16 |
| C5 | **0.413** | [0.112, 0.648] | 30% | 70% | 44.0 | 57.97 |

- **QWK médio das 5 competências**: **0.343**
- QWK do total (0–1000 em 26 níveis): 0.527 — IC 95% [0.375, 0.653]
- **RMSE do total**: 172.36 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.661 · MAE do total: 148.0 · viés: -38.7
- n = 30 redações
- Descartes: 0 sem parse · 0 sem par no corpus · 4 notas de competência fora da escala de 40 (arredondadas)

### Gemini 3.5 Flash Lite · seed 42

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.466** | [0.195, 0.641] | 33% | 93% | 29.3 | 37.24 |
| C2 | **0.564** | [0.274, 0.732] | 40% | 93% | 26.7 | 35.78 |
| C3 | **0.435** | [0.200, 0.611] | 40% | 80% | 32.0 | 43.82 |
| C4 | **0.406** | [0.209, 0.563] | 20% | 67% | 46.7 | 56.10 |
| C5 | **0.340** | [0.149, 0.528] | 20% | 60% | 56.0 | 69.28 |

- **QWK médio das 5 competências**: **0.442**
- QWK do total (0–1000 em 26 níveis): 0.560 — IC 95% [0.369, 0.677]
- **RMSE do total**: 189.60 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.737 · MAE do total: 165.3 · viés: -125.3
- n = 30 redações
- Descartes: 0 sem parse · 0 sem par no corpus · 5 notas de competência fora da escala de 40 (arredondadas)

### Gemini 3.5 FL prompt base · held-out seed 7

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.315** | [0.123, 0.472] | 27% | 87% | 34.7 | 42.58 |
| C2 | **0.285** | [0.083, 0.464] | 23% | 87% | 37.3 | 46.19 |
| C3 | **0.296** | [0.012, 0.569] | 37% | 80% | 36.0 | 50.07 |
| C4 | **0.396** | [0.211, 0.558] | 20% | 67% | 48.0 | 58.42 |
| C5 | **0.365** | [0.181, 0.543] | 23% | 60% | 50.7 | 62.82 |

- **QWK médio das 5 competências**: **0.331**
- QWK do total (0–1000 em 26 níveis): 0.411 — IC 95% [0.247, 0.551]
- **RMSE do total**: 219.09 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.676 · MAE do total: 189.3 · viés: -157.3
- n = 30 redações
- Descartes: 0 sem parse · 0 sem par no corpus · 7 notas de competência fora da escala de 40 (arredondadas)

### Gemini 3.5 FL prompt variante · held-out seed 7

| Competência | QWK | IC 95% (bootstrap) | Exato | ±1 nível | MAE | RMSE |
|---|---|---|---|---|---|---|
| C1 | **0.227** | [0.056, 0.372] | 37% | 83% | 32.0 | 42.58 |
| C2 | **0.323** | [0.053, 0.599] | 47% | 90% | 26.7 | 40.00 |
| C3 | **0.496** | [0.241, 0.717] | 43% | 90% | 28.0 | 40.66 |
| C4 | **0.477** | [0.230, 0.694] | 40% | 77% | 36.0 | 51.12 |
| C5 | **0.554** | [0.298, 0.741] | 33% | 80% | 36.0 | 47.89 |

- **QWK médio das 5 competências**: **0.416**
- QWK do total (0–1000 em 26 níveis): 0.569 — IC 95% [0.392, 0.705]
- **RMSE do total**: 171.58 — a métrica comparável com a Tabela XII do paper do corpus
- Spearman do total: 0.736 · MAE do total: 144.0 · viés: -101.3
- n = 30 redações
- Descartes: 0 sem parse · 0 sem par no corpus · 9 notas de competência fora da escala de 40 (arredondadas)

---

## Âncora: baselines publicados sobre o MESMO corpus

Marinho, J. C.; Anchiêta, R. T.; Moura, R. S. **Essay-BR: a Brazilian Corpus to Automatic Essay Scoring Task**. *Journal of Information and Data Management*, v. 13, n. 1, 2022 — Tabelas XI (QWK) e XII (RMSE), medidas no split de teste oficial do corpus.

| Modelo | C1 | C2 | C3 | C4 | C5 | QWK total | RMSE total |
|---|---|---|---|---|---|---|---|
| Amorim & Veloso (2017), regressão linear sobre 19 features | 0.39 | 0.46 | 0.40 | 0.38 | 0.34 | 0.49 | 161.09 |
| Fonseca et al. (2018), gradient boosting sobre 681 features | 0.44 | 0.48 | 0.42 | 0.47 | 0.38 | 0.53 | 157.33 |
| | | | | | | | |
| _(este projeto)_ DeepSeek versão antiga · seed 42 | 0.40 | 0.62 | 0.51 | 0.52 | 0.42 | 0.66 | 162.40 |
| _(este projeto)_ DeepSeek 0731 · seed 42 | 0.29 | 0.48 | 0.51 | 0.58 | 0.46 | 0.60 | 157.57 |
| _(este projeto)_ DeepSeek 0731 · held-out seed 7 | 0.27 | 0.32 | 0.37 | 0.34 | 0.41 | 0.53 | 172.36 |
| _(este projeto)_ Gemini 3.5 Flash Lite · seed 42 | 0.47 | 0.56 | 0.43 | 0.41 | 0.34 | 0.56 | 189.60 |
| _(este projeto)_ Gemini 3.5 FL prompt base · held-out seed 7 | 0.31 | 0.28 | 0.30 | 0.40 | 0.36 | 0.41 | 219.09 |
| _(este projeto)_ Gemini 3.5 FL prompt variante · held-out seed 7 | 0.23 | 0.32 | 0.50 | 0.48 | 0.55 | 0.57 | 171.58 |

### O que essa comparação permite dizer — e o que não permite

**Não é a mesma avaliação.** Quatro diferenças que impedem ler a tabela como um ranking:

1. **Conjunto de teste diferente.** Os baselines usam o split de teste oficial do corpus (~10% de 6.579 redações). Nós usamos amostras aleatórias de 30 tiradas do corpus inteiro — que inclui o split de treino deles. Números na mesma escala, populações diferentes.
2. **n=30 contra ~650.** Os IC de 95% das seções acima têm largura de 0,3–0,8 de kappa. Nessa largura cabem os dois baselines inteiros. Nenhuma diferença aqui é estatisticamente distinguível de ruído amostral.
3. **Supervisionado contra zero-shot.** Os baselines foram TREINADOS no corpus; o nosso prompt nunca viu uma redação rotulada dele. Isso favorece o nosso resultado como feito, e é a parte legitimamente interessante — mas o outro lado é o item 4.
4. **Contaminação possível, e assimétrica.** O Essay-BR é público desde 2021. Se o LLM viu pares redação↔nota em pré-treino, o zero-shot deixa de ser zero-shot. Não temos como verificar. Os baselines não têm esse problema — eles treinam no corpus abertamente, por desenho.

**O que a tabela sustenta**, com essas quatro ressalvas na frente: um LLM sem nenhum treino no corpus, guiado por um prompt escrito para *produto* (que além da nota produz feedback pedagógico com trechos citados), fica na mesma faixa dos baselines publicados — acima em C3/C4/C5, claramente abaixo em C1.

**C1 é o achado que interessa.** É a competência de domínio da norma culta, e é onde os métodos baseados em features ganham: contar erros gramaticais é exatamente o que eles fazem bem. Também é a competência mais ameaçada no produto real, onde o texto chega via OCR de manuscrito — um erro de transcrição vira um desvio inexistente. Sinal consistente com a decisão de mostrar o preview do OCR ao aluno antes de qualquer nota.

**Contexto de o que conta como bom.** O próprio paper do corpus registra que a área usa 0,6–0,8 de QWK como piso para uso somativo, e conclui que os baselines dele *"are not fit for summative student assessment"*. Nenhum número desta página chega lá. Isso não invalida o produto — sustenta o enquadramento dele: a ferramenta é **formativa** (devolve diagnóstico por competência com trecho citado), não somativa (não substitui a nota oficial). A nota é o gancho; o feedback é o valor.
