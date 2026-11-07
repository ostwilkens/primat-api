"""Compare one product's price across the stores near a place.

    export PRIMAT_API_KEY=primat_live_...
    python3 examples/compare_nearby.py Uppsala "mellanmjölk eko"

Resolves the place to the store selection the site itself would pick there,
searches those stores and takes the matching product (GTIN) that most of
them carry. Prints that product's price facts per store, ordered by the
effective price: the least price a card-carrying shopper pays right now.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from primat_api import Primat, PrimatError  # noqa: E402


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
    if len(sys.argv) != 3:
        print(__doc__.strip())
        return 2
    place, query = sys.argv[1], sys.argv[2]
    try:
        api = Primat()  # the key comes from PRIMAT_API_KEY
        resolved = api.resolve(place=place)
        stores = resolved["default_selection"]
        found = api.products(query, stores=stores, limit=100)
        rows = found["data"]
    except (PrimatError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    carried = Counter(row["gtin"] for row in rows if row.get("gtin"))
    if not carried:
        print(f"No product with a GTIN matches {query!r} in the "
              f"{len(stores)} stores near {place}.")
        return 1
    # Most stores first; among equals, the one the search ranked first
    # (most_common keeps first-seen order on ties).
    gtin = carried.most_common(1)[0][0]
    same = [row for row in rows if row.get("gtin") == gtin]
    same.sort(key=lambda row: (row["prices"].get("effective") is None,
                               row["prices"].get("effective") or 0))

    names = {s["key"]: f"{s['name']} ({s['km']} km)"
             for s in resolved["stores"]}
    print(f"{same[0]['name']} (GTIN {gtin}): {len(same)} of {len(stores)} "
          f"stores near {resolved['place']['label']}")
    print(f"{'effective':>9}  {'regular':>8}  store")
    for row in same:
        prices = row["prices"]
        key = f"{row['chain']}:{row['store_id']}"
        extra = facts(prices)
        print(f"{money(prices.get('effective')):>9}  "
              f"{money(prices.get('regular')):>8}  {names.get(key, key)}"
              + (f"  [{extra}]" if extra else ""))
    credit = found.get("attribution") or {}
    print(f"Prices in kr. {credit.get('text', '')} ({credit.get('url', '')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
