"""Trình dựng dữ liệu demo giao dịch cho DL-ERP.

Chạy qua ``post_init_hook`` khi cài ``dl_demo`` (``-i dl_demo``). Khác với XML
tĩnh, driver này gọi thẳng các entry-point nghiệp vụ thật (engine giá, state
machine, tạo đơn) để dữ liệu đi qua đúng logic, liên kết chuẩn giữa các màn.

An toàn cài đặt: mỗi khối bọc try/except + savepoint — một kịch bản lỗi KHÔNG
làm hỏng toàn bộ quá trình ``-i`` (chỉ log cảnh báo và bỏ qua khối đó).
"""

import logging

from odoo import fields, _

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Điểm vào seed. Idempotent: đã có RFQ demo thì bỏ qua (tránh nhân đôi khi
    lỡ chạy lại trên DB đã seed)."""
    if env["dl.quotation.request"].search_count([]):
        _logger.info("dl_demo: đã có RFQ trong DB — bỏ qua seed giao dịch.")
        return
    DemoBuilder(env).run()


class DemoBuilder:
    def __init__(self, env):
        # su=True: seed chạy dưới quyền hệ thống, vượt các field-RBAC (Kỹ thuật/
        # Sales) và cho phép set các field readonly về mặt UI.
        self.env = env
        self.today = fields.Date.context_today(env["res.partner"])

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    def run(self):
        steps = (
            ("giá NCC", self.build_supplier_prices),
            ("BOM + bản vẽ", self.build_boms_and_drawings),
            ("RFQ (7 trạng thái)", self.build_rfqs),
            ("báo giá (vòng đời)", self.build_quotations),
            ("nhóm khách hàng", self.refresh_customer_groups),
        )
        for label, fn in steps:
            try:
                with self.env.cr.savepoint():
                    fn()
                _logger.info("dl_demo: seed %s — OK.", label)
            except Exception as exc:  # noqa: BLE001 — seed không được làm vỡ -i
                _logger.warning("dl_demo: seed %s LỖI: %s", label, exc, exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def ref(self, xmlid):
        """env.ref không raise — trả None nếu thiếu (một số seed có thể vắng)."""
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _confirmed_bom(self, product):
        """BOM confirmed/locked mới nhất của một SP (tra qua DB, bền với savepoint)."""
        if not product:
            return None
        return self.env["dl.bom"].search(
            [("product_id", "=", product.id), ("status", "in", ("confirmed", "locked"))],
            order="id desc", limit=1)

    def _price_row(self, product, supplier, price, state="applied",
                   valid_from="2025-01-01"):
        """Tạo 1 dòng giá NCC (product.supplierinfo) ở trạng thái chỉ định.

        state: 'draft' (Nháp), 'approved' (Đã duyệt, chưa áp dụng),
               'applied' (Đã duyệt + Đang áp dụng — dùng để tính giá BOM/báo giá).
        """
        if not product or not supplier:
            return None
        vals = {
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "partner_id": supplier.id,
            "price": price,
            "min_qty": 1,
            "date_start": valid_from,
            "currency_id": self.env.company.currency_id.id,
        }
        if state in ("approved", "applied"):
            vals["approval_state"] = "approved"
            vals["dlm_approved_uid"] = self.env.user.id
            vals["dlm_approved_date"] = fields.Datetime.now()
        if state == "applied":
            vals["is_applied"] = True
            vals["dlm_applied_uid"] = self.env.user.id
            vals["dlm_applied_date"] = fields.Datetime.now()
        return self.env["product.supplierinfo"].create(vals)

    # ------------------------------------------------------------------
    # 1) Giá NCC
    # ------------------------------------------------------------------
    def build_supplier_prices(self):
        hoa_phat = self.ref("dl_demo.demo_supplier_hoa_phat")
        dai_bang = self.ref("dl_demo.demo_supplier_dai_bang")
        phu_thinh = self.ref("dl_demo.demo_supplier_phu_thinh")

        # Vật tư dùng trong BOM → phải "Đang áp dụng" để price_snapshot > 0
        # (giá vốn BOM, giá sàn báo giá). (product_xmlid, ncc, đơn giá).
        #
        # 🔴 ĐƠN GIÁ Ở ĐÂY LÀ ĐỒNG TRÊN ĐÚNG ĐVT MUA CỦA VẬT TƯ (đ/cây · đ/tấm ·
        # đ/cuộn · đ/kg), không phải đ/kg cho mọi thứ. Để nhầm đ/kg cho một vật
        # tư bán theo cây là hỏng ngay và hỏng lặng: giá vốn hụt ~10 lần, và
        # tiền phế liệu thu hồi (luôn quy về kg) có thể LỚN HƠN cả tiền vật tư
        # ⇒ thành tiền dòng BOM ÂM. Quy đổi tham chiếu: giá thị trường ~18.500
        # đ/kg × khối lượng mỗi đơn vị khai trên vật tư.
        applied_materials = [
            # 11.6 kg/cây × ~18.500 đ/kg
            ("dl_product.seed_mat_th_40", hoa_phat, 215_000),        # đ/cây
            # 49.06 kg/tấm (1250×2500×2mm)
            ("dl_product.seed_mat_tt_ct3_2", hoa_phat, 910_000),     # đ/tấm
            # 353.25 kg/tấm (1500×6000×5mm)
            ("dl_product.seed_mat_tt_ct3_5", hoa_phat, 6_290_000),   # đ/tấm
            # 5.6 kg/cây (hộp 25×25×1,5)
            ("dl_product.demo_product_ong_vuong", hoa_phat, 105_000),  # đ/cây
            # 392.5 kg/cuộn (khổ 1250 × 20m × 2mm)
            ("dl_product.demo_product_thep_cuon", hoa_phat, 7_260_000),  # đ/cuộn
            ("dl_product.demo_product_oc_vit", phu_thinh, 1_500),    # đ/cái
            ("dl_product.seed_mat_son_td", dai_bang, 85_000),        # đ/kg
        ]
        for xmlid, supplier, price in applied_materials:
            self._price_row(self.ref(xmlid), supplier, price, state="applied")

        # Một vật tư có 2 bảng giá đã duyệt (2 NCC) — 1 áp dụng, 1 chỉ duyệt:
        # test màn Bảng giá vật tư có nhiều dòng + trạng thái khác nhau.
        self._price_row(self.ref("dl_product.seed_mat_th_40"), phu_thinh,
                        275_000, state="approved")       # đ/cây, NCC đắt hơn
        # Một vật tư mới có giá NHÁP chờ Kế toán duyệt.
        self._price_row(self.ref("dl_product.seed_mat_th_50"), hoa_phat,
                        390_000, state="draft")          # đ/cây (16.2 kg/cây)

        # SP thương mại: 1 đang áp dụng (đủ điều kiện bán), 1 mới duyệt, 1 chưa có.
        self._price_row(self.ref("dl_demo.demo_trading_ban_le"), phu_thinh,
                        30_000, state="applied")
        self._price_row(self.ref("dl_demo.demo_trading_tay_nam"), phu_thinh,
                        42_000, state="approved")
        # demo_trading_ke_goc: cố ý KHÔNG có giá NCC.

    # ------------------------------------------------------------------
    # 2) BOM + bản vẽ
    # ------------------------------------------------------------------
    def _make_bom(self, product, lines, status="confirmed", bom_type="quotation"):
        """Tạo 1 dl.bom + dòng vật tư; đưa về trạng thái mong muốn qua action thật.

        lines: list dict giá trị dòng, bắt buộc có khoá "material" (recordset).
            Vật tư cắt đoạn/tấm nên nêu kích thước cắt (dim_length · piece_count)
            để định mức TỰ TÍNH ra đúng số cây/tấm — đó mới là dữ liệu demo thật;
            đưa thẳng "quantity" chỉ dùng cho vật tư đếm/định lượng.
        status: 'draft' | 'confirmed' | 'locked'.
        """
        if not product:
            return None
        line_vals = []
        for line in lines:
            vals = dict(line)
            material = vals.pop("material", None)
            if not material:
                continue
            vals["material_id"] = material.id
            line_vals.append((0, 0, vals))
        try:
            with self.env.cr.savepoint():
                bom = self.env["dl.bom"].create({
                    "product_id": product.id,
                    "bom_type": bom_type,
                    "product_qty": 1,
                    "line_ids": line_vals,
                })
                # ORM không chạy onchange ⇒ tự tính định mức từ kích thước cắt,
                # đúng như luồng UI (dòng nào chưa nêu kích thước thì giữ nguyên).
                for line in bom.line_ids:
                    qty = line._dlm_auto_quantity()
                    if qty is not None and qty > 0 and not line.is_override:
                        line.quantity = qty
                if status in ("confirmed", "locked"):
                    bom.action_confirm()
                if status == "locked":
                    bom.action_lock()
            return bom
        except Exception as exc:  # noqa: BLE001
            _logger.warning("dl_demo: tạo BOM cho %s LỖI: %s",
                            product.display_name, exc)
            return None

    def build_boms_and_drawings(self):
        th40 = self.ref("dl_product.seed_mat_th_40")
        ong_vuong = self.ref("dl_product.demo_product_ong_vuong")
        oc_vit = self.ref("dl_product.demo_product_oc_vit")
        thep_cuon = self.ref("dl_product.demo_product_thep_cuon")
        son_td = self.ref("dl_product.seed_mat_son_td")
        tam_sat = self.ref("dl_product.demo_product_tam_sat")  # BTP

        # (a) BOM cho BTP "Tấm sắt phủ sơn 600×400×2mm" — cắt 1 miếng 600×400 từ
        #     cuộn tôn ⇒ định mức tự ra ~0.0096 cuộn (KHÔNG phải 2.5 cuộn!).
        self._make_bom(
            tam_sat,
            [
                {"material": thep_cuon, "dim_length": 600, "dim_width": 400,
                 "piece_count": 1},
                {"material": son_td, "quantity": 0.3},          # kg — nhập thẳng
            ],
            status="confirmed",
        )

        # (b) BOM CHÍNH cho "Khung thép hàn CT-200" — có cả BTP (cha–con) →
        #     confirmed + là bom tham chiếu cho RFQ manufactured (build_rfqs).
        #     Khung 2000×1000: 4 đứng 1000 + 4 ngang 2000 = 12.000mm = 2 cây.
        ct200 = self.ref("dl_product.demo_product_ct200")
        self._make_bom(
            ct200,
            [
                {"material": th40, "dim_length": 1000, "piece_count": 4},
                {"material": th40, "dim_length": 2000, "piece_count": 4},
                {"material": oc_vit, "quantity": 24},
                {"material": tam_sat, "quantity": 1},
            ],
            status="confirmed",
        )

        # (c) BOM Nháp (màn BOM có bản Nháp) — cho "Bàn thép khung hộp"
        #     1200×800×750: 4 chân 750 + 2 dọc 1200 + 2 ngang 800, mặt bàn tôn.
        ban_thep = self.ref("dl_technical.demo_product_ban_thep")
        self._make_bom(
            ban_thep,
            [
                {"material": ong_vuong, "dim_length": 750, "piece_count": 4},
                {"material": ong_vuong, "dim_length": 1200, "piece_count": 2},
                {"material": ong_vuong, "dim_length": 800, "piece_count": 2},
                {"material": thep_cuon, "dim_length": 1200, "dim_width": 800,
                 "piece_count": 1},
            ],
            status="draft",
        )

        # (d) Bản vẽ kỹ thuật gắn với SP CT-200 (màn Bản vẽ có dữ liệu).
        #     Để 'draft' (xác nhận đòi file đính kèm — seed không có file thật).
        #     Bọc riêng để lỗi bản vẽ KHÔNG rollback các BOM ở trên.
        if ct200:
            try:
                with self.env.cr.savepoint():
                    self.env["dl.drawing"].create({
                        "name": "Bản vẽ khung thép CT-200",
                        "product_id": ct200.id,
                        "drawing_code": "BV-CT200",
                        "version": 1,
                        "status": "draft",
                        "created_by": self.env.user.id,
                    })
            except Exception as exc:  # noqa: BLE001
                _logger.warning("dl_demo: tạo bản vẽ LỖI: %s", exc)

    # ------------------------------------------------------------------
    # 3) RFQ — phủ 7 trạng thái
    # ------------------------------------------------------------------
    def _rfq(self, customer, lines):
        """Tạo RFQ + dòng (lines: list dict vals cho dòng); status suy từ dòng.

        Các trạng thái đặc biệt (returned/supplemented/processing/cancelled) do
        nơi gọi đặt thêm sau khi có RFQ.
        """
        if not customer:
            return None
        try:
            with self.env.cr.savepoint():
                rfq = self.env["dl.quotation.request"].create({
                    "customer_id": customer.id,
                    "requested_date": fields.Datetime.now(),
                    # Một RFQ chỉ một loại gia công haocwj thương mại
                    "request_type": lines[0].get("product_type", "manufactured"),
                    "line_ids": [(0, 0, l) for l in lines],
                })
                rfq._recompute_status_from_lines()
            return rfq
        except Exception as exc:  # noqa: BLE001
            _logger.warning("dl_demo: tạo RFQ cho %s LỖI: %s",
                            customer.display_name, exc)
            return None

    def build_rfqs(self):
        tan_tien = self.ref("dl_demo.demo_customer_tan_tien")
        minh_long = self.ref("dl_demo.demo_customer_minh_long")
        anh_hoang = self.ref("dl_demo.demo_customer_anh_hoang")
        phu_thinh = self.ref("dl_demo.demo_supplier_phu_thinh")
        thanh_do = self.ref("dl_demo.demo_customer_thanh_do")

        ct200 = self.ref("dl_product.demo_product_ct200")
        bom_ct200 = self._confirmed_bom(ct200)
        khung_cat = self.ref("dl_product.categ_khung_thep_han")
        ban_cat = self.ref("dl_product.categ_ban_ghe_sat")

        # (1) MỚI — Sales vừa tạo, KTV chưa đụng (dòng chưa xác định SP).
        self._rfq(tan_tien, [{
            "product_type": "manufactured",
            "product_name": "Khung thép hàn theo bản vẽ (chờ KTV)",
            "product_category_id": khung_cat.id if khung_cat else False,
            "quantity": 5,
            "dimension_note": "Khung 1200×800×750mm, thép hộp 40×40.",
        }])

        # (2) ĐANG XỬ LÝ — KTV đã nhận, 1 dòng đã xác định + 1 dòng chưa.
        rfq2 = self._rfq(minh_long, [
            {
                "product_type": "manufactured",
                "product_name": "Khung CT-200 (đã xác định)",
                "product_category_id": khung_cat.id if khung_cat else False,
                "quantity": 10,
                "dimension_note": "Khung 2000×800×750mm, thép hộp 40×40.",
                "resolved_product_id": ct200.id if ct200 else False,
                "resolved_bom_id": bom_ct200.id if bom_ct200 else False,
            },
            {
                "product_type": "manufactured",
                "product_name": "Giá đỡ đặc biệt (đang chờ KTV)",
                "product_category_id": ban_cat.id if ban_cat else False,
                "quantity": 4,
                "dimension_note": "Giá 3 tầng, cao 1800mm, tải 120kg/tầng.",
            },
        ])
        if rfq2:
            rfq2.write({
                "status": "processing",
                "received_by": self.env.user.id,
                "received_date": fields.Datetime.now(),
            })

        # (3) TRẢ LẠI BỔ SUNG — KTV trả về, dòng chờ Sales bổ sung.
        rfq3 = self._rfq(anh_hoang, [{
            "product_type": "manufactured",
            "product_name": "Bàn thao tác (thiếu kích thước)",
            "product_category_id": ban_cat.id if ban_cat else False,
            "quantity": 2,
            "dimension_note": "Mặt bàn khoảng 1200mm, chưa rõ chiều cao chân.",
        }])
        if rfq3 and rfq3.line_ids:
            rfq3.line_ids[0].write({
                "supplement_note": "Thiếu kích thước mặt bàn và chiều cao chân.",
                "supplement_done": False,
            })
            rfq3._recompute_status_from_lines()

        # (4) ĐÃ BỔ SUNG — Sales đã bổ sung, chờ KTV xử lý lại.
        rfq4 = self._rfq(phu_thinh, [{
            "product_type": "manufactured",
            "product_name": "Khung kệ kho (đã bổ sung bản vẽ)",
            "product_category_id": khung_cat.id if khung_cat else False,
            "quantity": 6,
            "dimension_note": "Kệ 4 tầng 2400×600×2000mm, theo bản vẽ đính kèm.",
        }])
        if rfq4 and rfq4.line_ids:
            rfq4.line_ids[0].write({
                "supplement_note": "Đã đính kèm bản vẽ chi tiết.",
                "supplement_done": True,
            })
            rfq4.write({"status": "supplemented"})

        # (5) CHỜ TẠO BÁO GIÁ (confirmed) — mọi dòng đã xác định SP + BOM.
        #     Để nguyên (không tạo báo giá) nhằm giữ 1 RFQ ở trạng thái confirmed.
        self._rfq(thanh_do, [{
            "product_type": "manufactured",
            "product_name": "Khung thép CT-200 (đủ điều kiện báo giá)",
            "product_category_id": khung_cat.id if khung_cat else False,
            "quantity": 8,
            "dimension_note": "Khung 2000×800×750mm, thép hộp 40×40.",
            "resolved_product_id": ct200.id if ct200 else False,
            "resolved_bom_id": bom_ct200.id if bom_ct200 else False,
        }])

        # (7) ĐÃ HỦY — test trạng thái đóng.
        rfq7 = self._rfq(tan_tien, [{
            "product_type": "manufactured",
            "product_name": "Yêu cầu khách đã rút lại",
            "product_category_id": ban_cat.id if ban_cat else False,
            "quantity": 1,
            "dimension_note": "Bàn 1500×700×750mm.",
        }])
        if rfq7:
            rfq7.action_cancel()

        # (6) ĐÃ TẠO BÁO GIÁ (quoted) được tạo trong build_quotations qua engine.

    # ------------------------------------------------------------------
    # 4) Báo giá — phủ vòng đời + đơn bán + phê duyệt
    # ------------------------------------------------------------------
    def _quoted_rfq(self, customer, lines):
        """Tạo RFQ confirmed rồi chạy engine giá → trả (rfq, quotation)."""
        rfq = self._rfq(customer, lines)
        if not rfq:
            return None, None
        # Bảo đảm confirmed (mọi dòng đã resolved).
        rfq._recompute_status_from_lines()
        if rfq.status != "confirmed":
            _logger.warning("dl_demo: RFQ %s chưa confirmed (status=%s) — bỏ tạo báo giá.",
                            rfq.name, rfq.status)
            return rfq, None
        self.env["dl.quotation.pricing.service"].create_from_rfq(rfq)
        quotation = self.env["dl.quotation"].search(
            [("quotation_request_id", "=", rfq.id)], order="id desc", limit=1)
        return rfq, quotation

    def _trading_line(self, product, qty):
        return {
            "product_type": "trading",
            "product_name": product.display_name if product else "?",
            "quantity": qty,
            "resolved_product_id": product.id if product else False,
        }

    def _manufactured_line(self, product, bom, qty, name=None):
        return {
            "product_type": "manufactured",
            "product_name": name or (product.display_name if product else "?"),
            "quantity": qty,
            # Bắt buộc theo _check_manufactured_spec: dòng gia công phải có mô tả
            # kích thước hoặc đính kèm.
            "dimension_note": "Theo định mức sản phẩm đã chuẩn hóa.",
            "resolved_product_id": product.id if product else False,
            "resolved_bom_id": bom.id if bom else False,
        }

    def _resolve_approval(self, quotation):
        """Nếu báo giá có yêu cầu phê duyệt đang chờ, DUYỆT nó (để có thể tiến
        tới accepted/ordered một cách nhất quán)."""
        req = quotation.approval_request_id
        if req and req.state == "pending":
            req.write({
                "state": "approved",
                "resolved_by_id": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
            })
            quotation.write({"approval_state": "approved"})

    def _force_state(self, quotation, target):
        """Đưa báo giá tới trạng thái đích bằng cách hợp lệ nhất có thể.

        Dùng action thật ở nơi có side-effect quan trọng (tạo đơn), còn lại
        ghi thẳng state + field phụ trợ cho tất định.
        """
        if not quotation:
            return
        validity_default = fields.Date.add(self.today, days=30)
        if target == "draft":
            return
        if target == "approved":
            self._resolve_approval(quotation)
            quotation.write({"state": "approved"})
        elif target == "sent":
            self._resolve_approval(quotation)
            quotation.write({"state": "sent", "validity_date": validity_default})
        elif target == "revision_requested":
            self._resolve_approval(quotation)
            quotation.write({
                "state": "revision_requested",
                "validity_date": validity_default,
                "revision_request_type": "commercial",
                "revision_request_note": "Khách xin giảm thêm 3% và giãn tiến độ giao.",
            })
        elif target == "rejected":
            self._resolve_approval(quotation)
            quotation.write({
                "state": "rejected",
                "reject_reason": "price_high",
                "reject_reason_note": "Khách phản hồi giá cao hơn đối thủ ~5%.",
            })
        elif target == "expired":
            self._resolve_approval(quotation)
            # Lùi cả ngày báo giá lẫn hạn hiệu lực về quá khứ để đại diện báo giá
            # thật sự đã hết hạn, đồng thời thỏa constraint validity >= date_order.
            quotation.write({
                "state": "expired",
                "date_order": fields.Date.add(self.today, days=-40),
                "validity_date": fields.Date.add(self.today, days=-10),
            })
        elif target == "accepted":
            self._resolve_approval(quotation)
            quotation.write({"state": "accepted", "validity_date": validity_default})
        elif target == "ordered":
            self._resolve_approval(quotation)
            quotation.write({"state": "accepted", "validity_date": validity_default})
            # action thật: snapshot dòng sang đơn + khóa 'ordered'.
            quotation.action_create_sale_order()
        elif target == "superseded":
            # Lập phiên bản mới: bản cũ superseded, bản mới v2 draft giữ liên kết.
            quotation.write({"state": "superseded"})
            quotation.copy({
                "revision": (quotation.revision or 1) + 1,
                "origin_quotation_id": quotation.id,
                "state": "draft",
            })

    def _scenario(self, customer, lines, target):
        """Một kịch bản báo giá độc lập chịu lỗi: tạo RFQ→engine giá→lái state.

        Bọc savepoint riêng để một kịch bản lỗi KHÔNG làm hỏng các kịch bản khác
        (vd một dòng gia công thiếu giá vốn) — chỉ log rồi bỏ qua kịch bản đó.
        """
        try:
            with self.env.cr.savepoint():
                _, quotation = self._quoted_rfq(customer, lines)
                self._force_state(quotation, target)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("dl_demo: báo giá [%s] LỖI: %s", target, exc, exc_info=True)

    def build_quotations(self):
        tan_tien = self.ref("dl_demo.demo_customer_tan_tien")
        minh_long = self.ref("dl_demo.demo_customer_minh_long")
        thanh_do = self.ref("dl_demo.demo_customer_thanh_do")
        anh_hoang = self.ref("dl_demo.demo_customer_anh_hoang")

        ban_le = self.ref("dl_demo.demo_trading_ban_le")       # list_price 45.000
        ct200 = self.ref("dl_product.demo_product_ct200")
        bom_ct200 = self._confirmed_bom(ct200)

        L = self._trading_line
        M = self._manufactured_line

        # ---- Khách THÂN THIẾT: đơn lớn > ngưỡng 150tr (đảm bảo loyal) ----
        # 6.000 × 45.000 = 270tr → 'ordered'. Cũng vượt ngưỡng → engine tạo yêu
        # cầu phê duyệt (được duyệt khi lên đơn).
        self._scenario(thanh_do, [L(ban_le, 6000)], "ordered")
        self._scenario(thanh_do, [L(ban_le, 2500)], "accepted")

        # ---- Khách CŨ: đơn nhỏ ≤ ngưỡng (existing) ----
        self._scenario(minh_long, [L(ban_le, 400)], "accepted")

        # ---- Khách MỚI: chỉ có báo giá CHƯA thắng (draft/sent/rejected) → 'new'.
        #      Dùng dòng gia công (đi BOM) để test nhánh manufactured + smart-button.
        self._scenario(tan_tien, [M(ct200, bom_ct200, 10)], "sent")
        # để nguyên 'draft' — nếu vượt ngưỡng sẽ nằm ở hòm phê duyệt.
        self._scenario(tan_tien, [M(ct200, bom_ct200, 3)], "draft")
        self._scenario(tan_tien, [L(ban_le, 200)], "rejected")

        # ---- Các trạng thái còn lại (đa dạng để test đủ) ----
        self._scenario(anh_hoang, [L(ban_le, 120)], "revision_requested")
        self._scenario(anh_hoang, [L(ban_le, 80)], "expired")
        self._scenario(minh_long, [L(ban_le, 150)], "superseded")

        # ---- HÒM PHÊ DUYỆT có việc chờ (để nguyên 'draft' → phiếu pending) ----
        # Ma trận (pricing_seed): >20tr cần Trưởng KD, >100tr cần CEO.
        # 3.000 × 45.000 = 135tr → chờ CEO.
        self._scenario(thanh_do, [L(ban_le, 3000)], "draft")
        # 700 × 45.000 = 31,5tr → chờ Trưởng KD.
        self._scenario(minh_long, [L(ban_le, 700)], "draft")

    # ------------------------------------------------------------------
    # 5) Nhóm khách hàng (computed-stored) — ép tính lại sau khi có báo giá thắng
    # ------------------------------------------------------------------
    def refresh_customer_groups(self):
        customers = self.env["res.partner"].search([("partner_role", "in", ("customer", "both"))])
        customers._compute_dlm_customer_group()
        customers.flush_recordset(["dlm_customer_group"])
