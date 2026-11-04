import base64
import io
import json

import pytest
import requests
from PIL import Image

from halalcheck import vision


def jpeg_bytes(size=(50, 40)):
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="JPEG")
    return out.getvalue()


class FakeResponse:
    def __init__(self, status=200, text="{}", raw=None):
        self.status_code = status
        self._raw = raw if raw is not None else {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def json(self):
        return self._raw


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, headers, json))
        if self.error:
            raise self.error
        return self.response


def reply(payload):
    return FakeSession(FakeResponse(text=json.dumps(payload)))


def test_parse_json_handles_fences_and_noise():
    assert vision.parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert vision.parse_json_reply('Sure! {"a": 1} Hope that helps') == {"a": 1}
    for bad in ("", "no json", "[1, 2]", "{broken"):
        with pytest.raises(vision.VisionError):
            vision.parse_json_reply(bad)


def test_prepare_image_resizes_and_rejects_junk():
    big = jpeg_bytes((3000, 2000))
    data, mime = vision.prepare_image(big)
    assert mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(data)).size) <= vision.MAX_SIDE
    with pytest.raises(vision.VisionError):
        vision.prepare_image(b"not an image")


def test_prepare_image_strips_exif():
    image = Image.new("RGB", (20, 20), "red")
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    cleaned, _ = vision.prepare_image(out.getvalue())
    assert b"SecretPhoneMaker" not in cleaned


def test_no_key_means_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(vision.VisionError, match="API key"):
        vision.read_label(jpeg_bytes())


def test_read_label_success_and_request_shape():
    session = reply({"readable": True, "product_name": "Chips", "ingredients_text": "Potatoes, salt", "halal_logo_seen": True})
    result = vision.read_label(jpeg_bytes(), api_key="k", model="m1", session=session)
    assert result.readable and result.halal_logo_seen
    assert result.ingredients_text == "Potatoes, salt"
    url, headers, body = session.calls[0]
    assert url.endswith("/models/m1:generateContent")
    assert headers["x-goog-api-key"] == "k"
    assert base64.b64decode(body["contents"][0]["parts"][1]["inline_data"]["data"])


def test_read_label_unreadable_when_text_empty():
    session = reply({"readable": True, "ingredients_text": "  ", "product_name": "x"})
    assert not vision.read_label(jpeg_bytes(), api_key="k", session=session).readable


def test_label_text_is_truncated_and_non_strings_ignored():
    session = reply({"readable": True, "ingredients_text": "a" * 9000, "product_name": 5})
    result = vision.read_label(jpeg_bytes(), api_key="k", session=session)
    assert len(result.ingredients_text) == vision.MAX_TEXT
    assert result.product_name == ""


def test_barcode_requires_valid_check_digit():
    good = reply({"digits": "5449 0000 00996"})
    assert vision.read_barcode(jpeg_bytes(), api_key="k", session=good) == "5449000000996"
    bad = reply({"digits": "5449000000995"})
    assert vision.read_barcode(jpeg_bytes(), api_key="k", session=bad) is None
    short = reply({"digits": "123"})
    assert vision.read_barcode(jpeg_bytes(), api_key="k", session=short) is None


def test_identify_dish():
    session = reply({"is_food": True, "dish_name": "Biryani", "likely_ingredients": ["rice", "chicken", "", 7]})
    dish = vision.identify_dish(jpeg_bytes(), api_key="k", session=session)
    assert dish.is_food and dish.dish_name == "Biryani"
    assert dish.ingredients == ["rice", "chicken"]


def test_dish_bad_ingredient_type():
    session = reply({"is_food": True, "dish_name": "x", "likely_ingredients": "rice"})
    assert vision.identify_dish(jpeg_bytes(), api_key="k", session=session).ingredients == []


@pytest.mark.parametrize("status", [429, 400, 403, 500])
def test_http_errors_become_visionerror(status):
    with pytest.raises(vision.VisionError):
        vision.read_label(jpeg_bytes(), api_key="k", session=FakeSession(FakeResponse(status)))


def test_network_error_and_empty_candidates():
    with pytest.raises(vision.VisionError):
        vision.read_label(jpeg_bytes(), api_key="k", session=FakeSession(error=requests.ConnectionError()))
    with pytest.raises(vision.VisionError):
        vision.read_label(jpeg_bytes(), api_key="k", session=FakeSession(FakeResponse(raw={"candidates": []})))
