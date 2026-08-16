# -*- coding: utf-8 -*-
"""Kết quả kiểm hàng (QC) ghi ngay trên dòng dịch chuyển — số đạt = `quantity` native."""

import base64

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_process
from odoo.tools.float_utils import float_compare

from .stock_picking import _DLM_QC_CODE


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # Đơn bán hàng của phiếu — để màn "Đang giữ chỗ" nói được hàng hứa cho đơn nào.
    dlm_sale_order_id = fields.Many2one(
        related="picking_id.dlm_sale_order_id", string="Đơn bán hàng",
        readonly=True)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _dlm_evidence_thumb(self, size=(480, 480)):
        """Thumbnail base64 của ảnh bằng chứng (thu về 480px), rỗng nếu không phải ảnh hoặc ảnh hỏng."""
        self.ensure_one()
        if not (self.mimetype or "").startswith("image/"):
            return ""
        try:
            # sudo: ảnh vừa upload còn res_id=0. Dùng `raw` (bytes thô), không phải `datas` base64.
            raw = self.sudo().raw
            if not raw:
                return ""
            thumb = image_process(raw, size=size, output_format="JPEG")
            return base64.b64encode(thumb or b"").decode()
        except Exception:  # noqa: BLE001 — ảnh hỏng chỉ mất tấm đó
            return ""


class StockMove(models.Model):
    _inherit = "stock.move"

    dlm_qty_rejected = fields.Float(
        string="Số loại", digits="Product Unit of Measure", default=0.0,
        help="Số lượng KHÔNG đạt khi kiểm — sẽ chuyển sang khu Chờ trả nhà cung cấp.")
    dlm_reject_reason = fields.Selection([
        ("defect", "Hàng lỗi / hư hỏng"),
        ("wrong_spec", "Sai quy cách"),
        ("wrong_item", "Giao sai mặt hàng"),
        ("other", "Khác"),
    ], string="Lý do loại")
    dlm_reject_note = fields.Char(string="Ghi chú loại")

    # ── Bằng chứng hàng loại ─────────────────────────────────────────────────
    # Neo vào DÒNG (không vào phiếu): 1 phiếu kiểm loại nhiều mặt hàng vì nhiều lý do.
    dlm_evidence_ids = fields.Many2many(
        "ir.attachment", "dlm_move_evidence_rel", "move_id", "attachment_id",
        string="Ảnh bằng chứng",
        help="Ảnh chụp hàng lỗi lúc mở hàng. Chỉ chụp được trên phiếu kiểm và "
             "KHOÁ lại sau khi xác nhận.")
    dlm_evidence_count = fields.Integer(
        string="Ảnh", compute="_compute_dlm_evidence_count")
    # Khoá bằng chứng sau khi xác nhận: ảnh phải chụp lúc mở hàng, sau đó chỉ ĐỌC.
    dlm_evidence_locked = fields.Boolean(
        string="Bằng chứng đã khoá", compute="_compute_dlm_evidence_locked")
    # Trường HTML render thumbnail thật (many2many_binary chỉ bày thẻ file, không xem được ảnh).
    dlm_evidence_gallery = fields.Html(
        string="Lưới ảnh bằng chứng", sanitize=False, readonly=True,
        compute="_compute_dlm_evidence_gallery")
    # Số đang nói tới của dòng theo từng chặng: phiếu kiểm = số loại; phiếu trả/phế liệu = nhu cầu dòng.
    dlm_reject_qty_shown = fields.Float(
        string="Số lượng", digits="Product Unit of Measure",
        compute="_compute_dlm_reject_qty_shown")

    @api.depends("dlm_evidence_ids")
    def _compute_dlm_evidence_count(self):
        for move in self:
            move.dlm_evidence_count = len(move.dlm_evidence_ids)

    # Số lô hiện trên phiếu trả NCC, kể cả lúc nháp chưa giữ chỗ (tra cùng cách biên bản PDF).
    dlm_return_lot_display = fields.Char(
        string="Lô", compute="_compute_dlm_return_lot_display")

    @api.depends("lot_ids", "product_id", "picking_id.location_id")
    def _compute_dlm_return_lot_display(self):
        for move in self:
            if move.lot_ids:
                move.dlm_return_lot_display = ", ".join(
                    move.lot_ids.mapped("name"))
            elif move.picking_id:
                # Cùng cách tra như biên bản PDF — một nguồn cho cả màn hình lẫn tờ giấy.
                move.dlm_return_lot_display = ", ".join(
                    move.picking_id._dlm_reject_report_lots(move))
            else:
                move.dlm_return_lot_display = ""

    @api.depends("dlm_qty_rejected", "product_uom_qty")
    def _compute_dlm_reject_qty_shown(self):
        for move in self:
            move.dlm_reject_qty_shown = (
                move.dlm_qty_rejected or move.product_uom_qty)

    @api.depends("dlm_evidence_ids")
    def _compute_dlm_evidence_gallery(self):
        """Dựng lưới thumbnail, ảnh nhúng thẳng dạng data URI (né route /web/image lỗi khi res_id=0)."""
        for move in self:
            o = []
            khac = self.env["ir.attachment"]
            for att in move.dlm_evidence_ids:
                thumb = att._dlm_evidence_thumb()
                if not thumb:
                    khac |= att
                    continue
                o.append(Markup(
                    '<div class="dl-evi-item" title="%s">'
                    '<img src="data:image/jpeg;base64,%s" alt="%s"/>'
                    '<span class="dl-evi-name">%s</span></div>'
                ) % (att.name or "", thumb, att.name or "", att.name or ""))
            # File không phải ảnh / ảnh hỏng: vẫn nêu tên để biết nó tồn tại.
            o += [Markup(
                '<a href="/web/content/%s?download=true" class="dl-evi-file">'
                '<i class="fa fa-paperclip me-1"></i>%s</a>'
            ) % (att.id, att.name or "") for att in khac]
            move.dlm_evidence_gallery = (
                Markup('<div class="dl-evi-gallery">%s</div>')
                % Markup("").join(o) if o else Markup(
                    '<div class="text-muted fst-italic">Chưa có ảnh nào.</div>'))

    @api.depends("picking_id.picking_type_id.sequence_code", "state")
    def _compute_dlm_evidence_locked(self):
        for move in self:
            move.dlm_evidence_locked = not (
                move.picking_id.picking_type_id.sequence_code == _DLM_QC_CODE
                and move.state not in ("done", "cancel"))

    def _dlm_stamp_evidence(self):
        """Đóng dấu res_model/res_id ảnh vừa upload về đúng dòng để Mua hàng đọc được (bẫy res_id=0)."""
        for move in self:
            orphan = move.dlm_evidence_ids.filtered(lambda a: not a.res_id)
            if orphan:
                orphan.sudo().write({"res_model": move._name, "res_id": move.id})

    def action_dlm_open_evidence(self):
        """Màn Phiếu kiểm: mở hộp ảnh bằng chứng của một dòng (dialog riêng, không nhét widget vào tree)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bằng chứng — %s") % self.product_id.display_name,
            "res_model": "stock.move",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(self.env.ref(
                "dl_inventory.view_dl_move_evidence_form").id, "form")],
            "target": "new",
        }

    # ── Tồn ở nơi lấy, hiện ngay cạnh mặt hàng ───────────────────────────────
    # Số KHẢ DỤNG tại nơi lấy của chính dòng (đọc chung stock.quant._dlm_available_qty).
    dlm_src_available_qty = fields.Float(
        string="Còn lấy được", digits="Product Unit of Measure",
        compute="_compute_dlm_src_available_qty",
        help="Số lấy được NGAY tại/dưới vị trí lấy hàng của dòng này — đã trừ "
             "phần phiếu khác đang giữ chỗ. 0 = không lấy được: hoặc nơi đó hết "
             "hàng, hoặc hàng còn nhưng đã hứa cho phiếu khác. Vẫn tạo phiếu "
             "được, nhưng phiếu sẽ treo chờ hàng chứ không giữ chỗ được ngay.")

    # move_line_ids.quantity: dòng vừa giữ chỗ thì số phải nhích lên lại.
    @api.depends("product_id", "location_id", "state", "move_line_ids.quantity")
    def _compute_dlm_src_available_qty(self):
        Quant = self.env["stock.quant"]
        for move in self:
            move.dlm_src_available_qty = Quant._dlm_available_qty(
                move.product_id, move.location_id,
                own_move_lines=move.move_line_ids)

    # ── Vai trò dòng trên phiếu Hoá phế liệu: phân biệt "Hàng bỏ" vs "Phế liệu thu về" ──
    dlm_is_scrap_line = fields.Boolean(
        string="Là dòng phế liệu thu về",
        compute="_compute_dlm_scrap_role")
    dlm_scrap_role = fields.Char(
        string="Vai trò", compute="_compute_dlm_scrap_role")

    @api.depends("product_id", "product_id.dlm_is_scrap")
    def _compute_dlm_scrap_role(self):
        for move in self:
            la_phe = bool(move.product_id.dlm_is_scrap)
            move.dlm_is_scrap_line = la_phe
            move.dlm_scrap_role = (
                _("Phế liệu thu về") if la_phe else _("Hàng bỏ"))

    # ── Vai trò dòng trên phiếu [8] Nhập kho từ xưởng ────────────────────────
    # Người dùng khai VAI TRÒ; vị trí nguồn/đích SUY RA (dùng vị trí ảo Sản xuất
    # để giữ vết và tránh tồn âm), không có ô vị trí nào để chọn sai.
    dlm_move_kind = fields.Selection([
        ("output", "Xưởng nộp về"),
        ("consume", "Vật tư đã dùng"),
        ("return", "Vật tư trả lại kho"),
    ], string="Vai trò dòng", copy=True,
        help="Quyết định vị trí lấy/nhận của dòng này. Chỉ dùng trên phiếu "
             "Nhập kho từ xưởng.")

    @api.model
    def _dlm_route_for(self, move_kind, product):
        """(nguồn, đích) suy từ vai trò dòng + mặt hàng; @api.model vì create cần vị trí trước khi bản ghi tồn tại."""
        if not move_kind:
            return False
        Location = self.env["stock.location"]
        production = Location._dlm_virtual_location("production")
        xuong = Location._dlm_location("dl_inventory.stock_location_xuong")
        if move_kind == "consume":
            return xuong, production
        if move_kind == "return":
            return xuong, Location._dlm_location(
                "dl_inventory.stock_location_nhan_kho")
        # "output" — đích theo MẶT HÀNG; soi cờ phế liệu TRƯỚC product_kind
        # (SCRAP-STEEL mang kind='material' y hệt thép thật).
        if product.dlm_is_scrap:
            dest_xml_id = "dl_inventory.stock_location_xuong_pl"
        elif product.product_kind == "material_processed":
            dest_xml_id = "dl_inventory.stock_location_nhan_kho"
        else:
            dest_xml_id = "dl_inventory.stock_location_tp"
        return production, Location._dlm_location(dest_xml_id)

    def _dlm_workshop_route(self):
        """(nguồn, đích) của chính dòng này. False = không phải dòng phiếu [8]."""
        self.ensure_one()
        return self._dlm_route_for(self.dlm_move_kind, self.product_id)

    def _dlm_stamp_workshop_route(self):
        """Đóng vị trí đúng theo vai trò dòng ở create/write (onchange không nổ với RPC/import)."""
        for move in self:
            if move.state in ("done", "cancel"):
                continue
            route = move._dlm_workshop_route()
            if not route:
                continue
            source, destination = route
            vals = {}
            if move.location_id != source:
                vals["location_id"] = source.id
            if move.location_dest_id != destination:
                vals["location_dest_id"] = destination.id
            if vals:
                super(StockMove, move).write(vals)

    @api.onchange("dlm_move_kind", "product_id")
    def _onchange_dlm_move_kind(self):
        """Bản UI của `_dlm_stamp_workshop_route` — để người dùng thấy ngay."""
        for move in self:
            if not move.dlm_move_kind or not move.product_id:
                continue
            route = move._dlm_workshop_route()
            if route:
                move.location_id, move.location_dest_id = route

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # `name` required nhưng không có default — điền tay để dòng tạo qua RPC/import/test không nổ.
            if not vals.get("dlm_move_kind"):
                continue
            product = self.env["product.product"].browse(vals.get("product_id"))
            if not vals.get("name"):
                vals["name"] = product.display_name or _("Dòng mẻ sản xuất")
            route = self._dlm_route_for(vals["dlm_move_kind"], product)
            if route:
                vals["location_id"] = route[0].id
                vals["location_dest_id"] = route[1].id
        moves = super().create(vals_list)
        moves._dlm_stamp_workshop_route()
        moves._dlm_stamp_evidence()
        return moves

    def write(self, vals):
        if "dlm_evidence_ids" in vals and not self.env.su:
            # Khoá bằng chứng ở tầng server, không chỉ readonly view (RPC né được view).
            locked = self.filtered("dlm_evidence_locked")
            if locked:
                raise UserError(_(
                    "Bằng chứng đã khoá — chỉ sửa được trên phiếu kiểm và "
                    "trước khi xác nhận kiểm:\n- %s\n\nCần bổ sung sau thì "
                    "đính kèm vào phần trao đổi của phiếu, đừng sửa bản gốc."
                ) % "\n- ".join(locked.mapped("product_id.display_name")))
        res = super().write(vals)
        if {"dlm_move_kind", "product_id"} & set(vals):
            self._dlm_stamp_workshop_route()
        if "dlm_evidence_ids" in vals:
            self._dlm_stamp_evidence()
        return res

    # Đạt + Loại không được vượt số nhận; là field (không @api.constrains) để tô đỏ INLINE khi gõ.
    dlm_qc_over = fields.Boolean(
        string="Vượt số nhận", compute="_compute_dlm_qc_over")

    @api.depends("quantity", "dlm_qty_rejected", "product_uom_qty", "product_uom",
                 "state")
    def _compute_dlm_qc_over(self):
        for move in self:
            if move.state in ("done", "cancel"):
                # Chỉ áp lúc nhập liệu; sau xác nhận dòng đã thu hẹp nhu cầu nên bỏ qua.
                move.dlm_qc_over = False
                continue
            rounding = move.product_uom.rounding or 0.01
            move.dlm_qc_over = float_compare(
                move.quantity + move.dlm_qty_rejected, move.product_uom_qty,
                precision_rounding=rounding) > 0

    # ── Gõ Loại thì tự hạ Đạt ────────────────────────────────────────────────
    @api.onchange("dlm_qty_rejected")
    def _onchange_dlm_qty_rejected(self):
        """Màn Phiếu kiểm: gõ Loại thì tự hạ Đạt (mô hình "trong 198 nhận, 2 loại")."""
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

    # ── Một lần nhận hàng = một phiếu kiểm riêng ─────────────────────────────
    def _action_confirm(self, merge=True, merge_into=False):
        """Đóng dấu nhóm cung ứng cho dòng nhận trước khi push sinh dòng kiểm — để không trộn 2 NCC vào 1 phiếu kiểm."""
        self.picking_id._dlm_group_receipt_moves()
        return super()._action_confirm(merge=merge, merge_into=merge_into)

    def _dlm_source_receipt(self):
        """Phiếu NHẬN đứng ngay trước dòng kiểm này (rỗng nếu tạo tay)."""
        self.ensure_one()
        return self.move_orig_ids.picking_id.filtered(
            lambda p: p.picking_type_id.code == "incoming")[:1]

    # ── Bất biến cứng: dòng kiểm chỉ gom vào phiếu kiểm ra từ ĐÚNG phiếu nhận của nó (kể cả khi mất nhóm) ──
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

    # ── Phiếu kho tự sinh mang nhóm cung ứng + NCC ───────────────────────────
    def _get_new_picking_values(self):
        """Điền nhóm cung ứng + NCC lên phiếu kho tự sinh (Odoo gốc để trống ⇒ phiếu kiểm mất NCC)."""
        vals = super()._get_new_picking_values()
        group = self.mapped("group_id")
        if len(group) == 1:
            vals["group_id"] = group.id
            if not vals.get("partner_id") and group.partner_id:
                vals["partner_id"] = group.partner_id.id
        return vals
