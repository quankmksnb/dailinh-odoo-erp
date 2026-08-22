# -*- coding: utf-8 -*-
"""Rà soát quyền/màn hình cho 18 màn SCR-36..SCR-53 (rà soát FDS 2026-08-22).

Bộ này KHÔNG lặp lại những gì TestScreenBoundaries/TestAccessWarehouse/
TestLotTraceability/TestDispatch/TestInventoryAdjustment/... đã canh (định
tuyến form RS-02, lọc miền RS-04/05, Thủ kho tách khỏi Mua hàng, Thủ kho áp
được kiểm kê, một chủ sở hữu cho nút Điều phối...). Nó lấp ba khoảng trống còn
lại sau khi đọc hết các bộ trên:

  1. TẬP VAI TRÒ trên mỗi menu lá đúng NHƯ THIẾT KẾ (FDS), không chỉ "vai trò
     được khai có thấy menu không" (đã có TestMenuRoleDeclaration ở dl_base lo
     phần đó, chạy trên toàn app). Menu khai dư một vai trò, hoặc thiếu một
     vai trò so với FDS, không nổ lỗi gì — chỉ lệch thầm lặng với đặc tả.
  2. RANH GIỚI ĐỌC-KHÔNG-SỬA ở tầng ir.model.access/ir.rule cho những vai trò
     "có tên trong ô groups của FDS" nhưng chỉ để XEM (Mua hàng/CEO trên màn
     Kiểm hàng, Trưởng KD trên màn Giao hàng, CEO trên màn Phế liệu...). Có
     mặt trên menu không đồng nghĩa được thao tác — chưa bộ nào canh việc
     này bằng vai trò thật.
  3. Vài lát cắt "làm được việc" thật của vai trò ít được nhắc tới nhất trong
     toàn repo: CEO. Grep toàn bộ thư mục tests trước khi viết file này cho
     thấy `dl_group_ceo` chưa từng được gắn vào một `with_user()` nào — vai
     trò xuất hiện ở 8/18 màn nhưng chưa từng có một dòng test nào chạy DƯỚI
     quyền CEO thật.

Bối cảnh mã hoạt động (đọc thẳng từ security/ir.model.access.csv, ir_rule.xml,
views/*.py trước khi viết): stock.picking cấp write/create RỘNG cho Mua hàng
và Kỹ thuật ở tầng ACL, rồi ir.rule mới BÓ LẠI đúng một loại phiếu mỗi bên
(TR cho Mua hàng, NTP cho Kỹ thuật) — đọc ACL một mình sẽ tưởng họ sửa được
mọi phiếu kho.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged
from odoo.tools.safe_eval import safe_eval

from .common import DlInventoryCase


def _role_users(env, prefix, roles):
    """Tạo một user thật cho mỗi vai trò trong `roles` (dict tên->xmlid)."""
    users = {}
    for key, xmlid in roles.items():
        users[key] = env["res.users"].create({
            "name": "%s (%s)" % (prefix, key),
            "login": "%s_%s" % (prefix, key),
            "email": "%s.%s@test.local" % (prefix, key),
            "groups_id": [(6, 0, [env.ref(xmlid).id])],
        })
    return users


class DlScreenAccessCase(DlInventoryCase):
    """Tiện ích dùng chung: sinh phiếu thuộc TỪNG loại hoạt động của Kho."""

    def _menu_groups(self, xmlid):
        return set(self.env.ref(xmlid).groups_id.mapped(
            lambda g: g.get_external_id().get(g.id)))

    def _qc_ready(self, qty=100.0):
        receipt = self._receive(self._make_receipt(qty=qty), qty=qty)
        return receipt, self._qc_picking(receipt)

    def _reject_some(self, qc, passed=92.0, rejected=8.0):
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.write({
            "quantity": passed, "picked": True,
            "dlm_qty_rejected": rejected, "dlm_reject_reason": "defect"})
        qc.action_dlm_validate_qc()
        return qc._dlm_vendor_returns()[:1]

    def _scrap_picking_assigned(self):
        """Phiếu Bán phế liệu ở trạng thái `assigned` (cân → bán → gán)."""
        scrap = self.env["product.product"].create({
            "name": "Phế liệu (test màn hình)", "product_kind": "material",
        })
        scrap.tracking = "none"
        scrap.sudo().list_price = 5000.0
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": scrap.id, "location_id": self.loc_xuong_pl.id,
            "inventory_quantity": 20.0,
        })
        quant.action_apply_inventory()
        quants = self.env["stock.quant"].search([
            ("product_id", "=", scrap.id), ("location_id", "=", self.loc_xuong_pl.id)])
        action = quants.action_dlm_sell_scrap()
        picking = self.env["stock.picking"].browse(action["res_id"])
        picking.partner_id = self.env["res.partner"].create(
            {"name": "Vựa ve chai (test màn hình)"})
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _fg_receipt_picking_assigned(self):
        """Phiếu Nhập kho từ xưởng ở trạng thái `assigned`."""
        fg_type = self.env.ref("dl_inventory.picking_type_mo_receipt")
        finished = self.env["product.product"].create({
            "name": "Thành phẩm (test màn hình)", "product_kind": "manufactured",
        })
        finished.tracking = "none"
        picking = self.env["stock.picking"].create({
            "picking_type_id": fg_type.id,
            "location_id": fg_type.default_location_src_id.id,
            "location_dest_id": self.loc_tp.id,
            "move_ids": [(0, 0, {
                "product_id": finished.id,
                "product_uom_qty": 3.0,
                "product_uom": finished.uom_id.id,
                "dlm_move_kind": "output",
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking


# ============================================================ SCR-36
@tagged("post_install", "-at_install", "dl_inventory")
class TestPickingQueueAccess(DlScreenAccessCase):

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestPickingQueueAccess-001: menu "Hàng đợi" (SCR-36) phải khai đúng 3 vai
        trò của FDS: Thủ kho, Admin, CEO — không hơn không kém.

        TestMenuRoleDeclaration (dl_base) chỉ canh "vai trò đã khai có thấy menu không";
        test này canh việc khác — TẬP vai trò đó có đúng đặc tả hay đã lệch (thừa một vai
        trò, hoặc thiếu một vai trò) mà không ai để ý.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_todo"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo"})

    def test_phieu_tra_ncc_khong_lot_vao_hang_doi(self):
        """TC-INT-TestPickingQueueAccess-002: RS-04/05 áp cho chính màn Hàng đợi — phiếu Trả
        hàng NCC dù đã `assigned` cũng không được lọt vào, đó là việc của Mua hàng.
        """
        receipt, qc = self._qc_ready()
        tra_ncc = self._reject_some(qc)
        tra_ncc.action_confirm()
        tra_ncc.action_assign()
        self.assertEqual(tra_ncc.state, "assigned")

        domain = safe_eval(self.env.ref("dl_inventory.action_dl_picking_todo").domain)
        self.assertNotIn(tra_ncc, self.env["stock.picking"].search(domain))

    def test_phieu_ban_phe_lieu_khong_lot_vao_hang_doi(self):
        """TC-INT-TestPickingQueueAccess-003: phiếu Bán phế liệu đã `assigned` cũng không
        được lọt vào Hàng đợi — nó đi từ màn Phế liệu, không phải việc thường nhật của
        hàng đợi thủ kho.
        """
        ban_phe_lieu = self._scrap_picking_assigned()
        self.assertEqual(ban_phe_lieu.state, "assigned")

        domain = safe_eval(self.env.ref("dl_inventory.action_dl_picking_todo").domain)
        self.assertNotIn(ban_phe_lieu, self.env["stock.picking"].search(domain))

    def test_phieu_nhap_kho_tu_xuong_khong_lot_vao_hang_doi(self):
        """TC-INT-TestPickingQueueAccess-004: phiếu Nhập kho từ xưởng (NTP) đã `assigned`
        cũng không được lọt vào Hàng đợi của thủ kho — Kỹ thuật lập, thủ kho ký nhận qua
        luồng bàn giao riêng (K16), không qua hàng đợi này.
        """
        ntp = self._fg_receipt_picking_assigned()
        self.assertEqual(ntp.state, "assigned")

        domain = safe_eval(self.env.ref("dl_inventory.action_dl_picking_todo").domain)
        self.assertNotIn(ntp, self.env["stock.picking"].search(domain))


# ============================================================ SCR-37/38
@tagged("post_install", "-at_install", "dl_inventory")
class TestGoodsReceiptAccess(DlScreenAccessCase):

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestGoodsReceiptAccess-001: menu "Nhận hàng" (SCR-37/38) phải khai đúng 4
        vai trò của FDS: Thủ kho, Admin, Mua hàng, CEO.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_receipt"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_purchasing", "dl_base.dl_group_ceo"})

    def test_ceo_doc_duoc_phieu_nhan(self):
        """TC-INT-TestGoodsReceiptAccess-002: CEO thật (không phải superuser) phải đọc được
        phiếu nhận — FDS cho CEO có mặt ở màn này để theo dõi, chưa test nào từng chạy
        bằng vai trò CEO thật trong cả bộ test của module.
        """
        ceo = _role_users(
            self.env, "sr37", {"ceo": "dl_base.dl_group_ceo"})["ceo"]
        receipt = self._make_receipt()
        found = self.env["stock.picking"].with_user(ceo).search(
            [("id", "=", receipt.id)])
        self.assertEqual(found, receipt, "CEO phải đọc được phiếu nhận hàng NCC.")


# ============================================================ SCR-39/40
@tagged("post_install", "-at_install", "dl_inventory")
class TestQcInspectionAccess(DlScreenAccessCase):
    """RS-02 (định tuyến form) đã có ở TestScreenBoundaries. Bộ này canh RANH GIỚI
    ĐỌC/SỬA cho hai vai trò chỉ có mặt để XEM ở màn Kiểm hàng: Mua hàng và CEO.
    """

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestQcInspectionAccess-001: menu "Kiểm hàng" (SCR-39/40) phải khai đúng 4
        vai trò của FDS: Thủ kho, Admin, Mua hàng, CEO.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_qc"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_purchasing", "dl_base.dl_group_ceo"})

    def test_mua_hang_doc_duoc_phieu_kiem(self):
        """TC-INT-TestQcInspectionAccess-002: Mua hàng đọc được phiếu kiểm — họ cần biết
        NCC nào đang bị loại hàng để đàm phán, dù không phải người kiểm.
        """
        purchasing = _role_users(
            self.env, "sr39",
            {"purchasing": "dl_base.dl_group_purchasing"})["purchasing"]
        _receipt, qc = self._qc_ready()
        found = self.env["stock.picking"].with_user(purchasing).search(
            [("id", "=", qc.id)])
        self.assertEqual(found, qc, "Mua hàng phải đọc được phiếu kiểm hàng.")

    def test_mua_hang_khong_sua_duoc_phieu_kiem(self):
        """TC-INT-TestQcInspectionAccess-003: Mua hàng có ACL ghi rộng trên stock.picking ở
        tầng CSV, nhưng `rule_picking_purchasing_vendor_return` bó việc ghi lại đúng loại
        Trả hàng NCC (sequence_code='TR'). Phiếu kiểm mang mã 'KC' nên phải bị chặn.

        Đọc một mình ir.model.access.csv sẽ tưởng Mua hàng sửa được phiếu kiểm — chỉ đọc
        thêm ir.rule mới thấy ranh giới thật, và chưa bộ test nào khẳng định nó bằng vai
        trò thật trên chính phiếu KIỂM (test tương đương ở TestAccessWarehouse chỉ chạy
        trên phiếu NHẬN).
        """
        purchasing = _role_users(
            self.env, "sr39b",
            {"purchasing": "dl_base.dl_group_purchasing"})["purchasing"]
        _receipt, qc = self._qc_ready()
        with self.assertRaises(
                AccessError,
                msg="Mua hàng KHÔNG được sửa phiếu kiểm hàng (chỉ được sửa phiếu Trả NCC)."):
            qc.with_user(purchasing).write({"note": "sua trom"})

    def test_ceo_doc_duoc_nhung_khong_sua_duoc_phieu_kiem(self):
        """TC-INT-TestQcInspectionAccess-004: CEO có mặt trên menu Kiểm hàng để theo dõi,
        ACL của CEO trên stock.picking là `1,0,0,0` — đọc được, không ghi được.
        """
        ceo = _role_users(
            self.env, "sr39c", {"ceo": "dl_base.dl_group_ceo"})["ceo"]
        _receipt, qc = self._qc_ready()
        found = self.env["stock.picking"].with_user(ceo).search(
            [("id", "=", qc.id)])
        self.assertEqual(found, qc, "CEO phải đọc được phiếu kiểm hàng.")
        with self.assertRaises(AccessError):
            qc.with_user(ceo).write({"note": "sua trom"})


# ============================================================ SCR-41/42
@tagged("post_install", "-at_install", "dl_inventory")
class TestWorkshopReceiptAccess(DlScreenAccessCase):

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestWorkshopReceiptAccess-001: menu "Nhập kho từ xưởng" (SCR-41/42) phải
        khai đúng 4 vai trò của FDS: Thủ kho, Admin, CEO, Kỹ thuật.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_fg_receipt"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo", "dl_base.dl_group_tech"})

    def test_ky_thuat_khong_lap_duoc_phieu_chuyen_kho(self):
        """TC-INT-TestWorkshopReceiptAccess-002: `rule_picking_tech_fg_receipt_only` bó
        quyền ghi của Kỹ thuật lại đúng loại NTP. TestWorkshopBatch-011 đã chứng minh
        chiều THUẬN (Kỹ thuật lập được phiếu NTP); test này khoá chiều NGƯỢC — họ không
        được tạo phiếu Chuyển kho nội bộ, dù ACL model rộng y hệt.

        Đỏ = Kỹ thuật lập được phiếu Chuyển kho, đi lố hẳn sang việc của Thủ kho.
        """
        tech = _role_users(
            self.env, "sr41", {"tech": "dl_base.dl_group_tech"})["tech"]
        with self.assertRaises(AccessError):
            self.env["stock.picking"].with_user(tech).create({
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.loc_xuong.id,
            })


# ============================================================ SCR-43/44
@tagged("post_install", "-at_install", "dl_inventory")
class TestInternalTransferAccess(DlScreenAccessCase):
    """K15/TestWorkshopHandover đã chứng minh Kỹ thuật ký nhận được qua sudo có kiểm
    vai trò dù ACL chỉ đọc. Test còn thiếu là TẬP vai trò trên menu có đúng FDS.
    """

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestInternalTransferAccess-001: menu "Chuyển kho" (SCR-43/44) phải khai
        đúng 4 vai trò của FDS: Thủ kho, Admin, CEO, Kỹ thuật.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_transfer"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo", "dl_base.dl_group_tech"})


# ============================================================ SCR-45/46
@tagged("post_install", "-at_install", "dl_inventory")
class TestCustomerDeliveryAccess(DlScreenAccessCase):
    """test_delivery_link.py (18 test) không có lấy MỘT lần `with_user` — toàn bộ chạy
    bằng superuser. Ranh giới vai trò của màn Giao hàng vì thế chưa từng được thực thi.
    """

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestCustomerDeliveryAccess-001: menu "Giao hàng" (SCR-45/46) phải khai
        đúng 4 vai trò của FDS: Thủ kho, Admin, CEO, Trưởng phòng KD.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_picking_delivery"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo", "dl_base.dl_group_sales_manager"})

    def test_truong_kd_doc_duoc_phieu_giao(self):
        """TC-INT-TestCustomerDeliveryAccess-002: Trưởng phòng KD đọc được phiếu giao hàng
        (theo dõi tiến độ giao cho khách của mình), vai trò thật, không phải superuser.
        """
        sm = _role_users(
            self.env, "sr45",
            {"sm": "dl_base.dl_group_sales_manager"})["sm"]
        delivery = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.loc_tp.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
        })
        found = self.env["stock.picking"].with_user(sm).search(
            [("id", "=", delivery.id)])
        self.assertEqual(found, delivery, "Trưởng KD phải đọc được phiếu giao hàng.")

    def test_truong_kd_khong_sua_duoc_phieu_giao(self):
        """TC-INT-TestCustomerDeliveryAccess-003: ACL của Trưởng KD trên stock.picking là
        `1,0,0,0` — họ THEO DÕI màn Giao hàng, không THAO TÁC nó. Có tên trong groups= của
        menu không có nghĩa là sửa được — đây đúng là khoảng trống 2. nêu ở đầu file.
        """
        sm = _role_users(
            self.env, "sr45b",
            {"sm": "dl_base.dl_group_sales_manager"})["sm"]
        delivery = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.loc_tp.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
        })
        with self.assertRaises(AccessError):
            delivery.with_user(sm).write({"note": "sua trom"})


# ============================================================ SCR-47
@tagged("post_install", "-at_install", "dl_inventory")
class TestScrapSaleAccess(DlScreenAccessCase):
    """test_scrap_flow.py/test_to_scrap.py không có lấy MỘT lần `with_user` — toàn bộ
    chạy bằng superuser, kể cả tiêu chí verify K7 (bán 50kg, tồn về 0).
    """

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestScrapSaleAccess-001: menu "Phế liệu" (SCR-47) phải khai đúng 3 vai
        trò của FDS: Thủ kho, Admin, CEO.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_scrap"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo"})

    def test_thu_kho_ban_duoc_phe_lieu_bang_vai_tro_that(self):
        """TC-INT-TestScrapSaleAccess-002: tiêu chí verify K7 (test_can_thuc_te_50kg...)
        chạy bằng superuser — test này chạy lại đúng luồng dưới vai trò Thủ kho thật, vì
        nút "Bán phế liệu" gắn `groups=` và ACL tạo phiếu kho là thứ superuser không bao
        giờ chạm phải.
        """
        warehouse_user = _role_users(
            self.env, "sr47",
            {"wh": "dl_base.dl_group_warehouse"})["wh"]
        scrap = self.env["product.product"].create({
            "name": "Phế liệu (vai trò thật)", "product_kind": "material",
        })
        scrap.tracking = "none"
        scrap.sudo().list_price = 5000.0
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": scrap.id, "location_id": self.loc_xuong_pl.id,
            "inventory_quantity": 30.0,
        })
        quant.action_apply_inventory()

        quants_wh = self.env["stock.quant"].with_user(warehouse_user).search([
            ("product_id", "=", scrap.id), ("location_id", "=", self.loc_xuong_pl.id)])
        action = quants_wh.action_dlm_sell_scrap()
        picking = self.env["stock.picking"].with_user(warehouse_user).browse(
            action["res_id"])
        picking.partner_id = self.env["res.partner"].create(
            {"name": "Vựa ve chai (vai trò thật)"})
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 30.0
        picking.move_ids.picked = True
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        self.assertEqual(self._qty_at(self.loc_xuong_pl, scrap), 0.0)

    def test_ceo_khong_ban_duoc_phe_lieu(self):
        """TC-INT-TestScrapSaleAccess-003: CEO có mặt trên menu Phế liệu để theo dõi, nhưng
        ACL của CEO trên stock.quant/stock.picking đều `1,0,0,0` — không tạo được phiếu
        bán.
        """
        ceo = _role_users(
            self.env, "sr47b", {"ceo": "dl_base.dl_group_ceo"})["ceo"]
        scrap = self.env["product.product"].create({
            "name": "Phế liệu (CEO)", "product_kind": "material",
        })
        scrap.tracking = "none"
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": scrap.id, "location_id": self.loc_xuong_pl.id,
            "inventory_quantity": 10.0,
        })
        quant.action_apply_inventory()
        quants = self.env["stock.quant"].search([
            ("product_id", "=", scrap.id), ("location_id", "=", self.loc_xuong_pl.id)])

        with self.assertRaises(AccessError):
            quants.with_user(ceo).action_dlm_sell_scrap()


# ============================================================ SCR-48
@tagged("post_install", "-at_install", "dl_inventory")
class TestStockOnHandAccess(DlScreenAccessCase):

    _SIX_ROLES = {
        "wh": "dl_base.dl_group_warehouse",
        "admin": "dl_base.dl_group_admin",
        "pur": "dl_base.dl_group_purchasing",
        "tech": "dl_base.dl_group_tech",
        "ceo": "dl_base.dl_group_ceo",
        "sm": "dl_base.dl_group_sales_manager",
    }

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestStockOnHandAccess-001: menu "Tồn kho" (SCR-48) phải khai đúng 6 vai
        trò của FDS.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_stock_quant"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_purchasing", "dl_base.dl_group_tech",
             "dl_base.dl_group_ceo", "dl_base.dl_group_sales_manager"})

    def test_ca_sau_vai_tro_deu_doc_duoc_ton_kho(self):
        """TC-INT-TestStockOnHandAccess-002: cả 6 vai trò của FDS đều thực sự đọc được
        stock.quant bằng vai trò thật, không chỉ suy từ có mặt trên menu.
        """
        self._receive(self._make_receipt())
        users = _role_users(self.env, "sr48", self._SIX_ROLES)
        for key, user in users.items():
            found = self.env["stock.quant"].with_user(user).search(
                [("product_id", "=", self.material.id)], limit=1)
            self.assertTrue(
                found, "Vai trò '%s' phải đọc được màn Tồn kho." % key)

    def test_ba_van_doc_duoc_ton_kho_qua_acl_goc_cua_odoo(self):
        """TC-INT-TestStockOnHandAccess-003: PHÁT HIỆN LỆCH FDS-vs-code — BA/Sales không
        có tên trong FDS của màn này và không có dòng ACL riêng nào của dl_inventory cho
        stock.quant, nhưng ACL GỐC của module `stock`
        (`stock/security/ir.model.access.csv:access_stock_quant_all`) đã cấp quyền đọc
        stock.quant cho TOÀN BỘ `base.group_user` — mọi vai trò DL đều implied nhóm này
        (dl_base/security/groups.xml).

        Test này CHỦ Ý khẳng định đúng thực tế đang chạy (BA đọc được), không phải hành
        vi mong muốn: hàng rào 6-vai-trò của SCR-48 chỉ có thật ở TẦNG MENU (ẩn mục khỏi
        rail), KHÔNG có thật ở tầng dữ liệu — BA (hoặc bất kỳ vai trò nào tương lai không
        có trong danh sách) vẫn đọc được stock.quant qua ORM/API nếu có đường vào khác
        ngoài menu này. Ngược lại ở màn Lô hàng (SCR-49/50, xem TestLotAccess-003) ranh
        giới này có thật vì stock.lot không có ACL "mọi user" tương đương.
        """
        self._receive(self._make_receipt())
        ba = _role_users(
            self.env, "sr48b", {"ba": "dl_base.dl_group_ba"})["ba"]
        found = self.env["stock.quant"].with_user(ba).search(
            [("product_id", "=", self.material.id)], limit=1)
        self.assertTrue(
            found, "Ghi nhận đúng thực tế: BA đọc được stock.quant qua ACL gốc "
            "access_stock_quant_all, không phải qua ACL riêng của dl_inventory.")


# ============================================================ SCR-49/50
@tagged("post_install", "-at_install", "dl_inventory")
class TestLotAccess(DlScreenAccessCase):

    _SIX_ROLES = {
        "wh": "dl_base.dl_group_warehouse",
        "admin": "dl_base.dl_group_admin",
        "pur": "dl_base.dl_group_purchasing",
        "tech": "dl_base.dl_group_tech",
        "ceo": "dl_base.dl_group_ceo",
        "sm": "dl_base.dl_group_sales_manager",
    }

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestLotAccess-001: menu "Lô hàng" (SCR-49/50) phải khai đúng 6 vai trò
        của FDS, giống hệt màn Tồn kho.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_stock_lot"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_purchasing", "dl_base.dl_group_tech",
             "dl_base.dl_group_ceo", "dl_base.dl_group_sales_manager"})

    def test_ca_sau_vai_tro_deu_doc_duoc_lo_hang(self):
        """TC-INT-TestLotAccess-002: cả 6 vai trò của FDS đều thực sự đọc được stock.lot
        bằng vai trò thật.
        """
        picking = self._receive(self._make_receipt())
        lot = picking.move_line_ids.lot_id
        users = _role_users(self.env, "sr49", self._SIX_ROLES)
        for key, user in users.items():
            found = self.env["stock.lot"].with_user(user).search(
                [("id", "=", lot.id)])
            self.assertEqual(
                found, lot, "Vai trò '%s' phải đọc được màn Lô hàng." % key)

    def test_ba_khong_doc_duoc_lo_hang(self):
        """TC-INT-TestLotAccess-003: khác với stock.quant (xem TestStockOnHandAccess-003),
        stock.lot KHÔNG có ACL "mọi user" tương đương — ACL gốc của Odoo
        (`stock/security/ir.model.access.csv:access_stock_lot_user`) chỉ cấp cho
        `stock.group_stock_user`, mà chỉ Thủ kho được gắn nhóm kỹ thuật đó
        (groups_stock_link.xml). BA không có dòng ACL nào của model này ⇒ ranh giới
        6-vai-trò ở đây có thật cả ở tầng dữ liệu, không chỉ tầng menu.
        """
        picking = self._receive(self._make_receipt())
        lot = picking.move_line_ids.lot_id
        ba = _role_users(
            self.env, "sr49b", {"ba": "dl_base.dl_group_ba"})["ba"]
        with self.assertRaises(AccessError):
            self.env["stock.lot"].with_user(ba).search([("id", "=", lot.id)])


# ============================================================ SCR-51
@tagged("post_install", "-at_install", "dl_inventory")
class TestStockCountAccess(DlScreenAccessCase):
    """test_inventory_adjustment.py đã chứng minh Thủ kho ÁP được kiểm kê mà không có
    group_stock_manager. Ba khoảng trống còn lại: (a) action này thật sự KHÔNG có
    menuitem nào — chỉ vào được bằng nút, (b) nút đó khai đúng 2 vai trò FDS, và (c) một
    vai trò có mặt ở Tồn kho (SCR-48) nhưng KHÔNG có trong SCR-51 (Mua hàng/Kỹ thuật)
    không áp được kiểm kê dù đọc được màn Tồn kho.
    """

    def test_khong_co_menuitem_nao_tro_toi_kiem_ke(self):
        """TC-INT-TestStockCountAccess-001: FDS ghi rõ SCR-51 "NO menuitem — reached only
        via a button". Nếu về sau ai đó thêm nhầm một `<menuitem>` trỏ tới action này,
        Kiểm kê sẽ có hai lối vào và menu mới có thể quên khai đúng 2 vai trò của nút.
        """
        action = self.env.ref("dl_inventory.action_dl_stock_inventory")
        menus = self.env["ir.ui.menu"].with_context(
            **{"ir.ui.menu.full_list": True}).search(
                [("action", "=", "ir.actions.act_window,%d" % action.id)])
        self.assertFalse(
            menus, "Kiểm kê (SCR-51) phải CHỈ vào được bằng nút trên màn Tồn kho, "
            "không qua menuitem nào.")

    def test_nut_kiem_ke_dung_hai_vai_tro_fds(self):
        """TC-INT-TestStockCountAccess-002: nút "Kiểm kê" trên màn Tồn kho phải khai đúng
        2 vai trò của FDS: Thủ kho, Admin — không có CEO/Mua hàng/Kỹ thuật dù các vai trò
        đó đọc được chính màn Tồn kho.

        `%(xmlid)d` trong arch được Odoo GIẢI NGAY lúc nạp dữ liệu XML thành số id thật
        (không còn chuỗi 'action_dl_stock_inventory' trong `arch` đã lưu) — so bằng
        chuỗi id thật của action, không so bằng tên gọi.
        """
        from lxml import etree

        action = self.env.ref("dl_inventory.action_dl_stock_inventory")
        arch = self.env.ref("dl_inventory.view_dl_stock_quant_tree").arch
        button = etree.fromstring(arch).find('.//button[@string="Kiểm kê"]')
        self.assertIsNotNone(button, "Không tìm thấy nút Kiểm kê trên màn Tồn kho.")
        self.assertEqual(button.get("type"), "action")
        self.assertEqual(
            button.get("name"), str(action.id),
            "Nút Kiểm kê phải trỏ đúng action_dl_stock_inventory.")
        self.assertEqual(
            set(button.get("groups", "").split(",")),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin"},
            "Nút Kiểm kê phải khai đúng 2 vai trò Thủ kho/Admin, không hơn không kém.")

    def test_mua_hang_va_ky_thuat_doc_duoc_ton_nhung_khong_ap_duoc_kiem_ke(self):
        """TC-INT-TestStockCountAccess-003: Mua hàng và Kỹ thuật đều có mặt ở màn Tồn kho
        (SCR-48) nhưng KHÔNG có trong SCR-51. ACL của cả hai trên stock.quant là
        `1,0,0,0` (chỉ đọc) nên không ghi được `inventory_quantity` — ranh giới "xem tồn"
        khác "sửa tồn" có thật ở tầng ACL, không chỉ ở việc ẩn nút.
        """
        item = self.env["product.product"].create({
            "name": "Hàng thương mại (SCR-51)", "product_kind": "trading",
        })
        item.tracking = "none"
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": item.id, "location_id": self.loc_kho.id,
            "inventory_quantity": 15.0,
        })
        quant.action_apply_inventory()
        quant = self.env["stock.quant"].search([
            ("product_id", "=", item.id), ("location_id", "=", self.loc_kho.id)])

        users = _role_users(self.env, "sr51", {
            "pur": "dl_base.dl_group_purchasing",
            "tech": "dl_base.dl_group_tech",
        })
        for key, user in users.items():
            found = self.env["stock.quant"].with_user(user).search(
                [("id", "=", quant.id)])
            self.assertEqual(
                found, quant, "Vai trò '%s' phải đọc được màn Tồn kho." % key)
            quant_as_user = quant.with_user(user).with_context(inventory_mode=True)
            with self.assertRaises(
                    AccessError,
                    msg="Vai trò '%s' KHÔNG được áp kiểm kê." % key):
                quant_as_user.write(
                    {"inventory_quantity": 18.0, "inventory_quantity_set": True})


# ============================================================ SCR-52/53
@tagged("post_install", "-at_install", "dl_inventory")
class TestDispatchAccess(DlScreenAccessCase):
    """test_dispatch.py đã canh U-4 (một chủ sở hữu: BA/Sales không bấm được nút Điều
    phối) và đã chạy bằng vai trò Thủ kho thật. Ba khoảng trống còn lại: (a) TẬP vai trò
    trên menu, (b) domain nào làm màn này thành "view lọc theo dl.sale.order liên quan
    tới điều phối" chứ không phải mọi đơn bán, và (c) CEO — vai trò dự phòng của
    `_DLM_DISPATCH_ROLES` — chưa từng chạy qua nút Điều phối bằng vai trò thật.
    """

    def test_tap_vai_tro_dung_nhu_fds(self):
        """TC-INT-TestDispatchAccess-001: menu "Điều phối đơn hàng" (SCR-52/53) phải khai
        đúng 3 vai trò của FDS: Thủ kho, Admin, CEO.
        """
        self.assertEqual(
            self._menu_groups("dl_inventory.menu_dl_dispatch_queue"),
            {"dl_base.dl_group_warehouse", "dl_base.dl_group_admin",
             "dl_base.dl_group_ceo"})

    def test_domain_chi_lay_don_da_xac_nhan(self):
        """TC-INT-TestDispatchAccess-002: action_dl_dispatch_queue phải lọc còn đúng đơn
        `state == 'confirmed'` — đơn Nháp/Hoàn tất/Đã huỷ không phải việc "chờ điều
        phối", lọt vào là mời thủ kho giữ chỗ cho một cam kết chưa tồn tại hoặc xong rồi.
        """
        customer = self.env["res.partner"].create({
            "name": "Khách hàng (SCR-52)", "partner_role": "customer",
            "mobile": "0900000099"})
        orders = {
            state: self.env["dl.sale.order"].create({
                "partner_id": customer.id, "state": state,
            })
            for state in ("draft", "confirmed", "done", "cancelled")
        }

        domain = safe_eval(
            self.env.ref("dl_inventory.action_dl_dispatch_queue").domain)
        queue = self.env["dl.sale.order"].search(
            domain + [("id", "in", [o.id for o in orders.values()])])

        self.assertEqual(queue, orders["confirmed"])

    def test_ceo_dieu_phoi_thanh_cong_bang_vai_tro_that(self):
        """TC-INT-TestDispatchAccess-003: CEO nằm trong `_DLM_DISPATCH_ROLES` làm vai trò
        DỰ PHÒNG cho Thủ kho/Admin — grep toàn bộ thư mục tests trước khi viết file này
        cho thấy chưa dòng nào từng chạy `action_dlm_dispatch` bằng CEO thật.
        """
        ceo = _role_users(
            self.env, "sr52", {"ceo": "dl_base.dl_group_ceo"})["ceo"]
        customer = self.env["res.partner"].create({
            "name": "Khách hàng (SCR-52 CEO)", "partner_role": "customer",
            "mobile": "0900000098"})
        ban = self.env["product.product"].create({
            "name": "Bàn học sinh (SCR-52 CEO)", "product_kind": "manufactured",
        })
        bom = self.env["dl.bom"].create({
            "product_id": ban.id, "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 2.0,
                "is_override": True,
            })],
        })
        bom.status = "confirmed"
        order = self.env["dl.sale.order"].create({
            "partner_id": customer.id, "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": ban.display_name, "product_id": ban.id, "qty": 3.0,
                "line_type": "manufactured", "bom_id": bom.id,
            })],
        })
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": ban.id, "location_id": self.loc_tp.id,
            "inventory_quantity": 10.0,
        })
        quant.action_apply_inventory()

        order.with_user(ceo).action_dlm_dispatch()

        delivery = order.dlm_picking_ids.filtered(
            lambda p: p.picking_type_id.sequence_code == "GH")
        self.assertEqual(
            len(delivery), 1, "CEO phải điều phối ra đúng phiếu giao — đủ thành phẩm "
            "trong kho thì không cấp vật tư.")

    def test_truong_kd_khong_dieu_phoi_duoc(self):
        """TC-INT-TestDispatchAccess-004: mở rộng U-4 sang một vai trò khác ngoài BA —
        Trưởng phòng KD cũng KHÔNG được trong `_DLM_DISPATCH_ROLES`, dù họ có ACL ghi khá
        rộng trên dl.sale.order (thừa hưởng từ dl_sale). Một chủ sở hữu cho bước điều
        phối nghĩa là MỌI vai trò ngoài Thủ kho/Admin/CEO đều bị chặn, không chỉ BA.
        """
        sm = _role_users(
            self.env, "sr52b",
            {"sm": "dl_base.dl_group_sales_manager"})["sm"]
        customer = self.env["res.partner"].create({
            "name": "Khách hàng (SCR-52 SM)", "partner_role": "customer",
            "mobile": "0900000097"})
        order = self.env["dl.sale.order"].create({
            "partner_id": customer.id, "state": "confirmed",
        })
        with self.assertRaises(UserError):
            order.with_user(sm)._dlm_check_dispatch_allowed()
