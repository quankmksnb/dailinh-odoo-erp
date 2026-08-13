from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Field dùng chung khi copy 1 dòng mixin sang model mixin khác (vd Tạo BOM từ
# BOM mẫu, bộ sinh định mức tham số).
#
# 🔴 BẪY (thiết kế §13.5): thiếu "piece_count" ở đây thì mọi BOM tạo từ mẫu
# ÂM THẦM mất số đoạn, rơi về 1 — giá vốn hụt mà không có cảnh báo nào.
# ---------------------------------------------------------------------------
BOM_LINE_MIXIN_FIELDS = [
    "material_id", "dim_length", "dim_width", "piece_count", "quantity",
    "complexity_id", "waste_rate", "is_override", "override_reason",
]


class DlBomLineMixin(models.AbstractModel):
    """Field/logic dùng chung cho 1 dòng BOM — dl.bom.line (BOM sản phẩm) và
    dl.bom.template.line (BOM mẫu).

    Thiết kế: docs/Doi_chieu_du_lieu_doanh_nghiep_va_thiet_ke_dinh_muc_vat_tu.md

    Quy trình nhập gọn còn 3 bước (§4):
      1. Chọn Vật tư — vật tư đã mang sẵn ĐVT mua, quy cách, chiều dài cây/khổ tấm.
      2. Nhập KÍCH THƯỚC CẮT theo kiểu tính của vật tư:
           cắt đoạn → chiều dài đoạn + số đoạn
           tấm      → dài × rộng + số tấm
           đếm/định lượng → nhập thẳng Số lượng
      3. Hao hụt: lấy từ vật tư × Mức phức tạp; thu hồi phế liệu theo vật tư.

    ⚠️ Cơ chế Rule/Shape cũ (dl.measurement.*) đã RỜI KHỎI dòng BOM (§6, §14).
    Định mức nay suy từ `material_id.dlm_calc_kind` × nhóm ĐVT của vật tư.
    """

    _name = "dl.bom.line.mixin"
    _description = "Dòng BOM — trường & logic dùng chung"

    material_id = fields.Many2one(
        "product.product",
        string="Vật tư",
        required=True,
        # Loại vật tư đã Ngừng (obsolete) khỏi dropdown chọn dòng BOM mới — giữ
        # lại Nháp (BTP đang xử lý) nên dùng '!= obsolete' chứ không ép '= active'.
        # Dòng cũ đã trỏ vật tư sau này bị Ngừng vẫn hiển thị (ngoài domain) như
        # tín hiệu cần thay; không tự xoá để giữ lịch sử BOM.
        domain=[("product_kind", "in", ("material", "material_processed")),
                ("dlm_lifecycle_state", "!=", "obsolete")],
    )

    # Kiểu tính + ĐVT lấy thẳng từ vật tư — dùng để ẩn/hiện đúng ô trong view.
    material_calc_kind = fields.Selection(
        related="material_id.dlm_calc_kind", string="Kiểu tính", readonly=True)
    material_uom_name = fields.Char(
        related="material_id.uom_id.name", string="ĐVT", readonly=True)

    # ── Kích thước cắt (mm) ──────────────────────────────────────────────
    # Chỉ còn 2 ô: mặt cắt (cạnh/đường kính/độ dày) nay là quy cách của VẬT TƯ,
    # không gõ lại mỗi dòng nữa — đó là cách xoá hẳn lỗi nhập nhầm mặt cắt.
    #
    # Cố ý giữ MILIMÉT: đây là số đọc thẳng từ bản vẽ (650 · 940 · 1200), gõ
    # 0,65 m thay cho 650 mm chỉ tạo thêm cơ hội lệch dấu phẩy. Quy cách MUA
    # trên vật tư thì ngược lại, khai theo MÉT — xem _dlm_auto_quantity.
    dim_length = fields.Float(string="Chiều dài đoạn (mm)", digits=(16, 3))
    dim_width = fields.Float(string="Chiều rộng (mm)", digits=(16, 3))
    piece_count = fields.Integer(
        string="Số đoạn", default=1,
        help="Số đoạn cắt cùng chiều dài (vd chân bàn 650mm × 4). "
             "Với vật tư dạng tấm: số tấm.")

    computed_quantity = fields.Float(
        string="Định mức (hệ thống tính)",
        compute="_compute_computed_quantity",
        digits="Product Unit of Measure",
    )

    quantity = fields.Float(
        string="Số lượng",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )

    # ── Hao hụt: NGUỒN là hệ số hao hụt trên VẬT TƯ (material.dlm_waste_rate).
    # Kỹ thuật chọn Mức phức tạp cho dòng này; % hao hụt áp dụng = hao hụt cơ sở
    # của vật tư × hệ số phức tạp. waste_rate vẫn cho sửa tay (ghi đè).
    complexity_id = fields.Many2one(
        "dl.pricing.complexity.level",
        string="Mức phức tạp",
        ondelete="set null",
        help="Hệ số phức tạp nhân vào tỷ lệ hao hụt cơ sở của vật tư khi tính giá.",
    )
    waste_rate = fields.Float(
        string="Tỷ lệ hao hụt (%)",
        default=0.0,
        digits=(5, 2),
        help="Tự tính = hao hụt cơ sở của vật tư × hệ số phức tạp; sửa tay được.",
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
        help="Bật để nhập thẳng số lượng (vd biết sẵn cần 3.5 cây) thay vì để "
             "hệ tính từ kích thước cắt.",
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

    @api.depends("material_id", "dim_length", "dim_width", "piece_count")
    def _compute_computed_quantity(self):
        for rec in self:
            qty = rec._dlm_auto_quantity()
            rec.computed_quantity = qty if qty is not None else 0.0

    # ==========================================================
    # ĐỊNH MỨC — 5 ca theo (kiểu tính × nhóm ĐVT), thiết kế §13.2
    # ==========================================================

    def _dlm_auto_quantity(self):
        """Định mức tự tính, ĐÃ theo đúng uom_id của vật tư.

        Trả None khi không tự tính được ⇒ caller giữ nguyên `quantity` mà kỹ
        thuật nhập tay (vật tư dạng đếm/định lượng, hoặc thiếu khai quy cách).
        """
        self.ensure_one()
        mat = self.material_id
        if not mat:
            return None
        kind = mat.dlm_calc_kind
        group = mat._dlm_uom_group()
        n = max(self.piece_count or 1, 1)

        if kind == "cut_length":
            total_mm = (self.dim_length or 0.0) * n
            if total_mm <= 0:
                return None
            total_m = total_mm / 1000.0        # mm (bản vẽ) → m (quy cách mua)
            if group == "weight":                       # ĐVT kg
                return total_m * (mat.dlm_mass_per_meter or 0.0)
            if group == "length":                       # ĐVT mét
                return total_m
            if mat.dlm_stock_length:                    # ĐVT cây — cây khai theo m
                return total_m / mat.dlm_stock_length
            return None

        if kind == "sheet":
            area_mm2 = (self.dim_length or 0.0) * (self.dim_width or 0.0) * n
            if area_mm2 <= 0:
                return None
            area_m2 = area_mm2 * 1e-6         # mm² (bản vẽ) → m² (quy cách mua)
            if group == "weight":                       # ĐVT kg
                return area_m2 * (mat.dlm_mass_per_sqm or 0.0)
            if group == "surface":                      # ĐVT m²
                return area_m2
            if mat.dlm_sheet_w and mat.dlm_sheet_h:     # ĐVT tấm — khổ khai theo m
                return area_m2 / (mat.dlm_sheet_w * mat.dlm_sheet_h)
            return None

        return None                 # count · bulk ⇒ nhập thẳng `quantity`

    # ==========================================================
    # CRUD
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        """RV-07 — Dòng BOM tạo BẰNG CODE (bộ sinh định mức tham số, import dữ
        liệu) KHÔNG chạy onchange nên % hao hụt không tự bung theo hệ số phức
        tạp ⇒ hao hụt thấp hơn thực, giá vốn thiếu. Nếu người tạo chưa nêu
        waste_rate rõ ràng mà dòng đã có vật tư, tự tính = hao hụt cơ sở của vật
        tư × hệ số phức tạp (đối xứng _onchange_material_waste của luồng UI).
        Không đụng khi caller đã truyền waste_rate (vd _mixin_copy_vals của BOM
        mẫu đã mang sẵn giá trị đúng)."""
        Product = self.env["product.product"]
        for vals in vals_list:
            if "waste_rate" not in vals and vals.get("material_id"):
                material = Product.browse(vals["material_id"])
                factor = 1.0
                if vals.get("complexity_id"):
                    factor = self.env["dl.pricing.complexity.level"].browse(
                        vals["complexity_id"]).factor or 1.0
                vals["waste_rate"] = (material.dlm_waste_rate or 0.0) * factor
        return super().create(vals_list)

    # ==========================================================
    # ONCHANGE
    # ==========================================================

    @api.onchange("material_id", "complexity_id")
    def _onchange_material_waste(self):
        """Tự tính % hao hụt = hao hụt cơ sở của vật tư × hệ số phức tạp."""
        if not self.material_id:
            return
        factor = self.complexity_id.factor if self.complexity_id else 1.0
        self.waste_rate = (self.material_id.dlm_waste_rate or 0.0) * factor

    @api.onchange("material_id", "dim_length", "dim_width", "piece_count")
    def _onchange_dlm_auto_quantity(self):
        """Tự điền Số lượng từ kích thước cắt — TRỪ KHI kỹ thuật bật ghi đè.

        Cảnh báo MỀM khi vật tư chưa khai đủ để tự tính: nêu đúng tên field
        thiếu thay vì để định mức im lặng ra 0."""
        if self.is_override:
            return
        qty = self._dlm_auto_quantity()
        if qty is not None and qty > 0:
            self.quantity = qty
        if not self.material_id:
            return
        missing = self.material_id._dlm_calc_missing_fields()
        if missing:
            return {"warning": {
                "title": _("Vật tư chưa khai đủ"),
                "message": _(
                    "Vật tư “%(mat)s” còn thiếu: %(fields)s.\n"
                    "Định mức sẽ không tự tính được — hãy bổ sung ở màn Vật tư, "
                    "hoặc bật “Ghi đè số lượng” để nhập tay."
                ) % {"mat": self.material_id.display_name,
                     "fields": ", ".join(missing)},
            }}

    # ==========================================================
    # THU HỒI PHẾ LIỆU
    # ==========================================================

    # 🔴 NGƯNG SỬ DỤNG 2026-08-13 (K16) — người dùng chốt BỎ cách tính % thu hồi
    # phế liệu. Hai hàm dưới đây trả 0 thay vì bị xoá, và đó là CHỦ Ý:
    #
    #   • Chúng là ĐIỂM NGHẼN duy nhất — `dl_bom_line._compute_recovery_value`
    #     và engine giá (`quotation_pricing_service` §5.3) đều gọi qua đây. Tắt
    #     một chỗ là tắt toàn hệ thống, không phải đi sửa ba nơi rồi bỏ sót nơi
    #     thứ tư.
    #   • Field `dlm_has_recovery` / `dlm_recovery_rate` trên vật tư vẫn còn
    #     (chỉ gỡ khỏi UI): xoá cột là mất dữ liệu cấu hình không lấy lại được,
    #     mà quyết định kinh doanh thì có thể đảo.
    #
    # HỆ QUẢ VỀ TIỀN, nói thẳng: giá vốn vật tư nay KHÔNG còn được trừ tiền phế
    # liệu ⇒ giá vốn cao lên ⇒ giá chào khách cao lên (hoặc biên lợi nhuận giảm
    # nếu giữ giá). Đổi lại, tiền bán phế liệu thành lãi thật và không còn hai
    # con số "thu hồi" phải đối chiếu với nhau.
    def _dlm_recovery_kg(self):
        """0.0 — xem khối chú thích trên. Giữ chữ ký hàm cho nơi gọi cũ."""
        self.ensure_one()
        return 0.0

    def _dlm_recovery_value(self):
        """0.0 — xem khối chú thích trên. Giữ chữ ký hàm cho nơi gọi cũ."""
        self.ensure_one()
        return 0.0

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

    @api.constrains("piece_count")
    def _check_piece_count(self):
        for rec in self:
            if rec.piece_count is not None and rec.piece_count < 1:
                raise ValidationError(_("Số đoạn phải lớn hơn hoặc bằng 1."))
