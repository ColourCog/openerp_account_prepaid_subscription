{
    "name" : "Prepaid Subscription Accounting",
    "version" : "0.1", 
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
* Batch create invoices
* Generate payment for arrear/advance invoices
    """,
    "data" : [ 
      "security/ir.model.access.csv",
      'subscription_view.xml', 
    ], 
    "application": False, 
    "installable": True
}

