from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import View
from pretix.base.models import Order, OrderPayment
from pretix.helpers.http import redirect_to_url
from pretix.multidomain.urlreverse import eventreverse

from pretix_flizpay import flizpay_client
from pretix_flizpay.payment import Flizpay


class ReturnView(View):
    def get(self, request, *args, **kwargs):
        try:
            order = get_object_or_404(Order, code=kwargs["order"], event=request.event)
            payment = get_object_or_404(OrderPayment, pk=kwargs["payment"], order=order)
            provider = Flizpay(request.event)
            provider._synchronize_payment_status(payment)
            return redirect_to_url(
                eventreverse(
                    request.event,
                    "presale:event.order",
                    kwargs={"order": order.code, "secret": order.secret},
                ) + ("?paid=yes" if order.status == Order.STATUS_PAID else "")
            )
        except Exception:
            messages.error(request, _("There was an error processing the FLIZpay payment."))
            return redirect_to_url(eventreverse(request.event, "presale:event.index"))


@csrf_exempt
@require_POST
def checkout_event(request, *args, **kwargs):
    provider = Flizpay(request.event)
    webhook_key = provider.settings.get("webhook_key")
    if not webhook_key or not flizpay_client.verify_webhook_signature(
        request.body, request.headers.get("X-Fliz-Signature", ""), webhook_key
    ):
        return HttpResponse(status=401)
    try:
        payload = flizpay_client.parse_webhook(request.body)
    except flizpay_client.FlizpayApiError:
        return HttpResponse(status=400)
    metadata = payload.get("metadata") or {}
    payment_id = metadata.get("paymentId")
    if not payment_id:
        return HttpResponse(status=400)
    order_payment = get_object_or_404(
        OrderPayment, pk=payment_id, order__event=request.event
    )
    status = str(payload.get("status", "")).lower()
    if status == "completed":
        order_payment.confirm()
    elif status in {"failed", "canceled", "cancelled"}:
        order_payment.fail()
    return HttpResponse(status=204)


