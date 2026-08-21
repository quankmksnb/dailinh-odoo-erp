# -*- coding: utf-8 -*-
"""Bảng giá NCC: dòng nào là "nhà cung cấp khác", dòng nào chỉ là giá cũ của
chính họ.

Hai lỗi được canh ở đây, cả hai đều IM LẶNG — không có gì nổ ra, chỉ có màn hình
nói sai và người mua đọc nhầm:

1. Nhãn dòng phụ in cứng "Nhà cung cấp khác" cho MỌI dòng không-đang-áp-dụng,
   kể cả khi đó là giá của CHÍNH nhà cung cấp đang dùng.
2. Giá hỏi lại trong cùng một ngày: `date_end` không được nhỏ hơn `date_start`
   nên dòng cũ chỉ đóng được về đúng hôm nay ⇒ vẫn lọt bộ lọc "Còn hiệu lực"
   suốt hôm đó, và bảng giá bày ra hai dòng của cùng một nhà cung cấp.
"""

from datetime import date

from lxml import etree

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install", "dl_product")
class TestSupplierinfoRowRoles(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `mobile` bắt buộc với partner (_check_partner_contact_channel ở
        # dl_partner) — thiếu là chết ở setUpClass chứ không phải ở ca đang đo.
        cls.hoa_phat = cls.env["res.partner"].create({
            "name": "Thép Hòa Phát (test vai trò dòng)",
            "partner_role": "supplier", "mobile": "0900000201"})
        cls.phu_thinh = cls.env["res.partner"].create({
            "name": "Cơ khí Phú Thịnh (test vai trò dòng)",
            "partner_role": "supplier", "mobile": "0900000202"})
        cls.thep = cls.env["product.product"].create({
            "name": "Thép hộp 40x40x1.8 (test vai trò dòng)",
            "product_kind": "material"})

    def _row(self, partner, price, start=None):
        return self.env["product.supplierinfo"].create({
            "partner_id": partner.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id,
            "price": price,
            "date_start": start or date.today(),
        })

    def _con_hieu_luc_domain(self):
        """Domain của bộ lọc "Còn hiệu lực" LẤY THẲNG TỪ VIEW.

        Chép lại domain vào test thì test vẫn xanh khi view bị sửa hỏng — mà
        view mới là thứ người dùng thực sự nhìn qua."""
        view = self.env.ref("dl_product.view_dl_supplierinfo_search")
        node = etree.fromstring(view.arch_db).xpath(
            "//filter[@name='con_hieu_luc']")[0]
        return safe_eval(node.get("domain"), {"context_today": date.today})

    def _tren_man_hinh(self):
        """Các dòng giá của vật tư này mà màn Bảng giá thực sự bày ra."""
        # set(ids): thứ tự sắp xếp của list không phải thứ đang đo.
        return set(self.env["product.supplierinfo"].search(
            self._con_hieu_luc_domain()
            + [("product_tmpl_id", "=", self.thep.product_tmpl_id.id)]).ids)

    # ------------------------------------------------------------------
    def test_gia_cu_cung_ncc_cung_ngay_roi_khoi_man_hinh(self):
        """Hòa Phát báo lại giá trong cùng ngày ⇒ chỉ còn MỘT dòng Hòa Phát."""
        cu = self._row(self.hoa_phat, 5000.0)
        cu.action_approve()                       # duyệt là tự áp dụng (chưa có ai)
        self.assertTrue(cu.is_applied)

        moi = self._row(self.hoa_phat, 6000.0)
        moi.action_approve()
        moi.action_set_applied()

        self.assertTrue(cu.dlm_superseded, "Giá cũ phải được đánh dấu đã bị thay")
        self.assertFalse(moi.dlm_superseded)
        self.assertEqual(
            self._tren_man_hinh(), {moi.id},
            "Cùng nhà cung cấp báo giá lại thì màn hình chỉ được còn 1 dòng — "
            "dòng cũ đóng date_end về đúng hôm nay nên bộ lọc ngày KHÔNG tự loại "
            "được nó.")

    def test_ncc_khac_van_o_lai_lam_phuong_an_thay_the(self):
        """Giá của NCC khác là chào giá song song — không được biến mất theo."""
        hp = self._row(self.hoa_phat, 5000.0)
        hp.action_approve()
        pt = self._row(self.phu_thinh, 7000.0)
        pt.action_approve()                       # đã có dòng áp dụng ⇒ chỉ 'Đã duyệt'

        moi = self._row(self.hoa_phat, 6000.0)
        moi.action_approve()
        moi.action_set_applied()

        self.assertFalse(pt.dlm_superseded)
        self.assertEqual(self._tren_man_hinh(), {moi.id, pt.id})

    def test_nhan_dong_phu_noi_dung_ncc(self):
        """Nhãn phải phân biệt được NCC khác / giá mới của chính họ / giá cũ."""
        hp = self._row(self.hoa_phat, 5000.0)
        hp.action_approve()
        self.assertFalse(hp.dlm_alt_label, "Dòng đang áp dụng không có nhãn phụ")

        pt = self._row(self.phu_thinh, 7000.0)
        pt.action_approve()
        self.assertEqual(pt.dlm_alt_label, "Nhà cung cấp khác")

        # Giá mới của CHÍNH Hòa Phát, đã duyệt nhưng chưa áp dụng.
        cho = self._row(self.hoa_phat, 6000.0)
        cho.action_approve()
        self.assertEqual(
            cho.dlm_alt_label, "Giá mới chờ áp dụng",
            "Giá mới của chính nhà cung cấp đang dùng KHÔNG phải 'nhà cung cấp khác'")

        cho.action_set_applied()
        hp.invalidate_recordset()
        self.assertEqual(hp.dlm_alt_label, "Giá cũ — đã thay")
