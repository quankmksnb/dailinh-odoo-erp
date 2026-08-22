"""Định mức theo (kiểu tính của vật tư × nhóm ĐVT), 5 ca thay cho 17 hình dạng.

Thiết kế: docs/Doi_chieu_du_lieu_doanh_nghiep_va_thiet_ke_dinh_muc_vat_tu.md §18.

Bài toán mà bộ test này khóa: Đại Linh mua thép theo cây 6m, không theo kg.
Vì vậy định mức phải ra thẳng số cây (giá là đồng/cây), và chỗ duy nhất còn
quy đổi khối lượng là tiền phế liệu thu hồi, phải quy đổi tường minh.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical", "dl_bom_calc")
class TestMaterialCalcKind(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bom = cls.env["dl.bom"]
        cls.Product = cls.env["product.product"]
        cls.uom_cay = cls.env.ref("dl_product.dlm_uom_cay")
        cls.uom_tam = cls.env.ref("dl_product.dlm_uom_tam")
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.categ_box = cls.env.ref("dl_product.material_categ_steel_box")

        # Thép hộp 25×50×1,4, mua theo cây 6m (ca chuẩn T1/T10 của thiết kế).
        cls.hop_25x50 = cls.Product.create({
            "name": "Thép hộp 25×50×1,4 (test cây)",
            "product_kind": "material",
            "categ_id": cls.categ_box.id,
            "uom_id": cls.uom_cay.id,
            "uom_po_id": cls.uom_cay.id,
            "dlm_calc_kind": "cut_length",
            "dlm_stock_length": 6,        # quy cách mua khai theo mét
            "dlm_mass_per_unit": 8.5,
        })
        cls.categ_ban = cls.env["product.category"].create({
            "name": "Bàn thép (test định mức)",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })
        cls.product_ban = cls.Product.create({
            "name": "Bàn thép (test định mức)",
            "product_kind": "manufactured",
            "categ_id": cls.categ_ban.id,
        })

    def _line(self, material, **vals):
        """Một dòng BOM rời để soi công thức (không cần BOM cha đã lưu)."""
        return self.env["dl.bom.line"].new(dict(vals, material_id=material.id))

    def _bom(self, material, **line_vals):
        return self.Bom.create({
            "product_id": self.product_ban.id,
            "bom_type": "quotation",
            "product_qty": 1,
            "line_ids": [(0, 0, dict(line_vals, material_id=material.id))],
        })

    # T1, T2: cắt đoạn ra số cây
    def test_t1_cut_length_to_cay(self):
        """TC-INT-TestMaterialCalcKind-001: 700mm x 2 đoạn chia cho cây 6m ra 0.2333 cây,
        không có kg ở đâu cả.

        Đoạn cắt nhập mm (số trên bản vẽ), cây khai mét (số lúc mua) nên phép chia phải
        quy đơn vị trước: viết 1,4m chia 6m chứ không phải 1400/6.
        """
        line = self._line(self.hop_25x50, dim_length=700, piece_count=2)
        self.assertAlmostEqual(line._dlm_auto_quantity(), 1.4 / 6, places=6)

    def test_t2_real_totals_divide_by_stock_length(self):
        """TC-INT-TestMaterialCalcKind-002: Bốn tổng mm có thật trong file BOM của Đại
        Linh, chia cho cây 6m, phải ra đúng số cây mà file ghi (§2.1). Đây là bằng chứng
        gốc của quyết định Q1.
        """
        for total_mm, expected_cay in ((10230, 1.705), (7410, 1.235),
                                       (23030, 3.8383), (570, 0.095)):
            line = self._line(self.hop_25x50, dim_length=total_mm, piece_count=1)
            self.assertAlmostEqual(
                line._dlm_auto_quantity(), expected_cay, places=4,
                msg="Tổng %smm phải ra %s cây" % (total_mm, expected_cay))

    def test_t2b_cut_list_from_real_sheet(self):
        """TC-INT-TestMaterialCalcKind-003: Cut list thật (§2.2): chân bàn 700×2 và giằng
        đơn 940×4, mỗi quy cách một dòng riêng, đúng cách xưởng ghi phiếu cắt.
        """
        chan = self._line(self.hop_25x50, dim_length=700, piece_count=2)
        giang = self._line(self.hop_25x50, dim_length=940, piece_count=4)
        self.assertAlmostEqual(chan._dlm_auto_quantity(), 0.233333, places=5)
        self.assertAlmostEqual(giang._dlm_auto_quantity(), 3.76 / 6, places=6)

    def test_cut_length_sold_by_kg_uses_mass_per_meter(self):
        """TC-INT-TestMaterialCalcKind-004: Cùng vật tư nhưng NCC bán theo kg thì định mức
        ra kg thông qua kg/m.
        """
        hop_kg = self.Product.create({
            "name": "Thép hộp 30×60×1,4 (test kg)",
            "product_kind": "material",
            "uom_id": self.uom_kg.id, "uom_po_id": self.uom_kg.id,
            "dlm_calc_kind": "cut_length",
            "dlm_mass_per_meter": 1.693,      # số cân thật: 10.16 kg/cây chia 6m
        })
        line = self._line(hop_kg, dim_length=2000, piece_count=3)
        self.assertAlmostEqual(line._dlm_auto_quantity(), 6.0 * 1.693, places=6)

    # T3: tấm
    def test_t3_sheet_to_tam(self):
        """TC-INT-TestMaterialCalcKind-005: Mặt bàn 1200×500 mm trên tôn khổ 1,25×2,5 m =
        0.192 tấm.
        """
        ton = self.Product.create({
            "name": "Tôn CT3 2mm (test tấm)",
            "product_kind": "material",
            "uom_id": self.uom_tam.id, "uom_po_id": self.uom_tam.id,
            "dlm_calc_kind": "sheet",
            "dlm_sheet_w": 1.25, "dlm_sheet_h": 2.5,
        })
        line = self._line(ton, dim_length=1200, dim_width=500, piece_count=1)
        self.assertAlmostEqual(line._dlm_auto_quantity(), 0.192, places=6)

    # T4: đếm / định lượng, không tự tính
    def test_t4_bulk_keeps_manual_quantity(self):
        """TC-INT-TestMaterialCalcKind-006: Vật tư dlm_calc_kind='bulk' (định lượng, không
        suy theo quy cách) thì _dlm_auto_quantity() trả về None và onchange không ghi đè
        số lượng kỹ thuật đã nhập tay.
        """
        son = self.Product.create({
            "name": "Sơn tĩnh điện (test bulk)",
            "product_kind": "material",
            "uom_id": self.uom_kg.id, "uom_po_id": self.uom_kg.id,
            "dlm_calc_kind": "bulk",
        })
        line = self._line(son, dim_length=1200, piece_count=3, quantity=0.4)
        self.assertIsNone(line._dlm_auto_quantity(),
                          "Vật tư định lượng phải để kỹ thuật nhập thẳng")
        self.assertEqual(line.quantity, 0.4, "Số kỹ thuật nhập không bị ghi đè")

    # ------------------------------------------------------------------
    # T5 — 🔴 hai trục vuông góc: kho cấp NGUYÊN cây, định mức vẫn LẺ
    # ------------------------------------------------------------------
    def test_t5_cay_rounding_nguyen_dinh_muc_van_le(self):
        """TC-INT-TestMaterialCalcKind-007: Cây để `rounding = 1.0` (kho không xé lẻ
        được một cây) NHƯNG dòng định mức vẫn giữ 0.2333 cây để tính giá đúng.

        Đỏ ở vế sau = `rounding` của ĐVT đã leo sang tầng định mức: một chi tiết
        dùng 1,4 m thép bị tính tròn nguyên cây ⇒ giá vốn đồ nhỏ đội ~4 lần.
        Độ mịn của định mức do "Product Unit of Measure" quyết định (≥4 chữ số),
        không phải do `rounding`.
        """
        self.assertEqual(self.uom_cay.rounding, 1.0,
                         "Cây phải cấp phát nguyên chiếc")
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure")
        self.assertGreaterEqual(precision, 4, "Cần ≥4 chữ số cho định mức lẻ")

        bom = self._bom(self.hop_25x50, dim_length=700, piece_count=2,
                        quantity=1.4 / 6)
        self.assertAlmostEqual(bom.line_ids.quantity, 0.2333, places=4)
        nho = self._bom(self.hop_25x50, dim_length=570, piece_count=1,
                        quantity=570 / 6000)
        self.assertAlmostEqual(nho.line_ids.quantity, 0.095, places=4)

    # ------------------------------------------------------------------
    # T6 — K16: thu hồi phế liệu không còn trừ vào giá vốn
    # ------------------------------------------------------------------
    # Hai test cũ (T6/T6b) canh phép quy đổi cây thì kg của tiền thu hồi. Người
    # dùng chốt 2026-08-13 BỎ cách tính này, nên phép quy đổi đó không còn tồn
    # tại. Test mới canh đúng bất biến MỚI, và canh ở chỗ đắt nhất: giá vốn.
    def test_t6_khong_con_tru_tien_thu_hoi_vao_gia_von(self):
        """TC-INT-TestMaterialCalcKind-008: Cấu hình thu hồi cũ còn nguyên trên vật tư vẫn
        không được ảnh hưởng một đồng nào — nếu không, hai đường tính giá lệch nhau âm
        thầm.
        """
        scrap = self.Product.create({
            "name": "Phế liệu thép (test)", "product_kind": "material",
            "uom_id": self.uom_kg.id, "uom_po_id": self.uom_kg.id,
            "list_price": 8000,
        })
        self.hop_25x50.write({
            "dlm_has_recovery": True, "dlm_recovery_rate": 55.0,
            "dlm_scrap_product_id": scrap.id,
        })
        line = self._line(self.hop_25x50, quantity=10.0, waste_rate=10.0,
                          is_override=True)

        self.assertEqual(line._dlm_recovery_value(), 0.0)
        self.assertEqual(line.recovery_value, 0.0)
        self.assertAlmostEqual(
            line.subtotal, line.effective_qty * line.price_snapshot, places=2,
            msg="Thành tiền dòng BOM = số lượng × đơn giá, không trừ gì nữa.")

    def test_t6b_khong_con_doi_khai_khoi_luong_cho_thu_hoi(self):
        """TC-INT-TestMaterialCalcKind-009: Trước K16, bật thu hồi mà chưa khai khối
        lượng/đơn vị là "thiếu field". Không còn tiền thu hồi thì điều kiện đó cũng hết
        lý do.
        """
        ton_kg = self.Product.create({
            "name": "Tôn CT3 (test bán theo kg)", "product_kind": "material",
            "uom_id": self.uom_kg.id, "uom_po_id": self.uom_kg.id,
            "dlm_calc_kind": "sheet", "dlm_mass_per_sqm": 15.7,
            "dlm_has_recovery": True, "dlm_recovery_rate": 60.0,
        })
        self.assertEqual(ton_kg._dlm_calc_missing_fields(), [])
        line = self._line(ton_kg, quantity=100.0, waste_rate=5.0,
                          is_override=True)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    # T7 - quy cách vật tư không còn chặn việc xác nhận định mức
    def test_t7_confirm_no_longer_blocks_incomplete_material(self):
        """TC-INT-TestMaterialCalcKind-010: Đảo chiều 2026-08-21: trước đây cổng cứng chặn BOM khi vật tư
        chưa khai Chiều dài cây. Số lượng nay kỹ thuật khai thẳng theo đơn vị
        mua nên mẫu số đó không còn ảnh hưởng gì, giữ cổng lại là chặn nhầm
        đúng những BOM hợp lệ."""
        thieu = self.Product.create({
            "name": "Thép hộp thiếu chiều dài cây (test)",
            "product_kind": "material",
            "uom_id": self.uom_cay.id, "uom_po_id": self.uom_cay.id,
            "dlm_calc_kind": "cut_length",
            "dlm_stock_length": 0,
        })
        bom = self._bom(thieu, quantity=2)
        bom.action_confirm()
        self.assertEqual(bom.status, "confirmed")

    # T8: BOM mẫu phải mang theo Số đoạn
    def _template(self, **line_vals):
        template = self.env["dl.bom.template"].create({
            "name": "Mẫu khung bàn (test số đoạn)",
            "product_category_id": self.categ_ban.id,
            "line_ids": [(0, 0, dict(line_vals, material_id=self.hop_25x50.id))],
        })
        template.action_confirm()
        return template

    def test_t8_piece_count_survives_template_copy(self):
        """TC-INT-TestMaterialCalcKind-012: Chép từ BOM mẫu: quên piece_count trong
        BOM_LINE_MIXIN_FIELDS thì mọi BOM tạo từ mẫu âm thầm mất số đoạn, rơi về 1.
        """
        template = self._template(dim_length=700, piece_count=4, quantity=1)
        bom = self.Bom.create({
            "product_id": self.product_ban.id,
            "bom_type": "template",
            "product_qty": 1,
        })
        self.env["dl.bom.from.template.wizard"].create({
            "bom_id": bom.id, "template_id": template.id,
        }).action_confirm()
        self.assertEqual(bom.line_ids.piece_count, 4)
        self.assertEqual(bom.line_ids.dim_length, 700)

    def test_t8b_param_map_fills_piece_count_as_int(self):
        """TC-INT-TestMaterialCalcKind-013: Ánh xạ tham số vào Số đoạn: giá trị tuyến tính
        là float, phải ép về số nguyên tròn, không thì 3.9999 bị cắt cụt thành 3 đoạn.
        """
        template = self._template(quantity=1)
        template.param_ids = [(0, 0, {
            "code": "N", "name": "Số nan", "required": True})]
        template.line_ids.param_map_ids = [(0, 0, {
            "target_field": "piece_count", "param_id": template.param_ids.id,
            "factor": 1.0,
        })]
        bom = template.generate_instance(self.product_ban, {"N": 4})
        self.assertEqual(bom.line_ids.piece_count, 4)

    # T9 - số kỹ thuật gõ là số cuối cùng, không cơ chế nào đè lên
    def test_t9_typed_quantity_is_never_overwritten(self):
        """TC-INT-TestMaterialCalcKind-014: Kỹ thuật khai 2 cây (đã gồm phần thừa do cắt) thì phải giữ nguyên 2,
        kể cả khi dòng còn mang kích thước cắt cũ từ dữ liệu trước."""
        line = self._line(self.hop_25x50, dim_length=700, piece_count=2,
                          quantity=2.0)
        line.dim_length = 1500
        self.assertEqual(line.quantity, 2.0)

    def test_t9b_auto_quantity_onchange_is_gone(self):
        """TC-INT-TestMaterialCalcKind-015: Onchange tự điền phải biến mất, không chỉ ngừng gọi.

        Nó bám vào material_id, nên nếu ai đó cho dim_length hiện lại trên
        form thì nó âm thầm sống dậy và đè lên số kỹ thuật vừa gõ. Test này nổ
        ngay lúc hàm được đặt lại, thay vì để giá vốn lệch trong im lặng."""
        self.assertFalse(
            hasattr(self.env["dl.bom.line"], "_onchange_dlm_auto_quantity"),
            "Đã gỡ 2026-08-21, xem chú thích ở dl_bom_line_mixin.py")

    # T10: tấm bán theo kg dùng kg/m² khai thẳng, không suy từ quy cách
    def _ton_kg(self, **extra):
        return self.Product.create(dict({
            "name": "Tôn CT3 2mm (test bán theo kg)",
            "product_kind": "material",
            "uom_id": self.uom_kg.id, "uom_po_id": self.uom_kg.id,
            "dlm_calc_kind": "sheet", "dlm_mass_per_sqm": 15.7,
        }, **extra))

    def test_t10_sheet_sold_by_kg_uses_declared_mass_per_sqm(self):
        """TC-INT-TestMaterialCalcKind-016: Miếng 1200×500 = 0.6 m² x 15.7 kg/m² = 9.42 kg.

        Con số 15.7 là kg cân thật do người dùng khai. Bản trước tính diện tích nhân độ
        dày nhân khối lượng riêng, ra đúng số barem, tức lặp lại chính lỗi mà cả đợt
        thiết kế này sinh ra để loại bỏ.
        """
        line = self._line(self._ton_kg(), dim_length=1200, dim_width=500,
                          piece_count=1)
        self.assertAlmostEqual(line._dlm_auto_quantity(), 0.6 * 15.7, places=6)

    def test_t10b_sheet_by_kg_missing_mass_per_sqm_no_longer_blocks(self):
        """TC-INT-TestMaterialCalcKind-017: Đảo chiều 2026-08-21, cùng lý do T7: kg/m² chỉ là mẫu số của bộ
        tự tính, không còn là điều kiện để xác nhận định mức."""
        thieu = self._ton_kg(dlm_mass_per_sqm=0)
        bom = self._bom(thieu, quantity=9.42)
        bom.action_confirm()
        self.assertEqual(bom.status, "confirmed")

    def test_no_geometry_fields_left_on_material(self):
        """TC-INT-TestMaterialCalcKind-018: Quy cách hình học đã bị gỡ khỏi vật tư, mọi mẫu
        số nay khai thẳng.
        """
        for gone in ("dlm_profile_kind", "dlm_spec_a", "dlm_spec_b",
                     "dlm_spec_t", "dlm_density"):
            self.assertNotIn(gone, self.Product._fields,
                             "%s phải được gỡ khỏi product.product" % gone)
