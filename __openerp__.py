# -*- coding: utf-8 -*-
{
    "name" : "Prepaid Subscription Accounting",
    "version" : "1.1",
    "category" : "Accounting",
    "sequence": 60,
    "complexity" : "normal",
    "author" : "ColourCog.com",
    "website" : "http://colourcog.com",
    "depends" : [
        "base",
        "account_accountant",
    ],
    "summary" : "Manage prepaid subscriptions invoices",
    "description" : """
Subscription Accounting
========================
This module enables advance and arrear invoicing for prepaid subscriptions.

Features:
---------
* Batch create invoices for the number of installment defined
* Generate payment for arrear/advance invoices
    """,
    "data" : [
      "security/ir.model.access.csv",
      'subscription_view.xml',
      'subscription_sequence.xml',
    ],
    "application": False,
    "installable": True
}

