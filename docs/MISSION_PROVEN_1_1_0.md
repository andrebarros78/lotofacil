# SARE Lotofácil 1.1.0 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A release não depende de PC local, VPS, servidor externo, processo residente ou banco local permanente para operação, continuidade, recuperação ou aceitação.

A identidade canônica e imutável da release é o **SHA Git completo de `main`**. O alias humano `release/v1.1.0` deve apontar exatamente para esse mesmo SHA no encerramento da prova da release.

O estado operacional persistente e auditável vive em `operations/state`. GitHub Actions é o executor canônico; GitHub Artifacts contém bancos reconstruídos, relatórios e evidências transitórias; o histórico Git fornece proveniência temporal.

## Regra de MISSION_PROVEN

A release só pode ser declarada `MISSION_PROVEN` quando as provas abaixo estiverem materialmente ligadas ao mesmo SHA canônico de `main`, com artefatos e estado operacional verificáveis. Nenhuma simples existência de arquivo, workflow ou teste encerra a missão isoladamente.

Cadeia mínima exigida:

`commit -> workflow run -> artifact -> provenance -> operations/state -> auditoria independente`

## Matriz de provas

| Prova | Implementação e testes | Condição |
|---|---|---|
| P-DADOS | `scripts/verify_third_party_history.py`, `tests/test_ingestion.py`, `tests/test_repository.py`, `tests/test_evidence.py`, workflow `Real History Check` | histórico validado, checkpoints oficiais, snapshot reproduzível, integridade SQLite reconstruída e hashes de artefatos válidos |
| P-MATEMATICA | `doctor`, `tests/test_combinatorics.py`, `tests/test_baseline.py` | `C(25,15)=3.268.760`, E=9, Var=1,5, M0 p=0,6 e Brier=0,24 |
| P-CIENCIA | `tests/test_protocol.py`, `tests/test_scientific_journey.py`, `tests/test_experiments.py` | protocolo congelado por hash, walk-forward, conclusão inconclusiva aceita e promoção bloqueada sem evidência prospectiva replicada |
| P-FUNCAO | `tests/test_api.py`, `tests/test_hardening.py`, `scripts/prove_operational_release.py` | jornada dados → hipótese → experimento → conclusão → carteira → avaliação executável |
| P-CARTEIRA | `tests/test_portfolios.py`, `tests/test_end_to_end.py`, `tests/test_hardening.py`, `SARE Operator Console Proof` | cartões válidos, auditáveis e com etiqueta obrigatória de ausência de vantagem comprovada |
| P-PERSISTENCIA | `GitHub Operational Cycle`, `operations/state`, `tests/test_repository.py`, `tests/test_persistence.py` | estado textual versionado, reconstrução determinística e continuidade entre execuções independentes do GitHub |
| P-RECUPERACAO | `tests/test_backup.py`, `tests/test_end_to_end.py`, `Release Proof`, reconstrução do SQLite a partir de `operations/state` | recuperação com `integrity_check=ok` e continuidade da jornada sem depender de máquina externa |
| P-SEGURANCA | `scripts/verify_github_governance.py`, `tests/test_api.py`, `tests/test_hardening.py` | Actions pinados por SHA, permissões mínimas, writer operacional único, autenticação/limites de entrada e ausência de runner `self-hosted` canônico |
| P-FILA | `tests/test_jobs.py`, `tests/test_hardening.py` | lease, fencing token, checkpoint, retomada, cancelamento e falha sem falso sucesso |
| P-EVIDENCIA | `tests/test_evidence.py`, `verify-evidence`, GitHub Artifacts | SHA-256 reprodutível, adulteração detectada e evidência vinculada ao workflow/commit |
| P-RELEASE | `tests/test_version.py`, workflow `Release Proof` | wheel 1.1.0 instalado em ambiente limpo, módulo em `site-packages`, `MATHEMATICAL_CHECKS_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS` |
| P-REGRESSAO | workflow `CI` | suíte completa aprovada em Python 3.12 e 3.13, incluindo governance gate e smoke da console |
| P-OPERACAO | `GitHub Operational Cycle`, `committed-state-audit`, `docs/GITHUB_OPERATIONS.md`, `SARE Operator Console` | execução, persistência, consulta e auditoria inteiramente GitHub-native |
| P-CONSOLE | `SARE Operator Console Proof` | `status`, `audit`, `analyze`, `portfolio` e `export` executados sobre `operations/state` e publicados como Artifact read-only |

## Gates finais do mesmo SHA

O SHA canônico da release precisa apresentar simultaneamente:

- `CI`: `completed/success` em Python 3.12 e 3.13;
- `Real History Check`: `completed/success`;
- `Release Proof`: `completed/success`;
- `GitHub Operational Cycle`: job `cycle` em `completed/success`;
- `GitHub Operational Cycle`: job `committed-state-audit` em `completed/success`;
- `SARE Operator Console Proof`: `completed/success` para todas as operações read-only;
- wheel e runtime declarando versão `1.1.0`;
- relatório histórico com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `operations/state` validado depois da persistência pelo auditor independente;
- `scripts/verify_github_governance.py` retornando PASS;
- branch `main` e alias `release/v1.1.0` resolvendo para exatamente o mesmo SHA comprovado.

A movimentação de `release/v1.1.0` só ocorre **depois** de todos os workflows obrigatórios do SHA de `main` terminarem com sucesso.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` é um resultado científico válido. A release não pode transformar ausência de evidência em alegação de capacidade preditiva.

Enquanto `predictive_evidence` não for formalmente promovida após as duas coortes prospectivas e revisão independente, as carteiras permanecem combinatórias e explicitamente rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

A conclusão prospectiva não é requisito para `MISSION_PROVEN` de engenharia da release; é uma investigação científica contínua cujo resultado pode legitimamente permanecer `NOT_ESTABLISHED`.

## Estado de hardening soberano

A governança lógica GitHub-only é comprovada pelo CI e por `verify_github_governance.py`.

Os **Rulesets nativos do GitHub** para `main` e `operations/state` são uma camada administrativa adicional de defesa. Enquanto não estiverem configurados, o estado deve ser registrado como:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

A ausência temporária dessa camada não autoriza escrita externa, não altera a autoridade de `operations/state` e não pode ser ocultada em relatórios de governança.

Quando os Rulesets nativos também forem ativados e verificados, o estado pode avançar separadamente para:

`SOVEREIGN_HARDENING_COMPLETE`

## Limitações 1.1.0

- o SQLite existe apenas como artefato reconstruível/transitório nos runners e provas; não é a memória permanente do produto;
- o histórico principal é corroborado por checkpoints oficiais e recebe patches provenientes da CAIXA; não é apresentado como reconciliação integral linha a linha de uma exportação oficial única;
- RIS numérico continua desabilitado;
- não existe vantagem preditiva comprovada no estado científico atual.

Somente após observação material de todos os gates finais no mesmo SHA canônico e alinhamento de `release/v1.1.0` o estado técnico da release pode ser registrado como `MISSION_PROVEN`.
