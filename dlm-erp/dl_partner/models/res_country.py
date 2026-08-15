from odoo import models


class ResCountry(models.Model):
    _inherit = 'res.country'

    def get_formview_action(self, access_uid=None):
        """Bấm mũi tên ở ô Quốc gia thì mở form quốc gia bản DLM thay vì form gốc Odoo."""
        action = self.env['ir.actions.act_window']._for_xml_id(
            'dl_partner.action_dl_country_form')
        action['res_id'] = self.id
        return action
