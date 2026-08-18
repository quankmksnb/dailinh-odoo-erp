import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .rfq_provisional_utils import has_stored_many2one_reference


_logger = logging.getLogger(__name__)


class DlBom(models.Model):
    _name = "dl.bom"
    _description = "BOM"
    _inherit = ["mail.thread", "mail.activity.mixin", "dl.bom.header.mixin"]
    _order = "id desc"

    _sql_constraints = [
        (
            "product_version_type_uniq",
            "unique(product_id,version,bom_type)",
            "Phiên bản BOM của sản phẩm đã tồn tại.",
        ),
    ]

    is_rfq_provisional = fields.Boolean(
        string="Dữ liệu tạm từ RFQ",
        default=False,
        copy=False,
        index=True,
        tracking=True,
        help="BOM được tạo/copy trong workspace RFQ nhưng dòng RFQ chưa hoàn tất.",
    )
    rfq_source_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ nguồn",
        ondelete="set null",
        copy=False,
        index=True,
        tracking=True,
    )

    name = fields.Char(
        string="Mã BOM",
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    # Nhóm sản phẩm — CHỈ để lọc nhanh Sản phẩm bên dưới, không phải chủ sở
    # hữu BOM (BOM theo nhóm sản phẩm dùng model riêng dl.bom.template).
    category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm (lọc)",
        ondelete="set null",
        # SP trên BOM là manufactured (nhánh Thành phẩm) hoặc BTP (nhánh Vật
        # tư) — filter chỉ hiện nhóm 2 nhánh chuẩn, khỏi lẫn nhóm hệ thống.
        domain=[("dl_branch", "in", ("finished", "material"))],
    )

    # Data Model refactor: dl.product/dl.semi.product đã hợp nhất vào
    # product.product (phân biệt bằng product_kind). Trước đây tách 2 field
    # product_id (manufactured)/semi_product_id (material_processed) — gộp
    # lại thành 1 field duy nhất vì đều là product.product, domain bao cả 2.
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        tracking=True,
        ondelete="restrict",
        # Không cho dựng BOM cho SP đã Ngừng (obsolete); vẫn cho SP Nháp vì
        # luồng RFQ tạo SP gia công ở Nháp rồi mới lập BOM.
        domain="[('product_kind', 'in', ('manufactured', 'material_processed')),"
               " ('dlm_lifecycle_state', '!=', 'obsolete')]"
               " + ([('categ_id', '=', category_id)] if category_id else [])",
    )

    bom_type = fields.Selection(
        [
            ("template", "BOM mẫu"),
            ("quotation", "BOM báo giá"),
        ],
        string="Loại BOM",
        default="template",
        required=True,
        tracking=True,
    )

    # ── Đợt 4 — vết của một INSTANCE sinh từ mẫu tham số (thiết kế §7.4c) ─────
    # Chỉ có ý nghĩa với bom_type='quotation' sinh qua generate_instance. BOM
    # dựng tay để trống các field này.
    source_template_id = fields.Many2one(
        "dl.bom.template", string="Sinh từ mẫu",
        readonly=True, ondelete="restrict", copy=False)
    source_template_version = fields.Integer(
        string="Phiên bản mẫu", readonly=True, copy=False)
    param_values = fields.Json(
        string="Giá trị tham số", readonly=True, copy=False)
    # Chữ ký chuẩn hoá của bộ tham số ("C=750|D=1400|R=830") — xương sống của
    # đường A (khớp cấu hình cũ) và cơ chế catalog (§18.4). Có index để tra nhanh.
    param_signature = fields.Char(
        string="Chữ ký tham số", readonly=True, index=True, copy=False)
    has_deviation = fields.Boolean(
        string="Có sai khác so với mẫu", readonly=True, copy=False)
    deviation_note = fields.Text(string="Ghi chú sai khác", copy=False)

    # ── Hiển thị: `version` mang HAI nghĩa tuỳ bom_type ──────────────────────
    # BOM mẫu = trục THỜI GIAN ⇒ version là PHIÊN BẢN, bản mới thay bản cũ.
    # BOM báo giá = trục ĐƠN HÀNG ⇒ version chỉ là SỐ SÊ-RI của lần sinh, các
    # bản tồn tại SONG SONG. Hiện cùng một con số cho hai nghĩa khiến người đọc
    # tưởng bản #3 thay thế bản #2 (xem _should_set_current_version).
    version_label = fields.Char(
        string="Phiên bản / Lần sinh", compute="_compute_version_label")
    # Bộ tham số của instance, dạng đọc được: "C=750 · D=1200 · R=800".
    param_display = fields.Char(string="Tham số", compute="_compute_param_display")

    @api.depends("version", "bom_type")
    def _compute_version_label(self):
        for rec in self:
            rec.version_label = (
                _("Lần sinh #%s") % rec.version
                if rec.bom_type == "quotation"
                else _("Phiên bản %s") % rec.version)

    @api.depends("param_signature")
    def _compute_param_display(self):
        for rec in self:
            rec.param_display = (rec.param_signature or "").replace("|", " · ")

    @api.model
    def _dlm_param_signature(self, param_values):
        """Chữ ký chuẩn hoá của bộ tham số: khoá sắp alphabet, số làm tròn 1 chữ
        số thập phân, số nguyên bỏ '.0'. VD {"D":1400,"R":830} → "D=1400|R=830".
        Dùng để so khớp cấu hình đã sinh (đường A) và đếm lần lặp (catalog)."""
        parts = []
        for code in sorted((param_values or {}).keys()):
            try:
                value = round(float(param_values[code]), 1)
            except (TypeError, ValueError):
                continue
            if value == int(value):
                value = int(value)
            parts.append("%s=%s" % (code, value))
        return "|".join(parts)

    line_ids = fields.One2many(
        "dl.bom.line",
        "bom_id",
        string="Danh sách vật tư",
        # Odoo mặc định KHÔNG copy one2many khi duplicate record — bật lên để
        # "Tạo phiên bản mới"/"Copy BOM" (action_create_new_version → copy())
        # mang theo toàn bộ dòng vật tư sang version mới.
        copy=True,
    )

    total_material_cost = fields.Float(
        string="Tổng chi phí vật tư",
        compute="_compute_total_material_cost",
        store=True,
        digits="Product Price",
    )

    # ── Công đoạn của định mức (RV-01/RV-04, thiết kế công đoạn §2.2) ─────────
    # copy=True để "Tạo phiên bản mới BOM" mang theo công đoạn (giống line_ids).
    operation_line_ids = fields.One2many(
        "dl.bom.operation.line", "bom_id", string="Công đoạn", copy=True,
    )
    # Ước tính THAM KHẢO tổng chi phí công đoạn BIẾN ĐỔI/đơn vị (gated — Kỹ thuật
    # không thấy). Không phải giá chốt (giá chốt tính khi tạo báo giá, pha B2).
    total_operation_cost_est = fields.Float(
        string="Ước tính chi phí công đoạn/đơn vị",
        compute="_compute_total_operation_cost_est",
        digits="Product Price",
        groups="dl_base.dl_group_ceo,dl_base.dl_group_admin,"
               "dl_base.dl_group_sales_manager",
    )

    note = fields.Text(
        string="Ghi chú",
    )

    @api.depends("operation_line_ids.estimated_unit_cost")
    def _compute_total_operation_cost_est(self):
        for rec in self:
            rec.total_operation_cost_est = sum(
                rec.operation_line_ids.mapped("estimated_unit_cost"))

    # ── Smart-button: BTP này được dùng ở bao nhiêu định mức cha (§13.2) ──────
    # Chỉ có nghĩa khi SP của BOM là bán thành phẩm — chống "chuyển đi chuyển
    # lại": từ BOM của một BTP nhảy thẳng sang các định mức cha đang dùng nó.
    dlm_used_in_parent_count = fields.Integer(
        string="Được dùng ở N định mức",
        compute="_compute_used_in_parent_count")

    @api.depends("product_id")
    def _compute_used_in_parent_count(self):
        Line = self.env["dl.bom.line"].sudo()
        for rec in self:
            if rec.product_id and rec.product_id.product_kind == "material_processed":
                rec.dlm_used_in_parent_count = Line.search_count(
                    [("material_id", "=", rec.product_id.id)])
            else:
                rec.dlm_used_in_parent_count = 0

    # ── Bản vẽ kỹ thuật của sản phẩm ─────────────────────────────────────
    # Tra theo product_id để KTV vừa xem bản vẽ vừa nhập vật tư vào BOM ngay
    # trên cùng màn (cả màn tạo BOM sản phẩm lẫn wizard tạo BOM khi nhận RFQ).
    # Chỉ đọc, không đụng dữ liệu bản vẽ — ưu tiên bản vẽ đã xác nhận, mới nhất.
    drawing_id = fields.Many2one(
        "dl.drawing",
        string="Bản vẽ kỹ thuật",
        compute="_compute_drawing_ref",
    )
    drawing_attachment_id = fields.Many2one(
        "ir.attachment",
        string="File bản vẽ",
        compute="_compute_drawing_ref",
    )
    drawing_mimetype = fields.Char(compute="_compute_drawing_ref")
    drawing_filename = fields.Char(compute="_compute_drawing_ref")

    @api.depends("product_id")
    def _compute_drawing_ref(self):
        Drawing = self.env["dl.drawing"]
        for rec in self:
            drawing = Drawing.browse()
            if rec.product_id:
                domain = [
                    ("product_id", "=", rec.product_id.id),
                    ("attachment_id", "!=", False),
                ]
                # D4 — ưu tiên bản vẽ HIỆN HÀNH (is_current) tường minh; rồi mới
                # tới confirmed mới nhất; cuối cùng bản mới nhất bất kỳ.
                drawing = Drawing.search(
                    domain + [("is_current", "=", True)], limit=1,
                ) or Drawing.search(
                    domain + [("status", "=", "confirmed")],
                    order="version desc", limit=1,
                ) or Drawing.search(domain, order="version desc", limit=1)
            att = drawing.attachment_id
            rec.drawing_id = drawing
            rec.drawing_attachment_id = att
            rec.drawing_mimetype = att.mimetype if att else False
            rec.drawing_filename = att.name if att else False

    def action_view_drawing(self):
        """§4a — XEM trực tiếp file bản vẽ (mở PDF/ảnh trong tab mới), không mở
        form thêm bản vẽ. download=false để trình duyệt render xem tại chỗ."""
        self.ensure_one()
        if not self.drawing_attachment_id:
            raise UserError(_("Sản phẩm chưa có bản vẽ kỹ thuật."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=false" % self.drawing_attachment_id.id,
            "target": "new",
        }

    def action_upload_drawing(self):
        """§4b — tải lên bản vẽ ngay từ màn BOM (mở form Bản vẽ trong dialog, tự
        gắn Sản phẩm hiện tại). Dùng chung cho cả màn Tạo BOM & Nhận RFQ."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Vui lòng chọn Sản phẩm trước khi tải bản vẽ."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Tải lên bản vẽ"),
            "res_model": "dl.drawing",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_id": self.product_id.id,
                "default_name": self.product_id.display_name,
            },
        }

    @api.depends("line_ids.subtotal")
    def _compute_total_material_cost(self):
        for rec in self:
            rec.total_material_cost = sum(rec.line_ids.mapped("subtotal"))
        # LK-16 (P10) — Giá vốn của một BTP = total_material_cost của BOM con
        # (đọc trong dl.bom.line._compute_price_snapshot). ORM KHÔNG cho khai
        # @api.depends theo kết quả search, nên khi tổng chi phí BOM con đổi thì
        # snapshot ở các dòng BOM CHA không tự lan. Vá bằng recompute chủ động.
        self._dlm_propagate_cost_to_parents()

    # 🔴 K16 — `_dlm_recovery_kg_per_unit` ĐÃ GỠ cùng màn Đối chiếu thu hồi
    # (dl_inventory), nơi duy nhất gọi nó. Xem chú thích ở
    # `dl_bom_line_mixin._dlm_recovery_kg` để biết vì sao cả nhánh thu hồi dừng.

    @api.model
    def _standard_child_bom(self, product):
        """BOM dùng làm GIÁ VỐN CHUẨN của một SP/BTP — NGUỒN DUY NHẤT (§12.2-A).

        Thứ tự (thiết kế §17.2 — cả pricing engine lẫn snapshot dòng BOM đều gọi
        hàm này để hai đường tính giá vốn KHÔNG bao giờ lệch nhau):
        1. BOM chuẩn (bom_type='template') đang là phiên bản hiện hành;
        2. BOM chuẩn mới nhất còn hiệu lực (confirmed/locked);
        3. chỉ khi SP CHƯA TỪNG có BOM chuẩn mới đành rơi về BOM báo giá mới
           nhất (dữ liệu chưa hoàn chỉnh).
        """
        if not product:
            return self.browse()
        base = [
            ("product_id", "=", product.id),
            ("status", "in", ("confirmed", "locked")),
        ]
        standard = [("bom_type", "=", "template")]
        return (
            self.search(base + standard + [("is_current", "=", True)], limit=1)
            or self.search(base + standard, order="version desc", limit=1)
            or self.search(base, order="version desc", limit=1)
        )

    def _dlm_propagate_cost_to_parents(self):
        """Lan chi phí BTP đổi lên các dòng BOM cha đang dùng nó (LK-16).

        Chỉ recompute ``price_snapshot`` của dòng cha; chuỗi phụ thuộc ORM tự
        cascade tiếp: price_snapshot → subtotal → total_material_cost (BOM cha)
        → lại gọi hàm này (nếu tổng thật sự đổi). TỰ DỪNG khi giá trị không đổi
        (Odoo bỏ qua ghi computed no-op nên không kích recompute vô ích). Cascade
        nhiều tầng (BTP lồng BTP) hữu hạn nhờ lá chắn vòng lặp LK-01 (đồ thị BOM
        là DAG)."""
        products = self.mapped("product_id").filtered(
            lambda p: p.product_kind == "material_processed")
        if not products:
            return
        parent_lines = self.env["dl.bom.line"].sudo().search(
            [("material_id", "in", products.ids)])
        if parent_lines:
            parent_lines._compute_price_snapshot()

    @api.constrains("product_qty")
    def _check_product_qty(self):
        for rec in self:
            if rec.product_qty <= 0:
                raise ValidationError(_("Số lượng đầu ra phải lớn hơn 0."))

    @api.constrains("product_id")
    def _check_product_not_obsolete(self):
        """Chặn cứng lập BOM cho SP đã Ngừng (song song domain UI, bịt import/API).
        Chỉ khai theo product_id ⇒ chỉ chạy khi tạo BOM mới hoặc đổi SP; BOM cũ
        có SP sau này bị Ngừng không bị chặn khi sửa việc khác."""
        for rec in self:
            if rec.product_id.dlm_lifecycle_state == "obsolete":
                raise ValidationError(_(
                    "Sản phẩm '%s' đã Ngừng sử dụng — không thể lập BOM mới cho "
                    "sản phẩm này."
                ) % rec.product_id.display_name)

    @api.model_create_multi
    def create(self, vals_list):
        # Cache version đã bị chiếm theo (product_id, bom_type) — tính từ DB một
        # lần, cộng dồn các bản vừa cấp trong cùng batch để không tự đụng nhau.
        taken_by_key = {}
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("dl.bom") or _("New")

            # Tự dời version về số TRỐNG kế tiếp thay vì để SQL constraint
            # unique(product_id, version, bom_type) nổ lỗi khó hiểu "Phiên bản BOM
            # của sản phẩm đã tồn tại". Onchange ở UI tính version có thể LỠ (mở
            # form với sản phẩm set sẵn, reload, tạo nhiều BOM liên tiếp...) nên
            # đây là lá chắn cuối cùng, đảm bảo lưu luôn thành công với số kế tiếp.
            product_id = vals.get("product_id")
            if product_id:
                bom_type = vals.get("bom_type", "template")
                key = (product_id, bom_type)
                if key not in taken_by_key:
                    existing = self.search([
                        ("product_id", "=", product_id),
                        ("bom_type", "=", bom_type),
                    ])
                    taken_by_key[key] = set(existing.mapped("version"))
                version = vals.get("version") or 1
                while version in taken_by_key[key]:
                    version += 1
                vals["version"] = version
                taken_by_key[key].add(version)
        return super().create(vals_list)

    def _version_domain(self):
        self.ensure_one()
        return [("bom_type", "=", self.bom_type), ("product_id", "=", self.product_id.id)]

    def _should_set_current_version(self):
        """BOM báo giá KHÔNG BAO GIỜ là "phiên bản hiện hành" của sản phẩm.

        Ba trục khác nhau (thiết kế §3 — Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md):
        - version  = trục THỜI GIAN: cách làm thay đổi, bản mới THAY THẾ bản cũ;
        - variant  = trục THUỘC TÍNH: các cấu hình bán song song;
        - instance = trục ĐƠN HÀNG: định mức sinh cho một đơn cụ thể.

        BOM `bom_type='quotation'` là INSTANCE — nó tồn tại song song với các
        instance khác (bàn 1200x800 và bàn 1400x830 cùng đặt được), nên không
        được tham gia cuộc đua `is_current`. Trước đây nó thắng cuộc đua đó và
        một đơn lẻ ghi đè "định mức chuẩn" của sản phẩm.

        `is_current` chỉ thuộc về BOM chuẩn (`bom_type='template'`) — xem I7/I9.
        Số `version` của BOM báo giá vẫn tăng, nhưng đó là SỐ SÊ-RI (lần sinh),
        không phải phiên bản: đánh số vẫn dùng `_version_domain()` như cũ để giữ
        nguyên SQL constraint unique(product_id, version, bom_type).
        """
        self.ensure_one()
        return self.bom_type != "quotation" and not self.is_rfq_provisional

    def _dlm_unpriced_raw_materials(self):
        """Vật tư THÔ trong định mức chưa có giá NCC đã duyệt & đang áp dụng (EX-13).

        Trả về recordset ``product.product`` (vật tư thô, product_kind='material')
        mà KHÔNG có supplierinfo nào vừa 'đang áp dụng' vừa 'đã duyệt'. Bán thành
        phẩm (material_processed) không tính vì giá vốn của nó suy từ BOM con, không
        phải từ giá NCC — khớp đúng cách pricing engine tính (QTE-003 chỉ áp cho
        vật tư thô).

        Dùng ``sudo`` để đọc được supplierinfo (Kỹ thuật thường không có quyền) —
        nhưng NƠI GỌI chỉ được lộ TÊN vật tư/số lượng, KHÔNG lộ giá (RBAC §15.4).
        """
        Product = self.env["product.product"]
        missing = Product.browse()
        for bom in self:
            for line in bom.line_ids:
                material = line.material_id
                if not material or material.product_kind != "material":
                    continue
                # Nguồn duy nhất: dlm_supplier_price_state (stored) — 'applied' ⟺
                # có bảng giá NCC đã duyệt & đang áp dụng (is_applied kéo theo
                # approved qua constraint). Dùng field này để đồng nhất với màn
                # "Vật tư chờ định giá" phía Mua hàng, tránh 2 định nghĩa lệch nhau.
                if material.dlm_supplier_price_state != "applied":
                    missing |= material
        return missing

    def _dlm_unpriced_components(self):
        """LK-09/LK-10 — Cấu phần khiến định mức tính THIẾU giá vốn:
        • vật tư thô chưa có giá NCC đã duyệt & đang áp dụng (mở rộng
          _dlm_unpriced_raw_materials); VÀ
        • bán thành phẩm chưa có BOM CHUẨN confirmed (giá vốn = 0 âm thầm, §3.3-D).

        Trả recordset product.product. NƠI GỌI chỉ lộ TÊN cấu phần, KHÔNG lộ giá
        (RBAC §15.4 — _COST_GROUPS)."""
        missing = self._dlm_unpriced_raw_materials()
        Bom = self.env["dl.bom"].sudo()
        for bom in self:
            for line in bom.line_ids:
                comp = line.material_id
                if not comp or comp.product_kind != "material_processed":
                    continue
                std = Bom._standard_child_bom(comp)
                if not std or std.status not in ("confirmed", "locked"):
                    missing |= comp
        return missing

    dlm_has_unpriced_component = fields.Boolean(
        string="Có cấu phần chưa định giá",
        compute="_compute_dlm_unpriced_component")
    dlm_unpriced_component_names = fields.Char(
        string="Cấu phần chưa định giá",
        compute="_compute_dlm_unpriced_component")

    @api.depends("line_ids.material_id",
                 "line_ids.material_id.dlm_supplier_price_state")
    def _compute_dlm_unpriced_component(self):
        for rec in self:
            missing = rec._dlm_unpriced_components()
            rec.dlm_has_unpriced_component = bool(missing)
            rec.dlm_unpriced_component_names = ", ".join(
                missing.mapped("display_name")) if missing else False

    # --- Công đoạn chưa định giá (review §4.3) ---------------------------------
    # Cảnh báo SỚM: công đoạn trên BOM chưa có dl.pricing.operation.rule đang áp
    # dụng ⇒ tạo báo giá sẽ văng QTE-011 tận cuối luồng. Đưa tín hiệu lên ngay
    # form BOM (đối xứng banner "thiếu giá vốn" của vật tư) để KTV thấy trước khi
    # Xác nhận/Khóa. KHÔNG chặn cứng (chặn vẫn ở bước tạo báo giá); chỉ lộ TÊN
    # công đoạn — không phải giá.
    dlm_has_unpriced_operation = fields.Boolean(
        string="Có công đoạn chưa định giá",
        compute="_compute_dlm_unpriced_operation")
    dlm_unpriced_operation_names = fields.Char(
        string="Công đoạn chưa định giá",
        compute="_compute_dlm_unpriced_operation")

    @api.depends("operation_line_ids.operation_id",
                 "operation_line_ids.has_active_rule")
    def _compute_dlm_unpriced_operation(self):
        for rec in self:
            missing = rec.operation_line_ids.filtered(
                lambda l: l.operation_id and not l.has_active_rule)
            names = sorted(set(missing.mapped("operation_id.display_name")))
            rec.dlm_has_unpriced_operation = bool(names)
            rec.dlm_unpriced_operation_names = ", ".join(names) if names else False

    def action_notify_purchasing_unpriced(self):
        """LK-09 — nút "Báo Mua hàng cập nhật giá" trên banner form BOM: giao
        việc cập nhật giá NCC cho các VẬT TƯ THÔ chưa có giá (BTP thiếu BOM thì
        KTV tự lập định mức, không phải việc của Mua hàng). Dùng chung khuôn báo
        Mua hàng của workspace RFQ (chống trùng việc đang mở)."""
        self.ensure_one()
        missing = self._dlm_unpriced_raw_materials()
        if not missing:
            return True
        purchasing = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        users = purchasing.users if purchasing else self.env["res.users"]
        todo_type = self.env.ref("mail.mail_activity_data_todo")
        Activity = self.env["mail.activity"].sudo()
        for material in missing:
            material.sudo().message_post(body=_(
                "Kỹ thuật (định mức %s) cần Mua hàng cập nhật giá nhà cung cấp (đã duyệt "
                "&amp; đang áp dụng) cho vật tư này.") % self.display_name)
            for user in users:
                if Activity.search_count([
                        ("res_model", "=", "product.product"),
                        ("res_id", "=", material.id),
                        ("user_id", "=", user.id),
                        ("activity_type_id", "=", todo_type.id)]):
                    continue
                material.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Cập nhật giá nhà cung cấp — %s") % material.display_name,
                    note=_("Yêu cầu từ Kỹ thuật khi lập định mức %s.")
                    % self.display_name,
                    user_id=user.id)
        return True

    def _dlm_check_drawing_policy(self):
        """LK-06 (§3.2-D1) — cổng bản vẽ theo CHÍNH SÁCH cấu hình
        (ir.config_parameter dl_technical.require_drawing_for_finished). Mặc định
        'warn' (không chặn); khi 'block': SP nhánh Thành phẩm (manufactured) phải
        có ≥1 bản vẽ đã xác nhận trước khi xác nhận BOM. BTP/ca đơn giản không áp
        (nhiều đơn nhỏ không cần bản vẽ CAD)."""
        policy = self.env["ir.config_parameter"].sudo().get_param(
            "dl_technical.require_drawing_for_finished", "warn")
        if policy != "block":
            return
        Drawing = self.env["dl.drawing"].sudo()
        for rec in self:
            if rec.product_id.product_kind != "manufactured":
                continue
            has = Drawing.search_count([
                ("product_id", "=", rec.product_id.id),
                ("status", "=", "confirmed"),
                ("attachment_id", "!=", False),
            ])
            if not has:
                raise UserError(_(
                    "Chính sách xưởng yêu cầu sản phẩm thành phẩm phải có bản vẽ "
                    "đã xác nhận trước khi xác nhận BOM. Hãy dùng nút “Tải lên bản "
                    "vẽ” trên form BOM để thêm bản vẽ cho “%s”."
                ) % rec.product_id.display_name)

    def _dlm_check_material_spec(self):
        """§12.4 — CỔNG CỨNG: vật tư khai thiếu quy cách thì định mức không tự
        tính được, dòng BOM âm thầm giữ số mặc định (1) ⇒ giá vốn sai mà không
        có tín hiệu nào. Chặn ngay lúc xác nhận và nêu đúng vật tư thiếu gì.

        Dòng đã bật Ghi đè số lượng không cần tự tính (kỹ thuật gõ thẳng số cây)
        nên chỉ còn bị soi phần khối lượng phục vụ tiền phế liệu."""
        for rec in self:
            problems = []
            for line in rec.line_ids:
                missing = line.material_id._dlm_calc_missing_fields(
                    for_auto_calc=not line.is_override)
                if missing:
                    problems.append("• %s — thiếu: %s" % (
                        line.material_id.display_name, ", ".join(missing)))
            if problems:
                raise UserError(_(
                    "Chưa xác nhận được “%(bom)s”: những vật tư sau chưa khai đủ "
                    "quy cách nên định mức không tự tính được.\n\n%(list)s\n\n"
                    "Bổ sung ở màn Vật tư — mục “Quy cách & cách tính định mức”."
                ) % {"bom": rec.display_name,
                     "list": "\n".join(dict.fromkeys(problems))})

    def action_confirm(self):
        self._dlm_check_drawing_policy()      # LK-06 — cổng bản vẽ (nếu bật)
        self._dlm_check_material_spec()       # §12.4 — cổng quy cách vật tư
        result = super().action_confirm()
        # LK-16 — Xác nhận một BOM (nhất là BOM chuẩn của BTP) đổi kết quả
        # _standard_child_bom ⇒ các dòng BOM cha đang dùng BTP này phải tính lại
        # snapshot (trước đây có thể đang rơi về báo giá hoặc = 0).
        self._dlm_propagate_cost_to_parents()
        return result

    def action_lock(self):
        if self.filtered("is_rfq_provisional"):
            raise UserError(_(
                "BOM tạm từ RFQ chưa thể khóa. Hãy quay lại workspace và bấm "
                "'Hoàn tất dòng' trước."))
        return super().action_lock()

    def action_archive(self):
        if self.filtered("is_rfq_provisional"):
            raise UserError(_(
                "Không thể lưu trữ BOM tạm từ RFQ. Hãy hoàn tất hoặc bỏ phương án "
                "trên dòng RFQ nguồn."))
        result = super().action_archive()
        # LK-16 — Lưu trữ BOM chuẩn của BTP loại nó khỏi _standard_child_bom ⇒
        # giá vốn BTP ở các dòng cha có thể đổi (rơi về bản khác/0).
        self._dlm_propagate_cost_to_parents()
        return result

    def _set_current_version(self):
        result = super()._set_current_version()
        # LK-16 — Đổi phiên bản hiện hành của BOM chuẩn BTP ⇒ _standard_child_bom
        # ưu tiên bản is_current nên giá vốn ở dòng cha có thể đổi theo.
        self._dlm_propagate_cost_to_parents()
        return result

    def action_create_new_version(self):
        self.ensure_one()
        result = super().action_create_new_version()
        if self.is_rfq_provisional:
            self.browse(result["res_id"]).write({
                "is_rfq_provisional": True,
                "rfq_source_line_id": self.rfq_source_line_id.id,
            })
        return result

    def _cleanup_unused_rfq_provisional(self):
        """Delete unused RFQ BOMs without touching locked/current/history data."""
        deleted = 0
        ignored = {("dl.bom.line", "bom_id")}
        for bom in self.sudo().exists():
            if (not bom.is_rfq_provisional
                    or bom.status not in ("draft", "confirmed")
                    or bom.is_current):
                continue
            if has_stored_many2one_reference(bom, ignored=ignored):
                continue
            try:
                with self.env.cr.savepoint():
                    bom.unlink()
                deleted += 1
            except Exception:
                _logger.exception(
                    "Không thể dọn BOM tạm RFQ %s; giữ lại để an toàn.", bom.id)
        return deleted

    @api.onchange("product_id", "bom_type")
    def _onchange_product_version(self):
        if self.product_id:
            self.version = self._compute_next_version()

    def action_open_form(self):
        """Mở BOM trên trang đầy đủ.

        Khi gọi từ workspace RFQ, web client tự giữ workspace trong breadcrumb;
        không cần context dò ngược hay nút quay lại riêng trên form BOM.
        """
        self.ensure_one()
        view = self.env.ref("dl_technical.view_dl_bom_form")
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "dl.bom",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }

    def action_open_create_btp_wizard(self):
        """§13.2 — nút [+ Bán thành phẩm] trên định mức: mở wizard tạo BTP + BOM
        con + gắn vào dòng (thay 3 bước rời rạc bằng một mạch, §3.3-A)."""
        self.ensure_one()
        if self.status != "draft":
            raise UserError(_(
                "Chỉ thêm bán thành phẩm khi định mức còn ở trạng thái Nháp."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Thêm bán thành phẩm"),
            "res_model": "dl.bom.create.btp.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bom_id": self.id},
        }

    def action_open_used_in_parents(self):
        """Smart-button "Được dùng ở N định mức": mở list các BOM cha đang dùng
        BTP này (dòng có material_id = product_id của BOM này)."""
        self.ensure_one()
        parent_bom_ids = self.env["dl.bom.line"].sudo().search(
            [("material_id", "=", self.product_id.id)]).mapped("bom_id").ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Định mức dùng %s") % self.product_id.display_name,
            "res_model": "dl.bom",
            "view_mode": "tree,form",
            "domain": [("id", "in", parent_bom_ids)],
            "target": "current",
        }

    def action_create_from_template(self):
        """Product BOM — nút "Create From BOM Template": mở wizard chọn 1
        BOM mẫu (dl.bom.template) rồi copy toàn bộ dòng sang BOM này."""
        self.ensure_one()
        if self.status != "draft":
            raise UserError(_("Chỉ BOM ở trạng thái Nháp mới copy được từ BOM mẫu."))
        category = self.product_id.categ_id
        if not category:
            raise UserError(_(
                'Sản phẩm "%s" chưa được gán Nhóm sản phẩm — hãy gán nhóm cho '
                'sản phẩm trước khi tạo BOM từ BOM mẫu.'
            ) % self.product_id.display_name)
        # LK-03/CAT-05 — chỉ tính mẫu ĐÃ DUYỆT (confirmed/locked); nhóm chỉ có
        # mẫu Nháp coi như CHƯA có mẫu để chép.
        has_template = self.env["dl.bom.template"].search(
            [
                ("product_category_id", "=", category.id),
                ("status", "in", ("confirmed", "locked")),
            ],
            limit=1,
        )
        if not has_template:
            raise UserError(_(
                'Nhóm sản phẩm "%s" chưa có BOM mẫu đã duyệt nào. Hãy tạo & xác '
                'nhận BOM mẫu cho nhóm này trước (menu BOM mẫu), hoặc nhập dòng '
                'vật tư trực tiếp vào BOM.'
            ) % category.display_name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Tạo từ BOM mẫu"),
            "res_model": "dl.bom.from.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bom_id": self.id},
        }

    def action_create_bom_template(self):
        """Chiều ngược của "Create From BOM Template": lấy chính BOM này làm
        BOM mẫu cho NHÓM sản phẩm mà sản phẩm của BOM đang thuộc về. Điều kiện:
        sản phẩm đã được gán 1 nhóm sản phẩm (categ_id). Copy toàn bộ dòng vật
        tư sang 1 BOM mẫu mới (nháp) để Kỹ thuật rà soát/điều chỉnh."""
        self.ensure_one()
        if self.is_rfq_provisional:
            raise UserError(_(
                "BOM này vẫn là dữ liệu tạm của RFQ. Hãy hoàn tất dòng RFQ trước "
                "khi dùng nó để tạo BOM mẫu."))
        category = self.product_id.categ_id
        if not category:
            raise UserError(_(
                'Sản phẩm "%s" chưa được gán Nhóm sản phẩm — hãy gán nhóm cho '
                'sản phẩm trước khi lấy BOM này làm BOM mẫu cho nhóm.'
            ) % self.product_id.display_name)
        if not self.line_ids:
            raise UserError(_("BOM này chưa có dòng vật tư nào để tạo BOM mẫu."))

        Template = self.env["dl.bom.template"]
        existing = Template.search([("product_category_id", "=", category.id)])
        version = (max(existing.mapped("version")) + 1) if existing else 1

        template = Template.create({
            "name": _("BOM mẫu - %s (từ %s)") % (category.name, self.name),
            "product_category_id": category.id,
            "product_qty": self.product_qty,
            "version": version,
            "status": "draft",
            "line_ids": [(0, 0, line._mixin_copy_vals()) for line in self.line_ids],
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("BOM mẫu"),
            "res_model": "dl.bom.template",
            "res_id": template.id,
            "view_mode": "form",
            "target": "current",
        }
