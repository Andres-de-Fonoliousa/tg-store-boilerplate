"""World4Card-style provider adapter.

Implements the canonical client API (docs: https://api.world4card.com/api-docs),
which is the same API family as shams4store/MHD: `api-token` header, content
tree, idempotent order creation via `order_uuid`, order checking, and the
numeric error-code table below.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.providers.base import (
    AuthError,
    InsufficientBalanceError,
    MaintenanceError,
    OrderError,
    PlayerBlockedError,
    ProductUnavailableError,
    ProviderError,
    QuantityNotAllowedError,
    StoreProvider,
    TryAgainLaterError,
    TwoFactorRequiredError,
)

logger = logging.getLogger(__name__)

ERROR_MAP: dict[int, type[ProviderError]] = {
    100: InsufficientBalanceError,
    105: QuantityNotAllowedError,
    106: QuantityNotAllowedError,
    107: PlayerBlockedError,
    108: TwoFactorRequiredError,
    109: ProductUnavailableError,
    110: ProductUnavailableError,
    111: TryAgainLaterError,
    112: QuantityNotAllowedError,
    113: QuantityNotAllowedError,
    114: OrderError,
    120: AuthError,
    121: AuthError,
    122: AuthError,
    123: AuthError,
    130: MaintenanceError,
    500: OrderError,
}

_API_TOKEN_HEADER = "api-token"
_TIMEOUT = 60


class World4CardProvider(StoreProvider):
    name = "world4card"

    def __init__(self, base_url: str, api_token: str | None):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token or ""
        if not self.api_token:
            logger.warning("PROVIDER_API_TOKEN is empty — provider calls will fail")

    # ── Public API ───────────────────────────────────────────────

    def get_profile(self) -> dict:
        return self._request("get", "/client/api/profile")

    def get_products(self, product_ids: list[int] | None = None) -> list:
        url = "/client/api/products"
        if product_ids:
            url += "?products_id=" + ",".join(str(i) for i in product_ids)
        data = self._request("get", url)
        return data if isinstance(data, list) else []

    def get_content(self, parent_id: int = 0) -> dict:
        data = self._request("get", f"/client/api/content/{parent_id}")
        return data if isinstance(data, dict) else {}

    def create_order(
        self,
        product_id: int,
        qty: int,
        params: dict[str, str],
        order_uuid: str,
    ) -> dict:
        query = {"qty": qty, "order_uuid": order_uuid}
        query.update(params)
        data = self._request(
            "get",
            f"/client/api/newOrder/{product_id}/params",
            params=query,
        )
        return data if isinstance(data, dict) else {}

    def check_order(self, order_id_or_uuid: str, is_uuid: bool = False) -> dict:
        url = "/client/api/check"
        params = {"orders": f"[{order_id_or_uuid}]"}
        if is_uuid:
            params["uuid"] = "1"
        data = self._request("get", url, params=params)
        records = data.get("data", []) if isinstance(data, dict) else []
        return records[0] if records else {}

    # ── Internals ────────────────────────────────────────────────

    def _request(self, method: str, url: str, params: dict | None = None) -> Any:
        logger.debug("provider request: %s %s", method, url)
        try:
            resp = requests.request(
                method,
                self.base_url + url,
                params=params,
                headers={_API_TOKEN_HEADER: self.api_token},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error("provider request failed: %s", exc)
            raise TryAgainLaterError(f"network error: {exc}") from exc

        if resp.status_code >= 400:
            code = _extract_code(resp)
            self._raise_for_code(code, resp.text)
            raise OrderError(f"http {resp.status_code}: {resp.text}")

        try:
            body = resp.json()
        except ValueError:
            logger.error("provider returned non-JSON: %s", resp.text[:300])
            raise TryAgainLaterError("non-JSON response")

        if isinstance(body, dict) and body.get("status") == "error":
            self._raise_for_code(body.get("code"), body.get("message", ""))
        return body

    def _raise_for_code(self, code: Any, detail: str) -> None:
        if code is None:
            return
        try:
            code = int(code)
        except (TypeError, ValueError):
            return
        exc_type = ERROR_MAP.get(code, OrderError)
        logger.warning("provider error %s: %s", code, detail)
        raise exc_type(detail or f"provider error {code}", code=code)

    @staticmethod
    def sleep_before_retry(seconds: int = 60) -> None:
        """Backoff helper for TryAgainLaterError (code 111)."""
        time.sleep(seconds)


def _extract_code(resp: requests.Response) -> Any:
    try:
        body = resp.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        return body.get("code") or body.get("error_code")
    return None
