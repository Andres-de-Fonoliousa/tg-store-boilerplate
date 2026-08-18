"""Catalog sync — mirrors the provider tree into local tables.

Pattern from store-app (SyncProductsFromProvider): BFS over content pages in
batches, updateOrCreate by provider ids, `--fresh` deactivates stale rows,
then margin pricing. Curation happens afterwards by toggling status /
display_name / price_override — the sync never resurrects hidden items and
never overwrites overridden prices.

Usage:
    python -m app.catalog.sync_catalog [--fresh] [--provider dummy]
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.catalog.normalize import dumps, normalize_qty_values, sanitize_name
from app.config import settings
from app.core.database import SessionLocal
from app.core.models import Category, Product
from app.providers.base import StoreProvider, get_provider

logger = logging.getLogger(__name__)

_BATCH = 10
_POOL = 6


def _apply_margin(product: Product) -> None:
    if not product.price_override:
        product.price = round(product.cost_price * (1 + settings.MARGIN_PERCENT / 100), 4)


def sync_catalog(provider: StoreProvider, fresh: bool = False) -> tuple[int, int]:
    """Sync categories + products. Returns (cats, products) counts.

    Existing curated rows keep their status/display_name/override — sync only
    updates raw fields (name, cost, availability, params).
    """
    db = SessionLocal()
    cat_count = 0
    prod_count = 0
    try:
        # ── BFS over content pages ──
        queue: list[tuple[int, int | None]] = [(0, None)]
        cat_map: dict[int, int] = {}

        while queue:
            batch, queue = queue[:_BATCH], queue[_BATCH:]
            contents = _fetch_many(provider, [pid for pid, _ in batch])

            for provider_pid, local_parent_id in batch:
                content = contents.get(provider_pid) or {}
                for raw_cat in content.get("categories") or []:
                    cat = db.query(Category).filter_by(
                        provider_category_id=raw_cat["id"]
                    ).first()
                    if cat is None:
                        cat = Category(provider_category_id=raw_cat["id"])
                        db.add(cat)
                    cat.name = sanitize_name(raw_cat.get("name") or "")
                    cat.image = raw_cat.get("image") or raw_cat.get("category_img") or None
                    cat.parent_id = local_parent_id
                    cat_count += 1
                    cat_map[raw_cat["id"]] = cat.id
                    queue.append((raw_cat["id"], cat.id))

            db.commit()

        # ── Products ──
        synced_ids: set[int] = set()
        for raw in provider.get_products() or []:
            ext_id = int(raw["id"])
            synced_ids.add(ext_id)

            product = db.query(Product).filter_by(external_id=ext_id).first()
            if product is None:
                product = Product(external_id=ext_id, status="active" if raw.get("available", True) else "inactive")
                db.add(product)
                # existing rows keep their curated status — sync never resurrects
                # hidden items nor re-hides curated ones

            product.name = sanitize_name(raw.get("name") or "")
            product.category_id = _lookup_category(db, raw, cat_map)
            product.cost_price = float(raw.get("base_price") or raw.get("price") or 0)
            product.params = dumps(raw.get("params") or [])
            product.qty_values = dumps(normalize_qty_values(raw.get("qty_values")))
            product.image = raw.get("category_img") or raw.get("image") or None
            product.is_auto = bool(raw.get("product_type") != "manual")
            _apply_margin(product)
            prod_count += 1

        db.commit()

        if fresh:
            gone = (
                db.query(Product)
                .filter(Product.status != "inactive", ~Product.external_id.in_(synced_ids))
                .update({"status": "inactive"}, synchronize_session=False)
            )
            if gone:
                logger.info("%s stale products deactivated", gone)
            db.commit()

        logger.info("catalog sync done: %s categories, %s products", cat_count, prod_count)
        return cat_count, prod_count
    finally:
        db.close()


def _fetch_many(provider: StoreProvider, parent_ids: list[int]) -> dict[int, dict]:
    """Fetch content pages in parallel, tolerating failures per page."""

    def one(pid: int):
        try:
            return pid, provider.get_content(pid)
        except Exception:  # noqa: BLE001 - a failing page must not kill the sync
            logger.warning("content page %s failed", pid)
            return pid, {}

    with ThreadPoolExecutor(max_workers=_POOL) as pool:
        futures = [pool.submit(one, pid) for pid in parent_ids]
        return {pid: data for pid, data in (f.result() for f in as_completed(futures))}


def _lookup_category(db, raw: dict, cat_map: dict[int, int]) -> int | None:
    parent = raw.get("parent_id") or 0
    if parent and parent in cat_map:
        return cat_map[parent]
    cat_name = raw.get("category_name")
    if cat_name:
        cat = db.query(Category).filter_by(name=sanitize_name(str(cat_name))).first()
        if cat:
            return cat.id
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync provider catalog")
    parser.add_argument("--fresh", action="store_true", help="deactivate products no longer in catalog")
    parser.add_argument("--provider", default=None, help="override STORE_PROVIDER (dummy|world4card)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    provider = get_provider(name=args.provider)
    cats, prods = sync_catalog(provider, fresh=args.fresh)
    print(f"Synced: {cats} categories, {prods} products")


if __name__ == "__main__":
    main()