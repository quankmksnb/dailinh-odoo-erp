# -*- coding: utf-8 -*-
"""Vòng đời SP thương mại: TPKD tạo thì Mua hàng nhập giá vốn thì TPKD chốt giá bán.

Chỗ dễ vỡ nhất ở đây là ranh giới vai trò: quyền tạo SP thương mại và chốt Giá bán vừa
chuyển hẳn từ Sales (BA) lên Trưởng phòng kinh doanh (2026-08-15).

Mọi thao tác đi qua `with_user` thật. `self.env` của TransactionCase là superuser
(`env.su` = True) nên các guard `if not self.env.su` sẽ bị bỏ qua — test viết bằng env
mặc định sẽ xanh giả, kể cả khi phân quyền hỏng hoàn toàn.
"""

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

_ACT_SUPPLIER_PRICE = "Thiết lập giá nhà cung cấp cho sản phẩm thương mại mới"
_ACT_SALE_PRICE = "Chốt giá bán cho sản phẩm thương mại"
_ACT_REVIEW_SALE_PRICE = "Xem lại giá bán — giá vốn đã vượt giá bán"


@tagged("post_install", "-at_install", "dl_product")
class TestTradingOwnership(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tpkd = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test SP)", "login": "tpkd_trading_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_sales_manager").id])],
        })
        cls.sales = cls.env["res.users"].create({
            "name": "Sales (test SP)", "login": "sales_trading_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ba").id])],
        })
        cls.mua_hang = cls.env["res.users"].create({
            "name": "Mua hàng (test SP)", "login": "muahang_trading_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })
        # `mobile` bắt buộc với partner Cá nhân (_check_partner_contact_channel
        # ở dl_partner) — thiếu là chết ở setUpClass chứ không phải ở ca đang đo.
        cls.vendor = cls.env["res.partner"].create({
            "name": "NCC máy bơm (test SP)", "partner_role": "supplier",
            "mobile": "0900000101"})

    # ------------------------------------------------------------------
    def _new_trading(self, user):
        """SP thương mại NHÁP do `user` tạo (đúng đường người dùng đi trên form:
        action đặt sẵn loại 'trading' + trạng thái Nháp qua context default_*)."""
        return self.env["product.product"].with_user(user).create({
            "name": "Máy bơm nước 1HP (test SP)",
            "product_kind": "trading",
            "dlm_lifecycle_state": "draft",
        })

    def _apply_vendor_price(self, product, price=100000.0):
        """Mua hàng nhập giá NCC rồi Duyệt — duyệt tự áp dụng thì sinh Giá vốn.
        """
        seller = self.env["product.supplierinfo"].with_user(self.mua_hang).create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "price": price,
            "date_start": fields.Date.today(),
        })
        seller.action_approve()
        product.invalidate_recordset()
        return seller

    def _raise_vendor_price(self, product, price):
        """NCC tăng giá: thêm bảng giá mới, duyệt rồi áp dụng (tự bỏ áp dụng bảng giá cũ)
        thì giá vốn tham chiếu nhảy theo.
        """
        seller = self.env["product.supplierinfo"].with_user(self.mua_hang).create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "price": price,
            "date_start": fields.Date.today(),
        })
        seller.action_approve()
        seller.action_set_applied()
        product.invalidate_recordset()
        return seller

    def _todos(self, product, summary):
        return self.env["mail.activity"].search([
            ("res_model", "=", "product.product"),
            ("res_id", "=", product.id),
            ("summary", "=", summary),
        ])

    # ── Ai được tạo SP thương mại ──────────────────────────────────────
    def test_tpkd_tao_duoc_sp_thuong_mai(self):
        """TC-INT-TestTradingOwnership-001.
        """
        product = self._new_trading(self.tpkd)

        self.assertEqual(product.product_kind, "trading")
        self.assertTrue(product.default_code.startswith("TM-"))

    def test_sales_khong_con_tao_duoc_sp_thuong_mai(self):
        """TC-INT-TestTradingOwnership-002: Ranh giới vừa đổi: BA chỉ còn XEM sản phẩm để
        làm RFQ/báo giá.

        Đỏ = ai cũng đẻ được hàng thương mại, TPKD hết là chủ sở hữu danh mục.
        """
        with self.assertRaises(AccessError):
            self._new_trading(self.sales)

    def test_sales_van_doc_duoc_san_pham(self):
        """TC-INT-TestTradingOwnership-003: Chặn ghi nhưng không được chặn đọc — BA cần
        chọn SP khi làm báo giá.
        """
        product = self._new_trading(self.tpkd)
        self.env.invalidate_all()

        self.assertEqual(
            product.with_user(self.sales).read(["name"])[0]["name"],
            "Máy bơm nước 1HP (test SP)")

    # ── Báo việc hai chiều với Mua hàng ────────────────────────────────
    def test_tao_sp_bao_viec_cho_mua_hang(self):
        """TC-INT-TestTradingOwnership-004.
        """
        product = self._new_trading(self.tpkd)

        todos = self._todos(product, _ACT_SUPPLIER_PRICE)
        self.assertIn(self.mua_hang, todos.mapped("user_id"))

    def test_ap_gia_ncc_dong_viec_mua_hang_va_bao_tpkd(self):
        """TC-INT-TestTradingOwnership-005: Khép vòng: Mua hàng xong việc thì việc của họ
        đóng, TPKD được gọi tên.

        Đỏ = TPKD phải tự mò xem Mua hàng đã nhập giá chưa, còn hòm việc Mua hàng thì
        treo mãi một dòng đã làm xong.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product)

        self.assertGreater(product.standard_price, 0.0)
        self.assertFalse(self._todos(product, _ACT_SUPPLIER_PRICE))
        self.assertIn(self.tpkd, self._todos(product, _ACT_SALE_PRICE).mapped("user_id"))

    def test_khong_bao_trung_khi_ap_gia_lai(self):
        """TC-INT-TestTradingOwnership-006: Bỏ áp dụng rồi áp dụng lại không được đẻ thêm
        việc thứ hai cho TPKD.
        """
        product = self._new_trading(self.tpkd)
        seller = self._apply_vendor_price(product)

        seller.action_unset_applied()
        seller.action_set_applied()
        product.invalidate_recordset()

        self.assertEqual(
            len(self._todos(product, _ACT_SALE_PRICE).filtered(
                lambda a: a.user_id == self.tpkd)), 1)

    # ── Mua trước thì bán sau ────────────────────────────────────────────
    def test_gia_ban_khoa_toi_khi_co_gia_von(self):
        """TC-INT-TestTradingOwnership-007.
        """
        product = self._new_trading(self.tpkd)
        as_tpkd = product.with_user(self.tpkd)
        as_tpkd.invalidate_recordset()

        self.assertFalse(as_tpkd.dlm_can_edit_sale_price)

        self._apply_vendor_price(product)
        as_tpkd.invalidate_recordset()

        self.assertTrue(as_tpkd.dlm_can_edit_sale_price)

    def test_sales_khong_chot_duoc_gia_ban(self):
        """TC-INT-TestTradingOwnership-008: Trọng tâm của thay đổi: giá niêm yết là quyết
        định của TPKD.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product)

        with self.assertRaises(AccessError):
            product.with_user(self.sales).write({"list_price": 150000.0})

    def test_tpkd_chot_gia_ban_va_kich_hoat(self):
        """TC-INT-TestTradingOwnership-009: Trọn vòng: tạo thì Mua hàng áp giá thì TPKD
        chốt giá bán thì kích hoạt.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product)

        as_tpkd = product.with_user(self.tpkd)
        as_tpkd.write({"list_price": 150000.0})
        as_tpkd.action_lifecycle_activate()
        product.invalidate_recordset()

        self.assertEqual(product.dlm_lifecycle_state, "active")
        # Việc "Chốt giá bán" đã xong thì hòm việc TPKD phải sạch.
        self.assertFalse(self._todos(product, _ACT_SALE_PRICE))

    # ── Giá bán phải CAO HƠN giá vốn (ràng buộc tầng server) ───────────
    def _active_trading(self, cost=100000.0, price=150000.0):
        """SP thương mại ĐANG BÁN: đã có giá NCC, đã chốt giá bán, đã kích hoạt."""
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product, cost)
        as_tpkd = product.with_user(self.tpkd)
        as_tpkd.write({"list_price": price})
        as_tpkd.action_lifecycle_activate()
        product.invalidate_recordset()
        return product

    def test_gia_ban_duoi_gia_von_bi_chan_o_server(self):
        """TC-INT-TestTradingOwnership-010: Đường ghi không qua form (import/API/code)
        trước đây lọt hết — controller JS chỉ sống trong form Sản phẩm.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product, 100000.0)

        # Bắt ĐÚNG lỗi giá — assertRaises trần sẽ xanh cả khi nổ vì ràng buộc
        # khác (nhóm SP, mã SP...), tức là xanh giả.
        with self.assertRaises(ValidationError) as err:
            product.sudo().write({"list_price": 90000.0})

        self.assertIn("phải CAO HƠN Giá vốn tham chiếu", str(err.exception))

    def test_gia_ban_bang_gia_von_bi_chan(self):
        """TC-INT-TestTradingOwnership-011: Bán ngang giá vốn (lãi 0) cũng không hợp lệ —
        luật chốt 2026-08-15.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product, 100000.0)

        with self.assertRaises(ValidationError) as err:
            product.sudo().write({"list_price": 100000.0})

        self.assertIn("bán ngang giá vốn", str(err.exception))

    def test_chua_co_gia_von_thi_khong_chan_gia_ban(self):
        """TC-INT-TestTradingOwnership-012: Chưa có giá vốn thì chưa tới lúc so (mua trước
        thì bán sau).

        Đỏ = ràng buộc bắn ngay lúc tạo SP, tpkd không tạo nổi sản phẩm nào.
        """
        product = self._new_trading(self.tpkd)

        product.sudo().write({"list_price": 50000.0})

        self.assertEqual(product.list_price, 50000.0)

    def test_mua_hang_van_ap_duoc_gia_von_vuot_gia_ban(self):
        """TC-INT-TestTradingOwnership-013: Cố ý không chặn Mua hàng: họ chỉ ghi nhận giá
        thật của NCC.

        Đỏ = giá thép lên, Mua hàng bị kẹt không nhập nổi giá mới, phải đi nhắc TPKD thủ
        công — chặn đúng luật nhưng chặn nhầm người.
        """
        product = self._active_trading(cost=100000.0, price=150000.0)

        self._raise_vendor_price(product, 200000.0)

        self.assertEqual(product.standard_price, 200000.0)

    def test_gia_von_vuot_thi_bao_viec_cho_tpkd(self):
        """TC-INT-TestTradingOwnership-014.
        """
        product = self._active_trading(cost=100000.0, price=150000.0)

        self._raise_vendor_price(product, 200000.0)

        self.assertTrue(product.dlm_price_below_cost)
        self.assertIn(
            self.tpkd,
            self._todos(product, _ACT_REVIEW_SALE_PRICE).mapped("user_id"))

    def test_tpkd_chot_lai_gia_thi_dong_viec(self):
        """TC-INT-TestTradingOwnership-015.
        """
        product = self._active_trading(cost=100000.0, price=150000.0)
        self._raise_vendor_price(product, 200000.0)

        product.with_user(self.tpkd).write({"list_price": 260000.0})
        product.invalidate_recordset()

        self.assertFalse(product.dlm_price_below_cost)
        self.assertFalse(self._todos(product, _ACT_REVIEW_SALE_PRICE))

    def test_sales_khong_kich_hoat_duoc(self):
        """TC-INT-TestTradingOwnership-016.
        """
        product = self._new_trading(self.tpkd)
        self._apply_vendor_price(product)
        product.sudo().write({"list_price": 150000.0})

        with self.assertRaises(AccessError):
            product.with_user(self.sales).action_lifecycle_activate()
