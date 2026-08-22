# -*- coding: utf-8 -*-
"""K8: kiểm kê và hàng đợi phiếu.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §11.10, §11.11, §12.1 (tiêu chí verify K8).

Hai bất biến quan trọng nhất:
  - Thủ kho áp được số kiểm kê dù không có group_stock_manager (§8.3). Native
    chốt cứng bằng group đó, dl_inventory nâng quyền sau khi kiểm vai trò. Test
    này phải chạy dưới quyền Thủ kho, không phải admin, nếu không nó không bắt
    được đúng lỗ hổng đang vá (màn Phế liệu K7 test bằng admin nên bị lọt).
  - Hàng đợi định tuyến đúng loại: mở phiếu kiểm bằng form nhận là mời ghi hàng
    lỗi vào ô hàng thiếu (§6). `dlm_picking_kind` là khoá định tuyến đó.
"""

from odoo.tests.common import tagged
from odoo.tools.safe_eval import safe_eval

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestInventoryAdjustment(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_warehouse = cls.env["res.users"].create({
            "name": "thukho_kiemke_test",
            "login": "thukho_kiemke_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })
        # Hàng thương mại: storable nhưng không theo lô (§4.2), đếm/áp không
        # vướng bước gán lô, tách bạch đúng thứ đang test là quyền áp kiểm kê.
        cls.item = cls.env["product.product"].create({
            "name": "Hàng thương mại (test K8)",
            "product_kind": "trading",
        })
        cls.item.tracking = "none"

    def _seed_stock(self, qty):
        """Đưa sẵn `qty` hàng vào kho chính (chạy dưới quyền admin có manager)."""
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.item.id,
            "location_id": self.loc_kho.id,
            "inventory_quantity": qty,
        })
        quant.action_apply_inventory()
        return quant

    # Tiêu chí verify K8: kiểm kê lệch -3 thì phải sinh move điều chỉnh, tồn khớp
    def test_kiem_ke_lech_am_3_sinh_move_dieu_chinh_va_ton_khop(self):
        """TC-INT-TestInventoryAdjustment-001: §12.1: đếm được 97 trên tồn hệ thống 100, áp
        xong thì tồn về 97, có phiếu điều chỉnh cho 3 đơn vị hụt.

        Áp dưới quyền Thủ kho: đây là chỗ duy nhất chứng minh quyết định K8 (Thủ kho áp
        được mà không cần manager) chạy thật.
        """
        self._seed_stock(100.0)
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.item.id),
            ("location_id", "=", self.loc_kho.id),
        ])
        self.assertEqual(quant.quantity, 100.0)

        quant_wh = quant.with_user(self.user_warehouse).with_context(
            inventory_mode=True)
        quant_wh.write({"inventory_quantity": 97.0, "inventory_quantity_set": True})
        quant_wh.action_apply_inventory()

        self.assertEqual(
            quant.quantity, 97.0,
            "Áp kiểm kê xong tồn hệ thống phải khớp số đếm.")

        # Chỉ lấy move hụt (hàng đi vào vị trí điều chỉnh), loại trừ chính move
        # 100 đơn vị lúc gây tồn ban đầu (đi ra từ vị trí điều chỉnh).
        shrink = self.env["stock.move"].search([
            ("product_id", "=", self.item.id),
            ("state", "=", "done"),
        ]).filtered(lambda m: m.location_dest_id.usage == "inventory")
        self.assertTrue(
            shrink, "Kiểm kê hụt phải sinh phiếu điều chỉnh (stock.move).")
        self.assertEqual(
            sum(shrink.mapped("quantity")), 3.0,
            "Phần điều chỉnh phải đúng bằng chênh lệch đếm được.")

    def test_thu_kho_ap_duoc_du_khong_co_group_manager(self):
        """TC-INT-TestInventoryAdjustment-002: §8.3 vs native: Thủ kho không có
        group_stock_manager nhưng vẫn áp được kiểm kê nhờ _apply_inventory nâng quyền có
        kiểm vai trò.

        Không có override này, native ném "Only a stock manager can validate".
        """
        self.assertFalse(
            self.user_warehouse.has_group("stock.group_stock_manager"),
            "Tiền đề của test: Thủ kho không phải manager (§8.3).")
        self._seed_stock(20.0)
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.item.id),
            ("location_id", "=", self.loc_kho.id),
        ])
        quant_wh = quant.with_user(self.user_warehouse).with_context(
            inventory_mode=True)
        quant_wh.write({"inventory_quantity": 25.0, "inventory_quantity_set": True})
        # Không raise = đã vá đúng.
        quant_wh.action_apply_inventory()
        self.assertEqual(quant.quantity, 25.0)

    # Định tuyến hàng đợi
    def test_picking_kind_suy_dung_tung_loai(self):
        """TC-INT-TestInventoryAdjustment-003: §11.11: `dlm_picking_kind` phải phân biệt
        được các loại đi chung `internal` (KC vs CK) và chung `outgoing` (GH vs TR vs
        BPL).
        """
        cases = [
            (self.warehouse.in_type_id, "receipt"),
            (self.env.ref("dl_inventory.picking_type_qc"), "qc"),
            (self.warehouse.int_type_id, "transfer"),
            (self.warehouse.out_type_id, "delivery"),
            (self.env.ref("dl_inventory.picking_type_vendor_return"),
             "vendor_return"),
            (self.env.ref("dl_inventory.picking_type_scrap_sale"), "scrap_sale"),
        ]
        for picking_type, expected in cases:
            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id,
            })
            self.assertEqual(
                picking.dlm_picking_kind, expected,
                "Loại '%s' phải định tuyến sang '%s'."
                % (picking_type.name, expected))

    def test_hang_doi_chi_gom_phieu_assigned_cua_thu_kho(self):
        """TC-INT-TestInventoryAdjustment-004: §11.11: hàng đợi là phiếu `assigned` của
        loại thủ kho phụ trách.

        Phiếu nháp chưa sẵn sàng nên không vào hàng đợi. Phiếu Trả NCC là việc Mua hàng
        nên cũng không vào, dù có thể ở assigned.
        """
        domain = safe_eval(
            self.env.ref("dl_inventory.action_dl_picking_todo").domain)

        receipt = self._make_receipt()  # action_confirm + assign, kết quả assigned
        self.assertEqual(receipt.state, "assigned")
        queue = self.env["stock.picking"].search(domain)
        self.assertIn(
            receipt, queue, "Phiếu nhận sẵn sàng phải nằm trong hàng đợi.")

        draft = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": self.vendor.id,
            "location_id": self.loc_vendors.id,
            "location_dest_id": self.loc_qc.id,
        })
        self.assertEqual(draft.state, "draft")
        self.assertNotIn(
            draft, self.env["stock.picking"].search(domain),
            "Phiếu nháp chưa sẵn sàng, không được lên hàng đợi.")
