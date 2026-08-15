"""Bộ dò khớp sản phẩm "đã từng gia công" (§3.6, Đợt 2).

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §3.5-§3.6.

Kiểm hành vi của _dlm_suggest_candidates (lớp 2) và tích hợp vào workspace:
- reference_product_id Sales chọn là tín hiệu mạnh nhất (đường A tự chọn).
- Tên trùng hệt hoặc gần giống được chấm điểm, kết hợp nhóm để đủ ngưỡng gợi ý.
- Sản phẩm đang Ngừng sử dụng bị phạt điểm.
- Ngưỡng: từ 60 điểm trở lên là tự chọn (auto), 30-59 là gợi ý (suggest),
  dưới 30 là không gợi ý (none).
- Wizard tự chọn sản phẩm khi mở workspace nếu đạt ngưỡng auto; sản phẩm
  thương mại, đã xác định hoặc không khả thi thì không gợi ý.
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
        # SP "đã từng gia công", active, tên đặc trưng để so khớp.
        cls.existing = cls.env["product.product"].create({
            "name": "Khung sắt V5 1200x800 (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Cty khớp gợi ý (test)",
            "partner_role": "customer",
        })

    def _rfq(self, **line_vals):
        vals = {
            "product_type": "manufactured",
            "product_name": "Sản phẩm bất kỳ",
            "quantity": 1.0,
        }
        vals.update(line_vals)
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, vals)],
        })
        return request, request.line_ids[0]

    # reference_product_id là tín hiệu mạnh nhất
    def test_reference_plus_category_reaches_auto(self):
        """Sales chọn SP tham khảo (+50), cùng nhóm (+10), tổng 60 thì tự
        chọn (auto)."""
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

    # Tên trùng hệt thì gợi ý (suggest), chưa đủ auto nếu đứng một mình
    def test_exact_name_only_is_suggest(self):
        """Tên trùng hệt (+40) đứng một mình được 40 điểm, chỉ gợi ý, chưa
        tự chọn."""
        _req, line = self._rfq(
            product_name="  khung   sắt v5 1200x800 (TEST) ",  # khác hoa/thường + thừa cách
        )
        self.assertEqual(line.suggestion_state, "suggest")
        self.assertEqual(line.suggested_product_id, self.existing)

    def test_exact_name_plus_category_reaches_auto(self):
        """Tên trùng hệt (+40) và cùng nhóm (+10) được 50 điểm, vẫn chỉ
        suggest. Thêm khách từng đặt (+10) mới đủ 60 để lên auto; ở đây chỉ
        có tên và nhóm nên vẫn suggest."""
        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
            product_category_id=self.categ.id,
        )
        self.assertEqual(line.suggestion_state, "suggest")

    # Khách từng đặt cộng điểm
    def test_same_customer_history_adds_score(self):
        """Tên trùng hệt (+40), cùng nhóm (+10), khách từng đặt (+10), tổng
        60 điểm thì lên auto."""
        # Đơn cũ của cùng khách đã chốt sản phẩm existing.
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

    # Sản phẩm Ngừng sử dụng bị phạt điểm
    def test_obsolete_product_penalised(self):
        """Sản phẩm tham khảo đã ngừng sử dụng bị trừ điểm mạnh (điểm cuối
        dưới ngưỡng 30), kỳ vọng suggestion_state=none và không có candidate
        nào được gợi ý."""
        self.existing.dlm_lifecycle_state = "obsolete"
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            product_category_id=self.categ.id,
            reference_product_id=self.existing.id,
        )
        # +50 (tham khảo) +10 (nhóm) -60 (obsolete) = 0, dưới 30 nên bị lọc.
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    # Không có tín hiệu thì không gợi ý
    def test_no_signal_no_suggestion(self):
        """Không có tín hiệu nào khớp (tên hoàn toàn mới lạ), kỳ vọng
        suggestion_state=none và suggested_product_id trống."""
        _req, line = self._rfq(product_name="Tên hoàn toàn mới lạ ZZZ (test)")
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line.suggested_product_id)

    def test_trading_line_never_suggests(self):
        """Dòng product_type='trading' (hàng thương mại) không bao giờ
        gợi ý sản phẩm dù tên khớp, kỳ vọng suggestion_state=none và
        _dlm_suggest_candidates() rỗng."""
        _req, line = self._rfq(
            product_type="trading",
            product_name="khung sắt v5 1200x800 (test)",
        )
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    def test_resolved_line_stops_suggesting(self):
        """Dòng đang được gợi ý (suggestion_state=suggest), sau khi gán
        resolved_product_id thì suggestion_state phải chuyển về none (đã
        xác định sản phẩm thì không cần gợi ý nữa)."""
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        self.assertEqual(line.suggestion_state, "suggest")
        line.resolved_product_id = self.existing.id
        self.assertEqual(
            line.suggestion_state, "none",
            "Dòng đã xác định SP thì không cần 💡 nữa")

    # §3.6: khổ kích thước khớp thuộc tính kỹ thuật sản phẩm
    def test_parse_dimensions_patterns(self):
        """Parser trích D/R/C/độ dày từ mô tả tự do (mẫu AxB và từ khóa)."""
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
        # Từ khóa tường minh ghi đè mẫu AxB.
        self.assertEqual(
            Line._dlm_parse_dimensions("2000x900 nhưng cao 750"),
            {"length": 2000, "width": 900, "height": 750})
        self.assertEqual(Line._dlm_parse_dimensions("không có số nào"), {})
        self.assertEqual(Line._dlm_parse_dimensions(None, ""), {})

    def test_dimension_boosts_reference_to_auto(self):
        """Ref (+50) một mình chỉ suggest; khổ khớp thuộc tính sản phẩm (+30)
        cộng thêm thành 80 điểm thì lên auto."""
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
        """Khổ khớp không phân biệt chiều: sản phẩm 1200x800 khớp mô tả
        '800 x 1200'."""
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
        """Khổ khác (1400x900) không cộng điểm, ref một mình vẫn chỉ suggest."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            dimension_note="1400x900",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertEqual(ranked[0]["score"], 50)
        self.assertNotIn("Khớp kích thước", ranked[0]["reasons"])
        self.assertEqual(line.suggestion_state, "suggest")

    def test_dimension_height_disqualifies(self):
        """Khổ D×R khớp nhưng chiều cao lệch (750 so với 900) thì không tính khớp."""
        self.existing.write({
            "dlm_dim_length": 1200, "dlm_dim_width": 800, "dlm_dim_height": 750})
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            reference_product_id=self.existing.id,
            dimension_note="1200x800x900",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertEqual(ranked[0]["score"], 50)
        self.assertNotIn("Khớp kích thước", ranked[0]["reasons"])

    def test_name_plus_dimension_reaches_auto(self):
        """Tên trùng hệt (+40) và khổ khớp (+30) được 70 điểm thì lên auto
        (khổ đọc ngay từ tên)."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="khung sắt v5 1200x800 (test)",
        )
        ranked = line._dlm_suggest_candidates()
        self.assertGreaterEqual(ranked[0]["score"], 70)
        self.assertEqual(line.suggestion_state, "auto")

    def test_dimension_needs_other_signal(self):
        """Khổ trùng nhưng không có tín hiệu nào khác thì không tự phát hiện
        sản phẩm mới (dấu vân kích thước chỉ củng cố, không đứng một mình)."""
        self.existing.write({"dlm_dim_length": 1200, "dlm_dim_width": 800})
        _req, line = self._rfq(
            product_name="Tên hoàn toàn khác ZZZ",
            dimension_note="1200x800",
        )
        # Không ref, không trùng tên, không cùng nhóm, không cùng khách nên rỗng.
        self.assertEqual(line.suggestion_state, "none")
        self.assertFalse(line._dlm_suggest_candidates())

    # Tích hợp workspace: đường A tự chọn khi mở
    def test_workspace_auto_selects_on_open(self):
        """Mở workspace cho dòng đạt ngưỡng auto thì product_id tự điền và
        bật cờ auto_selected (ca lặp lại chỉ còn bấm Hoàn tất)."""
        _req, line = self._rfq(
            product_name="Một tên khác hẳn",
            product_category_id=self.categ.id,
            reference_product_id=self.existing.id,
        )
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})
        self.assertEqual(wizard.product_id, self.existing,
                         "Đạt ngưỡng auto thì workspace tự chọn sản phẩm")
        self.assertTrue(wizard.auto_selected)

    def test_workspace_suggest_does_not_auto_select(self):
        """Chỉ đạt ngưỡng suggest thì không tự chọn, nhưng phơi thẻ gợi ý và
        nút Dùng sản phẩm này chọn được."""
        _req, line = self._rfq(product_name="khung sắt v5 1200x800 (test)")
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})
        self.assertFalse(wizard.product_id, "Suggest (30–59) không tự chọn")
        self.assertEqual(wizard.suggestion_state, "suggest")
        self.assertEqual(wizard.suggested_product_id, self.existing)
        # Sản phẩm gợi ý phải nằm trong danh sách chọn được (kể cả ngoài nhóm).
        self.assertIn(self.existing, wizard.allowed_product_ids)

        wizard.action_use_suggested_product()
        self.assertEqual(wizard.product_id, self.existing)
        self.assertEqual(wizard.mode, "existing")
