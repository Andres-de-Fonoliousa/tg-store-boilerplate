# tg-store-boilerplate — PLAN

Generic, reusable Telegram store bot skeleton. Extracted from `telegram-store-bot2` (client #1)
and `store-app` (white-label platform), with all bugfixes baked in and everything configurable.

## Requirements (Yazan, Aug 2026)

1. **Provider API (P1)**: one canonical adapter — the World4Card-style API
   (docs: https://api.world4card.com/api-docs, identical to the original MHD/shams4store
   integration). `api-token` header; endpoints: profile, products (`products_id` filter,
   `base=1`), content/{id} (BFS tree), newOrder/{id}/params (idempotent via `order_uuid`),
   check?orders=[]&uuid=1. Error codes 100/105–114/120–130 mapped to typed exceptions →
   friendly user messages. Other API providers = later integrations via the same interface.
2. **Products & categories (P2)**: pattern from store-app — mirror provider catalog locally:
   categories (provider_category_id unique, parent tree, image, status) + products
   (external_id unique, cost_price from base_price, sell price = cost × margin %,
   params, normalized qty_values, status). Sync via BFS content pages (batched, pooled),
   `--fresh` deactivates stale. **Curation = status + rename** (owner decides what shows;
   bot shows active only). Per-product price override on top of global margin.
3. **Front polish (P3)**: all user-facing strings in i18n (AR/EN), professional and clean;
   raw provider names sanitized + `display_name` override for malnamed products;
   conversations redesigned around clear summaries and confirmations.

## Decisions (confirmed)

- python-telegram-bot pinned **21.3**; providers via `STORE_PROVIDER` (world4card | dummy)
- Flask dashboard as optional importable addon (`app.dashboard`), CSRF-hardened
- Repo **private**, `tg-store-boilerplate`, at `Desktop\Python\tg-store-boilerplate`
- SQLite default (DATABASE_URL switchable), AR/EN i18n, pytest

## Architecture

```
app/
├── main.py            # entry: bot + job queue
├── config.py          # env-driven Settings; zero hardcoded values
├── core/              # database, models, migrations
├── handlers/          # user, navigation
├── conversations/     # order, deposit, admin
├── keyboards/         # inline, reply
├── providers/         # base (protocol + errors), world4card, dummy
├── catalog/           # sync_catalog (BFS+updateOrCreate+margin), normalize helpers
├── i18n/              # ar.py, en.py — ALL user-facing strings
└── dashboard/         # Flask addon (importable, optional)
seed_demo.py           # demo categories/products via dummy provider
tests/                 # pytest
deploy/                # Dockerfile, docker-compose.yml, systemd unit
.env.example
README.md
```

## Phases

### P0 — Scaffold
- git init (private), folder tree, requirements.txt pinned, .env.example, .gitignore
- config.py: BOT_TOKEN, ADMIN_USER_IDS, DATABASE_URL, STORE_PROVIDER, provider envs
  (BASE_URL, API_TOKEN), LANG, dashboard envs, MARGIN_PERCENT
- i18n/ar.py + en.py skeletons; LANG switch

### P1 — Provider adapter (priority 1)
- `providers/base.py`: StoreProvider protocol — get_profile, get_products(ids?),
  get_content(parent_id), create_order(product_id, qty, params, order_uuid), check_order(id_or_uuid)
  + typed exceptions: AuthError, Maintenance, InsufficientBalance, ProductUnavailable,
  QuantityNotAllowed, TryAgainLater, ProductNotFound, OrderError
- `providers/world4card.py`: canonical implementation per docs; error-code table;
  retry-safe (order_uuid reuse on 111); no prints, logger only
- `providers/dummy.py`: in-memory store for dev/tests

### P2 — Catalog & curation (priority 2)
- Models: Category (provider_category_id unique, parent_id, name, image, status),
  Product (external_id unique, category_id, name, display_name, cost_price, price,
  params JSON, qty_values JSON normalized, status, is_auto)
- `catalog/sync_catalog.py`: BFS over content pages (batched 10, ThreadPool), updateOrCreate,
  `--fresh` deactivates stale, applies margin %, busts cache
- Curation UX: Telegram admin — list cats/products, enable/disable, rename (display_name),
  per-product price override; dashboard addon mirrors it
- Bot shows only status=active

### P3 — Store flows with polished front (priority 3)
- Order conversation: product → params form (from product.params) → qty (qty_values rules)
  → order summary card → confirm; balance check, provider call with fresh order_uuid,
  status pending; polling: accept→deliver replay_api, reject→refund, wait→keep polling,
  TryAgainLater→backoff
- Deposit conversation: amount → method (from settings) → receipt photo → admin review;
  approve credits once (balance_credited), cancel refunds once (refunded)
- Admin conversation: stats, deposits, orders, catalog curation, broadcast, bot on/off
- Every message via i18n; product names sanitized (strip artifacts, title-case)

### P4 — Dashboard addon
- Flask app factory `create_app()`: CSRF, hashed access code + attempt limit,
  localhost default, env secret key; pages: overview, orders, deposits, catalog
  curation (toggle/rename/price), settings (margin, payment methods)

### P5 — Tests
- Regression: deposit double-approve credits once; cancel refunds once; auto-timeout
  refunds once; qty normalization (null/list/range); price = cost × margin;
  provider error-code mapping; order_uuid idempotency; dummy end-to-end conversation;
  Flask: login required, forged POST 403

### P6 — Deploy + docs
- Dockerfile, compose, systemd, backup note; bilingual README:
  clone → .env → sync catalog → run; acceptance: fresh clone runs dummy store, pytest green

## Creative features (after boilerplate core — propose when time)
- Order status tracking button (live provider check on demand)
- Referral/discount codes per user
- Sync price-drop alerts to admin channel
- Broadcast to all users with targeting (active buyers / last 30d)