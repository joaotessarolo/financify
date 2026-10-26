# Roteiro de aprendizado e implementação

O objetivo não é apenas terminar funcionalidades. Cada etapa deve produzir uma
compreensão verificável antes de avançar.

## 1. Fundação Python e Django

Estudar e decidir:

- Como o Python encontra e importa módulos?
- O que o Django configura no startup?
- Qual a responsabilidade de projeto, app e settings?
- Por que settings de desenvolvimento e produção diferem?
- O que migrations representam e por que não devem ser editadas casualmente?

Entrega sugerida: projeto Django executável, health check e um teste simples.

## 2. Persistência e domínio financeiro

Estudar e decidir:

- Qual a diferença entre uma transação financeira e um lançamento contábil?
- Como representar transferência sem tratá-la como despesa?
- Onde uma transação de banco de dados é necessária?
- Como `Decimal`, moeda e arredondamento serão tratados?
- Quais invariantes pertencem ao model e quais pertencem a um serviço?

Entrega sugerida: contas e transações com testes de invariantes, sem interface de IA.

## 3. API

Estudar e decidir:

- O que serializer, view e service devem validar?
- Como impedir acesso aos dados de outro usuário?
- Como paginação, filtros e erros serão representados?
- Qual é a política de versionamento da API?
- Onde idempotency keys serão exigidas?

Entrega sugerida: API documentada por OpenAPI e testada em nível HTTP.

## 4. React, TypeScript e Next.js

Estudar e decidir:

- O que deve ser Server Component e Client Component?
- Quem controla estado do servidor e estado temporário da interface?
- Como formulários e erros da API serão representados?
- Como impedir que tipos TypeScript virem uma segunda fonte de verdade?

Entrega sugerida: fluxo completo de criação e consulta de transações.

## 5. Chat por texto

Estudar e decidir:

- Uma mensagem é imutável?
- Como respostas, tentativas e falhas serão registradas?
- Como validar saída estruturada do modelo?
- Como testar o fluxo sem chamar um provedor real?

Entrega sugerida: texto natural produz um rascunho editável e confirmável.

## 6. Áudio e processamento assíncrono

Estudar e decidir:

- O que acontece se a mesma tarefa executar duas vezes?
- Como upload, retry, timeout e falha serão comunicados ao usuário?
- Por quanto tempo o áudio será mantido?
- Como medir latência de cada etapa?

Entrega sugerida: gravação, transcrição, rascunho e confirmação com métricas básicas.

## Critério para avançar

Antes de adicionar uma camada, deve ser possível explicar:

1. Qual problema concreto ela resolve.
2. Qual custo operacional ela adiciona.
3. Como será testada.
4. Como saberemos se está funcionando.

