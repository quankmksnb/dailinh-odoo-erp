# -*- coding: utf-8 -*-
"""Ma trận phê duyệt báo giá theo giá trị (đặc tả V3 mục 1–4, 9, 10).

Ma trận xác định người phê duyệt cuối cùng cho một báo giá dựa trên **tổng giá
bán sau chiết khấu, trước VAT**. Mỗi dòng chỉ là một ngưỡng tiền và một cấp
duyệt; hệ thống tự suy ra khoảng tiền từ ngưỡng kế tiếp nên KHÔNG có "giá trị
đến". Đây là cấu hình tối giản cho doanh nghiệp gia công sắt thép nhỏ:

* Không công thức điều kiện tự do, không nhiều tầng, không nhiều phạm vi.
* Mỗi báo giá chỉ chuyển tới MỘT cấp duyệt cuối — lấy cấp cao nhất khi nhiều
  điều kiện cùng phát sinh (giá trị / chiết khấu / giá sàn).

Vòng đời (revision, Áp dụng, Ngừng áp dụng, bảo toàn snapshot) tái dùng
``dl.pricing.rule.mixin``. Điểm khác biệt so với các quy tắc khác: NHIỀU dòng
ma trận cùng "Đang áp dụng" song song để tạo thành thang ngưỡng — nên "đối
tượng" để chống chồng lấn là *cùng một ngưỡng giá trị*, không phải toàn công ty.
"""

from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .pricing_rule import TECH_STATE_SELECTION

# Cấp duyệt = vai trò người duyệt. DN nhỏ chỉ có đúng hai cấp thương mại; thêm
# "Không cần duyệt" cho bậc giá trị thấp (vd 0–20 triệu) — đúng ví dụ đặc tả mục 3.
# rank dùng để so "cấp cao nhất" khi một báo giá phát sinh nhiều điều kiện.
APPROVAL_LEVEL_SELECTION = [
    ("none", "Không cần duyệt"),
    ("sales_manager", "Trưởng kinh doanh"),
    ("ceo", "Giám đốc"),
]
_LEVEL_RANK = {"none": 0, "sales_manager": 1, "ceo": 2}
_ROLE_GROUP = {
    "sales_manager": "dl_base.dl_group_sales_manager",
    "ceo": "dl_base.dl_group_ceo",
}


def _fmt_money(currency, amount):
    """Định dạng số tiền kiểu Việt Nam: 20.000.001 ₫."""
    txt = "{:,.0f}".format(amount or 0.0).replace(",", ".")
    return "%s %s" % (txt, currency.symbol) if currency else txt


class DlPricingApprovalMatrix(models.Model):
    _name = "dl.pricing.approval.matrix"
    _description = "Ma trận phê duyệt báo giá theo giá trị"
    _inherit = ["dl.pricing.rule.mixin"]
    _order = "value_from asc, revision desc, id desc"
    _rec_name = "name"

    name = fields.Char("Tên", compute="_compute_name", store=True)
    value_from = fields.Monetary(
        "Ngưỡng giá trị từ", required=True, currency_field="currency_id",
        tracking=True,
        help="Áp dụng cho báo giá có giá trị xét duyệt (sau chiết khấu, trước "
             "VAT) từ mức này trở lên, cho tới ngưỡng kế tiếp.",
    )
    currency_id = fields.Many2one(
        "res.currency", string="Tiền tệ",
        related="company_id.currency_id", store=True, readonly=True,
    )
    approval_level = fields.Selection(
        APPROVAL_LEVEL_SELECTION, string="Cấp duyệt / Vai trò", required=True,
        default="sales_manager", tracking=True,
        help="Cấp phê duyệt cuối cùng cho khoảng giá trị này.",
    )
    level_rank = fields.Integer(
        "Thứ bậc", compute="_compute_level_rank", store=True,
        help="Dùng nội bộ để chọn cấp duyệt cao nhất.",
    )
    approver_user_id = fields.Many2one(
        "res.users", string="Người duyệt cụ thể",
        help="Không bắt buộc. Để trống thì mọi người thuộc vai trò trên đều "
             "có thể duyệt.",
    )
    note = fields.Char("Ghi chú")
    # Ma trận là cấu hình kỹ thuật do Giám đốc/Admin quản lý — áp dụng ngay,
    # không cần luồng phê duyệt thương mại. Trạng thái: Nháp / Đang áp dụng /
    # Ngừng áp dụng (mục 3).
    state = fields.Selection(
        TECH_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )
    # Bản Nháp đã được TrKD "Gửi duyệt" thì có một yêu cầu đang chờ — khóa sửa
    # cho tới khi Giám đốc xử lý (duyệt = kích hoạt, từ chối = trả về Nháp).
    pending_request_id = fields.Many2one(
        "dl.pricing.approval.request", string="Đề xuất chờ duyệt",
        compute="_compute_pending_request",
    )
    has_pending_request = fields.Boolean(
        "Đang chờ duyệt", compute="_compute_pending_request",
    )
    # Bản gốc của một bản Sửa đổi — để khi áp dụng bản mới thì dòng gốc tự
    # ngừng KỂ CẢ khi người dùng đã đổi mức tiền (khác value_from).
    revised_from_id = fields.Many2one(
        "dl.pricing.approval.matrix", string="Sửa đổi từ",
        readonly=True, copy=False, ondelete="set null",
    )

    def _compute_pending_request(self):
        for rec in self:
            req = rec._pending_requests()[:1]
            rec.pending_request_id = req
            rec.has_pending_request = bool(req)

    def _pending_requests(self):
        """Yêu cầu đang chờ duyệt của các dòng này — search trực tiếp (không
        qua field computed vì giá trị đó bị cache trong cùng transaction)."""
        return self.env["dl.pricing.approval.request"].sudo().search([
            ("res_model", "=", self._name), ("res_id", "in", self.ids),
            ("state", "=", "pending"),
        ])

    @api.depends("value_from", "approval_level", "revision", "currency_id")
    def _compute_name(self):
        labels = dict(APPROVAL_LEVEL_SELECTION)
        for rec in self:
            rec.name = _("Từ %(amount)s → %(level)s (b%(rev)s)") % {
                "amount": _fmt_money(rec.currency_id, rec.value_from),
                "level": labels.get(rec.approval_level, ""),
                "rev": rec.revision,
            }

    @api.depends("approval_level")
    def _compute_level_rank(self):
        for rec in self:
            rec.level_rank = _LEVEL_RANK.get(rec.approval_level, 0)

    # ------------------------------------------------------------------
    # Phân quyền thao tác (bảng phân quyền màn Ma trận):
    # * Trưởng KD được ĐỀ XUẤT — tạo/sửa/xóa bản Nháp, tạo bản Sửa đổi.
    # * Chỉ Giám đốc/Admin được Nhập cấu hình tự do và Kích hoạt/Ngừng
    #   (bấm Áp dụng trên bản đề xuất = phê duyệt thay đổi).
    # ------------------------------------------------------------------
    def _is_matrix_manager(self):
        """CEO/Admin — người được kích hoạt/ngừng và sửa mọi trạng thái."""
        return (self.env.su or self.env.uid == SUPERUSER_ID
                or self.env.user.has_group("dl_base.dl_group_ceo")
                or self.env.user.has_group("dl_base.dl_group_admin"))

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_matrix_manager():
            for vals in vals_list:
                if vals.get("state", "draft") != "draft":
                    raise AccessError(_(
                        "Bạn chỉ được tạo bản đề xuất (Nháp). Việc kích hoạt do "
                        "Giám đốc/Admin thực hiện."
                    ))
        return super().create(vals_list)

    def write(self, vals):
        if (not self._is_matrix_manager()
                and not self.env.context.get("pricing_system_write")):
            if "state" in vals:
                raise AccessError(_(
                    "Chỉ Giám đốc/Admin được kích hoạt hoặc ngừng áp dụng "
                    "dòng ma trận."
                ))
            non_draft = self.filtered(lambda r: r.state != "draft")
            if non_draft:
                raise AccessError(_(
                    "Bạn chỉ được sửa bản đề xuất (Nháp). Muốn thay đổi dòng "
                    "'%s' đang áp dụng, hãy dùng \"Sửa đổi\" để tạo bản đề xuất."
                ) % non_draft[0].display_name)
        if not self.env.su and self.env.uid != SUPERUSER_ID \
                and not self.env.context.get("pricing_system_write"):
            # Bản đề xuất đang chờ duyệt: khóa nội dung để Giám đốc duyệt đúng
            # cái đã gửi. Muốn sửa thì chờ kết quả hoặc nhờ từ chối để mở lại.
            pending = self._pending_requests()
            if pending:
                raise UserError(_(
                    "Dòng '%s' đang có đề xuất chờ Giám đốc duyệt nên tạm khóa "
                    "sửa. Hãy chờ kết quả, hoặc nhờ Giám đốc Từ chối để sửa lại."
                ) % pending[0].object_label)
        # Chặn tự sửa hạn mức của bản thân: người duyệt cụ thể của một dòng
        # ĐANG ÁP DỤNG không được tự thay đổi dòng đó.
        if not self.env.su and self.env.uid != SUPERUSER_ID \
                and not self.env.context.get("pricing_system_write"):
            own = self.filtered(
                lambda r: r.state == "active"
                and r.approver_user_id.id == self.env.uid)
            if own:
                raise ValidationError(_(
                    "Bạn là người duyệt của dòng '%s' nên không được tự sửa "
                    "hạn mức này. Hãy nhờ Giám đốc/Admin khác thao tác."
                ) % own[0].display_name)
        return super().write(vals)

    def unlink(self):
        if not self._is_matrix_manager():
            if self.filtered(lambda r: r.state != "draft"):
                raise AccessError(_(
                    "Bạn chỉ được xóa bản đề xuất (Nháp)."
                ))
        if not self.env.su and self.env.uid != SUPERUSER_ID:
            pending = self._pending_requests()
            if pending:
                raise UserError(_(
                    "Dòng '%s' đang có đề xuất chờ duyệt — không thể xóa. Hãy "
                    "nhờ Giám đốc Từ chối trước."
                ) % pending[0].object_label)
        return super().unlink()

    # ------------------------------------------------------------------
    # Đối tượng chống chồng lấn: cùng một ngưỡng giá trị
    # ------------------------------------------------------------------
    def _target_domain(self):
        self.ensure_one()
        # Nhiều ngưỡng khác nhau cùng active để tạo thang; chỉ đóng bản cũ khi
        # tạo revision mới CHO CÙNG một ngưỡng.
        return [("value_from", "=", self.value_from)]

    # ------------------------------------------------------------------
    # Validation (mục 10)
    # ------------------------------------------------------------------
    @api.constrains("value_from")
    def _check_value_from(self):
        for rec in self:
            if rec.value_from < 0:
                raise ValidationError(_("Ngưỡng giá trị không được âm."))

    @api.constrains("approver_user_id", "approval_level")
    def _check_approver_in_role(self):
        """Người duyệt cụ thể phải thuộc đúng nhóm vai trò của cấp duyệt —
        tránh chỉ định người không có quyền đọc/duyệt báo giá (họ sẽ kẹt khi
        xử lý yêu cầu)."""
        for rec in self:
            if not rec.approver_user_id or rec.approval_level not in _ROLE_GROUP:
                continue
            group = self.env.ref(_ROLE_GROUP[rec.approval_level],
                                 raise_if_not_found=False)
            if group and rec.approver_user_id not in group.users:
                raise ValidationError(_(
                    "Người duyệt '%(user)s' không thuộc vai trò '%(level)s'. "
                    "Hãy chọn người trong đúng nhóm hoặc để trống."
                ) % {
                    "user": rec.approver_user_id.name,
                    "level": dict(APPROVAL_LEVEL_SELECTION).get(rec.approval_level),
                })

    @api.constrains("value_from", "state", "company_id")
    def _check_unique_threshold(self):
        """Không cho hai dòng đang áp dụng có cùng ngưỡng bắt đầu (mục 10)."""
        for rec in self:
            if rec.state != "active":
                continue
            twin = self.search([
                ("id", "!=", rec.id),
                ("state", "=", "active"),
                ("company_id", "=", rec.company_id.id),
                ("value_from", "=", rec.value_from),
            ], limit=1)
            if twin:
                raise ValidationError(_(
                    "Đã có một dòng ma trận đang áp dụng với cùng ngưỡng %s. "
                    "Mỗi ngưỡng chỉ được có một cấp duyệt."
                ) % _fmt_money(rec.currency_id, rec.value_from))

    def _assert_fits_ladder(self):
        """Dòng này (coi như sẽ áp dụng) phải khớp thang hiện tại: cấp duyệt
        TĂNG DẦN THẬT SỰ theo ngưỡng. Chặn hai kiểu cấu hình xấu:

        * Rối logic — cấp GIẢM khi giá trị tăng (20tr → Giám đốc nhưng
          100tr → Trưởng KD).
        * Ngưỡng thừa — cấp LẶP LẠI (2tr → TrKD đã có mà thêm 5tr → TrKD):
          không đổi ai duyệt cái gì, chỉ làm loãng cấu hình. Mỗi cấp duyệt
          chỉ cần đúng một ngưỡng bắt đầu ⇒ thang tối đa 3 dòng đang áp dụng.

        Dùng chung cho constraint khi kích hoạt và kiểm tra SỚM lúc Gửi duyệt
        (đề xuất xấu bị chặn ngay, không làm loãng hàng chờ của Giám đốc).
        """
        self.ensure_one()
        labels = dict(APPROVAL_LEVEL_SELECTION)
        others = self.search([
            ("id", "not in", self.ids + self.revised_from_id.ids),
            ("state", "=", "active"),
            ("company_id", "=", self.company_id.id),
            ("value_from", "!=", self.value_from),
        ])
        for other in others:
            lower, higher = ((self, other) if self.value_from < other.value_from
                             else (other, self))
            if lower.level_rank > higher.level_rank:
                raise ValidationError(_(
                    "Thang phê duyệt bị rối logic: ngưỡng %(low_amt)s cần "
                    "'%(low_level)s' duyệt nhưng ngưỡng cao hơn %(high_amt)s "
                    "lại chỉ cần '%(high_level)s'. Giá trị càng lớn thì cấp "
                    "duyệt phải cao hơn — hãy sửa lại cấp duyệt của một trong "
                    "hai ngưỡng."
                ) % {
                    "low_amt": _fmt_money(lower.currency_id, lower.value_from),
                    "low_level": labels.get(lower.approval_level, ""),
                    "high_amt": _fmt_money(higher.currency_id, higher.value_from),
                    "high_level": labels.get(higher.approval_level, ""),
                })
            if lower.level_rank == higher.level_rank:
                raise ValidationError(_(
                    "Ngưỡng %(high_amt)s là thừa: từ %(low_amt)s trở lên đã do "
                    "'%(level)s' duyệt rồi. Mỗi cấp duyệt chỉ cần một ngưỡng "
                    "bắt đầu — muốn đổi mức tiền hãy dùng \"Sửa đổi\" trên dòng "
                    "%(low_amt)s, muốn thêm bậc mới hãy chọn cấp duyệt cao hơn."
                ) % {
                    "high_amt": _fmt_money(higher.currency_id, higher.value_from),
                    "low_amt": _fmt_money(lower.currency_id, lower.value_from),
                    "level": labels.get(lower.approval_level, ""),
                })

    @api.constrains("value_from", "approval_level", "state", "company_id")
    def _check_level_monotonic(self):
        """Chỉ xét các dòng đang áp dụng vì chúng mới tạo thành thang."""
        for rec in self:
            if rec.state == "active":
                rec._assert_fits_ladder()

    def action_apply(self):
        """Kích hoạt dòng ma trận (mục 10).

        Chặn nếu thiếu vai trò người duyệt; với bản sửa đổi (revision > 1) bắt
        buộc có lý do thay đổi (mục 9).
        """
        if not self._is_matrix_manager():
            raise AccessError(_(
                "Chỉ Giám đốc/Admin được kích hoạt dòng ma trận. Bản đề xuất "
                "của bạn sẽ được cấp có thẩm quyền xem xét và Áp dụng."
            ))
        for rec in self:
            if not rec.approval_level:
                raise ValidationError(_(
                    "Không thể kích hoạt ma trận khi chưa chọn cấp duyệt / vai "
                    "trò người duyệt."
                ))
            # Không tự kích hoạt hạn mức mà chính mình là người duyệt cụ thể.
            if (rec.approver_user_id.id == self.env.uid
                    and not self.env.su and self.env.uid != SUPERUSER_ID):
                raise ValidationError(_(
                    "Bạn là người duyệt được chỉ định của ngưỡng này nên không "
                    "được tự kích hoạt. Hãy nhờ Giám đốc/Admin khác thao tác."
                ))
            if rec.revision > 1 and not rec.change_reason:
                raise ValidationError(_(
                    "Bắt buộc nhập lý do thay đổi cho bản sửa đổi của ma trận."
                ))
            # Chặn tạo MỚI một dòng trùng ngưỡng đang áp dụng (mục 10). Muốn đổi
            # cấp duyệt của một ngưỡng thì dùng "Sửa đổi" (revision) trên đúng
            # dòng đó — khi đó revision > 1 và bản cũ được tự đóng.
            if rec.revision == 1:
                twin = self.search([
                    ("id", "!=", rec.id),
                    ("state", "=", "active"),
                    ("company_id", "=", rec.company_id.id),
                    ("value_from", "=", rec.value_from),
                ], limit=1)
                if twin:
                    raise ValidationError(_(
                        "Đã có một dòng ma trận đang áp dụng với ngưỡng %s. Hãy "
                        "dùng \"Sửa đổi\" trên dòng đó thay vì tạo dòng trùng ngưỡng."
                    ) % _fmt_money(rec.currency_id, rec.value_from))
        res = super().action_apply()
        for rec in self:
            # "Không nên" mềm: người kích hoạt thuộc chính cấp duyệt của ngưỡng
            # (tự đặt hạn mức cho vai trò mình) — không chặn, ghi nhận kiểm toán.
            group_xmlid = _ROLE_GROUP.get(rec.approval_level)
            if group_xmlid and self.env.user.has_group(group_xmlid):
                rec.message_post(body=_(
                    "⚠️ Người kích hoạt thuộc chính cấp duyệt của ngưỡng này "
                    "(tự đặt hạn mức cho vai trò mình). Đã ghi nhận."
                ))
            # Giám đốc/Admin kích hoạt trực tiếp một bản đã gửi đề xuất: đóng
            # yêu cầu chờ như đã duyệt để không treo ở tab "Chờ duyệt".
            pending = self.env["dl.pricing.approval.request"].sudo().search([
                ("res_model", "=", rec._name), ("res_id", "=", rec.id),
                ("state", "=", "pending"),
                ("request_type", "=", "matrix_config"),
            ])
            if pending:
                pending.write({
                    "state": "approved",
                    "resolved_by_id": self.env.uid,
                    "resolved_at": fields.Datetime.now(),
                })
                pending.message_post(body=_(
                    "Dòng ma trận đã được kích hoạt trực tiếp — yêu cầu được "
                    "đóng như đã duyệt."))
        return res

    def action_expire(self):
        """Ngừng áp dụng — chỉ Giám đốc/Admin (bảng phân quyền màn Ma trận)."""
        if not self._is_matrix_manager():
            raise AccessError(_(
                "Chỉ Giám đốc/Admin được ngừng áp dụng dòng ma trận."
            ))
        return super().action_expire()

    def action_create_revision(self):
        """Bản sửa đổi nhớ dòng gốc — áp dụng bản mới là dòng gốc tự ngừng,
        kể cả khi đã đổi mức tiền (khác ngưỡng)."""
        res = super().action_create_revision()
        self.browse(res["res_id"]).with_context(pricing_system_write=True).write(
            {"revised_from_id": self.id})
        return res

    def _close_previous_active(self):
        """Ngoài bản cùng ngưỡng (mixin), đóng luôn dòng gốc của bản Sửa đổi
        khi người dùng đã đổi value_from — tránh dòng cũ nằm lại làm thang
        có hai ngưỡng cùng cấp."""
        super()._close_previous_active()
        origin = self.revised_from_id
        if origin and origin.state == "active" \
                and origin.value_from != self.value_from:
            close_date = max(self.valid_from - timedelta(days=1), origin.valid_from)
            origin.with_context(pricing_system_write=True).write({
                "state": "expired", "valid_to": close_date,
            })

    # ------------------------------------------------------------------
    # Luồng đề xuất của Trưởng KD: Gửi duyệt → Giám đốc duyệt = kích hoạt
    # ------------------------------------------------------------------
    def _diff_label(self):
        """Mô tả ngắn dễ đọc: 'Ngưỡng 2.000.000 ₫ — Trưởng kinh doanh'."""
        self.ensure_one()
        labels = dict(APPROVAL_LEVEL_SELECTION)
        txt = _("Ngưỡng %(amount)s — %(level)s") % {
            "amount": _fmt_money(self.currency_id, self.value_from),
            "level": labels.get(self.approval_level, ""),
        }
        if self.approver_user_id:
            txt += _(", người duyệt: %s") % self.approver_user_id.name
        return txt

    def _change_summary(self, old):
        """Liệt kê ĐÚNG những gì thay đổi so với bản cũ — Giám đốc nhìn là
        hiểu ngay (vd 'Ngưỡng: 2.000.000 ₫ → 5.000.000 ₫')."""
        self.ensure_one()
        if not old:
            return _("Thêm ngưỡng mới vào thang phê duyệt")
        labels = dict(APPROVAL_LEVEL_SELECTION)
        parts = []
        if old.value_from != self.value_from:
            parts.append(_("Ngưỡng: %(a)s → %(b)s") % {
                "a": _fmt_money(old.currency_id, old.value_from),
                "b": _fmt_money(self.currency_id, self.value_from)})
        if old.approval_level != self.approval_level:
            parts.append(_("Cấp duyệt: %(a)s → %(b)s") % {
                "a": labels.get(old.approval_level, ""),
                "b": labels.get(self.approval_level, "")})
        if old.approver_user_id != self.approver_user_id:
            parts.append(_("Người duyệt cụ thể: %(a)s → %(b)s") % {
                "a": old.approver_user_id.name or _("(theo vai trò)"),
                "b": self.approver_user_id.name or _("(theo vai trò)")})
        return "; ".join(parts) or _("Không thay đổi nội dung chính")

    def action_submit_approval(self):
        """Gửi bản Nháp cho Giám đốc phê duyệt (loại yêu cầu matrix_config).

        Duyệt = dòng tự kích hoạt (qua ``_on_approval_approved``); Từ chối =
        vẫn là Nháp, mở khóa cho người đề xuất sửa tiếp.
        """
        Request = self.env["dl.pricing.approval.request"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(_(
                    "Chỉ gửi duyệt được bản Nháp (bản đề xuất)."
                ))
            # Chặn SỚM đề xuất thừa/rối logic — không làm loãng hàng chờ.
            rec._assert_fits_ladder()
            # Bản cũ để so sánh: dòng gốc của "Sửa đổi" (kể cả khi đã đổi mức
            # tiền), không có thì tìm dòng active cùng ngưỡng.
            origin = rec.revised_from_id
            # Không nhận hai đề xuất cho cùng một ngưỡng.
            other_pending = Request.sudo().search([
                ("request_type", "=", "matrix_config"),
                ("state", "=", "pending"),
                ("company_id", "=", rec.company_id.id),
            ])
            twin = self.sudo().browse(other_pending.mapped("res_id")).exists() \
                .filtered(lambda r: r.id != rec.id
                          and r.value_from == rec.value_from)
            if twin:
                raise UserError(_(
                    "Đã có một đề xuất khác cho ngưỡng %s đang chờ duyệt. Hãy "
                    "chờ Giám đốc xử lý xong trước khi gửi đề xuất mới."
                ) % _fmt_money(rec.currency_id, rec.value_from))
            current = origin or self.search([
                ("state", "=", "active"),
                ("company_id", "=", rec.company_id.id),
                ("value_from", "=", rec.value_from),
            ], limit=1)
            req = Request._open_for(
                "matrix_config", rec,
                old_value=current._diff_label() if current else _("(ngưỡng mới)"),
                new_value=rec._diff_label(),
                impact=rec._change_summary(current),
                reason=rec.change_reason or _(
                    "Đề xuất thang phê duyệt từ %s") % self.env.user.name,
            )
            rec.message_post(body=_(
                "Đã gửi đề xuất chờ Giám đốc phê duyệt (yêu cầu #%s).") % req.id)
        return True

    def _on_approval_approved(self, request):
        """Giám đốc duyệt đề xuất → kích hoạt dòng ma trận ngay."""
        for rec in self:
            if rec.state == "draft":
                rec.action_apply()
                rec.message_post(body=_(
                    "Đề xuất được %s phê duyệt — dòng ma trận đã kích hoạt."
                ) % self.env.user.name)

    def _on_approval_rejected(self, request):
        """Từ chối: giữ Nháp, mở khóa để người đề xuất sửa lại."""
        for rec in self:
            rec.message_post(body=_(
                "Đề xuất bị từ chối bởi %(user)s. Lý do: %(why)s"
            ) % {"user": self.env.user.name,
                 "why": request.reject_comment or ""})

    # ------------------------------------------------------------------
    # Bộ giải ma trận — module báo giá gọi khi Gửi duyệt / Xác nhận (mục 4, 5)
    # ------------------------------------------------------------------
    def _allowed_user_ids(self):
        """Tập user được phép duyệt dòng này."""
        self.ensure_one()
        if self.approval_level == "none":
            return []
        if self.approver_user_id:
            return self.approver_user_id.ids
        group = self.env.ref(_ROLE_GROUP[self.approval_level], raise_if_not_found=False)
        return group.users.ids if group else []

    @api.model
    def _resolve_value_row(self, amount, company=None, date=None):
        """Dòng ma trận áp cho một giá trị báo giá.

        Trả về dòng đang áp dụng có ``value_from`` lớn nhất mà vẫn <= amount.
        Nếu giá trị thấp hơn mọi ngưỡng (vd < 20 triệu) thì không cần duyệt theo
        giá trị → trả về recordset rỗng.
        """
        company = company or self.env.company
        date = date or fields.Date.context_today(self)
        rows = self.search([
            ("state", "=", "active"),
            ("company_id", "=", company.id),
            ("value_from", "<=", amount),
            ("valid_from", "<=", date),
        ], order="value_from desc")
        rows = rows.filtered(lambda r: not r.valid_to or r.valid_to >= date)
        return rows[:1]

    @api.model
    def evaluate_quotation(self, amount, company=None, date=None,
                           discount_above_default=False,
                           discount_above_max=False, below_floor=False):
        """Xác định cấp duyệt cuối cùng cho một báo giá (mục 4).

        Kiểm tra ĐỒNG THỜI ba trục và lấy cấp cao nhất. Trả về dict phục vụ cả
        engine báo giá lẫn thông báo hiển thị (mục 6):

            {
              "required": bool,          # có cần phê duyệt không
              "level": "sales_manager"|"ceo"|False,
              "level_label": str,
              "rank": int,
              "matrix_row_id": int|False, "matrix_revision": int|False,
              "reasons": [str, ...],     # danh sách lý do phát sinh duyệt
            }
        """
        company = company or self.env.company
        candidates = []   # (rank, level, reason)
        matrix_row = self.browse()

        # A. Giá trị báo giá theo ma trận. Bậc "Không cần duyệt" (none) khớp giá
        # trị thấp thì KHÔNG phát sinh duyệt theo giá trị.
        row = self._resolve_value_row(amount, company=company, date=date)
        if row and row.approval_level != "none":
            matrix_row = row
            candidates.append((
                row.level_rank, row.approval_level,
                _("Giá trị trước VAT là %(amount)s, vượt ngưỡng %(threshold)s.") % {
                    "amount": _fmt_money(row.currency_id, amount),
                    "threshold": _fmt_money(row.currency_id, row.value_from),
                },
            ))

        # B. Chiết khấu (chốt 2026-07-27). "Tối đa" của nhóm khách CHÍNH LÀ trần
        # tự-quyết của Sales: deal tới mức tối đa = đã được cho phép sẵn → KHÔNG
        # phát sinh duyệt. "Mặc định" chỉ là mức gợi ý/tự điền, không còn là chốt
        # duyệt. Chỉ VƯỢT tối đa mới cần Trưởng KD duyệt ngoại lệ; giảm sâu tới
        # dưới giá sàn (lỗ) thì lên CEO (mục C) — tạo thang "giảm càng sâu, cấp
        # duyệt càng cao". discount_above_default vẫn nhận để tương thích chữ ký
        # nhưng không dùng để định tuyến.
        if discount_above_max:
            candidates.append((_LEVEL_RANK["sales_manager"], "sales_manager",
                               _("Chiết khấu vượt mức tối đa cho phép của nhóm "
                                 "khách.")))

        # C. Giá sàn — giảm giá tới mức lỗ (dưới giá sàn) luôn cần CEO, dù chiết
        # khấu có nằm trong "tối đa" hay không.
        if below_floor:
            candidates.append((_LEVEL_RANK["ceo"], "ceo",
                               _("Giá bán sau chiết khấu thấp hơn giá sàn.")))

        if not candidates:
            return {
                "required": False, "level": False, "level_label": "",
                "rank": 0, "matrix_row_id": False, "matrix_revision": False,
                "reasons": [],
            }

        top_rank = max(c[0] for c in candidates)
        top_level = next(c[1] for c in candidates if c[0] == top_rank)
        return {
            "required": True,
            "level": top_level,
            "level_label": dict(APPROVAL_LEVEL_SELECTION).get(top_level, ""),
            "rank": top_rank,
            "matrix_row_id": matrix_row.id if matrix_row else False,
            "matrix_revision": matrix_row.revision if matrix_row else False,
            "reasons": [c[2] for c in candidates],
        }
