"""In-memory provider for offline dev and tests.

Mimics the World4Card behaviour (idempotent order_uuid, status transitions
accept -> fulfilled with a replay payload, quantity rules) without any network.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.providers.base import (
    InsufficientBalanceError,
    ProductUnavailableError,
    StoreProvider,
)

# Deterministic demo catalog. Seed via seed_demo.py, or reuse these defaults.
DEMO_PRODUCTS: list[dict] = [
    {
        "id": 1,
        "name": "PUBG UC 60",
        "price": 1.10,
        "base_price": 0.92,
        "params": ["Player ID"],
        "category_name": "PUBG",
        "available": True,
        "qty_values": {"min": 1, "max": 15000},
        "product_type": "amount",
        "parent_id": 101,
    },
    {
        "id": 2,
        "name": "PUBG UC 325",
        "price": 5.95,
        "base_price": 4.96,
        "params": ["Player ID"],
        "category_name": "PUBG",
        "available": True,
        "qty_values": None,
        "product_type": "package",
        "parent_id": 101,
    },
    {
        "id": 3,
        "name": "Free Fire 100 Diamonds",
        "price": 1.35,
        "base_price": 1.12,
        "params": ["Player ID"],
        "category_name": "Free Fire",
        "available": False,
        "qty_values": ["100", "210", "530"],
        "product_type": "package",
        "parent_id": 102,
    },
]

DEMO_CATEGORIES: list[dict] = [
    {"id": 101, "name": "PUBG", "parent_id": 0},
    {"id": 102, "name": "Free Fire", "parent_id": 0},
]


class DummyProvider(StoreProvider):
    name = "dummy"

    def __init__(self, products: list[dict] | None = None):
        self._products = {p["id"]: dict(p) for p in (products or DEMO_PRODUCTS)}
        self._balance = 1000.0
        self._orders: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── API ──────────────────────────────────────────────────────

    def get_profile(self) -> dict:
        return {"balance": self._balance}

    def get_products(self, product_ids: list[int] | None = None) -> list[dict]:
        with self._lock:
            items = list(self._products.values())
        if product_ids:
            items = [p for p in items if p["id"] in product_ids]
        return [dict(p) for p in items]

    def get_content(self, parent_id: int = 0) -> dict:
        with self._lock:
            cats = [c for c in DEMO_CATEGORIES if c["parent_id"] == parent_id]
            prods = [p for p in self._products.values() if p["parent_id"] == parent_id]
        return {
            "categories": [dict(c) for c in cats],
            "products": [dict(p) for p in prods],
        }

    def create_order(
        self,
        product_id: int,
        qty: int,
        params: dict[str, str],
        order_uuid: str,
    ) -> dict:
        with self._lock:
            existing = self._orders.get(order_uuid)
            if existing is not None:
                return existing  # idempotent — same uuid returns the same order

            product = self._products.get(product_id)
            if product is None or not product.get("available", True):
                raise ProductUnavailableError(f"product {product_id} unavailable")

            cost = float(product["price"])
            if self._balance < cost * qty:
                raise InsufficientBalanceError("provider balance low")

            self._balance -= cost * qty
            order = {
                "order_id": f"ID_DUMMY_{time.time_ns()}",
                "status": "accept",
                "price": cost * qty,
                "data": dict(params),
                "replay_api": [{"replay": [f"code-{product_id}-{qty}"]}],
            }
            self._orders[order_uuid] = order
            return dict(order)

    def check_order(self, order_id_or_uuid: str, is_uuid: bool = False) -> dict:
        with self._lock:
            for uuid, order in self._orders.items():
                if (is_uuid and uuid == order_id_or_uuid) or (
                    not is_uuid and order["order_id"] == order_id_or_uuid
                ):
                    return dict(order)
        return {}
