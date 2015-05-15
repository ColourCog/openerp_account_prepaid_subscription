# -*- coding: utf-8 -*-

import time, datetime
from lxml import etree

import openerp.addons.decimal_precision as dp
import openerp.exceptions

from openerp import netsvc
from openerp import pooler
from openerp.osv import fields, osv, orm
from openerp.tools.translate import _

class invoice(osv.osv):
    _inherit = 'account.invoice'
    _columns = {
        'subscription_id': fields.many2one('account.prepaid', 'Company', ondelete='cascade'),
    }

invoice()

def _monthly_dates(start, nb):
    """Return a list of month end"""
    s = datetime.datetime.strptime(start, '%Y-%m-%d')
    if s.day > 1:
        nb += 1 # 13th month!
    d = datetime.timedelta(1)
    month = s.month
    year = s.year
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
     
def _partial(total, nb, start_date):

    f = datetime.datetime.strptime(start_date, '%Y-%m-%d')
    m = datetime.date(f.year, f.month + 1, 1) - datetime.timedelta(1)
    amount = float(total) / nb     
    inst = amount
    if f.day > 1:
        # if we pay to day, the service should start today, 
        # so m.day - f.day must be > 0
        inst = ((m.day - f.day + 1) / float(m.day)) * amount
    amounts = []

    while total > 0 :
        amounts.append(inst)
        total -= inst
        inst = amount
        if total < amount:
            inst = total
    return amounts

#TODO: hook workflow to get individual invoice payment feedback
#TODO: add residual_amount to go with above
#TODO: use residual_amount for "Pay Now"
#TODO: only get non-reconciled move_lines for voucher creation

class account_prepaid(osv.osv):
    _name='account.prepaid'
    _description = "Prepaid Subscription"

    STATES = [
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('validated', 'Validated'),
        ('paid', 'Paid'),
        ]
    
    FREQUENCY = [
        ('month', 'Month'),
        ]
    
    DATEFETCH = {
        'month':_monthly_dates,
    }
    
    VOUCHERTYPE = {
        'out_invoice': 'receipt',
        'in_invoice': 'payment',
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

    def onchange_total(self, cr, uid, ids, amount_total, nb_payments, context=None):
        val =  float(amount_total) / nb_payments
        return {'value': {'amount': val}}

    def onchange_amount(self, cr, uid, ids, amount_total, nb_payments, context=None):
        val =  float(amount_total) / nb_payments
        return {'value': {'amount': val}}

    def onchange_nb_payments(self, cr, uid, ids, amount, nb_payments, context=None):
        return self.onchange_amount(cr, uid, ids, amount, nb_payments, context=context)
        
    def _get_invoices(self, cr, uid, ids, context=None):
        res = []
        for prepaid in self.browse(cr, uid, ids, context=context):
            res. extend([inv.id for inv in prepaid.invoice_ids])
        return res
    
    _columns = {
        'name' : fields.char('Name', size=64, select=True, readonly=True), 
        'type': fields.selection([
            ('out_invoice','Customer Subscription'),
            ('in_invoice','Supplier Subscription'),
            ],'Type', readonly=True, select=True, change_default=True, track_visibility='always'),
        'partner_id':fields.many2one('res.partner', 'Partner', required=True),
        'invoice_ids':fields.one2many('account.invoice', 'subscription_id', 'Invoices'),
        'amount' : fields.float('Installment Amount', digits_compute=dp.get_precision('Account'), readonly=True, states={'draft':[('readonly',False)]}),
        'amount_total' : fields.float('Total', digits_compute=dp.get_precision('Account'), required=True), 
        'nb_payments': fields.integer("Number of payments", required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'date_from': fields.date('Start Date', required=True),
        'date_pay': fields.date('Payment Date', required=True),
        'post_account_id': fields.many2one('account.account', 'Post-paid Account', required=True),
        'pre_account_id': fields.many2one('account.account', 'Pre-paid Account', required=True),
        'product_id': fields.many2one('product.product', 'Product', required=True),
        'product_account_id': fields.many2one('account.account', 'Product Account', required=True, domain=[('type','<>','view'), ('type', '<>', 'closed')], help="The income or expense account related to the selected product."),
        'journal_id': fields.many2one('account.journal', 'Journal', required=True, readonly=True, states={'draft':[('readonly',False)]},
                                      domain="[('type', 'in', {'out_invoice': ['sale'], 'in_invoice': ['purchase']}.get(type, [])), ('company_id', '=', company_id)]"),
        'payment_id': fields.many2one('account.journal', 'Payment method', required=True, #readonly=True, states={'draft':[('readonly',False)]},
                                      domain="[('type', 'in',['bank','cash']), ('company_id', '=', company_id)]"),
        'currency_id': fields.many2one('res.currency', 'Currency', required=True, readonly=True, states={'draft':[('readonly',False)]}, track_visibility='always'),
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'voucher_id': fields.many2one('account.voucher', 'Payment voucher', readonly=True),
        'user_id': fields.many2one('res.users', 'User', required=True),
        'frequency': fields.selection(FREQUENCY, 'Period Frequency', required=True),
        'state': fields.selection(STATES, 'Status', readonly=True, track_visibility='onchange'),
    }

    _defaults = {
        'nb_payments': 1,
        'amount_total': 1,
        'frequency': 'month',
        'date_pay': fields.date.context_today,
        'type': _get_type,
        'state': 'draft',
        'journal_id': _get_journal,
        'currency_id': _get_currency,
        'company_id': lambda self,cr,uid,c: self.pool.get('res.company')._company_default_get(cr, uid, 'account.invoice', context=c),
        'user_id': lambda cr, uid, id, c={}: id,
    }


    def fields_view_get(self, cr, uid, view_id=None, view_type=False, context=None, toolbar=False, submenu=False):
        mod_obj = self.pool.get('ir.model.data')
        if context is None: context = {}

        if view_type == 'form':
            if not view_id and context.get('type'):
                if context.get('type') == 'out_invoice':
                    result = mod_obj.get_object_reference(cr, uid, 'account_prepaid_subscription', 'subscription_form')
                else:
                    result = mod_obj.get_object_reference(cr, uid, 'account_prepaid_subscription', 'subscription_supplier_form')
                result = result and result[1] or False
                view_id = result
        res = super(account_prepaid, self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=submenu)
        return res


    def create(self, cr, uid, vals, context=None):
        if vals.get('name','/') == '/':
            vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'account.prepaid') or '/'
        return super(account_prepaid, self).create(cr, uid, vals, context=context)
        
    def copy(self, cr, uid, prepaid_id, default=None, context=None):
        default = default or {}
        default.update({
            'name': self.pool.get('ir.sequence').get(cr, uid, 'account.prepaid') or '/',
            'date_from': context.get('date', fields.date.context_today(self,cr,uid,context=context)),
            'date_pay': context.get('date', fields.date.context_today(self,cr,uid,context=context)),
            'invoice_ids': [],
            'voucher_id': False,
        })
        return super(account_prepaid, self).copy(cr, uid, prepaid_id, default, context=context)

    def unlink(self, cr, uid, ids, context=None):
        for rec in self.browse(cr, uid, ids, context=context):
            if rec.state not in ['draft']:
                raise osv.except_osv(_('Warning!'),_('You must cancel the Subscription before you can delete it.'))
        return super(account_prepaid, self).unlink(cr, uid, ids, context)

    def action_draft(self, cr, uid, ids, context=None):
        #~ wf_service = netsvc.LocalService("workflow")
        #~ for prepaid in self.browse(cr, uid, ids):
            #~ wf_service.trg_delete(uid, 'account.prepaid', prepaid.id, cr)
            #~ wf_service.trg_create(uid, 'account.prepaid', prepaid.id, cr)
        return self.write(cr, uid, ids, {'state': 'draft'}, context=context)

    def action_compute(self, cr, uid, ids, context=None):
        if self._compute_invoices(cr, uid, ids, context=None):
            return self.write(cr, uid, ids, {'state': 'computed'}, context=context)
    
    def action_validate(self, cr, uid, ids, context=None):
        if self._validate_invoices(cr, uid, ids, context=None):
            return self.write(cr, uid, ids, {'state': 'validated'}, context=context)
    
    def action_paid(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'paid'}, context=context)

    def condition_paid(self, cr, uid, ids, context=None):
        ok = True
        for p in self.browse(cr, uid, ids, context=context):
            for inv in p.invoice_ids:
                if inv.state != 'paid':
                    ok = False
                    break
        return ok

    def _compute_invoices(self, cr, uid, ids, context):
        period_obj = self.pool.get('account.period')
        inv_obj = self.pool.get('account.invoice')
        inv_line_obj = self.pool.get('account.invoice.line')
        total = 0.0
        for prepaid in self.browse(cr, uid, ids, context=context):
            pay_date = datetime.datetime.strptime(prepaid.date_pay, '%Y-%m-%d')
            #~ 1. get period ids
            datelist = self.DATEFETCH.get(prepaid.frequency)(prepaid.date_from, prepaid.nb_payments)
            period_ids = [period_obj.find(cr, uid, m, context=context)[0] for m in datelist]
            #~ 2. associate periods with dates
            dates = dict(zip(datelist, period_ids))
            #~ 3. calculate amounts
            amountslists = _partial(prepaid.amount_total, prepaid.nb_payments, prepaid.date_from)
            amounts = dict(zip(datelist,amountslists))
            #~ 4. start building invoices
            for d in datelist:
                inv_line = (0, 0, {
                    'name': prepaid.product_id.name,
                    'product_id': prepaid.product_id.id,
                    'account_id': prepaid.product_account_id.id,
                    'price_unit': amounts.get(d, prepaid.amount),
                    'quantity': 1,
                    })
                invoice = {
                    'type': prepaid.type,
                    'name': " ".join([prepaid.partner_id.name, d]),
                    'date_invoice': d,
                    'partner_id': prepaid.partner_id.id,
                    'period_id': dates.get(d),
                    # payment made on the date the service starts is in advance
                    'account_id': datetime.datetime.strptime(d, '%Y-%m-%d') >= pay_date and prepaid.pre_account_id.id or prepaid.post_account_id.id,
                    'invoice_line': [inv_line],
                    'currency_id': prepaid.currency_id.id,
                    'journal_id': prepaid.journal_id.id,
                    'company_id': prepaid.company_id.id,
                    'subscription_id': prepaid.id,
                    }
                inv_id = inv_obj.create(cr, uid, invoice, context=context)
        return True

    def cancel_invoices(self, cr, uid, ids, context):
        inv_obj = self.pool.get('account.invoice')
        for prepaid in self.browse(cr, uid, ids, context=context):
            l = [inv.id for inv in prepaid.invoice_ids]
            inv_obj.action_cancel(cr,uid,l,context)
            inv_obj.action_cancel_draft(cr,uid,l,context)
            try:
                inv_obj.unlink(cr, uid, l, context=context)
            except:
                # can't delete ? disconnect from this subscription at least
                inv_obj.write(cr, uid, l, {'subscription_id': None}, context=context)
            self.write(cr, uid, [prepaid.id], {'invoice_ids': []}, context=context)
        return self.action_draft(cr, uid, ids, context=context)

    def _validate_invoices(self, cr, uid, ids, context):
        inv_obj = self.pool.get('account.invoice')
        #~ wf_service = netsvc.LocalService("workflow")
        for prepaid in self.browse(cr, uid, ids, context=context):
            for inv in prepaid.invoice_ids:
                #~ wf_service.trg_validate(uid, 'account.invoice', inv.id, 'invoice_open', cr)
                inv_obj.action_date_assign(cr,uid,[inv.id],context)
                inv_obj.action_move_create(cr,uid,[inv.id],context=context)
                inv_obj.action_number(cr,uid,[inv.id],context)
                inv_obj.invoice_validate(cr,uid,[inv.id],context=context)
        return True
        

    def _pay_subscription(self, cr, uid, ids, context):
        voucher_obj = self.pool.get('account.voucher')
        inv_obj = self.pool.get('account.invoice')
        journal_obj = self.pool.get('account.journal')
        move_line_obj = self.pool.get('account.move.line')
        company_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id.id

        for prepaid in self.browse(cr, uid, ids, context=context):
            name = _('Subscription %s') % (prepaid.partner_id.name)
            partner_id = prepaid.partner_id.id
            journal = prepaid.payment_id
            amt = prepaid.amount_total
            voucher = {
                'journal_id': journal.id,
                'company_id': company_id,
                'partner_id': partner_id,
                'type':self.VOUCHERTYPE.get(prepaid.type),
                'name': name,
                'reference': context.get('reference', prepaid.name),
                'account_id': journal.default_credit_account_id.id,
                'amount': amt > 0.0 and amt or 0.0,
                'date': prepaid.date_pay,
                'date_due': prepaid.date_pay,
                }

            # Define the voucher line
            lml = []
            move_lines = []
            # Collect move_lines
            for i in prepaid.invoice_ids:
                move_lines.extend(i.move_id.line_id)
            # Create voucher_lines
            for move_line_id in move_lines:
                if prepaid.type == 'in_invoice':
                    if move_line_id.debit > 0:
                        continue
                if prepaid.type == 'out_invoice':
                    if move_line_id.credit > 0:
                        continue
                lml.append({
                    'name': move_line_id.name,
                    'move_line_id': move_line_id.id,
                    'reconcile': True,
                    'amount': move_line_id.credit > 0 and move_line_id.credit or move_line_id.debit,
                    'account_id': move_line_id.account_id.id,
                    'type': move_line_id.credit and 'dr' or 'cr',
                    })
            lines = [(0,0,x) for x in lml]
            voucher['line_ids'] = lines
            voucher_id = voucher_obj.create(cr, uid, voucher, context=context)
            self.write(cr, uid, [prepaid.id], {'voucher_id': voucher_id}, context=context)
            voucher_obj.button_proforma_voucher(cr, uid, [voucher_id], context)
            move_id = voucher_obj.browse(cr, uid, voucher_id, context=context).move_id.id
            #~ # post the journal entry if 'Skip 'Draft' State for Manual Entries' is checked
            if journal.entry_posted:
                move_obj.button_validate(cr, uid, [move_id], context)
            inv_obj.confirm_paid(cr, uid, [i.id for i in prepaid.invoice_ids], context=context)
        # TODO: We need to make sure that all invoices are paid before this!!
        return self.action_paid(cr, uid, ids, context=context)

    def button_pay_subscription(self, cr, uid, ids, context=None):
        dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account_prepaid_subscription', 'account_prepaid_pay_view')

        return {
            'name':_("Pay Subscription"),
            'view_mode': 'form',
            'view_id': view_id,
            'view_type': 'form',
            'res_model': 'account.prepaid.pay',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'new',
            'domain': '[]',
            'context': context
        }
        
account_prepaid()

class account_prepaid_pay(osv.osv_memory):
    """
    This wizard will confirm the all the selected draft invoices
    """

    _name = "account.prepaid.pay"
    _description = "Pay the subscription"
    
    _columns = { 
        'reference': fields.char('Payment reference', size=64),
    } 
    
    def pay_prepaid(self, cr, uid, ids, context=None):
        wf_service = netsvc.LocalService('workflow')
        if context is None:
            context = {}
        pool_obj = pooler.get_pool(cr.dbname)
        prepaid_obj = pool_obj.get('account.prepaid')
        
        context.update({
            'reference': self.browse(cr,uid,ids)[0].reference,
            })
        
        prepaid_obj._pay_subscription(cr, uid, [context.get('active_id')], context=context)

        return {'type': 'ir.actions.act_window_close'}

account_prepaid_pay()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
