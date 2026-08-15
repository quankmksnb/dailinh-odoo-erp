from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DlBomHeaderMixin(models.AbstractModel):
    # Phần đầu BOM dùng chung cho form BOM sản phẩm (dl.bom) và form BOM mẫu (dl.bom.template).

    _name = "dl.bom.header.mixin"
    _description = "BOM — trường & workflow đầu BOM dùng chung"

    version = fields.Integer(
        string="Phiên bản",
        default=1,
        required=True,
        tracking=True,
    )

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

    approved_by = fields.Many2one(
        "res.users", string="Người duyệt", readonly=True, copy=False, tracking=True)
    approved_date = fields.Datetime(
        string="Ngày duyệt", readonly=True, copy=False, tracking=True)

    is_current = fields.Boolean(
        string="Phiên bản hiện hành", readonly=True, copy=False, default=False)

    def _version_domain(self):
        # Override ở dl.bom/dl.bom.template: domain lọc ra các phiên bản cùng 1 BOM.
        self.ensure_one()
        raise NotImplementedError

    def _compute_next_version(self):
        # Tính số phiên bản kế tiếp — dùng lúc tạo mới và khi bấm "Tạo phiên bản mới".
        self.ensure_one()
        existing = self.search(self._version_domain())
        return (max(existing.mapped("version")) + 1) if existing else 1

    def action_confirm(self):
        # Nút "Xác nhận" trên form BOM/BOM mẫu — chuyển Nháp → Đã xác nhận, ghi người/ngày duyệt.
        for rec in self:
            if rec.status != "draft":
                raise UserError(_("Chỉ %s ở trạng thái Nháp mới được xác nhận.") % rec._description)
            if not rec.line_ids:
                raise UserError(_("%s phải có ít nhất một dòng vật tư.") % rec._description)
            rec.status = "confirmed"
            rec.approved_by = rec.env.user
            rec.approved_date = fields.Datetime.now()
            if rec._should_set_current_version():
                rec._set_current_version()

    def _should_set_current_version(self):
        # Hook: BOM tạm từ RFQ chỉ thành phiên bản hiện hành sau khi RFQ hoàn tất.
        self.ensure_one()
        return True

    def action_lock(self):
        # Nút "Khóa" trên form BOM/BOM mẫu — chuyển Đã xác nhận → Đã khóa, sau đó không sửa được nữa.
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được khóa.") % rec._description)
            rec.status = "locked"

    def action_archive(self):
        # Nút "Lưu trữ" trên form BOM/BOM mẫu — cho phép lưu trữ cả bản đã khóa để retire bản cũ.
        for rec in self:
            rec.status = "archived"
            rec.is_current = False

    def action_reset_draft(self):
        # Nút "Về nháp" trên form BOM/BOM mẫu — chỉ cho từ Đã xác nhận, chặn nếu đã bị báo giá/đơn dùng.
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được chuyển về Nháp.") % rec._description)
            rec._check_can_reset_draft()
            rec.status = "draft"
            rec.is_current = False

    def _check_can_reset_draft(self):
        # Hook chặn về-nháp; dl_sale override để chặn khi BOM đã dùng cho báo giá/đơn chốt.
        return

    def _set_current_version(self):
        # Đánh dấu bản ghi này là phiên bản hiện hành, tự bỏ cờ ở các phiên bản khác cùng BOM.
        for rec in self:
            others = rec.search(rec._version_domain()) - rec
            current_others = others.filtered("is_current")
            if current_others:
                current_others.write({"is_current": False})
            if not rec.is_current:
                rec.is_current = True

    def action_create_new_version(self):
        # Nút "Tạo phiên bản mới" — nhân bản BOM/BOM mẫu hiện tại thành bản Nháp, mở form bản mới.
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
        # Chặn sửa mọi field khi BOM đã Khóa, trừ vài field hệ thống (is_current, approved_*...).
        allowed = {
            "status", "is_current", "approved_by", "approved_date",
            "message_main_attachment_id", "message_follower_ids",
        }
        for rec in self:
            if rec.status == "locked" and set(vals.keys()) - allowed:
                raise UserError(_("%s đã khóa không thể sửa — hãy tạo phiên bản mới.") % rec._description)
        return super().write(vals)

    def unlink(self):
        # Chặn xóa BOM/BOM mẫu đã Khóa.
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("%s đã khóa không thể xóa.") % rec._description)
        return super().unlink()
