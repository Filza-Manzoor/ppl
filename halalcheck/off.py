"""Open Food Facts client. The database is free and open and needs no API key.

Be kind to it: cache results, keep search volume low, and send a descriptive
User-Agent. See https://openfoodfacts.github.io/openfoodfacts-server/api/
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

BASE_URL = "https://world.openfoodfacts.org"
USER_AGENT = "Bayan/0.1 (open-source student project)"
TIMEOUT = 10
FIELDS = (
    "code",
    "product_name",
    "brands",
    "quantity",
    "countries_tags",
    "ingredients_text",
    "ingredients_text_en",
    "ingredients_tags",
    "additives_tags",
    "labels_tags",
    "image_front_small_url",
)

# Display name -> Open Food Facts country tag.
COUNTRIES: dict[str, str | None] = {
    "Any country": None,
    "United States": "united-states",
    "Canada": "canada",
    "United Kingdom": "united-kingdom",
    "Pakistan": "pakistan",
    "India": "india",
    "Bangladesh": "bangladesh",
    "United Arab Emirates": "united-arab-emirates",
    "Saudi Arabia": "saudi-arabia",
    "Qatar": "qatar",
    "Egypt": "egypt",
    "Turkey": "turkey",
    "Malaysia": "malaysia",
    "Indonesia": "indonesia",
    "Singapore": "singapore",
    "Australia": "australia",
    "France": "france",
    "Germany": "germany",
}


class OFFError(RuntimeError):
    """Raised with a message that is safe to show to a user."""


@dataclass
class Product:
    code: str = ""
    name: str = ""
    brands: str = ""
    quantity: str = ""
    countries: list[str] = field(default_factory=list)
    ingredients_text: str = ""
    ingredients_tags: list[str] = field(default_factory=list)
    additives_tags: list[str] = field(default_factory=list)
    labels_tags: list[str] = field(default_factory=list)
    image_url: str = ""

    @property
    def has_ingredients(self) -> bool:
        return bool(self.ingredients_text.strip() or self.ingredients_tags)

    def sold_in(self, country_tag: str | None) -> bool:
        return not country_tag or not self.countries or country_tag in self.countries


# ---------------------------------------------------------------- barcodes


def gtin_check_digit_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_barcode(raw: str | None) -> str | None:
    """Keep digits only. Returns None unless the length looks like a GTIN."""
    digits = re.sub(r"\D", "", raw or "")
    return digits if len(digits) in (8, 12, 13, 14) else None


# ---------------------------------------------------------------- requests


def _get(url: str, params: dict, session=None) -> dict | None:
    client = session or requests
    try:
        response = client.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise OFFError("Could not reach Open Food Facts. Try again in a minute.") from exc
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise OFFError(f"Open Food Facts answered with an error ({response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        raise OFFError("Open Food Facts sent a reply this app could not read.") from exc


def _tags(values) -> list[str]:
    return [str(v) for v in (values or []) if v]


def parse_product(raw: dict) -> Product:
    countries = [str(t).split(":")[-1] for t in _tags(raw.get("countries_tags"))]
    return Product(
        code=str(raw.get("code") or ""),
        name=str(raw.get("product_name") or "").strip(),
        brands=str(raw.get("brands") or "").strip(),
        quantity=str(raw.get("quantity") or "").strip(),
        countries=countries,
        ingredients_text=str(raw.get("ingredients_text_en") or raw.get("ingredients_text") or "").strip(),
        ingredients_tags=_tags(raw.get("ingredients_tags")),
        additives_tags=_tags(raw.get("additives_tags")),
        labels_tags=_tags(raw.get("labels_tags")),
        image_url=str(raw.get("image_front_small_url") or ""),
    )


def get_product(barcode: str, session=None) -> Product | None:
    """Look up one product by barcode. Returns None when it is not listed."""
    code = normalize_barcode(barcode)
    if code is None:
        raise OFFError("That does not look like a barcode. Use 8, 12, 13 or 14 digits.")
    if len(code) == 12:  # UPC-A is stored as EAN-13 with a leading zero
        code = "0" + code
    data = _get(
        f"{BASE_URL}/api/v2/product/{code}.json",
        {"fields": ",".join(FIELDS)},
        session,
    )
    if not data or data.get("status") != 1 or not data.get("product"):
        return None
    product = parse_product(data["product"])
    if not product.code:
        product.code = code
    return product


def search_products(query: str, *, country_tag: str | None = None, limit: int = 5, session=None) -> list[Product]:
    """Search by name. Treat results as a starting point, never the final answer."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": max(1, min(limit, 20)),
        "fields": ",".join(FIELDS),
    }
    if country_tag:
        params.update({"tagtype_0": "countries", "tag_contains_0": "contains", "tag_0": country_tag})
    data = _get(f"{BASE_URL}/cgi/search.pl", params, session)
    products = [parse_product(p) for p in (data or {}).get("products", [])]
    return [p for p in products if p.name or p.code][:limit]
