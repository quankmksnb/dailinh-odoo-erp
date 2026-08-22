# -*- coding: utf-8 -*-
"""SCR-54..57 — màn Đơn mua hàng, hàng đợi Hỏi giá, và Trả hàng NCC.

`test_access_purchase.py` đã canh chỗ rò GIÁ (kiểm soát chéo thủ kho/mua hàng).
File này canh một lớp khác: đúng vai trò nào mở được MÀN nào, và CEO thật sự
làm được gì trên màn đó — không suy từ `groups=` trên nút hay từ tên view, mà
đọc thẳng ACL/ir.rule/arch, vì repo này đã nhiều lần thấy ba thứ đó lệch nhau.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import tagged
from odoo.tools.safe_eval import safe_eval

from .common import DlPurchaseCase

_ROLE_XMLIDS = {
    "purchasing": "dl_base.dl_group_purchasing",
    "admin": "dl_base.dl_group_admin",
    "ceo": "dl_base.dl_group_ceo",
    "warehouse": "dl_base.dl_group_warehouse",
    "tech": "dl_base.dl_group_tech",
    "ba": "dl_base.dl_group_ba",
    "sales_manager": "dl_base.dl_group_sales_manager",
}


class _RoleUsersCase(DlPurchaseCase):
    """Một user THẬT cho mỗi vai trò — chỉ user thật mới kéo theo implied_ids
    (base.group_user...) quyết định phần lớn quyền đọc nền, và chỉ user thật
    mới đi qua `_visible_menu_ids` đúng như trên UI.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.role_users = {}
        for key, xmlid in _ROLE_XMLIDS.items():
            group = cls.env.ref(xmlid)
            user = cls.env["res.users"].create({
                "name": "%s (screen access test)" % group.name,
                "login": "dlm_screen_%s" % key,
                "groups_id": [(6, 0, [group.id])],
            })
            cls.role_users[key] = user


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseOrderScreenAccess(_RoleUsersCase):
    """SCR-54 (danh sách) / SCR-55 (chi tiết) — model `dl.purchase.order`."""

    def test_mua_hang_admin_ceo_mo_duoc_ca_menu_lan_du_lieu(self):
        """TC-INT-TestPurchaseOrderScreenAccess-001: cả ba vai trò khai trên
        `menu_dl_purchase_order` phải THỰC SỰ thấy menu (không bị Odoo tự ẩn vì
        thiếu ACL) và đọc được đơn mua — đúng những gì FDS mô tả cho SCR-54/55.
        """
        order = self._mk_po([(self.thep, 5.0, 100000.0)])
        menu = self.env.ref("dl_purchase.menu_dl_purchase_order")
        for key in ("purchasing", "admin", "ceo"):
            user = self.role_users[key]
            visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
            self.assertIn(menu.id, visible,
                          "Vai trò %s khai trên menu nhưng Odoo ẩn mất." % key)
            ten = order.with_user(user).read(["name"])[0]["name"]
            self.assertEqual(ten, order.name)

    def test_vai_tro_khong_co_dong_acl_bi_chan_that(self):
        """TC-INT-TestPurchaseOrderScreenAccess-002: Kỹ thuật, Trưởng KD, BA —
        ba vai trò không có dòng ACL nào cho `dl.purchase.order` — phải bị
        chặn thật (AccessError) chứ không phải chỉ ẩn menu.

        Thủ kho đã được canh riêng ở TC-INT-TestPurchaseAccess-002 (kiểm soát
        chéo nhận hàng/đặt hàng); không lặp lại ở đây.
        """
        order = self._mk_po([(self.thep, 5.0, 100000.0)])
        menu = self.env.ref("dl_purchase.menu_dl_purchase_order")
        for key in ("tech", "ba", "sales_manager"):
            user = self.role_users[key]
            visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
            self.assertNotIn(menu.id, visible,
                             "Vai trò %s không có ACL mà vẫn thấy menu." % key)
            with self.assertRaises(AccessError):
                order.with_user(user).read(["name"])

    def test_ceo_thuc_su_sua_va_tao_duoc_khong_chi_xem(self):
        """TC-INT-TestPurchaseOrderScreenAccess-003: khác với nhiều màn khác
        trong repo (nơi CEO chỉ đọc dù nút vẫn sáng), ACL của
        `dl.purchase.order` cho CEO write=1/create=1 thật — đúng với việc CEO
        là người bấm "Trình Giám đốc duyệt" rồi tự duyệt đơn của mình.
        """
        order = self._mk_po([(self.thep, 5.0, 100000.0)])
        order.with_user(self.role_users["ceo"]).write(
            {"note": "CEO tự sửa ghi chú"})
        self.assertEqual(order.note, "CEO tự sửa ghi chú")

        moi = self.env["dl.purchase.order"].with_user(
            self.role_users["ceo"]).create({
                "partner_id": self.vendor.id,
                "line_ids": [(0, 0, {
                    "product_id": self.thep.id, "qty": 3.0,
                    "price_unit": 90000.0,
                })],
            })
        self.assertTrue(moi.exists(), "CEO tạo đơn mua mới nhưng bị chặn.")

    def test_ceo_khong_xoa_duoc_don_mua(self):
        """TC-INT-TestPurchaseOrderScreenAccess-004: `perm_unlink=0` cho CEO —
        ranh giới còn lại CEO không vượt qua được trên màn này.
        """
        order = self._mk_po([(self.thep, 5.0, 100000.0)])
        with self.assertRaises(AccessError):
            order.with_user(self.role_users["ceo"]).unlink()

    def test_nut_chot_don_khai_dung_ba_vai_tro_tren_arch(self):
        """TC-INT-TestPurchaseOrderScreenAccess-005: canh hồi quy cho form —
        nút CTA chính (Chốt đơn) không được âm thầm mở rộng/thu hẹp nhóm so
        với đúng ba vai trò FDS khai.
        """
        arch = self.env.ref("dl_purchase.view_dl_purchase_order_form").arch
        self.assertIn(
            'name="action_dlm_confirm" string="Chốt đơn"', arch)
        idx = arch.index('name="action_dlm_confirm" string="Chốt đơn"')
        doan = arch[idx:idx + 400]
        self.assertIn(
            "groups=\"dl_base.dl_group_purchasing,dl_base.dl_group_admin,"
            "dl_base.dl_group_ceo\"", doan,
            "Nút Chốt đơn lệch nhóm so với Mua hàng/Admin/CEO.")


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseRfqQueueScreen(DlPurchaseCase):
    """Màn "Hỏi giá chờ trả lời" (`action_dl_purchase_rfq_queue`) — cùng
    model/nhóm với SCR-54 nhưng KHÔNG có dòng FDS riêng. Domain của nó và của
    danh sách chính loại trừ nhau thật (không chỉ khác bộ lọc mặc định), nên
    đây là một màn thật cần được FDS ghi nhận, không phải trùng lặp SCR-54.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.quo = cls.env["dl.quotation"].create({
            "partner_id": cls.customer.id})

    def _don_hoi_gia(self):
        """Đơn hỏi giá thật: sinh thẳng ở `sent` kèm `dlm_quotation_id`, đúng
        cách `action_dlm_request_vendor_quote` tạo (quotation_pricing_ext.py) —
        không đi qua `action_dlm_send`.
        """
        order = self._mk_po([(self.thep, 10.0, 200000.0)])
        order.write({"state": "sent", "dlm_quotation_id": self.quo.id})
        return order

    def test_hang_doi_rfq_chi_lay_don_da_gui_va_co_bao_gia_nguon(self):
        """TC-INT-TestPurchaseRfqQueueScreen-001: domain của hàng đợi chỉ khớp
        đơn `sent` VÀ có `dlm_quotation_id` — đơn mua chủ động (không có báo
        giá nguồn) hay đơn còn nháp không được lọt vào đây.
        """
        don_rfq = self._don_hoi_gia()
        don_sent_thuong = self._mk_po([(self.thep, 10.0, 200000.0)])
        don_sent_thuong.write({"state": "sent"})
        don_nhap = self._mk_po([(self.thep, 10.0, 200000.0)])

        domain = safe_eval(
            self.env.ref("dl_purchase.action_dl_purchase_rfq_queue").domain)
        ket_qua = self.env["dl.purchase.order"].search(domain)

        self.assertIn(don_rfq, ket_qua)
        self.assertNotIn(don_sent_thuong, ket_qua,
                         "Đơn mua chủ động (không báo giá nguồn) lọt vào hàng "
                         "đợi Hỏi giá.")
        self.assertNotIn(don_nhap, ket_qua)

    def test_danh_sach_chinh_khong_lan_don_hoi_gia_dang_cho(self):
        """TC-INT-TestPurchaseRfqQueueScreen-002: chiều ngược lại — danh sách
        chính (SCR-54) phải GIẤU đúng đơn đang nằm ở hàng đợi Hỏi giá, còn đơn
        nháp và đơn mua chủ động đã gửi thì vẫn phải thấy ở đây. Hai domain
        không chỉ khác bộ lọc mặc định mà loại trừ nhau thật.
        """
        don_rfq = self._don_hoi_gia()
        don_sent_thuong = self._mk_po([(self.thep, 10.0, 200000.0)])
        don_sent_thuong.write({"state": "sent"})
        don_nhap = self._mk_po([(self.thep, 10.0, 200000.0)])

        domain = safe_eval(
            self.env.ref("dl_purchase.action_dl_purchase_order").domain)
        ket_qua = self.env["dl.purchase.order"].search(domain)

        self.assertNotIn(don_rfq, ket_qua,
                         "Đơn đang chờ nhà cung cấp báo giá vẫn hiện ở danh "
                         "sách chính — mời Mua hàng bấm Chốt đơn cho một đơn "
                         "chưa tồn tại.")
        self.assertIn(don_sent_thuong, ket_qua)
        self.assertIn(don_nhap, ket_qua)


@tagged("post_install", "-at_install", "dl_purchase")
class TestVendorReturnScreenAccess(_RoleUsersCase):
    """SCR-56 (danh sách) / SCR-57 (chi tiết) — Trả hàng NCC, `stock.picking`
    lọc theo loại hoạt động `TR`. Menu đã dời sang rail Mua hàng
    (`dl_purchase/views/menus.xml` ghi đè `parent_id`/`sequence` bằng
    `<record>`, KHÔNG khai lại `groups=` — nhóm hiển thị vẫn là bản gốc của
    `dl_inventory/views/menus.xml`).
    """

    def test_menu_da_doi_rail_van_giu_dung_ba_nhom(self):
        """TC-INT-TestVendorReturnScreenAccess-001: xác nhận việc dời menu
        bằng `<record>` (đổi `parent_id`) không vô tình cuốn theo mất
        `groups=` — vẫn đúng ba vai trò Mua hàng/Admin/CEO của FDS.
        """
        menu = self.env.ref("dl_inventory.menu_dl_picking_vendor_return")
        self.assertEqual(menu.parent_id, self.env.ref(
            "dl_base.menu_dl_purchase"),
            "Menu chưa thực sự dời sang rail Mua hàng.")
        nhom = set(menu.groups_id.mapped("full_name"))
        for key in ("purchasing", "admin", "ceo"):
            user = self.role_users[key]
            visible = self.env["ir.ui.menu"].with_user(
                user)._visible_menu_ids()
            self.assertIn(menu.id, visible,
                         "Vai trò %s không thấy menu sau khi dời rail." % key)
        self.assertTrue(nhom, "Menu dời rail nhưng rỗng groups.")

    def test_tao_tay_phieu_tra_bi_khoa_ca_ba_lop_view(self):
        """TC-INT-TestVendorReturnScreenAccess-002: tên `_nocreate` phải là
        thật — kiểm tra thẳng thuộc tính `create` trên arch đã hợp nhất của cả
        list lẫn form (KHÔNG suy từ ir.rule RS-03, vì rule đó chỉ chặn Thủ
        kho; Mua hàng/Admin vẫn có `perm_create=1` ở ACL — cửa chặn thật cho
        chính họ nằm ở view).
        """
        Picking = self.env["stock.picking"]
        action = self.env.ref("dl_inventory.action_dl_picking_vendor_return")
        views = Picking.get_views(
            [(v.view_id.id, v.view_mode) for v in action.view_ids])["views"]
        self.assertIn('create="0"', views["tree"]["arch"])
        self.assertIn('create="0"', views["form"]["arch"],
                      "Form Trả hàng NCC không khoá create — tạo tay lọt qua "
                      "action rồi mở thẳng form vẫn cho lưu bản ghi mới.")
        # Bảng dòng move_ids bên trong form: lớp khoá thứ ba.
        idx = views["form"]["arch"].index('name="move_ids"')
        doan = views["form"]["arch"][idx:idx + 200]
        self.assertIn('create="0"', doan,
                      "Bảng dòng Hàng trả không khoá create.")

    def test_mua_hang_admin_chot_duoc_phieu_tra(self):
        """TC-INT-TestVendorReturnScreenAccess-003: chốt/huỷ là việc CỦA họ —
        đối chứng dương cho ca CEO bên dưới, không phải lặp lại
        TC-INT-TestScreenBoundaries-012 của dl_inventory (case đó không có
        user CEO).
        """
        phieu = self._reject_receive_po(self.thep)
        phieu.with_user(self.role_users["purchasing"]).action_confirm()
        self.assertNotEqual(phieu.state, "draft")

    def test_ceo_thay_nut_chot_tra_nhung_bam_thi_an_accesserror(self):
        """TC-INT-TestVendorReturnScreenAccess-004: LỆCH THẬT giữa ba tầng.
        Form khai `groups=` cho CEO ở nút "Chốt trả hàng"/"Không trả nữa", và
        guard server `_dlm_check_return_decision` (`_DLM_RETURN_DECIDERS`)
        cũng liệt CEO vào người được quyết định — cả hai đều nói CEO làm
        được. Nhưng ACL model `stock.picking` cho CEO
        (`access_dl_stock_picking_ceo`) chỉ có `perm_read=1`, write=0. Nút
        sáng, guard nghiệp vụ cho qua, bấm vẫn ăn AccessError — CEO trên màn
        này thực chất chỉ xem được, ngược hẳn với màn Đơn mua hàng
        (TC-INT-TestPurchaseOrderScreenAccess-003) nơi CEO sửa/tạo được thật.
        """
        arch = self.env.ref("dl_inventory.view_dl_vendor_return_form").arch
        self.assertIn('name="action_confirm"', arch)
        idx = arch.index('name="action_confirm"')
        self.assertIn("dl_base.dl_group_ceo", arch[idx:idx + 300],
                      "Nút Chốt trả hàng không còn khai cho CEO — cập nhật "
                      "lại nội dung test nếu FDS đổi ý.")

        phieu = self._reject_receive_po(self.thep)
        with self.assertRaises(AccessError):
            phieu.with_user(self.role_users["ceo"]).action_confirm()

    def test_truong_kd_doc_duoc_phieu_tra_du_khong_khai_o_menu(self):
        """TC-INT-TestVendorReturnScreenAccess-005: KHÔNG PHẢI khẳng định
        đúng thiết kế — đây là phát hiện để báo FDS. Menu/nhóm chỉ khai
        Mua hàng/Admin/CEO, nhưng ACL `access_dl_stock_picking_sm` cho Trưởng
        phòng KD `perm_read=1` trên TOÀN BỘ `stock.picking` và
        `dl_inventory/security/ir_rule.xml` không có rule nào thu hẹp phạm vi
        đọc của nhóm này (khác hẳn BA — nhóm đó bị `rule_picking_sales_delivery_only`
        ép domain về đúng phiếu giao hàng). Trưởng KD vì vậy đọc được phiếu
        Trả hàng NCC qua RPC/domain trực tiếp dù không có đường menu nào dẫn
        tới đó.
        """
        phieu = self._reject_receive_po(self.thep)
        ten = phieu.with_user(
            self.role_users["sales_manager"]).read(["name"])[0]["name"]
        self.assertEqual(ten, phieu.name,
                         "Nếu dòng này đỏ vì đã có rule thu hẹp — sửa lại "
                         "test này, đừng xoá: đó là tin tốt, không phải lỗi.")
