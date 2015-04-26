# -*- coding: utf-8 -*-

import time, datetime
import openerp.addons.decimal_precision as dp
import openerp.exceptions

from openerp import netsvc
from openerp import pooler
from openerp.osv import fields, osv, orm
from openerp.tools.translate import _

class invoice(osv.osv):
    _inherit = 'account.invoice'
    _columns = {
        'subscription_id': fields.many2one('account.subscription', 'Company', required=True),
    }

invoice()

def _monthly_dates(start, nb):
    """Return a list of month end"""
    d = datetime.timedelta(1)
    month = start.month
    year = start.year
    dates = []
    while nb > 0 :
        month += 1
        m = datetime.date(year, month, 1) - d
        dates.append(m.strftime('%Y-%m-%d'))
        if month == 12:
            year += 1
            month = 0
        nb -= 1
    return dates
     

class account_prepaid(osv.osv):
    _name='account.prepaid'
    _description = "Prepaid Subscription"

    STATES = [
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('paid', 'Paid'),
        ]
    
    FREQUENCY = [
        ('month', 'Month'),
        ]
    
    datefetch = {
        'month':_monthly_dates,
    }
    
    invoicetype = {
        'out_invoice': '',
    }
    
    def _get_type(self, cr, uid, context=None):
        if context is None:
            context = {}
        return context.get('type', 'in_invoice')

    def _get_journal(self, cr, uid, context=None):
        if context is None:
            context = {}
        type_inv = context.get('type', 'in_invoice')
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        company_id = context.get('company_id', user.company_id.id)
        type2journal = {'out_invoice': 'sale', 'in_invoice': 'purchase'}
        journal_obj = self.pool.get('account.journal')
        domain = [('company_id', '=', company_id)]
        if isinstance(type_inv, list):
            domain.append(('type', 'in_invoice', [type2journal.get(type) for type in type_inv if type2journal.get(type)]))
        else:
            domain.append(('type', '=', type2journal.get(type_inv, 'purchase')))
        res = journal_obj.search(cr, uid, domain, limit=1)
        return res and res[0] or False

    def _get_currency(self, cr, uid, context=None):
        res = False
        journal_id = self._get_journal(cr, uid, context=context)
        if journal_id:
            journal = self.pool.get('account.journal').browse(cr, uid, journal_id, context=context)
            res = journal.currency and journal.currency.id or journal.company_id.currency_id.id
        return res

    _columns = {
        'type': fields.selection([
            ('out_invoice','Customer Subscription'),
            ('in_invoice','Supplier Subscription'),
            ],'Type', readonly=True, select=True, change_default=True, track_visibility='always'),
        'partner_id':fields.many2one('res.partner', 'Partner', required=True),
        'invoice_ids':fields.one2many('account.invoice', 'subscription_id', 'Invoices'),
        'amount' : fields.float('Installment Amount', digits_compute=dp.get_precision('Account'), readonly=True), 
        'nb_payments': fields.integer("Number of payments", required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'date_from': fields.date('Start Date', required=True),
        'post_account_id': fields.many2one('account.account', 'Post-paid Account', required=True),
        'pre_account_id': fields.many2one('account.account', 'Pre-paid Account', required=True),
        'product_id': fields.many2one('product.product', 'Product', ondelete='set null', select=True),
        'product_account_id': fields.many2one('account.account', 'Product Account', required=True, domain=[('type','<>','view'), ('type', '<>', 'closed')], help="The income or expense account related to the selected product."),
        'journal_id': fields.many2one('account.journal', 'Journal', required=True, readonly=True, states={'draft':[('readonly',False)]},
                                      domain="[('type', 'in', {'out_invoice': ['sale'], 'in_invoice': ['purchase']}.get(type, [])), ('company_id', '=', company_id)]"),
        'currency_id': fields.many2one('res.currency', 'Currency', required=True, readonly=True, states={'draft':[('readonly',False)]}, track_visibility='always'),
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'currency_id': fields.many2one('res.currency', 'Currency'),
        'user_id': fields.many2one('res.users', 'User', required=True),
        'partial': fields.boolean('Partial ', help="Should we calculate mid-period amounts"),
        'frequency': fields.selection(FREQUENCY, 'Period Frequency', required=True),
        'state': fields.selection(STATES, 'Status', readonly=True, track_visibility='onchange'),
    }

    _defaults = {
        'frequency': 'month',
        'partial': False,
        'type': _get_type,
        'state': 'draft',
        'journal_id': _get_journal,
        'currency_id': _get_currency,
        'company_id': lambda self,cr,uid,c: self.pool.get('res.company')._company_default_get(cr, uid, 'account.invoice', context=c),
        'user_id': lambda cr, uid, id, c={}: id,
    }

    def create(self, cr, uid, vals, context=None):
        return super(account_prepaid, self).create(cr, uid, vals, context=context)
        
    
    def compute_invoices(self, uid, context):
        period_obj = self.pool.get('account.period')
        inv_obj = self.pool.get('account.invoice')
        inv_line_obj = self.pool.get('account.invoice.line')
        total = 0.0
        today = datetime.datetime.today()
        for prepaid in self.browse(cr, uid, ids, context=context):
            #~ 1. get period ids
            datelist = self.datefetch.get(prepaid.frequency)(prepaid.date_from, prepaid.nb_payments)
            period_ids = [period_obj.find(cr, uid, m, context=context).id for m in dates]
            #~ 2. associate periods with dates
            dates = dict(zip(datelist, period_ids))
            #~ 3. build invoice_line. We will supply invoice_id after
            inv_line = (0, 0, {
                'name': prepaid.product_id.name,
                'product_id': prepaid.product_id.id,
                'account_id': prepaid.product_account_id.id,
                'price_unit': prepaid.amount,
                'quantity': 1,
                })
            #~ 4. start building invoices
            for d in datelist:
                invoice = {
                    'type': prepaid.type,
                    'comment': fields.text('Additional Information'),
                    'date_invoice': d,
                    'partner_id': prepaid.partener_id.id,
                    'period_id': dates.get(d),
                    'account_id': datetime.datetime.strptime(d, '%Y-%m-%d') > today and prepaid.pre_account_id.id or prepaid.post_account_id.id,
                    'invoice_line': [inv_line],
                    'currency_id': prepaid.currency_id.id,
                    'journal_id': prepaid.journal_id.id,
                    'company_id': prepaid.company_id.id,
                    'subscription_id': prepaid.id,
                    }
                inv_id = inv_obj.create(cr, uid, invoice, context=context)
        return True


account_prepaid()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
