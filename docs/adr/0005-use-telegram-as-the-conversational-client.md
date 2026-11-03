# ADR 0005: Use Telegram as the conversational client

- Status: accepted
- Date: 2026-11-01

## Context

Financify needs a convenient interface for recording financial activity through text and voice. Building and maintaining a dedicated mobile application would introduce another client platform before the core ledger and conversational workflow have been validated.

Telegram already provides private chats, voice messages, commands, inline keyboards, and reliable delivery to a backend webhook. The web application is still needed for setup, review, reporting, and detailed financial management.

## Decision

Use a Telegram bot as the first conversational client and do not plan a dedicated mobile application at this stage.

Telegram is implemented as an inbound adapter inside the Django modular monolith. It delegates financial operations to application services and never writes directly to ledger models. Text and voice messages produce transaction drafts; only explicit user confirmation can post a transaction.

Production receives Telegram updates through an HTTPS webhook. Slow and external work, including voice download, transcription, and AI interpretation, runs in a background worker. Local development may use long polling.

The Next.js application remains a separate web client for management and visualization. A conversational interface on the web is outside this decision and may be evaluated later.

## Consequences

- The product validates conversational behavior without building a mobile app.
- Users need a Telegram account to use the conversational interface.
- A secure account-linking flow is required between Financify and Telegram.
- Telegram update and callback processing must be idempotent.
- Bot availability depends partly on Telegram's platform and Bot API.
- Conversation and assistant modules remain channel-independent so another interface can reuse them later.
- Telegram protocol details stay isolated from ledger rules.
