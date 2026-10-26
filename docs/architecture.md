# Arquitetura inicial

## Objetivo

Construir um produto pequeno e utilizável enquanto revisamos os fundamentos de
Python, Django, React, TypeScript e Next.js. A arquitetura deve permitir evolução,
mas não antecipar escala ou equipes que ainda não existem.

## Contexto

- Um desenvolvedor trabalhando continuamente no produto.
- Web primeiro; mobile será considerado posteriormente.
- Cada recurso financeiro pertence diretamente a um usuário.
- Entradas poderão ser feitas manualmente, por texto ou por áudio.
- Monetização e volume ainda são desconhecidos.

## Visão do sistema

```text
Browser / Next.js
       |
       | HTTP + JSON
       v
Django REST API ---------------- PostgreSQL
       |
       | agenda trabalhos demorados
       v
Fila / Worker ------------------ Object storage
       |
       +---- transcrição
       +---- interpretação estruturada
       +---- notificações de conclusão
```

O sistema será um monólito modular. API web e worker executam o mesmo código
Django, embora possam ser processos e containers separados.

## Contextos do backend

### Identity

Autenticação, perfil e preferências do usuário, incluindo moeda e timezone.

### Ledger

Contas, transações, lançamentos, transferências e consistência financeira. Este é
o núcleo do produto e não deve depender do módulo de IA.

### Classification

Categorias, tags e regras determinísticas de classificação.

### Conversations

Conversas, mensagens, anexos de áudio e estado visível de processamento.

### Assistant

Transcrição, identificação de intenção e extração estruturada. Produz rascunhos;
nunca persiste uma transação confirmada sem ação explícita do usuário.

## Regras arquiteturais

1. Valores monetários usam decimal e uma moeda explícita.
2. Toda consulta de domínio é limitada ao usuário autenticado.
3. Transferência não é receita nem despesa.
4. Requisições e tarefas repetidas devem ser idempotentes.
5. Chamadas a modelos de IA ficam atrás de interfaces da aplicação.
6. A saída da IA é dado não confiável e sempre passa por validação.
7. Áudio e chamadas externas são processados fora da requisição HTTP principal.
8. Código de domínio não importa SDKs de fornecedores de IA.
9. Uma otimização só é introduzida após medição.

## Fluxo de áudio

```text
mensagem de áudio
  -> upload e criação da mensagem
  -> tarefa de transcrição
  -> tarefa de interpretação
  -> validação do resultado
  -> TransactionDraft
  -> confirmação ou correção pelo usuário
  -> serviço do Ledger
  -> Transaction
```

Estados mínimos da mensagem: `uploaded`, `processing`, `completed` e `failed`.
Estados mínimos do rascunho: `pending`, `confirmed`, `rejected` e `expired`.

## Contrato entre frontend e backend

A API será REST e terá especificação OpenAPI. O frontend não duplicará
manualmente os tipos dos recursos: futuramente será gerado um cliente TypeScript
a partir da especificação.

O MVP pode consultar o estado do processamento por polling. SSE poderá substituir
o polling quando streaming e feedback progressivo justificarem a complexidade.

## Caminho de evolução

- O mobile entra como novo consumidor da mesma API.
- Propriedade direta por usuário pode migrar para um workspace quando houver
  compartilhamento.
- Um módulo só vira serviço separado por necessidade operacional comprovada.
- Rust será considerado apenas para um processamento local que apareça em
  profiling como gargalo relevante.

