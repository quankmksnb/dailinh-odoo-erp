import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Data Model PROD-02: default_code validate ^[A-Z0-9\-]+$ (chữ hoa, số, gạch ngang)
_CODE_RE = re.compile(r"^[A-Z0-9\-]+$")


class ProductProduct(models.Model):
    """PROD-02 — dl.product.

    Theo Data Model (TDS Report 4, §4.2): SẢN PHẨM là bảng HỢP NHẤT cho cả 4
    loại nghiệp vụ, phân biệt qua ``product_kind``. Kế thừa MỞ RỘNG THUẦN
    ``product.product`` (``_inherit`` — KHÔNG tạo bảng mới): mọi bản ghi nằm
    trực tiếp trong ``product_product``, giữ nguyên vẹn search/report/tồn kho.

    Thiết kế cũ (dl.product/dl.semi.product/dl.material là 3 bảng delegation
    riêng qua ``_inherits``) đã bị BỎ — semi → material_processed, material giữ
    nguyên; đổi loại sản phẩm nay chỉ là đổi 1 field ``product_kind``.

    Pattern: để MỞ RỘNG product.product ĐỒNG THỜI thêm mixin mail.thread, phải
    khai cả ``_name`` (= 'product.product') LẪN ``_inherit`` dạng list chứa chính
    nó + mixin. Thiếu ``_name`` khi ``_inherit`` là list ⇒ Odoo báo
    "The _name attribute ... is not valid".
    """

    _name = "product.product"
    _inherit = ["product.product", "mail.thread", "mail.activity.mixin"]

    product_kind = fields.Selection(
        [
            ("manufactured", "Sản phẩm gia công"),
            ("trading", "Sản phẩm thương mại"),
            ("material", "Vật tư"),
            ("material_processed", "Vật tư đã gia công"),
        ],
        string="Loại sản phẩm",
        required=True,
        default="manufactured",
        tracking=True,
        help="Phân loại nghiệp vụ (Data Model PROD-02):\n"
        "• Gia công (manufactured): tự sản xuất theo BOM\n"
        "• Thương mại (trading): nhập về bán thẳng, tra giá NCC\n"
        "• Vật tư (material): NVL thô, tra giá NCC\n"
        "• Vật tư đã gia công (material_processed): cắt/gia công từ vật tư gốc, có BOM riêng",
    )

    # Hàng thương mại (trading): giá vốn nhập dùng trực tiếp làm chi phí khi báo
    # giá (không qua BOM). Chỉ áp dụng khi product_kind='trading'.
    purchase_cost = fields.Monetary(
        string="Giá vốn nhập",
        currency_field="currency_id",
        help="Chỉ dùng cho hàng thương mại (trading) — làm giá vốn trực tiếp khi báo giá.",
    )

    # ── Constraints ──────────────────────────────────────────────────────
    @api.constrains("default_code")
    def _check_default_code(self):
        """Data Model §6 Indexing: default_code UNIQUE + validate ^[A-Z0-9\\-]+$."""
        for rec in self:
            code = rec.default_code
            if not code:
                continue
            if not _CODE_RE.match(code):
                raise ValidationError(
                    _(
                        "Mã sản phẩm '%s' không hợp lệ — chỉ cho phép chữ IN HOA, "
                        "số và dấu gạch ngang (VD: CT-200, VT-001)."
                    )
                    % code
                )
            dup = self.with_context(active_test=False).search(
                [("default_code", "=", code), ("id", "!=", rec.id)], limit=1
            )
            if dup:
                raise ValidationError(
                    _("Mã sản phẩm '%s' đã tồn tại (%s).") % (code, dup.display_name)
                )
