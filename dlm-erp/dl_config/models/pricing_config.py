# -*- coding: utf-8 -*-
# ============================================================================
# S02 — Cấu hình Hệ thống · Tab 1 (Tham số báo giá / Cost Structure)
# Model lưu thật vào DB cho màn OWL sys_config.
# Cơ cấu giá = 5 thành phần (vật tư/nhân công/vận hành/rủi ro/lợi nhuận) cộng
# lại nên bằng 100% tổng báo giá — nhưng là tỷ lệ THAM KHẢO (không chặn cứng).
# Mọi thay đổi ghi audit vào dl.config.audit.log (BR-28).
# ============================================================================
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

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

# Nhãn tiếng Việt cho từng field Tab 3 (SLA & Escalation) — dùng khi ghi audit.
# Thứ tự dict = thứ tự dòng audit sinh ra khi Lưu.
_TAB3_LABELS = {
    "sla_sales_manager_hours": "SLA Trưởng KD (giờ)",
    "sla_ceo_hours": "SLA CEO (giờ)",
    "sla_reminder_every_hours": "Tần suất nhắc nhở (giờ)",
    "sla_overdue_remind": "Nhắc nhở khi quá SLA",
    "sla_overdue_escalate": "Tự động escalate khi quá SLA",
    "sla_overdue_log": "Ghi log khi quá SLA",
    "sla_overdue_kpi": "Ghi nhận KPI khi quá SLA",
    "sla_require_late_reason": "Bắt buộc lý do khi duyệt trễ",
}


def _bool_label(v):
    """True → 'Bật', False → 'Tắt' (dùng khi ghi audit các công tắc SLA)."""
    return "Bật" if v else "Tắt"


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

    # --- S02 · Tab 3: SLA & Escalation --------------------------------------
    # SLA phê duyệt (giờ làm việc) + hành động khi quá hạn. S10 (Phê duyệt) đọc
    # cấu hình này để tính deadline & trigger escalation. Sửa SLA chỉ áp dụng
    # cho bước duyệt MỚI bắt đầu sau thời điểm lưu; bước đang chạy giữ nguyên.
    sla_sales_manager_hours = fields.Integer(
        "SLA Trưởng KD (giờ làm việc)", default=4
    )
    sla_ceo_hours = fields.Integer("SLA CEO (giờ làm việc)", default=8)
    sla_reminder_every_hours = fields.Integer("Tần suất nhắc nhở (giờ)", default=2)
    sla_require_late_reason = fields.Boolean(
        "Bắt buộc lý do khi duyệt trễ", default=True
    )
    # Hành động khi quá SLA (đặc tả: Nhắc → Escalate → Ghi log → Ghi nhận KPI)
    sla_overdue_remind = fields.Boolean("Nhắc nhở khi quá SLA", default=True)
    sla_overdue_escalate = fields.Boolean(
        "Tự động escalate lên cấp trên / Backup", default=True
    )
    sla_overdue_log = fields.Boolean("Ghi log khi quá SLA", default=True)
    sla_overdue_kpi = fields.Boolean("Ghi nhận để tính KPI", default=True)

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

    def _read_sla(self):
        """Trả cấu hình SLA theo khóa camelCase khớp state.sla bên OWL."""
        self.ensure_one()
        return {
            "salesManager": self.sla_sales_manager_hours,
            "ceo": self.sla_ceo_hours,
            "reminderEvery": self.sla_reminder_every_hours,
            "requireLateReason": self.sla_require_late_reason,
            "onOverdue": {
                "remind": self.sla_overdue_remind,
                "escalate": self.sla_overdue_escalate,
                "log": self.sla_overdue_log,
                "kpi": self.sla_overdue_kpi,
            },
        }

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

    # --- Tab 3: SLA & Escalation -------------------------------------------
    @api.model
    def get_tab3(self):
        """OWL gọi lúc mở màn: nạp cấu hình SLA + quyền sửa.
        (Audit dùng chung, đã nạp ở get_tab1.)"""
        cfg = self._get_singleton()
        return {"sla": cfg._read_sla(), "canEdit": cfg._can_edit()}

    @api.model
    def save_tab3(self, sla):
        """OWL gọi khi Lưu SLA: ghi DB + sinh audit "cũ → mới". Trả về giá trị
        chuẩn (server là nguồn sự thật) + các dòng audit vừa tạo."""
        cfg = self._get_singleton()
        if not cfg._can_edit():
            raise AccessError(_("Chỉ Admin/CEO được sửa cấu hình SLA."))

        sla = sla or {}
        overdue = sla.get("onOverdue") or {}
        sm = int(sla.get("salesManager") or 0)
        ceo = int(sla.get("ceo") or 0)
        remind_every = int(sla.get("reminderEvery") or 0)

        # SLA & tần suất nhắc phải ≥ 1 giờ làm việc (chặn cứng — vô nghĩa nếu < 1).
        if sm < 1 or ceo < 1 or remind_every < 1:
            raise ValidationError(
                _("SLA và tần suất nhắc nhở phải ≥ 1 giờ làm việc.")
            )

        new_vals = {
            "sla_sales_manager_hours": sm,
            "sla_ceo_hours": ceo,
            "sla_reminder_every_hours": remind_every,
            "sla_require_late_reason": bool(sla.get("requireLateReason")),
            "sla_overdue_remind": bool(overdue.get("remind")),
            "sla_overdue_escalate": bool(overdue.get("escalate")),
            "sla_overdue_log": bool(overdue.get("log")),
            "sla_overdue_kpi": bool(overdue.get("kpi")),
        }

        # Diff → dòng audit (số cho SLA/giờ, Bật/Tắt cho các công tắc)
        audit = []
        for fname, label in _TAB3_LABELS.items():
            old, new = cfg[fname], new_vals[fname]
            if isinstance(old, bool) or isinstance(new, bool):
                if bool(old) != bool(new):
                    audit.append(
                        (label, "%s → %s" % (_bool_label(old), _bool_label(new)))
                    )
            elif int(old) != int(new):
                audit.append((label, "%s → %s" % (_fmt_num(old), _fmt_num(new))))

        cfg.write(new_vals)

        # Audit ghi sudo (append-only, người dùng không cần quyền create)
        Log = self.env["dl.config.audit.log"].sudo()
        created = Log.create(
            [
                {
                    "config_tab": "SLA & Escalation",
                    "param_label": label,
                    "detail": detail,
                    "user_id": self.env.uid,
                }
                for label, detail in audit
            ]
        ) if audit else Log.browse()

        return {
            "sla": cfg._read_sla(),
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
