# SARE Lotofácil 1.1.10 — Fechamento técnico, funcional, operacional e de segurança

## Autoridade canônica

O SARE Lotofácil permanece **GitHub-only**. A autoridade de código é `main`; o estado operacional persistente é `operations/state`; GitHub Actions é o executor canônico; GitHub Artifacts contém as evidências reconstruíveis; Git history fornece proveniência.

A release 1.1.10 só pode ser selada quando o SHA final de `main` tiver passado pelos gates pós-merge e o alias imutável de escopo `release/v1.1.10` apontar para esse mesmo SHA.

## Estado reconciliado

Baseline anterior ao fechamento:

- `main`: `7e961d5ce8bcece897991497561084ec58c613d9`;
- protocolo Nested Walk-Forward temporal incorporado e validado sobre histórico real;
- `operations/state` separado de `main` e protegido por ruleset nativo;
- nenhum pull request aberto no início deste ciclo de fechamento;
- versão declarada antes da reconciliação: `1.1.9`.

A reconciliação 1.1.10 corrige a divergência entre a capacidade incorporada e a identidade de release, alinhando:

- `pyproject.toml` para `1.1.10`;
- `sare_lotofacil.__version__` para `1.1.10`;
- `Release Proof` para exigir `1.1.10` no wheel instalado, módulo e API;
- README para documentar o Nested Walk-Forward temporal;
- `Max Capacity Audit` para disparar também quando `tests/test_calibration_rounds.py` ou `tests/test_nested_walk_forward.py` forem alterados isoladamente.

## Escopo científico consolidado

O protocolo Nested Walk-Forward temporal da 1.1.10 preserva:

- 8 folds externos temporais não sobrepostos;
- seleção interna walk-forward de M1/M2 em cada fold;
- lockbox final de 15% excluído de toda seleção;
- Brier, ΔBrier, MAE, RMSE, Log Loss, ΔLogLoss e ECE-10;
- intervalo de confiança por moving-block bootstrap;
- fingerprint determinístico da seleção pré-lockbox;
- prova automatizada de isolamento do lockbox;
- ausência de promoção automática de modelo.

No histórico real de 3.779 concursos usado na prova canônica anterior, M1 `lambda=400` foi selecionado em 8/8 folds externos e na seleção final pré-lockbox. O ganho permaneceu pequeno e os intervalos de confiança atravessaram zero; portanto a conclusão científica continua obrigatoriamente:

`predictive_evidence=NOT_ESTABLISHED`

`EVIDENCIA_PREDITIVA_INSUFICIENTE`

A release 1.1.10 fecha engenharia e governança do protocolo; **não declara vantagem preditiva**.

## Fechamento técnico

Condição obrigatória:

- CI Python 3.12: `success`;
- CI Python 3.13: `success`;
- `doctor`: PASS dentro do CI;
- ambiente instalado sob `requirements.lock.txt`;
- Max Capacity Audit: `success` sobre histórico real reconciliado;
- Nested Walk-Forward: `status=PASS`, `leakage_safe=true` e lockbox fora da seleção;
- Release Proof: wheel limpo, versão `1.1.10` e origem em `site-packages`;
- regressão integral sem falha observada.

## Fechamento funcional

O Release Proof deve comprovar no wheel instalado:

- criação da API com versão `1.1.10`;
- rotas obrigatórias `/health/live`, `/health/ready`, `/v1/analyses`, `/v1/portfolios`, `/v1/evaluations`, `/v1/evaluations/revisions` e `/v1/ris`;
- doctor matemático;
- backup/restore de persistência;
- RIS categórico sem score numérico;
- integridade de regime, alternativas controladas, backtest, risco/reprodutibilidade/cobertura conjunta, economia de carteira e PRIMARY_CARD;
- jornada Operational 1.1.

## Fechamento operacional

Condição obrigatória:

- `Real History Check`: `success`;
- `GitHub Operational Cycle`: `success`;
- `committed-state-audit`: `success`;
- `economic-state-proof`: `success`;
- `SARE Operator Console Proof`: `success`;
- `operations/state` protegido contra deleção e non-fast-forward;
- nenhuma dependência de PC local, VPS ou processo residente para operação canônica.

## Fechamento de segurança e governança

Rulesets nativos observados como ativos:

- `SARE Main Protection` sobre `refs/heads/main`;
- `SARE Operations State Protection` sobre `refs/heads/operations/state`.

A `main` exige:

- PR;
- merge por squash;
- resolução de threads;
- status checks `test (3.12)` e `test (3.13)` em modo estrito;
- bloqueio de deleção;
- bloqueio de non-fast-forward;
- sem ator de bypass.

A política GitHub-only continua exigindo Actions pinados, permissões mínimas e writer controlado.

## Baseline limpa

Para considerar o fechamento comprovado, após o merge final devem ser simultaneamente verdadeiros:

1. `main` aponta para o SHA de fechamento 1.1.10;
2. não existe PR aberta pertencente a este escopo;
3. todos os checks aplicáveis observados para o SHA final terminam em `success`;
4. `Release Proof` valida a versão `1.1.10` instalada;
5. `Max Capacity Audit` publica artefato do mesmo SHA;
6. o alias `release/v1.1.10` aponta exatamente para o mesmo SHA de `main`;
7. não há commit adicional necessário para completar este escopo.

## Selagem de escopo

Escopo selado da 1.1.10:

- Nested Walk-Forward temporal;
- calibração e métricas de erro já incorporadas;
- isolamento de lockbox;
- consistência de versionamento;
- cobertura de gatilho dos testes científicos novos;
- fechamento técnico/funcional/operacional/segurança.

Fora do escopo e explicitamente não promovido:

- qualquer alegação de previsão superior ao acaso;
- retuning usando o lockbox já observado;
- troca automática do modelo operacional por M1 `lambda=400`;
- nova família de modelo;
- alteração das regras econômicas ou de premiação além do que já está versionado.

Qualquer evolução posterior deve abrir novo escopo, novo branch/PR, novos gates e nova evidência. O estado 1.1.10 não pode ser reescrito retroativamente.
