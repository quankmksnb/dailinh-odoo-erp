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

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

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

    def action_apply(self):
        """Kích hoạt dòng ma trận (mục 10).

        Chặn nếu thiếu vai trò người duyệt; với bản sửa đổi (revision > 1) bắt
        buộc có lý do thay đổi (mục 9).
        """
        for rec in self:
            if not rec.approval_level:
                raise ValidationError(_(
                    "Không thể kích hoạt ma trận khi chưa chọn cấp duyệt / vai "
                    "trò người duyệt."
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
        return super().action_apply()

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

        # B. Chiết khấu.
        if discount_above_max:
            candidates.append((_LEVEL_RANK["ceo"], "ceo",
                               _("Chiết khấu vượt mức tối đa cho phép.")))
        elif discount_above_default:
            candidates.append((_LEVEL_RANK["sales_manager"], "sales_manager",
                               _("Chiết khấu cao hơn mức mặc định.")))

        # C. Giá sàn.
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
