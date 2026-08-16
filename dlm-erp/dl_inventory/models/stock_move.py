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

import base64

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_process
from odoo.tools.float_utils import float_compare

from .stock_picking import _DLM_QC_CODE


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # K14 — màn "Đang giữ chỗ" phải nói được hàng hứa cho ĐƠN nào, không chỉ cho
    # phiếu nào: thủ kho biết số phiếu cũng chưa gọi được cho ai. Related không
    # lưu — dữ liệu đã ở phiếu, nhân bản sang dòng chỉ tạo thêm chỗ lệch.
    dlm_sale_order_id = fields.Many2one(
        related="picking_id.dlm_sale_order_id", string="Đơn bán hàng",
        readonly=True)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _dlm_evidence_thumb(self, size=(480, 480)):
        """Thumbnail base64 của một ảnh bằng chứng, hoặc rỗng nếu không phải ảnh.

        Thu nhỏ TRƯỚC khi nhúng: ảnh điện thoại 4MB nhúng thẳng vào HTML sẽ đẩy
        gói onchange lên hàng chục MB cho một hộp thoại. 480px là đủ để nhìn ra
        vết gỉ mà chỉ tốn vài chục KB.

        Nuốt mọi lỗi: một tấm ảnh hỏng phải rơi xuống dạng link tên file, không
        được giết cả lưới — cùng nguyên tắc đã áp cho biên bản PDF.
        """
        self.ensure_one()
        if not (self.mimetype or "").startswith("image/"):
            return ""
        try:
            # sudo: ảnh vừa upload còn `res_id=0`; đọc qua quyền thường là đi
            # vào đúng vùng ACL mà cả tính năng này đang né.
            # 🔴 `raw` chứ KHÔNG phải `datas`: `image_process` của Odoo 17 mở
            # thẳng bằng `Image.open(BytesIO(source))` nên nhận BYTES THÔ. Đưa
            # base64 vào thì PIL báo "cannot identify image file" — và vì lỗi bị
            # nuốt để một ảnh hỏng không giết cả lưới, nó im lặng thành ô trống.
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

    # ── K17 — Bằng chứng hàng loại ───────────────────────────────────────────
    # Neo vào DÒNG, không vào phiếu: một phiếu kiểm loại được 3 mặt hàng vì 3 lý
    # do khác nhau, gom ảnh ở mức phiếu thì không nói được tấm nào của mặt hàng
    # nào. Bộ ba lý do / ghi chú / ảnh vì thế nằm cùng chỗ và đi cùng nhau qua cả
    # ba chặng chứng từ ([2] kiểm → [3] trả NCC → [9] hoá phế liệu).
    dlm_evidence_ids = fields.Many2many(
        "ir.attachment", "dlm_move_evidence_rel", "move_id", "attachment_id",
        string="Ảnh bằng chứng",
        help="Ảnh chụp hàng lỗi lúc mở hàng. Chỉ chụp được trên phiếu kiểm và "
             "KHOÁ lại sau khi xác nhận.")
    dlm_evidence_count = fields.Integer(
        string="Ảnh", compute="_compute_dlm_evidence_count")
    # 🔴 Vì sao phải khoá: bằng chứng bổ sung được SAU KHI biết NCC cãi gì thì
    # không còn là bằng chứng — nó thành lời khai. Ảnh phải chụp lúc mở hàng,
    # tại phiếu kiểm, trước khi xác nhận. Sau đó cả 3 chặng chỉ được ĐỌC.
    # Quên chụp thì đường bù là chatter phiếu trả (phân biệt rõ với bản gốc).
    dlm_evidence_locked = fields.Boolean(
        string="Bằng chứng đã khoá", compute="_compute_dlm_evidence_locked")
    # Widget `many2many_binary` bày FILE (thẻ "JPG" + tên cắt cụt), không bày
    # ẢNH — muốn xem chỗ gỉ phải tải từng tấm về. Với một màn hình mà toàn bộ lý
    # do tồn tại là "nhìn tận mắt vết lỗi" thì đó là hỏng đúng việc chính. Trường
    # HTML này render thumbnail thật; bấm vào mở ảnh gốc ở tab mới.
    dlm_evidence_gallery = fields.Html(
        string="Lưới ảnh bằng chứng", sanitize=False, readonly=True,
        compute="_compute_dlm_evidence_gallery")
    # Số lượng ĐANG NÓI TỚI của dòng, đúng theo từng chặng: ở phiếu kiểm là số
    # bị loại, ở phiếu trả / hoá phế liệu thì chính nhu cầu của dòng LÀ số hàng
    # lỗi. Không có nó thì hộp ảnh trên phiếu trả hiện "Số loại 0" — một con số
    # sai ngay cạnh bằng chứng, chỗ tệ nhất để đặt một con số sai.
    dlm_reject_qty_shown = fields.Float(
        string="Số lượng", digits="Product Unit of Measure",
        compute="_compute_dlm_reject_qty_shown")

    @api.depends("dlm_evidence_ids")
    def _compute_dlm_evidence_count(self):
        for move in self:
            move.dlm_evidence_count = len(move.dlm_evidence_ids)

    # Cột Lô của phiếu trả NCC đứng TRỐNG suốt lúc nháp — mà nháp mới là trạng
    # thái người ta nhìn màn này nhiều nhất: `lot_ids` chỉ có sau khi giữ chỗ.
    # Một cột rỗng vẫn chiếm chỗ, và tệ hơn: biên bản PDF thì in ra số lô đầy đủ
    # còn màn hình lại để trắng — hai nguồn nói hai chuyện về cùng lô hàng.
    dlm_return_lot_display = fields.Char(
        string="Lô", compute="_compute_dlm_return_lot_display")

    @api.depends("lot_ids", "product_id", "picking_id.location_id")
    def _compute_dlm_return_lot_display(self):
        for move in self:
            if move.lot_ids:
                move.dlm_return_lot_display = ", ".join(
                    move.lot_ids.mapped("name"))
            elif move.picking_id:
                # Cùng đúng một cách tra như biên bản PDF (xem
                # vendor_return_document._dlm_reject_report_lots) — một nguồn
                # sự thật cho cả màn hình lẫn tờ giấy đưa NCC.
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
        """Dựng lưới thumbnail, ảnh NHÚNG THẲNG dưới dạng data URI.

        🔴 Cố ý KHÔNG dùng `<img src="/web/image/ir.attachment/...">`. Bản đầu
        làm vậy và ảnh vỡ ngay khi thủ kho vừa upload (biểu tượng ảnh hỏng + tên
        file). Truy ngược tầng server thì mọi mắt xích đều sạch: `check('read')`
        pass cho chính người upload kể cả khi attachment còn `res_id=0`,
        `_find_record` pass, route `/web/image/<model>/<id>/<field>` và field
        `datas` đều hợp lệ. Nghĩa là chỗ gãy nằm ở tầng HTTP/trình duyệt, chỗ
        không quan sát được từ đây.

        Nhúng thẳng thì cả đoạn đường đó biến mất: không request, không quyền,
        không phụ thuộc bản ghi đã lưu hay chưa. Ảnh được thu về 480px trước khi
        mã hoá nên payload chỉ vài chục KB/tấm, không phải ảnh điện thoại 4MB.
        """
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
            # File không phải ảnh (PDF chứng thư, video) — và cả ảnh hỏng không
            # đọc nổi — vẫn phải nêu tên: không xem trực tiếp được thì ít nhất
            # phải biết là nó tồn tại.
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
        """Gắn ảnh vừa upload về đúng dòng — bẫy `res_id=0` đã vấp ở RFQ.

        Widget many2many_binary tạo `ir.attachment` với res_id=0 khi file được
        upload trước lúc bản ghi có id. Attachment res_id=0 chỉ NGƯỜI TẠO và
        admin đọc được (cơ chế lọc của ir.attachment) ⇒ Mua hàng mở phiếu trả sẽ
        ăn AccessError trên đúng thứ họ cần nhất. Đóng dấu res_model/res_id về
        dòng kiểm thì quyền đọc ảnh bám theo quyền đọc dòng — mà Mua hàng, Kế
        toán, CEO, Trưởng KD đều có read `stock.move`.
        (Cùng lỗi và cùng cách chữa: dl_technical `_stamp_attachments`.)
        """
        for move in self:
            orphan = move.dlm_evidence_ids.filtered(lambda a: not a.res_id)
            if orphan:
                orphan.sudo().write({"res_model": move._name, "res_id": move.id})

    def action_dlm_open_evidence(self):
        """Mở hộp ảnh của MỘT dòng.

        Cố ý không nhét many2many_binary thẳng vào tree: bảng kiểm là bảng gõ
        nhanh theo hàng ngang (Đạt / Loại / Lý do), bỏ `editable` để có chỗ đặt
        widget upload là đánh đổi sai — thủ kho gõ 20 dòng mỗi ngày, còn ảnh thì
        chỉ vài dòng lỗi mới cần.
        """
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
    # Danh sách mặt hàng của phiếu chuyển kho KHÔNG còn ẩn hàng đã hết (xem
    # stock_picking._compute_dlm_blocked_product_ids). Ẩn đi thì thủ kho
    # tìm không thấy và tưởng hệ thống hỏng; đổi lại, đã cho chọn thì phải nói
    # ra số tồn NGAY trên dòng — không thì họ chọn xong mới biết là chọn hụt.
    # Neo vào `location_id` của chính dòng (không phải của phiếu): native
    # `_onchange_locations` đã đẩy vị trí phiếu xuống mọi dòng, nên số này theo
    # kịp khi đổi "Từ vị trí" mà không cần đi vòng qua parent.
    # 🔴 K14 — đọc số KHẢ DỤNG, KHÔNG phải tồn thực. Cột này nằm ngay cạnh dải
    # cảnh báo thiếu hàng của phiếu; hai chỗ đọc hai công thức khác nhau thì dải
    # báo "bị giữ hết" trong khi cột cạnh nó khoe "24" — người dùng tin cột, và
    # cột đang sai. Cả hai nay gọi chung stock.quant._dlm_available_qty.
    dlm_src_available_qty = fields.Float(
        string="Còn lấy được", digits="Product Unit of Measure",
        compute="_compute_dlm_src_available_qty",
        help="Số lấy được NGAY tại/dưới vị trí lấy hàng của dòng này — đã trừ "
             "phần phiếu khác đang giữ chỗ. 0 = không lấy được: hoặc nơi đó hết "
             "hàng, hoặc hàng còn nhưng đã hứa cho phiếu khác. Vẫn tạo phiếu "
             "được, nhưng phiếu sẽ treo chờ hàng chứ không giữ chỗ được ngay.")

    # move_line_ids.quantity: chính dòng này vừa giữ chỗ thì số phải nhích lên
    # lại, không thì dòng tự tố mình thiếu hàng ngay sau khi giữ chỗ thành công.
    @api.depends("product_id", "location_id", "state", "move_line_ids.quantity")
    def _compute_dlm_src_available_qty(self):
        Quant = self.env["stock.quant"]
        for move in self:
            move.dlm_src_available_qty = Quant._dlm_available_qty(
                move.product_id, move.location_id,
                own_move_lines=move.move_line_ids)

    # ── K12 — Vai trò dòng trên phiếu Hoá phế liệu ───────────────────────────
    # Phiếu [9] có hai loại dòng ngược nhau trong cùng một bảng. Không có cột
    # nói ra vai trò thì người dùng nhìn hai dòng cùng cỡ và không biết dòng nào
    # là thứ mình đang bỏ đi, dòng nào là thứ thu về — mà đó là toàn bộ nội dung
    # của phiếu này.
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

    # ── K16 — Vai trò dòng trên phiếu [8] Nhập kho từ xưởng ──────────────────
    # Phiếu [8] mô tả TRỌN một mẻ sản xuất, nên nó có ba loại dòng đi hai chiều
    # ngược nhau trên cùng một chứng từ. Người dùng khai VAI TRÒ; vị trí nguồn
    # và đích thì SUY RA — không có ô vị trí nào trên màn để chọn sai.
    #
    # 🔴 Vì sao "Vật tư đã dùng" đi vào vị trí ẢO Sản xuất chứ không phải "biến
    # mất": thép rời sổ vì nó đã thành cái bàn, không phải vì ai đó xoá nó.
    # Vị trí ảo giữ lại vết đó — truy ngược được "100 cây này đi đâu".
    #
    # 🔴 Vì sao "Xưởng nộp về" lấy nguồn ảo chứ không phải Xưởng: ở B1 chưa nổ
    # BOM nên cái bàn CHƯA TỪNG tồn tại ở Xưởng trên sổ. Xuất bàn từ Xưởng là
    # ghi tồn ÂM ở một chỗ đang có 0 — mà Odoo không chặn tồn âm nội bộ, nên nó
    # hỏng im lặng. Đây là lý do nguồn không được là một ô để người dùng chọn.
    dlm_move_kind = fields.Selection([
        ("output", "Xưởng nộp về"),
        ("consume", "Vật tư đã dùng"),
        ("return", "Vật tư trả lại kho"),
    ], string="Vai trò dòng", copy=True,
        help="Quyết định vị trí lấy/nhận của dòng này. Chỉ dùng trên phiếu "
             "Nhập kho từ xưởng.")

    @api.model
    def _dlm_route_for(self, move_kind, product):
        """(nguồn, đích) suy từ vai trò dòng + mặt hàng. False nếu không khai.

        Là `@api.model` chứ không phải phương thức của bản ghi vì `create` phải
        biết vị trí TRƯỚC khi bản ghi tồn tại: `location_id` là required trên
        stock.move, nên đóng dấu sau khi tạo thì đã nổ mất rồi.
        """
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
        # "output" — đích theo MẶT HÀNG. Soi cờ phế liệu TRƯỚC `product_kind`:
        # SCRAP-STEEL mang product_kind='material' y hệt thép thật (xem
        # _DLM_LOCATION_RULES), nên hỏi theo loại hàng sẽ trả lời sai.
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
        """Đóng vị trí đúng theo vai trò dòng.

        Chạy ở `create`/`write` chứ không chỉ ở onchange: onchange KHÔNG nổ với
        import, RPC, hay bất kỳ đường ghi nào không đi qua form. Vị trí sai trên
        phiếu này không phải lỗi hiển thị — nó là tồn âm hoặc hàng vào nhầm kho.
        """
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
            # `name` là required trên stock.move nhưng KHÔNG có mặc định nào —
            # nó chỉ được điền nhờ onchange của form. Dòng tạo qua RPC, import,
            # hay test sẽ nổ "trường bắt buộc chưa được đặt" ở đúng chỗ khó đoán
            # nhất (xem cùng bẫy đã gặp với location_id ở 4 form phiếu kho).
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
            # Khoá ở TẦNG SERVER, không chỉ readonly trên view: bằng chứng mà
            # sửa được qua RPC thì lá chắn chỉ là trang trí. Các đường tự động
            # (tách dòng loại, sinh phiếu trả, hoá phế liệu) chạy dưới sudo hoặc
            # qua `create` nên không vướng.
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
