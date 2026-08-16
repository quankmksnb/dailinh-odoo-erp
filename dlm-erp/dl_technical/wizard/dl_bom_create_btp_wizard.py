from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlBomCreateBtpWizard(models.TransientModel):
    """§13.1 — Wizard "Thêm bán thành phẩm vào định mức".

    Biến việc tạo BTP + BOM con thành MỘT hành động bậc nhất trên dòng BOM (§3.3-A),
    thay cho 3 bước rời rạc "sang menu Vật tư tạo BTP → sang màn BOM tạo BOM con →
    quay lại BOM cha chọn vào dòng". Modal 1 bước gọn: tạo BTP (Nháp, tạm theo cha
    nếu cha là bản tạm RFQ) + BOM con Nháp + 1 dòng vào BOM cha, rồi đẩy form BOM
    con lên breadcrumb để KTV nhập vật tư ngay (một mạch, không rời màn thủ công).
    """

    _name = "dl.bom.create.btp.wizard"
    _description = "Thêm bán thành phẩm vào định mức"

    bom_id = fields.Many2one(
        "dl.bom", string="Định mức cha", required=True, readonly=True,
        ondelete="cascade")

    name = fields.Char(string="Tên bán thành phẩm", required=True)

    # BTP thuộc nhánh Vật tư (nhóm "Bán thành phẩm" hoặc nhóm vật tư kỹ thuật khác).
    category_id = fields.Many2one(
        "product.category", string="Nhóm (Vật tư)", required=True,
        domain=[("dl_branch", "=", "material")])

    quantity = fields.Float(
        string="Số lượng dùng trong định mức cha", default=1.0, required=True)

    # M9 — phân biệt BTP THẬT (tự nằm trong kho, tái dùng cho đơn khác) với
    # "cắt vật tư theo khổ của đơn này". BTP có BOM riêng, nên đẻ một BTP cho mỗi
    # khổ là đường nổ dữ liệu nhanh nhất: 10 cỡ × 4 bộ phận = 40 BTP + 40 BOM.
    # Cảnh báo MỀM (không chặn) — Kỹ thuật vẫn có thể có lý do chính đáng.
    will_be_stocked = fields.Boolean(
        string="Bán thành phẩm này nhập kho & dùng lại cho đơn khác")

    init_mode = fields.Selection(
        [
            ("empty", "Tạo trống"),
            ("copy", "Chép từ bán thành phẩm tương tự"),
        ],
        string="Định mức bán thành phẩm", default="empty", required=True)
    copy_from_bom_id = fields.Many2one(
        "dl.bom", string="Chép định mức từ",
        domain="[('product_id.product_kind', '=', 'material_processed'),"
               " ('status', 'in', ('confirmed', 'locked'))]",
        help="Chép các dòng vật tư của một bán thành phẩm tương tự làm điểm khởi đầu.")

    # Cảnh báo mềm khi cha là bản tạm RFQ — BTP sẽ kế thừa trạng thái tạm.
    parent_is_provisional = fields.Boolean(
        related="bom_id.is_rfq_provisional", readonly=True)

    # ── Soi trùng/gần giống tên BTP (tái dùng _dlm_find_name_matches, §3.3-A#3) ──
    name_dup_state = fields.Selection(
        [("none", "Không trùng"), ("exact", "Trùng hệt"), ("similar", "Gần giống")],
        string="Kết quả soi trùng tên", compute="_compute_name_dup")
    name_dup_message = fields.Char(
        string="Cảnh báo trùng tên", compute="_compute_name_dup")
    name_dup_exact_id = fields.Many2one(
        "product.product", string="Bán thành phẩm trùng hệt", compute="_compute_name_dup")
    confirm_similar_name = fields.Boolean(
        string="Xác nhận đây thực sự là bán thành phẩm khác")

    @api.depends("name")
    def _compute_name_dup(self):
        Product = self.env["product.product"]
        for rec in self:
            rec.name_dup_state = "none"
            rec.name_dup_message = False
            rec.name_dup_exact_id = False
            if not rec.name:
                continue
            matches = Product._dlm_find_name_matches(
                rec.name, kinds=("material_processed",),
                extra_domain=[("is_rfq_provisional", "=", False)])
            if matches["exact"]:
                dup = matches["exact"][0]
                rec.name_dup_state = "exact"
                rec.name_dup_exact_id = dup.id
                rec.name_dup_message = _(
                    "Đã có bán thành phẩm “%(name)s” (nhóm %(categ)s). Không "
                    "tạo trùng — hãy chọn bán thành phẩm này vào dòng.",
                    name=dup.display_name,
                    categ=dup.categ_id.display_name or _("chưa phân nhóm"))
            elif matches["similar"]:
                rec.name_dup_state = "similar"
                names = ", ".join(matches["similar"][:5].mapped("display_name"))
                rec.name_dup_message = _(
                    "Có bán thành phẩm gần giống: %s. Nếu đây thực sự là bán "
                    "thành phẩm khác, tick xác nhận bên dưới rồi bấm Tạo."
                ) % names

    def action_create(self):
        """Tạo BTP + BOM con + 1 dòng vào định mức cha, mở BOM con trên breadcrumb."""
        self.ensure_one()
        parent = self.bom_id
        if parent.status != "draft":
            raise UserError(_(
                "Chỉ thêm bán thành phẩm khi định mức cha còn ở trạng thái Nháp."))

        name = " ".join((self.name or "").split())
        if not name:
            raise UserError(_("Vui lòng nhập tên bán thành phẩm."))

        # Soi trùng LẠI lúc bấm (không tin state đã compute) — trùng hệt chặn cứng,
        # gần giống đòi tick xác nhận (như luồng SP gia công của wizard RFQ).
        Product = self.env["product.product"]
        matches = Product._dlm_find_name_matches(
            name, kinds=("material_processed",),
            extra_domain=[("is_rfq_provisional", "=", False)])
        if matches["exact"]:
            dup = matches["exact"][0]
            raise UserError(_(
                "Đã tồn tại bán thành phẩm “%(name)s” (nhóm %(categ)s). Không "
                "tạo trùng — hãy chọn bán thành phẩm này vào dòng định mức.",
                name=dup.display_name,
                categ=dup.categ_id.display_name or _("chưa phân nhóm")))
        if matches["similar"] and not self.confirm_similar_name:
            names = ", ".join(matches["similar"][:5].mapped("display_name"))
            raise UserError(_(
                "Có bán thành phẩm gần giống: %s.\nNếu đây thực sự là bán thành "
                "phẩm khác, hãy tick “Xác nhận đây thực sự là bán thành phẩm "
                "khác” rồi tạo lại.") % names)

        # BTP kế thừa trạng thái tạm từ định mức cha: cha tạm RFQ ⇒ BTP + BOM con
        # cũng tạm (bị cron dọn nếu RFQ bỏ dở; chính thức hóa khi Hoàn tất dòng).
        provisional = parent.is_rfq_provisional
        source_line = parent.rfq_source_line_id.id if provisional else False

        product = Product.create({
            "name": name,
            "categ_id": self.category_id.id,
            "product_kind": "material_processed",
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": provisional,
            "rfq_source_line_id": source_line,
        })

        # §12.2-C — BOM của một BTP là ĐỊNH MỨC CHUẨN tái dùng (không phải instance
        # một đơn) ⇒ bom_type='template'; được is_current khi confirm và khớp bước
        # (1) của _standard_child_bom.
        Bom = self.env["dl.bom"]
        child_vals = {
            "product_id": product.id,
            "bom_type": "template",
            "status": "draft",
            "is_rfq_provisional": provisional,
            "rfq_source_line_id": source_line,
        }
        if self.init_mode == "copy" and self.copy_from_bom_id:
            child_vals["line_ids"] = [
                (0, 0, self._copy_line_vals(line))
                for line in self.copy_from_bom_id.line_ids
            ]
        child = Bom.create(child_vals)

        # Thêm 1 dòng vào định mức cha trỏ BTP vừa tạo (uom_id/waste tự tính).
        self.env["dl.bom.line"].create({
            "bom_id": parent.id,
            "material_id": product.id,
            "quantity": self.quantity or 1.0,
        })

        # Mở form BOM con full-page trên breadcrumb (giữ định mức cha phía sau) để
        # KTV nhập vật tư ngay — một mạch, không "hai cửa".
        view = self.env.ref("dl_technical.view_dl_bom_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Định mức của %s") % product.display_name,
            "res_model": "dl.bom",
            "res_id": child.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }

    def _copy_line_vals(self, line):
        """Chép 1 dòng từ BTP tương tự. Tính TAY quantity/waste (onchange KHÔNG
        chạy khi tạo qua ORM — bẫy G1/W3): giữ nguyên số của bản gốc là đúng."""
        vals = line._mixin_copy_vals()
        return vals
