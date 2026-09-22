# Análise Pós-Concurso — Lotofácil Operacional

- Concurso Número: 3785
- Resultado: 01 04 07 08 11 12 14 15 17 18 19 22 23 24 25
- Cartão gerado: 01 02 03 04 05 10 11 12 13 14 15 20 22 24 25
- Número de acertos: 9

- Acertos: 01 04 11 12 14 15 22 24 25
- Selecionadas que não saíram: 02 03 05 10 13 20
- Sorteadas que ficaram fora: 07 08 17 18 19 23

## Autoanálise do processo
- Cartão obteve 9 acertos; 6 selecionadas não saíram e 6 sorteadas ficaram fora.
- O modelo primário ficou abaixo do baseline uniforme neste concurso.

### Correções necessárias
- Nenhuma correção de integridade obrigatória foi identificada neste ciclo.

### Ajustes sugeridos
- Examinar a recorrência das dezenas selecionadas que não saíram e das sorteadas que ficaram fora em uma janela prospectiva; um único concurso não deve virar regra de seleção.
- Se a perda para o baseline persistir na coorte, abrir challenger predeclarado e compará-lo sem alterar retroativamente o champion.

### Implementações necessárias
- Emitir e persistir este relatório automaticamente após cada resultado oficial avaliado.
- Acumular padrões de erro em vários concursos antes de propor qualquer alteração do modelo.

### Restrições
- O cartão congelado não pode ser reescrito após o resultado.
- Um único concurso não autoriza retuning nem promoção de modelo.

