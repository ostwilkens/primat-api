"""A store's current price drops.

    export PRIMAT_API_KEY=primat_live_...
    python3 examples/store_deals.py willys:2193     # a chain:store_id key
    python3 examples/store_deals.py Uppsala         # first store the site picks there

Lists /api/v3/deals for one store: the API's discount_ratio, the previous
price, the regular price now and the effective price (the least price a
card-carrying shopper pays right now), plus member price, multibuy and
campaign when the store has them.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from primat_api import Primat, PrimatError  # noqa: E402


LIMIT = 20


def money(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def facts(prices: dict) -> str:
    """Member price, multibuy and campaign, when the store has them."""
    out = []
    if prices.get("member") is not None:
        out.append(f"member {money(prices['member'])}")
    multi = prices.get("multiprice") or {}
    if multi.get("price") is not None and multi.get("quantity"):
        # multiprice.price is the PER-UNIT price when buying `quantity`.
        total = multi["price"] * multi["quantity"]
        out.append(f"{multi['quantity']} for {money(total)}")
    offer = prices.get("offer")
    if offer:
        until = (offer.get("valid_until") or "")[:10]
        out.append(f"offer {offer.get('label') or money(offer.get('price'))}"
                   + (f" until {until}" if until else ""))
    return ", ".join(out)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    target = sys.argv[1]
    try:
        api = Primat()  # the key comes from PRIMAT_API_KEY
        if ":" in target:
            store, label = target, target
        else:
            resolved = api.resolve(place=target)
            store = resolved["default_selection"][0]
            name = next((s["name"] for s in resolved["stores"]
                         if s["key"] == store), store)
            label = f"{name} ({store})"
        found = api.deals(store, limit=LIMIT)
    except (PrimatError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Price drops at {label}, {found['count']} rows (limit {LIMIT}):")
    print(f"{'drop':>5}  {'previous':>8}  {'regular':>8}  {'effective':>9}"
          "  product")
    for row in found["data"]:
        prices = row["prices"]
        extra = facts(prices)
        print(f"{-row['discount_ratio']:>5.0%}  "
              f"{money(prices.get('previous')):>8}  "
              f"{money(prices.get('regular')):>8}  "
              f"{money(prices.get('effective')):>9}  {row['name']}"
              + (f"  [{extra}]" if extra else ""))
    credit = found.get("attribution") or {}
    print(f"Prices in kr. {credit.get('text', '')} ({credit.get('url', '')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
