# -*- coding: utf-8 -*-
"""K1 — Vai trò Thủ kho: làm được việc kho, không đụng tới giá.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §8.

Hai bất biến quan trọng nhất:
  • Thủ kho tách khỏi Mua hàng — người ĐẶT hàng không được đồng thời là người
    xác nhận ĐÃ NHẬN ĐỦ hàng (kiểm soát chéo cơ bản của nghiệp vụ mua sắm).
  • Thủ kho đếm hàng, không định giá.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestAccessWarehouse(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_warehouse = cls._make_user(
            cls, "thukho_test", "dl_base.dl_group_warehouse")
        cls.user_purchasing = cls._make_user(
            cls, "muahang_test", "dl_base.dl_group_purchasing")

    def _make_user(self, login, group_xml_id):
        return self.env["res.users"].create({
            "name": login,
            "login": login,
            "groups_id": [(6, 0, [self.env.ref(group_xml_id).id])],
        })

    # ── Thủ kho làm được việc của mình ───────────────────────────────────────
    def test_thu_kho_tao_duoc_phieu_kho(self):
        """§8.4 — Thủ kho là chủ sở hữu phiếu kho: tạo/sửa được."""
        picking = self.env["stock.picking"].with_user(
            self.user_warehouse).create({
                "picking_type_id": self.warehouse.in_type_id.id,
                "partner_id": self.vendor.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
            })
        self.assertTrue(picking.id)

    # ── Thủ kho không đụng tới giá ───────────────────────────────────────────
    def test_thu_kho_khong_thay_gia_von_trong_bom(self):
        """§8.3 — Giá vốn trong định mức bị chặn bằng _COST_GROUPS.

        Thủ kho KHÔNG có tên trong nhóm đó, và cũng không được thêm vào.
        """
        bom_fields = self.env["dl.bom.line"].with_user(
            self.user_warehouse).fields_get()
        for field_name in ("price_snapshot", "recovery_value", "subtotal"):
            self.assertNotIn(
                field_name, bom_fields,
                "Thủ kho đọc được '%s' — đã bị thêm nhầm vào _COST_GROUPS."
                % field_name)

    def test_thu_kho_khong_phai_quan_ly_kho_odoo(self):
        """§8.3 — Chỉ cấp stock.group_stock_user, KHÔNG cấp group_stock_manager.

        group_stock_manager mở các field giá trị tồn của Odoo. Cấp nhầm là rò
        giá cho người chỉ cần đếm hàng.
        """
        self.assertTrue(
            self.user_warehouse.has_group("stock.group_stock_user"))
        self.assertFalse(
            self.user_warehouse.has_group("stock.group_stock_manager"))

    # ── Kiểm soát chéo với Mua hàng ──────────────────────────────────────────
    def test_mua_hang_chi_sua_duoc_phieu_tra_ncc(self):
        """§8.5 — Mua hàng có quyền ghi phiếu kho, nhưng ir.rule bó lại đúng
        phiếu Trả hàng nhà cung cấp.

        Không có rule này thì Mua hàng sửa được MỌI phiếu kho, kể cả phiếu giao
        hàng khách — trong khi việc của họ chỉ là đàm phán trả hàng với NCC.
        """
        receipt = self._make_receipt()
        with self.assertRaises(
                AccessError,
                msg="Mua hàng KHÔNG được sửa phiếu nhận hàng."):
            receipt.with_user(self.user_purchasing).write({"note": "sua trom"})

        vendor_return = self.env["stock.picking"].create({
            "picking_type_id": self.env.ref(
                "dl_inventory.picking_type_vendor_return").id,
            "partner_id": self.vendor.id,
            "location_id": self.loc_tra.id,
            "location_dest_id": self.loc_vendors.id,
        })
        # note là field Html ⇒ Odoo bọc lại thành <p>...</p>, so bằng 'in'.
        vendor_return.with_user(self.user_purchasing).write({"note": "da bao NCC"})
        self.assertIn("da bao NCC", vendor_return.note)
