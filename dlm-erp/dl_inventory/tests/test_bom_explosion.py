# -*- coding: utf-8 -*-
"""K15 — Nổ BOM thành nhu cầu vật tư.

Mỗi phép thử kèm câu "nếu đỏ nghĩa là gì ngoài đời", theo khuôn
``docs/Kich_ban_test_Kho_K1_K3.md``: một con số sai ở đây không dừng lại ở màn
hình, nó thành đơn mua sai và thép nằm chết trong kho.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_inventory")
class TestBomExplosion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loc_kho = cls.env.ref("dl_inventory.stock_location_nhan_kho")
        cls.Bom = cls.env["dl.bom"]
        cls.Product = cls.env["product.product"]

        # thep/que_han để ĐVT kg (nhóm chia được) — các test số học dưới đây đo
        # phép nổ BOM, không đo luật làm tròn; kg giữ nhu cầu lẻ đúng như xưa.
        # Luật "ĐVT đếm được tròn lên" có test riêng ở cuối file.
        kg = cls.env.ref("uom.product_uom_kgm")
        cls.thep = cls._mk("material", "Thép hộp 25x50 (nổ BOM)", uom=kg)
        cls.que_han = cls._mk("material", "Que hàn (nổ BOM)", uom=kg)
        cls.oc = cls._mk("material", "Ốc M8 (nổ BOM)")
        cls.khung = cls._mk("material_processed", "Khung bàn (nổ BOM)")
        cls.ban = cls._mk("manufactured", "Bộ bàn ghế (nổ BOM)")

    # ------------------------------------------------------------------ helpers
    @classmethod
    def _mk(cls, kind, name, uom=None):
        vals = {"name": name, "product_kind": kind}
        if uom:
            vals["uom_id"] = uom.id
            vals["uom_po_id"] = uom.id
        return cls.env["product.product"].create(vals)

    def _mk_bom(self, product, lines, product_qty=1.0, confirmed=True):
        """BOM với các dòng ``(vật tư, số lượng)``.

        Ghi thẳng ``status`` thay vì gọi ``action_confirm``: cổng quy cách vật tư
        (§12.4) không phải thứ bộ test này đo, và vật tư test cố ý khai trống.
        """
        bom = self.Bom.create({
            "product_id": product.id,
            "bom_type": "template",
            "product_qty": product_qty,
            "line_ids": [(0, 0, {
                "material_id": material.id,
                "quantity": qty,
                "is_override": True,
            }) for material, qty in lines],
        })
        if confirmed:
            bom.status = "confirmed"
        return bom

    def _stock_up(self, product, qty, location=None):
        """Tồn đầu kỳ thẳng vào quant. Hàng theo lô BẮT BUỘC có lot_id, không
        thì kiểm kê không áp được và quant im lặng không sinh ra."""
        vals = {
            "product_id": product.id,
            "location_id": (location or self.loc_kho).id,
            "inventory_quantity": qty,
        }
        if product.tracking == "lot":
            vals["lot_id"] = self.env["stock.lot"].create({
                "name": "LOT-TEST-%s" % product.id,
                "product_id": product.id,
                "company_id": self.env.company.id,
            }).id
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            vals).action_apply_inventory()

    # ------------------------------------------------------------------ tests
    def test_mot_tang_khong_nhan_them_hao_hut(self):
        """TC-INT-TestBomExplosion-001: Nhu cầu = effective_qty × số lượng, không nhân hao
        hụt lần nữa.

        Đỏ = tính hao hụt hai lần thì mua thừa đúng bằng tỷ lệ hao hụt, mọi đơn, mãi
        mãi.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.5), (self.oc, 20.0)])
        bom.line_ids.filtered(
            lambda l: l.material_id == self.thep).waste_rate = 10.0

        need = bom._dlm_explode_requirements(10.0)

        # 2,5 × 1,1 = 2,75 cho một bộ thì 27,5 cho mười bộ.
        self.assertAlmostEqual(need[self.thep], 27.5, places=2)
        self.assertAlmostEqual(need[self.oc], 200.0, places=2)

    def test_chia_so_luong_dau_ra_cua_bom(self):
        """TC-INT-TestBomExplosion-002: BOM khai đầu ra 6 thì dòng của nó là số cho cả 6.

        Đỏ = đòi gấp 6 lần vật tư. Sai theo hướng mua thừa: tiền đã chi ra rồi mới có
        người phát hiện. Engine giá đã chia đúng (quotation_pricing_service.py:627) nên
        báo giá vẫn đúng — chỉ kho sai.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 30.0)], product_qty=6.0)

        need = bom._dlm_explode_requirements(10.0)

        self.assertAlmostEqual(need[self.thep], 50.0, places=2)

    def test_bu_tru_btp_theo_tang(self):
        """TC-INT-TestBomExplosion-003: BTP tồn 4, cần 10 thì dùng 4 + nổ BOM con cho đúng
        6.

        Đỏ (nổ cả 10) = mua thừa thép, và 4 khung đã hàn nằm chết trong kho — đúng thứ
        tiền hai lần: một lần mua thừa, một lần công đã bỏ ra.
        """
        self._mk_bom(self.khung, [(self.thep, 2.5), (self.que_han, 0.3)])
        bom = self._mk_bom(self.ban, [(self.khung, 1.0)])
        self._stock_up(self.khung, 4.0)

        report = bom._dlm_explode_report(10.0, location=self.loc_kho)

        self.assertAlmostEqual(report["btp_used"][self.khung], 4.0, places=2)
        self.assertAlmostEqual(report["requirements"][self.khung], 4.0, places=2)
        # 6 khung còn thiếu × 2,5 cây = 15 cây, KHÔNG phải 25.
        self.assertAlmostEqual(report["requirements"][self.thep], 15.0, places=2)
        self.assertAlmostEqual(report["requirements"][self.que_han], 1.8, places=2)

    def test_khong_truyen_vi_tri_thi_no_thang_xuong_day(self):
        """TC-INT-TestBomExplosion-004: Không có khu để hỏi thì coi như không có BTP nào
        sẵn.

        Đỏ = màn nào quên truyền vị trí sẽ âm thầm "thấy đủ" BTP thì nhu cầu vật tư thô
        biến mất.
        """
        self._mk_bom(self.khung, [(self.thep, 2.5)])
        bom = self._mk_bom(self.ban, [(self.khung, 1.0)])
        self._stock_up(self.khung, 4.0)

        need = bom._dlm_explode_requirements(10.0)

        self.assertAlmostEqual(need[self.thep], 25.0, places=2)
        self.assertNotIn(self.khung, need)

    def test_cung_vat_tu_nhieu_dong_nhieu_tang_thi_cong_don(self):
        """TC-INT-TestBomExplosion-005: Kết quả là dict cộng dồn, không phải danh sách.

        Đỏ = mỗi dòng tự thấy đủ mà tổng thì thiếu — kiểu sai không màn nào bắt được vì
        từng con số đều đúng.
        """
        self._mk_bom(self.khung, [(self.thep, 2.0)])
        bom = self._mk_bom(
            self.ban, [(self.khung, 1.0), (self.thep, 1.0), (self.thep, 0.5)])

        need = bom._dlm_explode_requirements(10.0, location=self.loc_kho)

        # 10 khung × 2 + 10 × 1 + 10 × 0,5 = 35 — MỘT mục.
        self.assertAlmostEqual(need[self.thep], 35.0, places=2)

    def test_hai_dong_cung_an_mot_btp_khong_dem_hai_lan_ton(self):
        """TC-INT-TestBomExplosion-006: Hai dòng cùng ăn một BTP: dòng sau không được thấy
        lại tồn đã dùng.

        Doc §5.2 bẫy 6 nói "thứ tự chỉ đổi phân bổ, không đổi tổng" — điều đó chỉ đúng
        nếu có sổ theo dõi. Đỏ = cả hai dòng cùng trừ 4 khung thì tổng nhu cầu thép bị
        tính thiếu thì mua thiếu, xưởng đứng giữa chừng.
        """
        self._mk_bom(self.khung, [(self.thep, 2.5)])
        bom = self._mk_bom(self.ban, [(self.khung, 1.0), (self.khung, 1.0)])
        self._stock_up(self.khung, 4.0)

        report = bom._dlm_explode_report(10.0, location=self.loc_kho)

        # Cần 20 khung, kho có 4 thì phải nổ đúng 16 × 2,5 = 40 cây thép.
        self.assertAlmostEqual(report["btp_used"][self.khung], 4.0, places=2)
        self.assertAlmostEqual(report["requirements"][self.thep], 40.0, places=2)

    def test_btp_khong_co_dinh_muc_thi_bao_ten(self):
        """TC-INT-TestBomExplosion-007: DP-04 — BTP thiếu BOM con thì nhánh vật tư của nó
        mất hẳn.

        Đỏ = im lặng bỏ qua: mua thiếu một nhánh nguyên vật liệu mà không ai biết cho
        tới lúc xưởng dừng.
        """
        bom = self._mk_bom(self.ban, [(self.khung, 1.0)])

        report = bom._dlm_explode_report(10.0, location=self.loc_kho)

        self.assertIn(self.khung, report["btp_no_bom"])
        self.assertAlmostEqual(report["requirements"][self.khung], 10.0, places=2)

    def test_phe_lieu_khong_lot_vao_nhu_cau(self):
        """TC-INT-TestBomExplosion-008: DP-09 — vật tư gắn cờ phế liệu không phải nguyên
        liệu đầu vào.

        Đỏ = phiếu xuất vật tư giữ chỗ chính đống phế liệu chờ bán để đem đi làm hàng.
        """
        scrap = self._mk("material", "Phế liệu thép (nổ BOM)")
        scrap.sudo().dlm_is_scrap = True
        bom = self._mk_bom(self.ban, [(self.thep, 1.0), (scrap, 5.0)])

        report = bom._dlm_explode_report(10.0, location=self.loc_kho)

        self.assertNotIn(scrap, report["requirements"])
        self.assertIn(scrap, report["scrap"])

    def test_don_vi_dem_duoc_lam_tron_len(self):
        """ĐVT đếm được (cây/túi...) có hao hụt ⇒ nhu cầu kho tròn LÊN số nguyên.

        Đỏ = phiếu kho đòi xuất 1,04 cây — con số không cấp được ngoài đời, thủ
        kho phải tự làm tròn bằng tay mỗi lần. Giá thành vẫn để lẻ ở engine giá,
        chỉ nhu cầu xuất kho mới tròn.
        """
        cay = self.env.ref("dl_product.dlm_uom_cay")
        thep_cay = self._mk("material", "Thép cây tròn (nổ BOM)", uom=cay)
        thep_cay.dlm_waste_rate = 20.0      # cây CÓ hao hụt: mạch cắt, ba-via
        bom = self._mk_bom(self.ban, [(thep_cay, 1.0)])

        # Trục 1 — định mức giữ LẺ để tính giá đúng.
        self.assertAlmostEqual(bom.line_ids.waste_rate, 20.0, places=2)
        self.assertAlmostEqual(bom.line_ids.effective_qty, 1.2, places=2)

        # Trục 2 — kho cấp nguyên cây: 1,2 → 2.
        self.assertAlmostEqual(
            bom._dlm_explode_requirements(1.0)[thep_cay], 2.0, places=2)
        # 10 sản phẩm: 12 cây chẵn → giữ 12, KHÔNG phải 10 × 2 = 20.
        self.assertAlmostEqual(
            bom._dlm_explode_requirements(10.0)[thep_cay], 12.0, places=2)

    def test_dvt_dem_nguyen_chiec_khong_co_hao_hut(self):
        """Hàng đếm nguyên chiếc (túi) KHÔNG tự gán hao hụt, dù vật tư khai sẵn.

        Đỏ = 2% của túi 1000 con biến thành cả một túi thứ hai khi kho tròn lên.
        """
        tui = self.env.ref("dl_product.dlm_uom_tui")
        dinh = self._mk("material", "Đinh rút (nổ BOM)", uom=tui)
        dinh.dlm_waste_rate = 5.0
        bom = self._mk_bom(self.ban, [(dinh, 1.0)])

        self.assertEqual(bom.line_ids.waste_rate, 0.0)
        self.assertAlmostEqual(bom.line_ids.effective_qty, 1.0, places=2)
        self.assertAlmostEqual(
            bom._dlm_explode_requirements(1.0)[dinh], 1.0, places=2)

    def test_don_vi_do_luong_giu_le(self):
        """ĐVT đo lường (kg) CÓ hao hụt (tự gán từ vật tư) và KHÔNG bị tròn.

        Đỏ = tròn cả kg/m ⇒ mua thừa vật tư bán theo cân, sai ngược hướng.
        """
        kg = self.env.ref("uom.product_uom_kgm")
        son = self._mk("material", "Sơn tĩnh điện (nổ BOM)", uom=kg)
        son.dlm_waste_rate = 4.0
        bom = self._mk_bom(self.ban, [(son, 1.0)])

        self.assertAlmostEqual(bom.line_ids.waste_rate, 4.0, places=2)
        self.assertAlmostEqual(
            bom._dlm_explode_requirements(1.0)[son], 1.04, places=2)

    def test_bom_vong_lap_bao_chuoi_khong_treo(self):
        """TC-INT-TestBomExplosion-009: A cần b, b cần A thì phải raise nêu chuỗi, không đệ
        quy vô hạn.

        Đỏ = treo tiến trình Odoo. Không phải lỗi hiển thị — cả server đứng.

        Vòng lặp dựng bằng SQL vì lá chắn `_dlm_check_no_cycle` (LK-01) chặn từ lúc tạo.
        Đó chính là ca hàm này tồn tại để đỡ: BOM đã lỡ nằm trong DB **trước khi** lá
        chắn ra đời — lá chắn không quét lại dữ liệu cũ.
        """
        btp_a = self._mk("material_processed", "Cụm A (nổ BOM)")
        btp_b = self._mk("material_processed", "Cụm B (nổ BOM)")
        bom_a = self._mk_bom(btp_a, [(self.thep, 1.0)])
        self._mk_bom(btp_b, [(btp_a, 1.0)])
        bom = self._mk_bom(self.ban, [(btp_a, 1.0)])
        # Khép vòng sau lưng constraint: dòng của BOM(A) trỏ ngược về B.
        self.env.cr.execute(
            "UPDATE dl_bom_line SET material_id = %s WHERE id = %s",
            (btp_b.id, bom_a.line_ids[0].id))
        self.env.invalidate_all()

        with self.assertRaises(UserError) as err:
            bom._dlm_explode_requirements(1.0, location=self.loc_kho)

        self.assertIn("Cụm A", err.exception.args[0])
