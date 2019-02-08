# Copyright (C) 2018 Eficent Business and IT Consulting Services S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models, api, _
from odoo.tools import float_is_zero
from collections import defaultdict
from odoo.exceptions import UserError


class BlanketOrderWizard(models.TransientModel):
    _name = 'purchase.blanket.order.wizard'
    _description = 'Blanket Order Wizard'

    @api.model
    def _default_order(self):
        # in case the cron hasn't run
        self.env['purchase.blanket.order'].expire_orders()
        if not self.env.context.get('active_id'):
            return False
        blanket_order = self.env['purchase.blanket.order'].search(
            [('id', '=', self.env.context['active_id'])], limit=1)
        if blanket_order.state == 'expired':
            raise UserError(_('You can\'t create a purchase order from '
                              'an expired blanket order!'))
        return blanket_order

    @api.model
    def _check_valid_blanket_order_line(self, bo_lines):
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        company_id = False

        for line in bo_lines:

            if line.order_id.state != 'open':
                raise UserError(
                    _('Purchase Blanket Order %s is not open') %
                    line.order_id.name)

            if float_is_zero(line.remaining_qty, precision_digits=precision):
                raise UserError(
                    _('The purchase has already been completed.'))

            line_company_id = line.company_id \
                              and line.company_id.id or False
            if company_id is not False \
                    and line_company_id != company_id:
                raise UserError(
                    _('You have to select lines '
                      'from the same company.'))
            else:
                company_id = line_company_id

    @api.model
    def _default_lines(self):
        blanket_order_line_obj = self.env['purchase.blanket.order.line']
        blanket_order_line_ids = self.env.context.get('active_ids', False)
        active_model = self.env.context.get('active_model', False)

        if active_model == 'purchase.blanket.order':
            bo_lines = self._default_order().line_ids
        else:
            bo_lines = blanket_order_line_obj.browse(blanket_order_line_ids)

        self._check_valid_blanket_order_line(bo_lines)

        lines = [(0, 0, {
            'blanket_line_id': l.id,
            'product_id': l.product_id.id,
            'date_schedule': l.date_schedule,
            'remaining_qty': l.remaining_qty,
            'price_unit': l.price_unit,
            'qty': l.remaining_qty,
            'partner_id': l.partner_id,
        }) for l in bo_lines]
        return lines

    blanket_order_id = fields.Many2one(
        'purchase.blanket.order', readonly=True)
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        domain=[('state', '=', 'draft')])
    line_ids = fields.One2many(
        'purchase.blanket.order.wizard.line', 'wizard_id',
        string='Lines', default=_default_lines)

    @api.multi
    def create_purchase_order(self):

        order_lines_by_supplier = defaultdict(list)
        for line in self.line_ids:
            if line.qty == 0.0:
                continue

            if line.qty > line.remaining_qty:
                raise UserError(
                    _('You can\'t order more than the remaining quantities'))

            date_planned = line.blanket_line_id.date_schedule

            vals = {'product_id': line.product_id.id,
                    'name': line.product_id.name,
                    'date_planned': date_planned if date_planned else
                    line.blanket_line_id.order_id.date_order,
                    'product_uom': line.blanket_line_id.product_uom.id,
                    'sequence': line.blanket_line_id.sequence,
                    'price_unit': line.blanket_line_id.price_unit,
                    'blanket_order_line': line.blanket_line_id.id,
                    'product_qty': line.qty}
            order_lines_by_supplier[line.partner_id.id].append((0, 0, vals))

        if not order_lines_by_supplier:
            raise UserError(_('An order can\'t be empty'))

        res = []
        for supplier in order_lines_by_supplier:
            order_vals = {
                'partner_id': int(supplier),
            }
            order_vals.update(self.env['purchase.order'].onchange(
                order_vals, 'partner_id', {'partner_id': 'true'})['value'])
            if self.blanket_order_id:
                order_vals.update({
                    'origin': self.blanket_order_id.name,
                    'currency_id': self.blanket_order_id.currency_id.id,
                    'payment_term_id': (
                        self.blanket_order_id.payment_term_id.id
                        if self.blanket_order_id.payment_term_id
                        else False),
                })
            order_vals.update({
                'order_line': order_lines_by_supplier[supplier],
            })
            purchase_order = self.env['purchase.order'].create(order_vals)
            res.append(purchase_order.id)
        return {
            'domain': [('id', 'in', res)],
            'name': _('RFQ'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'purchase.order',
            'view_id': False,
            'context': {'from_purchase_order': True},
            'type': 'ir.actions.act_window'
        }


class BlanketOrderWizardLine(models.TransientModel):
    _name = 'purchase.blanket.order.wizard.line'

    wizard_id = fields.Many2one('purchase.blanket.order.wizard')
    blanket_line_id = fields.Many2one(
        'purchase.blanket.order.line')
    product_id = fields.Many2one(
        'product.product',
        related='blanket_line_id.product_id',
        string='Product', readonly=True)
    date_schedule = fields.Date(
        related='blanket_line_id.date_schedule', readonly=True)
    remaining_qty = fields.Float(
        related='blanket_line_id.remaining_qty', readonly=True)
    qty = fields.Float(string='Quantity to Order', required=True)
    price_unit = fields.Float(
        related='blanket_line_id.price_unit', readonly=True)
    partner_id = fields.Many2one(
        'res.partner',
        related='blanket_line_id.partner_id',
        string='Vendor', readonly=True,
    )
