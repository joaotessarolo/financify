# ADR 0004: Processar áudio de forma assíncrona

- Status: aceito
- Data: 2026-10-26

## Contexto

Upload, transcrição e interpretação têm latência e disponibilidade externas ao
servidor HTTP. Manter a requisição aberta fragiliza o fluxo e dificulta retries.

## Decisão

O endpoint recebe o áudio, persiste a mensagem e agenda processamento em worker.
Inicialmente o cliente consulta o estado por polling.

Python será usado no pipeline inicial. Rust só será introduzido após profiling
demonstrar um gargalo local que ele resolva.

## Consequências

- Tarefas precisam ser idempotentes e possuir políticas de retry e timeout.
- A interface precisa representar processamento e falha.
- O sistema precisa guardar métricas de latência por etapa.
- SSE poderá ser adotado futuramente sem alterar o domínio.

