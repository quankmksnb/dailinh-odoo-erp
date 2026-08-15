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

    # Validate lúc lưu Nhóm sản phẩm: "BOM mẫu mặc định" phải cùng nhóm và đã Xác nhận/Khóa.
    @api.constrains("bom_template_id")
    def _dlm_check_bom_template_id(self):
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

    # Tính lại danh sách BOM/BOM chuẩn/BOM theo đơn hiện trên tab "BOM liên quan" của form sản phẩm.
    @api.depends("product_kind")
    def _compute_bom_ids(self):
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

    # Kiểm tra sản phẩm này có phải "Sản phẩm dùng chung" của 1 BOM mẫu tham số không — dùng để chặn wizard RFQ tự động chọn nhầm nó.
    def _dlm_is_parametric_generic(self):
        self.ensure_one()
        return bool(self.env["dl.bom.template"].search_count([
            ("generic_product_id", "=", self.id),
            ("is_parametric", "=", True),
            ("status", "in", ("confirmed", "locked")),
        ]))

    # Validate lúc lưu sản phẩm: chặn tạo sản phẩm gia công/BTP trùng hệt tên với sản phẩm chính thức đã có.
    @api.constrains("name", "product_kind", "is_rfq_provisional")
    def _check_dlm_name_duplicate(self):
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

    # Nút "Chuyển Hoạt động" trên form sản phẩm — chặn nếu sản phẩm còn tạm từ RFQ chưa hoàn tất.
    def action_lifecycle_activate(self):
        provisional = self.filtered("is_rfq_provisional")
        if provisional:
            raise UserError(_(
                "Sản phẩm tạm từ RFQ chỉ được chính thức hóa khi Kỹ thuật bấm "
                "'Hoàn tất dòng' trong workspace RFQ."))
        return super().action_lifecycle_activate()

    # Dọn tự động các sản phẩm tạm từ RFQ bị bỏ dở (chưa dùng tới) — không đụng sản phẩm đang được tham chiếu.
    def _cleanup_unused_rfq_provisional(self):
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

    # Khi đổi Nhóm sản phẩm trên form vật tư mà chưa nhập % hao hụt, tự điền theo quy tắc hao hụt cấu hình cho nhóm đó.
    @api.onchange("categ_id", "product_kind")
    def _onchange_dlm_waste_default(self):
        if self.product_kind not in ("material", "material_processed"):
            return
        if self.dlm_waste_rate:
            return
        rule = self._dlm_category_waste_rule()
        if rule:
            self.dlm_waste_rate = rule.waste_rate
            self.dlm_scrap_product_id = rule.scrap_product_id

    # Tìm quy tắc hao hụt đang áp dụng cho Nhóm sản phẩm của vật tư này.
    def _dlm_category_waste_rule(self):
        self.ensure_one()
        if not self.categ_id:
            return self.env["dl.pricing.waste.rule"].browse()
        return self.env["dl.pricing.waste.rule"].sudo().search([
            ("state", "=", "active"),
            ("target_type", "=", "category"),
            ("category_id", "=", self.categ_id.id),
        ], order="valid_from desc, revision desc", limit=1)

    # Nút "+ Tạo BOM" trên tab "BOM liên quan" của form sản phẩm — mở form BOM mới, tự gắn sẵn sản phẩm đang xem.
    def action_create_bom(self):
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
