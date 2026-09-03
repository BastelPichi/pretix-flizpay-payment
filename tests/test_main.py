import hashlib
import hmac
import json

import pytest

from pretix_flizpay import flizpay_client


def test_webhook_signature_verification():
    body = b'{"status":"completed"}'
    secret = "webhook-secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert flizpay_client.verify_webhook_signature(body, signature, secret)
    assert not flizpay_client.verify_webhook_signature(body, "wrong", secret)


def test_parse_webhook_requires_json_object():
    with pytest.raises(flizpay_client.FlizpayApiError):
        flizpay_client.parse_webhook(json.dumps(["invalid"]).encode())


def test_get_webhook_key_uses_business_endpoint(monkeypatch):
    response = type("Response", (), {
        "status_code": 200,
        "json": lambda self: {"webhookKey": "webhook-secret"},
    })()
    captured = {}

    def request(method, url, **kwargs):
        captured.update(method=method, url=url, kwargs=kwargs)
        return response

    monkeypatch.setattr(flizpay_client.requests, "request", request)

    assert flizpay_client.get_webhook_key("api-key") == "webhook-secret"
    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.flizpay.de/business/generate-webhook-key"
    assert captured["kwargs"]["headers"]["X-API-Key"] == "api-key"


def test_create_transaction_sends_major_currency_amount(monkeypatch):
    captured = {}

    def request(method, url, **kwargs):
        captured.update(method=method, url=url, kwargs=kwargs)
        response = type("Response", (), {
            "status_code": 200,
            "json": lambda self: {"redirectUrl": "https://checkout.flizpay.de/test"},
        })()
        return response

    monkeypatch.setattr(flizpay_client.requests, "request", request)

    flizpay_client.create_transaction(
        "api-key", "0.01", "EUR", "order-1", "https://example.test/success",
        "https://example.test/failure", {},
    )

    assert captured["kwargs"]["json"]["amount"] == 0.01
