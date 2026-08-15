from odoo import fields, models

# Ai được xem số tiền của từng cấu phần giá: Kế toán/Trưởng KD/CEO/Admin.
# Sales chỉ thấy giá bán, không thấy giá vốn cấu thành.
_COST_GROUPS = (
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
    "dl_base.dl_group_accountant,"
    "dl_base.dl_group_sales_manager"
)


class DlQuotationPriceComponent(models.Model):
    """Ảnh chụp BẤT BIẾN từng cấu phần giá của một dòng báo giá — dữ liệu nuôi
    bảng công thức ở trang Phân tích giá thành.

    Lúc tạo báo giá, engine chép sang đây các con số (số lượng, đơn giá, thành
    tiền) và nguồn gốc (model/id/version). Sau này giá NCC hay giá bán có đổi
    thì báo giá cũ vẫn giữ nguyên số — mọi field ở đây là dữ liệu tĩnh, không
    tính động theo rule sống."""

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
            ("recovery", "Thu hồi phế liệu"),
            ("operation", "Công đoạn"),
            ("operation_setup", "Phí setup công đoạn"),
            ("adjustment", "Chi phí chung/điều chỉnh"),
            ("markup", "Lợi nhuận (markup)"),
            ("discount", "Chiết khấu"),
            ("vat", "Thuế GTGT"),
        ],
        string="Loại cấu phần",
        required=True,
    )

    # Nguồn gốc cấu phần — lưu model/id/version rời thay vì reference, để không
    # bị ràng cứng vào bản ghi nguồn (nguồn có thể đổi, ảnh chụp thì không).
    # Ví dụ: product.supplierinfo / dl.bom / product.product.
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
        help="Khoản không bị trừ chiết khấu (để dành cho phase sau).",
    )
