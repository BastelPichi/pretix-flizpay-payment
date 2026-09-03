import logging
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextInput
from i18nfield.strings import LazyI18nString
from pretix.base.forms import SECRET_REDACTED, SecretKeySettingsField
from pretix.base.models import Order, OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.multidomain.urlreverse import build_absolute_uri

from pretix_flizpay import flizpay_client

logger = logging.getLogger("pretix.plugins.flizpay")


class Flizpay(BasePaymentProvider):
    identifier = "flizpay"
    verbose_name = _("Pay with FLIZpay")
    abort_pending_allowed = True

    @property
    def public_name(self):
        return str(self.settings.get("public_name", as_type=LazyI18nString) or _("FLIZpay"))

    @property
    def settings_form_fields(self):
        fields = OrderedDict([
            ("public_name", I18nFormField(
                label=_("Payment method name"),
                widget=I18nTextInput,
            )),
            ("api_key", SecretKeySettingsField(
                label=_("API key"), required=False,
                help_text=_("Enter the API key from your FLIZpay dashboard."),
            )),
            ("webhook_key", SecretKeySettingsField(
                label=_("Webhook signing secret"), required=False,
                help_text=_("Filled automatically during FLIZpay setup."),
            )),
            ("webhook_url", forms.CharField(
                label=_("Webhook URL"), required=False, disabled=True,
                help_text=_("Filled automatically during FLIZpay setup."),
            )),
        ])
        fields.update(super().settings_form_fields)
        fields.move_to_end("_enabled", last=False)
        return fields

    def settings_form_clean(self, cleaned_data):
        cleaned_data = super().settings_form_clean(cleaned_data)
        api_key = cleaned_data.get("payment_flizpay_api_key")
        if api_key and api_key != SECRET_REDACTED:
            try:
                webhook_key = flizpay_client.get_webhook_key(api_key)
                webhook_url = build_absolute_uri(
                    self.event, "plugins:pretix_flizpay:webhook"
                )
                flizpay_client.configure_webhook(api_key, webhook_url)
                if not cleaned_data.get("payment_flizpay_webhook_key"):
                    cleaned_data["payment_flizpay_webhook_key"] = webhook_key
                cleaned_data["payment_flizpay_webhook_url"] = webhook_url
            except Exception as exc:
                raise forms.ValidationError({
                    "payment_flizpay_api_key": _("Invalid FLIZpay API key: {}.").format(exc)
                })
        return cleaned_data

    def is_allowed(self, request: HttpRequest, total: Decimal = None):
        return total is None or total >= Decimal("0.01")

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        if self._synchronize_payment_status(payment):
            return
        order = payment.order
        event = order.event
        api_key = self.settings.get("api_key")
        if not api_key:
            raise PaymentException(_("FLIZpay is not configured."))
        external_id = f"{event.slug}/{order.code}/{payment.pk}"
        try:
            return_url = build_absolute_uri(
                event, "plugins:pretix_flizpay:return",
                kwargs={"order": order.code, "payment": payment.pk},
            )
            result = flizpay_client.create_transaction(
                api_key, payment.amount, event.currency, external_id,
                return_url, return_url,
                {"paymentId": str(payment.pk), "externalId": external_id},
            )
            info_data = payment.info_data
            info_data.update({
                "flizpay_reference": result["reference"],
                "flizpay_external_id": external_id,
                "flizpay_redirect_url": result["redirect_url"],
            })
            payment.info_data = info_data
            payment.save()
            return result["redirect_url"]
        except Exception as exc:
            payment.fail(info={"error": str(exc)})
            logger.exception("Error while creating FLIZpay transaction")
            raise PaymentException(_("Error while creating FLIZpay transaction")) from exc

    def checkout_confirm_render(self, request, **kwargs):
        return _("After confirmation you will be redirected to FLIZpay to complete the payment.")

    def payment_form_render(self, request: HttpRequest, **kwargs):
        return self.checkout_confirm_render(request, **kwargs)

    def payment_pending_render(self, request, payment):
        self._synchronize_payment_status(payment)
        if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
            return "<script>window.location.reload();</script>"
        redirect_url = payment.info_data.get("flizpay_redirect_url")
        if not redirect_url:
            return ""
        return get_template("pretix_flizpay/payment_widget.html").render(
            {"redirect_url": redirect_url}, request=request
        )

    def payment_is_valid_session(self, request):
        return True

    def payment_refund_supported(self, payment):
        return False

    def payment_partial_refund_supported(self, payment):
        return False

    def execute_refund(self, refund: OrderRefund):
        raise PaymentException(_("FLIZpay refunds must be handled manually."))

    def render_invoice_text(self, order: Order, payment: OrderPayment):
        return _("Paid via FLIZpay") if payment.info_data.get("flizpay_reference") else ""

    def matching_id(self, payment):
        return payment.info_data.get("flizpay_reference")

    def api_payment_details(self, payment):
        return {"flizpay_reference": payment.info_data.get("flizpay_reference")}

    def _synchronize_payment_status(self, payment):
        reference = payment.info_data.get("flizpay_reference")
        api_key = self.settings.get("api_key")
        if not reference or not api_key:
            return False
        try:
            transaction = flizpay_client.get_transaction_status(api_key, reference)
        except Exception as exc:
            logger.warning("Could not synchronize FLIZpay transaction: %s", exc)
            return False
        status = str(transaction.get("status", "")).lower()
        if status in {"completed", "paid", "successful"}:
            if payment.state != OrderPayment.PAYMENT_STATE_CONFIRMED:
                payment.confirm()
            return True
        if status in {"failed", "canceled", "cancelled"}:
            if payment.state != OrderPayment.PAYMENT_STATE_FAILED:
                payment.fail()
            return False
        if payment.state != OrderPayment.PAYMENT_STATE_PENDING:
            payment.state = OrderPayment.PAYMENT_STATE_PENDING
            payment.save(update_fields=["state"])
        return True
