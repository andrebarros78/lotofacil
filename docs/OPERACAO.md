# SARE Operational 1.1 — Operação local

## Princípios

- A API escuta em loopback por padrão e o CLI recusa binding externo nesta versão.
- Escritas ficam desabilitadas quando `SARE_WRITE_TOKEN` não está definido.
- Toda escrita HTTP exige `X-SARE-Token` e `Idempotency-Key`.
- Carteiras são combinatórias e exibem `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA` enquanto `predictive_evidence` não for `REPLICATED`.
- RIS numérico permanece desabilitado; `/v1/ris` devolve somente painel categórico.

## Instalação

```bash
python -m venv .venv
.venv/bin/python -m pip install .
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
```

## Inicialização e diagnóstico

```bash
python -m sare_lotofacil doctor
python -m sare_lotofacil init-db --path data/sare.db
```

O diagnóstico matemático deve terminar com `MATHEMATICAL_CHECKS_PASS`.

## API local

Defina um token de escrita e inicie em loopback:

```bash
export SARE_WRITE_TOKEN='troque-por-um-segredo-local'
python -m sare_lotofacil serve --db data/sare.db
```

PowerShell:

```powershell
$env:SARE_WRITE_TOKEN='troque-por-um-segredo-local'
python -m sare_lotofacil serve --db data/sare.db
```

Sem token, a API continua consultável, mas operações de escrita retornam `WRITE_DISABLED`.

Endpoints operacionais principais:

- `GET /health/live`
- `GET /health/ready`
- `GET /v1/snapshots`
- `POST /v1/analyses`
- `GET /v1/runs/{run_id}`
- `POST /v1/portfolios`
- `GET /v1/portfolios/{portfolio_id}`
- `POST /v1/evaluations`
- `GET /v1/ris`

## Backup e restauração

```bash
python -m sare_lotofacil backup-db --db data/sare.db --out backups/sare.db
python -m sare_lotofacil restore-db --backup backups/sare.db --out restore/sare.db
```

O backup usa a API consistente do SQLite e só é aceito se `PRAGMA integrity_check` retornar `ok`. A restauração exige destino inexistente e repete a verificação de integridade.

## Recuperação

Após reinício, use o mesmo banco. `run_id`, `portfolio_id`, snapshots e auditorias permanecem persistidos. Após restauração, a mesma identidade deve ser recuperada do banco restaurado.

## Segurança e limites

- nenhuma URL arbitrária é aceita pela API;
- o servidor local recusa bind externo no CLI;
- body HTTP padrão limitado a 65.536 bytes;
- SQL é parametrizado;
- token não é persistido no banco nem no log da aplicação;
- idempotência detecta reutilização da mesma chave com payload diferente e retorna conflito;
- CORS permissivo não é habilitado;
- exposição remota, HTTPS e autenticação multiusuário estão fora do Operational 1.1 local.

## Evidência científica

Uma execução concluída não significa vantagem. O Core mantém `predictive_evidence=NOT_ESTABLISHED` nas análises retrospectivas atuais. M0 (`p=0,6`) tem Brier exato `0,24`; candidatos M1/M2 reportam Brier, delta contra M0, intervalo de 95%, amostra e `delta_min`.
