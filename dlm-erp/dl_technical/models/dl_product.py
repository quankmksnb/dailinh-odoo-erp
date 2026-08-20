import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .rfq_provisional_utils import has_stored_many2one_reference


_logger = logging.getLogger(__name__)

BOM_ELIGIBLE_KINDS = ("manufactured", "material_processed")


class ProductCategoryTechnical(models.Model):
    _inherit = "product.category"

    # PROD-01: FK category → BOM mẫu (TECH-04). Khai ở dl_technical (layer trên)
    # vì dl_product không depends dl_technical. Thay field cũ template_bom_id→dl.bom.
    bom_template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu mặc định",
        ondelete="set null",
    )

    @api.constrains("bom_template_id")
    def _dlm_check_bom_template_id(self):
        """LK-04 (§3.1-L2) — mẫu mặc định của nhóm không được trỏ bậy: phải CÙNG
        NHÓM và ĐÃ DUYỆT (confirmed/locked). Giữ field nhập tay (cho override)
        nhưng chặn trỏ bản Nháp/Archived/khác nhóm để hết lệch phiên bản."""
        for rec in self:
            tmpl = rec.bom_template_id
            if not tmpl:
                continue
            if tmpl.product_category_id != rec:
                raise ValidationError(_(
                    "BOM mẫu mặc định “%s” không thuộc nhóm “%s”."
                ) % (tmpl.name, rec.display_name))
            if tmpl.status not in ("confirmed", "locked"):
                raise ValidationError(_(
                    "BOM mẫu mặc định “%s” chưa được duyệt — chỉ chọn mẫu đã "
                    "Xác nhận/Khóa làm mẫu mặc định của nhóm."
                ) % tmpl.name)

    def _dlm_parametric_generic_ids(self):
        """Các SẢN PHẨM DÙNG CHUNG có mẫu tham số đã duyệt trong nhóm này (và con).

        Từ 2026-08-19 mẫu tham số neo theo SẢN PHẨM, không theo nhóm — một nhóm
        thương mại chứa được nhiều kết cấu, mỗi kết cấu một mẫu. Nhóm vì thế
        không còn trả về "một mẫu" nữa; nó chỉ trả về TẬP các kiểu hàng cho
        Sales chọn. Hàm cũ `_dlm_parametric_template()` đã bỏ vì câu hỏi
        "mẫu của nhóm này là mẫu nào" nay không có câu trả lời đơn nhất."""
        self.ensure_one()
        if not self.id:
            return self.env["product.product"]
        templates = self.env["dl.bom.template"].search([
            ("status", "in", ("confirmed", "locked")),
            ("is_parametric", "=", True),
            ("generic_product_id", "!=", False),
            ("generic_product_id.categ_id", "child_of", self.id),
        ])
        return templates.mapped("generic_product_id")


class DlProductTechnical(models.Model):
    # Data Model refactor: dl.product = product.product (mở rộng thuần).
    _inherit = "product.product"

    is_rfq_provisional = fields.Boolean(
        string="Dữ liệu tạm từ RFQ",
        default=False,
        copy=False,
        index=True,
        tracking=True,
        help="Sản phẩm được tạo trong workspace RFQ nhưng dòng RFQ chưa hoàn tất.",
    )
    rfq_source_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ nguồn",
        ondelete="set null",
        copy=False,
        index=True,
        tracking=True,
    )

    # ── S05 · Thuộc tính kỹ thuật (Đợt 2, §3.6) ─────────────────────────────
    # Điều kiện tiên quyết của bộ dò khớp: có D/R/C + vật liệu + độ dày + lớp
    # hoàn thiện thì engine gợi ý SP so được SỐ VỚI SỐ (thay vì chỉ so tên/nhóm),
    # tái sử dụng BOM/báo giá cũ đúng như S05 đặc tả. Chỉ có nghĩa với SP gia
    # công / bán thành phẩm (BOM-eligible) — SP thương mại/vật tư bỏ trống.
    dlm_dim_length = fields.Float(string="Dài (mm)")
    dlm_dim_width = fields.Float(string="Rộng (mm)")
    dlm_dim_height = fields.Float(string="Cao (mm)")
    dlm_thickness = fields.Float(string="Độ dày (mm)")
    dlm_main_material_id = fields.Many2one(
        "product.product",
        string="Vật liệu chính",
        domain=[("product_kind", "=", "material")],
        ondelete="restrict",
    )
    dlm_finish = fields.Selection(
        [
            ("powder", "Sơn tĩnh điện"),
            ("galv", "Mạ kẽm"),
            ("raw", "Để nguyên"),
        ],
        string="Lớp hoàn thiện",
    )
    dlm_est_weight = fields.Float(string="Khối lượng ước tính (kg)")

    bom_ids = fields.One2many(
        "dl.bom",
        "product_id",
        string="Danh sách BOM",
        compute="_compute_bom_ids",
    )
    # Tách hai TRỤC khác nhau để người đọc không tưởng chúng cùng một dòng dõi:
    # định mức chuẩn nối tiếp nhau theo thời gian (một bản hiện hành), định mức
    # theo đơn tồn tại song song (mỗi cấu hình một bản).
    standard_bom_ids = fields.One2many(
        "dl.bom", "product_id", string="Định mức chuẩn",
        compute="_compute_bom_ids")
    instance_bom_ids = fields.One2many(
        "dl.bom", "product_id", string="Định mức theo đơn",
        compute="_compute_bom_ids")

    @api.depends("product_kind")
    def _compute_bom_ids(self):
        # SP thương mại / vật tư thô không bao giờ có BOM — bỏ qua tìm kiếm
        # trên dl.bom để các role không có quyền dl.bom (VD: Kế toán) không
        # bị chặn quyền truy cập khi mở SP thương mại/vật tư.
        eligible = self.filtered(lambda p: p.product_kind in BOM_ELIGIBLE_KINDS)
        boms = (
            self.env["dl.bom"].search([("product_id", "in", eligible.ids)])
            if eligible
            else self.env["dl.bom"]
        )
        for product in self:
            visible = boms.filtered(
                lambda b: b.product_id.id == product.id
                and (not b.is_rfq_provisional
                     or (product.is_rfq_provisional
                         and b.rfq_source_line_id == product.rfq_source_line_id)))
            product.bom_ids = visible
            product.standard_bom_ids = visible.filtered(
                lambda b: b.bom_type == "template")
            product.instance_bom_ids = visible.filtered(
                lambda b: b.bom_type == "quotation")

    def _dlm_parametric_template(self):
        """Mẫu tham số đã duyệt của CHÍNH sản phẩm này (bản hiện hành).

        Nguồn DUY NHẤT cho ba chỗ phải trả lời giống nhau: bảng thông số ở form
        Sales, bộ dò khớp, và workspace Kỹ thuật. Neo theo sản phẩm nên câu trả
        lời là đơn nhất (index bộ phận `unique(generic_product_id, version)`)."""
        self.ensure_one()
        if not self.id:
            return self.env["dl.bom.template"]
        return self.env["dl.bom.template"].search([
            ("generic_product_id", "=", self.id),
            ("status", "in", ("confirmed", "locked")),
            ("is_parametric", "=", True),
        ], order="is_current desc, version desc", limit=1)

    def _dlm_standard_bom(self):
        """Định mức CHUẨN hiện hành của sản phẩm (Hạng B — hàng cỡ cố định).

        Có bản này nghĩa là món đã thành mặt hàng catalog: Sales chọn xong là
        báo giá được ngay, không cần qua Kỹ thuật (làn L0-a)."""
        self.ensure_one()
        if not self.id:
            return self.env["dl.bom"]
        return self.env["dl.bom"].search([
            ("product_id", "=", self.id),
            ("bom_type", "=", "template"),
            ("is_current", "=", True),
            ("status", "in", ("confirmed", "locked")),
        ], limit=1)

    @api.depends_context("dlm_show_bom_kind")
    def _compute_display_name(self):
        """Thêm đuôi "· theo kích thước / · cỡ cố định" khi context bật cờ.

        Chỉ dùng ở ô "Kiểu hàng" của form Sales: hai loại kiểu hàng dẫn tới hai
        hành vi khác hẳn nhau (một cái hỏi kích thước rồi sinh định mức, một
        cái vào thẳng làn tự chốt), nên Sales phải phân biệt được NGAY TRONG
        danh sách chứ không phải chọn xong mới biết.

        Bật bằng context để không đụng mọi chỗ khác đang hiện tên sản phẩm."""
        super()._compute_display_name()
        if not self.env.context.get("dlm_show_bom_kind"):
            return
        for rec in self:
            if rec.product_kind != "manufactured":
                continue
            if rec._dlm_parametric_template():
                rec.display_name = "%s · %s" % (
                    rec.display_name, _("theo kích thước"))
            elif rec._dlm_standard_bom():
                rec.display_name = "%s · %s" % (
                    rec.display_name, _("cỡ cố định"))

    def _dlm_is_parametric_generic(self):
        """SP này có phải SẢN PHẨM DÙNG CHUNG của một mẫu tham số không?

        Hai hệ quả, đều là "đừng tự quyết hộ" ở workspace xử lý RFQ:
          • KHÔNG tự gán làm sản phẩm của dòng — điểm nó nhận là điểm "thuộc họ",
            tức tín hiệu về HỌ chứ không phải về món cụ thể; mọi cỡ trong họ đều
            khớp như nhau.
          • KHÔNG tự chọn định mức — định mức của nó là INSTANCE, mỗi bản một cỡ
            và tồn tại SONG SONG, nên không bản nào là "mặc định".
        """
        self.ensure_one()
        return bool(self.env["dl.bom.template"].search_count([
            ("generic_product_id", "=", self.id),
            ("is_parametric", "=", True),
            ("status", "in", ("confirmed", "locked")),
        ]))

    @api.constrains("name", "product_kind", "is_rfq_provisional")
    def _check_dlm_name_duplicate(self):
        """Chặn cứng SP gia công/BTP TRÙNG HỆT tên (đã chuẩn hoá) với SP chính
        thức đã có — bảo vệ MỌI đường tạo (form SP, RPC, import), không chỉ
        wizard RFQ. SP tạm từ RFQ (is_rfq_provisional) xử lý mềm ở wizard nên
        bỏ qua khi CÒN tạm; khi chính thức hóa (cờ tạm tắt) mới soi lại để chặn
        hai dòng RFQ cùng chốt một tên trùng. Bỏ qua khi context
        'dl_skip_name_dup_check' (seed/migration)."""
        if self.env.context.get("dl_skip_name_dup_check"):
            return
        for rec in self:
            if rec.product_kind not in BOM_ELIGIBLE_KINDS or not rec.name:
                continue
            if rec.is_rfq_provisional:
                continue
            matches = rec._dlm_find_name_matches(
                rec.name, kinds=BOM_ELIGIBLE_KINDS, exclude_ids=rec.ids,
                extra_domain=[("is_rfq_provisional", "=", False)])
            if matches["exact"]:
                dup = matches["exact"][0]
                raise ValidationError(_(
                    "Đã tồn tại sản phẩm cùng tên “%(name)s” (nhóm %(categ)s). "
                    "Hãy dùng lại sản phẩm đó thay vì tạo bản trùng.",
                    name=dup.display_name,
                    categ=dup.categ_id.display_name or _("chưa phân nhóm")))

    def action_lifecycle_activate(self):
        provisional = self.filtered("is_rfq_provisional")
        if provisional:
            raise UserError(_(
                "Sản phẩm tạm từ RFQ chỉ được chính thức hóa khi Kỹ thuật bấm "
                "'Hoàn tất dòng' trong workspace RFQ."))
        return super().action_lifecycle_activate()

    def _cleanup_unused_rfq_provisional(self):
        """Delete only unused RFQ-created draft products; fail closed on doubt."""
        deleted = 0
        for product in self.sudo().with_context(active_test=False).exists():
            if (not product.is_rfq_provisional
                    or product.dlm_lifecycle_state != "draft"):
                continue
            if has_stored_many2one_reference(product):
                continue
            try:
                with self.env.cr.savepoint():
                    product.unlink()
                deleted += 1
            except Exception:
                _logger.exception(
                    "Không thể dọn sản phẩm tạm RFQ %s; giữ lại để an toàn.",
                    product.id,
                )
        return deleted

    # ── Hao hụt: tự điền mặc định theo nhóm (field ở dl_product; logic đọc
    # dl.pricing.waste.rule phải ở đây vì dl_technical mới depends dl_config) ──
    @api.onchange("categ_id", "product_kind")
    def _onchange_dlm_waste_default(self):
        """Khi chọn nhóm cho vật tư mà chưa nhập hao hụt: điền mặc định từ quy
        tắc hao hụt theo NHÓM đang áp dụng (dl.pricing.waste.rule)."""
        if self.product_kind not in ("material", "material_processed"):
            return
        if self.dlm_waste_rate:
            return
        rule = self._dlm_category_waste_rule()
        if rule:
            self.dlm_waste_rate = rule.waste_rate
            # K16 — không chép `has_recovery`/`recovery_rate` nữa (đã ngưng dùng,
            # xem dl_bom_line_mixin._dlm_recovery_kg). `scrap_product_id` thì vẫn
            # chép: "vật tư này thải ra loại phế nào" là câu hỏi còn sống.
            self.dlm_scrap_product_id = rule.scrap_product_id

    def _dlm_category_waste_rule(self):
        self.ensure_one()
        if not self.categ_id:
            return self.env["dl.pricing.waste.rule"].browse()
        return self.env["dl.pricing.waste.rule"].sudo().search([
            ("state", "=", "active"),
            ("target_type", "=", "category"),
            ("category_id", "=", self.categ_id.id),
        ], order="valid_from desc, revision desc", limit=1)

    def action_create_bom(self):
        # bom_ids là computed field (chỉ đọc) — nút này mở form dl.bom mới,
        # tự set product_id theo sản phẩm đang xem (dl.bom.product_id đã gộp
        # chung cho cả manufactured lẫn material_processed).
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tạo BOM",
            "res_model": "dl.bom",
            "view_mode": "form",
            "view_id": self.env.ref("dl_technical.view_dl_bom_form").id,
            "target": "current",
            "context": {"default_bom_type": "quotation", "default_product_id": self.id},
        }
