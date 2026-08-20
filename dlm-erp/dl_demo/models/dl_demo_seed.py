# -*- coding: utf-8 -*-
"""Seed kịch bản "giá vật tư lấy theo tồn kho" — bấm thử được trên UI.

Khác `post_init_hook` (chỉ chạy lúc `-i`), khối này gọi qua `<function>` trong
data file nên chạy cả khi `-u dl_demo`. Vì thế nó phải TỰ CHẶN chạy lại: mọi
bước đều tra trước rồi mới tạo.

Kịch bản dựng ra:
    • Vật tư riêng "Thép hộp 40×80×2 (demo giá kho)" — không đụng seed cũ.
    • Hai lô nhập THẬT qua đơn mua: 30 cây @195.000 và 20 cây @205.000.
    • Bảng giá NCC hiện hành 215.000 ⇒ mua thêm tính theo giá này.
    • Báo giá A: đặt 80 cái ⇒ 50 lấy từ kho + 30 phải mua ⇒ 205.000 đ/cây.
    • Báo giá B: đã quá hạn + khách đã đồng ý ⇒ bấm "Tạo đơn bán hàng" là bị
      CHẶN, phải bấm "Cập nhật giá theo thị trường" trước. Giá NCC đã được
      đẩy lên 240.000 sau khi lập B nên con số sẽ nhảy thấy rõ.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Tên vật tư dùng làm mốc idempotent — có nó nghĩa là kịch bản đã dựng rồi.
_MAT_NAME = "Thép hộp 40×80×2 (demo giá kho)"
_PRODUCT_NAME = "Khung bàn thép 40×80 (demo giá kho)"
# Mốc idempotent là DÒNG BÁO GIÁ — đầu ra thật của kịch bản. Lấy mốc là vật tư
# thì một lần seed hỏng giữa chừng sẽ khoá luôn mọi lần chạy sau, đúng cái bẫy
# đã dính ở lần đầu.
_LINE_A = "%s — 80 cái" % _PRODUCT_NAME
_LINE_B = "%s — 100 cái (quá hạn)" % _PRODUCT_NAME

_GIA_LO_CU = 195_000       # đ/cây, nhập trước
_GIA_LO_MOI = 205_000      # đ/cây, nhập sau
_GIA_BANG_LUC_BAO = 215_000  # đ/cây, bảng giá NCC lúc lập báo giá
_GIA_BANG_HOM_NAY = 240_000  # đ/cây, thị trường đã tăng sau khi báo giá B hết hạn


class DlDemoSeed(models.AbstractModel):
    _name = "dl.demo.seed"
    _description = "Seed kịch bản demo (gọi từ data file)"

    # ------------------------------------------------------------------
    @api.model
    def seed_stock_pricing(self):
        """Điểm vào. Bọc try/except: seed hỏng KHÔNG được làm vỡ lệnh -u."""
        # 🔴 Mốc đặt ở DÒNG RFQ, không đặt ở dòng báo giá: engine đặt tên
        # dòng báo giá bằng `display_name` của sản phẩm nên chuỗi mốc
        # ("— 80 cái") bị mất hẳn. Mốc không khớp thì seed chạy lại mỗi
        # lần `-u dl_purchase` (Odoo cascade sang dl_demo), đẻ thêm bảng
        # giá và GHI ĐÈ giá đang áp dụng. Đã dính thật: 45 dòng rác.
        if self.env["dl.quotation.request.line"].search_count(
                [("product_name", "=", _LINE_A)]):
            _logger.info("dl_demo: kịch bản giá-theo-kho đã có — bỏ qua.")
            return True
        try:
            with self.env.cr.savepoint():
                self._build_stock_pricing()
            _logger.info("dl_demo: seed kịch bản giá-theo-kho — OK.")
        except Exception as exc:  # noqa: BLE001 — seed không được làm vỡ -u
            _logger.warning("dl_demo: seed kịch bản giá-theo-kho LỖI: %s",
                            exc, exc_info=True)
        return True

    # ------------------------------------------------------------------
    def _build_stock_pricing(self):
        from odoo.addons.dl_demo.hooks import DemoBuilder

        env = self.env
        builder = DemoBuilder(env)
        ncc = builder.ref("dl_demo.demo_supplier_hoa_phat")
        khach = builder.ref("dl_demo.demo_customer_tan_tien")
        if not ncc or not khach:
            _logger.warning("dl_demo: thiếu NCC/khách seed — bỏ kịch bản giá-theo-kho.")
            return

        self._bao_dam_cau_hinh_gia()
        nhom = builder.ref("dl_product.categ_khung_thep_han")
        thep = self._tra_hoac_tao(_MAT_NAME, {"product_kind": "material"})
        san_pham = self._tra_hoac_tao(_PRODUCT_NAME, {
            "product_kind": "manufactured",
            "categ_id": nhom.id if nhom else False,
        })
        # 1 cây thép cho 1 sản phẩm. is_override để bộ tự-tính định mức không
        # ghi đè — vật tư demo này cố ý không khai quy cách cắt.
        bom = env["dl.bom"].search(
            [("product_id", "=", san_pham.id)], limit=1)
        bom = bom or builder._make_bom(san_pham, [{
            "material": thep, "quantity": 1.0, "is_override": True,
            "waste_rate": 0.0,
        }], status="confirmed", bom_type="template")
        if not bom:
            _logger.warning("dl_demo: không dựng được BOM demo giá kho.")
            return

        # ── Hai lô nhập THẬT: đi trọn đơn mua → nhận → kiểm, để lô mang giá ──
        if not thep.seller_ids:
            builder._price_row(thep, ncc, _GIA_LO_CU, state="applied")
        if not self._da_co_ton(thep):
            self._nhap_lo(ncc, thep, 30, _GIA_LO_CU)
            self._doi_gia_bang(builder, thep, ncc, _GIA_LO_MOI)
            self._nhap_lo(ncc, thep, 20, _GIA_LO_MOI)

        # Bảng giá lúc lập báo giá. Cố ý KHÔNG đẻ thêm mốc trung gian: mỗi lần
        # đổi giá là một dòng trên màn Bảng giá Vật tư, seed khoe lịch sử là
        # seed rải rác lên màn của người dùng. Hai lô đã mang giá riêng rồi.
        self._doi_gia_bang(builder, thep, ncc, _GIA_BANG_LUC_BAO)

        # ── Báo giá A: 80 cái ⇒ 50 từ kho + 30 phải mua ──────────────────────
        _rfq_a, bao_gia_a = builder._quoted_rfq(khach, [
            dict(builder._manufactured_line(san_pham, bom, 80, name=_LINE_A),
                 product_category_id=nhom.id if nhom else False)])
        if bao_gia_a:
            bao_gia_a.message_post(body=(
                "<p><b>Kịch bản demo — giá vật tư lấy theo tồn kho.</b></p>"
                "<p>Kho có 50 cây (30 @195.000 nhập trước, 20 @205.000 nhập "
                "sau). Đơn cần 80 cây ⇒ 30 cây còn lại mua theo bảng giá "
                "215.000. Đơn giá vật tư ra <b>205.000 đ/cây</b>, còn nền giá "
                "sàn vẫn là 215.000.</p>"
                "<p>Mở tab <i>Phân tích giá thành</i> để xem dòng giải trình "
                "và khối <i>Vật tư phải mua thêm</i>.</p>"))

        # ── Báo giá B: quá hạn + khách đã đồng ý ─────────────────────────────
        _rfq_b, bao_gia_b = builder._quoted_rfq(khach, [
            dict(builder._manufactured_line(san_pham, bom, 100, name=_LINE_B),
                 product_category_id=nhom.id if nhom else False)])
        if bao_gia_b:
            self._lam_qua_han(builder, bao_gia_b)
            # Thị trường tăng SAU khi báo giá B hết hạn ⇒ bấm cập nhật là thấy nhảy.
            self._doi_gia_bang(builder, thep, ncc, _GIA_BANG_HOM_NAY)
            bao_gia_b.message_post(body=(
                "<p><b>Kịch bản demo — khách chốt muộn.</b></p>"
                "<p>Báo giá lập 10 ngày trước, hạn 7 ngày, khách đồng ý hôm "
                "nay. Đơn cần 100 cây mà kho chỉ có 50 ⇒ 50 cây phải mua, và "
                "giá thép đã tăng 215.000 → 240.000 trong lúc chờ.</p>"
                "<p>Đơn giá vật tư sẽ nhảy <b>207.000 → 219.500 đ/cây</b> khi "
                "bấm cập nhật.</p>"
                "<p>Bấm <i>Tạo đơn bán hàng</i> sẽ bị <b>chặn</b>. Bấm "
                "<i>Cập nhật giá theo thị trường</i> → giá đổi nên báo giá "
                "quay về <b>Nháp</b>: khách chưa được chào mức mới, phải "
                "gửi lại khách → khách đồng ý → rồi mới lên đơn.</p>"))

    # ------------------------------------------------------------------
    def _bao_dam_cau_hinh_gia(self):
        """Không có markup đang áp dụng thì engine ném QTE-005 và mọi báo giá chết.

        DB dev đang trống bảng này (gap đã ghi ở `Cau_hinh_bao_gia_...md`), nên
        seed phải tự dựng.

        Vẫn đi qua luồng duyệt thật (`action_submit_approval` → duyệt yêu cầu →
        `_on_approval_approved` kích hoạt rule) chứ không ghi thẳng
        `state='active'`. Không dùng `action_apply_self_approve` vì nó kiểm vai
        trò duyệt của NGƯỜI BẤM, mà seed chạy dưới OdooBot — OdooBot không phải
        Giám đốc. Đây cũng là cách `hooks._resolve_approval` đang làm."""
        Rule = self.env["dl.pricing.profit.rule"]
        if Rule.search_count([("state", "=", "active")]):
            return
        rule = Rule.create({
            "company_id": self.env.company.id,
            "target_markup": 20.0,
            "min_markup": 8.0,
            "valid_from": fields.Date.context_today(self),
            "change_reason": "Seed demo — chính sách lợi nhuận khởi tạo.",
        })
        rule.action_submit_approval()
        request = self.env["dl.pricing.approval.request"].search(
            [("state", "=", "pending")], order="id desc", limit=1)
        if request:
            request.write({
                "state": "approved",
                "resolved_by_id": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
            })
        rule._on_approval_approved(request)
        _logger.info("dl_demo: đã dựng chính sách lợi nhuận 20%%/8%% (state=%s).",
                     rule.state)

    def _tra_hoac_tao(self, name, vals):
        """Tra theo tên rồi mới tạo — để chạy lại không đẻ bản sao."""
        Product = self.env["product.product"]
        found = Product.search([("name", "=", name)], limit=1)
        return found or Product.create(dict(vals, name=name))

    def _da_co_ton(self, product):
        """Đã có tồn ở Kho nguyên vật liệu chưa (chạy lại thì đừng nhập thêm lô)."""
        location = self.env["stock.location"].sudo()._dlm_location(
            "dl_inventory.stock_location_nhan_kho")
        return bool(self.env["stock.quant"].sudo().search_count([
            ("location_id", "child_of", location.id),
            ("product_id", "=", product.id),
        ]))

    def _doi_gia_bang(self, builder, product, ncc, price):
        """Đổi bảng giá NCC đang áp dụng — gỡ dòng cũ rồi tạo dòng mới.

        Không sửa giá dòng cũ: `is_applied` chỉ cho MỘT dòng, và lịch sử giá là
        thứ demo cần thấy (màn Bảng giá vật tư hiện đủ các mốc)."""
        product.sudo().seller_ids.filtered("is_applied").write({"is_applied": False})
        return builder._price_row(product, ncc, price, state="applied")

    def _nhap_lo(self, ncc, product, qty, price):
        """Đơn mua → nhận đủ → kiểm đạt ⇒ một lô mang đúng giá đã chốt.

        Đi trọn luồng thật chứ không dựng tồn bằng kiểm kê: giá vốn chỉ đóng lên
        lô ở `button_validate` của phiếu nhận, kiểm kê tay thì lô không có giá và
        cả kịch bản mất ý nghĩa."""
        env = self.env
        order = env["dl.purchase.order"].create({
            "partner_id": ncc.id,
            "date_expected": fields.Date.context_today(self),
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
            })],
        })
        order.action_dlm_confirm()
        receipt = order.dlm_picking_ids[:1]
        if not receipt:
            _logger.warning("dl_demo: đơn mua %s không sinh phiếu nhận.", order.name)
            return order
        for move in receipt.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        receipt.button_validate()
        qc = receipt.move_ids.move_dest_ids.picking_id.filtered(
            lambda p: p.picking_type_id.sequence_code == "KC")[:1]
        if qc:
            qc.action_dlm_pass_all()
            qc.action_dlm_validate_qc()
        return order

    def _lam_qua_han(self, builder, quotation):
        """Lùi báo giá về 10 ngày trước (hạn 7 ngày ⇒ quá hạn 3 ngày) rồi cho khách đồng ý.

        Ghi thẳng `state` thay vì đi qua action: các action gửi/đồng ý đóng dấu
        ngày HÔM NAY, làm hỏng đúng cái mốc thời gian mà kịch bản cần."""
        lap = fields.Date.context_today(self) - fields.date_utils.relativedelta(days=10)
        builder._resolve_approval(quotation)
        quotation.sudo().write({
            "date_order": lap,
            "pricing_date": lap,
            "validity_date": lap + fields.date_utils.relativedelta(days=7),
            "state": "accepted",
        })
        return quotation
