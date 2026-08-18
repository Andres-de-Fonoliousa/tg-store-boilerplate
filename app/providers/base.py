"""Store provider protocol and typed error hierarchy.

All providers implement :class:`StoreProvider`. The bot only talks to this
interface, so adding another provider is a pure integration job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ── Error hierarchy ─────────────────────────────────────────────
# Mapped from the World4Card-style error code table (see world4card.py).

class ProviderError(Exception):
    """Base class for all provider errors."""

    code: int | None = None

    def __init__(self, message: str = "", code: int | None = None):
        self.code = code
        super().__init__(message or self.__class__.__name__)


class AuthError(ProviderError):
    """api-token missing/invalid/not allowed (120/121/122/123)."""


class MaintenanceError(ProviderError):
    """Provider site under maintenance (130)."""


class InsufficientBalanceError(ProviderError):
    """Provider balance is too low for the order (100)."""


class QuantityNotAllowedError(ProviderError):
    """Quantity not available/allowed/out of range (105/106/112/113)."""


class PlayerBlockedError(ProviderError):
    """Player ID blocked by provider (107)."""


class TwoFactorRequiredError(ProviderError):
    """2FA required — manual fulfillment (108)."""


class ProductUnavailableError(ProviderError):
    """Product deleted/not available now (109/110)."""


class TryAgainLaterError(ProviderError):
    """Rate limit / transient failure — retry with backoff (111/114)."""


class OrderError(ProviderError):
    """Generic order failure (114/500)."""


# ── Payload types ───────────────────────────────────────────────
# Plain dicts on purpose: providers are thin, the catalog layer owns
# normalization and persistence.

Category = dict
Product = dict
Profile = dict
OrderResult = dict


# ── Protocol ────────────────────────────────────────────────────

class StoreProvider(ABC):
    """Contract every provider adapter must satisfy."""

    name: str = "provider"

    @abstractmethod
    def get_profile(self) -> Profile:
        """Balance + account info."""

    @abstractmethod
    def get_products(self, product_ids: list[int] | None = None) -> list[Product]:
        """All products, optionally filtered by ids."""

    @abstractmethod
    def get_content(self, parent_id: int = 0) -> dict:
        """Categories + products under a category (home = 0)."""

    @abstractmethod
    def create_order(
        self,
        product_id: int,
        qty: int,
        params: dict[str, str],
        order_uuid: str,
    ) -> OrderResult:
        """Create an order. order_uuid makes the call idempotent — reuse
        the same uuid when retrying the same order attempt."""

    @abstractmethod
    def check_order(self, order_id_or_uuid: str, is_uuid: bool = False) -> OrderResult:
        """Check order status."""


def get_provider(name: str | None = None) -> StoreProvider:
    """Instantiate a provider. `name` overrides the configured STORE_PROVIDER."""
    from app.config import settings

    provider_name = (name or settings.STORE_PROVIDER).lower()
    if provider_name == "dummy":
        from app.providers.dummy import DummyProvider

        return DummyProvider()
    from app.providers.world4card import World4CardProvider

    return World4CardProvider(settings.PROVIDER_BASE_URL, settings.PROVIDER_API_TOKEN)
