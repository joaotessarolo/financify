# Web dashboard

The dashboard lives in `apps/web` and uses Next.js, TypeScript, React, and Bun. Django remains responsible for authentication, authorization, validation, and every financial calculation.

## Local workflow

Start PostgreSQL and the API first, then run the web client:

```bash
docker compose -f infra/compose.yaml up -d --wait
cd apps/api && uv run python manage.py migrate && uv run python manage.py runserver
cd apps/web && bun install && bun run dev
```

`API_INTERNAL_URL` defaults to `http://127.0.0.1:8000`. Browser requests go through the `/backend` rewrite so the session and CSRF flow stay same-origin.

## Quality checks

```bash
cd apps/web
bun run lint
bun run format:check
bun run typecheck
bun run test
bun run build
```

The critical backend flows are covered in the Django suites under `users/tests` and `ledger/tests`. Run them with PostgreSQL before merging:

```bash
cd apps/api
uv run python manage.py test
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Never expose API keys through `NEXT_PUBLIC_*`, browser logs, test fixtures, or committed environment files.
