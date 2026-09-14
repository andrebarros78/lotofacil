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
| `regime` | `STABLE / ALERT / INCONCLUSIVE` | detector e taxa de falso alarme calibrados |
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

A linha atual expõe somente um diagnóstico de deslocamento de frequência em corte fixo. Como ainda não há detector de regime com taxa de falso alarme calibrada, o estado permanece obrigatoriamente `INCONCLUSIVE`.

Resultados diagnósticos podem orientar uma futura hipótese, mas não podem ser convertidos em `STABLE` ou `ALERT` sem a calibração exigida.

### Evidência preditiva

A API SQLite só retorna `REPLICATED` quando há promoção formal persistida em `model_promotions`; experimentos retrospectivos isolados permanecem `NOT_ESTABLISHED`.

Na Operator Console, `operations/state` permite distinguir protocolo prospectivo em andamento como `UNDER_TEST`, mantendo separadamente `predictive_evidence=NOT_ESTABLISHED` até a promoção formal.

## Canais

A autoridade de cálculo é o módulo `sare_lotofacil.analysis.ris`.

- API: `GET /v1/ris`;
- Operator Console: ação `ris` / opção `ris-categorical`;
- prova automática: `SARE Operator Console Proof` executa o RIS sobre `operations/state` e verifica os guardrails.

Nenhum canal implementa uma fórmula paralela de RIS.
