# -*- coding: utf-8 -*-
"""Giá vật tư trong báo giá = lô đang có trong kho (FIFO) + giá mua mới cho phần thiếu.

Phép thử xương sống là ``test_tron_gia_kho_va_phan_phai_mua``: khách đặt lượng
vượt tồn, hệ thống phải tính phần có sẵn theo GIÁ ĐÃ MUA và phần thiếu theo GIÁ
MUA HÔM NAY. Ra sai con số này thì báo giá hoặc lỗ (tính thấp) hoặc mất đơn
(tính cao) — và không lỗi nào nổ ra để biết.

``test_gia_san_khong_an_theo_lo_cu`` canh cái bẫy ngược lại: giá thành được rẻ
nhờ lô cũ thì GIÁ SÀN vẫn phải neo theo giá mua lại. Sàn tụt theo lô cũ là mỗi
vòng giá thép tăng lại bào một nấc biên, sổ vẫn lãi mà tiền thì hụt dần.
"""

from datetime import timedelta

from lxml import etree

from odoo.tools.safe_eval import safe_eval

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestQuotationStockPrice(DlPurchaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["dl.quotation.pricing.service"]
        cls.ctx = {
            "company": cls.env.company,
            "currency": cls.env.company.currency_id,
            "pricing_date": fields.Date.today(),
        }

    def _gia_ncc(self, price):
        """Đặt bảng giá NCC đang áp dụng = giá mua lại hôm nay."""
        applied = self.thep.seller_ids.filtered("is_applied")
        applied.write({"is_applied": False})
        return self._apply_price(self.thep, self.vendor, price)

    def _nhap_kho(self, qty, price):
        """Nhập thật qua đơn mua ⇒ lô mang đúng giá đã chốt."""
        order = self._mk_po([(self.thep, qty, price)])
        self._receive_po(order)
        return order

    # ------------------------------------------------------------------
    def test_tron_gia_kho_va_phan_phai_mua(self):
        """30 cây trong kho @200k + 70 cây phải mua @220k ⇒ 214.000 đ/cây."""
        self._nhap_kho(30, 200000)
        self._gia_ncc(220000)

        info = self.service._material_unit_price(self.thep, 100.0, self.ctx)

        self.assertAlmostEqual(info["qty_from_stock"], 30.0, places=2)
        self.assertAlmostEqual(info["qty_to_buy"], 70.0, places=2)
        # (30 × 200.000 + 70 × 220.000) / 100
        self.assertAlmostEqual(info["unit_price"], 214000.0, places=2)
        # Giá mua lại KHÔNG bị lô cũ kéo xuống — đây là nền của giá sàn.
        self.assertAlmostEqual(info["replacement_price"], 220000.0, places=2)
        self.assertIn("phải mua", info["note"])

    def test_ton_du_thi_khong_co_phan_mua(self):
        """Tồn nhiều hơn nhu cầu ⇒ giá thành đúng bằng giá lô, không dính giá mới."""
        self._nhap_kho(50, 200000)
        self._gia_ncc(260000)

        info = self.service._material_unit_price(self.thep, 20.0, self.ctx)

        self.assertAlmostEqual(info["qty_from_stock"], 20.0, places=2)
        self.assertAlmostEqual(info["qty_to_buy"], 0.0, places=2)
        self.assertAlmostEqual(info["unit_price"], 200000.0, places=2)

    def test_kho_rong_thi_y_het_bang_gia(self):
        """Không tồn ⇒ hành vi phải trùng khít bản gốc ở dl_sale."""
        self._gia_ncc(215000)

        info = self.service._material_unit_price(self.thep, 40.0, self.ctx)

        self.assertAlmostEqual(info["qty_from_stock"], 0.0, places=2)
        self.assertAlmostEqual(info["qty_to_buy"], 40.0, places=2)
        self.assertAlmostEqual(info["unit_price"], 215000.0, places=2)
        self.assertAlmostEqual(info["replacement_price"], 215000.0, places=2)

    def test_lay_lo_cu_truoc_khi_co_hai_lo(self):
        """Hai lô hai giá ⇒ phải ăn hết lô CŨ rồi mới sang lô mới (FIFO)."""
        self._nhap_kho(30, 200000)
        self._nhap_kho(90, 220000)
        self._gia_ncc(240000)

        info = self.service._material_unit_price(self.thep, 100.0, self.ctx)

        # Đủ hàng trong kho ⇒ không phải mua; 30 cây giá cũ + 70 cây giá mới.
        self.assertAlmostEqual(info["qty_to_buy"], 0.0, places=2)
        self.assertAlmostEqual(
            info["unit_price"] * 100.0, 21400000.0, places=0)

    def test_hang_da_giu_cho_khong_duoc_tinh_la_co_san(self):
        """Tồn đã giữ chỗ cho đơn khác thì KHÔNG được coi là hàng của báo giá này."""
        self._nhap_kho(30, 200000)
        self._gia_ncc(220000)
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.thep.id),
            ("location_id", "=", self.loc_kho.id),
        ], limit=1)
        quant.reserved_quantity = 30.0

        info = self.service._material_unit_price(self.thep, 100.0, self.ctx)

        self.assertAlmostEqual(info["qty_from_stock"], 0.0, places=2)
        self.assertAlmostEqual(info["unit_price"], 220000.0, places=2)

    # ------------------------------------------------------------------
    def test_gia_san_khong_an_theo_lo_cu(self):
        """Giá thành rẻ nhờ lô cũ, nhưng giá vật tư nuôi GIÁ SÀN vẫn là giá mua lại."""
        self._nhap_kho(100, 200000)
        self._gia_ncc(300000)

        bom = self._mk_bom(qty_thep=1.0)
        mat_unit, mat_repl, _op, _specs = self.service._bom_unit_cost(
            bom, self.ctx, visited=frozenset(), order_qty=10.0)

        # 10 sp × 1 cây, kho có đủ 100 ⇒ giá thành ăn theo lô cũ.
        self.assertAlmostEqual(mat_unit, 200000.0, places=2)
        # Còn sàn thì neo theo giá mua lại — đây là điểm dễ làm sai nhất.
        self.assertAlmostEqual(mat_repl, 300000.0, places=2)

    def test_dat_nhieu_hon_ton_thi_gia_thanh_nang_len(self):
        """Cùng một BOM, đặt càng nhiều thì phần phải mua càng lớn ⇒ đơn giá vật tư tăng."""
        self._nhap_kho(10, 200000)
        self._gia_ncc(300000)
        bom = self._mk_bom(qty_thep=1.0)

        it, _r1, _o1, _s1 = self.service._bom_unit_cost(
            bom, self.ctx, visited=frozenset(), order_qty=10.0)
        nhieu, _r2, _o2, _s2 = self.service._bom_unit_cost(
            bom, self.ctx, visited=frozenset(), order_qty=20.0)

        self.assertAlmostEqual(it, 200000.0, places=2)
        # 20 cây: 10 từ kho @200k + 10 mua @300k ⇒ 250.000/cây.
        self.assertAlmostEqual(nhieu, 250000.0, places=2)
        self.assertGreater(nhieu, it)

    # ------------------------------------------------------------------
    def _mk_bom(self, qty_thep=1.0):
        """BOM tối thiểu: 1 sản phẩm gia công cần `qty_thep` cây thép, không hao hụt."""
        product = self.env["product.product"].create({
            "name": "Khung thép (test giá kho)",
            "product_kind": "manufactured",
        })
        return self.env["dl.bom"].create({
            "name": "BOM-GIAKHO",
            "product_id": product.id,
            "bom_type": "template",
            "product_qty": 1.0,
            "line_ids": [(0, 0, {
                "material_id": self.thep.id,
                "quantity": qty_thep,
                "waste_rate": 0.0,
            })],
        })


@tagged("post_install", "-at_install", "dl_purchase")
class TestBuyPriceGate(DlPurchaseCase):
    """Không cam kết giá với khách trên một giá mua chưa ai kiểm.

    Phần vật tư LẤY TỪ KHO có giá chắc chắn (lô đã đóng giá). Phần PHẢI MUA thì
    chỉ là bảng giá NCC — có thể đã cũ. Gửi khách lúc đó là cam kết 7 ngày trên
    con số chưa kiểm; mua về đắt hơn thì phần chênh ăn thẳng vào biên lãi và
    KHÔNG có chứng từ nào nổ ra để biết. Đây là bộ canh đúng lỗ đó.
    """

    def _quo(self, shortage=True):
        """Báo giá + 1 dòng + 1 cấu phần vật tư — giả lập kết quả của engine.

        🔴 Cấu phần phải gắn vào DÒNG chứ không gắn thẳng vào header: cờ thiếu
        hàng duyệt `line_ids.component_ids`. Gắn nhầm chỗ thì cờ luôn False và
        bộ test xanh giả."""
        quo = self.env["dl.quotation"].create({
            "partner_id": self.customer.id,
            "state": "draft",
        })
        line = self.env["dl.quotation.line"].create({
            "quotation_id": quo.id,
            "name": "Khung thép (test cổng giá mua)",
            "line_type": "manufactured",
            "qty": 100.0,
            "price_unit": 250000.0,
        })
        self.env["dl.quotation.price.component"].create({
            "quotation_id": quo.id,
            "quotation_line_id": line.id,
            "component_type": "material",
            "material_id": self.thep.id,
            "qty": 100.0,
            "dlm_qty_to_buy": 30.0 if shortage else 0.0,
        })
        quo.invalidate_recordset()
        return quo

    def test_thieu_vat_tu_thi_chua_gui_khach_duoc(self):
        quo = self._quo(shortage=True)
        self.assertTrue(quo.dlm_need_price_confirm)
        with self.assertRaises(UserError) as ctx:
            quo._dlm_check_ready_to_send()
        self.assertIn("chưa được", ctx.exception.args[0])

    def test_du_hang_thi_khong_chan(self):
        """Đủ hàng trong kho ⇒ giá đã chắc chắn ⇒ gửi khách thẳng, không chờ ai."""
        quo = self._quo(shortage=False)
        self.assertFalse(quo.dlm_need_price_confirm)
        self.assertTrue(quo._dlm_check_ready_to_send())

    def test_mua_hang_xac_nhan_thi_mo_cong(self):
        quo = self._quo(shortage=True)
        quo.with_user(self._mua_hang()).action_dlm_confirm_buy_price()
        self.assertFalse(quo.dlm_need_price_confirm)
        self.assertTrue(quo._dlm_check_ready_to_send())

    def test_chi_mua_hang_duoc_xac_nhan(self):
        """Sales tự xác nhận giá mua của chính mình là mất kiểm soát chéo."""
        quo = self._quo(shortage=True)
        with self.assertRaises(UserError):
            quo.with_user(self._sales()).action_dlm_confirm_buy_price()

    def test_tinh_lai_gia_thi_xac_nhan_cu_het_hieu_luc(self):
        """Số phải mua đổi ⇒ xác nhận cũ nói về một con số không còn tồn tại."""
        quo = self._quo(shortage=True)
        quo.with_user(self._mua_hang()).action_dlm_confirm_buy_price()
        self.assertFalse(quo.dlm_need_price_confirm)
        quo.recompute_quotation_clear_confirm()
        self.assertTrue(quo.dlm_need_price_confirm)

    # ------------------------------------------------------------------
    def _mua_hang(self):
        return self._user("mh.gate", "dl_base.dl_group_purchasing")

    def _sales(self):
        return self._user("ba.gate", "dl_base.dl_group_ba")

    def _user(self, login, group_xmlid):
        """User test PHẢI có email: `action_dlm_confirm_buy_price` ghi chatter,
        mà `message_post` từ chối tác giả không có địa chỉ gửi."""
        group = self.env.ref(group_xmlid)
        return self.env["res.users"].create({
            "name": login, "login": login,
            "email": "%s@test.local" % login,
            "groups_id": [(6, 0, [group.id])],
        })


@tagged("post_install", "-at_install", "dl_purchase")
class TestVongGia(DlPurchaseCase):
    """Vòng giá: giá chốt thật quay về bảng giá, và giá cũ phải CHẾT hẳn.

    Trước đợt này bảng giá là sổ lịch sử đội lốt bảng giá hiện hành: dòng
    195.000 từ tháng 1 vẫn ghi "Đã duyệt / Còn hiệu lực", và bỏ áp dụng dòng
    hiện hành rồi áp nhầm nó là mọi báo giá mới tính theo giá 8 tháng trước —
    hai thao tác, không một cảnh báo.
    """

    def _gia_cu(self, price, ngay_truoc=30):
        """Bảng giá phát hành TRƯỚC đây — ca thật của "giá cũ".

        Không dùng giá cùng ngày: hai dòng cùng `date_start` thì đóng ngày về
        "hôm qua" bị kẹp lại thành chính ngày đó (không được đẻ date_end <
        date_start), nên cả hai vẫn còn hiệu lực trong ngày. Đó là hành vi ĐÚNG
        — thép đổi giá hai lần một ngày thì cả hai giá đều từng có hiệu lực —
        và cũng không phải cái bẫy đang cần chặn (giá đặt hôm nay không phải
        giá cũ 8 tháng)."""
        row = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id, "price": price,
            "date_start": fields.Date.today() - timedelta(days=ngay_truoc),
            "approval_state": "approved",
        })
        row.action_set_applied()
        return row

    def test_ap_dung_gia_moi_thi_gia_cu_het_hieu_luc(self):
        cu = self._gia_cu(200000)
        moi = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id, "price": 260000,
            "date_start": fields.Date.today(), "approval_state": "approved",
        })
        cu.action_unset_applied()
        moi.action_set_applied()

        self.assertTrue(cu.date_end, "giá cũ phải bị đóng Đến ngày")
        self.assertFalse(cu._is_valid_on(fields.Date.today()))
        self.assertFalse(moi.date_end)

    def test_gia_cu_da_dong_thi_khong_ap_dung_nham_duoc(self):
        """Lá chắn thật: đóng ngày xong thì `_ensure_currently_valid` tự chặn."""
        cu = self._gia_cu(200000)
        moi = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id, "price": 260000,
            "date_start": fields.Date.today(), "approval_state": "approved",
        })
        cu.action_unset_applied()
        moi.action_set_applied()
        moi.action_unset_applied()
        with self.assertRaises(UserError):
            cu.action_set_applied()

    def test_ncc_khac_khong_bi_dong_lay(self):
        """Giá NCC khác là chào giá song song — đóng nó là xoá lựa chọn thay thế."""
        ncc2 = self.env["res.partner"].create({
            "name": "Phú Thịnh (vòng giá)", "partner_role": "supplier",
            "mobile": "0900000031"})
        khac = self.env["product.supplierinfo"].create({
            "partner_id": ncc2.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id, "price": 300000,
            "date_start": fields.Date.today(), "approval_state": "approved",
        })
        moi = self._apply_price(self.thep, self.vendor, 260000)
        moi._dlm_close_superseded()
        self.assertFalse(khac.date_end)

    def test_day_gia_tu_don_mua_ap_dung_ngay(self):
        """Đơn mua chốt xong cập nhật được giá hiện hành trong MỘT bước.

        Không đẻ dòng nháp bắt sang màn khác duyệt: người duyệt bảng giá cũng là
        nhóm Mua hàng, tách ra chỉ là tự duyệt chính mình."""
        cu = self._apply_price(self.thep, self.vendor, 200000)
        po = self._mk_po([(self.thep, 10, 275000)])
        po.action_dlm_confirm()

        act = po.action_dlm_push_price_list()
        wiz = self.env["dl.purchase.price.update.wizard"].browse(act["res_id"])
        self.assertEqual(len(wiz.line_ids), 1)
        self.assertAlmostEqual(wiz.line_ids.old_price, 200000.0, places=2)
        self.assertAlmostEqual(wiz.line_ids.new_price, 275000.0, places=2)
        self.assertTrue(wiz.line_ids.selected)
        self.assertTrue(wiz.line_ids.apply_now)

        wiz.action_confirm()
        moi = self.thep.seller_ids.filtered("is_applied")
        self.assertAlmostEqual(moi.price, 275000.0, places=2)
        self.assertEqual(moi.dlm_source_note, po._dlm_price_source_note())
        # Giá cũ tự đóng ngày ⇒ không áp nhầm lại được.
        self.assertTrue(cu.date_end)

    def test_chuyen_mua_ca_biet_chi_luu_lich_su(self):
        """Bỏ tick "Áp dụng ngay" ⇒ vẫn lưu vào bảng giá nhưng KHÔNG thành giá chào."""
        cu = self._apply_price(self.thep, self.vendor, 200000)
        po = self._mk_po([(self.thep, 2, 400000)])   # mua lẻ, giá cao bất thường
        po.action_dlm_confirm()
        act = po.action_dlm_push_price_list()
        wiz = self.env["dl.purchase.price.update.wizard"].browse(act["res_id"])
        wiz.line_ids.apply_now = False
        wiz.action_confirm()

        self.assertAlmostEqual(
            self.thep.seller_ids.filtered("is_applied").price, 200000.0, places=2,
            msg="chuyến mua lẻ KHÔNG được thành giá chào khách")
        self.assertTrue(
            self.thep.seller_ids.filtered(lambda r: r.price == 400000),
            "nhưng vẫn phải lưu lại làm lịch sử")

    def test_gia_y_het_thi_bo_tick_san(self):
        """Giá chốt trùng giá đang áp dụng ⇒ không có gì để cập nhật."""
        self._apply_price(self.thep, self.vendor, 200000)
        po = self._mk_po([(self.thep, 10, 200000)])
        po.action_dlm_confirm()
        act = po.action_dlm_push_price_list()
        wiz = self.env["dl.purchase.price.update.wizard"].browse(act["res_id"])
        self.assertFalse(wiz.line_ids.selected)

    # ------------------------------------------------------------------
    # Chốt đơn ⇒ bảng giá tự theo, nhưng có ngưỡng
    # ------------------------------------------------------------------
    def test_chot_don_gia_lech_nho_thi_tu_ap_dung(self):
        """Trôi giá thị trường bình thường ⇒ bảng giá tự theo, không bấm gì thêm."""
        self._apply_price(self.thep, self.vendor, 200000)
        po = self._mk_po([(self.thep, 50, 210000)])      # +5%, dưới ngưỡng 10%
        po.action_dlm_confirm()

        ap = self.thep.seller_ids.filtered("is_applied")
        self.assertAlmostEqual(ap.price, 210000.0, places=2)
        self.assertEqual(ap.dlm_source_note, po._dlm_price_source_note())

    def test_chot_don_gia_lech_lon_thi_KHONG_tu_ap_dung(self):
        """Lệch quá ngưỡng ⇒ chỉ lưu lịch sử. Một chuyến mua gấp không được
        định giá cho cả doanh nghiệp."""
        self._apply_price(self.thep, self.vendor, 200000)
        po = self._mk_po([(self.thep, 2, 400000)])       # +100%, mua lẻ giá sốc
        po.action_dlm_confirm()

        ap = self.thep.seller_ids.filtered("is_applied")
        self.assertAlmostEqual(ap.price, 200000.0, places=2,
                               msg="giá chào khách KHÔNG được nhảy theo chuyến cá biệt")
        self.assertTrue(self.thep.seller_ids.filtered(lambda r: r.price == 400000),
                        "nhưng vẫn phải lưu lại làm lịch sử")

    def test_gia_khong_doi_thi_khong_de_dong_rac(self):
        """Giá y hệt ⇒ không tạo dòng bảng giá nào. Đây là ca THƯỜNG GẶP NHẤT."""
        self._apply_price(self.thep, self.vendor, 200000)
        truoc = len(self.thep.seller_ids)
        po = self._mk_po([(self.thep, 50, 200000)])
        po.action_dlm_confirm()

        self.assertEqual(len(self.thep.seller_ids), truoc,
                         "giá không đổi mà vẫn đẻ dòng là rác hoá bảng giá")

    def test_vat_tu_chua_co_gia_thi_cu_ap(self):
        """Chưa có giá nào đang áp dụng ⇒ có giá còn hơn không có."""
        moi = self.env["product.product"].create({
            "name": "Thép chưa có giá (ngưỡng)", "product_kind": "material"})
        po = self._mk_po([(moi, 10, 180000)])
        po.action_dlm_confirm()

        self.assertAlmostEqual(
            moi.seller_ids.filtered("is_applied").price, 180000.0, places=2)

    # ------------------------------------------------------------------
    # Đơn HỎI GIÁ: chứng từ thật thay cho lời nhắc
    # ------------------------------------------------------------------
    def _quo_thieu(self):
        """Báo giá thiếu vật tư, vật tư đã có nhà cung cấp để hỏi."""
        self._apply_price(self.thep, self.vendor, 200000)
        quo = self.env["dl.quotation"].create({
            "partner_id": self.customer.id, "state": "draft"})
        line = self.env["dl.quotation.line"].create({
            "quotation_id": quo.id, "name": "Khung thép (hỏi giá)",
            "line_type": "manufactured", "qty": 100.0, "price_unit": 250000.0})
        self.env["dl.quotation.price.component"].create({
            "quotation_id": quo.id, "quotation_line_id": line.id,
            "component_type": "material", "material_id": self.thep.id,
            "qty": 100.0, "dlm_qty_to_buy": 30.0, "dlm_buy_price": 200000.0})
        quo.invalidate_recordset()
        return quo

    def test_hoi_gia_sinh_don_that_khong_phai_loi_nhac(self):
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()

        po = self.env["dl.purchase.order"].search([("dlm_quotation_id", "=", quo.id)])
        self.assertEqual(len(po), 1)
        self.assertEqual(po.state, "sent", "phải nằm ở nấc Đã gửi hỏi giá")
        self.assertAlmostEqual(po.line_ids.qty, 30.0, places=2)
        self.assertEqual(quo.dlm_vendor_quote_count, 1)

    def test_hoi_gia_hai_lan_khong_de_don_thu_hai(self):
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        quo.action_dlm_request_vendor_quote()
        self.assertEqual(
            self.env["dl.purchase.order"].search_count(
                [("dlm_quotation_id", "=", quo.id)]), 1)

    def test_chua_nhap_gia_thi_khong_ghi_nhan_duoc(self):
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        po = self.env["dl.purchase.order"].search([("dlm_quotation_id", "=", quo.id)])
        with self.assertRaises(UserError):
            po.action_dlm_record_vendor_price()

    def _ghi_nhan(self, po):
        """Bấm [Ghi nhận giá NCC báo] rồi Xác nhận trên modal — như người dùng."""
        act = po.action_dlm_record_vendor_price()
        wiz = self.env["dl.purchase.price.update.wizard"].browse(act["res_id"])
        wiz.action_confirm()
        return wiz

    def test_ghi_nhan_gia_KHONG_cam_ket_mua(self):
        """🔴 Ghi nhận giá ≠ đặt hàng. Báo giá chưa chắc thắng."""
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        po = self.env["dl.purchase.order"].search([("dlm_quotation_id", "=", quo.id)])
        po.line_ids.price_unit = 210000
        self._ghi_nhan(po)

        self.assertEqual(po.state, "sent", "đơn KHÔNG được tự chốt")
        self.assertFalse(po.dlm_picking_ids, "KHÔNG được sinh phiếu nhận")
        self.assertAlmostEqual(
            self.thep.seller_ids.filtered("is_applied").price, 210000.0, places=2)

    def test_ghi_nhan_gia_lech_lon_van_vao_bang_gia(self):
        """🔴 Lệch lớn KHÔNG được rơi vào nhánh "chỉ lưu Nháp".

        Đó là ca cần nhất: giá nằm Nháp ⇒ `_dlm_buy_price_moved` không thấy gì
        đổi (nó chỉ soi dòng đang áp dụng) ⇒ cổng gửi khách vẫn mở, và báo giá
        đi ra bằng giá CŨ trong khi NCC vừa báo giá gấp nhiều lần."""
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        po = self.env["dl.purchase.order"].search([("dlm_quotation_id", "=", quo.id)])
        po.line_ids.price_unit = 900000        # lệch >> ngưỡng 10%
        self._ghi_nhan(po)

        ap = self.thep.seller_ids.filtered("is_applied")
        self.assertAlmostEqual(ap.price, 900000.0, places=2,
                               msg="giá NCC vừa báo phải thành giá đang áp dụng")
        self.assertEqual(ap.dlm_source_note, po._dlm_price_source_note())

    def test_ghi_nhan_hai_lan_khong_de_dong_bang_gia_thu_hai(self):
        """Bấm ghi nhận lần hai là SỬA con số của đơn này, không đẻ dòng bản sao."""
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        po = self.env["dl.purchase.order"].search([("dlm_quotation_id", "=", quo.id)])
        po.line_ids.price_unit = 900000
        self._ghi_nhan(po)
        po.line_ids.price_unit = 950000        # NCC báo lại
        self._ghi_nhan(po)

        rows = self.env["product.supplierinfo"].search([
            ("dlm_source_note", "=", po._dlm_price_source_note()),
            ("product_id", "=", self.thep.id)])
        self.assertEqual(len(rows), 1, "một đơn × một mặt hàng = một dòng bảng giá")
        self.assertAlmostEqual(rows.price, 950000.0, places=2)
        self.assertTrue(rows.is_applied)
        # Giá vốn tham chiếu phải theo con số vừa sửa, không kẹt ở lần ghi đầu.
        self.assertAlmostEqual(self.thep.standard_price, 950000.0, places=2)

    # ------------------------------------------------------------------
    # Ranh giới HỎI GIÁ ↔ ĐƠN MUA
    # ------------------------------------------------------------------
    def _hoi_gia(self):
        """Báo giá thiếu vật tư ⇒ một đơn hỏi giá ở nấc 'Đã gửi hỏi giá'."""
        quo = self._quo_thieu()
        quo.action_dlm_request_vendor_quote()
        po = self.env["dl.purchase.order"].search(
            [("dlm_quotation_id", "=", quo.id)])
        return quo, po

    def _hang_doi_hoi_gia(self):
        """Đúng những dòng màn 'Hỏi giá chờ trả lời' bày ra ở segment mặc định."""
        return self.env["dl.purchase.order"].search([
            ("state", "=", "sent"),
            ("dlm_quotation_id", "!=", False),
            ("dlm_vendor_replied_date", "=", False)])

    def test_ghi_nhan_gia_xong_thi_roi_hang_doi_hoi_gia(self):
        """Đơn đã có giá không được nằm chắn giữa việc đang thật sự chờ.

        Nó cố ý ở lại nấc `sent` (chưa cam kết mua) nên không có trạng thái nào
        đánh dấu "xong" — trước đây hàng đợi vì thế không bao giờ vơi."""
        quo, po = self._hoi_gia()
        self.assertIn(po, self._hang_doi_hoi_gia())

        po.line_ids.price_unit = 210000
        self._ghi_nhan(po)

        self.assertTrue(po.dlm_vendor_replied_date)
        self.assertEqual(po.state, "sent", "vẫn chưa cam kết mua")
        self.assertNotIn(po, self._hang_doi_hoi_gia())
        # Vẫn tra được: domain của action không đổi, chỉ segment mặc định lọc.
        self.assertIn(po, self.env["dl.purchase.order"].search([
            ("state", "=", "sent"), ("dlm_quotation_id", "!=", False)]))

    def test_bao_gia_chua_len_don_thi_khong_chot_mua_duoc(self):
        """🔴 Cổng: chốt đơn hỏi giá lúc báo giá còn Nháp là mua cho một đơn
        hàng chưa tồn tại — khách quay xe thì thép nằm kho không ai trả tiền."""
        quo, po = self._hoi_gia()
        po.line_ids.price_unit = 210000
        po.date_expected = fields.Date.today()

        with self.assertRaises(UserError) as bat:
            po.action_dlm_confirm()
        self.assertIn(quo.name, str(bat.exception),
                      "lỗi phải nói RÕ báo giá nào đang chặn")
        self.assertEqual(po.state, "sent")
        self.assertFalse(po.dlm_picking_ids, "không được sinh phiếu nhận")

    def test_bao_gia_len_don_roi_thi_chot_mua_duoc(self):
        quo, po = self._hoi_gia()
        po.line_ids.price_unit = 210000
        po.date_expected = fields.Date.today()
        quo.sudo().state = "ordered"

        po.action_dlm_confirm()
        self.assertEqual(po.state, "confirmed")
        self.assertTrue(po.dlm_picking_ids, "chốt xong phải có phiếu nhận")

    def test_mua_chu_dong_khong_bi_cong_nay_rang(self):
        """Đơn không sinh từ báo giá (nhập thép về sẵn) không đi qua cổng."""
        po = self._mk_po([(self.thep, 50.0, 200000.0)])
        po.action_dlm_confirm()
        self.assertEqual(po.state, "confirmed")

    def test_don_hoi_gia_co_moc_gui(self):
        """Sinh thẳng ở `sent` thì mốc gửi vẫn phải có — dải chữ trên form đọc nó,
        và nó là thứ trả lời "gửi mấy ngày rồi mà NCC chưa báo giá"."""
        quo, po = self._hoi_gia()
        self.assertTrue(po.date_sent, "đơn hỏi giá phải mang mốc đã gửi")

    def test_co_khach_chot_moi_mo_duong_chot(self):
        """Cờ nuôi phần ẩn/hiện của [Chốt đơn] — phải khớp đúng cổng phía server,
        nếu không nút sáng nhất màn hình lại là nút bấm phát nào lỗi phát ấy."""
        quo, po = self._hoi_gia()
        self.assertFalse(po.dlm_customer_committed)

        quo.sudo().state = "ordered"
        po.invalidate_recordset()
        self.assertTrue(po.dlm_customer_committed)

        # Mua chủ động: không chờ khách nào cả.
        self.assertTrue(self._mk_po([(self.thep, 5.0, 100.0)]).dlm_customer_committed)

    # ------------------------------------------------------------------
    # Header: đúng MỘT nút primary cho mỗi trạng thái (§11.1)
    # ------------------------------------------------------------------
    def _nut_hien(self, po):
        """Các nút header thực sự hiện trên form của `po`, đánh dấu nút primary.

        Tự dựng lại phép `invisible` của client: đó là thứ quyết định người dùng
        nhìn thấy gì, mà không có test nào chạm tới nó thì một điều kiện sai vẫn
        đi qua toàn bộ bộ test."""
        arch = etree.fromstring(
            self.env.ref("dl_purchase.view_dl_purchase_order_form").arch_db)
        ctx = {
            "state": po.state,
            "dlm_needs_approval": po.dlm_needs_approval,
            "dlm_customer_committed": po.dlm_customer_committed,
            "dlm_quotation_id": po.dlm_quotation_id.id or False,
            "line_ids": po.line_ids.ids,
        }
        hien = []
        for b in arch.xpath("//header/button"):
            inv = b.get("invisible")
            if inv and safe_eval(" ".join(inv.split()), dict(ctx)):
                continue
            hien.append((b.get("string"),
                         "btn-primary" in (b.get("class") or "")))
        return hien

    def _primary(self, po):
        return [ten for ten, la_primary in self._nut_hien(po) if la_primary]

    def test_cta_hoi_gia_nam_o_header(self):
        """[Ghi nhận giá NCC báo] là CTA của đơn hỏi giá — phải nằm trong
        <header> cạnh các nút hành động, không lạc giữa sheet."""
        arch = etree.fromstring(
            self.env.ref("dl_purchase.view_dl_purchase_order_form").arch_db)
        nut = arch.xpath("//button[@name='action_dlm_record_vendor_price']")
        self.assertTrue(nut)
        for b in nut:
            self.assertEqual(b.getparent().tag, "header")

    def test_don_hoi_gia_khong_bay_nut_chot_don(self):
        """Chính cái người dùng thấy: đơn hỏi giá chỉ còn việc ghi nhận giá."""
        quo, po = self._hoi_gia()
        ten = [t for t, _p in self._nut_hien(po)]

        self.assertIn("Ghi nhận giá NCC báo", ten)
        self.assertNotIn("Chốt đơn", ten,
                         "server đã chặn cứng ca này — để nút sáng là mời bấm vào lỗi")
        self.assertNotIn("Trình Giám đốc duyệt", ten)
        self.assertNotIn("Đưa về nháp", ten,
                         "đưa về nháp làm đơn rơi khỏi hàng đợi hỏi giá")

    def test_khach_chot_roi_thi_chot_don_thanh_viec_chinh(self):
        quo, po = self._hoi_gia()
        quo.sudo().state = "ordered"
        po.invalidate_recordset()
        self.assertIn("Chốt đơn", [t for t, _p in self._nut_hien(po)])

    def test_moi_trang_thai_dung_MOT_nut_primary(self):
        """§11.1. Hai nút sáng cùng lúc là bắt người dùng chọn hộ máy.

        Phủ cả nấc `draft` — chỗ từng có hai nút sáng cùng lúc ([Gửi hỏi giá
        nhà cung cấp] + [Chốt đơn]) cho tới khi nút gửi hỏi giá hạ xuống phụ."""
        quo, po = self._hoi_gia()
        self.assertLessEqual(len(self._primary(po)), 1, self._primary(po))

        quo.sudo().state = "ordered"
        po.invalidate_recordset()
        self.assertLessEqual(len(self._primary(po)), 1, self._primary(po))

        tu_mua = self._mk_po([(self.thep, 5.0, 100.0)])
        self.assertLessEqual(len(self._primary(tu_mua)), 1, self._primary(tu_mua))
        tu_mua.action_dlm_confirm()
        self.assertLessEqual(len(self._primary(tu_mua)), 1, self._primary(tu_mua))


@tagged("post_install", "-at_install", "dl_purchase")
class TestDonMuaGiaThamChieu(DlPurchaseCase):
    """Màn Đơn mua hàng lấy giá thẳng từ Bảng giá nhà cung cấp.

    Ba cách hỏng, cả ba đều IM LẶNG — đơn vẫn lưu, vẫn chốt được, chỉ là bằng
    một con số không phải con số đã thoả thuận. Mà giá chốt thì đóng lên LÔ
    thành giá vốn thật, nên sai ở đây là sai vĩnh viễn.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor2 = cls.env["res.partner"].create({
            "name": "Phú Thịnh (mua hàng)", "partner_role": "supplier",
            "mobile": "0900000003"})

    def _row(self, partner, price, applied=False):
        return self.env["product.supplierinfo"].create({
            "partner_id": partner.id,
            "product_tmpl_id": self.thep.product_tmpl_id.id,
            "product_id": self.thep.id,
            "price": price,
            "date_start": fields.Date.today(),
            "approval_state": "approved",
            "is_applied": applied,
        })

    def _don(self, partner, qty=10.0):
        """Đơn mua tạo đúng như client gửi lên: KHÔNG có price_list_unit —
        field đó `readonly` nên trình duyệt không bao giờ gửi nó."""
        return self.env["dl.purchase.order"].create({
            "partner_id": partner.id,
            "date_expected": fields.Date.today(),
            "line_ids": [(0, 0, {"product_id": self.thep.id, "qty": qty})],
        })

    # ------------------------------------------------------------------
    def test_moc_gia_song_sot_sau_khi_luu(self):
        """🔴 `price_list_unit` khai readonly ⇒ client không gửi lên. Điền bằng
        onchange thôi là mất trắng, cột hiện 0 đ — và cảnh báo lệch giá lấy đúng
        ô đó làm mốc nên im luôn."""
        self._row(self.vendor, 200000.0, applied=True)
        don = self._don(self.vendor)

        self.assertAlmostEqual(don.line_ids.price_list_unit, 200000.0, places=2)
        self.assertAlmostEqual(don.line_ids.price_unit, 200000.0, places=2)

    def test_moc_la_gia_cua_CHINH_ncc_tren_don(self):
        """Đặt hàng Phú Thịnh thì mốc phải là giá Phú Thịnh, dù dòng ĐANG ÁP DỤNG
        của vật tư lại thuộc về nhà cung cấp khác."""
        self._row(self.vendor, 200000.0, applied=True)      # đang áp dụng
        self._row(self.vendor2, 275000.0)                   # đã duyệt, chưa áp dụng

        don = self._don(self.vendor2)
        self.assertAlmostEqual(don.line_ids.price_list_unit, 275000.0, places=2)

    def test_ncc_chua_co_gia_thi_roi_ve_gia_dang_ap_dung(self):
        """Có mặt bằng chung còn hơn không có mốc nào."""
        self._row(self.vendor, 200000.0, applied=True)
        don = self._don(self.vendor2)
        self.assertAlmostEqual(don.line_ids.price_list_unit, 200000.0, places=2)

    def test_doi_ncc_thi_gia_di_theo(self):
        """Thêm dòng trước rồi mới chọn nhà cung cấp — thứ tự thao tác rất thường."""
        self._row(self.vendor, 200000.0, applied=True)
        self._row(self.vendor2, 275000.0)
        don = self._don(self.vendor)
        self.assertAlmostEqual(don.line_ids.price_unit, 200000.0, places=2)

        don.partner_id = self.vendor2
        don._onchange_dlm_partner_refresh_price()

        self.assertAlmostEqual(don.line_ids.price_list_unit, 275000.0, places=2)
        self.assertAlmostEqual(don.line_ids.price_unit, 275000.0, places=2)

    def test_gia_go_tay_khong_bi_de(self):
        """Người mua thoả thuận qua điện thoại rồi gõ vào — đổi nhà cung cấp
        KHÔNG được xoá con số đó."""
        self._row(self.vendor, 200000.0, applied=True)
        self._row(self.vendor2, 275000.0)
        don = self._don(self.vendor)
        don.line_ids.price_unit = 188000.0          # gõ tay

        don.partner_id = self.vendor2
        don._onchange_dlm_partner_refresh_price()

        self.assertAlmostEqual(don.line_ids.price_unit, 188000.0, places=2,
                               msg="giá gõ tay bị đè mất")
        self.assertAlmostEqual(don.line_ids.price_list_unit, 275000.0, places=2,
                               msg="mốc để so lệch thì vẫn phải theo NCC mới")

    def test_don_hoi_gia_KHONG_duoc_dien_san_gia_chot(self):
        """🔴 Mốc để so thì có, giá chốt thì không.

        Đơn hỏi giá mở ra mà đã sẵn một con số là mời Mua hàng bấm [Ghi nhận giá
        NCC báo] luôn — đóng dấu giá CŨ như thể nhà cung cấp vừa báo. Cả luồng
        hỏi giá sinh ra để chống đúng chuyện đó."""
        self._row(self.vendor, 200000.0, applied=True)
        quo = self.env["dl.quotation"].create({
            "partner_id": self.customer.id, "state": "draft"})
        don = self.env["dl.purchase.order"].create({
            "partner_id": self.vendor.id,
            "dlm_quotation_id": quo.id,
            "state": "sent",
            "line_ids": [(0, 0, {"product_id": self.thep.id, "qty": 10.0})],
        })

        self.assertAlmostEqual(don.line_ids.price_list_unit, 200000.0, places=2,
                               msg="mốc để so lệch vẫn phải có")
        self.assertFalse(don.line_ids.price_unit,
                         "giá chốt phải để trống cho người mua gõ giá NCC báo")

    def test_gia_cu_da_bi_thay_the_khong_duoc_dung_lam_moc(self):
        """Nối với đợt sửa Bảng giá: dòng `dlm_superseded` là lịch sử, không phải
        giá của hôm nay."""
        cu = self._row(self.vendor, 200000.0, applied=True)
        moi = self._row(self.vendor, 260000.0)
        moi.action_set_applied()                    # đóng ngày + đánh dấu dòng cũ

        self.assertTrue(cu.dlm_superseded)
        don = self._don(self.vendor)
        self.assertAlmostEqual(don.line_ids.price_list_unit, 260000.0, places=2)
