"""Giá vốn bán thành phẩm phải lấy từ ĐỊNH MỨC CHUẨN, không phải từ đơn khác.

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §17.2 (C4), §15.3 (RC14).

Lỗi được sửa: `_bom_material_cost()` chọn BOM con của bán thành phẩm bằng
``order="version desc"`` mà KHÔNG lọc `bom_type` ⇒ một BOM **báo giá** (sinh khi
xử lý RFQ cho một đơn cụ thể) có số version cao hơn sẽ thắng BOM chuẩn của
chính bán thành phẩm đó. Hệ quả: định mức riêng của đơn A âm thầm trở thành giá
vốn cho đơn B — sai lệch chỉ hiện ra ở TIỀN nên rất khó phát hiện.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestChildBomSelection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["dl.quotation.pricing.service"]
        cls.semi = cls.env["product.product"].create({
            "name": "Khung ống vuông 25x25 (test BTP)",
            "product_kind": "material_processed",
        })
        cls.raw = cls.env["product.product"].create({
            "name": "Ống thép vuông 25x25 (test vật tư)",
            "product_kind": "material",
        })

    def _make_bom(self, bom_type, version, confirm=True):
        bom = self.env["dl.bom"].create({
            "product_id": self.semi.id,
            "bom_type": bom_type,
            "version": version,
            "product_qty": 1.0,
            "line_ids": [(0, 0, {
                "material_id": self.raw.id,
                "quantity": 1.0,
            })],
        })
        if confirm:
            bom.action_confirm()
        return bom

    def test_standard_bom_wins_over_higher_numbered_quotation_bom(self):
        """RC14 — BOM chuẩn v2 phải thắng BOM báo giá v5."""
        standard = self._make_bom("template", 2)
        self._make_bom("quotation", 5)   # số sê-ri cao hơn nhưng là của MỘT đơn

        chosen = self.service._resolve_child_bom(self.semi)

        self.assertEqual(
            chosen, standard,
            "Giá vốn bán thành phẩm phải theo định mức chuẩn, không theo đơn khác",
        )

    def test_current_standard_wins_over_newer_draft_standard(self):
        """Ưu tiên 1: bản chuẩn đang là phiên bản hiện hành."""
        first = self._make_bom("template", 1)
        self.assertTrue(first.is_current)
        # Bản chuẩn v2 chưa xác nhận ⇒ không được chọn.
        self._make_bom("template", 2, confirm=False)

        self.assertEqual(self.service._resolve_child_bom(self.semi), first)

    def test_falls_back_to_quotation_bom_only_when_no_standard_exists(self):
        """Ưu tiên 3: BTP chưa từng có định mức chuẩn thì mới đành dùng BOM báo giá."""
        only_quotation = self._make_bom("quotation", 1)

        self.assertEqual(
            self.service._resolve_child_bom(self.semi), only_quotation,
            "Dữ liệu chưa hoàn chỉnh vẫn phải tính được giá, không chặn cứng",
        )

    def test_returns_empty_when_nothing_confirmed(self):
        """BOM nháp không được dùng làm giá vốn — trả rỗng để engine raise QTE-004."""
        self._make_bom("template", 1, confirm=False)

        self.assertFalse(self.service._resolve_child_bom(self.semi))
