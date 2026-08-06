# -*- coding: utf-8 -*-
# ============================================================================
# dl.pricing.config — singleton cấu hình báo giá.
# Màn OWL "Cấu hình Hệ thống" (S02) ĐÃ khai tử; nay engine chỉ còn đọc hai tham
# số vat_pct + rounding_to (quotation_pricing_service._build_context), được sửa
# trên màn "Cấu hình Báo giá" qua get_quote_settings/save_quote_settings.
# Các field/method S02 cũ (cơ cấu %, ma trận dl.approval.level, SLA) giữ lại làm
# dữ liệu chết — không còn UI, engine không đọc; dọn schema là việc riêng.
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


# Nhãn tiếng Việt cho các giá trị Selection của Tab 2 (Ma trận phê duyệt) —
# dùng khi hiển thị & ghi audit "cũ → mới".
_ROLE_LABELS = {
    "none": "Không cần duyệt",
    "sales_manager": "Trưởng KD",
    "ceo": "CEO",
    "custom": "Vai trò tùy chỉnh",
}
_MODE_LABELS = {
    "sequential": "Tuần tự",
    "parallel": "Song song",
    "direct": "Trực tiếp",
    "none": "—",
}

# Các field của 1 cấp duyệt sẽ được so sánh để sinh dòng audit khi Lưu.
# (key nội bộ dùng ở _level_snapshot → nhãn hiển thị)
_TAB2_FIELD_LABELS = [
    ("name", "Tên cấp"),
    ("value", "Ngưỡng giá trị (triệu)"),
    ("discount", "Ngưỡng chiết khấu (%)"),
    ("margin", "Margin tối thiểu (%)"),
    ("role", "Vai trò duyệt"),
    ("user", "Người duyệt cụ thể"),
    ("backup", "Người duyệt thay thế"),
    ("mode", "Kiểu duyệt"),
    ("sla", "SLA (giờ)"),
    ("active", "Trạng thái"),
    ("priority", "Ưu tiên"),
    ("note", "Ghi chú"),
]

# Ma trận phê duyệt mặc định (đặc tả S02 "Ví dụ ma trận mặc định"). value_max=0
# ⇒ ∞ (không giới hạn trên); margin_min=0 ⇒ không áp điều kiện margin. Người
# duyệt/backup để trống — Admin gán user thật ở màn cấu hình.
_DEFAULT_LEVELS = [
    {
        "sequence": 0, "name": "Tự động",
        "value_min": 0, "value_max": 20, "discount_min": 0, "discount_max": 5,
        "margin_min": 0, "approver_role": "none", "mode": "none", "sla_hours": 0,
        "note": "Không cần duyệt → Ready to Send", "is_active": True, "is_priority": False,
    },
    {
        "sequence": 10, "name": "Cấp 1 – Trưởng KD",
        "value_min": 20, "value_max": 100, "discount_min": 5, "discount_max": 15,
        "margin_min": 8, "approver_role": "sales_manager", "mode": "sequential",
        "sla_hours": 4, "note": "", "is_active": True, "is_priority": False,
    },
    {
        "sequence": 20, "name": "Cấp 2 – CEO",
        "value_min": 100, "value_max": 0, "discount_min": 15, "discount_max": 100,
        "margin_min": 8, "approver_role": "ceo", "mode": "sequential",
        "sla_hours": 8, "note": "", "is_active": True, "is_priority": False,
    },
    {
        "sequence": 30, "name": "Cấp 2 (ưu tiên) – Margin thấp",
        "value_min": 0, "value_max": 0, "discount_min": 0, "discount_max": 100,
        "margin_min": 8, "approver_role": "ceo", "mode": "direct", "sla_hours": 8,
        "note": "Margin < 8% → CEO trực tiếp, bỏ qua Cấp 1",
        "is_active": True, "is_priority": True,
    },
]


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

    # --- S02 · Tab 2: Ma trận phê duyệt (Approval Matrix) -------------------
    # Danh sách các cấp duyệt (cấu hình động). S09 (Tạo báo giá) đọc để định
    # tuyến; S10 (Phê duyệt) dùng người duyệt/backup/SLA của từng cấp.
    level_ids = fields.One2many(
        "dl.approval.level", "config_id", "Các cấp duyệt"
    )
    # Đã seed ma trận mặc định lần đầu chưa (để không tạo lại nếu user xóa hết).
    matrix_seeded = fields.Boolean("Đã khởi tạo ma trận", default=False)

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

    # --- Tab 2: Ma trận phê duyệt ------------------------------------------
    def _ensure_default_levels(self):
        """Seed ma trận mặc định lần đầu mở Tab 2 (kể cả DB đã tồn tại trước khi
        có tính năng). Cờ matrix_seeded ⇒ KHÔNG seed lại nếu user đã xóa hết."""
        self.ensure_one()
        if self.matrix_seeded:
            return
        # DB cũ có thể đã có cấp (vd seed XML trước đây) → chỉ đánh dấu, không nhân đôi.
        vals = {"matrix_seeded": True}
        if not self.level_ids:
            vals["level_ids"] = [(0, 0, dict(v)) for v in _DEFAULT_LEVELS]
        self.sudo().write(vals)

    def _read_levels(self):
        """Trả danh sách cấp duyệt theo khóa camelCase khớp state.levels bên OWL.
        vMax/marginMin = null khi ≤ 0 (∞ / không áp) — giữ đúng ngữ nghĩa client."""
        self.ensure_one()
        out = []
        for l in self.level_ids:  # đã _order theo sequence, id
            out.append(
                {
                    "id": l.id,
                    "name": l.name or "",
                    "vMin": l.value_min,
                    "vMax": l.value_max if l.value_max > 0 else None,
                    "dMin": l.discount_min,
                    "dMax": l.discount_max,
                    "marginMin": l.margin_min if l.margin_min > 0 else None,
                    "role": l.approver_role,
                    "user": str(l.approver_user_id.id) if l.approver_user_id else "",
                    "backup": str(l.backup_user_id.id) if l.backup_user_id else "",
                    "mode": l.mode,
                    "sla": l.sla_hours,
                    "note": l.note or "",
                    "active": l.is_active,
                    "priority": l.is_priority,
                    "pending": l.pending_count,
                }
            )
        return out

    @api.model
    def _read_approvers(self):
        """Ứng viên người duyệt / backup = user thật thuộc nhóm CEO / Trưởng KD /
        Admin (đúng đặc tả: người duyệt lấy từ danh sách user - S01)."""
        Groups = self.env["res.groups"].sudo()
        role_of = []  # (group_id, nhãn) theo thứ tự ưu tiên hiển thị
        for xmlid, label in (
            ("dl_base.dl_group_ceo", "CEO"),
            ("dl_base.dl_group_sales_manager", "Trưởng KD"),
            ("dl_base.dl_group_admin", "Admin"),
        ):
            g = self.env.ref(xmlid, raise_if_not_found=False)
            if g:
                role_of.append((g.id, label))
        group_ids = [gid for gid, _l in role_of]
        excluded = []
        root = self.env.ref("base.user_root", raise_if_not_found=False)
        if root:
            excluded.append(root.id)
        users = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("share", "=", False),
                    ("groups_id", "in", group_ids),
                    ("id", "not in", excluded),
                ],
                order="name",
            )
        )
        out = []
        for u in users:
            tag = next((lbl for gid, lbl in role_of if gid in u.groups_id.ids), "")
            out.append(
                {
                    "id": str(u.id),
                    "name": "%s (%s)" % (u.name, tag) if tag else u.name,
                }
            )
        return out

    @api.model
    def get_tab2(self):
        """OWL gọi lúc mở màn: nạp ma trận + danh sách người duyệt + quyền sửa.
        (Audit dùng chung, đã nạp ở get_tab1.)"""
        cfg = self._get_singleton()
        cfg._ensure_default_levels()
        return {
            "levels": cfg._read_levels(),
            "approvers": self._read_approvers(),
            "canEdit": cfg._can_edit(),
        }

    def _parse_level(self, l):
        """Chuẩn hóa 1 cấp duyệt từ payload OWL → dict field DB (+ _id để khớp
        bản ghi cũ). id là số > 0 ⇒ cấp có sẵn; ngược lại (tmp/None) ⇒ cấp mới."""
        l = l or {}

        def _f(x):
            try:
                return float(x or 0)
            except (TypeError, ValueError):
                return 0.0

        raw_id = l.get("id")
        lid = raw_id if isinstance(raw_id, int) and raw_id > 0 else 0
        role = l.get("role") if l.get("role") in _ROLE_LABELS else "none"
        mode = l.get("mode") if l.get("mode") in _MODE_LABELS else "sequential"
        return {
            "_id": lid,
            "name": (l.get("name") or "Cấp duyệt").strip(),
            "value_min": _f(l.get("vMin")),
            "value_max": _f(l.get("vMax")),  # 0 ⇒ ∞ (không giới hạn trên)
            "discount_min": _f(l.get("dMin")),
            "discount_max": _f(l.get("dMax")),
            "margin_min": _f(l.get("marginMin")),  # 0 ⇒ không áp điều kiện margin
            "approver_role": role,
            "approver_user_id": int(l["user"]) if l.get("user") else False,
            "backup_user_id": int(l["backup"]) if l.get("backup") else False,
            "mode": mode,
            "sla_hours": int(l.get("sla") or 0),
            "note": (l.get("note") or "").strip(),
            "is_active": bool(l.get("active", True)),
            "is_priority": bool(l.get("priority")),
        }

    def _check_overlap(self, parsed):
        """EX-06: chặn cứng khi 2 cấp (đang bật, không phải cấp ưu tiên) trùng
        khoảng giá trị. Một khoảng giá không được thuộc 2 cấp."""
        act = [d for d in parsed if d["is_active"] and not d["is_priority"]]
        bad = set()
        for i in range(len(act)):
            for j in range(i + 1, len(act)):
                a, b = act[i], act[j]
                a_max = a["value_max"] if a["value_max"] > 0 else float("inf")
                b_max = b["value_max"] if b["value_max"] > 0 else float("inf")
                lo = max(a["value_min"], b["value_min"])
                hi = min(a_max, b_max)
                if hi - lo > 0:
                    bad.add(a["name"])
                    bad.add(b["name"])
        if bad:
            raise ValidationError(
                _(
                    "Ngưỡng giá trị chồng chéo giữa các cấp: %s. "
                    "Một khoảng giá không được thuộc 2 cấp — hãy điều chỉnh trước khi lưu."
                )
                % ", ".join(sorted(bad))
            )

    def _diff_levels(self, old_by_id, parsed):
        """So khớp theo id → sinh dòng audit chi tiết (thêm/xóa/sửa từng field/
        đổi thứ tự). Trả về list (param_label, detail)."""
        self.ensure_one()
        Users = self.env["res.users"].sudo()

        def _n(v):
            return _fmt_num(v)

        def _rng(lo, hi):
            hi_s = "∞" if not hi or hi <= 0 else _n(hi)
            return "%s–%s" % (_n(lo), hi_s)

        def _margin(m):
            return "—" if not m or m <= 0 else _n(m)

        def snap_old(lv):
            return {
                "name": lv.name or "",
                "value": _rng(lv.value_min, lv.value_max),
                "discount": _rng(lv.discount_min, lv.discount_max),
                "margin": _margin(lv.margin_min),
                "role": _ROLE_LABELS.get(lv.approver_role, lv.approver_role),
                "user": lv.approver_user_id.name or "(Theo vai trò)",
                "backup": lv.backup_user_id.name or "(Chưa gán)",
                "mode": _MODE_LABELS.get(lv.mode, lv.mode),
                "sla": _n(lv.sla_hours),
                "active": _bool_label(lv.is_active),
                "priority": _bool_label(lv.is_priority),
                "note": lv.note or "",
            }

        def snap_new(d):
            return {
                "name": d["name"],
                "value": _rng(d["value_min"], d["value_max"]),
                "discount": _rng(d["discount_min"], d["discount_max"]),
                "margin": _margin(d["margin_min"]),
                "role": _ROLE_LABELS.get(d["approver_role"], d["approver_role"]),
                "user": (
                    Users.browse(d["approver_user_id"]).name
                    if d["approver_user_id"]
                    else "(Theo vai trò)"
                ),
                "backup": (
                    Users.browse(d["backup_user_id"]).name
                    if d["backup_user_id"]
                    else "(Chưa gán)"
                ),
                "mode": _MODE_LABELS.get(d["mode"], d["mode"]),
                "sla": _n(d["sla_hours"]),
                "active": _bool_label(d["is_active"]),
                "priority": _bool_label(d["is_priority"]),
                "note": d["note"],
            }

        audit = []
        seen = set()
        for d in parsed:
            lid = d["_id"]
            if lid and lid in old_by_id:
                seen.add(lid)
                o, n = snap_old(old_by_id[lid]), snap_new(d)
                for key, label in _TAB2_FIELD_LABELS:
                    if o[key] != n[key]:
                        audit.append(
                            (n["name"] or o["name"], "%s: %s → %s" % (label, o[key], n[key]))
                        )
            else:
                audit.append((d["name"], "Thêm cấp duyệt"))

        for lid, lv in old_by_id.items():
            if lid not in seen:
                audit.append((lv.name or "(không tên)", "Xóa cấp duyệt"))

        # Đổi thứ tự giữa các cấp còn giữ lại
        old_order = [lv.id for lv in self.level_ids if lv.id in seen]
        new_order = [d["_id"] for d in parsed if d["_id"] in seen]
        if len(old_order) > 1 and old_order != new_order:
            audit.append(("Ma trận phê duyệt", "Thay đổi thứ tự các cấp duyệt"))

        return audit

    @api.model
    def save_tab2(self, levels):
        """OWL gọi khi Lưu ma trận: validate chồng chéo (chặn cứng) → diff audit
        → ghi DB (incremental, giữ pending_count). Trả về ma trận chuẩn + audit."""
        cfg = self._get_singleton()
        if not cfg._can_edit():
            raise AccessError(_("Chỉ Admin/CEO được sửa ma trận phê duyệt."))

        parsed = [cfg._parse_level(l) for l in (levels or [])]
        cfg._check_overlap(parsed)  # EX-06 — ValidationError nếu chồng chéo

        old_by_id = {lv.id: lv for lv in cfg.level_ids}
        keep_ids = {d["_id"] for d in parsed if d["_id"]}

        # Không cho xóa vĩnh viễn cấp đang có báo giá chờ duyệt (chỉ được tắt).
        for lid, lv in old_by_id.items():
            if lid not in keep_ids and lv.pending_count > 0:
                raise ValidationError(
                    _(
                        'Không thể xóa cấp "%s" đang có %d báo giá chờ duyệt — '
                        "chỉ được vô hiệu hóa."
                    )
                    % (lv.name, lv.pending_count)
                )

        # Diff audit TRƯỚC khi ghi (còn giá trị cũ trong old_by_id).
        audit = cfg._diff_levels(old_by_id, parsed)

        # Ghi incremental: (1) sửa cấp cũ, (0) tạo cấp mới, (2) xóa cấp bỏ đi.
        # pending_count không nằm trong vals ⇒ giữ nguyên khi update.
        commands, seq = [], 0
        for d in parsed:
            vals = {k: v for k, v in d.items() if k != "_id"}
            vals["sequence"] = seq
            seq += 10
            lid = d["_id"]
            if lid and lid in old_by_id:
                commands.append((1, lid, vals))
            else:
                commands.append((0, 0, vals))
        for lid in old_by_id:
            if lid not in keep_ids:
                commands.append((2, lid))
        cfg.write({"level_ids": commands})

        # Audit ghi sudo (append-only, người dùng không cần quyền create)
        Log = self.env["dl.config.audit.log"].sudo()
        created = (
            Log.create(
                [
                    {
                        "config_tab": "Ma trận phê duyệt",
                        "param_label": label,
                        "detail": detail,
                        "user_id": self.env.uid,
                    }
                    for label, detail in audit
                ]
            )
            if audit
            else Log.browse()
        )

        return {
            "levels": cfg._read_levels(),
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


class DlApprovalLevel(models.Model):
    _name = "dl.approval.level"
    _description = "Cấp duyệt trong Ma trận phê duyệt (S02 · Tab 2)"
    _order = "sequence, id"

    config_id = fields.Many2one(
        "dl.pricing.config", "Cấu hình", ondelete="cascade", required=True
    )
    sequence = fields.Integer("Thứ tự", default=10)
    name = fields.Char("Tên cấp duyệt", required=True)

    # Điều kiện kích hoạt: giá trị (triệu VNĐ) và chiết khấu (%).
    # value_max ≤ 0 ⇒ không giới hạn trên (∞); margin_min ≤ 0 ⇒ không áp margin.
    value_min = fields.Float("Giá trị từ (triệu)", default=0.0)
    value_max = fields.Float("Giá trị đến (triệu)", default=0.0)
    discount_min = fields.Float("Chiết khấu từ (%)", default=0.0)
    discount_max = fields.Float("Chiết khấu đến (%)", default=100.0)
    margin_min = fields.Float("Margin tối thiểu (%)", default=0.0)

    approver_role = fields.Selection(
        [
            ("none", "Không cần duyệt"),
            ("sales_manager", "Trưởng KD"),
            ("ceo", "CEO"),
            ("custom", "Vai trò tùy chỉnh"),
        ],
        "Vai trò duyệt",
        default="sales_manager",
        required=True,
    )
    # Người duyệt cụ thể / Backup — tùy chọn, gán đích danh user (S01).
    approver_user_id = fields.Many2one("res.users", "Người duyệt cụ thể")
    backup_user_id = fields.Many2one(
        "res.users",
        "Người duyệt thay thế",
        help="Người thay thế khi người duyệt chính vắng mặt hoặc quá hạn xử lý.",
    )

    mode = fields.Selection(
        [
            ("sequential", "Tuần tự"),
            ("parallel", "Song song"),
            ("direct", "Trực tiếp"),
            ("none", "—"),
        ],
        "Kiểu duyệt",
        default="sequential",
        required=True,
    )
    sla_hours = fields.Integer("SLA (giờ)", default=4)
    note = fields.Char("Ghi chú nội bộ")

    # KHÔNG dùng tên field 'active' để tránh Odoo tự ẩn record inactive khỏi
    # One2many (active_test) — cấp bị tắt vẫn phải hiển thị trong ma trận.
    is_active = fields.Boolean("Kích hoạt", default=True)
    is_priority = fields.Boolean(
        "Cấp ưu tiên", default=False,
        help="Cấp điều kiện đặc biệt (vd margin thấp → CEO trực tiếp); "
        "không tính vào kiểm tra chồng chéo ngưỡng.",
    )
    # Số báo giá đang chờ duyệt ở cấp này — trạng thái runtime do S10 cập nhật,
    # KHÔNG sửa qua màn cấu hình. Dùng để chặn xóa cấp đang có việc.
    pending_count = fields.Integer("Số BG chờ duyệt", default=0, readonly=True)


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
