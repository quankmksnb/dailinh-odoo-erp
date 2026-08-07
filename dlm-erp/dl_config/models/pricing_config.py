# -*- coding: utf-8 -*-
# ============================================================================
# dl.pricing.config — singleton cấu hình báo giá.
# Màn OWL "Cấu hình Hệ thống" (S02) ĐÃ khai tử. Engine nay CHỈ còn đọc hai tham
# số vat_pct + rounding_to (quotation_pricing_service._build_context), được sửa
# trên màn "Cấu hình Báo giá" qua get_quote_settings/save_quote_settings.
#
# Các cấu hình khác (markup, chiết khấu, công đoạn, hao hụt, ma trận phê duyệt…)
# đã chuyển sang các model quy tắc V3 riêng. Toàn bộ field/method S02 cũ (cơ cấu
# %, SLA, tab1/2/3, ma trận dl.approval.level, hao hụt dl.pricing.waste) đã được
# GỠ khỏi model này (review §1.1) — không còn UI, engine không đọc, không caller.
#
# Hai model dl.pricing.waste và dl.approval.level được GIỮ (rỗng, deprecated) để
# ACL trỏ tới chúng ở dl_config + dl_technical không gãy; sẽ xóa hẳn kèm migration
# trong một phiên riêng.
# Mọi thay đổi ghi audit vào dl.config.audit.log (BR-28).
# ============================================================================
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

_ROUNDING_LABELS = {
    0: "Không làm tròn",
    1000: "Làm tròn đến 1.000đ",
    10000: "Làm tròn đến 10.000đ",
}


def _fmt_num(v):
    """55.0 → '55', 12.5 → '12.5' (bỏ đuôi .0 cho gọn khi ghi audit)."""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else ("%g" % f)
    except (TypeError, ValueError):
        return str(v)


class DlPricingConfig(models.Model):
    _name = "dl.pricing.config"
    _description = "Cấu hình tham số báo giá (VAT & làm tròn giá bán)"

    name = fields.Char("Tên cấu hình", default="Cấu hình báo giá", required=True)

    # HAI tham số DUY NHẤT engine còn đọc từ singleton này (xem
    # quotation_pricing_service._build_context). VAT cộng ở cấp báo giá; làm tròn
    # giá bán theo bội số (đ), 0 = không làm tròn.
    vat_pct = fields.Float("VAT mặc định (%)", default=0.0)
    rounding_to = fields.Integer("Làm tròn giá bán đến (đ)", default=1000)

    # --- Quyền & singleton --------------------------------------------------
    def _can_edit(self):
        """Chỉ Admin/CEO được sửa (đúng đặc tả S02); các role khác chỉ xem."""
        u = self.env.user
        return u.has_group("dl_base.dl_group_admin") or u.has_group(
            "dl_base.dl_group_ceo"
        )

    @api.model
    def _get_singleton(self):
        """Trả về bản ghi cấu hình duy nhất; tạo (sudo) nếu chưa có seed."""
        cfg = self.sudo().search([], limit=1)
        if not cfg:
            cfg = self.sudo().create({"name": "Cấu hình báo giá"})
        # browse lại theo quyền người dùng để read/write tôn trọng ACL
        return self.browse(cfg.id)

    def _round_label(self, v):
        return _ROUNDING_LABELS.get(int(v or 0), str(v))

    # --- VAT & Làm tròn: 2 tham số S02 THẬT SỰ vào giá bán ------------------
    # Sau khi khai tử màn "Cấu hình Hệ thống" (S02), hai tham số duy nhất engine
    # còn đọc từ singleton này (vat_pct, rounding_to — xem quotation_pricing_service
    # ._build_context) được sửa ngay trên màn "Cấu hình Báo giá" để cả hệ chỉ còn
    # MỘT nguồn cấu hình. Model + singleton giữ nguyên; chỉ UI chuyển nhà.
    @api.model
    def get_quote_settings(self):
        cfg = self._get_singleton()
        return {
            "vat": cfg.vat_pct,
            "rounding": cfg.rounding_to,
            "canEdit": cfg._can_edit(),
        }

    @api.model
    def save_quote_settings(self, vat, rounding):
        cfg = self._get_singleton()
        if not cfg._can_edit():
            raise AccessError(_("Chỉ Admin/CEO được sửa VAT & làm tròn giá bán."))
        new_vals = {
            "vat_pct": float(vat or 0),
            "rounding_to": int(rounding or 0),
        }
        # Diff → audit (giữ BR-28: mọi thay đổi cấu hình đều ghi vết).
        audit = []
        if float(cfg.vat_pct) != new_vals["vat_pct"]:
            audit.append(("VAT mặc định (%)",
                          "%s → %s" % (_fmt_num(cfg.vat_pct), _fmt_num(new_vals["vat_pct"]))))
        if int(cfg.rounding_to) != new_vals["rounding_to"]:
            audit.append(("Làm tròn giá bán",
                          "%s → %s" % (cfg._round_label(cfg.rounding_to),
                                       cfg._round_label(new_vals["rounding_to"]))))
        cfg.write(new_vals)
        if audit:
            self.env["dl.config.audit.log"].sudo().create([
                {
                    "config_tab": "Thuế & Làm tròn",
                    "param_label": label,
                    "detail": detail,
                    "user_id": self.env.uid,
                }
                for label, detail in audit
            ])
        return {"vat": cfg.vat_pct, "rounding": cfg.rounding_to}

    @api.constrains("vat_pct", "rounding_to")
    def _check_quote_settings(self):
        """VAT & làm tròn là 2 tham số engine áp vào giá bán — chặn giá trị vô
        lý ở mọi đường ghi (UI, RPC, import)."""
        for cfg in self:
            if not (0 <= cfg.vat_pct <= 100):
                raise ValidationError(_("VAT phải trong khoảng 0–100%."))
            if cfg.rounding_to < 0:
                raise ValidationError(_("Mức làm tròn giá bán không được âm."))


class DlPricingWaste(models.Model):
    # DEPRECATED (review §1.1): nguồn hao hụt thật là product.dlm_waste_rate.
    # Model giữ lại (rỗng) chỉ để ACL trỏ tới model_dl_pricing_waste (dl_config +
    # dl_technical) không gãy; không còn UI, engine không đọc. Xóa hẳn (kèm
    # migration drop bảng + gỡ ACL) để dành một phiên riêng.
    _name = "dl.pricing.waste"
    _description = "[Ngừng dùng] Tỷ lệ hao hụt mặc định theo nhóm vật tư"
    _order = "id"

    group_name = fields.Char("Nhóm vật tư")
    waste_pct = fields.Float("Hao hụt (%)")


class DlApprovalLevel(models.Model):
    # DEPRECATED (review §1.1): luồng phê duyệt báo giá thật dùng
    # dl.pricing.approval.matrix. Model giữ lại (rỗng) chỉ để ACL trỏ tới
    # model_dl_approval_level không gãy; không còn UI/caller. Xóa hẳn (kèm
    # migration) để dành một phiên riêng.
    _name = "dl.approval.level"
    _description = "[Ngừng dùng] Cấp duyệt trong Ma trận phê duyệt (S02 · Tab 2)"
    _order = "sequence, id"

    sequence = fields.Integer("Thứ tự", default=10)
    name = fields.Char("Tên cấp duyệt")


class DlConfigAuditLog(models.Model):
    _name = "dl.config.audit.log"
    _description = "Nhật ký thay đổi cấu hình hệ thống (S02)"
    _order = "id desc"

    config_tab = fields.Char("Nhóm cấu hình")
    param_label = fields.Char("Tham số")
    detail = fields.Char("Thay đổi (cũ → mới)")
    user_id = fields.Many2one(
        "res.users", "Người thay đổi", default=lambda s: s.env.uid
    )

    def _to_dict(self):
        self.ensure_one()
        ts = (
            fields.Datetime.context_timestamp(self, self.create_date)
            if self.create_date
            else False
        )
        return {
            "time": ts.strftime("%d/%m/%Y %H:%M") if ts else "",
            "tab": self.config_tab or "",
            "param": self.param_label or "",
            "detail": self.detail or "",
        }
