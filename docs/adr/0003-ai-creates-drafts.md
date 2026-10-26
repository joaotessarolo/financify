# ADR 0003: IA cria rascunhos, não transações

- Status: aceito
- Data: 2026-10-26

## Contexto

Transcrição e modelos generativos podem omitir, inventar ou interpretar dados de
forma incorreta. Um lançamento financeiro exige intenção clara do usuário.

## Decisão

Texto e áudio processados pela IA produzem um `TransactionDraft`. Apenas uma ação
explícita de confirmação chama o serviço responsável por criar a transação.

## Consequências

- A interface deve permitir confirmar, editar e rejeitar.
- A saída estruturada sempre será validada no backend.
- Rascunhos, execuções e erros deverão ser auditáveis.
- Testes do ledger não dependerão de um modelo de IA.

