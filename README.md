# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Estado

A linha atual implementa o **SARE Core 1.0** e a interface **SARE Operational 1.1 local**. O sistema prioriza dados, matemática, reprodutibilidade e auditoria antes de qualquer alegação preditiva.

**Não há vantagem preditiva comprovada.** Carteiras operam como cobertura combinatória e são rotuladas explicitamente dessa forma.

## Capacidades implementadas

- invariantes oficiais do domínio: 25 dezenas e sorteio de 15;
- espaço combinatório exato `C(25,15) = 3.268.760`;
- distribuição hipergeométrica exata e máscaras de 25 bits;
- M0 uniforme `p_i = 0,6`, Brier `0,24`;
- M1 frequência regularizada e M2 média exponencial em walk-forward;
- Brier do candidato, `ΔBrier`, intervalo de 95%, amostra e `delta_min`;
- ingestão/validação, revisões, artefatos de fonte e snapshots SQLite;
- fonte CAIXA e corroborador de histórico de terceiro por checkpoints oficiais;
- motores de uniformidade, pares e repetição temporal;
- simulador nulo de subconjuntos uniformes 15 de 25;
- carteiras uniformes com etiqueta obrigatória de ausência de vantagem comprovada;
- auditoria de carteira;
- API FastAPI local com autenticação de escrita, idempotência e limite de body;
- persistência de análises, carteiras, avaliações e eventos de auditoria;
- backup/restore SQLite com `integrity_check`;
- CI em Python 3.12/3.13, prova de histórico real e workflow de clean install/release.

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

## Banco e API

```bash
python -m sare_lotofacil init-db --path data/sare.db
export SARE_WRITE_TOKEN='segredo-local'
python -m sare_lotofacil serve --db data/sare.db
```

A API local usa `127.0.0.1` por padrão e o CLI recusa binding externo nesta versão.

## Recuperação

```bash
python -m sare_lotofacil backup-db --db data/sare.db --out backups/sare.db
python -m sare_lotofacil restore-db --backup backups/sare.db --out restore/sare.db
```

## Documentação

- especificação: `docs/SARE_LOTOFACIL_1_1_PROJETO_CONCEITUAL_EXECUTIVO.md`;
- operação: `docs/OPERACAO.md`.
