import pytest
import requests

from halalcheck import off


class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("bad json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        if self.error:
            raise self.error
        return self.response


PRODUCT = {
    "code": "5449000000996",
    "product_name": "Cola",
    "brands": "Acme",
    "countries_tags": ["en:france", "en:united-kingdom"],
    "ingredients_text": "Water, sugar",
    "ingredients_tags": ["en:water", "en:sugar"],
    "additives_tags": ["en:e150d"],
    "labels_tags": [],
}


def test_normalize_barcode():
    assert off.normalize_barcode("5449 0000 00996") == "5449000000996"
    assert off.normalize_barcode("123") is None
    assert off.normalize_barcode(None) is None


def test_check_digit():
    assert off.gtin_check_digit_ok("5449000000996")
    assert not off.gtin_check_digit_ok("5449000000995")


def test_get_product_parses_fields_and_sends_user_agent():
    session = FakeSession(FakeResponse(payload={"status": 1, "product": PRODUCT}))
    product = off.get_product("5449000000996", session)
    assert product.name == "Cola"
    assert product.countries == ["france", "united-kingdom"]
    assert product.has_ingredients
    assert "Bayan" in session.calls[0][2]["User-Agent"]


def test_upca_gets_leading_zero():
    session = FakeSession(FakeResponse(payload={"status": 0}))
    assert off.get_product("012345678905", session) is None
    assert session.calls[0][0].endswith("/0012345678905.json")


def test_not_found_returns_none():
    assert off.get_product("5449000000996", FakeSession(FakeResponse(404))) is None
    assert off.get_product("5449000000996", FakeSession(FakeResponse(payload={"status": 0}))) is None


def test_bad_barcode_raises():
    with pytest.raises(off.OFFError):
        off.get_product("abc")


def test_network_and_server_errors_become_offerror():
    with pytest.raises(off.OFFError):
        off.get_product("5449000000996", FakeSession(error=requests.ConnectionError()))
    with pytest.raises(off.OFFError):
        off.get_product("5449000000996", FakeSession(FakeResponse(500)))
    with pytest.raises(off.OFFError):
        off.get_product("5449000000996", FakeSession(FakeResponse(bad_json=True)))


def test_search_adds_country_filter():
    session = FakeSession(FakeResponse(payload={"products": [PRODUCT]}))
    results = off.search_products("cola", country_tag="united-kingdom", session=session)
    params = session.calls[0][1]
    assert params["tag_0"] == "united-kingdom"
    assert results[0].name == "Cola"


def test_short_search_makes_no_request():
    session = FakeSession(FakeResponse(payload={}))
    assert off.search_products("a", session=session) == []
    assert session.calls == []


def test_sold_in():
    product = off.parse_product(PRODUCT)
    assert product.sold_in("france")
    assert not product.sold_in("pakistan")
    assert product.sold_in(None)
