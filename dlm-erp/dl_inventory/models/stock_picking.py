# -*- coding: utf-8 -*-
"""K3–K5 — Phiếu kho: lô tự sinh, truy vết nguồn gốc, và kiểm hàng NCC.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §3.4, §6, §11.3, §11.4.

Nhận hàng đi HAI BƯỚC:

    [1] NH/xxxxx  NCC → Chờ kiểm hàng      thủ kho đếm số NCC giao
    [2] KC/xxxxx  Chờ kiểm → Vật tư & HTM  thủ kho kiểm chất lượng, ghi Đạt/Loại
    [3] TR/xxxxx  Chờ trả NCC → NCC        NHÁP, Mua hàng quyết định

Phiếu [2] là màn quan trọng nhất của phân hệ: nó là chỗ duy nhất phân biệt được
"NCC giao thiếu" với "NCC giao hàng kém" — xem ``stock_move.py``.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

# Mã trình tự của loại hoạt động — neo vào đây thay vì XML ID vì `sequence_code`
# không đổi khi người dùng sửa tên hiển thị (cùng lý do như ir_rule.xml).
_DLM_QC_CODE = "KC"


def _dlm_fmt(qty):
    """Số lượng cho câu thông báo: bỏ số 0 thừa, dấu thập phân kiểu Việt."""
    return ("%g" % qty).replace(".", ",")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ── K5 — Liên kết chứng từ ───────────────────────────────────────────────
    dlm_origin_picking_id = fields.Many2one(
        "stock.picking", string="Phiếu nhận gốc", index=True, copy=False,
        help="Phiếu nhận hàng đã sinh ra phiếu trả NCC này.")
    # Đếm (không phải o2m ngược): phiếu trả neo vào phiếu NHẬN, nên o2m ngược sẽ
    # rỗng khi đang đứng ở phiếu KIỂM — đúng chỗ vừa bấm ra phiếu trả. Một hàm
    # tra chung cho cả hai chặng thay vì hai field nói cùng một chuyện.
    dlm_return_count = fields.Integer(
        string="Số phiếu trả NCC", compute="_compute_dlm_return_count")

    # ── K5 — Trạng thái kiểm hàng ────────────────────────────────────────────
    dlm_is_qc = fields.Boolean(
        string="Là phiếu kiểm hàng", compute="_compute_dlm_is_qc")
    dlm_qty_rejected_total = fields.Float(
        string="Số loại", digits="Product Unit of Measure",
        compute="_compute_dlm_qty_rejected_total", store=True)
    dlm_qc_state = fields.Selection([
        ("none", "—"),
        ("pending", "Chờ kiểm"),
        ("passed", "Đạt toàn bộ"),
        ("has_reject", "Có hàng loại"),
    ], string="Kết quả kiểm", compute="_compute_dlm_qc_state", store=True)

    # ── K5 — Chặn xác nhận + dải thông báo (INLINE, không modal) ─────────────
    dlm_blocked = fields.Boolean(
        string="Đang bị chặn", compute="_compute_dlm_banner")
    dlm_banner_level = fields.Selection([
        ("info", "Thông tin"),
        ("success", "Xong"),
        ("warning", "Cảnh báo"),
        ("danger", "Chặn"),
    ], string="Mức thông báo", compute="_compute_dlm_banner")
    dlm_banner_message = fields.Html(
        string="Thông báo", compute="_compute_dlm_banner", sanitize=False)

    # ── Compute ──────────────────────────────────────────────────────────────
    @api.depends("picking_type_id")
    def _compute_dlm_is_qc(self):
        for picking in self:
            picking.dlm_is_qc = (
                picking.picking_type_id.sequence_code == _DLM_QC_CODE)

    @api.depends("dlm_origin_picking_id", "state", "move_ids")
    def _compute_dlm_return_count(self):
        for picking in self:
            picking.dlm_return_count = len(picking._dlm_vendor_returns())

    @api.depends("move_ids.dlm_qty_rejected")
    def _compute_dlm_qty_rejected_total(self):
        for picking in self:
            picking.dlm_qty_rejected_total = sum(
                picking.move_ids.mapped("dlm_qty_rejected"))

    @api.depends("state", "picking_type_id", "dlm_qty_rejected_total")
    def _compute_dlm_qc_state(self):
        for picking in self:
            if picking.picking_type_id.sequence_code != _DLM_QC_CODE:
                picking.dlm_qc_state = "none"
            elif picking.dlm_qty_rejected_total > 0:
                picking.dlm_qc_state = "has_reject"
            elif picking.state == "done":
                picking.dlm_qc_state = "passed"
            else:
                picking.dlm_qc_state = "pending"

    @api.depends(
        "state", "picking_type_id", "partner_id", "dlm_qty_rejected_total",
        "move_ids.quantity", "move_ids.product_uom_qty", "move_ids.dlm_qc_over",
        "move_ids.dlm_qty_rejected", "move_ids.dlm_reject_reason",
        "move_ids.dlm_reject_note", "move_ids.product_id",
        "move_line_ids.lot_id", "move_line_ids.lot_name")
    def _compute_dlm_banner(self):
        """MỘT dải thông báo theo ngữ cảnh cho cả phiếu nhận lẫn phiếu kiểm.

        Gộp thay vì rải nhiều `<div class="alert">` có điều kiện chồng nhau —
        tiền lệ đã chốt ở form Báo giá (`_compute_status_banner`): mỗi trạng
        thái chỉ được hiện đúng MỘT dải, nội dung do model quyết định.

        Dải phải nêu **hệ quả** ("sẽ tạo phiếu trả nháp cho Mua hàng"), không
        chỉ nêu sự kiện — người dùng cần biết bấm tiếp thì chuyện gì xảy ra.
        """
        for picking in self:
            level, message, blocked = picking._dlm_banner_vals()
            picking.dlm_banner_level = level
            picking.dlm_banner_message = message
            picking.dlm_blocked = blocked

    def _dlm_banner_vals(self):
        """Trả về (mức, nội dung HTML, có chặn xác nhận không)."""
        self.ensure_one()
        if self.state in ("cancel",):
            return False, False, False
        if self.dlm_is_qc:
            return self._dlm_banner_qc()
        if self.picking_type_id.code == "incoming":
            return self._dlm_banner_receipt()
        return False, False, False

    def _dlm_banner_qc(self):
        """Dải cho phiếu [2] Kiểm & cất hàng."""
        if self.state == "done":
            if self.dlm_qty_rejected_total > 0:
                returns = ", ".join(self._dlm_vendor_returns().mapped("name"))
                return "warning", _(
                    "Đã cất hàng đạt vào kho. <b>%s</b> đơn vị hàng loại đang ở "
                    "khu <b>Chờ trả NCC</b>%s — Mua hàng xử lý tiếp với nhà "
                    "cung cấp."
                ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                     _(" (phiếu %s)") % returns if returns else ""), False
            return "success", _("Đã kiểm đạt toàn bộ và cất vào kho."), False

        problems = self._dlm_qc_problems()
        if problems:
            return "danger", _(
                "Chưa xác nhận kiểm được:<ul>%s</ul>"
            ) % "".join("<li>%s</li>" % p for p in problems), True

        if self.dlm_qty_rejected_total > 0:
            return "warning", _(
                "Xác nhận kiểm sẽ chuyển <b>%s</b> đơn vị hàng loại sang khu "
                "<b>Chờ trả NCC</b> và tạo <b>phiếu trả hàng (nháp)</b> để Mua "
                "hàng thoả thuận với %s. Phần đạt được cất vào kho."
            ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                 self.partner_id.display_name or _("nhà cung cấp")), False

        return "info", _(
            "Nhập số <b>Đạt</b> và số <b>Loại</b> cho từng dòng. Chưa kiểm hết "
            "cũng xác nhận được — phần còn lại tự tách sang một phiếu kiểm mới."
        ), False

    def _dlm_banner_receipt(self):
        """Dải cho phiếu [1] Nhận hàng NCC."""
        if self.state == "done":
            return "success", _(
                "Đã nhận hàng vào khu <b>Chờ kiểm hàng</b>. Bước tiếp theo là "
                "<b>kiểm & cất hàng</b>."), False
        if self.state == "draft":
            return False, False, False

        short = []
        for move in self.move_ids:
            rounding = move.product_uom.rounding or 0.01
            if float_compare(move.quantity, move.product_uom_qty,
                             precision_rounding=rounding) < 0:
                short.append(_("%s: thiếu %s %s") % (
                    move.product_id.display_name,
                    _dlm_fmt(move.product_uom_qty - move.quantity),
                    move.product_uom.name))
        if short:
            return "warning", _(
                "NCC giao thiếu so với dự kiến:<ul>%s</ul>Xác nhận sẽ tạo "
                "<b>phiếu chờ giao tiếp</b> cho phần còn thiếu — không phải "
                "hàng lỗi, đừng ghi vào mục Loại ở bước kiểm."
            ) % "".join("<li>%s</li>" % s for s in short), False
        return "info", _(
            "Nhập số thực nhận rồi xác nhận. Số lô do hệ thống tự sinh "
            "(LO/năm/số) — sửa được nếu cần."), False

    def _dlm_qc_problems(self):
        """Danh sách lỗi CỤ THỂ chặn xác nhận kiểm (QC-02/03/04 + thiếu lô).

        Nêu đích danh từng dòng: "thiếu lý do loại" chung chung thì thủ kho phải
        tự dò 20 dòng để tìm chỗ sai.
        """
        self.ensure_one()
        problems = []
        for move in self.move_ids:
            name = move.product_id.display_name
            if move.dlm_qty_rejected < 0:                                # QC-01
                problems.append(_("%s: số loại không được âm.") % name)
            if move.dlm_qc_over:                                         # QC-02
                problems.append(_(
                    "%s: Đạt + Loại = %s, vượt quá %s đang chờ kiểm."
                ) % (name, _dlm_fmt(move.quantity + move.dlm_qty_rejected),
                     _dlm_fmt(move.product_uom_qty)))
            if move.dlm_qty_rejected > 0 and not move.dlm_reject_reason:  # QC-03
                problems.append(_("%s: có hàng loại nhưng chưa chọn lý do.") % name)
            if (move.dlm_reject_reason == "other"
                    and not (move.dlm_reject_note or "").strip()):        # QC-04
                problems.append(_("%s: lý do \"Khác\" phải ghi rõ ở ô ghi chú.") % name)
        problems.extend(
            _("%s: chưa có số lô.") % n for n in self._dlm_lot_missing_names())
        return problems

    def _dlm_lot_missing_names(self):
        """Tên các mặt hàng theo lô mà dòng đã nhập số nhưng chưa gán lô.

        Không có lô thì chuỗi truy vết đứt ngay tại đây: khách báo nứt mối hàn
        sẽ không tra ngược ra được thép của NCC nào.
        """
        self.ensure_one()
        names = set()
        for line in self.move_line_ids:
            if (line.product_id.tracking == "lot"
                    and not float_is_zero(line.quantity, precision_digits=3)
                    and not line.lot_id and not line.lot_name):
                names.add(line.product_id.display_name)
        return sorted(names)

    # ── K5 — Mỗi phiếu nhận sinh ĐÚNG MỘT phiếu kiểm ─────────────────────────
    def action_confirm(self):
        self._dlm_group_receipt_moves()
        return super().action_confirm()

    def _dlm_group_receipt_moves(self):
        """Gắn mỗi phiếu nhận một nhóm cung ứng riêng.

        🔴 Không có bước này, `stock.move._assign_picking` gom MỌI dòng đang chờ
        ở khu Chờ kiểm vào CÙNG MỘT phiếu kiểm (nó khớp theo vị trí + loại hoạt
        động + `group_id`, không khớp theo đối tác). Hậu quả không lỗi nào nổ:
        phiếu kiểm trộn hàng của nhiều NCC, "Từ phiếu"/"Nhà cung cấp" trên form
        chỉ ra một trong số đó, và phiếu trả hàng sinh ra sẽ ghi **SAI NCC** —
        trả nhầm 8 cây thép gỉ cho nhà cung cấp không giao lô đó.

        `group_id` được stock.rule truyền tiếp sang chặng sau, nên đặt ở đây là
        đủ cho cả chuỗi.
        """
        Group = self.env["procurement.group"]
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            moves = picking.move_ids.filtered(lambda move: not move.group_id)
            if not moves:
                continue
            moves.group_id = Group.create({
                "name": picking.name,
                "partner_id": picking.partner_id.id,
            })
        return True

    # ── K3 — Lô tự sinh & đóng dấu nguồn gốc ─────────────────────────────────
    def button_validate(self):
        self._dlm_autofill_lot_names()
        return super().button_validate()

    def _action_done(self):
        """K4 — Đóng dấu nguồn gốc lô ngay khi phiếu nhập hoàn tất.

        Đặt ở `_action_done` chứ không ở `button_validate` vì button_validate có
        thể trả về wizard (hỏi tạo phiếu chờ giao tiếp) và phiếu chưa xong thật.
        """
        res = super()._action_done()
        self._dlm_stamp_lot_origin()
        return res

    def _dlm_stamp_lot_origin(self):
        """Ghi NCC + ngày nhập + phiếu nguồn lên các lô vừa nhận.

        Chỉ phiếu NHẬP mới đóng dấu, và chỉ đóng dấu lô CHƯA có nguồn: lô sinh
        ra từ lần nhập đầu tiên, những lần luân chuyển sau không được ghi đè
        (nếu không, truy vết sẽ trỏ về phiếu chuyển kho nội bộ thay vì NCC).
        """
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            lots = picking.move_line_ids.lot_id.filtered(
                lambda lot: not lot.dlm_receipt_picking_id)
            if lots:
                lots.sudo().write({
                    "dlm_supplier_id": picking.partner_id.id,
                    "dlm_receipt_date": picking.date_done or fields.Date.context_today(picking),
                    "dlm_receipt_picking_id": picking.id,
                })
        return True

    def _dlm_autofill_lot_names(self):
        """Điền số lô tự sinh cho dòng NHẬN HÀNG còn trống.

        Chỉ áp cho phiếu nhập: hàng vào kho là nơi lô được SINH RA. Phiếu xuất /
        chuyển kho tiêu thụ lô đã có — tự sinh ở đó sẽ đẻ lô ma không có nguồn.

        Chỉ điền khi người dùng để trống: thủ kho vẫn có thể gõ đè số riêng.
        """
        sequence = self.env["ir.sequence"].sudo()
        for line in self.move_line_ids:
            if (line.picking_id.picking_type_id.code == "incoming"
                    and line.product_id.tracking == "lot"
                    and not line.lot_id and not line.lot_name):
                line.lot_name = sequence.next_by_code("stock.lot.serial")
        return True

    # ── K5 — Hành động trên màn Kiểm & cất hàng ──────────────────────────────
    def action_dlm_pass_all(self):
        """Nút phụ "Đạt tất cả": điền Đạt = số NCC giao cho mọi dòng.

        Ca phổ biến nhất (hàng về đủ và tốt) — tiết kiệm hàng chục lần gõ.
        """
        self.ensure_one()
        for move in self.move_ids:
            move.write({
                "quantity": move.product_uom_qty,
                "dlm_qty_rejected": 0.0,
                "dlm_reject_reason": False,
                "dlm_reject_note": False,
                "picked": True,
            })
        return True

    def action_dlm_validate_qc(self):
        """Xác nhận kiểm: hàng đạt vào kho, hàng loại sang khu Chờ trả NCC.

        Trình tự (§6.4). Điểm tinh nhưng quan trọng là bước 2: phải THU HẸP nhu
        cầu dòng gốc về đúng số đạt trước khi tách dòng loại. Không làm vậy thì
        tổng nhu cầu (100) vượt tổng thực hiện (92) và Odoo đẻ ra một phiếu kiểm
        chờ tiếp 8 đơn vị — trong khi 8 đơn vị đó đã sang khu trả hàng rồi.
        """
        self.ensure_one()
        problems = self._dlm_qc_problems()
        if problems:
            # UI đã chặn nút; đây là lưới an toàn cho gọi qua RPC/test.
            raise UserError(_("Chưa xác nhận kiểm được:\n- %s")
                            % "\n- ".join(problems))

        rejected_moves = self.move_ids.filtered(
            lambda m: m.dlm_qty_rejected > 0)
        if rejected_moves:
            self._dlm_split_rejected_moves(rejected_moves)

        # skip_backorder: KHÔNG mở modal hỏi phiếu chờ tiếp (quy ước dự án).
        # Cố ý KHÔNG kèm picking_ids_not_to_backorder — phần CHƯA KIỂM (nếu thủ
        # kho kiểm dở) vẫn phải tách sang phiếu kiểm mới, không được biến mất.
        result = self.with_context(skip_backorder=True).button_validate()

        if rejected_moves:
            self._dlm_create_vendor_return(rejected_moves)
        self._dlm_post_qc_summary()
        return result

    def _dlm_split_rejected_moves(self, rejected_moves):
        """Tách phần hàng loại của mỗi dòng sang một dòng đích Chờ trả NCC."""
        self.ensure_one()
        reject_location = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_nhan_tra")
        Move = self.env["stock.move"]
        new_moves = Move.browse()
        reject_moves = Move.browse()

        for move in rejected_moves:
            rounding = move.product_uom.rounding or 0.01
            con_lai = move.product_uom_qty - move.dlm_qty_rejected
            if float_is_zero(con_lai, precision_rounding=rounding):
                # Loại SẠCH cả dòng: đổi thẳng đích của dòng gốc. Tách ra dòng
                # mới thì dòng gốc còn nhu cầu 0 — Odoo huỷ nó và mất luôn kết
                # quả kiểm đã ghi trên dòng.
                # sudo: xem lý do ở nhánh dưới.
                move.sudo().write({
                    "location_dest_id": reject_location.id,
                    "product_uom_qty": move.dlm_qty_rejected,
                })
                move.move_line_ids.location_dest_id = reject_location
                reject_moves |= move
                continue
            new_moves |= Move.create({
                "name": move.name,
                "picking_id": self.id,
                "picking_type_id": move.picking_type_id.id,
                "product_id": move.product_id.id,
                "product_uom": move.product_uom.id,
                "product_uom_qty": move.dlm_qty_rejected,
                "location_id": move.location_id.id,
                "location_dest_id": reject_location.id,
                "company_id": move.company_id.id,
                # Kết quả kiểm ở lại dòng GỐC (một dòng = một lần kiểm). Dòng
                # tách chỉ chở hàng đi, mang theo lý do để phiếu trả đọc được.
                "dlm_reject_reason": move.dlm_reject_reason,
                "dlm_reject_note": move.dlm_reject_note,
            })
            # Nhu cầu dòng gốc BỚT ĐI đúng phần loại — KHÔNG đặt bằng số đạt.
            # Đặt bằng số đạt thì phần CHƯA KIỂM (giao 100, kiểm 90 đạt + 8 loại
            # ⇒ còn 2) biến mất khỏi nhu cầu: hàng thật nằm lại khu Chờ kiểm mà
            # không phiếu nào nhắc tới nữa.
            #
            # sudo: stock.move.write ghi log chatter mỗi lần đổi nhu cầu, mà
            # message_post nổ UserError nếu người dùng chưa khai email. Đây là
            # bút toán nội bộ của hệ thống, không phải người dùng sửa tay —
            # không được để hồ sơ thiếu email chặn cả việc nhập kho.
            move.sudo().product_uom_qty = move.product_uom_qty - move.dlm_qty_rejected

        if new_moves:
            new_moves._action_confirm()
        reject_moves |= new_moves
        if not reject_moves:
            return
        reject_moves._action_assign()
        for move in reject_moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        self._dlm_force_lot_on(reject_moves)

    def _dlm_force_lot_on(self, moves):
        """Gán lô cho dòng hàng loại nếu bước giữ chỗ không tự gán được.

        Hàng loại vẫn thuộc lô đã nhận — mất lô ở đây là mất luôn bằng chứng
        "lô LO/2026/00002 của NCC X có 8 cây gỉ", đúng thứ khiến khiếu nại NCC
        thành lời nói suông. Xác nhận phiếu cũng sẽ nổ ("cần cung cấp số lô")
        nhưng lỗi đó không nói được phải điền lô nào.

        Hai nguồn suy ra lô, theo thứ tự tin cậy: dòng khác của chính phiếu này,
        rồi tồn đang nằm ở khu Chờ kiểm.
        """
        Quant = self.env["stock.quant"]
        for move in moves:
            if move.product_id.tracking != "lot":
                continue
            lines = move.move_line_ids.filtered(lambda line: not line.lot_id)
            if not lines:
                continue
            lot = move.picking_id.move_line_ids.filtered(
                lambda line: line.product_id == move.product_id and line.lot_id
            )[:1].lot_id
            if not lot:
                lot = Quant.search([
                    ("location_id", "=", move.location_id.id),
                    ("product_id", "=", move.product_id.id),
                    ("lot_id", "!=", False),
                ], order="quantity desc", limit=1).lot_id
            if lot:
                lines.lot_id = lot

    def _dlm_create_vendor_return(self, rejected_moves):
        """Phiếu [3] Trả hàng NCC — để NHÁP, giao việc cho Mua hàng.

        Vì sao không tự xác nhận: trả hàng là việc ĐỐI NGOẠI, phải thoả thuận
        với NCC trước (đổi hàng? giảm trừ công nợ? NCC tự đến lấy?). Thủ kho ghi
        nhận, Mua hàng quyết định — đúng ranh giới kiểm soát chéo đã có.
        """
        self.ensure_one()
        return_type = self.env.ref(
            "dl_inventory.picking_type_vendor_return", raise_if_not_found=False)
        if not return_type:
            return self.env["stock.picking"]
        reject_location = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_nhan_tra")
        receipt = self._dlm_source_receipt()
        partner = receipt.partner_id or self.partner_id

        picking = self.env["stock.picking"].create({
            "picking_type_id": return_type.id,
            "partner_id": partner.id,
            "location_id": reject_location.id,
            "location_dest_id": return_type.default_location_dest_id.id,
            "origin": receipt.name or self.name,
            "dlm_origin_picking_id": (receipt or self).id,
            "move_ids": [(0, 0, {
                "name": move.product_id.display_name,
                "product_id": move.product_id.id,
                "product_uom": move.product_uom.id,
                "product_uom_qty": move.dlm_qty_rejected,
                "location_id": reject_location.id,
                "location_dest_id": return_type.default_location_dest_id.id,
                "dlm_reject_reason": move.dlm_reject_reason,
                "dlm_reject_note": move.dlm_reject_note,
            }) for move in rejected_moves],
        })
        # sudo: ghi chatter là DẤU VẾT, không phải nghiệp vụ. Người dùng chưa
        # khai email làm message_post nổ UserError (mail_thread._message_compute
        # _author) — để nguyên thì cả phiếu kiểm rollback chỉ vì thiếu email
        # trong hồ sơ thủ kho. sudo() đặt env.su ⇒ Odoo bỏ qua kiểm tra đó.
        picking.sudo().message_post(body=_(
            "Sinh tự động từ kết quả kiểm phiếu %s. Phiếu để <b>nháp</b>: Mua "
            "hàng thoả thuận với NCC rồi mới xác nhận trả."
        ) % self.name)
        self._dlm_notify_purchasing(picking)
        return picking

    def _dlm_notify_purchasing(self, return_picking):
        """Giao việc cho nhóm Mua hàng — phiếu trả nháp không ai biết là nằm im."""
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        if not group:
            return
        summary = _("Xử lý trả hàng NCC — %s") % return_picking.name
        for user in group.users:
            return_picking.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=_("Kiểm hàng phiếu %s phát hiện hàng không đạt. Thoả "
                       "thuận với %s rồi xác nhận (hoặc huỷ) phiếu trả này.")
                % (self.name, return_picking.partner_id.display_name),
                user_id=user.id)

    def _dlm_post_qc_summary(self):
        """Ghi kết quả kiểm theo từng dòng lên chatter — dấu vết cho khiếu nại."""
        self.ensure_one()
        reasons = dict(
            self.env["stock.move"]._fields["dlm_reject_reason"].selection)
        rows = []
        for move in self.move_ids:
            if move.dlm_qty_rejected <= 0:
                continue
            rows.append(_("<li>%s — loại <b>%s</b> %s (%s)%s</li>") % (
                move.product_id.display_name,
                _dlm_fmt(move.dlm_qty_rejected),
                move.product_uom.name,
                reasons.get(move.dlm_reject_reason, _("chưa rõ")),
                _(": %s") % move.dlm_reject_note if move.dlm_reject_note else ""))
        # sudo: xem lý do ở _dlm_create_vendor_return.
        if rows:
            self.sudo().message_post(
                body=_("Kết quả kiểm:<ul>%s</ul>") % "".join(rows))
        else:
            self.sudo().message_post(body=_("Kiểm đạt toàn bộ, đã cất vào kho."))

    # ── K5 — Điều hướng giữa các chặng chứng từ ──────────────────────────────
    def _dlm_source_receipt(self):
        """Phiếu nhận [1] đứng trước phiếu kiểm này (rỗng nếu tạo tay)."""
        self.ensure_one()
        origins = self.move_ids.move_orig_ids.picking_id.filtered(
            lambda p: p.picking_type_id.code == "incoming")
        return origins[:1]

    def action_dlm_open_source_receipt(self):
        """Phiếu kiểm → phiếu nhận gốc."""
        self.ensure_one()
        receipt = self._dlm_source_receipt()
        if not receipt:
            raise UserError(_("Phiếu kiểm này không đi từ phiếu nhận nào."))
        return self._dlm_open_picking(receipt, _("Phiếu nhận %s") % receipt.name)

    def action_dlm_open_qc_picking(self):
        """Phiếu nhận → phiếu kiểm sinh ra từ nó."""
        self.ensure_one()
        qc = self.move_ids.move_dest_ids.picking_id.filtered(
            lambda p: p.picking_type_id.sequence_code == _DLM_QC_CODE)[:1]
        if not qc:
            raise UserError(_(
                "Chưa có phiếu kiểm. Phiếu kiểm chỉ sinh ra sau khi xác nhận "
                "nhận hàng."))
        return self._dlm_open_picking(qc, _("Phiếu kiểm %s") % qc.name)

    def _dlm_vendor_returns(self):
        """Phiếu trả NCC của cả chặng nhận hàng này.

        Neo vào phiếu NHẬN (Mua hàng cần biết trả hàng thuộc lần giao nào để đối
        chiếu hoá đơn NCC), nhưng tra được từ cả phiếu nhận lẫn phiếu kiểm —
        người bấm ra phiếu trả đang đứng ở phiếu kiểm.
        """
        self.ensure_one()
        anchor = self._dlm_source_receipt() | self
        return self.search([("dlm_origin_picking_id", "in", anchor.ids)])

    def action_dlm_open_returns(self):
        """Phiếu nhận / phiếu kiểm → các phiếu trả NCC của chặng này."""
        self.ensure_one()
        returns = self._dlm_vendor_returns()
        if len(returns) == 1:
            return self._dlm_open_picking(
                returns, _("Phiếu trả NCC %s") % returns.name)
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "name": _("Phiếu trả NCC của %s") % self.name,
            "view_mode": "tree,form",
            "domain": [("id", "in", returns.ids)],
        }

    def _dlm_open_picking(self, picking, name):
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "name": name,
        }
