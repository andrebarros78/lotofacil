# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Estado

Esta baseline implementa o início do **SARE Core 1.0**. O objetivo imediato é provar dados, matemática e reprodutibilidade antes de qualquer alegação preditiva ou camada operacional.

**Não há vantagem preditiva comprovada.** Geração de apostas, compra automática e promessa de retorno não fazem parte desta baseline.

## O que já existe

- invariantes oficiais do domínio: 25 dezenas, sorteio de 15;
- espaço combinatório exato `C(25,15) = 3.268.760`;
- distribuição hipergeométrica exata de acertos de um cartão simples;
- representação reversível de cartões por máscara de 25 bits;
- baseline uniforme `p_i = 0,6` e Brier de referência `0,24`;
- validação estrutural de concursos;
- schema SQLite mínimo para revisões, snapshots e execuções;
- CLI para diagnóstico e inicialização do banco;
- testes automatizados dos invariantes implementados.

## Instalação para desenvolvimento

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

No Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Testes

```bash
python -m pytest
```

## Diagnóstico matemático

```bash
python -m sare_lotofacil doctor
```

Resultado esperado inclui:

```text
MATHEMATICAL_CHECKS_PASS
```

## Banco local

```bash
python -m sare_lotofacil init-db --path data/sare.db
```

O diretório de dados deve permanecer fora de releases empacotadas em produção.

## Especificação

A especificação conceitual e executiva vigente é `SARE_LOTOFACIL_1_1_PROJETO_CONCEITUAL_EXECUTIVO.md`, utilizada como baseline desta implementação.
