# -*- coding: utf-8 -*-
"""K4 — Màn Tồn kho đọc thẳng nguồn gốc lô. K7 — bán phế liệu.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §11.2, §7.3, §11.8.

Hai field related để thủ kho trả lời được "thép đang nằm kho này của ai, về ngày
nào" mà KHÔNG phải mở từng lô. Không lưu (`store=False`): dữ liệu đã nằm ở
stock.lot, nhân bản sang quant chỉ tạo thêm chỗ lệch.
"""

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # ── K8 — Cho Thủ kho áp kiểm kê mà KHÔNG cấp group_stock_manager ──────────
    def _apply_inventory(self):
        """Áp số kiểm kê ⇒ sinh phiếu điều chỉnh, tồn khớp số đếm.

        🔴 Native `stock.quant._apply_inventory` chốt cứng: chỉ
        `stock.group_stock_manager` mới validate được. Nhưng §8.3 CẤM cấp
        manager cho Thủ kho — manager mở kèm cả xoá quant, sửa vị trí, cấu hình
        tồn kho. Thay vì nới group (rủi ro rộng), kiểm vai trò Thủ kho tường
        minh rồi chạy phần thân native dưới quyền superuser — đúng khuôn "kiểm
        vai trò rồi nâng quyền" đã dùng ở K6 (`action_dlm_create_delivery`).

        `base.user_root` là thành viên `stock.group_stock_manager`
        (stock/security/stock_security.xml) nên `with_user(SUPERUSER_ID)` vượt
        được chốt native mà không phải chép logic sinh move.

        Một chốt này vá cho CẢ màn Kiểm kê (K8) lẫn màn Phế liệu (K7): mọi lối
        áp kiểm kê của Thủ kho đều đi qua đây. Vai trò khác giữ nguyên luật
        native (admin/CEO có manager thì rẽ thẳng super).
        """
        self._dlm_check_inventory_allowed()
        if (not self.user_has_groups("stock.group_stock_manager")
                and self.user_has_groups("dl_base.dl_group_warehouse")):
            return super(StockQuant, self.with_user(SUPERUSER_ID))._apply_inventory()
        return super()._apply_inventory()

    def _dlm_check_inventory_allowed(self):
        """RS-07 — Khu quá cảnh không cho đếm tay, kể cả admin.

        Domain của màn Kiểm kê đã ẩn hai khu này, nhưng ẩn khỏi danh sách không
        phải là chặn: quant vẫn tới được qua màn khác hay RPC. Và đây đúng là
        chỗ đáng chặn cứng — hàng ở khu Chờ trả NCC đang được một phiếu trả
        (nháp) tham chiếu tới; đếm về 0 là phiếu đó trỏ vào hàng không tồn tại.
        """
        blocked = self.location_id.filtered("dlm_no_inventory")
        if not blocked:
            return True
        raise UserError(_(
            "Không kiểm kê tay được ở khu quá cảnh: %s.\n\n"
            "Tồn ở đây đang gắn với chứng từ đang mở (phiếu kiểm, phiếu trả "
            "NCC). Muốn đổi số thì xử lý bằng chính phiếu đó — đếm tay sẽ xoá "
            "mất hàng mà chứng từ còn tham chiếu."
        ) % ", ".join(blocked.mapped("display_name")))

    dlm_supplier_id = fields.Many2one(
        related="lot_id.dlm_supplier_id", string="Nhà cung cấp", readonly=True)
    dlm_receipt_date = fields.Date(
        related="lot_id.dlm_receipt_date", string="Ngày nhập", readonly=True)

    # ── K14 — Số KHẢ DỤNG: một hàm, mọi chỗ đọc ──────────────────────────────
    @api.model
    def _dlm_available_qty(self, product, location, own_move_lines=None):
        """Số lấy được NGAY của `product` tại/dưới `location`.

        🔴 Khả dụng = tồn − phần đã bị phiếu khác giữ. Đọc thẳng `quantity` là
        ca hai người cùng bán một lô thép: cả hai đều thấy "còn 24", cả hai đều
        hứa giao. Dùng đúng hàm mà `action_assign` gọi khi giữ chỗ
        (`_get_available_quantity`) ⇒ số màn hình báo và số phiếu giữ được không
        bao giờ lệch. `strict=False` ⇒ gộp theo cây, khớp phạm vi giữ chỗ.

        `own_move_lines`: dòng của CHÍNH phiếu đang xét — cộng trả lại phần nó
        đang giữ, không thì phiếu vừa giữ chỗ xong lại tự báo mình thiếu hàng.

        🔴 Đây là NGUỒN SỰ THẬT DUY NHẤT cho câu "còn lấy được bao nhiêu". Ba
        chỗ đọc nó (dải cảnh báo phiếu chuyển · dải phiếu bán phế liệu · cột
        "Còn lấy được" trên từng dòng) phải cùng ra một số — hai chỗ trên cùng
        một màn nói hai số là lỗi người dùng không bao giờ báo, chỉ mất niềm tin.
        """
        if not product or not location:
            return 0.0
        con = self.sudo()._get_available_quantity(
            product, location, strict=False)
        if own_move_lines and location.parent_path:
            giu = own_move_lines.filtered(
                lambda ml: ml.product_id == product
                and ml.state not in ("done", "cancel")
                and ml.location_id.parent_path
                and ml.location_id.parent_path.startswith(location.parent_path))
            # quantity_product_uom (không phải `quantity`): quant tính theo ĐVT
            # gốc của sản phẩm, dòng phiếu có thể ghi theo ĐVT khác.
            con += sum(giu.mapped("quantity_product_uom"))
        return con

    @api.model
    def _dlm_on_hand_qty(self, product, location):
        """Tồn THỰC (chưa trừ chỗ giữ) — chỉ dùng để nói đúng LÝ DO khi thiếu.

        "Hết hàng" và "bị phiếu khác giữ hết" là hai việc phải làm khác hẳn
        nhau: một cái đi mua, một cái đi nói chuyện với người đang giữ. Gộp hai
        ca vào một câu là đẩy người dùng đi mua thứ đang nằm trong kho.
        """
        if not product or not location:
            return 0.0
        return sum(self.sudo().search([
            ("location_id", "child_of", location.id),
            ("product_id", "=", product.id),
        ]).mapped("quantity"))

    # ── K14 — "Ai đang giữ chỗ lô hàng này?" ─────────────────────────────────
    def action_dlm_open_reservations(self):
        """Phiếu đang giữ chỗ đúng dòng tồn này.

        Cột "Đang giữ chỗ" trả lời BAO NHIÊU; câu hỏi tiếp theo luôn là CHO AI —
        không trả lời được thì người dùng chỉ còn cách đoán, và cách đoán rẻ nhất
        là bán chồng. Một cú bấm ra thẳng phiếu + đơn hàng để còn thương lượng.
        """
        self.ensure_one()
        domain = [
            ("product_id", "=", self.product_id.id),
            ("location_id", "=", self.location_id.id),
            ("state", "not in", ("done", "cancel")),
        ]
        # Khớp lô CHỈ khi mặt hàng theo lô: hàng không theo lô có lot_id rỗng ở
        # cả hai bên, thêm điều kiện chỉ tổ lọc nhầm khi dữ liệu cũ lệch.
        if self.product_id.tracking != "none":
            domain.append(("lot_id", "=", self.lot_id.id))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.move.line",
            "name": _("Đang giữ chỗ — %s") % self.product_id.display_name,
            "view_mode": "tree",
            "views": [(self.env.ref(
                "dl_inventory.view_dl_reservation_tree").id, "tree")],
            "domain": domain,
            "target": "new",
        }

    # ── K7 — Phế liệu ────────────────────────────────────────────────────────
    # Đơn giá ở đây là GIÁ BÁN phế liệu (`list_price`), KHÔNG phải giá vốn — nên
    # không vi phạm §8.3 ("Thủ kho không thấy giá"). Thủ kho là người cân và
    # giao phế liệu cho bên thu mua, phải biết lô vụn này đáng bao nhiêu tiền.
    dlm_scrap_unit_price = fields.Float(
        related="product_id.list_price", string="Đơn giá", readonly=True,
        digits="Product Price")
    dlm_scrap_value = fields.Float(
        string="Thành tiền", compute="_compute_dlm_scrap_value",
        digits="Product Price")

    @api.depends("quantity", "product_id.list_price")
    def _compute_dlm_scrap_value(self):
        for quant in self:
            quant.dlm_scrap_value = quant.quantity * quant.product_id.list_price

    def action_dlm_to_scrap(self):
        """K12 — Hoá phế liệu các dòng tồn đang chọn ở màn Tồn kho.

        Lối vào thứ hai của phiếu [9] (§11.14): vật tư hỏng trong kho — gỉ, quá
        hạn, cong vênh — mà KHÔNG đòi được NCC (§6.5). Ca đòi được NCC thì phải
        đi đường phiếu trả, và đường đó cố ý khoá ở B1.
        """
        quants = self.filtered(
            lambda q: not float_is_zero(
                q.quantity, precision_rounding=q.product_uom_id.rounding or 0.01)
            and q.quantity > 0)
        if not quants:
            raise UserError(_(
                "Chọn ít nhất một dòng tồn còn hàng để hoá phế liệu."))
        cam = quants.location_id.filtered("dlm_no_inventory")
        if cam:
            raise UserError(_(
                "Không hoá phế liệu thẳng từ khu quá cảnh (%s) được.\n\n"
                "Hàng ở đó đang gắn với một phiếu đang mở. Mở đúng phiếu trả "
                "NCC rồi bấm <Chuyển thành phế liệu> trên đó — làm vậy mới giữ "
                "được dấu vết lô hàng này đi từ đâu ra."
            ) % ", ".join(cam.mapped("display_name")))
        picking = self.env["stock.picking"]._dlm_build_to_scrap(quants)
        return picking._dlm_open_picking(
            picking, _("Hoá phế liệu %s") % picking.name)

    def action_dlm_sell_scrap(self):
        """Tạo phiếu Bán phế liệu (nháp) từ các dòng tồn đang chọn.

        Để NHÁP và chưa gán khách: bán phế liệu là thoả thuận với bên thu mua
        (giá theo ngày, ai chở, cân ở đâu). Hệ thống dựng sẵn dòng hàng đúng số
        đang tồn; người dùng điền khách rồi mới xác nhận.
        """
        quants = self.filtered(
            lambda q: not float_is_zero(
                q.quantity, precision_rounding=q.product_uom_id.rounding or 0.01)
            and q.quantity > 0)
        if not quants:
            raise UserError(_(
                "Chọn ít nhất một dòng phế liệu còn tồn để lập phiếu bán."))

        picking_type = self.env.ref(
            "dl_inventory.picking_type_scrap_sale", raise_if_not_found=False)
        if not picking_type:
            raise UserError(_(
                "Chưa cấu hình loại hoạt động Bán phế liệu. "
                "Chạy lại: -u dl_inventory"))
        source = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_xuong_pl")
        destination = picking_type.default_location_dest_id

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "move_ids": [(0, 0, {
                "name": quant.product_id.display_name,
                "product_id": quant.product_id.id,
                "product_uom": quant.product_uom_id.id,
                "product_uom_qty": quant.quantity,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }) for quant in quants],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "name": _("Bán phế liệu %s") % picking.name,
            "views": [(self.env.ref(
                "dl_inventory.view_dl_scrap_sale_form").id, "form")],
        }
