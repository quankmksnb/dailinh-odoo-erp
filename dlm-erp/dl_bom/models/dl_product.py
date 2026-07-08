from odoo import api, fields, models, _


class DlProductCategory(models.Model):
    """Mở rộng dl.product.category CỦA dl_sale (S05, model đã tồn tại, có bảng
    riêng) — chỉ thêm template_bom_id, KHÔNG khai báo _name mới để tránh xung
    đột registry giữa 2 module (đã từng gây lỗi khi merge)."""
    _inherit = 'dl.product.category'

    template_bom_id = fields.Many2one(
        'dl.bom', string='BOM mẫu mặc định',
        help='Khung BOM trừu tượng cấp nhóm (dl.bom với category_id=nhóm này), '
             'gợi ý khi tạo sản phẩm mới trong nhóm.',
    )


class DlProduct(models.Model):
    """Mở rộng dl.product CỦA dl_sale (S05) — thêm thuộc tính cần cho S08
    BOM: loại cung ứng, giá vốn nhập (hàng trading), NCC mặc định, liên kết BOM."""
    _inherit = 'dl.product'

    supply_type = fields.Selection([
        ('manufactured', 'Gia công theo yêu cầu'),
        ('trading', 'Hàng có sẵn / nhập về'),
    ], string='Loại cung ứng', default='manufactured')
    purchase_cost = fields.Float(
        string='Giá vốn nhập', digits='Product Price',
        help='Chỉ áp dụng khi supply_type=trading — thay thế chi phí tính từ BOM.',
    )
    default_supplier_id = fields.Many2one(
        'res.partner', string='NCC mặc định (hàng trading)',
    )
    uom_id = fields.Many2one('uom.uom', string='Đơn vị tính')

    bom_ids = fields.One2many('dl.bom', 'product_id', string='BOM liên quan')
    bom_count = fields.Integer(compute='_compute_bom_count', string='Số BOM')

    @api.depends('bom_ids')
    def _compute_bom_count(self):
        for rec in self:
            rec.bom_count = len(rec.bom_ids)

    def action_view_boms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOM — %s') % self.name,
            'res_model': 'dl.bom',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }
