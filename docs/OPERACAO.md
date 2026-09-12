# SARE Operational 1.1 — Operação local

Release operacional: **1.1.0**.

## Princípios

- API em loopback; o CLI recusa binding externo nesta linha.
- Escritas desabilitadas quando `SARE_WRITE_TOKEN` não está definido.
- Escritas HTTP exigem `X-SARE-Token` e `Idempotency-Key`.
- Carteiras são combinatórias e exibem `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA` enquanto `predictive_evidence != REPLICATED`.
- RIS numérico permanece desabilitado.
- Execução técnica concluída não equivale a vantagem preditiva.

## Instalação

```bash
python -m venv .venv
.venv/bin/python -m pip install .
python -m sare_lotofacil doctor
python -m sare_lotofacil init-db --path data/sare.db
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m sare_lotofacil doctor
.\.venv\Scripts\python.exe -m sare_lotofacil init-db --path data\sare.db
```

`doctor` deve terminar com `MATHEMATICAL_CHECKS_PASS`.

## API local

```bash
export SARE_WRITE_TOKEN='troque-por-um-segredo-local'
python -m sare_lotofacil serve --db data/sare.db
```

PowerShell:

```powershell
$env:SARE_WRITE_TOKEN='troque-por-um-segredo-local'
python -m sare_lotofacil serve --db data\sare.db
```

Principais endpoints:

- `GET /health/live`, `GET /health/ready`
- `GET /v1/contests`, `GET /v1/contests/{contest_id}`
- `POST /v1/ingestions`, `POST /v1/ingestions/caixa`, `GET /v1/ingestions/{ingestion_id}`
- `GET/POST /v1/snapshots`
- `GET/POST /v1/hypotheses`
- `POST /v1/experiments`, `GET /v1/experiments/{experiment_id}`
- `POST /v1/promotions`, `POST /v1/models/{model_name}/promotions`
- `POST /v1/analyses`, `GET /v1/runs/{run_id}`
- `POST /v1/portfolios`, `GET /v1/portfolios/{portfolio_id}`
- `GET /v1/portfolios/{portfolio_id}/export`
- `POST /v1/evaluations`
- `POST /v1/jobs`, `GET /v1/jobs/{job_id}`, `POST /v1/jobs/{job_id}/cancel`
- `GET /v1/evidence/integrity`
- `GET /v1/ris`
- `GET /ui/portfolios/{portfolio_id}`

## Fila persistente e recuperação

O banco mantém jobs com estados `QUEUED`, `LEASED`, `COMPLETED`, `FAILED` e `CANCELLED`. O lease usa `lease_token` monotônico como fencing token; um worker antigo não pode publicar resultado depois que seu lease é substituído.

Execução de um trabalho:

```bash
python -m sare_lotofacil worker-once --db data/sare.db --worker-id worker-01 --lease-seconds 30
```

Checkpoint e estado ficam no SQLite. Um trabalho expirado pode ser retomado por outro worker; os testes de regressão verificam ausência de duplicação do resultado de domínio.

## Integridade de evidências

```bash
python -m sare_lotofacil verify-evidence --db data/sare.db
```

Artefatos de fonte são re-hashados a partir dos bytes persistidos. Qualquer divergência entre SHA-256 esperado e observado faz a verificação falhar.

## Backup e restauração

```bash
python -m sare_lotofacil backup-db --db data/sare.db --out backups/sare.db
python -m sare_lotofacil restore-db --backup backups/sare.db --out restore/sare.db
```

Backup e restore só são aceitos quando `PRAGMA integrity_check` retorna `ok`. A restauração exige destino inexistente. Hipóteses, experimentos, carteiras e jobs são comprovados novamente no workflow `Release Proof` após restauração.

## Segurança e limites

- URL arbitrária não é aceita pela ingestão; a fonte operacional configurada é CAIXA.
- servidor local recusa bind externo;
- body HTTP padrão limitado a 65.536 bytes;
- SQL parametrizado;
- token não é persistido no banco;
- idempotência detecta reutilização da mesma chave com payload diferente;
- concorrência com a mesma chave idempotente resulta em um único trabalho lógico;
- CORS permissivo não é habilitado;
- falha de persistência simulada como `disk full` não pode produzir estado `COMPLETED`.

## Evidência científica

M0 usa `p=0,6` e Brier exato `0,24`. M1/M2 são avaliados em walk-forward e reportam `ΔBrier`, IC95%, amostra e `delta_min`. Hipóteses são congeladas por hash antes da execução. Promoção para uso preditivo exige `predictive_evidence=REPLICATED`.

O Real History Check atual conclui `EVIDENCIA_PREDITIVA_INSUFICIENTE`; portanto nenhuma carteira desta release recebe alegação de vantagem preditiva.

## Prova de release

A release só é aceita quando, no mesmo commit:

1. `CI` passa em Python 3.12 e 3.13;
2. `Real History Check` passa e publica o relatório/banco de evidência;
3. `Release Proof` constrói o wheel, instala em ambiente limpo, comprova origem em `site-packages`, executa a jornada operacional e retorna `OPERATIONAL_RELEASE_PROOF_PASS`.

A matriz completa está em `docs/MISSION_PROVEN.md`.
