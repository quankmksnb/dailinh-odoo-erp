# -*- coding: utf-8 -*-
"""K14 — Số khả dụng: tồn trừ phần đã bị phiếu khác giữ chỗ.

Thiết kế: docs/Thiet_ke_luong_sau_don_hang_check_kho_dieu_phoi.md §4.2–4.3 (đc-07,
D-07).

Cái sai đắt nếu hỏng — nguyên văn ca người dùng kể: kho còn đúng 5 tấn thép, khách A
chốt đơn và hệ thống báo "đủ"; 5 phút sau nhân viên khác mở màn tồn kho, CŨNG thấy 5
tấn, và bán thẳng cho khách B. Tới lúc xưởng của khách A chạy máy thì thép đã bị bốc đi
— trễ tiến độ, đền hợp đồng.

Trước K14 hệ thống đọc `sum(quant.quantity)` nên **đúng là** báo đủ cho cả hai. Bộ test
này canh hai chiều:

* trừ thiếu thì hai phiếu cùng thấy đủ trên một lô hàng (lỗi cũ); * trừ thừa thì phiếu
vừa giữ chỗ xong lại tự tố mình thiếu hàng, thủ kho không xác nhận nổi phiếu mình vừa
tạo.

Và canh **phạm vi**: khả dụng phải tính ở đúng khu mà phiếu sẽ lấy hàng. Cộng nhầm hàng
đang nằm ở khu Chờ kiểm là hứa giao thứ chưa qua QC.
"""

from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestAvailability(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ô cạnh Kho nguyên vật liệu dưới cùng khu cha (Kho nhà máy sản xuất) —
        # dùng để canh phạm vi tính khả dụng. Trước K15 là ô "Bán thành phẩm";
        # ô đó đã gộp vào Kho nguyên vật liệu nên nay dùng khu Phế liệu chờ bán.
        cls.loc_ben_canh = cls.env.ref("dl_inventory.stock_location_xuong_pl")
        cls.lot = cls.env["stock.lot"].create({
            "name": "LO/TEST/K14",
            "product_id": cls.material.id,
            "company_id": cls.env.company.id,
        })

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _stock_up(self, qty, location, lot=None):
        """Đặt tồn đầu kỳ thẳng vào quant, không đi qua phiếu nhận."""
        vals = {
            "product_id": self.material.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }
        if lot is not False:
            vals["lot_id"] = (lot or self.lot).id
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            vals).action_apply_inventory()

    def _transfer(self, qty, source=None, dest=None):
        source = source or self.loc_kho
        dest = dest or self.loc_xuong
        return self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": source.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": qty,
                "product_uom": self.material.uom_id.id,
                "location_id": source.id,
                "location_dest_id": dest.id,
            })],
        })

    def _reserve(self, qty, source=None):
        """Phiếu đã giữ chỗ `qty` — đóng vai "đơn của khách A"."""
        picking = self._transfer(qty, source=source)
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _available(self, location=None):
        return self.env["stock.quant"]._dlm_available_qty(
            self.material, location or self.loc_kho)

    # ── Chiều 1: trừ THIẾU — đúng ca người dùng kể ───────────────────────────
    def test_kha_dung_tru_phan_phieu_khac_dang_giu(self):
        """TC-INT-TestAvailability-001: Tồn 10, phiếu khác giữ 8 thì còn lấy được 2, không
        phải 10.
        """
        self._stock_up(10.0, self.loc_kho)
        self.assertEqual(self._available(), 10.0, "Chưa ai giữ mà đã hụt.")

        khach_a = self._reserve(8.0)
        self.assertEqual(khach_a.state, "assigned",
                         "Phiếu chưa giữ được chỗ thì test sau vô nghĩa.")

        self.assertEqual(
            self._available(), 2.0,
            "Khả dụng vẫn đọc TỒN THỰC — hai phiếu sẽ cùng thấy đủ trên một lô "
            "hàng (đây chính là lỗi ĐC-07).")

    def test_phieu_thu_hai_bi_bao_thieu(self):
        """TC-INT-TestAvailability-002: Khách B đòi 5 trong khi chỉ còn 2 khả dụng thì phải
        có dòng cảnh báo.
        """
        self._stock_up(10.0, self.loc_kho)
        self._reserve(8.0)

        khach_b = self._transfer(5.0)
        self.assertEqual(khach_b._dlm_qty_available(self.material), 2.0)
        self.assertTrue(
            khach_b._dlm_shortage_lines(),
            "Phiếu đòi 5 mà chỉ còn 2 khả dụng lại không cảnh báo gì.")

    def test_cot_tren_dong_cung_mot_so_voi_dai_canh_bao(self):
        """TC-INT-TestAvailability-003: Cột "Còn lấy được" nằm ngay cạnh dải cảnh báo — hai
        chỗ nói hai số là lỗi người dùng không bao giờ báo, chỉ mất niềm tin vào bảng.
        """
        self._stock_up(10.0, self.loc_kho)
        self._reserve(8.0)

        khach_b = self._transfer(5.0)
        self.assertEqual(khach_b.move_ids.dlm_src_available_qty, 2.0,
                         "Cột trên dòng còn đọc tồn thực trong khi dải đã trừ.")

    # ── Chiều 2: trừ THỪA — phiếu tự tố mình ─────────────────────────────────
    def test_phieu_khong_tu_to_minh_thieu_hang(self):
        """TC-INT-TestAvailability-004: Phiếu đã giữ chỗ xong phải thấy đủ: phần nó đang
        giữ là của nó.

        Không cộng lại thì thủ kho tạo phiếu, giữ chỗ thành công, rồi mở ra thấy dải đỏ
        "thiếu hàng" — và không dám xác nhận phiếu của chính mình.
        """
        self._stock_up(10.0, self.loc_kho)
        khach_a = self._reserve(8.0)

        self.assertEqual(
            khach_a._dlm_qty_available(self.material), 10.0,
            "Phiếu đang trừ cả phần chỗ giữ của CHÍNH nó.")
        self.assertFalse(
            khach_a._dlm_shortage_lines(),
            "Phiếu giữ chỗ đủ mà vẫn báo thiếu hàng.")
        self.assertEqual(khach_a.move_ids.dlm_src_available_qty, 10.0)

    def test_ban_phe_lieu_khong_tu_chan_minh(self):
        """TC-INT-TestAvailability-005: Cùng một lỗi, đường khác: phiếu Bán phế liệu đã giữ
        chỗ mà dải vẫn báo "bán quá tay" thì không ai giao được phế liệu đi.
        """
        scrap = self.env["product.product"].create({
            "name": "Phế liệu thép (test K14)", "product_kind": "material"})
        scrap.tracking = "none"
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": scrap.id,
            "location_id": self.loc_xuong_pl.id,
            "inventory_quantity": 50.0,
        }).action_apply_inventory()

        picking = self.env["stock.picking"].create({
            "picking_type_id": self.env.ref(
                "dl_inventory.picking_type_scrap_sale").id,
            "location_id": self.loc_xuong_pl.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
            "move_ids": [(0, 0, {
                "name": scrap.name,
                "product_id": scrap.id,
                "product_uom_qty": 50.0,
                "product_uom": scrap.uom_id.id,
                "location_id": self.loc_xuong_pl.id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers").id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()

        muc, _noi_dung, chan = picking._dlm_banner_scrap_sale()
        self.assertNotEqual(
            muc, "warning",
            "Phiếu bán đúng 50kg đang giữ chỗ lại tự báo bán quá tay.")
        self.assertFalse(chan)

    # ── Phạm vi: đúng khu, không cộng nhầm khu khác ──────────────────────────
    def test_khong_cong_hang_khu_ben_canh(self):
        """TC-INT-TestAvailability-006: Khả dụng tính ở đúng khu, và gộp theo cây — khớp
        phạm vi giữ chỗ.

        Kho nguyên vật liệu và khu Phế liệu là hai ô cạnh nhau dưới Kho nhà máy sản
        xuất. Phiếu lấy nguồn Kho nguyên vật liệu không với được sang ô kia, nên số báo
        cũng không được với theo; ngược lại lấy nguồn khu CHA thì với được cả hai
        (`child_of`), số báo phải cộng đủ. Lệch hai cái này là màn báo một đằng, phiếu
        giữ được một nẻo — sai âm thầm, không lỗi nào nổ.

        (K15 — khu cha nay là `loc_khosx`, không còn là `loc_xuong`: Xưởng sản xuất đã
        thành ô lá. Xem test_warehouse_layout.)
        """
        self._stock_up(10.0, self.loc_kho)
        self._stock_up(30.0, self.loc_ben_canh)

        self.assertEqual(
            self._available(self.loc_kho), 10.0,
            "Khả dụng ở Kho nguyên vật liệu đang cộng cả hàng ô bên cạnh.")
        # Chiều ngược: canh cả hai chiều, không chỉ chiều cấm — hàm chỉ trả 0 thì
        # dòng trên vẫn xanh mà tính năng thì chết.
        self.assertEqual(self._available(self.loc_ben_canh), 30.0,
                         "Tính ở đúng ô bên cạnh lại không thấy hàng.")
        self.assertEqual(self._available(self.loc_khosx), 40.0,
                         "Khu cha không gộp đủ hai ô con (child_of).")

    def test_xuong_khong_voi_duoc_vao_kho(self):
        """TC-INT-TestAvailability-007: K15 — Xưởng sản xuất không được thấy hàng đang nằm
        trong kho.

        Đây là nửa còn lại của việc tách chỗ cất khỏi chỗ làm, đo bằng chính con số mà
        màn hình hiển thị. Trước K15 Xưởng là khu CHA của Kho vật tư thì hỏi "xưởng còn
        lấy được bao nhiêu" trả về cả đống thép chưa ai bàn giao. Nay phải là 0 cho tới
        khi có phiếu bàn giao thật.
        """
        self._stock_up(10.0, self.loc_kho)
        self.assertEqual(
            self._available(self.loc_xuong), 0.0,
            "Xưởng đang đọc được tồn của Kho nguyên vật liệu — vai trò kép "
            "quay lại rồi.")

    def test_hang_chua_qua_kiem_khong_phai_kha_dung(self):
        """TC-INT-TestAvailability-008: Hàng NCC vừa giao, còn nằm khu Chờ kiểm thì Kho vật
        tư vẫn là 0.

        Cộng vào là hứa giao/đưa vào sản xuất thứ chưa qua QC. Dựng tồn ở đây bằng phiếu
        nhận thật chứ không kiểm kê tay — RS-07 cấm đếm tay ở khu quá cảnh, và chính
        lệnh cấm đó là lý do khu này không bao giờ được coi là hàng dùng được.
        """
        receipt = self._make_receipt(qty=30.0)
        self._receive(receipt, qty=30.0)

        self.assertEqual(
            self.env["stock.quant"]._dlm_on_hand_qty(
                self.material, self.loc_qc), 30.0,
            "Phiếu nhận chưa đưa hàng vào khu Chờ kiểm — test sau vô nghĩa.")
        self.assertEqual(
            self._available(self.loc_kho), 0.0,
            "Kho vật tư đang tính cả hàng còn nằm chờ kiểm.")

    # ── Câu thông báo: ba ca, ba việc phải làm khác nhau ─────────────────────
    def test_bi_giu_het_noi_khac_voi_het_hang(self):
        """TC-INT-TestAvailability-009: "Hết hàng" thì đi mua. "Bị giữ hết" thì đi nói
        chuyện với người đang giữ.

        Gộp hai ca vào một câu là đẩy thủ kho đi mua thứ đang nằm trong kho.
        """
        self._stock_up(8.0, self.loc_kho)
        self._reserve(8.0)                      # giữ sạch, tồn thực vẫn 8

        khach_b = self._transfer(3.0)
        canh_bao = " ".join(khach_b._dlm_shortage_lines())
        self.assertIn("đã giữ hết", canh_bao,
                      "Hàng còn trong kho mà báo là hết — sai việc phải làm.")
        self.assertNotIn("tồn 0", canh_bao)

    def test_het_sach_thi_van_noi_la_het(self):
        """TC-INT-TestAvailability-010: Chiều còn lại: tồn thật sự bằng 0 thì đừng đổ cho
        người khác giữ.
        """
        khach_b = self._transfer(3.0)
        canh_bao = " ".join(khach_b._dlm_shortage_lines())
        self.assertIn("tồn 0", canh_bao)
        self.assertNotIn("đã giữ hết", canh_bao)

    # ── Đường tra "ai đang giữ" ──────────────────────────────────────────────
    def test_biet_duoc_hang_dang_giu_cho_ai(self):
        """TC-INT-TestAvailability-011: Cột "Đang giữ chỗ" trả lời bao nhiêu; nút cạnh nó
        phải trả lời CHO AI — không thì cách đoán rẻ nhất vẫn là bán chồng.
        """
        self._stock_up(10.0, self.loc_kho)
        khach_a = self._reserve(8.0)

        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.material.id),
            ("location_id", "=", self.loc_kho.id),
        ], limit=1)
        self.assertEqual(quant.reserved_quantity, 8.0)
        self.assertEqual(quant.available_quantity, 2.0)

        action = quant.action_dlm_open_reservations()
        lines = self.env["stock.move.line"].search(action["domain"])
        self.assertEqual(lines.picking_id, khach_a,
                         "Không tra ra được phiếu nào đang giữ lô hàng này.")
