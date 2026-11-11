"""Minimal Python client for the Primat API.

Daily per-store Swedish grocery prices from ICA, Coop, Willys, Hemköp, Lidl
and City Gross. Docs: https://primat.nu/api. Contract:
https://primat.nu/api/v3/openapi.json (a copy sits next to this file).

Standard library only, Python 3.10 or later.

    from primat_api import Primat

    api = Primat()                          # key from PRIMAT_API_KEY
    place = api.resolve(place="Uppsala")
    stores = place["default_selection"]     # ready for stores=
    for row in api.products("kaffe", stores=stores, limit=10)["data"]:
        print(row["chain"], row["store_id"], row["name"],
              row["prices"]["regular"])

Every method returns the API's JSON answer as a dict. A non-2xx answer
raises PrimatError, or one of its subclasses, carrying the API's error code
and message.
"""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any

__all__ = [
    "Primat",
    "PrimatError",
    "AuthenticationError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "NotFoundError",
    "RateLimitError",
]
__version__ = "0.2.0"

BASE_URL = "https://primat.nu"
USER_AGENT = f"primat-api-python/{__version__}"

Stores = str | Iterable[str] | None
"""A store scope: "willys:2103,citygross:3204" or a list of chain:store_id
keys, at most 15 per call (6 for history_gtin)."""


class PrimatError(Exception):
    """A non-2xx answer from the API.

    status:      the HTTP status.
    code:        the API's machine code, e.g. invalid_api_key (the Error
                 schema in openapi.json lists them).
    message:     the API's English text, which names the way forward.
    details:     the whole error object; some codes add fields, such as
                 trial_url.
    retry_after: the Retry-After header in seconds, or None.
    """

    def __init__(self, status: int, code: str, message: str, *,
                 details: dict[str, Any] | None = None,
                 retry_after: int | None = None) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.retry_after = retry_after


class AuthenticationError(PrimatError):
    """401 invalid_api_key: the key is missing, wrong or revoked."""


class PaymentRequiredError(PrimatError):
    """402 trial_required, tryout_expired or tryout_used: the account needs
    a plan. details["trial_url"], when present, is where the account owner
    starts the trial."""


class PermissionDeniedError(PrimatError):
    """403, e.g. upgrade_required (the plan does not include the feature),
    origin_not_allowed, read_only_key or secret_key_required."""


class NotFoundError(PrimatError):
    """404, e.g. not_found, product_not_found or place_not_found."""


class RateLimitError(PrimatError):
    """429, e.g. rate_limited (per minute) or daily_row_budget_exceeded.
    retry_after says how many seconds to wait."""


_ERROR_CLASSES: dict[int, type[PrimatError]] = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    429: RateLimitError,
}


class Primat:
    """Client for https://primat.nu/api/v3.

    api_key:     a secret key (primat_live_...); default: the environment
                 variable PRIMAT_API_KEY. Keys: https://primat.nu/data.
    timeout:     seconds per HTTP request.
    max_retries: how many times a 429 rate_limited or a 503 is retried, after
                 the wait its Retry-After header names, when that wait is at
                 most max_wait seconds. Anything else raises at once.
    """

    def __init__(self, api_key: str | None = None, *,
                 base_url: str = BASE_URL, timeout: float = 60,
                 max_retries: int = 2, max_wait: float = 60,
                 user_agent: str = USER_AGENT) -> None:
        key = (api_key or os.environ.get("PRIMAT_API_KEY") or "").strip()
        if not key:
            raise ValueError(
                "No API key: set PRIMAT_API_KEY or pass api_key=. "
                "Keys: https://primat.nu/data")
        self._key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_wait = max_wait
        self.user_agent = user_agent

    def __repr__(self) -> str:
        return f"Primat(base_url={self.base_url!r})"

    # -- account ---------------------------------------------------------

    def me(self) -> dict:
        """GET /api/v3/me: account, plan limits and today's usage."""
        return self._get("/api/v3/me")

    # -- stores ----------------------------------------------------------

    def stores(self, *, all: bool = False) -> dict:
        """GET /api/v3/stores: the store register, data[Store].

        By default only stores with price data; all=True adds the
        register-only stores."""
        return self._get("/api/v3/stores", {"all": 1 if all else None})

    def resolve(self, place: str | None = None, *,
                postcode: str | None = None, lat: float | None = None,
                lon: float | None = None) -> dict:
        """GET /api/v3/stores/resolve: ranked nearby stores for ONE of
        place (locality name or 5-digit postcode), postcode, or lat and lon.

        The answer's default_selection is a list of chain:store_id keys
        ready for the stores argument of the other methods."""
        return self._get("/api/v3/stores/resolve", {
            "place": place, "postcode": postcode, "lat": lat, "lon": lon})

    # -- products and prices ---------------------------------------------

    def products(self, q: str, *, stores: Stores = None,
                 limit: int | None = None) -> dict:
        """GET /api/v3/products: ranked product search, data[Product].

        With stores: every carrying (store, product) row in those stores.
        Without: one row per product at its cheapest carrying store
        nationally. Search is bounded and does not paginate; full store
        catalogs come from prices() and iter_prices()."""
        return self._get("/api/v3/products", {
            "q": q, "stores": _scope(stores), "limit": limit})

    def product(self, chain: str, store_id: str, product_id: str) -> dict:
        """GET /api/v3/products/{chain}/{store_id}/{product_id}: one
        product at one store."""
        return self._get(_path("/api/v3/products", chain, store_id,
                               product_id))

    def prices(self, stores: Stores, *, cursor: str | None = None,
               limit: int | None = None, offers: bool = False) -> dict:
        """GET /api/v3/prices: one keyset page of full store catalogs,
        data[PriceRow] and next_cursor (null on the last page).

        offers=True (offers=1) keeps only the rows whose offer_price is set:
        the stores' current campaigns, member campaigns included, without
        the rest of the catalog. Same row shape, order and cursor.

        Every row carries the product's category: the chain's own category
        path in the chain's own names, top level first, null when the chain
        states none."""
        return self._get("/api/v3/prices", {
            "stores": _scope(stores), "cursor": cursor, "limit": limit,
            "offers": 1 if offers else None})

    def iter_prices(self, stores: Stores, *, limit: int | None = None,
                    offers: bool = False) -> Iterator[dict]:
        """Every current price row of the stores: prices() pages, following
        next_cursor until it is null. limit is the page size; offers=True
        yields only the rows with a current campaign price."""
        cursor = None
        while True:
            page = self.prices(stores, cursor=cursor, limit=limit,
                               offers=offers)
            yield from page.get("data") or []
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def deals(self, stores: Stores = None, *, limit: int | None = None,
              lookback_days: int | None = None) -> dict:
        """GET /api/v3/deals: drops of the ordinary price on products
        without a current campaign, data[Product] with prices.previous and
        discount_ratio. A store's campaigns: iter_prices(offers=True)."""
        return self._get("/api/v3/deals", {
            "stores": _scope(stores), "limit": limit,
            "lookback_days": lookback_days})

    def cheap(self, stores: Stores = None, *,
              limit: int | None = None) -> dict:
        """GET /api/v3/cheap: products ranked by comparison (unit) price."""
        return self._get("/api/v3/cheap", {
            "stores": _scope(stores), "limit": limit})

    def batch(self, lookups: list[dict], *, stores: Stores = None) -> dict:
        """POST /api/v3/batch: up to 100 lookups in one call. Each lookup
        is {"gtin": ...}, {"chain", "store_id", "product_id"} or
        {"chain", "product_id"}. The answer's data holds one entry per
        lookup: {lookup, count, results[Product]}."""
        body: dict[str, Any] = {"lookups": list(lookups)}
        scope = _scope(stores)
        if scope:
            body["stores"] = scope
        return self._request("POST", "/api/v3/batch", body=body)

    # -- history (Pro and Byrå) -----------------------------------------

    def history(self, chain: str, store_id: str, product_id: str) -> dict:
        """GET /api/v3/history/{chain}/{store_id}/{product_id}: the days a
        product's price changed at one store (HistoryResult). Plans without
        history answer 403 upgrade_required."""
        return self._get(_path("/api/v3/history", chain, store_id,
                               product_id))

    def history_gtin(self, gtin: str, *, stores: Stores = None) -> dict:
        """GET /api/v3/history/{gtin}: history across carrying stores, up to
        6 series; by default each chain's cheapest carrying store."""
        return self._get(_path("/api/v3/history", gtin),
                         {"stores": _scope(stores)})

    # -- transport -------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        return self._request("GET", path, params=params)

    def _request(self, method: str, path: str, *,
                 params: dict[str, Any] | None = None,
                 body: Any = None) -> dict:
        url = self.base_url + path
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": self.user_agent,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            request = urllib.request.Request(url, data=data, headers=headers,
                                             method=method)
            try:
                with urllib.request.urlopen(request,
                                            timeout=self.timeout) as resp:
                    return _parse_ok(resp.status, resp.headers, resp.read())
            except urllib.error.HTTPError as exc:
                error = _parse_error(exc.code, exc.headers, exc.read())
            retryable = ((error.status == 429 and error.code == "rate_limited")
                         or error.status == 503)
            if (retryable and attempt < self.max_retries
                    and error.retry_after is not None
                    and error.retry_after <= self.max_wait):
                attempt += 1
                time.sleep(error.retry_after)
                continue
            raise error


def _scope(stores: Stores) -> str | None:
    if stores is not None and not isinstance(stores, str):
        stores = ",".join(stores)
    return stores or None


def _path(prefix: str, *segments: str) -> str:
    return "/".join([prefix] + [urllib.parse.quote(str(s), safe="")
                                for s in segments])


def _body_text(headers, raw: bytes) -> str:
    if (headers.get("Content-Encoding") or "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _parse_ok(status: int, headers, raw: bytes) -> dict:
    text = _body_text(headers, raw)
    try:
        return json.loads(text)
    except ValueError:
        raise PrimatError(status, "unexpected_response",
                          "The answer was not JSON: " + text[:200]) from None


def _parse_error(status: int, headers, raw: bytes) -> PrimatError:
    text = _body_text(headers, raw)
    try:
        error = json.loads(text)["error"]
        code, message = error["code"], error["message"]
    except (ValueError, KeyError, TypeError):
        # Not the API's error shape: a proxy or network answer.
        error, code, message = {}, "http_error", text[:200].strip()
    cls = _ERROR_CLASSES.get(status, PrimatError)
    return cls(status, code, message, details=error,
               retry_after=_seconds(headers.get("Retry-After")))


def _seconds(value: str | None) -> int | None:
    try:
        return max(0, int(float(value))) if value else None
    except ValueError:
        return None
