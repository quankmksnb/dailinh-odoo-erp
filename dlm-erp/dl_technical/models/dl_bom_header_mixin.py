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

    # ── Truy vết người/ngày duyệt (thiết kế BOM truy xuất §5.1) ──────────────
    # Điền khi action_confirm. Không copy sang phiên bản mới (bản mới phải được
    # xác nhận lại). Dùng để stamp sang dòng báo giá/đơn và audit.
    approved_by = fields.Many2one(
        "res.users", string="Người duyệt", readonly=True, copy=False, tracking=True)
    approved_date = fields.Datetime(
        string="Ngày duyệt", readonly=True, copy=False, tracking=True)

    # ── Phiên bản hiện hành (§4.3) ──────────────────────────────────────────
    # Mỗi phạm vi (_version_domain) chỉ có 1 bản is_current. Confirm bản mới sẽ
    # tự bỏ cờ ở bản cũ (auto-supersede, chỉ bỏ cờ — KHÔNG lưu trữ bản cũ).
    is_current = fields.Boolean(
        string="Phiên bản hiện hành", readonly=True, copy=False, default=False)

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
            rec.approved_by = rec.env.user
            rec.approved_date = fields.Datetime.now()
            # Xác nhận = trở thành phiên bản hiện hành, bỏ cờ ở bản cũ.
            rec._set_current_version()

    def action_lock(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được khóa.") % rec._description)
            rec.status = "locked"

    def action_archive(self):
        # Cho phép lưu trữ BOM đã khóa để retire bản cũ đã bị phiên bản mới thay
        # thế (§6 — trước đây khóa là ngõ cụt). BOM lưu trữ không còn là hiện hành.
        for rec in self:
            rec.status = "archived"
            rec.is_current = False

    def action_reset_draft(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ %s đã xác nhận mới được chuyển về Nháp.") % rec._description)
            # Chặn cứng nếu BOM đã được báo giá/đơn chốt tham chiếu (hook được
            # dl_sale override — bảo toàn lịch sử: sửa = tạo phiên bản mới).
            rec._check_can_reset_draft()
            rec.status = "draft"
            rec.is_current = False

    def _check_can_reset_draft(self):
        """Hook chặn hạ-nháp. Mặc định no-op (BOM mẫu không bị đơn tham chiếu);
        dl_sale override cho dl.bom để chặn khi đã dùng cho báo giá/đơn chốt."""
        return

    def _set_current_version(self):
        """Đặt bản ghi này làm phiên bản hiện hành của phạm vi (_version_domain),
        bỏ cờ is_current ở mọi bản khác cùng phạm vi (chỉ bỏ cờ, không đổi trạng
        thái/lưu trữ bản cũ)."""
        for rec in self:
            others = rec.search(rec._version_domain()) - rec
            current_others = others.filtered("is_current")
            if current_others:
                current_others.write({"is_current": False})
            if not rec.is_current:
                rec.is_current = True

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
        # is_current/approved_* là cờ hệ thống — bản khóa vẫn cho đổi (auto-
        # supersede có thể bỏ cờ hiện hành ở một bản đã khóa khi có bản mới).
        allowed = {
            "status", "is_current", "approved_by", "approved_date",
            "message_main_attachment_id", "message_follower_ids",
        }
        for rec in self:
            if rec.status == "locked" and set(vals.keys()) - allowed:
                raise UserError(_("%s đã khóa không thể sửa — hãy tạo phiên bản mới.") % rec._description)
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("%s đã khóa không thể xóa.") % rec._description)
        return super().unlink()
