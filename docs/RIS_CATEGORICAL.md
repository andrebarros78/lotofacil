# RIS categórico — contrato da linha 1.x

## Regra soberana

O RIS da linha 1.x é exclusivamente um **painel categórico de integridade por dimensão**.

São invariantes obrigatórios:

- `numeric_ris_enabled = false`;
- `score = null`;
- nenhuma média de p-valores, porcentagem de testes aprovados, ranking arbitrário ou transformação como `100 × p` pode substituir uma nota RIS;
- `COMPATIBLE` não significa prova de aleatoriedade;
- `ALERT` não significa vantagem preditiva;
- estado categórico não promove modelo nem altera sozinho a política de carteira.

Qualquer nota numérica futura exige um projeto científico separado, com construto, comportamento sob o nulo, sensibilidade, estabilidade e interpretação previamente validados.

## Dimensões canônicas

O schema `ris-categorical-v1` contém exatamente seis dimensões:

| Dimensão | Estados | Evidência mínima |
|---|---|---|
| `data_integrity` | `VERIFIED / LIMITED / INVALID` | integridade, snapshot, procedência e artefatos |
| `uniformity` | `COMPATIBLE / ALERT / INCONCLUSIVE` | família das 25 dezenas, efeito, p e Holm |
| `cooccurrence` | `COMPATIBLE / ALERT / INCONCLUSIVE` | família dos 300 pares, efeito, p e Holm |
| `temporal` | `COMPATIBLE / ALERT / INCONCLUSIVE` | lags 1,2,3,5,10, permutação de concursos completos, efeito e Holm |
| `regime` | `STABLE / ALERT / INCONCLUSIVE` | detector global, candidatos datados e falso alarme calibrado/validado |
| `predictive_evidence` | `NOT_ESTABLISHED / UNDER_TEST / REPLICATED` | protocolo prospectivo e estado de promoção |

## Métodos implementados

### Integridade dos dados

Na API baseada no SQLite reconstruído, `VERIFIED` exige `integrity_check=ok`, snapshot publicado e artefatos de fonte válidos por SHA-256. Divergência de integridade ou artefato produz `INVALID`; ausência de evidência suficiente produz `LIMITED`.

Na Operator Console GitHub-only, a integridade é derivada do estado canônico já auditado em `operations/state` e inclui os hashes do histórico persistido.

### Uniformidade

Cada uma das 25 frequências marginais é comparada ao valor de referência `0,6` por teste binomial bilateral exato. A família completa é corrigida por Holm a `alpha=0,05`.

`ALERT` significa ao menos uma rejeição após correção. `COMPATIBLE` significa ausência de rejeição ajustada nessa família e não constitui prova de aleatoriedade.

### Coocorrência

Os 300 pares são comparados à probabilidade teórica `0,35`. A família completa usa correção de Holm.

Um par em `ALERT` não recebe peso preditivo automaticamente.

### Temporal

O teste inicial usa os lags predefinidos `1, 2, 3, 5, 10` e estatística de repetição média entre concursos separados por cada lag.

A calibração permuta **concursos completos**, preservando a composição interna de cada resultado e destruindo a ordem temporal. Os p-valores dos lags são corrigidos por Holm. A execução é determinística para seed e número de replicações fixos.

### Regime

O detector de regime da 1.1.3 é um **scan global retrospectivo de mudança marginal**. Os pontos candidatos são predefinidos por segmento mínimo e stride; em cada ponto mede-se o maior deslocamento padronizado entre as 25 frequências antes/depois. A estatística final é o máximo conjunto sobre todas as dezenas e todos os candidatos.

O limiar não vem de testes independentes. Ele é calibrado por séries `NULO_UNIFORME` completas. Uma segunda amostra nula, independente da calibração, estima a taxa de falso alarme e seu IC95% de Wilson.

Parâmetros canônicos iniciais:

- `alpha = 0,05`;
- segmento mínimo = 100 concursos;
- stride dos candidatos = 10 concursos;
- 199 replicações para calibração;
- 199 replicações independentes para validação;
- seed = `20260914`.

Estados:

- `STABLE`: calibração compatível com o alvo e nenhuma mudança ultrapassa o limiar global;
- `ALERT`: calibração compatível, máximo observado acima do limiar e p Monte Carlo no nível predefinido;
- `INCONCLUSIVE`: amostra insuficiente ou validação nula não confirma a taxa de falso alarme alvo.

Todos os candidatos avaliados são registrados com índice e, quando disponíveis, concurso/data. O modo é sempre `RETROSPECTIVE_DISCOVERY`: um `ALERT` retrospectivo **não** é descrito como alerta emitido em tempo real.

O teste T16 valida falso alarme em nulo sintético; o T19 usa `ALTERNATIVA_CONTROLADA` com mudança marginal conhecida para medir sensibilidade e localização. Nenhum alerta atribui causa física sem metadados.

### Evidência preditiva

A API SQLite só retorna `REPLICATED` quando há promoção formal persistida em `model_promotions`; experimentos retrospectivos isolados permanecem `NOT_ESTABLISHED`.

Na Operator Console, `operations/state` permite distinguir protocolo prospectivo em andamento como `UNDER_TEST`, mantendo separadamente `predictive_evidence=NOT_ESTABLISHED` até a promoção formal.

## Canais

A autoridade de cálculo é o módulo `sare_lotofacil.analysis.ris`.

- API: `GET /v1/ris`;
- Operator Console: ação `ris` / opção `ris-categorical`;
- prova automática: `SARE Operator Console Proof` executa o RIS sobre `operations/state` e verifica os guardrails e a calibração de regime.

Nenhum canal implementa uma fórmula paralela de RIS.
