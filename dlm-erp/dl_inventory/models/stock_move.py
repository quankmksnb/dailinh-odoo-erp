# -*- coding: utf-8 -*-
"""K5 — Kết quả kiểm hàng ghi ngay trên dòng dịch chuyển.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §6.

Ba tình huống phải tách bạch, vì mỗi cái là một vấn đề NCC khác nhau:

    NCC giao thiếu   đặt 100, giao 95      ⇒ phiếu NHẬN ghi 95, Odoo sinh backorder
    NCC giao hàng lỗi  giao 100, 8 cây gỉ  ⇒ phiếu KIỂM ghi Loại 8, sang Chờ trả NCC
    NCC giao thừa    đặt 100, giao 103     ⇒ phiếu NHẬN ghi 103

Gộp "giao thiếu" vào "hàng lỗi" là mất đúng thông tin quý nhất của QC: NCC nào
giao thiếu, NCC nào giao hàng kém — hai cách xử lý hoàn toàn khác nhau.

KHÔNG có field "số đạt": số đạt CHÍNH LÀ ``quantity`` native (số thực hiện của
dòng), view chỉ đổi nhãn thành "Đạt". Thêm một field alias chỉ để đổi nhãn là
đẻ ra hai nguồn sự thật cho cùng một con số.
"""

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare

from .stock_picking import _DLM_QC_CODE


class StockMove(models.Model):
    _inherit = "stock.move"

    dlm_qty_rejected = fields.Float(
        string="Số loại", digits="Product Unit of Measure", default=0.0,
        help="Số lượng KHÔNG đạt khi kiểm — sẽ chuyển sang khu Chờ trả NCC.")
    dlm_reject_reason = fields.Selection([
        ("defect", "Hàng lỗi / hư hỏng"),
        ("wrong_spec", "Sai quy cách"),
        ("wrong_item", "Giao sai mặt hàng"),
        ("other", "Khác"),
    ], string="Lý do loại")
    dlm_reject_note = fields.Char(string="Ghi chú loại")

    # ── Tồn ở nơi lấy, hiện ngay cạnh mặt hàng ───────────────────────────────
    # Danh sách mặt hàng của phiếu chuyển kho KHÔNG còn ẩn hàng đã hết (xem
    # stock_picking._compute_dlm_blocked_product_ids). Ẩn đi thì thủ kho
    # tìm không thấy và tưởng hệ thống hỏng; đổi lại, đã cho chọn thì phải nói
    # ra số tồn NGAY trên dòng — không thì họ chọn xong mới biết là chọn hụt.
    # Neo vào `location_id` của chính dòng (không phải của phiếu): native
    # `_onchange_locations` đã đẩy vị trí phiếu xuống mọi dòng, nên số này theo
    # kịp khi đổi "Từ vị trí" mà không cần đi vòng qua parent.
    dlm_src_available_qty = fields.Float(
        string="Tồn ở nơi lấy", digits="Product Unit of Measure",
        compute="_compute_dlm_src_available_qty",
        help="Tồn thực của mặt hàng tại/dưới vị trí lấy hàng của dòng này. "
             "0 = nơi đó đang hết — vẫn tạo phiếu được, nhưng phiếu sẽ treo "
             "chờ hàng chứ không giữ chỗ được ngay.")

    @api.depends("product_id", "location_id")
    def _compute_dlm_src_available_qty(self):
        """sudo(): chỉ đọc SỐ LƯỢNG tồn, không đụng giá (§8.3 doc kho)."""
        Quant = self.env["stock.quant"].sudo()
        for move in self:
            if not move.product_id or not move.location_id:
                move.dlm_src_available_qty = 0.0
                continue
            move.dlm_src_available_qty = sum(Quant.search([
                ("location_id", "child_of", move.location_id.id),
                ("product_id", "=", move.product_id.id),
            ]).mapped("quantity"))

    # QC-02 — Đạt + Loại không được vượt số hàng đang nằm ở khu Chờ kiểm.
    # Là field (không phải @api.constrains) để view tô đỏ dòng NGAY khi gõ:
    # ràng buộc sửa-được-trên-form phải báo INLINE, không bắn modal.
    dlm_qc_over = fields.Boolean(
        string="Vượt số nhận", compute="_compute_dlm_qc_over")

    @api.depends("quantity", "dlm_qty_rejected", "product_uom_qty", "product_uom",
                 "state")
    def _compute_dlm_qc_over(self):
        for move in self:
            if move.state in ("done", "cancel"):
                # QC-02 là luật lúc NHẬP LIỆU. Sau khi xác nhận, dòng gốc đã bị
                # thu hẹp nhu cầu về đúng số đạt (xem _dlm_split_rejected_moves)
                # nên phép so Đạt+Loại ≤ nhu cầu không còn nghĩa — để nguyên thì
                # phiếu đã xong lại hiện dải đỏ vô cớ.
                move.dlm_qc_over = False
                continue
            rounding = move.product_uom.rounding or 0.01
            move.dlm_qc_over = float_compare(
                move.quantity + move.dlm_qty_rejected, move.product_uom_qty,
                precision_rounding=rounding) > 0

    # ── RS-06 — Gõ Loại thì tự hạ Đạt ────────────────────────────────────────
    @api.onchange("dlm_qty_rejected")
    def _onchange_dlm_qty_rejected(self):
        """Bỏ phép cộng trừ khỏi đầu thủ kho.

        Luồng thật: bấm "Đạt tất cả" (ca phổ biến nhất) ⇒ Đạt = 198. Rồi phát
        hiện 2 cái lỗi, gõ Loại = 2 ⇒ QC-02 nổ dải đỏ, nút Xác nhận biến mất, và
        thủ kho phải tự hiểu là còn phải quay lại hạ Đạt xuống 196.

        Mô hình suy nghĩ của người dùng là "trong 198 cái nhận, 2 cái loại" —
        chứ không phải "ghi Đạt 196 và Loại 2". Ở đây làm nốt phép trừ đó.
        QC-02 GIỮ NGUYÊN làm lưới an toàn: nó vẫn bắt ca gõ Đạt lớn hơn số nhận,
        và ca Loại một mình đã vượt số nhận (Đạt bị kẹp về 0).
        """
        for move in self:
            if (move.picking_type_id.sequence_code != _DLM_QC_CODE
                    or move.state in ("done", "cancel")):
                continue
            rounding = move.product_uom.rounding or 0.01
            if float_compare(move.quantity + move.dlm_qty_rejected,
                             move.product_uom_qty,
                             precision_rounding=rounding) > 0:
                move.quantity = max(
                    move.product_uom_qty - move.dlm_qty_rejected, 0.0)

    # ── RS-01 — Một lần nhận hàng = một phiếu kiểm riêng ──────────────────────
    def _action_confirm(self, merge=True, merge_into=False):
        """Đóng dấu nhóm cung ứng cho dòng NHẬN trước khi push sinh dòng kiểm.

        Thiết kế: docs/Ra_soat_phan_he_kho_2026-08-12.md RS-01.

        `_push_apply` (sinh dòng kiểm cho tuyến nhận 2 bước) nằm BÊN TRONG
        `super()._action_confirm()`, và nó copy nguyên dòng nhận — kể cả
        `group_id`. Nên chỉ cần dòng nhận đã có nhóm TRƯỚC lời gọi super() là
        dòng kiểm thừa hưởng đúng nhóm của phiếu nhận đó.

        🔴 Vì sao phải đứng ở đây chứ không ở `stock.picking.action_confirm`:
        đó chỉ là MỘT trong nhiều đường xác nhận. Đo trên dlm_dev (DL/KC/00003):
        hai phiếu nhận DL/NH/00003 + DL/NH/00004 đều CÓ nhóm, nhưng hai dòng
        kiểm sinh ra lại `group_id = NULL` — nghĩa là nhóm được đóng dấu SAU khi
        push đã copy xong, tức lần xác nhận thật không đi qua override ở tầng
        phiếu. Hậu quả: hai dòng kiểm cùng khoá `group_id = NULL` nên
        `_assign_picking` nhồi hàng của hai NCC vào CÙNG một phiếu kiểm, ô Nhà
        cung cấp bị xoá trắng, và phiếu trả hàng sẽ ghi SAI NCC.

        `_action_confirm` của move thì KHÔNG đường nào né được: push chỉ chạy
        trong chính nó.
        """
        self.picking_id._dlm_group_receipt_moves()
        return super()._action_confirm(merge=merge, merge_into=merge_into)

    def _dlm_source_receipt(self):
        """Phiếu NHẬN đứng ngay trước dòng kiểm này (rỗng nếu tạo tay)."""
        self.ensure_one()
        return self.move_orig_ids.picking_id.filtered(
            lambda p: p.picking_type_id.code == "incoming")[:1]

    # ── RS-01 — Bất biến cứng: phiếu kiểm không được trộn hai phiếu nhận ──────
    #
    # Nhóm cung ứng ở trên là cơ chế "đúng theo Odoo", nhưng nó vẫn là một giá
    # trị có thể trống (dữ liệu cũ, phiếu tạo tay, code khác ghi đè). Hai móc
    # dưới đây neo thẳng vào NGUỒN GỐC — dòng kiểm chỉ được gom vào phiếu kiểm
    # đi ra từ ĐÚNG phiếu nhận của nó — nên mất nhóm cũng không gộp nhầm được.
    # Đây là thứ giữ được truy xuất "lô này của NCC nào, theo lần giao nào".
    def _key_assign_picking(self):
        keys = super()._key_assign_picking()
        if self.picking_type_id.sequence_code == _DLM_QC_CODE:
            keys += (self._dlm_source_receipt(),)
        return keys

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        if self.picking_type_id.sequence_code != _DLM_QC_CODE:
            return domain
        receipt = self._dlm_source_receipt()
        if not receipt:
            return domain
        return domain + [("move_ids.move_orig_ids.picking_id", "=", receipt.id)]

    # ── RS-01 — Phiếu kho tự sinh phải mang nhóm cung ứng + NCC của nó ────────
    def _get_new_picking_values(self):
        """Điền nhóm cung ứng và NCC lên phiếu kho do hệ thống tự sinh.

        Thiết kế: docs/Ra_soat_phan_he_kho_2026-08-12.md RS-01 (b).

        Odoo gốc dựng phiếu mới KHÔNG set `group_id`, và chỉ điền `partner_id` khi
        MỌI dòng cùng một đối tác — mà move kiểm không có `partner_id` (nó compute
        từ phiếu, phiếu thì chưa tồn tại lúc này). Kết quả: phiếu kiểm để trống cả
        nhóm lẫn NCC (đúng ô "Nhà cung cấp" trống trong ảnh chụp).

        Sau khi move đã mang `group_id` (xem `_action_confirm` trên), mỗi phiếu tự sinh
        gom đúng MỘT nhóm ⇒ điền nhóm để `_search_picking_for_assignation` gộp
        đúng các move cùng nhóm, và điền NCC của nhóm để phiếu kiểm hiện đúng đối
        tác. `group_id.partner_id` do `_dlm_group_receipt_moves` đóng dấu.
        """
        vals = super()._get_new_picking_values()
        group = self.mapped("group_id")
        if len(group) == 1:
            vals["group_id"] = group.id
            if not vals.get("partner_id") and group.partner_id:
                vals["partner_id"] = group.partner_id.id
        return vals
