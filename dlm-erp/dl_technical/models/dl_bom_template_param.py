from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


# Các ô của một dòng vật tư mà tham số sản phẩm có thể ánh xạ vào.
# Trùng tên field trên dl.bom.line.mixin + "quantity" (số lượng cố định theo
# tham số, vd số nan = tham số N).
#
# Mặt cắt (độ dày / cạnh / đường kính) ĐÃ RỜI sang quy cách của VẬT TƯ nên
# không còn là đích ánh xạ — xem thiết kế §15.1. Chi tiết cần nhiều đoạn cắt
# (vd "khung bao = 2×(D+R)") nay diễn đạt bằng 2 DÒNG, mỗi dòng một chiều —
# vừa đúng bản chất, vừa ra cut list thật cho xưởng (§15.2).
_TARGET_FIELDS = [
    ("dim_length", "Chiều dài đoạn (mm)"),
    ("dim_width", "Chiều rộng (mm)"),
    ("piece_count", "Số đoạn"),
    ("quantity", "Số lượng"),
]


# Đơn vị của một tham số — SUY từ vai trò kích thước chứ không khai tay: mọi
# kích thước CẮT trong hệ thống đều tính bằng mm (quy ước dim_* ở
# dl_bom_line_mixin), còn tham số không phải kích thước (vd số nan) là số đếm
# nên không có đơn vị. Dùng chung cho cả tham số MẪU lẫn bản chép sang RFQ
# (dl.quotation.request.line.param) để hai màn không nói hai đơn vị khác nhau.
DIM_UNIT = "mm"


def dim_unit_hint(dim_role):
    """Đơn vị hiện cạnh ô nhập của một tham số ("mm" hoặc rỗng)."""
    return DIM_UNIT if dim_role and dim_role != "none" else ""


class DlBomTemplateParam(models.Model):
    """Tham số CẤP SẢN PHẨM của một BOM mẫu (Đợt 4 — thiết kế §7.4a).

    Khác hẳn kích thước cấp DÒNG VẬT TƯ (dl.bom.line.mixin.dim_*): đây là các
    đại lượng của cả sản phẩm (Dài/Rộng/Cao của cái bàn), KTV nhập MỘT LẦN khi
    xử lý một đơn; hệ thống suy kích thước từng thanh vật tư từ chúng qua ánh xạ
    tuyến tính (dl.bom.template.line.param.map), rồi để công thức hình dạng có
    sẵn tính định mức. `code` là mã tham chiếu (D/R/C), KHÔNG phải biểu thức."""

    _name = "dl.bom.template.param"
    _description = "Tham số BOM mẫu"
    _order = "sequence, id"

    bom_template_id = fields.Many2one(
        "dl.bom.template", string="BOM mẫu",
        required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(
        string="Mã", required=True,
        help="Mã tham chiếu ngắn (vd D, R, C) — dùng để ánh xạ vào dòng vật tư.")
    name = fields.Char(string="Tên tham số", required=True)
    # Vai trò kích thước — để tự điền từ mô tả Sales (dimension_note) khi xử lý.
    dim_role = fields.Selection(
        [
            ("length", "Chiều dài"),
            ("width", "Chiều rộng"),
            ("height", "Chiều cao"),
            ("thickness", "Độ dày"),
            ("side", "Cạnh"),
            ("none", "— (không tự đọc)"),
        ],
        string="Vai trò kích thước", default="none",
        help="Dùng để tự đọc giá trị từ mô tả Sales (vd '1400x830, cao 750'). "
             "Để '—' nếu tham số không phải kích thước đọc được từ văn bản.")
    default_value = fields.Float(string="Giá trị mặc định")
    value_min = fields.Float(string="Tối thiểu")
    value_max = fields.Float(string="Tối đa")
    required = fields.Boolean(string="Bắt buộc", default=True)
    # Hiện cạnh Giá trị/Tối thiểu/Tối đa để KTV biết mấy con số này là mm.
    unit_hint = fields.Char(string="Đơn vị", compute="_compute_unit_hint")

    @api.depends("dim_role")
    def _compute_unit_hint(self):
        for rec in self:
            rec.unit_hint = dim_unit_hint(rec.dim_role)

    _sql_constraints = [
        ("code_uniq", "unique(bom_template_id, code)",
         "Mã tham số đã tồn tại trong BOM mẫu này."),
    ]

    @api.constrains("value_min", "value_max")
    def _check_domain(self):
        for rec in self:
            if rec.value_min and rec.value_max and rec.value_min > rec.value_max:
                raise ValidationError(_(
                    "Tham số %s: giá trị tối thiểu không được lớn hơn tối đa.")
                    % rec.code)


class DlBomTemplateLineParamMap(models.Model):
    """Ánh xạ tuyến tính TỪ một tham số sản phẩm VÀO một ô kích thước của dòng
    vật tư mẫu (thiết kế §7.4b): `giá trị = factor × tham số + offset`.

    KHÔNG dùng biểu thức tự do (tôn trọng V3 nguyên tắc 5). Phần phi tuyến
    (diện tích/chu vi/khối lượng) do công thức hình dạng (measurement_shape) đã
    có sẵn lo — ánh xạ chỉ cần phép nhân/cộng. Một dòng có thể có nhiều ánh xạ
    (vd mặt bàn: dim_length ← D và dim_width ← R)."""

    _name = "dl.bom.template.line.param.map"
    _description = "Ánh xạ tham số → dòng vật tư mẫu"
    _order = "id"

    template_line_id = fields.Many2one(
        "dl.bom.template.line", string="Dòng vật tư mẫu",
        required=True, ondelete="cascade", index=True)
    # Related (store) để lọc param_id trong đúng BOM mẫu của dòng.
    bom_template_id = fields.Many2one(
        related="template_line_id.bom_template_id", store=True, index=True)
    target_field = fields.Selection(
        _TARGET_FIELDS, string="Ánh xạ vào", required=True)
    # Domain lọc theo mẫu được đặt ở VIEW bằng parent.bom_template_id (đáng tin
    # cả khi dòng ánh xạ chưa lưu). Không domain ở model vì field related
    # bom_template_id của bản ghi MỚI chưa resolve kịp ⇒ dropdown rỗng.
    param_id = fields.Many2one(
        "dl.bom.template.param", string="Tham số", required=True,
        ondelete="cascade")
    factor = fields.Float(string="Hệ số nhân", default=1.0)
    offset = fields.Float(string="Cộng thêm", default=0.0)

    @api.constrains("param_id", "template_line_id")
    def _check_same_template(self):
        for rec in self:
            if rec.param_id.bom_template_id != rec.template_line_id.bom_template_id:
                raise ValidationError(_(
                    "Ánh xạ phải dùng tham số thuộc cùng BOM mẫu với dòng vật tư."))
