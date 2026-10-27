# Financify

Aplicação de finanças pessoais com entrada de receitas e despesas por formulário,
texto natural e áudio.

As primeiras decisões e os limites do produto estão registrados em
[`docs/architecture.md`](docs/architecture.md) e nos ADRs em [`docs/adr`](docs/adr).

## Estado atual

- API Django em `apps/api`.
- PostgreSQL local definido em `infra/compose.yaml`.
- App `users` criado; o model será implementado como exercício.
- Django REST Framework instalado; endpoints ainda não foram implementados.

## Desenvolvimento da API

Pré-requisitos: Python 3.15, `uv` e Docker.

```bash
cp apps/api/.env.example apps/api/.env
docker compose -f infra/compose.yaml up -d --wait
cd apps/api
uv sync
uv run python manage.py migrate
uv run python manage.py test
uv run python manage.py runserver
```

O `.env.example` contém somente valores adequados ao desenvolvimento local. Em
qualquer outro ambiente, a chave secreta e as credenciais devem ser substituídas.

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

