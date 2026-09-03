import hashlib
import hmac
import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import requests
from django.utils.translation import gettext_lazy as _

FLIZPAY_BASE_URL = "https://api.flizpay.de"


class FlizpayApiError(Exception):
    pass


def _request(method, path, api_key=None, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        response = requests.request(
            method,
            f"{FLIZPAY_BASE_URL}{path}",
            headers=headers,
            timeout=20,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise FlizpayApiError(_("Could not contact FLIZpay.")) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise FlizpayApiError(_("FLIZpay returned an invalid response.")) from exc

    if response.status_code < 200 or response.status_code >= 300:
        message = body.get("message", "") if isinstance(body, dict) else ""
        raise FlizpayApiError(message or _("FLIZpay rejected the request."))
    return body.get("data", body) if isinstance(body, dict) else body


def get_webhook_key(api_key):
    body = _request("GET", "/business/generate-webhook-key", api_key=api_key)
    key = body.get("webhookKey") if isinstance(body, dict) else None
    if not key:
        raise FlizpayApiError(_("FLIZpay did not return a webhook key."))
    return key


def configure_webhook(api_key, webhook_url):
    body = _request(
        "POST",
        "/business/edit",
        api_key=api_key,
        json={"webhookUrl": webhook_url},
    )
   
    configured_url = body.get("webhookUrl") if isinstance(body, dict) else None
    if configured_url != webhook_url:
        raise FlizpayApiError(_("FLIZpay did not accept the webhook URL."))
    return configured_url


def create_transaction(api_key, amount, currency, external_id, success_url, failure_url, metadata):
    body = _request(
        "POST",
        "/transactions",
        api_key=api_key,
        json={
            "amount": float(Decimal(amount).quantize(Decimal("0.01"))),
            "currency": currency,
            "externalId": external_id,
            "successUrl": success_url,
            "failureUrl": failure_url,
            "metadata": metadata,
        },
    )
    redirect_url = body.get("redirectUrl") if isinstance(body, dict) else None
    if not redirect_url:
        raise FlizpayApiError(_("FLIZpay did not return a checkout URL."))
    reference = body.get("reference") if isinstance(body, dict) else None
    if not reference:
        query = parse_qs(urlparse(redirect_url).query)
        reference = (query.get("reference") or [None])[0]
    return {"redirect_url": redirect_url, "reference": reference or external_id}


def get_transaction_status(api_key, reference):
    return _request(
        "GET", f"/transactions/{reference}/status", api_key=api_key
    )


def verify_webhook_signature(raw_body, signature, webhook_key):
    expected = hmac.new(
        webhook_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def parse_webhook(raw_body):
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FlizpayApiError(_("FLIZpay sent invalid webhook JSON.")) from exc
    if not isinstance(payload, dict):
        raise FlizpayApiError(_("FLIZpay sent an invalid webhook payload."))
    return payload
