"""Workspace xử lý dòng RFQ — "một màn, ba khối, tự thu gọn" (Đợt 3).

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §5, §9.4, §19.7.

Trọng tâm kiểm ở đây là các thay đổi HÀNH VI (không phải trình bày):
- Hoàn tất dòng TỰ xác nhận định mức còn Nháp — "một ý định = một cú bấm"
  (§19.7); bỏ vòng "sang form BOM chỉ để bấm Xác nhận rồi quay lại".
- `can_confirm` / `confirm_blocker` gác nút Hoàn tất ở decision dock: chưa đủ
  thì nút disable + nêu thiếu gì, KHÔNG raise modal (§9.4, §15.1).
- `step` là trục tiến độ SUY TỪ dữ liệu (không còn cổng chặn tuần tự).
- Nhánh "Không khả thi" ở dock loại trừ đường Hoàn tất.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqResolveWorkspace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({"name": "Bàn thép WS (test)"})
        cls.product = cls.env["product.product"].create({
            "name": "Bàn thép khung hộp WS (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
        })
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 40x40x1.4 WS (test)",
            "product_kind": "material",
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test workspace",
            "partner_role": "customer",
            # dl_partner: khách CÁ NHÂN phải có điện thoại, và số KHÔNG được trùng
            # giữa các khách ⇒ mỗi file test giữ một số riêng.
            "phone": "0989204713",
        })

    def _make_rfq_line(self):
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_category_id": self.categ.id,
                "product_name": "Bàn thép WS",
                "quantity": 2.0,
                "dimension_note": "1400x830",
            })],
        })
        return request, request.line_ids[0]

    def _make_draft_bom(self, line, with_lines=True):
        vals = {
            "product_id": self.product.id,
            "bom_type": "quotation",
            "version": 1,
            "status": "draft",
            "rfq_source_line_id": line.id,
        }
        if with_lines:
            vals["line_ids"] = [(0, 0, {
                "material_id": self.material.id,
                "quantity": 1.0,
            })]
        return self.env["dl.bom"].create(vals)

    def _wizard(self, line, **vals):
        base = {"rfq_line_id": line.id}
        base.update(vals)
        return self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create(base)

    # ------------------------------------------------------------------
    # §19.7 — Hoàn tất dòng TỰ xác nhận định mức Nháp (một cú bấm)
    # ------------------------------------------------------------------
    def test_hoan_tat_auto_confirms_draft_bom(self):
        request, line = self._make_rfq_line()
        bom = self._make_draft_bom(line)
        wizard = self._wizard(line, product_id=self.product.id, manual_bom_id=bom.id)

        # Tiền đề: đúng là định mức Nháp được tự chọn.
        self.assertEqual(wizard.selected_bom_id, bom)
        self.assertEqual(bom.status, "draft")

        wizard.action_confirm()

        self.assertEqual(
            bom.status, "confirmed",
            "Hoàn tất dòng phải TỰ xác nhận định mức Nháp (không bắt bấm 2 lần)")
        self.assertEqual(line.resolved_product_id, self.product)
        self.assertEqual(line.resolved_bom_id, bom)

    def test_confirm_bom_inline_does_not_complete_line(self):
        """Nút [Xác nhận định mức ngay] trong checklist chỉ chốt định mức, KHÔNG
        ghi kết quả về dòng — dành cho ai muốn chốt trước rồi bàn giao."""
        request, line = self._make_rfq_line()
        bom = self._make_draft_bom(line)
        wizard = self._wizard(line, product_id=self.product.id, manual_bom_id=bom.id)

        wizard.action_confirm_bom()

        self.assertEqual(bom.status, "confirmed")
        self.assertFalse(line.resolved_bom_id, "Chưa Hoàn tất thì dòng chưa có kết quả")

    # ------------------------------------------------------------------
    # §9.4 — can_confirm / confirm_blocker gác nút Hoàn tất (disable, không modal)
    # ------------------------------------------------------------------
    def test_can_confirm_requires_product(self):
        request, line = self._make_rfq_line()
        wizard = self._wizard(line)
        # Workspace nay TỰ quyết sản phẩm khi mở (2026-08-19). Cổng "chưa có sản
        # phẩm thì chưa Hoàn tất được" vẫn phải đứng — nó gác ca KTV bấm "Đổi
        # sản phẩm" rồi bỏ dở, nên dựng lại đúng ca đó.
        wizard.action_change_product()

        self.assertFalse(wizard.product_id)
        self.assertFalse(wizard.can_confirm)
        self.assertIn("sản phẩm", (wizard.confirm_blocker or "").lower())

    def test_can_confirm_requires_bom_lines(self):
        """RES-009 — định mức rỗng: nút disable + nêu lý do, thay vì để
        action_confirm nổ modal."""
        request, line = self._make_rfq_line()
        empty_bom = self._make_draft_bom(line, with_lines=False)
        wizard = self._wizard(line, product_id=self.product.id,
                              manual_bom_id=empty_bom.id)

        self.assertFalse(wizard.selected_bom_has_lines)
        self.assertFalse(wizard.can_confirm)
        self.assertIn("dòng vật tư", (wizard.confirm_blocker or "").lower())

    def test_can_confirm_true_even_when_bom_draft(self):
        """Định mức Nháp KHÔNG chặn Hoàn tất (Hoàn tất sẽ tự xác nhận, §19.7)."""
        request, line = self._make_rfq_line()
        bom = self._make_draft_bom(line)
        wizard = self._wizard(line, product_id=self.product.id, manual_bom_id=bom.id)

        self.assertEqual(bom.status, "draft")
        self.assertFalse(wizard.check_bom_confirmed)
        self.assertTrue(wizard.can_confirm, "Nháp có dòng vật tư vẫn đủ điều kiện Hoàn tất")
        self.assertFalse(wizard.confirm_blocker)

    # ------------------------------------------------------------------
    # Trục tiến độ suy từ dữ liệu
    # ------------------------------------------------------------------
    def test_step_computed_from_data(self):
        request, line = self._make_rfq_line()
        wizard = self._wizard(line)
        # Mở ra là đã có sản phẩm (hệ thống tự quyết) ⇒ đứng ngay ở khối ⑵.
        self.assertEqual(wizard.step, "bom", "Có sản phẩm sẵn → khối ⑵")

        wizard.action_change_product()
        self.assertEqual(wizard.step, "product", "Chưa có sản phẩm → khối ⑴")

        wizard.product_id = self.product.id
        self.assertEqual(wizard.step, "bom", "Có sản phẩm, chưa có định mức → khối ⑵")

        bom = self._make_draft_bom(line)
        wizard.manual_bom_id = bom.id
        # bom_ids là compute KHÔNG lưu, chỉ phụ thuộc product_id/mode — BOM vừa
        # tạo không tự lọt vào danh sách đã tính trước đó. Ngoài đời workspace
        # tính lại mỗi lần nạp; ở đây phải xoá cache thì mới đo đúng.
        wizard.invalidate_recordset()
        self.assertEqual(wizard.step, "confirm", "Đủ sản phẩm + định mức → khối ⑶")

    # ------------------------------------------------------------------
    # Lối thoát "Cần bổ sung" / "Không khả thi" mở trong MODAL (không xổ dock)
    # ------------------------------------------------------------------
    def test_exit_buttons_open_modal(self):
        request, line = self._make_rfq_line()
        wizard = self._wizard(line, product_id=self.product.id)

        act = wizard.action_show_supplement()
        self.assertEqual(act.get("res_model"), "dl.rfq.line.supplement.wizard")
        self.assertEqual(act.get("target"), "new")
        self.assertEqual(act["context"].get("default_rfq_line_id"), line.id)

        act = wizard.action_show_infeasible()
        self.assertEqual(act.get("res_model"), "dl.rfq.line.infeasible.wizard")
        self.assertEqual(act.get("target"), "new")
        self.assertEqual(act["context"].get("default_rfq_line_id"), line.id)

    def test_reopen_infeasible_line_blocks_then_reprocesses(self):
        # Mở lại dòng đã kết luận không khả thi: banner + chặn Hoàn tất cho tới
        # khi bấm "Xử lý lại dòng này".
        request, line = self._make_rfq_line()
        line.write({"is_infeasible": True, "infeasible_reason": "Vượt năng lực máy"})
        bom = self._make_draft_bom(line)
        wizard = self._wizard(line, product_id=self.product.id, manual_bom_id=bom.id)

        self.assertTrue(wizard.is_infeasible)
        self.assertFalse(wizard.can_confirm, "Đang kết luận Không khả thi thì chưa Hoàn tất")

        wizard.action_reopen_feasible()
        self.assertFalse(wizard.is_infeasible)
        self.assertTrue(wizard.can_confirm)

    def test_change_product_reopens_block(self):
        request, line = self._make_rfq_line()
        bom = self._make_draft_bom(line)
        wizard = self._wizard(line, product_id=self.product.id, manual_bom_id=bom.id)

        wizard.action_change_product()

        self.assertFalse(wizard.product_id)
        self.assertFalse(wizard.manual_bom_id)
        self.assertEqual(wizard.step, "product")
