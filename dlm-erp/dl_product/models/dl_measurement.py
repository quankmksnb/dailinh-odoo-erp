from odoo import fields, models


class DlMeasurementType(models.Model):
    """PROD-04 — dl.measurement.type [Model mới].

    Bảng định nghĩa ĐẠI LƯỢNG đo lường (Area / Length / Weight / Volume). Thay
    cho cơ chế công thức lưu-trong-DB cũ (dl.parametric.formula đã bỏ), việc
    tính vật tư từ kích thước dựa trên bộ Type → Shape → Param (PROD-04/05/06).
    """

    _name = "dl.measurement.type"
    _description = "Loại đo lường"
    _order = "name"

    name = fields.Char(string="Tên đại lượng", required=True)
    description = fields.Text(string="Mô tả")
    active = fields.Boolean(string="Đang sử dụng", default=True)

    shape_ids = fields.One2many(
        "dl.measurement.shape", "measurement_type_id", string="Hình dạng"
    )


class DlMeasurementShape(models.Model):
    """PROD-05 — dl.measurement.shape [Model mới].

    Định nghĩa HÌNH DẠNG đo lường (tấm phẳng, ống vuông rỗng, tròn...) thuộc một
    loại đo lường.
    """

    _name = "dl.measurement.shape"
    _description = "Hình dạng đo lường"
    _order = "measurement_type_id, name"

    measurement_type_id = fields.Many2one(
        "dl.measurement.type",
        string="Loại đo lường",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Tên hình dạng", required=True)
    # code: khóa để dispatch CÔNG THỨC HARD-CODE trong Python (vd 'flat_plate',
    # 'hollow_square_tube'). Cơ chế tính vật tư từ kích thước = code cứng theo
    # shape (tài liệu để mở phần "nơi lưu công thức"; đây là lựa chọn thiết kế).
    code = fields.Char(
        string="Mã hình dạng",
        help="Khóa dispatch công thức hard-code (vd: flat_plate, hollow_square_tube).",
    )
    default_coefficient = fields.Float(
        string="Hệ số mặc định",
        digits=(16, 4),
        help="Gợi ý hệ số khi dựng BOM (vd khối lượng riêng thép 7850 kg/m³). Sửa được trên từng dòng BOM.",
    )
    coefficient_label = fields.Char(
        string="Nhãn hệ số",
        default="Hệ số",
        help="Nhãn hiển thị cho hệ số (vd: Khối lượng riêng (kg/m³)).",
    )
    active = fields.Boolean(string="Đang sử dụng", default=True)

    param_ids = fields.One2many(
        "dl.measurement.shape.param", "shape_id", string="Tham số"
    )


class DlMeasurementShapeParam(models.Model):
    """PROD-06 — dl.measurement.shape.param [Model mới].

    Định nghĩa TÊN các tham số theo từng hình dạng (chiều dài, chiều rộng, độ
    dày, cạnh ngoài...) — dùng để tính vật tư từ kích thước.

    Ghi chú (theo Kịch bản dữ liệu, mục PROD-06 ⚠): model này chỉ định nghĩa
    TÊN tham số. Nơi lưu GIÁ TRỊ cụ thể cho từng sản phẩm material_processed và
    hệ số/công thức tính (density 7850 kg/m³...) hiện CHƯA được tài liệu chốt —
    để lại chờ xác nhận, không tự thêm field ngoài đặc tả.
    """

    _name = "dl.measurement.shape.param"
    _description = "Tham số hình dạng đo lường"
    _order = "shape_id, name"

    shape_id = fields.Many2one(
        "dl.measurement.shape",
        string="Hình dạng",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Tên tham số", required=True)
    # code: khóa để công thức hard-code đọc giá trị tham số (vd length/width/
    # thickness/side). Công thức map biến theo code này.
    code = fields.Char(
        string="Mã tham số",
        help="Khóa để công thức đọc giá trị (vd: length, width, thickness, side).",
    )
    active = fields.Boolean(string="Đang sử dụng", default=True)
