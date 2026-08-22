"""Tách trục BOM: version / variant / instance.

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §3 (ba trục), §7.4c (C1–C5),
§15.3 (RC05, RC14). Bất biến được kiểm: I7 và I9 (§7.1).

Vì sao cần bộ test này: BOM báo giá (bom_type='quotation') là định mức riêng
của một đơn, tồn tại song song với các đơn khác, nên không được tranh cờ
"phiên bản hiện hành" với định mức chuẩn của sản phẩm. Trước đây nó tranh cờ:
mỗi lần Kỹ thuật hoàn tất một dòng RFQ, định mức chuẩn của sản phẩm lại bị
đơn lẻ đó ghi đè.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestBomAxisSeparation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({"name": "Bàn thép (test)"})
        cls.product = cls.env["product.product"].create({
            "name": "Bàn thép khung hộp (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
        })
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 40x40x1.4 (test)",
            "product_kind": "material",
        })

    def _make_bom(self, bom_type, version, product=None, qty=1.0):
        """BOM tối thiểu nhưng đủ điều kiện xác nhận (phải có ít nhất 1 dòng vật tư)."""
        return self.env["dl.bom"].create({
            "product_id": (product or self.product).id,
            "bom_type": bom_type,
            "version": version,
            "product_qty": qty,
            "line_ids": [(0, 0, {
                "material_id": self.material.id,
                "quantity": 1.0,
            })],
        })

    # I7: instance không bao giờ là phiên bản hiện hành
    def test_quotation_bom_never_becomes_current(self):
        """TC-INT-TestBomAxisSeparation-001: RC05: xác nhận BOM báo giá không bật cờ hiện
        hành.
        """
        quotation_bom = self._make_bom("quotation", 1)
        quotation_bom.action_confirm()

        self.assertEqual(quotation_bom.status, "confirmed")
        self.assertFalse(
            quotation_bom.is_current,
            "BOM báo giá là định mức của một đơn, không phải phiên bản của sản phẩm",
        )

    def test_standard_bom_still_becomes_current(self):
        """TC-INT-TestBomAxisSeparation-002: Không hồi quy: BOM chuẩn vẫn phải nhận cờ hiện
        hành như trước.
        """
        standard = self._make_bom("template", 1)
        standard.action_confirm()

        self.assertTrue(
            standard.is_current,
            "BOM chuẩn (template) vẫn là trục thời gian, phải giữ nguyên hành vi",
        )

    def test_quotation_boms_do_not_steal_current_from_standard(self):
        """TC-INT-TestBomAxisSeparation-003: RC05 (trọng tâm): ba đơn khác kích thước không
        được đụng vào định mức chuẩn.

        Đây là kịch bản đã từng hỏng: mỗi lần hoàn tất một dòng RFQ, BOM riêng của đơn
        đó lại thành "phiên bản hiện hành" của sản phẩm.
        """
        standard = self._make_bom("template", 1)
        standard.action_confirm()
        self.assertTrue(standard.is_current)

        for serial in (1, 2, 3):
            instance = self._make_bom("quotation", serial)
            instance.action_confirm()
            self.assertFalse(instance.is_current)

        standard.invalidate_recordset()
        self.assertTrue(
            standard.is_current,
            "Định mức chuẩn phải giữ nguyên cờ hiện hành sau 3 đơn tuỳ kích thước",
        )

    # I9: mỗi sản phẩm tối đa một bản hiện hành, và phải là BOM chuẩn
    def test_at_most_one_current_bom_per_product_and_it_is_standard(self):
        """TC-INT-TestBomAxisSeparation-004: I9: xác nhận 2 BOM chuẩn (version 1, 2) rồi
        thêm 1 BOM báo giá cùng sản phẩm. Tìm theo is_current=True chỉ trả về đúng 1 bản
        ghi, kiểu template, và đó là bản chuẩn mới nhất (version 2).
        """
        first = self._make_bom("template", 1)
        first.action_confirm()
        second = self._make_bom("template", 2)
        second.action_confirm()

        instance = self._make_bom("quotation", 1)
        instance.action_confirm()

        current = self.env["dl.bom"].search([
            ("product_id", "=", self.product.id),
            ("is_current", "=", True),
        ])
        self.assertEqual(len(current), 1, "Mỗi sản phẩm chỉ có một bản hiện hành")
        self.assertEqual(current.bom_type, "template")
        self.assertEqual(current, second, "Bản chuẩn mới hơn thay thế bản cũ")

    # Chỉnh định mức cho một đơn phải ra BOM báo giá, không phải BOM mẫu
    def test_editing_standard_bom_for_an_order_creates_quotation_bom(self):
        """TC-INT-TestBomAxisSeparation-005: copy() kế thừa bom_type, nên nếu không ghi đè
        thì chỉnh một BOM mẫu cho một đơn lại đẻ thêm một BOM mẫu khác: định mức của đơn
        đó chiếm số phiên bản trong dòng dõi định mức chuẩn của sản phẩm, sai nhãn, và
        có thể bị lấy làm giá vốn chuẩn nếu sản phẩm là bán thành phẩm.
        """
        standard = self._make_bom("template", 1)
        standard.action_confirm()

        customer = self.env["res.partner"].create({
            "name": "Khách test copy BOM",
            "partner_role": "customer",
            # dl_partner: khách CÁ NHÂN phải có điện thoại, và số KHÔNG được trùng
            # giữa các khách ⇒ mỗi file test giữ một số riêng.
            "phone": "0989204711",
        })
        # Dòng gia công bắt buộc có Nhóm SP — nhóm định tuyến form Sales và mẫu
        # định mức. Bài test này chỉ soi trục BOM nên nhóm rỗng là đủ.
        categ = self.env["product.category"].create({
            "name": "Bàn thép (test copy BOM)",
            "parent_id": self.env.ref("dl_product.categ_root_finished").id,
        })
        request = self.env["dl.quotation.request"].create({
            "customer_id": customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_category_id": categ.id,
                "product_name": "Bàn thép UAT copy",
                "quantity": 1.0,
                "dimension_note": "1400x830",
            })],
        })
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=request.line_ids[0].id).create({
                "rfq_line_id": request.line_ids[0].id,
                "product_id": self.product.id,
                "manual_bom_id": standard.id,
            })

        wizard.action_edit_selected_bom()
        edited = wizard.manual_bom_id

        self.assertNotEqual(edited, standard, "Bản đã duyệt phải được sao chép")
        self.assertEqual(
            edited.bom_type, "quotation",
            "Định mức chỉnh cho một đơn là BOM báo giá, không phải BOM mẫu",
        )
        self.assertEqual(edited.status, "draft")
        self.assertTrue(edited.is_rfq_provisional)
        self.assertEqual(edited.rfq_source_line_id, request.line_ids[0])
        self.assertEqual(
            standard.version, 1,
            "Dòng dõi định mức chuẩn không bị bản của một đơn chiếm số",
        )

    def test_version_numbering_untouched(self):
        """TC-INT-TestBomAxisSeparation-006: C3: không đụng đến _version_domain().

        Đánh số vẫn theo (product, bom_type) để giữ nguyên SQL constraint
        unique(product_id, version, bom_type). Chỉ cờ hiện hành bị chặn.
        """
        standard = self._make_bom("template", 1)
        instance = self._make_bom("quotation", 1)

        self.assertEqual(standard._compute_next_version(), 2)
        self.assertEqual(
            instance._compute_next_version(), 2,
            "BOM báo giá vẫn được cấp số sê-ri tăng dần trong phạm vi của nó",
        )
