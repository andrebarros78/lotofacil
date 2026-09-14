# SARE Lotofácil 1.1.8 — PRIMARY_CARD

## Objetivo

Produzir uma única combinação principal de 15 dezenas para o próximo concurso canônico.

O `PRIMARY_CARD` é a saída principal do produto. Carteiras com múltiplos cartões são opcionais e têm finalidade de cobertura combinatória.

## Regra canônica

Método: `M1_TOP15_M2_TIEBREAK_V1`.

Para o concurso N:

1. o treinamento termina obrigatoriamente em N-1;
2. M1 `M1_frequency_regularized_lambda_100` fornece o escore primário de cada uma das 25 dezenas;
3. M2 `M2_exponential_alpha_0.05` só desempata dezenas com mesmo escore M1;
4. persistindo empate, vence a menor dezena;
5. as 15 primeiras dezenas do ranking formam o cartão;
6. a representação final do cartão é ordenada crescentemente.

Não existe seed aleatória na seleção do `PRIMARY_CARD`.

## Identidade e congelamento

Cada decisão recebe `decision_sha256` calculado sobre:

- concurso-alvo;
- último concurso de treinamento;
- 15 dezenas selecionadas;
- ranking completo das 25 dezenas;
- nomes dos modelos;
- método de seleção;
- vetores de escores M1/M2.

Nas novas previsões da 1.1.8, o `primary_card` integra a previsão prospectiva e o `prediction_sha256`.

A avaliação posterior é gravada separadamente em `primary_card_evaluation`; o cartão congelado não é alterado.

## Compatibilidade com previsão legada

Previsões anteriores à 1.1.8 não são regravadas.

Se a previsão legada já contém M1/M2 congelados, o cartão principal pode ser derivado read-only desses vetores. A Console registra:

`DERIVED_FROM_FROZEN_LEGACY_MODEL_SCORES`

Essa regra é relevante para o concurso 3780, cuja previsão foi congelada na 1.1.7.

## Operação

No workflow `SARE Operator Console`, escolha:

`generate-primary-card`

O resultado é publicado como `primary_card.json` em GitHub Artifact e contém a decisão completa e sua proveniência.

## Carteira opcional

`generate-portfolio` aceita de 1 a 100 cartões, mas continua sendo um mecanismo uniforme baseado em seed. Ele não substitui o `PRIMARY_CARD`.

## Avaliação

Após a publicação do resultado oficial, o SARE mede quantas das 15 dezenas do cartão principal coincidiram com o sorteio e registra esse valor sem alterar a decisão original.
