# SARE Lotofácil — Sanitização do repositório

## Objetivo

A sanitização protege o baseline GitHub-only contra resíduos de execução, credenciais, chaves privadas, bancos locais, caches, arquivos gerados e artefatos que não pertencem ao código canônico.

Ela não reescreve histórico, não apaga evidência científica histórica válida e não altera `operations/state`. O gate atua sobre o checkout versionado e falha antes da incorporação de conteúdo incompatível.

## Contrato

O script canônico é `scripts/sanitize_repository.py`.

Quando executado dentro de um checkout Git, ele prioriza `git ls-files` e verifica os arquivos rastreados. Fora de um checkout Git, usa descoberta recursiva para permitir testes isolados.

O gate rejeita:

- `.env` e variantes sensíveis;
- material de chave privada;
- padrões de tokens de alta confiança para GitHub, AWS, OpenAI, Slack e Google;
- credenciais literais atribuídas diretamente, exceto placeholders reconhecidos;
- bancos e estados locais (`*.db`, `*.sqlite`, WAL/SHM);
- caches e ambientes Python;
- diretórios `build`, `dist` e `artifacts` rastreados;
- logs, temporários, backups, arquivos de chave/certificado privado e arquivos compactados gerados.

## Evidência

O relatório JSON contém:

- status `REPOSITORY_SANITIZATION_PASS` ou `REPOSITORY_SANITIZATION_FAIL`;
- quantidade de arquivos e bytes inspecionados;
- quantidade de violações;
- lista estruturada das violações;
- `manifest_sha256`, calculado sobre caminho, tamanho e SHA-256 de cada arquivo inspecionado.

O workflow `.github/workflows/repository-sanitization.yml` executa em toda pull request e em pushes para `main`, roda os testes específicos, produz o relatório e publica `repository-sanitization` como GitHub Artifact.

## Limites

Este gate é defesa em profundidade e não substitui os mecanismos nativos de secret scanning do provedor Git. Ele usa padrões de alta confiança para reduzir falsos positivos e não tenta interpretar toda possível forma de segredo ofuscado.

A sanitização não concede autoridade de escrita a agentes, não promove evidência científica, não reabre lockbox e não habilita auto-merge.
