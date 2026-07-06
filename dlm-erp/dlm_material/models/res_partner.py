from odoo import fields, models


class ResPartner(models.Model):
    """Bổ sung liên kết Bảng giá Vật tư cho NCC (S04 ↔ S06).

    dl_sale định nghĩa NCC (is_dlm_supplier); dlm_material giữ dl.material.price
    tham chiếu tới NCC qua supplier_id. Ở đây thêm inverse One2many để form NCC
    hiển thị tab 'Giá vật tư' (chỉ đọc) các dòng giá do NCC này cung cấp.
    """
    _inherit = 'res.partner'

    dlm_supplier_price_ids = fields.One2many(
        'dl.material.price', 'supplier_id',
        string='Giá vật tư cung cấp',
    )
