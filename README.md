# Financify

Aplicação de finanças pessoais com entrada de receitas e despesas por formulário,
texto natural e áudio.

Este repositório começa deliberadamente sem código. As primeiras decisões e os
limites do produto estão registrados em [`docs/architecture.md`](docs/architecture.md)
e nos ADRs em [`docs/adr`](docs/adr).

## Escopo inicial

- Aplicação web para um único proprietário por conta.
- Cadastro manual de contas, receitas, despesas e transferências.
- Chat com mensagens de texto e áudio.
- IA transforma linguagem natural em um rascunho estruturado.
- O usuário precisa confirmar o rascunho antes de criar uma transação.
- Backend em Python/Django e frontend em React/Next.js.

## Fora do MVP

- Aplicativo mobile.
- Contas familiares ou compartilhadas.
- Integração bancária automática.
- Microsserviços.
- Processamento de áudio em Rust.
- Recomendações financeiras autônomas.

## Ordem de construção

1. Registrar as decisões e perguntas em aberto.
2. Criar o projeto Django sem domínio financeiro.
3. Configurar qualidade, testes e integração contínua.
4. Implementar autenticação e isolamento dos dados por usuário.
5. Modelar contas e o ledger financeiro.
6. Criar a API e integrar o primeiro fluxo no frontend.
7. Adicionar chat por texto.
8. Adicionar áudio e processamento assíncrono.

Antes de iniciar cada etapa, consulte [`docs/learning-roadmap.md`](docs/learning-roadmap.md).

