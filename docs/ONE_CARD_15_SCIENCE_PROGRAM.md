# SARE P15 — Programa Científico para Um Único Cartão de 15 Pontos

## 1. Mandato

O objetivo operacional desta linha de pesquisa é emitir **exatamente um cartão simples de 15 dezenas** para cada concurso alvo e maximizar, com informação disponível antes do sorteio, a probabilidade conjunta estimada de que esse cartão seja o resultado exato.

Isso é diferente de cobertura combinatória. Um único cartão simples corresponde a exatamente **1** dos `C(25,15) = 3.268.760` resultados possíveis. Portanto, não existe garantia combinatória de 15 pontos com um único cartão. O objetivo cientificamente defensável é construir e testar uma distribuição condicional:

`P(S_t = s | I_{t-1})`, para todo `s` com 15 dezenas entre 25,

onde `I_{t-1}` contém somente informação conhecida antes do concurso alvo. O cartão emitido é o MAP:

`argmax_s P(S_t = s | I_{t-1})`.

O programa não autoriza compra automática e não transforma hipótese em alegação de vantagem.

## 2. Mudança arquitetural central

A linha anterior mede principalmente probabilidades marginais por dezena e Brier. Isso continua útil, mas é insuficiente para o objetivo de 15 pontos em um único cartão. Quinze marginais altas não definem, por si só, a combinação conjunta mais provável.

A nova linha introduz um **Joint Probability Engine**. Todo modelo candidato precisa, diretamente ou por transformação registrada, atribuir um score conjunto a estados completos de 15 dezenas.

O baseline conjunto uniforme é:

- espaço: `3.268.760` cartões;
- probabilidade de cada cartão: `1 / 3.268.760 ≈ 3,0592640634e-7`;
- log-loss uniforme: `ln(3.268.760) ≈ 14,9999212661` nats;
- entropia uniforme: `log2(3.268.760) ≈ 21,6403120243` bits.

A métrica primária científica do P15 passa a ser **joint log-loss versus uniforme**. Brier marginal, hits do cartão MAP, calibração e posição do resultado verdadeiro no ranking permanecem métricas secundárias.

Um acerto de 15 continua sendo o resultado operacional máximo, mas não pode ser a única métrica de aprendizagem: o evento é raro demais para fornecer potência estatística adequada em poucas centenas ou milhares de concursos.

## 3. Princípio de uso da ciência

O SARE não limitará a pesquisa a combinatória ou a um único modelo estatístico. Serão usados métodos científicos de várias áreas, desde que sejam:

1. falsificáveis;
2. computáveis com dados disponíveis;
3. registrados antes do período confirmatório;
4. avaliados cronologicamente;
5. comparados ao nulo correto;
6. submetidos a controle de multiplicidade;
7. impedidos de acessar o resultado alvo;
8. incapazes de alterar o campeão diretamente após um único concurso.

Métodos estabelecidos em outros domínios não são automaticamente evidência para Lotofácil. Eles entram como instrumentos científicos e precisam provar utilidade neste domínio.

## 4. Camadas científicas

### 4.1 Camada J0 — Nulo estrutural

Modelo uniforme de subconjuntos de 15 entre 25. É o comparador obrigatório de toda hipótese.

### 4.2 Camada J1 — Estatística regularizada e Bayesiana

Famílias imediatas:

- frequência regularizada;
- modelo condicional de Bernoulli com cardinalidade fixa;
- modelos Beta-Binomial/hierárquicos para propensões;
- shrinkage de James-Stein/empírico Bayes quando aplicável;
- médias exponenciais e filtros de estado para parâmetros lentamente variáveis;
- Bayesian model averaging.

O primeiro modelo implementado é uma família exponencial aditiva condicionada a exatamente 15 dezenas. Ele já fornece uma distribuição conjunta normalizada sobre todos os 3.268.760 cartões.

### 4.3 Camada J2 — Dependência entre dezenas

Se frequências marginais não bastarem, testar dependência residual por:

- modelos de máxima entropia com interações de pares;
- modelo Ising-like condicionado a soma 15;
- grafos de coocorrência com regularização;
- hypergraph sparse para trincas e interações superiores;
- graphical lasso ou equivalentes somente se a representação e hipóteses forem justificadas.

A interpretação correta é: pares/trincas só entram se explicarem informação prospectiva adicional depois de considerar as marginais e a estrutura de 15 entre 25.

### 4.4 Camada J3 — Tempo, memória e regimes

Testar se a ordem dos concursos contém informação real:

- autocorrelação multivariada;
- hazard de presença após sequências de ausência/presença;
- modelos de estado dinâmico;
- CUSUM/EWMA;
- Bayesian Online Changepoint Detection;
- Hidden Markov Models e Markov switching;
- filtros bayesianos preditivos;
- análise de janelas e meia-vida de informação.

Todo detector de regime precisa ser calibrado contra séries nulas para controlar falso alarme. Um regime encontrado retrospectivamente não pode ser tratado como se tivesse sido conhecido antes.

### 4.5 Camada J4 — Teoria da informação

Ferramentas:

- informação mútua corrigida;
- conditional mutual information;
- transfer entropy com correção para amostra finita;
- entropia de Shannon;
- entropia condicional;
- permutation entropy;
- Lempel-Ziv complexity;
- minimum description length.

Informação mútua e transfer entropy são usadas para descobrir dependência candidata, não para criar pesos arbitrários. Viés de amostra pequena e sparse bins devem ser tratados explicitamente.

Permutation entropy e medidas algorítmicas são diagnósticas por padrão. Só se tornam preditores após protocolo próprio e validação prospectiva.

## 5. Dinâmica não linear, caos e sistemas complexos

Hipóteses conceituais permitidas para investigação:

- recurrence quantification analysis;
- ordinal pattern dynamics;
- surrogate-data tests para não linearidade;
- estimativas de dimensão/complexidade quando a representação for justificável;
- assinaturas compatíveis com processos caóticos versus estocásticos;
- redes de recorrência;
- complexidade multiescala.

Limite obrigatório: detectar baixa entropia, não linearidade ou estrutura não prova previsibilidade útil. Sistemas caóticos podem ser determinísticos e ainda serem imprevisíveis sem condições iniciais precisas.

## 6. Física do sorteio e causalidade

A Lotofácil é um processo físico macroscópico. A CAIXA informa que o sorteio usa um globo carregado com bolas numeradas de 01 a 25, sem repetição no mesmo concurso. A página de regras também descreve carregamento, intervenções, auditoria e possibilidade de mudanças de dinâmica conforme equipamentos disponíveis.

Isso abre uma linha causal potencialmente mais relevante do que procurar padrões puramente numéricos no histórico, mas somente se forem obtidos metadados reais anteriores ao sorteio.

Variáveis desejáveis:

- identificador do globo;
- identificador do conjunto de bolas;
- massa e diâmetro medidos das bolas, se publicamente disponíveis ou legitimamente medidos;
- desgaste e manutenção;
- ordem de carregamento;
- local do sorteio;
- condições ambientais quando disponíveis;
- intervenções no equipamento;
- troca de equipamento ou conjunto de bolas;
- sequência temporal das extrações, quando registrada.

Sem esses metadados, o sistema deve registrar `BLOCKED_BY_METADATA`; não pode inferir causalidade física a partir do número sorteado.

Fontes oficiais: https://loterias.caixa.gov.br/Paginas/regras-sorteios.aspx

## 7. Aprendizado de máquina

### 7.1 Modelos de baixa variância primeiro

Antes de redes profundas:

- regressão regularizada;
- modelos lineares generalizados;
- árvores rasas/boosting com forte regularização, se dependências permitirem;
- modelos bayesianos hierárquicos;
- stacking prequential.

### 7.2 Modelos de sequência e rede

Somente como challengers isolados:

- HMM;
- reservoir computing;
- temporal convolution;
- transformers pequenos;
- graph neural networks sobre os 25 nós;
- modelos de energia neurais com cardinalidade fixa;
- neural conditional random fields ou equivalentes.

O histórico tem apenas alguns milhares de concursos, portanto capacidade excessiva é risco dominante. Modelos grandes precisam provar ganho contra modelos simples com nested walk-forward e penalização explícita de complexidade.

## 8. Descoberta de equações e teorias

A pesquisa poderá usar:

- symbolic regression;
- physics-informed symbolic regression;
- neuro-symbolic discovery;
- sparse identification of nonlinear dynamics quando a representação temporal satisfizer as premissas;
- genetic programming apenas como mecanismo de busca de expressões, nunca como evidência por si só.

Toda expressão descoberta é hipótese, não lei. Deve ser congelada antes da prova e comparada fora do intervalo em que foi descoberta.

Referências de método incluem trabalhos modernos de symbolic regression com restrições físicas e integração de conhecimento prévio.

## 9. Ensemble científico

Nenhum motor recebe peso porque teve um bom concurso isolado.

O meta-modelo deverá combinar distribuições conjuntas congeladas por:

- Bayesian model averaging, ou
- stacking baseado em log-score prequential.

Regras:

- pesos não usam o concurso alvo;
- soma de pesos = 1;
- pesos e janela são congelados antes da previsão;
- candidato sem densidade conjunta coerente não entra diretamente no ensemble;
- modelos altamente correlacionados não contam como evidência independente.

## 10. Busca global do cartão único

Depois que o ensemble produzir uma função `joint_score(card)`, o sistema deve pesquisar todo o universo de 3.268.760 cartões e retornar o maior score global.

Nenhum filtro de soma, paridade, moldura, linhas, colunas, números quentes/frios ou frequência histórica pode excluir um cartão apenas por tradição. Tais propriedades só influenciam o ranking se estiverem dentro de um modelo registrado e validado.

Para modelos aditivos, o MAP é exato pelos 15 maiores pesos. Para modelos com interações, usar enumeração nativa, branch-and-bound, branch-and-price, dynamic programming ou método exato equivalente com certificado de ótimo quando computacionalmente viável.

## 11. Métricas do P15

### Primária

`JointLogSkill = ln(C(25,15)) - JointLogLoss(model)`

Positivo significa que o modelo atribuiu ao resultado verdadeiro probabilidade maior que o uniforme.

### Secundárias

- rank do resultado verdadeiro entre os 3.268.760 estados;
- percentil do rank;
- probabilidade atribuída ao cartão MAP;
- gap de score entre top-1 e top-2/top-100;
- hits do cartão MAP;
- frequência de 11+, 12+, 13+, 14+, 15;
- Brier marginal;
- calibração;
- estabilidade por regime;
- informação adicionada por ablação de cada motor.

## 12. Validação

Todo candidato segue:

`descoberta -> registro -> treino -> seleção interna -> congelamento -> walk-forward protegido -> avaliação prospectiva -> replicação -> revisão independente`.

É proibido:

- recalibrar porque o último cartão fez poucos acertos;
- selecionar janela depois de ver o resultado alvo;
- testar centenas de regras e reportar somente a melhor;
- usar 15 pontos retrospectivos como prova suficiente;
- alterar previsão congelada;
- usar resultado futuro em feature engineering.

## 13. Hierarquia de evidência

### ESTABLISHED_METHOD

Método matemático/estatístico bem estabelecido, mas ainda sem evidência específica de vantagem na Lotofácil.

### DOMAIN_SIGNAL_UNDER_TEST

Há efeito retrospectivo ou prequential suficiente para justificar teste prospectivo.

### PROSPECTIVE_SIGNAL

O método melhora a métrica pré-registrada em dados futuros não usados no desenvolvimento.

### REPLICATED_PREDICTIVE_EVIDENCE

O efeito prospectivo é replicado, supera comparadores e passa revisão independente.

Somente a última classe pode alterar o rótulo científico de vantagem preditiva do produto.

## 14. Fronteiras que não entram como ciência preditiva

Não recebem peso por ausência de mecanismo mensurável e protocolo falsificável:

- numerologia;
- astrologia;
- sincronicidade não testável;
- alegações quânticas sem mecanismo físico medido ligando fenômenos microscópicos ao globo;
- padrões escolhidos depois de ver o resultado;
- qualquer vazamento de resultado futuro.

Esses itens podem ser discutidos como história de ideias, mas não entram no motor científico.

## 15. Referências iniciais

- CAIXA, Regras dos Sorteios: https://loterias.caixa.gov.br/Paginas/regras-sorteios.aspx
- Adams & MacKay, Bayesian Online Changepoint Detection, arXiv:0710.3742.
- Bandt & Pompe, Permutation entropy: a natural complexity measure for time series, Physical Review Letters 88, 174102 (2002).
- Castellana & Bialek, Inverse spin glass and related maximum entropy problems, Physical Review Letters 113, 117204 (2014).
- Cocco & Monasson, Adaptive cluster expansion for inferring Boltzmann machines with noisy data, Physical Review Letters 106, 090601 (2011).
- Zaffran et al., Adaptive Conformal Predictions for Time Series, arXiv:2202.07282.
- Kirkley, Transfer entropy for finite data, Physical Review E 112, L052304 (2025).
- Reinbold et al., Robust learning from noisy, incomplete, high-dimensional experimental data via physically constrained symbolic regression, Nature Communications 12, 3219 (2021).

## 16. Estado inicial desta missão

- P15 joint baseline: IMPLEMENTED IN BRANCH.
- P15 conditional additive model: IMPLEMENTED IN BRANCH.
- Pairwise maximum entropy: PLANNED.
- Bayesian changepoint/regime: PLANNED.
- Information-theoretic discovery: RESEARCH.
- Physical metadata: BLOCKED_BY_METADATA.
- Deep/network models: RESEARCH_DATA_LIMITED.
- Automatic champion replacement: FORBIDDEN.
- Automatic wagering: FORBIDDEN.
- Predictive evidence: NOT_ESTABLISHED.
