from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_flizpay"
    verbose_name = "Pretix FLIZpay Payment"

    class PretixPluginMeta:
        name = "FLIZpay"
        author = "BastelPichi"
        description = gettext_lazy("Accept payments via FLIZpay")
        visible = True
        version = __version__
        category = "PAYMENT"
        compatibility = "pretix>=2.7.0"

    def ready(self):
        from . import signals  # NOQA
