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
    """Return a list of dates"""
     

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
        ('trimestre', 'Trimestre'),
        ('semestre', 'Semestre'),
        ('year', 'Year'),
        ]
    
    def _get_type(self, cr, uid, context=None):
        if context is None:
            context = {}
        return context.get('type', 'in_subscription')

    def _get_journal(self, cr, uid, context=None):
        if context is None:
            context = {}
        type_inv = context.get('type', 'in_subscription')
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        company_id = context.get('company_id', user.company_id.id)
        type2journal = {'out_subscription': 'sale', 'in_subscription': 'purchase'}
        journal_obj = self.pool.get('account.journal')
        domain = [('company_id', '=', company_id)]
        if isinstance(type_inv, list):
            domain.append(('type', 'in_subscription', [type2journal.get(type) for type in type_inv if type2journal.get(type)]))
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
            ('out_subscription','Customer Subscription'),
            ('in_subscription','Supplier Subscription'),
            ],'Type', readonly=True, select=True, change_default=True, track_visibility='always'),
        'partner_id':fields.many2one('res.partner', 'Partner', required=True),
        'invoice_ids':fields.one2many('account.invoice', 'subscription_id', 'Invoices'),
        'amount' : fields.float('Installment Amount', digits_compute=dp.get_precision('Account'), readonly=True), 
        'nb_payments': fields.integer("Number of payments", required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'date_from': fields.date('Start Date', required=True),
        'post_account_id': fields.many2one('account.account', 'Post-paid Account', required=True),
        'pre_account_id': fields.many2one('account.account', 'Pre-paid Account', required=True),
        'product_id': fields.many2one('product.product', 'Product', ondelete='set null', select=True),
        'account_id': fields.many2one('account.account', 'Product Account', required=True, domain=[('type','<>','view'), ('type', '<>', 'closed')], help="The income or expense account related to the selected product."),
        'journal_id': fields.many2one('account.journal', 'Journal', required=True, readonly=True, states={'draft':[('readonly',False)]},
                                      domain="[('type', 'in', {'out_subscription': ['sale'], 'in_subscription': ['purchase']}.get(type, [])), ('company_id', '=', company_id)]"),
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
        
    


account_prepaid()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
