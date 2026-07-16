from odoo import fields, models

# Nhóm được xem cấu phần giá thành (giống BOM: chỉ Kế toán/Trưởng KD/CEO/Admin).
# Sales (BA) chỉ cần thấy giá bán ở dòng báo giá, không cần chi tiết chi phí.
_COST_GROUPS = (
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
    "dl_base.dl_group_accountant,"
    "dl_base.dl_group_sales_manager"
)


class DlQuotationPriceComponent(models.Model):
    """Snapshot BẤT BIẾN từng cấu phần giá của một dòng báo giá (Decision A2).

    Khi tạo báo giá, dịch vụ tính giá copy các giá trị vô hướng (qty, đơn giá,
    thành tiền) và metadata nguồn (model/id/revision) vào đây. Sau đó thay đổi
    supplierinfo.price, is_applied, BOM.total_material_cost hay list_price
    KHÔNG được làm đổi số của báo giá đã tạo — mọi field ở đây là dữ liệu tĩnh,
    không compute động theo rule sống.
    """

    _name = "dl.quotation.price.component"
    _description = "Cấu phần giá báo giá (snapshot)"
    _order = "quotation_line_id, id"

    quotation_id = fields.Many2one(
        "dl.quotation",
        string="Báo giá",
        required=True,
        index=True,
        ondelete="cascade",
    )
    quotation_line_id = fields.Many2one(
        "dl.quotation.line",
        string="Dòng báo giá",
        index=True,
        ondelete="cascade",
    )

    component_type = fields.Selection(
        [
            ("trading_base", "Giá gốc thương mại"),
            ("material", "Vật tư thô"),
            ("processed_material", "Bán thành phẩm"),
            ("discount", "Chiết khấu"),
            ("vat", "Thuế GTGT"),
        ],
        string="Loại cấu phần",
        required=True,
    )

    # Truy vết nguồn — dùng model/id/revision thay vì reference field để không
    # ràng buộc cứng vào bản ghi nguồn (bản ghi nguồn có thể đổi, snapshot thì
    # không). Ví dụ: product.supplierinfo / dl.bom / product.product.
    source_model = fields.Char(string="Model nguồn")
    source_id = fields.Integer(string="ID nguồn")
    source_revision = fields.Integer(string="Revision nguồn")
    material_id = fields.Many2one(
        "product.product",
        string="Vật tư/Sản phẩm",
        ondelete="set null",
    )

    qty = fields.Float(string="Số lượng", digits="Product Unit of Measure")
    unit_price = fields.Float(
        string="Đơn giá", digits="Product Price", groups=_COST_GROUPS,
    )
    rate = fields.Float(string="Tỷ lệ (%)", digits=(5, 2))
    amount = fields.Float(
        string="Thành tiền", digits="Product Price", groups=_COST_GROUPS,
    )
    no_discount = fields.Boolean(
        string="Không chịu chiết khấu",
        default=False,
        help="Khoản không nằm trong cơ sở chịu chiết khấu (dành cho P1).",
    )
