from django.urls import re_path

from pretix_flizpay.views import ReturnView, checkout_event

event_patterns = [
    re_path(
        r"^flizpay/webhook/$",
        checkout_event,
        name="webhook",
    ),
    re_path(
        r"^flizpay/return/(?P<order>[^/]+)/(?P<payment>[0-9]+)/$",
        ReturnView.as_view(),
        name="return",
    ),
]
