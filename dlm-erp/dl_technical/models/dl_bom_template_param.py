from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


# Danh sách ô kích thước/số lượng trên 1 dòng vật tư mẫu mà tham số có thể ánh xạ vào.
_TARGET_FIELDS = [
    ("dim_length", "Chiều dài đoạn (mm)"),
    ("dim_width", "Chiều rộng (mm)"),
    ("piece_count", "Số đoạn"),
    ("quantity", "Số lượng"),
]


class DlBomTemplateParam(models.Model):
    # Tham số cấp sản phẩm (VD Dài/Rộng/Cao) của 1 BOM mẫu — KTV nhập 1 lần khi xử lý RFQ,
    # dùng để tự suy kích thước từng dòng vật tư qua bảng ánh xạ tuyến tính bên dưới.

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

    _sql_constraints = [
        ("code_uniq", "unique(bom_template_id, code)",
         "Mã tham số đã tồn tại trong BOM mẫu này."),
    ]

    # Validate lúc lưu tham số trên form BOM mẫu: chặn tối thiểu > tối đa.
    @api.constrains("value_min", "value_max")
    def _check_domain(self):
        for rec in self:
            if rec.value_min and rec.value_max and rec.value_min > rec.value_max:
                raise ValidationError(_(
                    "Tham số %s: giá trị tối thiểu không được lớn hơn tối đa.")
                    % rec.code)


class DlBomTemplateLineParamMap(models.Model):
    # Công thức ánh xạ 1 tham số sản phẩm vào 1 ô của dòng vật tư mẫu: giá trị = factor × tham số + offset.

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

    # Validate lúc lưu ánh xạ: tham số chọn phải thuộc đúng BOM mẫu của dòng vật tư.
    @api.constrains("param_id", "template_line_id")
    def _check_same_template(self):
        for rec in self:
            if rec.param_id.bom_template_id != rec.template_line_id.bom_template_id:
                raise ValidationError(_(
                    "Ánh xạ phải dùng tham số thuộc cùng BOM mẫu với dòng vật tư."))
