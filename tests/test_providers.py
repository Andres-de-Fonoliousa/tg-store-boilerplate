"""Provider + normalization tests."""

import uuid

import pytest

from app.catalog.normalize import is_qty_allowed, normalize_qty_values, sanitize_name
from app.providers.base import (
    InsufficientBalanceError,
    MaintenanceError,
    ProductUnavailableError,
    TryAgainLaterError,
)
from app.providers.dummy import DummyProvider
from app.providers.world4card import ERROR_MAP


class TestNormalize:
    def test_null_qty_is_unit(self):
        assert normalize_qty_values(None) == {"type": "unit"}

    def test_list_qty(self):
        assert normalize_qty_values(["110", "150"]) == {"type": "list", "values": [110, 150]}

    def test_range_qty(self):
        assert normalize_qty_values({"min": "500", "max": "500000"}) == {
            "type": "range", "min": 500, "max": 500000}

    def test_is_qty_allowed(self):
        assert is_qty_allowed({"type": "unit"}, 1) is True
        assert is_qty_allowed({"type": "unit"}, 2) is False
        assert is_qty_allowed({"type": "list", "values": [110, 150]}, 150) is True
        assert is_qty_allowed({"type": "list", "values": [110, 150]}, 160) is False
        assert is_qty_allowed({"type": "range", "min": 1, "max": 15000}, 9999) is True
        assert is_qty_allowed({"type": "range", "min": 1, "max": 15000}, 99999) is False

    def test_sanitize_name(self):
        assert sanitize_name("  UC  60  ") == "UC 60"
        assert sanitize_name("\x00bad\x1f name") == "bad name"


class TestDummyProvider:
    def test_order_uuid_idempotency(self):
        p = DummyProvider()
        u = str(uuid.uuid4())
        r1 = p.create_order(1, 1, {"playerId": "a"}, u)
        r2 = p.create_order(1, 1, {"playerId": "a"}, u)
        assert r1["order_id"] == r2["order_id"]

    def test_unavailable_product(self):
        p = DummyProvider()
        with pytest.raises(ProductUnavailableError):
            p.create_order(999, 1, {}, str(uuid.uuid4()))

    def test_unavailable_flag(self):
        p = DummyProvider()
        with pytest.raises(ProductUnavailableError):
            p.create_order(3, 1, {}, str(uuid.uuid4()))

    def test_insufficient(self):
        p = DummyProvider()
        p._balance = 0.5
        with pytest.raises(InsufficientBalanceError):
            p.create_order(2, 1, {}, str(uuid.uuid4()))

    def test_content_tree(self):
        p = DummyProvider()
        home = p.get_content(0)
        assert len(home["categories"]) == 2
        assert home["products"] == []


class TestErrorMap:
    def test_known_codes(self):
        assert ERROR_MAP[100] is InsufficientBalanceError
        assert ERROR_MAP[111] is TryAgainLaterError
        assert ERROR_MAP[130] is MaintenanceError