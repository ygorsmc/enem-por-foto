# Perguntas feitas ao Jev

Cada redação foi enviada ao Jev (`jev-1.14.0`, da TypeSafe AI) com estas 71 perguntas. O Jev responde cada uma de forma independente, e a resposta vira uma ou mais colunas `jev_*` do dataset [`data/essaybr_jev.csv.gz`](data/essaybr_jev.csv.gz), usado no [notebook do modelo](modelo_hibrido.ipynb).

- **`noul`** (sim ou não): a coluna é a probabilidade de "sim" que o Jev devolve, entre 0 e 1.
- **`score`** (escala de níveis): a coluna é o nível contínuo que o Jev devolve (campo `score`, por exemplo 1,89): de 0 a 5 nas cinco notas por competência (`score_c1` a `score_c5`) e de 0 a 2 nas demais.
- **`choice`** (escolha entre opções): uma coluna `jev_tipo_<opção>` por opção, com a probabilidade de cada.
- `redacao` e `tema` são os campos enviados junto com as perguntas. Nas perguntas com `{tema}`, o texto do tema entra na própria pergunta.
- **No modelo:** 60 das 76 colunas entram no modelo de nota. As outras 16 são versões antigas ou variantes de perguntas reformuladas (o mesmo conceito duas vezes) e ficam de fora; algumas delas ainda servem ao portão de nota zero ou ao checklist do feedback no bot.

## `score_c1`

Tipo `score` · coluna `jev_score_c1` · no modelo: **sim**

**Pergunta:** Qual o nível de domínio da escrita formal da língua portuguesa em `redacao`?
<br>**Inspecionar:** `redacao`
<br>**Foco:** Avaliar desvios gramaticais, ortografia, acentuação, pontuação, regência, concordância, crase, registro formal e estrutura sintática dos períodos.

Níveis:

- **0:** Desconhecimento da modalidade escrita formal. Texto incompreensível ou quase sem domínio das convenções básicas da escrita.
- **1:** Domínio precário da escrita formal. Desvios frequentes, diversificados e sistemáticos de gramática, ortografia, pontuação ou oralidade ao longo de todo o texto.
- **2:** Domínio insuficiente da escrita formal. Muitos desvios de gramática, convenções da escrita, registro informal ou falhas frequentes de estruturação dos períodos.
- **3:** Domínio mediano da escrita formal. Alguns desvios gramaticais, de pontuação ou de convenção que se repetem ou chamam atenção, mas sem impedir a leitura.
- **4:** Bom domínio da escrita formal. Poucos desvios pontuais de gramática ou convenção da escrita e períodos no geral bem estruturados.
- **5:** Domínio excelente da escrita formal. Escrita formal consistente, períodos bem articulados e no máximo desvio raro e isolado.

## `score_c2`

Tipo `score` · coluna `jev_score_c2` · no modelo: **sim**

**Pergunta:** Qual o nível de compreensão do tema, estrutura dissertativo-argumentativa e uso de repertório em `redacao`?
<br>**Inspecionar:** `tema`, `redacao`
<br>**Foco:** Avaliar aderência completa ao recorte do tema, defesa de ponto de vista em texto dissertativo-argumentativo e produtividade do repertório sociocultural.

Níveis:

- **0:** Fuga total ao `tema` ou texto não dissertativo-argumentativo. Não trata nem do assunto geral de `tema`, ou predomina outro tipo textual (narrativo/descritivo).
- **1:** Tangenciamento do `tema` ou traços constantes de outro tipo textual. Aborda apenas o assunto genérico sem alcançar o recorte específico de `tema`.
- **2:** Estrutura dissertativa insuficiente. Falta proposição, argumentação ou conclusão reconhecíveis.
- **3:** Aborda o tema com argumentação previsível e domínio mediano da estrutura. Repertório ausente, senso comum ou repertório de bolso desconectado do argumento.
- **4:** Argumentação consistente sobre o tema e bom domínio da estrutura dissertativa. Proposição, argumentação e conclusão bem formadas, com repertório pertinente mas pouco produtivo.
- **5:** Argumentação consistente com repertório sociocultural produtivo e excelente domínio da estrutura. Repertório legítimo, pertinente ao `tema` e articulado diretamente ao argumento.

## `score_c3`

Tipo `score` · coluna `jev_score_c3` · no modelo: **sim**

**Pergunta:** Qual o nível do projeto de texto, seleção, organização e desenvolvimento dos argumentos em `redacao`?
<br>**Inspecionar:** `tema`, `redacao`
<br>**Foco:** Avaliar a arquitetura das ideias: planejamento prévio, progressão lógica, desenvolvimento das causas/consequências e autoria própria.

Níveis:

- **0:** Informações não relacionadas ao `tema` e sem defesa de ponto de vista. Ausência total de tese e de projeto argumentativo.
- **1:** Pouco relacionado ao `tema`, incoerente ou sem defesa clara de ponto de vista. Ideias soltas ou contraditórias que não sustentam uma tese.
- **2:** Argumentos desorganizados ou contraditórios, presos a ideias genéricas sobre o `tema`. Reprodução desarticulada de ideias óbvias sobre o assunto, com lacunas graves.
- **3:** Argumentos previsíveis, presos a ideias genéricas sobre o `tema`, e pouco organizados. Ideias apenas enunciadas sem aprofundamento suficiente ou sem hierarquia clara.
- **4:** Projeto de texto organizado com indícios de autoria. Argumentos bem relacionados à tese e desenvolvidos, ainda que com alguma lacuna pontual.
- **5:** Projeto de texto consistente, bem organizado e com autoria evidente. Progressão lógica clara entre introdução, desenvolvimentos e conclusão, com explicação completa dos argumentos.

## `score_c4`

Tipo `score` · coluna `jev_score_c4` · no modelo: **sim**

**Pergunta:** Qual o nível de coesão textual na articulação das partes de `redacao`?
<br>**Inspecionar:** `redacao`
<br>**Foco:** Avaliar conectivos entre parágrafos e períodos, adequação das relações lógicas e uso de referenciação (pronomes, sinônimos) sem repetição excessiva.

Níveis:

- **0:** Não articula as informações. Frases desconexas sem ligação linguística entre si.
- **1:** Articulação precária. Texto em bloco único ou com ausência generalizada de conectivos e referenciação.
- **2:** Articulação insuficiente, com muitas inadequações e repertório coesivo limitado. Conectivos usados fora da relação lógica real ou muitas repetições desnecessárias de palavras.
- **3:** Articulação mediana, com algumas inadequações e repertório pouco diversificado. Conectivos repetitivos ou falhas pontuais de ligação entre orações e parágrafos.
- **4:** Boa articulação, com poucas inadequações e repertório coesivo diversificado. Uso variado e no geral adequado de conectivos interparágrafo e referenciação.
- **5:** Boa articulação em todo o texto, com repertório diversificado de recursos coesivos e sem inadequações graves. Parágrafos e períodos articulados com variedade e precisão lógica.

## `score_c5`

Tipo `score` · coluna `jev_score_c5` · no modelo: **sim**

**Pergunta:** Qual o nível da proposta de intervenção apresentada em `redacao`?
<br>**Inspecionar:** `tema`, `redacao`
<br>**Foco:** Avaliar quantos dos cinco elementos válidos estão presentes (agente específico, ação, modo/meio, efeito, detalhamento) e se a proposta se articula à discussão, respeitando os direitos humanos.

Níveis:

- **0:** Sem proposta de intervenção, proposta não relacionada ao `tema` ou violação aos direitos humanos. Apenas constata um problema, ou não propõe ação, ou viola direitos humanos.
- **1:** Proposta vaga, precária ou ligada apenas ao assunto genérico fora do recorte de `tema`. Apenas um elemento válido ou formulação condicional/hipotética sem ação concreta.
- **2:** Proposta insuficiente ou desarticulada da discussão do texto. Apenas dois elementos válidos ou proposta genérica que não responde aos argumentos desenvolvidos.
- **3:** Proposta elaborada de forma mediana. Apresenta cerca de três elementos válidos relacionados ao problema discutido.
- **4:** Proposta bem elaborada, relacionada ao `tema` e articulada à discussão. Apresenta quatro elementos válidos (por exemplo: agente específico, ação, modo/meio e efeito).
- **5:** Proposta muito bem elaborada, detalhada, relacionada ao `tema` e articulada à discussão. Apresenta todos os cinco elementos válidos: agente específico, ação, modo/meio, efeito e detalhamento de algum deles.

## `triagem_fuga_total`

Tipo `noul` · coluna `jev_triagem_fuga_total` · no modelo: **não**

**Pergunta:** A `redacao` foge totalmente do assunto geral e do recorte específico de `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** O texto trata de um assunto completamente alheio ao `tema` proposto. *Não incluir:* Textos que abordam o assunto geral de forma rasa ou tangenciam o recorte.
- **Não:** O texto aborda ao menos o assunto geral de `tema` ou seu recorte específico.

## `triagem_identificacao`

Tipo `noul` · coluna `jev_triagem_identificacao` · no modelo: **não**

**Pergunta:** A `redacao` contém nome próprio do autor ou assinatura no corpo do texto para se identificar?


## `triagem_parte_desconectada`

Tipo `noul` · coluna `jev_triagem_parte_desconectada` · no modelo: **não**

**Pergunta:** A `redacao` contém recado dirigido à banca, xingamento proposital ou trecho solto sem relação com o argumento?


## `triagem_lingua_estrangeira`

Tipo `noul` · coluna `jev_triagem_lingua_estrangeira` · no modelo: **sim**

**Pergunta:** A maior parte de `redacao` está escrita em outro idioma que não o português?


## `c2_aborda_recorte_completo`

Tipo `noul` · coluna `jev_c2_aborda_recorte_completo` · no modelo: **não**

**Pergunta:** A `redacao` desenvolve todos os elementos centrais e o recorte específico de `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Trata explicitamente tanto do assunto geral quanto do recorte específico pedido em `tema`.
- **Não:** Fica apenas no assunto genérico (tangenciamento) ou foge totalmente do `tema`.

## `c2_tipo_dissertativo_argumentativo`

Tipo `noul` · coluna `jev_c2_tipo_dissertativo_argumentativo` · no modelo: **sim**

**Pergunta:** A `redacao` é predominantemente um texto dissertativo-argumentativo?
<br>**Inspecionar:** `redacao`

- **Sim:** O texto busca defender uma opinião/tese por meio de argumentos e explicações.
- **Não:** Predomina relato narrativo, descrição neutra, lista de instruções ou pura exposição informativa sem defesa de tese.

## `c2_tese_explicita`

Tipo `noul` · coluna `jev_c2_tese_explicita` · no modelo: **sim**

**Pergunta:** A `redacao` enuncia explicitamente uma tese ou ponto de vista sobre `tema`?

- **Sim:** Há posicionamento claro defendido ao longo do texto.
- **Não:** O texto apenas descreve fatos ou menciona o assunto sem tomar posição clara.

## `c2_repertorio_legitimado`

Tipo `noul` · coluna `jev_c2_repertorio_legitimado` · no modelo: **sim**

**Pergunta:** O repertório sociocultural citado em `redacao` apoia-se em área do conhecimento reconhecida ou fonte nomeada (obra, autor, lei, fato histórico, órgão ou especialista)?

- **Sim:** Cita pelo menos uma obra, autor, lei, fato histórico, conceito teórico, dado com instituição ou especialista identificado por nome ou área.
- **Não:** Não há repertório externo, ou limita-se a senso comum sem fonte ('estudos apontam', 'a ciência diz', 'dizem por aí').

## `c2_repertorio_produtivo`

Tipo `noul` · coluna `jev_c2_repertorio_produtivo` · no modelo: **sim**

**Pergunta:** O repertório sociocultural em `redacao` é articulado para sustentar um argumento específico?

- **Sim:** A referência é explicada e conectada ao argumento de modo que removê-la enfraqueceria o parágrafo.
- **Não:** Não há repertório externo, ou ele é apenas mencionado de passagem / usado de forma genérica aplicável a qualquer tema.

## `c3_projeto_texto_claro`

Tipo `noul` · coluna `jev_c3_projeto_texto_claro` · no modelo: **sim**

**Pergunta:** A `redacao` demonstra planejamento prévio em que cada parágrafo cumpre uma função clara na defesa da tese?

- **Sim:** É possível identificar o plano do texto, com introdução, desenvolvimento dos argumentos e conclusão articulados entre si.
- **Não:** As ideias parecem enfileiradas sem hierarquia, com saltos ou falta de direção argumentativa.

## `c3_argumentos_desenvolvidos`

Tipo `score` · coluna `jev_c3_argumentos_desenvolvidos` · no modelo: **sim**

**Pergunta:** Em que grau os argumentos anunciados em `redacao` são desenvolvidos e explicados?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Os argumentos ficam só enunciados, são contraditórios ou deixam lacunas graves de sentido.
- **1:** Parte dos argumentos é explicada, mas há trechos rasos ou apoiados só em afirmações genéricas.
- **2:** Os argumentos são explicados de forma consistente (causa-consequência, dados, comparações ou exemplos) com elaboração própria.

## `c3_conclusao_retoma_tese`

Tipo `score` · coluna `jev_c3_conclusao_retoma_tese` · no modelo: **sim**

**Pergunta:** Em que grau o último parágrafo de `redacao` fecha a argumentação desenvolvida no texto?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Não há parágrafo conclusivo, ou o último parágrafo muda de assunto, contradiz a tese ou traz ideia nova não preparada.
- **1:** O último parágrafo existe, mas é genérico: repete frases feitas ou só propõe medidas sem amarrar a tese e os argumentos.
- **2:** O último parágrafo retoma a tese e os argumentos desenvolvidos e os fecha de forma coerente com a introdução.

## `c5_tem_proposta`

Tipo `noul` · coluna `jev_c5_tem_proposta` · no modelo: **sim**

**Pergunta:** A `redacao` apresenta ao menos uma proposta de intervenção social ou institucional para enfrentar o problema de `tema`?

- **Sim:** Propõe medida concreta de intervenção na sociedade (política pública, ação educativa, regulação, projeto coletivo ou iniciativa institucional).
- **Não:** Apenas constata o problema, faz desejo genérico ou dá só conselhos individuais de cuidado pessoal ao leitor sem medida coletiva ou institucional.

## `c5_agente_presente`

Tipo `noul` · coluna `jev_c5_agente_presente` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` nomeia quem deve executar a ação?

- **Sim:** Há um sujeito indicado como responsável pela ação, mesmo que genérico.
- **Não:** Não há proposta ou a ação aparece sem indicar quem a executa ('é preciso fazer X').

## `c5_agente_especifico`

Tipo `noul` · coluna `jev_c5_agente_especifico` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` nomeia um agente específico e institucional (e não um agente vago)?

- **Sim:** Indica órgão, poder ou instituição concreta (como Ministério da Educação, governo federal, escolas, mídia, ONGs).
- **Não:** Não nomeia agente ou usa termo vago como 'a sociedade', 'as pessoas', 'todos', 'nós' ou 'alguém'.

## `c5_acao`

Tipo `noul` · coluna `jev_c5_acao` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` indica claramente qual ação deve ser realizada?


## `c5_modo_meio`

Tipo `noul` · coluna `jev_c5_modo_meio` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` explica como ou por qual meio a ação será executada?

- **Sim:** Especifica o instrumento, canal ou forma de execução (ex.: 'por meio de campanhas...', 'através de verbas...').
- **Não:** Diz apenas o que fazer sem explicar como ou por qual meio executar.

## `c5_efeito`

Tipo `noul` · coluna `jev_c5_efeito` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` declara a finalidade ou resultado esperado da ação?

- **Sim:** Explicita o objetivo da medida (ex.: 'para reduzir...', 'a fim de garantir...', 'com o intuito de...').
- **Não:** Não indica qual efeito ou finalidade se espera alcançar com a medida.

## `c5_detalhamento`

Tipo `noul` · coluna `jev_c5_detalhamento` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` aprofunda ou exemplifica algum dos elementos (agente, ação, modo/meio ou efeito) com informação adicional?


## `c5_articulada_discussao`

Tipo `noul` · coluna `jev_c5_articulada_discussao` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` responde diretamente aos problemas discutidos nos parágrafos anteriores?


## `c5_viola_direitos_humanos`

Tipo `noul` · coluna `jev_c5_viola_direitos_humanos` · no modelo: **sim**

**Pergunta:** A `redacao` defende tortura, execução sumária, justiça com as próprias mãos, discurso de ódio ou incitação à violência contra grupos?

- **Sim:** Há defesa explícita de violação grave aos direitos humanos na proposta ou no texto.
- **Não:** A proposta e o texto respeitam os direitos humanos.

## `c2_repertorio_presente`

Tipo `noul` · coluna `jev_c2_repertorio_presente` · no modelo: **sim**

**Pergunta:** A `redacao` usa algum repertório sociocultural — informação, fato, citação, dado, lei, obra, conceito ou experiência — relacionado ao `tema` como argumento?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Cita ao menos uma referência (autor, obra, filme, dado estatístico, fato histórico, lei, conceito teórico ou experiência) usada para sustentar o ponto de vista.
- **Não:** Baseia-se apenas em opinião e senso comum, sem nenhuma referência.

## `c1_truncamento`

Tipo `score` · coluna `jev_c1_truncamento` · no modelo: **sim**

**Pergunta:** Com que frequência `redacao` apresenta períodos truncados (ponto final separando orações que deveriam formar um mesmo período) ou justapostos (vírgula no lugar de ponto final)?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Truncamentos ou justaposições recorrentes, prejudicando a fluidez em vários trechos.
- **1:** Truncamentos ou justaposições em casos isolados.
- **2:** Períodos completos e bem delimitados ao longo do texto.

## `c1_periodos_complexos`

Tipo `noul` · coluna `jev_c1_periodos_complexos` · no modelo: **sim**

**Pergunta:** A `redacao` constrói períodos complexos, com orações subordinadas ou intercaladas bem articuladas?
<br>**Inspecionar:** `redacao`

- **Sim:** Alterna períodos simples e complexos com segurança, usando subordinação ou intercalação sem perder a clareza.
- **Não:** Predominam períodos curtos e simples, ou os períodos complexos ficam mal resolvidos.

## `c1_registro_informal`

Tipo `noul` · coluna `jev_c1_registro_informal` · no modelo: **sim**

**Pergunta:** A `redacao` usa registro informal ou marcas de oralidade?
<br>**Inspecionar:** `redacao`

- **Sim:** Usa gírias, coloquialismos ou marcas de fala (como 'a gente', 'tipo', 'né', 'pra', 'tá', 'aí').
- **Não:** Mantém o registro formal ao longo de todo o texto.

## `c1_vocabulario`

Tipo `score` · coluna `jev_c1_vocabulario` · no modelo: **sim**

**Pergunta:** Em que grau o vocabulário de `redacao` é preciso e adequado ao contexto?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Há palavras com sentido trocado ou impreciso, ou confusão entre palavras parecidas.
- **1:** Vocabulário adequado, mas genérico ou repetitivo.
- **2:** Vocabulário preciso, variado e usado no sentido correto.

## `c1_reincidencia_desvios`

Tipo `score` · coluna `jev_c1_reincidencia_desvios` · no modelo: **sim**

**Pergunta:** Como se distribuem os desvios de gramática e de convenções da escrita em `redacao`?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Desvios frequentes e variados ao longo de todo o texto.
- **1:** Alguns desvios, que se repetem ou chamam atenção.
- **2:** No máximo um deslize isolado e não reincidente.

## `c2_tangenciamento`

Tipo `noul` · coluna `jev_c2_tangenciamento` · no modelo: **não**

**Pergunta:** A `redacao` discute apenas o assunto geral de `tema`, sem enfrentar o recorte específico pedido?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Fala do assunto amplo (por exemplo, 'educação') e ignora a delimitação do `tema` (por exemplo, 'educação de surdos'), ou trata só de uma parte secundária dele.
- **Não:** A discussão gira em torno do recorte específico do `tema`.

## `c2_tracos_outro_tipo`

Tipo `noul` · coluna `jev_c2_tracos_outro_tipo` · no modelo: **sim**

**Pergunta:** A `redacao` tem trechos extensos predominantemente narrativos, descritivos ou meramente expositivos, sem defesa de opinião?
<br>**Inspecionar:** `redacao`

- **Sim:** Em parte relevante do texto, conta uma história, descreve ou apenas informa, sem argumentar.
- **Não:** Argumenta em defesa de um ponto de vista ao longo do texto.

## `c2_estrutura_completa`

Tipo `noul` · coluna `jev_c2_estrutura_completa` · no modelo: **sim**

**Pergunta:** A `redacao` apresenta as três partes do texto dissertativo-argumentativo: introdução com proposição, desenvolvimento argumentativo e conclusão?
<br>**Inspecionar:** `redacao`

- **Sim:** As três partes são reconhecíveis: a introdução apresenta o ponto de vista, o desenvolvimento argumenta e há um fechamento.
- **Não:** Falta alguma das três partes, ou elas não são reconhecíveis.

## `c2_repertorio_de_bolso`

Tipo `noul` · coluna `jev_c2_repertorio_de_bolso` · no modelo: **não**

**Pergunta:** O repertório citado em `redacao` é genérico, do tipo que serviria para qualquer tema, sem conexão específica com `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Usa referência pronta e decorativa (por exemplo, Constituição citada de forma genérica, Bauman, 'Utopia') sem relacioná-la ao recorte do `tema`.
- **Não:** O repertório é específico do `tema` e explicado, ou não há repertório.

## `c2_argumentacao_consistente`

Tipo `score` · coluna `jev_c2_argumentacao_consistente` · no modelo: **sim**

**Pergunta:** Em que grau a argumentação de `redacao` vai além do senso comum?
<br>**Inspecionar:** `tema`, `redacao`

Níveis:

- **0:** Argumentação previsível: repete ideias óbvias e clichês sobre o `tema`, sem aprofundar.
- **1:** Argumentação parcialmente consistente: alguns argumentos vão além do óbvio, outros ficam no senso comum.
- **2:** Argumentação consistente: argumentos fundamentados, com reflexão que vai além do senso comum.

## `c3_progressao`

Tipo `score` · coluna `jev_c3_progressao` · no modelo: **sim**

**Pergunta:** Em que grau as ideias de `redacao` progridem sem saltos temáticos nem repetições desnecessárias?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** As ideias se repetem ou saltam de um assunto a outro sem ligação.
- **1:** Progressão em geral clara, com algum salto ou repetição pontual.
- **2:** Cada parte acrescenta algo novo e prepara a seguinte, em progressão clara.

## `c3_contradicao`

Tipo `noul` · coluna `jev_c3_contradicao` · no modelo: **não**

**Pergunta:** A `redacao` apresenta ideias que se contradizem ou que contrariam o ponto de vista defendido?
<br>**Inspecionar:** `redacao`

- **Sim:** Há afirmações incompatíveis entre si, ou trechos que enfraquecem ou negam a tese defendida.
- **Não:** As ideias são compatíveis entre si e com o ponto de vista.

## `c3_informacoes_soltas`

Tipo `noul` · coluna `jev_c3_informacoes_soltas` · no modelo: **não**

**Pergunta:** A `redacao` traz informações, fatos ou opiniões soltos, sem desenvolvimento nem ligação com o ponto de vista?
<br>**Inspecionar:** `redacao`

- **Sim:** Há informações jogadas no texto que não são explicadas nem usadas para sustentar a tese.
- **Não:** Cada informação é desenvolvida e ligada ao ponto de vista.

## `c3_autoria`

Tipo `score` · coluna `jev_c3_autoria` · no modelo: **sim**

**Pergunta:** Em que grau `redacao` revela autoria, isto é, interpretação própria das informações em defesa do ponto de vista?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Só reproduz informações genéricas, sem interpretação própria.
- **1:** Há indícios de autoria, mas parte do texto é genérica.
- **2:** Autoria evidente: interpreta e relaciona as informações de forma própria e consistente.

## `c3_especificidade`

Tipo `score` · coluna `jev_c3_especificidade` · no modelo: **sim**

**Pergunta:** Em que grau os argumentos de `redacao` são específicos e concretos?
<br>**Inspecionar:** `tema`, `redacao`

Níveis:

- **0:** Afirmações amplas que serviriam para muitos temas.
- **1:** Argumentos parcialmente específicos.
- **2:** Argumentos que apontam causas, grupos, situações ou consequências precisas ligadas ao `tema`.

## `c3_evidencia_concreta`

Tipo `noul` · coluna `jev_c3_evidencia_concreta` · no modelo: **sim**

**Pergunta:** A `redacao` sustenta algum argumento com exemplo concreto, dado ou fato verificável?
<br>**Inspecionar:** `redacao`

- **Sim:** Usa exemplo real, estatística, fato histórico ou caso documentado para apoiar um argumento.
- **Não:** Usa só afirmações gerais ou exemplos hipotéticos.

## `c4_articulacao_paragrafos`

Tipo `score` · coluna `jev_c4_articulacao_paragrafos` · no modelo: **sim**

**Pergunta:** Em que grau os parágrafos de `redacao` se ligam uns aos outros por conectivos ou expressões de retomada?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Parágrafos justapostos, sem marca de ligação entre eles.
- **1:** Alguns parágrafos se ligam explicitamente ao anterior, outros começam soltos.
- **2:** Todos os parágrafos se ligam explicitamente ao anterior.

## `c4_articulacao_periodos`

Tipo `score` · coluna `jev_c4_articulacao_periodos` · no modelo: **sim**

**Pergunta:** Em que grau as frases dentro dos parágrafos de `redacao` estão encadeadas?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Frases soltas, sem conectivos nem retomadas.
- **1:** Encadeamento irregular: parte das frases ligadas, parte soltas.
- **2:** Frases encadeadas por conectivos e retomadas variados.

## `c4_inadequacoes_coesivas`

Tipo `score` · coluna `jev_c4_inadequacoes_coesivas` · no modelo: **sim**

**Pergunta:** Com que frequência `redacao` usa conectivos ou retomadas com relação lógica inadequada (por exemplo, 'portanto' sem conclusão, 'entretanto' sem oposição)?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Inadequações frequentes.
- **1:** Inadequações pontuais.
- **2:** Nenhuma inadequação: cada conectivo expressa a relação lógica correta.

## `c4_referenciacao`

Tipo `score` · coluna `jev_c4_referenciacao` · no modelo: **sim**

**Pergunta:** Em que grau `redacao` retoma termos já citados por pronomes, sinônimos ou expressões resumitivas em vez de repeti-los?
<br>**Inspecionar:** `redacao`

Níveis:

- **0:** Repete as mesmas palavras em vez de retomá-las, ou usa pronomes com referente confuso.
- **1:** Usa retomadas, mas com repetições ou ambiguidades.
- **2:** Retoma termos com recursos variados e referentes claros.

## `c4_conectivos_artificiais`

Tipo `noul` · coluna `jev_c4_conectivos_artificiais` · no modelo: **não**

**Pergunta:** A `redacao` empilha conectivos de forma artificial ou excessiva, sem relação lógica real entre as partes?
<br>**Inspecionar:** `redacao`

- **Sim:** Usa conectivos ou expressões de transição em excesso, como enfeite, sem que liguem ideias de fato.
- **Não:** Os conectivos aparecem onde há relação lógica a expressar.

## `c5_proposta_vaga`

Tipo `noul` · coluna `jev_c5_proposta_vaga` · no modelo: **não**

**Pergunta:** A proposta de intervenção em `redacao` é vaga ou genérica, aplicável a quase qualquer problema?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Propõe algo genérico (por exemplo, 'o governo deve investir em educação e conscientização') sem especificar o problema do `tema`.
- **Não:** A proposta é específica para o problema discutido, ou não há proposta.

## `c5_condicional`

Tipo `noul` · coluna `jev_c5_condicional` · no modelo: **não**

**Pergunta:** A proposta de intervenção em `redacao` é formulada só como condição ou hipótese, sem propor a ação de forma assertiva?
<br>**Inspecionar:** `redacao`

- **Sim:** Usa construções como 'se X for feito, Y poderá acontecer' sem afirmar o que deve ser feito.
- **Não:** Propõe a ação de forma assertiva, ou não há proposta.

## `c5_relacionada_recorte`

Tipo `noul` · coluna `jev_c5_relacionada_recorte` · no modelo: **não**

**Pergunta:** A proposta de intervenção em `redacao` enfrenta o problema específico do recorte de `tema`, e não só o assunto geral?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** A ação proposta ataca o problema delimitado pelo `tema`.
- **Não:** A proposta trata só do assunto geral, de outro problema, ou não há proposta.

## `triagem_prosa`

Tipo `noul` · coluna `jev_triagem_prosa` · no modelo: **sim**

**Pergunta:** A `redacao` está escrita em prosa, em parágrafos, e não em versos, tópicos ou lista?
<br>**Inspecionar:** `redacao`

- **Sim:** O texto é corrido, organizado em frases e parágrafos.
- **Não:** O texto está em versos, em tópicos ou em forma de lista.

## `triagem_ininteligivel`

Tipo `noul` · coluna `jev_triagem_ininteligivel` · no modelo: **sim**

**Pergunta:** Uma parte relevante de `redacao` é ininteligível, com sequências de palavras sem sentido?
<br>**Inspecionar:** `redacao`

- **Sim:** Há trechos que não podem ser compreendidos, com palavras truncadas ou sem nexo.
- **Não:** O texto pode ser lido e compreendido, mesmo com desvios.

## `global_persuasao`

Tipo `score` · coluna `jev_global_persuasao` · no modelo: **sim**

**Pergunta:** Quão convincente seria a argumentação de `redacao` para um leitor que ainda não concorda com o ponto de vista?
<br>**Inspecionar:** `tema`, `redacao`

Níveis:

- **0:** Pouco convincente: o leitor não teria motivo para mudar de opinião.
- **1:** Convence em parte: alguns argumentos têm força, outros não.
- **2:** Convincente: os argumentos juntos sustentam bem o ponto de vista.

## `tema_assunto_ref`

Tipo `noul` · coluna `jev_tema_assunto_ref` · no modelo: **sim**

**Pergunta:** A `redacao` trata do assunto geral de `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** O texto discute o mesmo assunto amplo de `tema`, mesmo que não chegue ao recorte específico.
- **Não:** O texto trata de outro assunto, sem relação com `tema`.

## `tema_recorte_ref`

Tipo `noul` · coluna `jev_tema_recorte_ref` · no modelo: **sim**

**Pergunta:** A `redacao` discute o recorte específico proposto em `tema`, e não só o assunto amplo?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** A discussão gira em torno do problema delimitado por `tema`.
- **Não:** O texto fica no assunto amplo, trata de outro aspecto ou de outro assunto.

## `tema_assunto_emb`

Tipo `noul` · coluna `jev_tema_assunto_emb` · no modelo: **não**

**Pergunta:** A `redacao` trata do assunto geral do tema "{tema}"?
<br>**Inspecionar:** `redacao`

- **Sim:** O texto discute o mesmo assunto amplo do tema "{tema}", mesmo que não chegue ao recorte específico.
- **Não:** O texto trata de outro assunto, sem relação com o tema "{tema}".

## `tema_recorte_emb`

Tipo `noul` · coluna `jev_tema_recorte_emb` · no modelo: **não**

**Pergunta:** A `redacao` discute o recorte específico do tema "{tema}", e não só o assunto amplo?
<br>**Inspecionar:** `redacao`

- **Sim:** A discussão gira em torno do problema delimitado pelo tema "{tema}".
- **Não:** O texto fica no assunto amplo, trata de outro aspecto ou de outro assunto.

## `tema_e_emb`

Tipo `noul` · coluna `jev_tema_e_emb` · no modelo: **não**

**Pergunta:** O tema de `redacao` é "{tema}"?
<br>**Inspecionar:** `redacao`

- **Sim:** A redação foi escrita sobre esse tema.
- **Não:** A redação foi escrita sobre outro tema.

## `c5_recorte_emb`

Tipo `noul` · coluna `jev_c5_recorte_emb` · no modelo: **sim**

**Pergunta:** A proposta de intervenção em `redacao` enfrenta o problema do tema "{tema}"?
<br>**Inspecionar:** `redacao`

- **Sim:** A ação proposta ataca o problema do tema "{tema}".
- **Não:** A proposta trata de outro problema, só do assunto geral, ou não há proposta.

## `triagem_identificacao_v2`

Tipo `noul` · coluna `jev_triagem_identificacao_v2` · no modelo: **não**

**Pergunta:** A `redacao` traz a assinatura ou o nome de quem a escreveu?
<br>**Inspecionar:** `redacao`

- **Sim:** O autor se identifica no texto: assina, escreve o próprio nome ou se apresenta pelo nome.
- **Não:** O autor não se identifica. Nomes de pessoas citadas como referência (autores, cientistas, personagens históricos ou públicos) não contam como identificação.

## `c3_coerencia`

Tipo `noul` · coluna `jev_c3_coerencia` · no modelo: **sim**

**Pergunta:** As ideias de `redacao` são coerentes entre si e com o ponto de vista defendido?
<br>**Inspecionar:** `redacao`

- **Sim:** Todas as afirmações são compatíveis entre si e ajudam a sustentar o ponto de vista.
- **Não:** Há afirmações incompatíveis entre si, ou trechos que enfraquecem ou negam o ponto de vista.

## `c3_informacoes_articuladas`

Tipo `noul` · coluna `jev_c3_informacoes_articuladas` · no modelo: **sim**

**Pergunta:** Cada informação, fato ou opinião de `redacao` é desenvolvido e ligado ao ponto de vista?
<br>**Inspecionar:** `redacao`

- **Sim:** As informações são explicadas e usadas para sustentar a tese.
- **Não:** Há informações jogadas no texto, sem explicação nem ligação com a tese.

## `c5_proposta_especifica`

Tipo `noul` · coluna `jev_c5_proposta_especifica` · no modelo: **sim**

**Pergunta:** A proposta de intervenção de `redacao` é específica para o problema de `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Diz concretamente o que fazer diante do problema discutido; não serviria para qualquer outro tema.
- **Não:** Propõe algo genérico, que serviria para quase qualquer problema (por exemplo, 'investir em educação e conscientização'), ou não há proposta.

## `c4_conectivos_funcionais`

Tipo `noul` · coluna `jev_c4_conectivos_funcionais` · no modelo: **sim**

**Pergunta:** Os conectivos de `redacao` expressam relações lógicas reais entre as ideias que ligam?
<br>**Inspecionar:** `redacao`

- **Sim:** Cada conectivo marca uma relação de fato presente entre as ideias (causa, oposição, conclusão, adição).
- **Não:** Há conectivos usados como enfeite ou em excesso, sem relação lógica real.

## `c2_repertorio_especifico`

Tipo `noul` · coluna `jev_c2_repertorio_especifico` · no modelo: **sim**

**Pergunta:** O repertório citado em `redacao` tem relação direta com o recorte de `tema`?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** A referência trata do mesmo problema delimitado pelo tema e é explicada no texto.
- **Não:** A referência é genérica, serviria para qualquer tema, ou não há repertório.

## `c5_proposta_assertiva`

Tipo `noul` · coluna `jev_c5_proposta_assertiva` · no modelo: **sim**

**Pergunta:** A proposta de intervenção de `redacao` afirma diretamente qual ação deve ser feita?
<br>**Inspecionar:** `redacao`

- **Sim:** Diz o que deve ser feito de forma assertiva (por exemplo, 'o Ministério da Educação deve criar…').
- **Não:** Só levanta hipóteses ou condições ('se X for feito, Y poderá acontecer'), ou não há proposta.

## `triagem_identificacao_v3`

Tipo `noul` · coluna `jev_triagem_identificacao_v3` · no modelo: **sim**

**Pergunta:** A `redacao` traz assinatura, nome, apelido ou rubrica de quem a escreveu?
<br>**Inspecionar:** `redacao`

- **Sim:** O autor se identifica no texto: assina, escreve o próprio nome, apelido ou rubrica, ou se apresenta pelo nome.
- **Não:** O autor não se identifica. Nomes de pessoas citadas como referência (autores, cientistas, personagens históricos ou públicos) não contam como identificação.

## `triagem_trechos_relacionados`

Tipo `noul` · coluna `jev_triagem_trechos_relacionados` · no modelo: **sim**

**Pergunta:** Todos os trechos de `redacao` têm relação com o tema ou com a argumentação?
<br>**Inspecionar:** `tema`, `redacao`

- **Sim:** Cada trecho trata do tema ou serve à argumentação.
- **Não:** Há algum trecho solto, sem relação com o tema nem com a argumentação, como receita, hino, letra de música, oração, biografia ou recado à banca.

## `triagem_improperio`

Tipo `noul` · coluna `jev_triagem_improperio` · no modelo: **sim**

**Pergunta:** A `redacao` contém palavrão, xingamento ou ofensa dirigida a alguém?
<br>**Inspecionar:** `redacao`

- **Sim:** Há palavrão, xingamento ou ofensa a uma pessoa ou grupo.
- **Não:** O texto não ofende ninguém, mesmo quando critica ideias ou instituições.

## `triagem_tipo_textual`

Tipo `choice` · colunas `jev_tipo_narrativo`, `jev_tipo_poema`, `jev_tipo_carta`, `jev_tipo_lista`, `jev_tipo_expositivo`, `jev_tipo_dissertativo_argumentativo` · no modelo: **sim**

**Pergunta:** Que tipo de texto é `redacao`?

- `narrativo`: Conta uma história, com personagens e acontecimentos em sequência.
- `poema`: Escrito em versos ou estrofes.
- `carta`: Dirigido a um destinatário, com vocativo e despedida (por exemplo, 'Prezado…', 'Atenciosamente').
- `lista`: Organizado em tópicos ou itens soltos, não em parágrafos corridos.
- `expositivo`: Apenas informa ou explica o assunto, sem defender um ponto de vista.
- `dissertativo_argumentativo`: Texto em prosa que defende um ponto de vista com argumentos.
