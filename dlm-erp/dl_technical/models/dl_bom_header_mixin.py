from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DlBomHeaderMixin(models.AbstractModel):
    """Field/logic dùng chung cho phần đầu 1 BOM — dl.bom (Product BOM) và
    dl.bom.template (BOM Template). Hai màn "cấu trúc gần giống nhau": cùng
    version/status/Output Quantity, cùng workflow xác nhận/khóa/lưu trữ/tạo
    phiên bản mới (giữ khả năng versioning cho cả 2)."""

    _name = "dl.bom.header.mixin"
    _description = "BOM — trường & workflow đầu BOM dùng chung"

    version = fields.Integer(
        string="Phiên bản",
        default=1,
        required=True,
        tracking=True,
    )

    # Output Quantity — mặc định 1 (1 BOM tạo cho 1 sản phẩm/nhóm sản phẩm).
    product_qty = fields.Float(
        string="Số lượng đầu ra",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
    )

    status = fields.Selection(
        [
            ("draft", "Nháp"),
            ("confirmed", "Đã xác nhận"),
            ("locked", "Đã khóa"),
            ("archived", "Lưu trữ"),
        ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        copy=False,
    )

    def _version_domain(self):
        """Override ở model cụ thể: domain tìm các phiên bản cùng 1 BOM (dùng
        để tính version tiếp theo + là cơ sở cho SQL constraint unique)."""
        self.ensure_one()
        raise NotImplementedError

    def _compute_next_version(self):
        """Version tiếp theo cho phạm vi hiện tại (sản phẩm/nhóm sản phẩm +
        loại BOM) — dùng cho onchange lúc tạo mới VÀ cho action_create_new_version."""
        self.ensure_one()
        existing = self.search(self._version_domain())
        return (max(existing.mapped("version")) + 1) if existing else 1

    def action_confirm(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError(_("Chỉ %s ở trạng thái Nháp mới được xác nhận.") % rec._description)
            if not rec.line_ids:
                raise UserError(_("%s phải có ít nhất một dòng vật tư.") % rec._description)
            rec.status = "confirmed"

    def action_lock(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được khóa.") % rec._description)
            rec.status = "locked"

    def action_archive(self):
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("Không thể lưu trữ %s đã khóa.") % rec._description)
            rec.status = "archived"

    def action_reset_draft(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được chuyển về Nháp.") % rec._description)
            rec.status = "draft"

    def action_create_new_version(self):
        self.ensure_one()
        new_rec = self.copy({"version": self._compute_next_version(), "status": "draft"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": new_rec.id,
            "target": "current",
        }

    def write(self, vals):
        allowed = {"status", "message_main_attachment_id", "message_follower_ids"}
        for rec in self:
            if rec.status == "locked" and set(vals.keys()) - allowed:
                raise UserError(_("%s đã khóa không thể sửa — hãy tạo phiên bản mới.") % rec._description)
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("%s đã khóa không thể xóa.") % rec._description)
        return super().unlink()
