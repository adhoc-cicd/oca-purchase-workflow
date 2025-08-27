# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    all_picking_ids = fields.One2many(
        "stock.picking", string="All Pickings", compute="_compute_all_pickings"
    )
    all_picking_count = fields.Integer(
        "All Pickings Count", compute="_compute_all_picking_count"
    )

    def _compute_all_picking_count(self):
        for rec in self:
            rec.all_picking_count = len(rec.all_picking_ids)

    def _compute_all_pickings(self):
        for rec in self:
            all_picking_ids = set()
            groups = rec.mapped("picking_ids.group_id")
            if groups:
                group_pickings = self.env["stock.picking"].search(
                    [("group_id", "in", groups.ids)]
                )
                all_picking_ids.update(group_pickings.ids)
            # add pickings connected by move_orig_ids (multi-steps) - recursively
            for line in rec.order_line:
                for move in line.move_ids:
                    self._add_connected_pickings(move, all_picking_ids)
            rec.all_picking_ids = self.env["stock.picking"].browse(list(all_picking_ids))

    def _add_connected_pickings(self, move, all_picking_ids):
        """Recursively add all pickings connected through move_orig_ids"""
        # Find moves that have this move as origin
        next_moves = self.env['stock.move'].search([
            ('move_orig_ids', 'in', move.ids)
        ])
        for next_move in next_moves:
            if next_move.picking_id:
                if next_move.picking_id.id not in all_picking_ids:
                    all_picking_ids.add(next_move.picking_id.id)
                    # Recursively search for more connected moves
                    self._add_connected_pickings(next_move, all_picking_ids)

    def action_view_all_pickings(self):
        return self._get_action_view_all_pickings(self.all_picking_ids)

    def _get_action_view_all_pickings(self, picking_ids):
        """Similar to the _get_action_view_picking method in the purchase module"""
        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        # override the context to get rid of the default filtering on picking type
        result["context"] = {}

        if not picking_ids or len(picking_ids) > 1:
            result["domain"] = [("id", "in", picking_ids.ids)]
        elif len(picking_ids) == 1:
            res = self.env.ref("stock.view_picking_form", False)
            form_view = [(res and res.id or False, "form")]
            result["views"] = form_view + [
                (state, view)
                for state, view in result.get("views", [])
                if view != "form"
            ]
            result["res_id"] = picking_ids.id
        return result
