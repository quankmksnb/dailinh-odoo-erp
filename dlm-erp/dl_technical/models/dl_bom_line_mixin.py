import math

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Rule/Shape LẤY TỪ DB (dl.measurement.type/dl.measurement.shape — không cho
# tạo mới từ dòng BOM, xem views: option no_create/no_create_edit). Vì chỉ có
# một số Shape cố định, công thức tính định mức HARD-CODE ở đây theo
# shape.code, đọc trực tiếp từ các field kích thước khai báo cứng bên dưới
# (KHÔNG dùng bảng con kích thước chung) — thêm Shape mới = thêm field kích
# thước (nếu cần) + 1 nhánh code ở đây + xử lý ẩn/hiện tương ứng trong view.
# Dùng chung cho dl.bom.line VÀ dl.bom.template.line (qua DlBomLineMixin).
#
# ⚠ Khi tạo Shape mới ở màn "Hình dạng đo lường" (Sản phẩm > Đo lường), cột
# "Mã hình dạng" (code) PHẢI gõ đúng 1 trong các giá trị dưới đây thì mới tự
# tính được — nếu không hệ thống coi là "chưa có công thức" và để nhập tay.
#
# Rule (đại lượng)   Shape                    code                    Hệ số?
# -----------------  -----------------------  ----------------------  ------
# Khối lượng         Tấm phẳng                flat_plate               Có
# Khối lượng         Ống vuông rỗng           hollow_square_tube       Có
# Khối lượng         Ống tròn rỗng            hollow_round_tube        Có
# Khối lượng         Thanh đặc tròn           solid_round_bar          Có
# Khối lượng         Thanh đặc vuông          solid_square_bar         Có
# Diện tích          Hình chữ nhật            area_rectangle           Không
# Diện tích          Hình vuông               area_square              Không
# Diện tích          Hình tròn                area_circle              Không
# Diện tích          Hình tam giác            area_triangle            Không
# Chu vi             Hình chữ nhật            perimeter_rectangle      Không
# Chu vi             Hình vuông               perimeter_square         Không
# Chu vi             Hình tròn                perimeter_circle         Không
# Thể tích           Hình hộp chữ nhật        volume_box               Không
# Thể tích           Hình lập phương          volume_cube              Không
# Thể tích           Hình trụ                 volume_cylinder          Không
# Thể tích           Hình cầu                 volume_sphere            Không
# Chiều dài          Đoạn thẳng               length_segment           Không
# ---------------------------------------------------------------------------
SHAPE_FLAT_PLATE = "flat_plate"
SHAPE_HOLLOW_SQUARE_TUBE = "hollow_square_tube"
SHAPE_HOLLOW_ROUND_TUBE = "hollow_round_tube"
SHAPE_SOLID_ROUND_BAR = "solid_round_bar"
SHAPE_SOLID_SQUARE_BAR = "solid_square_bar"
SHAPE_AREA_RECTANGLE = "area_rectangle"
SHAPE_AREA_SQUARE = "area_square"
SHAPE_AREA_CIRCLE = "area_circle"
SHAPE_AREA_TRIANGLE = "area_triangle"
SHAPE_PERIMETER_RECTANGLE = "perimeter_rectangle"
SHAPE_PERIMETER_SQUARE = "perimeter_square"
SHAPE_PERIMETER_CIRCLE = "perimeter_circle"
SHAPE_VOLUME_BOX = "volume_box"
SHAPE_VOLUME_CUBE = "volume_cube"
SHAPE_VOLUME_CYLINDER = "volume_cylinder"
SHAPE_VOLUME_SPHERE = "volume_sphere"
SHAPE_LENGTH_SEGMENT = "length_segment"

# Shape có dùng "Hệ số" (khối lượng riêng) — chỉ nhóm Khối lượng. Dùng ở view
# (invisible=) để ẩn field Hệ số với Diện tích/Chu vi/Thể tích/Chiều dài.
WEIGHT_SHAPE_CODES = (
    SHAPE_FLAT_PLATE, SHAPE_HOLLOW_SQUARE_TUBE, SHAPE_HOLLOW_ROUND_TUBE,
    SHAPE_SOLID_ROUND_BAR, SHAPE_SOLID_SQUARE_BAR,
)
# Toàn bộ code có công thức — group "Kích thước" chỉ hiện khi Shape thuộc tập
# này; Shape khác/không có code → nhập thẳng Quantity (Step 5).
KNOWN_SHAPE_CODES = WEIGHT_SHAPE_CODES + (
    SHAPE_AREA_RECTANGLE, SHAPE_AREA_SQUARE, SHAPE_AREA_CIRCLE, SHAPE_AREA_TRIANGLE,
    SHAPE_PERIMETER_RECTANGLE, SHAPE_PERIMETER_SQUARE, SHAPE_PERIMETER_CIRCLE,
    SHAPE_VOLUME_BOX, SHAPE_VOLUME_CUBE, SHAPE_VOLUME_CYLINDER, SHAPE_VOLUME_SPHERE,
    SHAPE_LENGTH_SEGMENT,
)

# Shape chỉ cần 1 kích thước "Cạnh" (dim_side) — dùng chung set này ở view.
SIDE_ONLY_SHAPE_CODES = (
    SHAPE_HOLLOW_SQUARE_TUBE, SHAPE_SOLID_SQUARE_BAR,
    SHAPE_AREA_SQUARE, SHAPE_PERIMETER_SQUARE, SHAPE_VOLUME_CUBE,
)
# Shape cần "Đường kính ngoài" (dim_diameter).
DIAMETER_SHAPE_CODES = (
    SHAPE_HOLLOW_ROUND_TUBE, SHAPE_SOLID_ROUND_BAR,
    SHAPE_AREA_CIRCLE, SHAPE_PERIMETER_CIRCLE, SHAPE_VOLUME_CYLINDER, SHAPE_VOLUME_SPHERE,
)

# Field dùng chung khi copy 1 dòng mixin sang model mixin khác (vd Tạo BOM từ
# BOM mẫu) — đã gồm cả field kích thước vì giờ nằm ngay trên mixin.
BOM_LINE_MIXIN_FIELDS = [
    "material_id", "measurement_type_id", "measurement_shape_id",
    "measurement_coefficient", "dim_length", "dim_width", "dim_thickness",
    "dim_side", "dim_diameter", "dim_height", "quantity", "waste_config_id",
    "waste_rate", "is_override", "override_reason",
]


class DlBomLineMixin(models.AbstractModel):
    """Field/logic dùng chung cho 1 dòng BOM — dl.bom.line (BOM sản phẩm) và
    dl.bom.template.line (BOM mẫu). Quy trình theo màn "Product BOM"/"BOM
    Template" (đều theo Step 1-6):
      1. Chọn Material (material_id — domain đã bao vật tư thô + đã gia công,
         không cần field Bán thành phẩm riêng nữa).
      2. Chọn Calculation Rule (measurement_type_id — có sẵn trong DB, không
         tạo mới ở đây).
      3. (optional) Chọn Shape, lọc theo Rule đã chọn (có sẵn trong DB, không
         tạo mới ở đây).
      4. (optional, nếu có Rule+Shape) Nhập kích thước — field cứng theo
         Shape, ẩn/hiện đúng field cần trong view (chỉ vài Shape nên bao hết
         được). Shape không thuộc nhóm cơ bản / không chọn Shape → nhập thẳng
         Quantity ở Step 5.
      5. Nhập Quantity (số thực dùng — computed_quantity chỉ để xem kết quả
         hệ thống tính).
      6. Liên kết Waste Percentage từ Cấu hình (waste_config_id, dl_config).
    """

    _name = "dl.bom.line.mixin"
    _description = "Dòng BOM — trường & logic dùng chung"

    material_id = fields.Many2one(
        "product.product",
        string="Vật tư",
        required=True,
        domain=[("product_kind", "in", ("material", "material_processed"))],
    )

    # Step 2 — Rule (đại lượng đo: Area/Length/Width/Height/Perimeter/Volume...).
    measurement_type_id = fields.Many2one(
        "dl.measurement.type",
        string="Rule",
        help="Đại lượng đo dùng để tính định mức (vd Area, Length, Volume...). "
             "Danh sách quản lý sẵn trong hệ thống, không tạo mới ở đây.",
    )

    # Step 3 (optional) — Shape, lọc theo Rule đã chọn ở trên.
    measurement_shape_id = fields.Many2one(
        "dl.measurement.shape",
        string="Shape",
        domain="[('measurement_type_id', '=', measurement_type_id)]",
        help="Chọn hình dạng để nhập kích thước và tự tính định mức theo công "
             "thức. Danh sách quản lý sẵn trong hệ thống, không tạo mới ở đây.",
    )
    # Related để dùng trong invisible= của view (ẩn/hiện field kích thước đúng
    # theo Shape) — không thể tham chiếu measurement_shape_id.code trực tiếp.
    shape_code = fields.Char(related="measurement_shape_id.code", string="Mã Shape")

    measurement_coefficient = fields.Float(
        string="Hệ số",
        digits=(16, 4),
        help="Hệ số tính (vd khối lượng riêng). Mặc định theo hình dạng, sửa được.",
    )

    # Step 4 — kích thước (mm), field cứng theo Shape (chỉ hiện đúng field cần
    # dùng — xem invisible= trong view theo shape_code).
    dim_length = fields.Float(string="Chiều dài (mm)", digits=(16, 3))
    dim_width = fields.Float(string="Chiều rộng (mm)", digits=(16, 3))
    dim_thickness = fields.Float(string="Độ dày (mm)", digits=(16, 3))
    dim_side = fields.Float(string="Cạnh ngoài (mm)", digits=(16, 3))
    dim_diameter = fields.Float(string="Đường kính ngoài (mm)", digits=(16, 3))
    dim_height = fields.Float(string="Chiều cao (mm)", digits=(16, 3))

    # Kết quả hiển thị định mức hệ thống tự tính từ Shape+kích thước (chỉ để
    # xem — Step 5 "quantity" mới là số thực dùng, có thể sửa/ghi đè).
    computed_quantity = fields.Float(
        string="Định mức (hệ thống tính)",
        compute="_compute_computed_quantity",
        digits="Product Unit of Measure",
    )

    # Step 5 — nếu không chọn Shape, hoặc Shape chưa có công thức, nhập định
    # mức trực tiếp tại đây.
    quantity = fields.Float(
        string="Số lượng",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )

    # Step 6 — liên kết Waste % từ Cấu hình (dl_config.dl.pricing.waste).
    waste_config_id = fields.Many2one(
        "dl.pricing.waste",
        string="Hao hụt (Cấu hình)",
        ondelete="set null",
        help="Chọn nhóm hao hụt đã khai ở Cấu hình — tự điền % hao hụt, sửa được.",
    )
    waste_rate = fields.Float(
        string="Tỷ lệ hao hụt (%)",
        default=0.0,
        digits=(5, 2),
    )

    effective_qty = fields.Float(
        string="Số lượng thực tế",
        compute="_compute_effective_qty",
        store=True,
        digits="Product Unit of Measure",
    )

    is_override = fields.Boolean(
        string="Ghi đè số lượng",
        default=False,
    )
    override_reason = fields.Text(
        string="Lý do ghi đè",
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị tính",
        compute="_compute_uom",
        store=True,
    )

    # ==========================================================
    # COMPUTE
    # ==========================================================

    @api.depends("quantity", "waste_rate")
    def _compute_effective_qty(self):
        for rec in self:
            rec.effective_qty = rec.quantity * (1 + rec.waste_rate / 100)

    @api.depends("material_id")
    def _compute_uom(self):
        for rec in self:
            rec.uom_id = rec.material_id.uom_id if rec.material_id else False

    @api.depends(
        "measurement_shape_id", "measurement_coefficient",
        "dim_length", "dim_width", "dim_thickness", "dim_side",
        "dim_diameter", "dim_height",
    )
    def _compute_computed_quantity(self):
        for rec in self:
            qty = rec._measurement_quantity()
            rec.computed_quantity = qty if qty is not None else 0.0

    # ==========================================================
    # ONCHANGE
    # ==========================================================

    @api.onchange("waste_config_id")
    def _onchange_waste_config(self):
        if self.waste_config_id:
            self.waste_rate = self.waste_config_id.waste_pct

    @api.onchange("measurement_type_id")
    def _onchange_measurement_type(self):
        if (self.measurement_shape_id
                and self.measurement_shape_id.measurement_type_id != self.measurement_type_id):
            self.measurement_shape_id = False

    @api.onchange("measurement_shape_id")
    def _onchange_measurement_shape(self):
        shape = self.measurement_shape_id
        self.dim_length = self.dim_width = self.dim_thickness = self.dim_side = 0.0
        self.dim_diameter = self.dim_height = 0.0
        self.measurement_coefficient = shape.default_coefficient if shape else 0.0

    @api.onchange(
        "measurement_shape_id", "measurement_coefficient",
        "dim_length", "dim_width", "dim_thickness", "dim_side",
        "dim_diameter", "dim_height",
    )
    def _onchange_measurement_values(self):
        if self.is_override:
            return
        qty = self._measurement_quantity()
        if qty is not None and qty > 0:
            self.quantity = qty

    def _measurement_quantity(self):
        """Tính định mức từ kích thước + hệ số — công thức hard-code theo
        shape.code (chỉ vài Shape cố định, xử lý trực tiếp ở đây, xem bảng
        Rule/Shape/code ở đầu file). Trả về None nếu không chọn Shape / Shape
        không có công thức (giữ nguyên quantity đang có — nhập trực tiếp).
        Kích thước nhập bằng mm, quy đổi sang mét trước khi tính."""
        self.ensure_one()
        shape = self.measurement_shape_id
        if not shape or not shape.code:
            return None
        code = shape.code
        if code not in KNOWN_SHAPE_CODES:
            return None

        coef = self.measurement_coefficient or 0.0
        length = self.dim_length / 1000.0
        width = self.dim_width / 1000.0
        thickness = self.dim_thickness / 1000.0
        side = self.dim_side / 1000.0
        radius = (self.dim_diameter / 2.0) / 1000.0
        height = self.dim_height / 1000.0

        if code == SHAPE_FLAT_PLATE:
            # Tấm phẳng: KL = dài × rộng × dày × khối lượng riêng.
            return length * width * thickness * coef

        if code == SHAPE_HOLLOW_SQUARE_TUBE:
            # Ống vuông rỗng: KL = (cạnh² − (cạnh−2·dày)²) × dài × KLR.
            inner = max(side - 2 * thickness, 0.0)
            return (side ** 2 - inner ** 2) * length * coef

        if code == SHAPE_HOLLOW_ROUND_TUBE:
            # Ống tròn rỗng: KL = π×(R² − (R−dày)²) × dài × KLR.
            inner_r = max(radius - thickness, 0.0)
            return math.pi * (radius ** 2 - inner_r ** 2) * length * coef

        if code == SHAPE_SOLID_ROUND_BAR:
            # Thanh đặc tròn: KL = π×R² × dài × KLR.
            return math.pi * radius ** 2 * length * coef

        if code == SHAPE_SOLID_SQUARE_BAR:
            # Thanh đặc vuông: KL = cạnh² × dài × KLR.
            return side ** 2 * length * coef

        if code == SHAPE_AREA_RECTANGLE:
            return length * width

        if code == SHAPE_AREA_SQUARE:
            return side ** 2

        if code == SHAPE_AREA_CIRCLE:
            return math.pi * radius ** 2

        if code == SHAPE_AREA_TRIANGLE:
            # Đáy dùng chung field Chiều dài.
            return 0.5 * length * height

        if code == SHAPE_PERIMETER_RECTANGLE:
            return 2 * (length + width)

        if code == SHAPE_PERIMETER_SQUARE:
            return 4 * side

        if code == SHAPE_PERIMETER_CIRCLE:
            return 2 * math.pi * radius

        if code == SHAPE_VOLUME_BOX:
            return length * width * height

        if code == SHAPE_VOLUME_CUBE:
            return side ** 3

        if code == SHAPE_VOLUME_CYLINDER:
            return math.pi * radius ** 2 * height

        if code == SHAPE_VOLUME_SPHERE:
            return (4.0 / 3.0) * math.pi * radius ** 3

        if code == SHAPE_LENGTH_SEGMENT:
            return length

        return None

    def _mixin_copy_vals(self):
        """Trả về dict giá trị các field dùng chung — dùng khi copy 1 dòng
        sang model mixin khác (vd Tạo BOM từ BOM mẫu)."""
        self.ensure_one()
        vals = {}
        for name in BOM_LINE_MIXIN_FIELDS:
            field = self._fields[name]
            value = self[name]
            vals[name] = value.id if field.type == "many2one" else value
        return vals

    # ==========================================================
    # CONSTRAINT
    # ==========================================================

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Số lượng phải lớn hơn 0."))

    @api.constrains("waste_rate")
    def _check_waste_rate(self):
        for rec in self:
            if rec.waste_rate < 0:
                raise ValidationError(_("Tỷ lệ hao hụt không được nhỏ hơn 0."))

    @api.constrains("is_override", "override_reason")
    def _check_override_reason(self):
        for rec in self:
            if rec.is_override and not rec.override_reason:
                raise ValidationError(_("Vui lòng nhập lý do khi ghi đè số lượng."))


class DlMeasurementShapeCodeCheck(models.Model):
    """Extension nhỏ — chặn gõ sai "Mã hình dạng" (code) ngay khi lưu Shape,
    vì BOM chỉ tự tính được với đúng 1 trong các code đã hard-code ở trên.
    Đặt ở dl_technical (không phải dl_product) vì bộ code hợp lệ gắn chặt với
    công thức Python ở đây, không phải khái niệm chung của dl_product."""

    _inherit = "dl.measurement.shape"

    @api.constrains("code")
    def _check_code_known(self):
        for rec in self:
            if rec.code and rec.code not in KNOWN_SHAPE_CODES:
                raise ValidationError(_(
                    "Mã hình dạng \"%s\" không khớp công thức nào đã code sẵn.\n"
                    "Chỉ dùng đúng 1 trong các mã sau: %s\n"
                    "(để trống nếu Shape này chưa có công thức tự tính, Kỹ thuật sẽ nhập tay Quantity)."
                ) % (rec.code, ", ".join(KNOWN_SHAPE_CODES)))
