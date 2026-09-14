# SARE Operational 1.1 — Operação GitHub-only

Release operacional: **1.1.0**.

## Autoridade operacional

O SARE Lotofácil é operado exclusivamente no GitHub.

Não existe requisito operacional de PC local, VPS, servidor externo, banco residente ou processo de longa duração fora do GitHub. Qualquer execução fora do GitHub é não canônica e serve apenas para desenvolvimento ou diagnóstico.

A cadeia operacional aceita é:

`commit GitHub -> GitHub Actions -> artifact -> provenance -> operations/state -> auditoria independente`

Somente essa cadeia pode alterar estado operacional, produzir evidência oficial, promover readiness ou participar de `MISSION_PROVEN`.

## Componentes canônicos

- `main`: código, testes, protocolos, políticas e workflows aprovados.
- `operations/state`: memória operacional textual, persistente, versionada e auditável.
- GitHub Actions: executor operacional e científico.
- GitHub Artifacts: SQLite reconstruído, relatórios, manifests e evidências de cada execução.
- Git history: trilha de proveniência e marca temporal.
- `docs/GITHUB_OPERATIONS.md`: contrato detalhado da operação integral no GitHub.

## Princípios científicos preservados

- carteiras permanecem combinatórias enquanto `predictive_evidence != REPLICATED`;
- toda carteira aplicável exibe `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`;
- RIS numérico permanece desabilitado;
- execução técnica concluída não equivale a vantagem preditiva;
- M0 usa `p=0,6` e Brier exato `0,24`;
- M1/M2 são avaliados em walk-forward com `ΔBrier`, IC95%, amostra e efeito mínimo;
- nenhuma promoção preditiva é automática.

## Estado operacional e banco transitório

SQLite pode ser usado durante uma execução do GitHub Actions, mas não é a memória permanente do produto.

O estado persistente é textual e versionável no branch `operations/state`. Cada ciclo reconstrói o SQLite em runner efêmero, exige `PRAGMA integrity_check = ok`, produz os relatórios necessários e publica o banco apenas como artefato de prova.

O encerramento do runner não pode causar perda de estado canônico, porque a continuidade deriva de `operations/state` e do histórico Git.

## GitHub Operational Cycle

O workflow operacional deve:

1. fazer checkout do código aprovado;
2. fazer checkout de `operations/state`;
3. instalar o pacote em runner efêmero;
4. executar suíte, doctor e gates prévios;
5. reconstruir o banco transitório;
6. obter somente os dados externos previstos pelo contrato;
7. atualizar histórico, ledger e previsão prospectiva sem vazamento temporal;
8. recalcular hashes e métricas;
9. persistir estado validado em `operations/state`;
10. publicar artefatos;
11. realizar auditoria independente do estado já commitado.

Se qualquer gate falhar, `operations/state` não deve ser alterado.

## Recuperação

Recuperação é GitHub-native:

1. selecionar um commit válido de `operations/state`;
2. reconstruir o ambiente em runner limpo;
3. reconstruir o SQLite a partir do estado textual;
4. verificar hashes, ledger, protocolo e `integrity_check`;
5. reproduzir os resultados esperados;
6. publicar nova evidência de recuperação.

Não existe procedimento de recuperação que dependa de arquivo existente em PC local.

## Segurança e limites

- workflows devem operar com permissões mínimas necessárias;
- alterações de estado exigem gates prévios;
- fonte externa arbitrária não pode substituir a fonte definida em protocolo;
- segredos, quando necessários, pertencem ao mecanismo de secrets do GitHub e nunca ao repositório;
- artifacts não são tratados como autoridade de estado quando existir representação canônica em `operations/state`;
- nenhum resultado local pode fechar gap remoto por equivalência presumida.

## Evidência e aceitação

A release só é aceita quando a evidência produzida no GitHub liga materialmente:

`commit -> workflow run -> artifact -> provenance -> state -> evidence application`

e, quando aplicável:

`integração -> regressão -> recuperação`.

A presença de arquivo, workflow ou script isolado não prova readiness.

A matriz completa permanece em `docs/MISSION_PROVEN.md` e a especificação operacional detalhada em `docs/GITHUB_OPERATIONS.md`.
