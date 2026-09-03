from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from pretix.base.middleware import _merge_csp, _parse_csp, _render_csp
from pretix.base.signals import register_payment_providers
from pretix.presale.signals import process_response


@receiver(register_payment_providers, dispatch_uid="flizpay_payment")
def register_payment_provider(sender, **kwargs):
    from .payment import Flizpay

    return Flizpay


@receiver(process_response, dispatch_uid="flizpay_csp_middleware_resp")
def signal_process_response(
    sender, request: HttpRequest, response: HttpResponse, **kwargs
):
    if "Content-Security-Policy" in response:
        h = _parse_csp(response["Content-Security-Policy"])
    else:
        h = {}

    csps = {"frame-src": ["https://checkout.flizpay.de"]}

    _merge_csp(h, csps)

    if h:
        response["Content-Security-Policy"] = _render_csp(h)

    return response
