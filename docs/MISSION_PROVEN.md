# SARE Lotofácil 1.1.0 — Evidências de MISSION_PROVEN

A release é considerada `MISSION_PROVEN` somente quando os três workflows obrigatórios terminarem com sucesso no mesmo commit de release.

A identidade canônica e imutável da release é o **SHA Git completo**. O alias humano `release/v1.1.0` deve apontar exatamente para esse SHA no encerramento da missão.

## Matriz

| Prova | Implementação e testes | Condição |
|---|---|---|
| P-DADOS | `scripts/verify_third_party_history.py`, `tests/test_ingestion.py`, `tests/test_repository.py`, `tests/test_evidence.py` | histórico validado, checkpoints oficiais, snapshot reproduzível, integridade SQLite e hashes de artefatos válidos |
| P-MATEMATICA | `doctor`, `tests/test_combinatorics.py`, `tests/test_baseline.py` | `C(25,15)=3.268.760`, E=9, Var=1,5, M0 p=0,6 e Brier=0,24 |
| P-CIENCIA | `tests/test_protocol.py`, `tests/test_scientific_journey.py`, `tests/test_experiments.py` | protocolo congelado por hash, walk-forward, conclusão inconclusiva aceita e promoção bloqueada sem evidência replicada |
| P-FUNCAO | `tests/test_api.py`, `tests/test_hardening.py`, `scripts/prove_operational_release.py` | jornada dados → hipótese → experimento → conclusão → carteira → avaliação executável |
| P-CARTEIRA | `tests/test_portfolios.py`, `tests/test_end_to_end.py`, `tests/test_hardening.py` | cartões válidos, persistência, auditoria e etiqueta de ausência de vantagem comprovada |
| P-PERSISTENCIA | `tests/test_repository.py`, `tests/test_persistence.py`, `tests/test_api.py`, `tests/test_jobs.py` | estado recuperável após nova conexão/processo |
| P-RECUPERACAO | `tests/test_backup.py`, `tests/test_end_to_end.py`, workflow `Release Proof` | backup/restauração com `integrity_check=ok` e continuidade da jornada |
| P-SEGURANCA | `tests/test_api.py`, `tests/test_hardening.py` | autenticação de escrita, limites de entrada, fonte de ingestão restrita, idempotência e loopback |
| P-FILA | `tests/test_jobs.py`, `tests/test_hardening.py` | lease, fencing token, checkpoint, retomada, cancelamento e falha sem falso sucesso |
| P-EVIDENCIA | `tests/test_evidence.py`, endpoint `/v1/evidence/integrity`, comando `verify-evidence` | SHA-256 reprodutível e adulteração detectada |
| P-RELEASE | `tests/test_version.py`, workflow `Release Proof` | wheel 1.1.0 instalado em ambiente limpo, módulo em `site-packages`, `MATHEMATICAL_CHECKS_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS` |
| P-REGRESSAO | workflow `CI` | suíte completa aprovada em Python 3.12 e 3.13 |
| P-OPERACAO | `docs/OPERACAO.md`, health endpoints e trilha de auditoria | operação e limitações documentadas |

## Gates finais

O SHA da release precisa apresentar simultaneamente:

- `CI`: `completed/success`;
- `Real History Check`: `completed/success`;
- `Release Proof`: `completed/success`;
- wheel e runtime declarando versão `1.1.0`;
- relatório histórico com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- branch `main` e alias `release/v1.1.0` resolvendo para o mesmo SHA de release.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` é um resultado válido. A release não pode transformar ausência de evidência em alegação de capacidade preditiva. Enquanto `predictive_evidence` não for `REPLICATED`, as carteiras permanecem combinatórias e explicitamente rotuladas como sem vantagem preditiva comprovada.

## Limitações da 1.1.0

A release é local e usa SQLite. O histórico principal de terceiro é corroborado por checkpoints oficiais e recebe apenas patches limitados provenientes da CAIXA; não é apresentado como reconciliação integral linha a linha de uma exportação oficial única. RIS numérico continua desabilitado.

Quando todos os gates forem observados no SHA canônico e no alias de release, o estado técnico desta release é `MISSION_PROVEN`.
