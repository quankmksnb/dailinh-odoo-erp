from odoo import models


class ResCountry(models.Model):
    _inherit = 'res.country'

    def get_formview_action(self, access_uid=None):
        """Mở qua mũi tên bằng action DLM ĐÃ LƯU (có id) để F5/deep-link giữ UI
        mới. KHÔNG đặt priority nên form gốc Odoo vẫn là mặc định toàn hệ thống
        (Settings không đổi). Chỉ đổi điều hướng/chọn view, không đổi nghiệp vụ."""
        action = self.env['ir.actions.act_window']._for_xml_id(
            'dl_partner.action_dl_country_form')
        action['res_id'] = self.id
        return action
