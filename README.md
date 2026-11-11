# Primat API

Primat API är ett API för svenska matpriser: dagliga priser per butik från
ICA, Coop, Willys, Hemköp, Lidl och City Gross. Det här är Primats eget repo
för API:t, med OpenAPI-specifikationen, en liten Python-klient utan beroenden
och två exempel.

Dokumentation: [primat.nu/api](https://primat.nu/api) ·
Specifikation: [openapi.json](https://primat.nu/api/v3/openapi.json) ·
Nivåer och priser: [primat.nu/data](https://primat.nu/data) ·
Villkor: [primat.nu/villkor](https://primat.nu/villkor)

[English below](#english)

## Vad API:t innehåller

- Priserna som kedjorna själva publicerar per butik, insamlade varje dag.
- 2 837 butiker med aktuella priser och 214 388 produkter, enligt
  [primat.nu/press](https://primat.nu/press) den 7 november 2026. Aktuella
  siffror finns där.
- Varje butik har en täckningsnivå: `full` är hela sortimentet med priser,
  `offers_only` är bara kampanjpriser, där inget sortimentsflöde finns.
- Varorna har GTIN/EAN, nyckeln för samma vara i olika butiker (null där
  kedjan inte publicerar någon).
- Prishistorik sedan december 2025. Historiken via API:t ingår i nivåerna
  Pro och Byrå, se [primat.nu/data](https://primat.nu/data).

### En prisrad

Varje vara i en butik bär prisfakta under `prices`:

| Fält | Betydelse |
| --- | --- |
| `regular` | Ordinarie pris, det alla betalar (publika kampanjer inräknade). |
| `member` | Medlemspris, satt bara medan ett medlemspris gäller. |
| `multiprice`, `member_multiprice` | Styckpris vid köp av `quantity` stycken: `price` 7 med `quantity` 5 betyder "5 för 35 kr". |
| `comparison` | Jämförpris per kg, l, st eller m, räknat på ordinarie pris. |
| `offer` | Kampanjen bakom prissättningen just nu (pris, etikett, giltighetstid), null när ingen gäller. |
| `effective` | Det lägsta pris en kund med medlemskort betalar just nu. En sammanställning för enkelhetens skull: kombinera fälten själv när det ska vara exakt. |
| `previous` | Tidigare pris, i svaren från `/api/v3/deals`. |

Tidsstämplarna följer en ändringslogg: `changed_at` är när priset senast
ändrades, `confirmed_at` är när butiken senast kontrollerades. Ingen ändring
sedan `changed_at` betyder bekräftat oförändrat, inte omätt. I historiken
står de dagar priset ändrades: ett datum som saknas betyder oförändrat, och
`price` null betyder att varan inte längre finns i butiken.

## Nyckel

Nya konton får en testnyckel som gäller en timme. Den skapas med ett anrop,
utan mejlverifiering, och visas en gång i svaret:

```sh
curl -X POST https://primat.nu/api/v3/signup \
  -H 'Content-Type: application/json' \
  -d '{"email": "du@exempel.se"}'
```

Fortsatt åtkomst börjar med 30 dagars gratis provperiod på nivån App (kort
krävs): logga in på [primat.nu/data](https://primat.nu/data) med samma
adress och starta den. Samma nyckel fortsätter då att fungera. Nivåer och
priser står på [primat.nu/data](https://primat.nu/data).

Nyckeln skickas som `Authorization: Bearer <nyckel>` eller
`X-API-Key: <nyckel>`. Hemliga nycklar (`primat_live_…`) används på servern.
Publika nycklar (`primat_pk_…`) kan byggas in i webbappar: de är låsta till
dina domäner och kan bara läsa. Nycklarna hanteras på
[primat.nu/konto](https://primat.nu/konto).

## Snabbstart med curl

```sh
export PRIMAT_API_KEY='<din nyckel>'

# Butikerna vid en ort, med sajtens eget standardval:
curl -H "Authorization: Bearer $PRIMAT_API_KEY" \
  'https://primat.nu/api/v3/stores/resolve?place=Uppsala'

# En sökning i två av butikerna:
curl -H "Authorization: Bearer $PRIMAT_API_KEY" \
  'https://primat.nu/api/v3/products?q=banan&stores=willys:2193,hemkop:4256&limit=5'
```

`default_selection` i svaret från `stores/resolve` är en lista med
`chain:store_id`, klar att använda som `stores=`. Hela sortiment hämtas från
`/api/v3/prices`, i sidor som följs med `next_cursor` tills den är null. Med
`offers=1` ger samma anrop bara raderna där `offer_price` är satt: butikernas
aktuella kampanjer, medlemskampanjerna inräknade, utan resten av sortimentet.

```sh
# Bara kampanjerna i en butik:
curl -H "Authorization: Bearer $PRIMAT_API_KEY" \
  'https://primat.nu/api/v3/prices?stores=willys:2193&offers=1'
```

Varje rad bär varans kategori i `category`: kedjans egen kategoriväg med
kedjans egna namn och huvudkategorin först, till exempel
`Kött, chark & fågel > Kött > Fläsk`. Samma värde står på varuraderna i
`/api/v3/products`. Varje kedja har sitt eget träd, och `category` är null
när kedjan inte anger någon kategori.

`/api/v3/deals` ger sänkta ordinarie priser med tidigare pris, på varor utan
kampanj, och `/api/v3/cheap` varorna med lägst jämförpris. Alla anrop:
[primat.nu/api](https://primat.nu/api).

Ett svar som inte är 2xx har formen `{"error": {"code", "message"}}`, med
`Retry-After` eller `WWW-Authenticate` när det är relevant. Felkoderna står i
[specifikationen](https://primat.nu/api/v3/openapi.json).

## Python

`primat_api.py` använder bara standardbiblioteket och kräver Python 3.10
eller senare. Kopiera filen eller klona repot.

```python
from primat_api import Primat

api = Primat()  # nyckeln läses från PRIMAT_API_KEY

place = api.resolve(place="Uppsala")
stores = place["default_selection"]

for row in api.products("mellanmjölk", stores=stores, limit=20)["data"]:
    prices = row["prices"]
    print(row["chain"], row["store_id"], row["name"],
          prices["regular"], prices["effective"])

# Hela sortimentet i en butik, sida för sida:
for row in api.iter_prices("willys:2193", limit=500):
    print(row["product_id"], row["name"], row["price"])

# Bara butikens aktuella kampanjer, med varans kategori:
for row in api.iter_prices("willys:2193", offers=True):
    print(row["category"], row["name"], row["offer_price"],
          row["offer_label"], row["offer_valid_until"])
```

| Metod | Anrop |
| --- | --- |
| `me()` | `GET /api/v3/me` |
| `stores(all=False)` | `GET /api/v3/stores` |
| `resolve(place, postcode=, lat=, lon=)` | `GET /api/v3/stores/resolve` |
| `products(q, stores=, limit=)` | `GET /api/v3/products` |
| `product(chain, store_id, product_id)` | `GET /api/v3/products/{chain}/{store_id}/{product_id}` |
| `prices(stores, cursor=, limit=, offers=)`, `iter_prices(stores, limit=, offers=)` | `GET /api/v3/prices` |
| `deals(stores, limit=, lookback_days=)` | `GET /api/v3/deals` |
| `cheap(stores, limit=)` | `GET /api/v3/cheap` |
| `batch(lookups, stores=)` | `POST /api/v3/batch` |
| `history(chain, store_id, product_id)`, `history_gtin(gtin, stores=)` | `GET /api/v3/history/...` |

Varje metod returnerar API:ets JSON-svar som en dict. Ett svar som inte är
2xx blir ett `PrimatError` med `status`, `code`, `message`, `details` och
`retry_after`. Underklasserna är `AuthenticationError` (401),
`PaymentRequiredError` (402: `trial_required`, `tryout_expired`,
`tryout_used`), `PermissionDeniedError` (403, till exempel
`upgrade_required`), `NotFoundError` (404) och `RateLimitError` (429). Vid
429 `rate_limited` och vid 503 väntar klienten den tid som `Retry-After`
anger, om den är högst en minut, och försöker sedan igen, högst två gånger.

Exempel i [examples/](examples):

```sh
export PRIMAT_API_KEY='<din nyckel>'
python3 examples/compare_nearby.py Uppsala "mellanmjölk eko"   # en vara i butikerna vid en ort
python3 examples/store_deals.py Uppsala                        # prissänkningar i en butik
```

Specifikationen i [openapi.json](openapi.json) är en kopia av
https://primat.nu/api/v3/openapi.json och uppdateras med
`python3 scripts/update_openapi.py`.

## Synk: din egen databas

Med Synk har du alla aktuella priser i en egen databas, i SQLite, DuckDB
eller Postgres, eller som Parquet-filer direkt från flödet. Du hämtar en
ögonblicksbild en gång och sedan bara ändringarna, som kommer efter varje
prisvåg (de flesta mellan midnatt och nio på morgonen). Synk är en egen nivå
och ingår också i Pro och Byrå.

```sh
export PRIMAT_API_KEY='<din nyckel>'
uv run https://primat.nu/api/synk/primat-sync.py sqlite:///primat.sqlite
```

Kör samma kommando regelbundet, till exempel varje timme med cron, så hålls
databasen aktuell: en körning hämtar bara det som ändrats sedan förra
körningen. Med `--watch` går klienten hela tiden. Hur flödet fungerar:
[primat.nu/api#synk](https://primat.nu/api#synk).

## Villkor och licens

Koden i det här repot är MIT-licensierad, se [LICENSE](LICENSE).

Datat är inte öppen data. Det som API:t och Synk levererar regleras av
villkoren på [primat.nu/villkor](https://primat.nu/villkor). Där står bland
annat:

- Appar, tjänster och analyser får byggas på datat, även kommersiellt.
- Program hämtar data via API:t, inte genom att läsa sidorna på primat.nu.
- Datat får inte återförsäljas, vidaredistribueras eller tillgängliggöras som
  dataset, spegel eller eget prisdata-API, oavsett nivå.
- En Synk-databas är för ditt eget bruk.

Primat är under utveckling. Strukturen, datat och prismodellen kan ändras,
och då meddelas användarna via e-post.

Frågor: [kontakt@primat.nu](mailto:kontakt@primat.nu).

---

## English

The Primat API serves daily per-store Swedish grocery prices from ICA, Coop,
Willys, Hemköp, Lidl and City Gross: regular, member, multibuy and campaign
prices, GTIN/EAN-keyed, with change-log history since December 2025. This is
Primat's own repository for the API: the OpenAPI spec, a small
dependency-free Python client and two examples.

- [primat.nu/press](https://primat.nu/press) lists 2 837 stores with current
  prices (7 November 2026). Each store has a coverage tier: `full` (complete
  assortment with prices) or `offers_only` (campaign prices only).
- Price facts under `prices`: `regular` (what everyone pays, public campaigns
  included), `member`, `multiprice` and `member_multiprice` (per-unit price
  when buying `quantity`), `comparison` (unit price on the regular price),
  `offer` (the active campaign), `effective` (the least price a card-carrying
  shopper pays right now) and `previous` (on `/api/v3/deals`).
- `changed_at` is when the price last changed, `confirmed_at` when the store
  was last checked. No change since `changed_at` means confirmed unchanged,
  not unmeasured.

**Key.** A key in one call, no email round-trip:

```sh
curl -X POST https://primat.nu/api/v3/signup \
  -H 'Content-Type: application/json' \
  -d '{"email": "you@example.com"}'
```

The tryout key works for one hour. Ongoing access starts with a 30-day free
App trial (card required): log in at [primat.nu/data](https://primat.nu/data)
with the same address, and the key keeps working once the trial starts. Send
the key as `Authorization: Bearer <key>` or `X-API-Key: <key>`. Plans and
prices: [primat.nu/data](https://primat.nu/data).

**Quickstart.**

```sh
export PRIMAT_API_KEY='<your key>'
curl -H "Authorization: Bearer $PRIMAT_API_KEY" \
  'https://primat.nu/api/v3/stores/resolve?place=Uppsala'
curl -H "Authorization: Bearer $PRIMAT_API_KEY" \
  'https://primat.nu/api/v3/products?q=banan&stores=willys:2193,hemkop:4256&limit=5'
```

Full store catalogs come from `/api/v3/prices` as cursor pages: follow
`next_cursor` until it is null. With `offers=1` the same call returns only the
rows where `offer_price` is set: the stores' current campaigns, member
campaigns included, without the rest of the catalog
(`/api/v3/prices?stores=willys:2193&offers=1`). Every row carries the product's
`category`: the chain's own category path in the chain's own names, top level
first (`Kött, chark & fågel > Kött > Fläsk`), the same value as on the product
rows, and null when the chain states none. `/api/v3/deals` gives drops of
the ordinary price on products without a campaign.

**Python.** `primat_api.py` is standard library only, Python 3.10+. See the
Python section above for the methods and the errors it raises (401, 402 with
`trial_required`, `tryout_expired` or `tryout_used`, 403, 404, 429 with
`Retry-After`).

```python
from primat_api import Primat

api = Primat()  # reads PRIMAT_API_KEY
stores = api.resolve(place="Uppsala")["default_selection"]
for row in api.products("mellanmjölk", stores=stores, limit=20)["data"]:
    print(row["chain"], row["store_id"], row["name"], row["prices"]["regular"])
```

**Synk.** Synk keeps all current prices in a database of your own, in
SQLite, DuckDB or Postgres, or as Parquet files straight from the feed. You
fetch a snapshot once and then only the changes, which arrive after each
price wave (most between midnight and 09:00 Swedish time). Synk is a plan of
its own and is also included in Pro and Byrå.

```sh
uv run https://primat.nu/api/synk/primat-sync.py sqlite:///primat.sqlite
```

**Terms.** The code in this repository is MIT licensed. The data is not open
data: its use is governed by [primat.nu/villkor](https://primat.nu/villkor)
(in Swedish). Apps, services and analyses built on the data are welcome,
commercial ones included. Programs fetch through the API, not by reading the
pages. The data may not be resold, redistributed or made available as a
dataset, mirror or price-data API of your own, on any plan. Primat is under
development: the structure, the data and the pricing model may change, and
users are told by email when they do.

Docs: [primat.nu/api](https://primat.nu/api) ·
Spec: [openapi.json](https://primat.nu/api/v3/openapi.json) ·
Plans and prices: [primat.nu/data](https://primat.nu/data) ·
Terms: [primat.nu/villkor](https://primat.nu/villkor) ·
Contact: [kontakt@primat.nu](mailto:kontakt@primat.nu)
