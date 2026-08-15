from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DlBomLine(models.Model):
    _name = "dl.bom.line"
    _description = "Dòng BOM"
    _inherit = ["dl.bom.line.mixin"]
    _order = "id"

    bom_id = fields.Many2one(
        "dl.bom",
        string="BOM",
        required=True,
        ondelete="cascade",
    )

    # Bản vẽ kỹ thuật của sản phẩm (lấy từ BOM cha) — hiển thị ngay trên form
    # tạo/sửa dòng vật tư để KTV vừa xem bản vẽ vừa nhập kích thước/định mức.
    # related qua bom_id.product_id nên hoạt động cả khi BOM cha chưa lưu.
    drawing_attachment_id = fields.Many2one(
        related="bom_id.drawing_attachment_id", string="File bản vẽ", readonly=True)
    drawing_mimetype = fields.Char(related="bom_id.drawing_mimetype", readonly=True)
    drawing_filename = fields.Char(related="bom_id.drawing_filename", readonly=True)

    price_snapshot = fields.Float(
        string="Đơn giá snapshot",
        compute="_compute_price_snapshot",
        store=True,
        readonly=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    recovery_value = fields.Float(
        string="Giá trị thu hồi",
        compute="_compute_recovery_value",
        store=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    subtotal = fields.Float(
        string="Thành tiền",
        compute="_compute_subtotal",
        store=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    @api.depends(
        "material_id",
        "material_id.seller_ids.price",
        "material_id.seller_ids.approval_state",
        "material_id.seller_ids.is_applied",
    )
    # Tính lại "Đơn giá snapshot" mỗi khi đổi vật tư/giá NCC — cột chi phí trên tab Dòng BOM (chỉ Kế toán/CEO/Admin/Trưởng KD thấy).
    def _compute_price_snapshot(self):
        for rec in self:
            price = 0.0
            component = rec.material_id

            if component and component.product_kind == "material_processed":
                # LK-02 (P1) — dùng CHUNG helper chọn BOM chuẩn với pricing engine
                # (_resolve_child_bom). Trước đây tìm "version desc" không lọc
                # bom_type ⇒ một BOM báo giá (instance đơn) version cao THẮNG BOM
                # chuẩn của BTP, làm hai đường tính giá vốn lệch nhau (§3.3-B).
                bom = self.env["dl.bom"]._standard_child_bom(component)
                if bom:
                    price = bom.total_material_cost
            elif component:
                seller = component.seller_ids.filtered("is_applied")
                if seller:
                    price = seller[0].price

            rec.price_snapshot = price

    @api.depends("effective_qty", "quantity", "material_id.dlm_has_recovery",
                 "material_id.dlm_recovery_rate",
                 "material_id.dlm_scrap_product_id.list_price")
    # Tính lại "Giá trị thu hồi" (tiền phế liệu thu hồi được) khi số lượng/vật tư đổi.
    def _compute_recovery_value(self):
        for rec in self:
            rec.recovery_value = rec._dlm_recovery_value()

    # Tính lại "Thành tiền" của dòng = số lượng thực dùng × đơn giá − giá trị thu hồi.
    @api.depends("effective_qty", "price_snapshot", "recovery_value")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.effective_qty * rec.price_snapshot - rec.recovery_value

    dlm_material_is_btp = fields.Boolean(
        string="Là bán thành phẩm",
        compute="_compute_dlm_material_is_btp")

    # Cờ hiển thị nút "Mở định mức BTP" trên dòng — bật khi vật tư của dòng là bán thành phẩm.
    @api.depends("material_id")
    def _compute_dlm_material_is_btp(self):
        for rec in self:
            rec.dlm_material_is_btp = bool(
                rec.material_id
                and rec.material_id.product_kind == "material_processed")

    # Nút "Mở định mức BTP ↗" trên dòng BOM — mở BOM chuẩn của BTP, hoặc mở form tạo mới nếu chưa có.
    def action_open_btp_bom(self):
        self.ensure_one()
        material = self.material_id
        if not material or material.product_kind != "material_processed":
            raise UserError(_("Dòng này không phải bán thành phẩm."))
        bom = self.env["dl.bom"]._standard_child_bom(material)
        if not bom:
            bom = self.env["dl.bom"].search(
                [("product_id", "=", material.id)], order="version desc", limit=1)
        view = self.env.ref("dl_technical.view_dl_bom_form")
        if bom:
            return {
                "type": "ir.actions.act_window",
                "name": bom.display_name,
                "res_model": "dl.bom",
                "res_id": bom.id,
                "view_mode": "form",
                "views": [(view.id, "form")],
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Định mức của %s") % material.display_name,
            "res_model": "dl.bom",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
            "context": {
                "default_product_id": material.id,
                "default_bom_type": "template",
            },
        }

    # Validate lúc lưu dòng BOM: chặn tham chiếu BTP vòng lặp (BTP con lại chứa chính sản phẩm cha).
    @api.constrains("material_id", "bom_id")
    def _dlm_check_no_cycle(self):
        Bom = self.env["dl.bom"]
        for line in self:
            mat = line.material_id
            if not mat or mat.product_kind != "material_processed":
                continue
            root = line.bom_id.product_id
            if not root:
                continue
            seen, stack, depth = set(), [mat], 0
            while stack:
                depth += 1
                if depth > 100:      # fail-safe tuyệt đối (không tin dữ liệu)
                    break
                comp = stack.pop()
                if comp.id in seen:
                    continue
                seen.add(comp.id)
                if comp.id == root.id:
                    raise ValidationError(_(
                        "Định mức vòng lặp: bán thành phẩm “%(mat)s” đã (gián "
                        "tiếp) dùng chính sản phẩm “%(root)s”. Hãy bỏ mắt xích "
                        "này khỏi định mức.",
                        mat=mat.display_name, root=root.display_name))
                child = Bom._standard_child_bom(comp)
                stack += [
                    cl.material_id for cl in child.line_ids
                    if cl.material_id
                    and cl.material_id.product_kind == "material_processed"
                ]
