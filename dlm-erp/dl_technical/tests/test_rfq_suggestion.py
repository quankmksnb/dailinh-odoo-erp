"""Bộ dò khớp SP "đã từng gia công" (§3.6, Đợt 2).

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §3.5–§3.6.

Kiểm hành vi của `_dlm_suggest_candidates` (LỚP 2) + tích hợp vào workspace:
- reference_product_id Sales chọn là tín hiệu mạnh nhất (đường A tự chọn).
- Tên trùng hệt / gần giống được chấm điểm; kết hợp nhóm để đủ ngưỡng gợi ý.
- SP đang Ngừng sử dụng bị phạt điểm.
- Ngưỡng: ≥60 = tự chọn (auto), 30–59 = gợi ý (suggest), <30 = none.
- Wizard tự chọn SP khi mở workspace nếu đạt ngưỡng auto; SP thương mại/đã
  xác định/không khả thi không gợi ý.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqSuggestion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create(
            {"name": "Khung thép SG (test)"})
        cls.other_categ = cls.env["product.category"].create(
            {"name": "Giá kệ SG (test)"})
        # SP "đã từng gia công" — active, tên đặc trưng để so khớp.
        cls.existing = cls.env["product.product"].create({
            "name": "Khung sắt V5 1200x800 (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Cty khớp gợi ý (test)",
            "partner_role": "customer",
            # dl_partner: khách CÁ NHÂN phải có điện thoại, và số KHÔNG được trùng
            # giữa các khách ⇒ mỗi file test giữ một số riêng.
            "phone": "0989204716",
        })
        # Sản phẩm thương mại cho ca "dòng thương mại không bao giờ gợi ý":
        # dòng loại này bắt buộc có SP xác định (_check_product_type_required).
        cls.trading_product = cls.env["product.product"].create({
            "name": "Ốc vít M8 (test gợi ý)",
            "product_kind": "trading",
            "dlm_lifecycle_state": "active",
        })
        # Định mức đã duyệt cho cls.existing — _check_product_has_bom chặn gán
        # resolved_product_id cho SP gia công chưa có BOM confirmed/locked.
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp (test gợi ý)",
            "product_kind": "material",
        })
        cls.existing_bom = cls.env["dl.bom"].create({
            "product_id": cls.existing.id,
            # 🔴 'quotation' chứ KHÔNG phải 'template': BOM chuẩn hiện hành biến
            # sản phẩm thành mặt hàng catalog ⇒ dòng trỏ vào nó tự chốt qua làn
            # L0 và `suggestion_state` thành 'none', làm câm cả file test này.
            # Định mức theo đơn vẫn thoả `_check_product_has_bom`.
            "bom_type": "quotation",
            "line_ids": [(0, 0, {
                "material_id": cls.material.id, "quantity": 1.0})],
        })
        cls.existing_bom.action_confirm()

    def _rfq(self, request_type="manufactured", **line_vals):
        vals = {
            "product_type": "manufactured",
            "product_category_id": self.categ.id,
            "product_name": "Sản phẩm bất kỳ",
            "quantity": 1.0,
            # _check_manufactured_spec đòi mô tả kích thước hoặc đính kèm.
            "dimension_note": "1000x500",
        }
        vals.update(line_vals)
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": request_type,
            "line_ids": [(0, 0, vals)],
        })
        return request, request.line_ids[0]

    # ------------------------------------------------------------------
    # reference_product_id = tín hiệu mạnh nhất
    # ------------------------------------------------------------------
    def test_reference_plus_category_reaches_auto(self):
        """Sales chọn SP tham khảo (+50) + cùng nhóm (+10) = 60 ⇒ tự chọn (auto)."""
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            product_category_id=self.categ.id,
            reference_product_id=self.existing.id,
        )
        ranked = line._dlm_suggest_candidates()
        self.assertTrue(ranked, "Phải có ứng viên khi Sales chọn SP tham khảo")
        self.assertEqual(ranked[0]["product"], self.existing)
        self.assertGreaterEqual(ranked[0]["score"], 60)
        self.assertEqual(line.suggestion_state, "auto")
        self.assertEqual(line.suggested_product_id, self.existing)

    # ------------------------------------------------------------------
    # Tên trùng hệt → gợi ý (suggest), chưa đủ auto nếu đứng một mình
    # ------------------------------------------------------------------
    def test_exact_name_only_is_suggest(self):
        """Tên trùng hệt (+40) đứng một mình = 40 ⇒ gợi ý, chưa tự chọn."""
        _req, line = self._rfq(
            product_name="  khung   sắt v5 1200x800 (TEST) ",  # khác hoa/thường + thừa cách
        )
        self.assertEqual(line.suggestion_state, "suggest")
        self.assertEqual(line.suggested_product_id, self.existing)

    def test_exact_name_plus_category_reaches_auto(self):
        """Tên trùng hệt (+40) + cùng nhóm (+10) = 50 vẫn suggest; thêm khách
        từng đặt (+10) = 60 ⇒ auto. Ở đây chỉ tên+nhóm nên vẫn suggest."""
        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.categ.id,
        )
        self.assertEqual(line.suggestion_state, "suggest")

    # ------------------------------------------------------------------
    # Khách từng đặt cộng điểm
    # ------------------------------------------------------------------
    def test_same_customer_history_adds_score(self):
        """Tên trùng hệt (+40) + cùng nhóm (+10) + khách từng đặt (+10) = 60 → auto."""
        # Đơn cũ của cùng khách đã chốt SP existing.
        prev_req, prev_line = self._rfq(product_name="Đơn cũ")
        prev_line.resolved_product_id = self.existing.id

        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.categ.id,
        )
        ranked = line._dlm_suggest_candidates()
        self.assertEqual(ranked[0]["product"], self.existing)
        self.assertGreaterEqual(ranked[0]["score"], 60)
        self.assertEqual(line.suggestion_state, "auto")

    # ------------------------------------------------------------------
    # DEF-L2-004 / DEF-L2-005 / DEF-L2-006 — test đúng TC-ID theo Report 5.2
    # ------------------------------------------------------------------
    def test_customer_history_name_category_reaches_auto(self):
        """TC-INT-TestRfqSuggestion-004: Khách từng đặt (+10) cộng khớp tên
        trùng hệt (+40) + cùng nhóm (+10) = 60 -> đủ ngưỡng tự chọn.
        DEF-L2-004: đơn cũ của cùng khách đã có resolved_product_id=SP X;
        dòng RFQ mới tên trùng hệt SP X và cùng nhóm."""
        prev_req, prev_line = self._rfq(product_name="Đơn cũ (test 004)")
        prev_line.resolved_product_id = self.existing.id

        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.categ.id,
        )
        ranked = line._dlm_suggest_candidates()

        self.assertTrue(ranked, "Phải có ứng viên")
        self.assertEqual(ranked[0]["product"], self.existing)
        self.assertGreaterEqual(ranked[0]["score"], 60)
        self.assertEqual(line.suggestion_state, "auto")

    def test_trading_line_type_blocks_suggestion(self):
        """TC-INT-TestRfqSuggestion-007: dòng product_type='trading' không
        bao giờ được gợi ý, dù product_name trùng hệt một SP gia công có sẵn.
        DEF-L2-005."""
        _req, line = self._rfq(
            request_type="trading",
            product_type="trading",
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=False,
            resolved_product_id=self.trading_product.id,
        )
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    def test_resolving_line_turns_suggestion_state_none(self):
        """TC-INT-TestRfqSuggestion-008: dòng đang suggestion_state='suggest',
        khi gán line.resolved_product_id thì suggestion_state phải chuyển về
        'none' (dòng đã xác định SP thì không cần gợi ý nữa). DEF-L2-004."""
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        self.assertEqual(line.suggestion_state, "suggest")

        line.resolved_product_id = self.existing.id

        self.assertEqual(line.suggestion_state, "none")

    def test_exact_name_plus_dimension_from_name_reaches_auto(self):
        """TC-INT-TestRfqSuggestion-014: Tên trùng hệt (+40, kích thước trích
        trực tiếp từ TÊN) + khớp kích thước (+30) = 70 -> tự chọn.
        DEF-L2-006."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.other_categ.id,
            dimension_note=False,
            attachment_ids=[(0, 0, {"name": "bv.pdf", "datas": b"MA=="})],
        )
        ranked = line._dlm_suggest_candidates()

        self.assertGreaterEqual(ranked[0]["score"], 70)
        self.assertEqual(line.suggestion_state, "auto")

    # ------------------------------------------------------------------
    # SP Ngừng sử dụng bị phạt điểm
    # ------------------------------------------------------------------
    def test_obsolete_product_penalised(self):
        self.existing.dlm_lifecycle_state = "obsolete"
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            product_category_id=self.categ.id,
            reference_product_id=self.existing.id,
        )
        # +50 (tham khảo) +10 (nhóm) −60 (obsolete) = 0 < 30 ⇒ bị lọc.
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    # ------------------------------------------------------------------
    # Không có tín hiệu → không gợi ý
    # ------------------------------------------------------------------
    def test_no_signal_no_suggestion(self):
        _req, line = self._rfq(product_name="Tên hoàn toàn mới lạ ZZZ (test)")
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line.suggested_product_id)

    def test_trading_line_never_suggests(self):
        _req, line = self._rfq(
            request_type="trading",
            product_type="trading",
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=False,
            resolved_product_id=self.trading_product.id,
        )
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    def test_resolved_line_stops_suggesting(self):
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        self.assertEqual(line.suggestion_state, "suggest")
        line.resolved_product_id = self.existing.id
        self.assertEqual(
            line.suggestion_state, "none",
            "Dòng đã xác định SP thì không cần 💡 nữa")

    # ------------------------------------------------------------------
    # §3.6 · So SỐ VỚI SỐ — khổ kích thước khớp thuộc tính kỹ thuật SP
    # ------------------------------------------------------------------
    def test_parse_dimensions_patterns(self):
        """Parser trích D/R/C/độ dày từ mô tả tự do (mẫu AxB + từ khoá)."""
        Line = self.env["dl.quotation.request.line"]
        self.assertEqual(
            Line._dlm_parse_dimensions("1400x830, cao 750"),
            {"length": 1400, "width": 830, "height": 750})
        self.assertEqual(
            Line._dlm_parse_dimensions("1200 x 800 x 750"),
            {"length": 1200, "width": 800, "height": 750})
        self.assertEqual(
            Line._dlm_parse_dimensions("dài 1200 rộng 800 dày 1,4"),
            {"length": 1200, "width": 800, "thickness": 1.4})
        # Từ khoá tường minh ghi đè mẫu AxB.
        self.assertEqual(
            Line._dlm_parse_dimensions("2000x900 nhưng cao 750"),
            {"length": 2000, "width": 900, "height": 750})
        self.assertEqual(Line._dlm_parse_dimensions("không có số nào"), {})
        self.assertEqual(Line._dlm_parse_dimensions(None, ""), {})

    def test_dimension_boosts_reference_to_auto(self):
        """Ref (+50) một mình = suggest; khổ khớp thuộc tính SP (+30) = 80 → auto."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            dimension_note="Khách cần khổ 1200x800, sơn tĩnh điện",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertGreaterEqual(ranked[0]["score"], 80)
        self.assertIn("Khớp kích thước", ranked[0]["reasons"])
        self.assertEqual(line.suggestion_state, "auto")

    def test_dimension_orientation_independent(self):
        """Khổ khớp không phân biệt chiều: SP 1200x800 khớp mô tả '800 x 1200'."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            dimension_note="800 x 1200",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertIn("Khớp kích thước", ranked[0]["reasons"])
        self.assertEqual(line.suggestion_state, "auto")

    def test_dimension_mismatch_no_boost(self):
        """Khổ khác (1400x900) không cộng điểm — ref một mình vẫn chỉ suggest."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            product_category_id=self.other_categ.id,
            dimension_note="1400x900",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertEqual(ranked[0]["score"], 50)
        self.assertNotIn("Khớp kích thước", ranked[0]["reasons"])
        self.assertEqual(line.suggestion_state, "suggest")

    def test_dimension_height_disqualifies(self):
        """Khổ D×R khớp nhưng chiều cao lệch (750 vs 900) ⇒ không tính khớp."""
        self.existing.write({
            "dlm_dim_length": 1200, "dlm_dim_width": 800, "dlm_dim_height": 750})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            product_category_id=self.other_categ.id,
            dimension_note="1200x800x900",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertEqual(ranked[0]["score"], 50)
        self.assertNotIn("Khớp kích thước", ranked[0]["reasons"])

    def test_name_plus_dimension_reaches_auto(self):
        """Tên trùng hệt (+40) + khổ khớp (+30) = 70 → auto (khổ đọc ngay từ tên)."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.other_categ.id,
            dimension_note=False,
            attachment_ids=[(0, 0, {"name": "bv.pdf", "datas": b"MA=="})],
        )
        ranked = line._dlm_suggest_candidates()
        self.assertGreaterEqual(ranked[0]["score"], 70)
        self.assertEqual(line.suggestion_state, "auto")

    def test_dimension_needs_other_signal(self):
        """Khổ trùng nhưng không tín hiệu nào khác ⇒ không tự phát hiện SP mới
        (dấu vân kích thước chỉ củng cố, không đứng một mình)."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Tên hoàn toàn khác ZZZ",
            product_category_id=self.other_categ.id,
            dimension_note="1200x800",
        )
        # Không ref, không trùng tên, không cùng nhóm, không cùng khách → rỗng.
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    # ------------------------------------------------------------------
    # Tích hợp workspace — đường A tự chọn khi mở
    # ------------------------------------------------------------------
    def test_workspace_auto_selects_on_open(self):
        """Mở workspace cho dòng đạt ngưỡng auto ⇒ product_id tự điền + cờ
        auto_selected (ca lặp lại chỉ còn bấm Hoàn tất)."""
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            product_category_id=self.categ.id,
            reference_product_id=self.existing.id,
        )
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})
        self.assertEqual(wizard.product_id, self.existing,
                         "Đạt ngưỡng auto ⇒ workspace tự chọn SP")
        self.assertTrue(wizard.auto_selected)

    def test_exact_name_resolves_to_existing_product(self):
        """Tên TRÙNG HỆT ⇒ dùng lại chính sản phẩm đó, không đẻ bản trùng nghĩa.

        Điểm dò khớp chỉ 50 (nằm dải "gợi ý"), nhưng TÊN thì trùng hệt — mà tạo
        sản phẩm trùng tên vốn đã bị `_check_dlm_name_duplicate` chặn cứng. Nên
        đây là câu trả lời duy nhất chạy được, không phải phỏng đoán."""
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({})
        self.assertEqual(wizard.product_origin, "name_match")
        self.assertEqual(wizard.product_id, self.existing)

    def test_suggested_product_stays_reachable(self):
        """KTV bấm "Đổi sản phẩm" ⇒ thẻ gợi ý + danh sách chọn vẫn phục vụ được."""
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({})
        wizard.action_change_product()

        self.assertEqual(wizard.suggestion_state, "suggest")
        self.assertEqual(wizard.suggested_product_id, self.existing)
        # SP gợi ý phải nằm trong danh sách chọn được (kể cả ngoài nhóm).
        self.assertIn(self.existing, wizard.allowed_product_ids)

        wizard.action_use_suggested_product()
        self.assertEqual(wizard.product_id, self.existing)

    # ------------------------------------------------------------------
    # Làn L0-a — kiểu hàng cỡ cố định thì dòng tự chốt, không qua Kỹ thuật
    # ------------------------------------------------------------------
    def test_catalog_item_autoresolves_without_technician(self):
        """SP có ĐỊNH MỨC CHUẨN hiện hành = mặt hàng catalog ⇒ Sales chọn xong
        là dòng tự chốt, RFQ lên thẳng "Chờ tạo báo giá"."""
        catalog = self.env["product.product"].create({
            "name": "Bàn giáo viên cỡ cố định (test)",
            "categ_id": self.categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        std = self.env["dl.bom"].create({
            "product_id": catalog.id,
            "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 1.0})],
        })
        std.action_confirm()
        self.assertTrue(std.is_current, "Tiền đề: đây là định mức chuẩn hiện hành")

        req, line = self._rfq(
            product_name="Bàn giáo viên khách A đặt",
            reference_product_id=catalog.id)

        self.assertTrue(line.auto_resolved)
        self.assertEqual(line.resolved_product_id, catalog)
        self.assertEqual(line.resolved_bom_id, std)
        self.assertEqual(req.status, "confirmed",
                         "RFQ không còn việc gì cho Kỹ thuật")
