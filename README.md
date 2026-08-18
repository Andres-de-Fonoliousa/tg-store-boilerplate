# Telegram Store Boilerplate

Generic, reusable Telegram store bot — provider-driven catalog, balance wallet,
receipt deposits, order polling, admin panel (in-chat + optional web dashboard).

Built from two production projects (`telegram-store-bot2`, `store-app`) with every
money bug fixed and covered by regression tests.

## Features

- Catalog synced from a World4Card-style provider API (content tree, products,
  cost prices) with margin pricing and manual price overrides
- Curation: hide/show categories & products, rename malnamed products
  (display_name) — sync never resurrects hidden items
- Wallet: users top up via payment methods + receipt photo; deposit approvals
  credit exactly once (`balance_credited` guard)
- Orders: dynamic params forms, qty rules (unit / list / range), provider order
  with `order_uuid` idempotency, polling resolve (accept → deliver replay,
  reject/timeout → refund once — `refunded` guard)
- Optional Flask dashboard addon: CSRF, hashed access code, rate-limited login
- AR/EN UI strings via `app/i18n`, fully configurable through `.env`

## Quick start (demo, no API keys)

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux: cp .env.example .env

# set BOT_TOKEN and ADMIN_USER_IDS in .env, then:
python seed_demo.py               # dummy provider catalog + defaults
python app/main.py                # run the bot
```

`seed_demo.py` uses the built-in dummy provider (in-memory) — a store with
3 products / 2 categories works without touching any external API.

## Real provider

```dotenv
STORE_PROVIDER=world4card
PROVIDER_BASE_URL=https://api.world4card.com
PROVIDER_API_TOKEN=your_token_here
MARGIN_PERCENT=20
```

Then sync the catalog (options: `--fresh` deactivates products removed upstream):

```bash
python -m app.catalog.sync_catalog --fresh
```

The bot also syncs automatically every `CATALOG_SYNC_MINUTES`.

### Provider API contract

One canonical adapter (see `app/providers/world4card.py`): `api-token` header;
`profile`, `products` (optional `products_id`, `base=1`), `content/{id}` tree,
`newOrder/{id}/params` (idempotent via `order_uuid`), `check?orders=[..]`.
Error codes (100/105–114/120–130) map to typed exceptions with friendly user
messages. Adding another provider = implement `StoreProvider` and set
`STORE_PROVIDER`; the bot logic doesn't change.

## Dashboard addon (optional)

```bash
python -m app.dashboard          # http://127.0.0.1:5000
```

Needs `FLASK_SECRET_KEY` + `ADMIN_ACCESS_CODE` in `.env`. Runs on 127.0.0.1 by
default; behind nginx with TLS in production (see deploy/).

## Tests

```bash
pytest
```

Regression coverage: deposit double-approve, refund idempotency, qty rules,
price margin, curation preservation, provider idempotency/errors, dashboard CSRF
and rate limiting.

## Deploy

- `deploy/docker-compose.yml` — bot + dashboard services
- `deploy/tg-store-boilerplate.service` — systemd unit (edit paths)

## Customizing per client

1. `.env` — token, admins, provider, margin, payment methods (in dashboard settings)
2. `app/i18n/` — all user-facing copy (AR/EN), theme emojis
3. `app/providers/` — drop another provider adapter
4. `seed_demo.py` — demo catalog

## Project layout

```
app/
├── main.py            # entry: bot + jobs
├── config.py          # env-driven settings (no hardcoded values)
├── core/              # db, models, notifications
├── handlers/          # start / catalog browsing
├── conversations/     # order, deposit, admin (curation/broadcast)
├── keyboards/         # inline + reply builders
├── providers/         # base (protocol+errors), world4card, dummy
├── catalog/           # sync (BFS+updateOrCreate+margin), normalize helpers
├── i18n/              # ar.py / en.py message maps
└── dashboard/         # optional Flask addon
seed_demo.py           # demo store via dummy provider
tests/                 # pytest
deploy/                # docker + systemd
```