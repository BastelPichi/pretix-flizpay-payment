Pretix FLIZpay Payment
======================

WARNING: Vibe coded and untested. Use at your own risk.
This Pretix plugin accepts payments through FLIZpay.

Setup
-----

1. Enable the FLIZpay payment provider for an event.
2. Open its settings page.
3. Enter the FLIZpay API key.
4. Save the settings. Pretix generates a webhook signing secret and registers the
    event webhook URL with FLIZpay.

The API key and webhook signing secret are stored in the event settings. Payment state is updated from signed FLIZpay
webhooks and is also checked on the customer return page.

Testing
-------

FLIZpay processes real bank transfers and does not provide a traditional sandbox.
Use small real transactions between two different accounts, as recommended by the
FLIZpay documentation. Run the local checks with::

    python3 -m compileall -q pretix_flizpay
    pytest -q

Development
-----------

Install the plugin in a Pretix development environment with::

    python3 setup.py develop

The plugin package is ``pretix_flizpay``.
