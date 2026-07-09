# -*- coding: utf-8 -*-
# ============================================================================
# S02 — Cấu hình Hệ thống · Tab 1 (Tham số báo giá / Cost Structure)
# Model lưu thật vào DB cho màn OWL sys_config.
# Cơ cấu giá = 5 thành phần (vật tư/nhân công/vận hành/rủi ro/lợi nhuận) cộng
# lại nên bằng 100% tổng báo giá — nhưng là tỷ lệ THAM KHẢO (không chặn cứng).
# Mọi thay đổi ghi audit vào dl.config.audit.log (BR-28).
# ============================================================================
from odoo import api, fields, models, _
from odoo.exceptions import AccessError

# Nhãn tiếng Việt cho từng field Tab 1 — dùng khi ghi audit "cũ → mới".
_TAB1_LABELS = {
    "material_pct": "Tỷ lệ chi phí vật tư (%)",
    "labor_pct": "Tỷ lệ chi phí nhân công (%)",
    "overhead_pct": "Chi phí vận hành / overhead (%)",
    "risk_pct": "Tỷ lệ rủi ro / phát sinh (%)",
    "margin_pct": "Lợi nhuận mục tiêu (%)",
    "max_discount_pct": "Chiết khấu tối đa (%)",
    "vat_pct": "VAT mặc định (%)",
    "price_validity_days": "Hiệu lực giá vật tư (ngày)",
    "rounding_to": "Làm tròn giá bán",
}
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
    _description = "Cấu hình tham số báo giá (S02 · Tab 1)"

    name = fields.Char("Tên cấu hình", default="Cấu hình báo giá", required=True)

    # --- Cơ cấu giá: 5 thành phần, Σ nên = 100% tổng báo giá ----------------
    material_pct = fields.Float("Tỷ lệ vật tư (%)", default=55.0)
    labor_pct = fields.Float("Tỷ lệ nhân công (%)", default=25.0)
    overhead_pct = fields.Float("Tỷ lệ vận hành / overhead (%)", default=5.0)
    risk_pct = fields.Float("Tỷ lệ rủi ro / phát sinh (%)", default=3.0)
    margin_pct = fields.Float("Lợi nhuận mục tiêu (%)", default=12.0)
    structure_total = fields.Float(
        "Tổng cơ cấu (%)", compute="_compute_structure_total"
    )

    # --- Tham số khác (không nằm trong 100%) --------------------------------
    max_discount_pct = fields.Float("Chiết khấu tối đa (%)", default=15.0)
    vat_pct = fields.Float("VAT mặc định (%)", default=0.0)
    price_validity_days = fields.Integer("Hiệu lực giá vật tư (ngày)", default=30)
    rounding_to = fields.Integer("Làm tròn giá bán đến (đ)", default=1000)

    waste_ids = fields.One2many(
        "dl.pricing.waste", "config_id", "Hao hụt theo nhóm vật tư"
    )

    @api.depends(
        "material_pct", "labor_pct", "overhead_pct", "risk_pct", "margin_pct"
    )
    def _compute_structure_total(self):
        for r in self:
            r.structure_total = (
                r.material_pct + r.labor_pct + r.overhead_pct + r.risk_pct + r.margin_pct
            )

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

    # --- Đọc / ghi cho OWL (khóa camelCase khớp state.cost bên client) ------
    def _read_cost(self):
        self.ensure_one()
        return {
            "material": self.material_pct,
            "labor": self.labor_pct,
            "overhead": self.overhead_pct,
            "risk": self.risk_pct,
            "margin": self.margin_pct,
            "maxDiscount": self.max_discount_pct,
            "vat": self.vat_pct,
            "priceValidity": self.price_validity_days,
            "rounding": self.rounding_to,
        }

    def _read_waste(self):
        self.ensure_one()
        return [
            {"group": w.group_name, "pct": w.waste_pct} for w in self.waste_ids
        ]

    @api.model
    def get_tab1(self):
        """OWL gọi lúc mở màn: nạp cấu hình + bảng hao hụt + audit + quyền sửa."""
        cfg = self._get_singleton()
        logs = self.env["dl.config.audit.log"].sudo().search(
            [], order="id desc", limit=100
        )
        return {
            "cost": cfg._read_cost(),
            "waste": cfg._read_waste(),
            "canEdit": cfg._can_edit(),
            "audit": [l._to_dict() for l in logs],
        }

    @api.model
    def save_tab1(self, cost, waste):
        """OWL gọi khi Lưu: ghi DB + sinh audit "cũ → mới". Trả về giá trị chuẩn
        (server là nguồn sự thật) + các dòng audit vừa tạo để client hiển thị."""
        cfg = self._get_singleton()
        if not cfg._can_edit():
            raise AccessError(_("Chỉ Admin/CEO được sửa cấu hình báo giá."))

        cost = cost or {}
        new_vals = {
            "material_pct": float(cost.get("material") or 0),
            "labor_pct": float(cost.get("labor") or 0),
            "overhead_pct": float(cost.get("overhead") or 0),
            "risk_pct": float(cost.get("risk") or 0),
            "margin_pct": float(cost.get("margin") or 0),
            "max_discount_pct": float(cost.get("maxDiscount") or 0),
            "vat_pct": float(cost.get("vat") or 0),
            "price_validity_days": int(cost.get("priceValidity") or 0),
            "rounding_to": int(cost.get("rounding") or 0),
        }

        # Diff scalar → dòng audit
        audit = []
        for fname, label in _TAB1_LABELS.items():
            old, new = cfg[fname], new_vals[fname]
            if fname == "rounding_to":
                if int(old) != int(new):
                    audit.append((label, "%s → %s" % (cfg._round_label(old), cfg._round_label(new))))
            elif float(old) != float(new):
                audit.append((label, "%s → %s" % (_fmt_num(old), _fmt_num(new))))

        # Diff bảng hao hụt
        old_waste = [(w.group_name or "", w.waste_pct) for w in cfg.waste_ids]
        new_waste = [
            ((w.get("group") or "").strip(), float(w.get("pct") or 0))
            for w in (waste or [])
        ]
        waste_changed = old_waste != new_waste

        # Ghi
        cfg.write(new_vals)
        if waste_changed:
            cfg.waste_ids.unlink()
            cfg.write(
                {
                    "waste_ids": [
                        (0, 0, {"group_name": g, "waste_pct": p})
                        for g, p in new_waste
                    ]
                }
            )
            audit.append(("Tỷ lệ hao hụt theo nhóm vật tư", "Đã cập nhật bảng"))

        # Audit ghi sudo (append-only, người dùng không cần quyền create)
        Log = self.env["dl.config.audit.log"].sudo()
        created = Log.create(
            [
                {
                    "config_tab": "Tham số báo giá",
                    "param_label": label,
                    "detail": detail,
                    "user_id": self.env.uid,
                }
                for label, detail in audit
            ]
        ) if audit else Log.browse()

        return {
            "cost": cfg._read_cost(),
            "waste": cfg._read_waste(),
            "audit_new": [l._to_dict() for l in created],
        }


class DlPricingWaste(models.Model):
    _name = "dl.pricing.waste"
    _description = "Tỷ lệ hao hụt mặc định theo nhóm vật tư"
    _order = "id"

    config_id = fields.Many2one(
        "dl.pricing.config", "Cấu hình", ondelete="cascade", required=True
    )
    group_name = fields.Char("Nhóm vật tư", required=True)
    waste_pct = fields.Float("Hao hụt (%)")


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
