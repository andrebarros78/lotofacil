# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Release

**SARE Core 1.0 + SARE Operational 1.1 — versão 1.1.0.**

O sistema prioriza integridade dos dados, matemática exata, reprodutibilidade, auditoria e recuperação antes de qualquer alegação preditiva.

**Não há vantagem preditiva comprovada.** O histórico real validado até o concurso 3779 produz `EVIDENCIA_PREDITIVA_INSUFICIENTE`; carteiras permanecem combinatórias e são rotuladas explicitamente dessa forma.

## Capacidades

- invariantes oficiais: 25 dezenas e sorteio de 15;
- `C(25,15) = 3.268.760`, distribuição hipergeométrica exata e máscaras de 25 bits;
- M0 uniforme `p_i = 0,6`, Brier `0,24`;
- M1 frequência regularizada e M2 média exponencial em walk-forward, com `ΔBrier` e IC95%;
- ingestão validada, revisões imutáveis, artefatos de fonte e snapshots SQLite;
- fonte oficial CAIXA e histórico de terceiro corroborado por checkpoints oficiais;
- protocolo científico congelado por hash, hipóteses e experimentos auditáveis;
- promoção de modelo bloqueada enquanto a evidência não for `REPLICATED`;
- carteiras uniformes com etiqueta obrigatória de ausência de vantagem comprovada;
- API FastAPI local com autenticação de escrita, idempotência e limite de body;
- fila persistente com lease, fencing token, checkpoint, cancelamento e retomada;
- verificação SHA-256 de evidências persistidas;
- backup/restore SQLite com `integrity_check`;
- UI mínima de carteira em 8+7 com dezenas de dois dígitos;
- CI Python 3.12/3.13, Real History Check e Release Proof a partir do wheel instalado.

## Desenvolvimento

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
python -m pytest
python -m sare_lotofacil doctor
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m sare_lotofacil doctor
```

## Banco, worker e API

```bash
python -m sare_lotofacil init-db --path data/sare.db
python -m sare_lotofacil worker-once --db data/sare.db --worker-id worker-01
python -m sare_lotofacil verify-evidence --db data/sare.db
export SARE_WRITE_TOKEN='segredo-local'
python -m sare_lotofacil serve --db data/sare.db
```

O servidor recusa binding externo nesta linha e opera em loopback por padrão.

## Recuperação

```bash
python -m sare_lotofacil backup-db --db data/sare.db --out backups/sare.db
python -m sare_lotofacil restore-db --backup backups/sare.db --out restore/sare.db
```

## Provas e documentação

- operação: `docs/OPERACAO.md`;
- matriz de comprovação: `docs/MISSION_PROVEN.md`;
- identidade da especificação-fonte: `docs/SOURCE_SPEC.md`;
- testes automatizados: `tests/`;
- prova do wheel instalado: `scripts/prove_operational_release.py`;
- workflows: `.github/workflows/ci.yml`, `real-history-check.yml` e `release-proof.yml`.
