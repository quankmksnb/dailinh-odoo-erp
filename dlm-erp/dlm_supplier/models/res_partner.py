from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # supplier_type (Vật tư/Gia công ngoài/Cả hai) bị bỏ theo TDS 4.0 — loại
    # NCC được suy ra từ nơi tham chiếu (dl.material.price, dl.material,
    # dl.quotation.outsource.line...), không lưu thành field cứng trên partner.
    #
    # payment_terms/contact_person (Char) đã bỏ theo Cap_Nhat_S04_Nha_Cung_Cap.md:
    # - Điều khoản thanh toán: TDS không có, không triển khai ở Phase 1.
    # - Người liên hệ: thay bằng contact con chuẩn Odoo (child_ids, type='contact').
    supplier_code = fields.Char(string='Mã NCC', copy=False, readonly=True, tracking=True)

    # Tab "Giá vật tư" trong form NCC (S04 mục 5) — One2many thuần, không cần cột DB.
    material_price_ids = fields.One2many('dl.material.price', 'supplier_id',
                                          string='Giá vật tư cung cấp')

    def _assign_supplier_code(self):
        seq = self.env['ir.sequence'].sudo()
        for partner in self:
            if partner.partner_role in ('supplier', 'both') and not partner.supplier_code:
                partner.supplier_code = seq.next_by_code('res.partner.supplier') or 'New'

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._assign_supplier_code()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if vals.get('partner_role') in ('supplier', 'both'):
            self._assign_supplier_code()
        return res
