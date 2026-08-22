"""Trình dựng dữ liệu demo giao dịch cho DL-ERP.

Chạy qua ``post_init_hook`` khi cài ``dl_demo`` (``-i dl_demo``). Khác với XML
tĩnh, driver này gọi thẳng các entry-point nghiệp vụ thật (engine giá, state
machine, tạo đơn) để dữ liệu đi qua đúng logic, liên kết chuẩn giữa các màn.

An toàn cài đặt: mỗi khối bọc try/except + savepoint — một kịch bản lỗi KHÔNG
làm hỏng toàn bộ quá trình ``-i`` (chỉ log cảnh báo và bỏ qua khối đó).
"""

import logging
import random

from odoo import fields, _

_logger = logging.getLogger(__name__)

# Marker idempotent riêng cho bộ seed giao dịch chính. KHÔNG dùng "đã có RFQ":
# kịch bản giá-theo-kho (dl.demo.seed, chạy qua <function> lúc NẠP DATA) tạo RFQ
# TRƯỚC khi post_init_hook chạy ⇒ nếu lấy RFQ làm mốc thì một lần `-i` sạch sẽ
# BỎ QUA toàn bộ DemoBuilder.run() (chỉ còn dữ liệu giá-theo-kho). Marker này do
# chính run() đặt ở cuối nên hai đường không giẫm chân nhau và deploy `-i` tái
# tạo được y hệt.
_SEEDED_PARAM = "dl_demo.transactions_seeded"

# Đơn giá công đoạn (đ) — mức xưởng cơ khí sắt thép. Với 'percent_material'
# price_rate là %; với 'per_unit'/'per_batch' là đồng. Các method này KHÔNG cần
# base_qty nên gắn thẳng lên BOM không sợ QTE-010.
# (operation_xmlid, method, price_rate, setup_fee)
_OPERATION_RATES = [
    ("dl_config.operation_cut",   "percent_material", 5.0,    0),        # Cắt ~5% vật liệu
    ("dl_config.operation_weld",  "per_unit",         40_000, 60_000),   # Hàn 40k/sp + 60k setup/lô
    ("dl_config.operation_grind", "per_unit",         12_000, 0),        # Mài 12k/sp
    ("dl_config.operation_drill", "per_unit",         8_000,  0),        # Khoan 8k/sp
    ("dl_config.operation_bend",  "per_unit",         15_000, 0),        # Chấn 15k/sp
    ("dl_config.operation_paint", "percent_material", 18.0,   0),        # Sơn ~18% vật liệu
]


def post_init_hook(env):
    """Điểm vào seed. Idempotent theo marker riêng (xem _SEEDED_PARAM)."""
    if env["ir.config_parameter"].sudo().get_param(_SEEDED_PARAM):
        _logger.info("dl_demo: đã seed giao dịch (marker) — bỏ qua.")
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
            ("chính sách giá", self.build_pricing_policy),
            ("đơn giá công đoạn", self.build_operation_rules),
            ("giá NCC", self.build_supplier_prices),
            ("BOM + bản vẽ", self.build_boms_and_drawings),
            ("tồn kho vật tư", self.build_stock),
            ("RFQ", self.build_rfqs),
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
        # Đặt marker CUỐI: chỉ khi đã đi hết chuỗi mới coi là seeded, để lần `-i`
        # sau (nếu lần này hỏng giữa chừng) còn chạy lại.
        self.env["ir.config_parameter"].sudo().set_param(_SEEDED_PARAM, "1")

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
    # 0) Chính sách giá + đơn giá công đoạn (engine cần trước khi tính giá)
    # ------------------------------------------------------------------
    def build_pricing_policy(self):
        """Bảo đảm có chính sách lợi nhuận (markup) đang áp dụng — không có thì
        mọi báo giá ném QTE-005. Ủy thác cho dl.demo.seed (đã đi qua luồng duyệt
        thật). An toàn khi kịch bản giá-theo-kho đã dựng trước (idempotent)."""
        self.env["dl.demo.seed"]._bao_dam_cau_hinh_gia()

    def build_operation_rules(self):
        """Seed đơn giá công đoạn ĐANG ÁP DỤNG cho từng công đoạn. BOM có công
        đoạn mà thiếu rule active tại ngày báo giá sẽ ném QTE-011."""
        Rule = self.env["dl.pricing.operation.rule"]
        for op_xmlid, method, rate, setup in _OPERATION_RATES:
            operation = self.ref(op_xmlid)
            if not operation:
                continue
            if Rule.search_count([("operation_id", "=", operation.id),
                                  ("state", "=", "active")]):
                continue
            rule = Rule.create({
                "operation_id": operation.id,
                "method": method,
                "price_rate": rate,
                "setup_fee": setup,
                # Hiệu lực lùi xa để phủ mọi ngày báo giá (kể cả báo giá lùi ngày).
                "valid_from": "2024-01-01",
                "change_reason": "Seed demo — đơn giá công đoạn khởi tạo.",
            })
            rule.action_apply()

    # ------------------------------------------------------------------
    # 1) Giá NCC
    # ------------------------------------------------------------------
    def build_supplier_prices(self):
        hoa_phat = self.ref("dl_demo.demo_supplier_hoa_phat")
        dai_bang = self.ref("dl_demo.demo_supplier_dai_bang")
        phu_thinh = self.ref("dl_demo.demo_supplier_phu_thinh")
        viet_nhat = self.ref("dl_demo.demo_supplier_viet_nhat")
        thang_long = self.ref("dl_demo.demo_supplier_thang_long")

        # Vật tư dùng trong BOM → phải "Đang áp dụng" để price_snapshot > 0
        # (giá vốn BOM, giá sàn báo giá). (product_xmlid, ncc, đơn giá).
        #
        # 🔴 ĐƠN GIÁ Ở ĐÂY LÀ ĐỒNG TRÊN ĐÚNG ĐVT MUA CỦA VẬT TƯ (đ/cây · đ/tấm ·
        # đ/cuộn · đ/kg · đ/túi · đ/cái), không phải đ/kg cho mọi thứ. Để nhầm
        # đ/kg cho vật tư bán theo cây là hỏng lặng: giá vốn hụt ~10 lần và tiền
        # phế liệu thu hồi (luôn quy về kg) có thể LỚN HƠN tiền vật tư ⇒ dòng BOM
        # ÂM. Quy đổi tham chiếu: thị trường ~18.500 đ/kg × khối lượng mỗi đơn vị.
        applied_materials = [
            # ---- Thép hộp (đ/cây 6m) ----
            ("dl_product.seed_mat_th_14", hoa_phat, 30_000),         # 1.35 kg/cây
            ("dl_product.seed_mat_th_20", hoa_phat, 52_000),         # 2.55
            ("dl_product.seed_mat_th_20x40", hoa_phat, 98_000),      # 4.9
            ("dl_product.seed_mat_th_25", hoa_phat, 82_000),         # 4.05
            ("dl_product.seed_mat_th_25x50", hoa_phat, 168_000),     # 8.5
            ("dl_product.seed_mat_th_30", hoa_phat, 115_000),        # 5.8
            ("dl_product.seed_mat_th_30x60", hoa_phat, 205_000),     # 10.16
            ("dl_product.seed_mat_th_40", hoa_phat, 215_000),        # 11.6
            ("dl_product.seed_mat_th_50", hoa_phat, 320_000),        # 16.2
            ("dl_product.seed_mat_th_100x50", hoa_phat, 600_000),    # 30.5
            ("dl_product.demo_product_ong_vuong", hoa_phat, 105_000),  # hộp 25×1.5
            # ---- Thép ống tròn (đ/cây 6m) — nguồn Việt Nhật ----
            ("dl_product.seed_mat_to_34", viet_nhat, 152_000),       # 7.7
            ("dl_product.seed_mat_to_49", viet_nhat, 248_000),       # 12.5
            ("dl_product.seed_mat_to_76", viet_nhat, 390_000),       # 19.7
            ("dl_product.seed_mat_to_90", viet_nhat, 575_000),       # 29.1
            ("dl_product.seed_mat_to_114", viet_nhat, 1_150_000),    # 58.0
            # ---- Thép tấm / tôn cuộn / lưới ----
            ("dl_product.seed_mat_tt_ct3_2", hoa_phat, 910_000),     # đ/tấm 49.06 kg
            ("dl_product.seed_mat_tt_ct3_5", hoa_phat, 6_290_000),   # đ/tấm 353.25 kg
            ("dl_product.seed_mat_tt_ss400_10", hoa_phat, 13_500_000),  # đ/tấm 706.5 kg
            ("dl_product.seed_mat_luoi_b40", thang_long, 850_000),   # đ/cuộn
            ("dl_product.demo_product_thep_cuon", hoa_phat, 7_260_000),  # đ/cuộn 392.5 kg
            # ---- Sơn ----
            ("dl_product.seed_mat_son_td", dai_bang, 85_000),        # đ/kg
            # seed_mat_son_lot: CỐ Ý chừa — vật tư DUY NHẤT chưa có giá NCC (test
            # màn "Chưa có giá NCC" phía vật tư).
            # ---- Vật tư tiêu hao & phụ kiện (nguồn kim khí Thăng Long) ----
            ("dl_product.seed_mat_quehan_25", thang_long, 45_000),   # đ/kg
            ("dl_product.seed_mat_dacat_180", thang_long, 12_000),   # đ/cái
            ("dl_product.seed_mat_banle", thang_long, 15_000),       # đ/cái
            ("dl_product.seed_mat_taynam", thang_long, 35_000),      # đ/cái
            ("dl_product.seed_mat_ocvit_m8", thang_long, 2_500),     # đ/cái
            ("dl_product.demo_product_oc_vit", phu_thinh, 1_500),    # đ/cái (M6)
            ("dl_product.seed_mat_vit_ca", thang_long, 60_000),      # đ/túi
            ("dl_product.seed_mat_dinh_rut", thang_long, 55_000),    # đ/túi
        ]
        for xmlid, supplier, price in applied_materials:
            self._price_row(self.ref(xmlid), supplier, price, state="applied")

        # Một vật tư có 2 nguồn giá đã duyệt (2 NCC) — 1 áp dụng, 1 chỉ duyệt:
        # test màn Bảng giá vật tư có nhiều dòng + trạng thái khác nhau.
        self._price_row(self.ref("dl_product.seed_mat_th_40"), viet_nhat,
                        228_000, state="approved")       # đ/cây, NCC thứ hai
        # Một dòng giá NHÁP chờ Kế toán duyệt (th_50 đã có giá áp dụng ở trên,
        # đây là bản chào mới của NCC khác đang chờ duyệt).
        self._price_row(self.ref("dl_product.seed_mat_th_50"), viet_nhat,
                        335_000, state="draft")          # đ/cây

        # SP thương mại: đang áp dụng (đủ điều kiện bán) / mới duyệt / chưa có.
        self._price_row(self.ref("dl_demo.demo_trading_ban_le"), phu_thinh,
                        30_000, state="applied")
        self._price_row(self.ref("dl_product.demo_product_gs100"), phu_thinh,
                        180_000, state="applied")
        self._price_row(self.ref("dl_demo.demo_trading_tay_nam"), phu_thinh,
                        42_000, state="approved")
        # demo_trading_ke_goc: cố ý KHÔNG có giá NCC (test phía SP thương mại).

    # ------------------------------------------------------------------
    # 2) BOM + bản vẽ
    # ------------------------------------------------------------------
    def _ops(self, *xmlids):
        """Danh sách công đoạn (recordset) từ xmlid, bỏ cái thiếu — truyền cho
        _make_bom(operations=...)."""
        return [op for op in (self.ref(x) for x in xmlids) if op]

    def _make_bom(self, product, lines, status="confirmed", bom_type="quotation",
                  operations=None):
        """Tạo 1 dl.bom + dòng vật tư (+ dòng công đoạn); đưa về trạng thái mong
        muốn qua action thật.

        lines: list dict giá trị dòng, bắt buộc có khoá "material" (recordset).
            Vật tư cắt đoạn/tấm nên nêu kích thước cắt (dim_length · piece_count)
            để định mức TỰ TÍNH ra đúng số cây/tấm — đó mới là dữ liệu demo thật;
            đưa thẳng "quantity" chỉ dùng cho vật tư đếm/định lượng.
        operations: list công đoạn (dl.pricing.operation) đưa vào giá thành. Đơn
            giá lấy từ rule active (build_operation_rules); method percent_material
            /per_unit nên không cần base_qty.
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
        op_vals = [
            (0, 0, {"operation_id": op.id, "sequence": (i + 1) * 10})
            for i, op in enumerate(operations or []) if op
        ]
        try:
            with self.env.cr.savepoint():
                bom = self.env["dl.bom"].create({
                    "product_id": product.id,
                    "bom_type": bom_type,
                    "product_qty": 1,
                    "line_ids": line_vals,
                    "operation_line_ids": op_vals,
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
        th50 = self.ref("dl_product.seed_mat_th_50")
        th30 = self.ref("dl_product.seed_mat_th_30")
        th30x60 = self.ref("dl_product.seed_mat_th_30x60")
        th25 = self.ref("dl_product.seed_mat_th_25")
        th20 = self.ref("dl_product.seed_mat_th_20")
        th100x50 = self.ref("dl_product.seed_mat_th_100x50")
        to34 = self.ref("dl_product.seed_mat_to_34")
        tt2 = self.ref("dl_product.seed_mat_tt_ct3_2")
        tt5 = self.ref("dl_product.seed_mat_tt_ct3_5")
        ong_vuong = self.ref("dl_product.demo_product_ong_vuong")
        oc_vit = self.ref("dl_product.demo_product_oc_vit")
        ocvit_m8 = self.ref("dl_product.seed_mat_ocvit_m8")
        thep_cuon = self.ref("dl_product.demo_product_thep_cuon")
        # 🔴 CHỈ dùng sơn tĩnh điện (đã có giá) trong BOM. Sơn lót cố ý chưa có
        # giá NCC nên đưa vào BOM là ném lỗi giá sàn khi báo giá.
        son_td = self.ref("dl_product.seed_mat_son_td")
        tam_sat = self.ref("dl_product.demo_product_tam_sat")  # BTP

        # Bộ công đoạn dùng lại: gia công thép điển hình = Cắt → Hàn → Mài → Sơn.
        ops_full = self._ops("dl_config.operation_cut", "dl_config.operation_weld",
                             "dl_config.operation_grind", "dl_config.operation_paint")

        # (a) BOM cho BTP "Tấm sắt phủ sơn 600×400×2mm" — cắt 1 miếng 600×400 từ
        #     cuộn tôn ⇒ định mức tự ra ~0.0096 cuộn (KHÔNG phải 2.5 cuộn!).
        #     Công đoạn: cắt + sơn (BTP chỉ cắt tấm rồi phủ sơn).
        self._make_bom(
            tam_sat,
            [
                {"material": thep_cuon, "dim_length": 600, "dim_width": 400,
                 "piece_count": 1},
                {"material": son_td, "quantity": 0.3},          # kg — nhập thẳng
            ],
            status="confirmed",
            operations=self._ops("dl_config.operation_cut", "dl_config.operation_paint"),
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
            operations=ops_full,
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
            operations=ops_full,
        )

        # (e) Cổng 2 cánh 3000×1800 — khung th40 + song đứng th25 + tấm trang trí.
        self._make_bom(
            self.ref("dl_demo.demo_product_cong_2canh"),
            [
                {"material": th40, "dim_length": 1800, "piece_count": 2},   # 2 trụ
                {"material": th40, "dim_length": 3000, "piece_count": 2},   # khung ngang
                {"material": th25, "dim_length": 1800, "piece_count": 20},  # song đứng
                {"material": tt2, "dim_length": 600, "dim_width": 400,
                 "piece_count": 2},                                          # tấm trang trí
                {"material": son_td, "quantity": 2.5},
                {"material": ocvit_m8, "quantity": 8},
            ],
            status="confirmed",
            operations=ops_full,
        )

        # (f) Hàng rào 2400×1500 — khung th40 + song th20.
        self._make_bom(
            self.ref("dl_demo.demo_product_hang_rao"),
            [
                {"material": th40, "dim_length": 1500, "piece_count": 2},
                {"material": th40, "dim_length": 2400, "piece_count": 2},
                {"material": th20, "dim_length": 1500, "piece_count": 16},
                {"material": son_td, "quantity": 1.8},
            ],
            status="confirmed",
            operations=ops_full,
        )

        # (g) Giá đỡ khuôn 800×600×1200 — chân chịu tải th50, mặt đỡ tấm 5mm.
        self._make_bom(
            self.ref("dl_demo.demo_product_gia_do"),
            [
                {"material": th50, "dim_length": 1200, "piece_count": 4},
                {"material": th40, "dim_length": 800, "piece_count": 4},
                {"material": th40, "dim_length": 600, "piece_count": 4},
                {"material": tt5, "dim_length": 800, "dim_width": 600,
                 "piece_count": 1},
                {"material": son_td, "quantity": 1.2},
                {"material": ocvit_m8, "quantity": 16},
            ],
            status="confirmed",
            operations=ops_full,
        )

        # (h) Cầu thang xương cá 3200×900 — dầm th100x50, bậc tấm 5mm.
        self._make_bom(
            self.ref("dl_demo.demo_product_cau_thang"),
            [
                {"material": th100x50, "dim_length": 3200, "piece_count": 2},
                {"material": th40, "dim_length": 900, "piece_count": 12},   # đỡ bậc
                {"material": tt5, "dim_length": 900, "dim_width": 250,
                 "piece_count": 12},                                         # 12 bậc
                {"material": son_td, "quantity": 2.0},
            ],
            status="confirmed",
            operations=ops_full,
        )

        # (i) Lan can ban công Ø34 — tay vịn + trụ + thanh ngang thép ống.
        self._make_bom(
            self.ref("dl_demo.demo_product_lan_can"),
            [
                {"material": to34, "dim_length": 3000, "piece_count": 1},   # tay vịn
                {"material": to34, "dim_length": 900, "piece_count": 6},    # trụ đứng
                {"material": to34, "dim_length": 2800, "piece_count": 2},   # thanh ngang
                {"material": son_td, "quantity": 1.0},
            ],
            status="confirmed",
            operations=ops_full,
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
    # 2b) Tồn kho vật tư — cho màn tồn trông thực tế
    # ------------------------------------------------------------------
    # (xmlid vật tư, min, max) — biên số lượng tồn theo ĐVT MUA của vật tư. Tổng
    # điểm giữa ~150–190 đơn vị, đúng khoảng "100–200 cái" mong muốn.
    _STOCK_PLAN = [
        ("dl_product.seed_mat_th_14", 6, 15),
        ("dl_product.seed_mat_th_20", 8, 18),
        ("dl_product.seed_mat_th_25", 10, 20),
        ("dl_product.seed_mat_th_30", 6, 14),
        ("dl_product.seed_mat_th_30x60", 5, 12),
        ("dl_product.seed_mat_th_40", 12, 25),
        ("dl_product.seed_mat_th_50", 4, 10),
        ("dl_product.demo_product_ong_vuong", 8, 16),
        ("dl_product.seed_mat_to_34", 5, 12),
        ("dl_product.seed_mat_to_49", 3, 8),
        ("dl_product.seed_mat_tt_ct3_2", 3, 8),          # tấm
        ("dl_product.seed_mat_tt_ct3_5", 1, 4),          # tấm
        ("dl_product.demo_product_thep_cuon", 1, 3),     # cuộn
        ("dl_product.seed_mat_ocvit_m8", 20, 45),        # cái
        ("dl_product.seed_mat_dacat_180", 10, 25),       # cái
    ]

    def build_stock(self):
        """Đặt tồn đầu kỳ ngẫu-nhiên-tất-định cho vật tư ở Kho nguyên vật liệu.
        random.Random seed cố định ⇒ mỗi lần seed ra số giống hệt (deploy tái
        tạo y hệt). Idempotent: vật tư đã có tồn thì bỏ qua."""
        Location = self.env["stock.location"].sudo()
        try:
            loc = Location._dlm_location("dl_inventory.stock_location_nhan_kho")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("dl_demo: thiếu Kho nguyên vật liệu — bỏ seed tồn: %s", exc)
            return
        rng = random.Random(20260822)
        Quant = self.env["stock.quant"].with_context(inventory_mode=True).sudo()
        Lot = self.env["stock.lot"].sudo()
        StockQuant = self.env["stock.quant"].sudo()
        company = self.env.company
        for xmlid, lo, hi in self._STOCK_PLAN:
            product = self.ref(xmlid)
            qty = rng.randint(lo, hi)      # rút số TRƯỚC khi bỏ qua để chuỗi RNG cố định
            if not product:
                continue
            if StockQuant.search_count([
                    ("location_id", "child_of", loc.id),
                    ("product_id", "=", product.id)]):
                continue
            vals = {
                "product_id": product.id,
                "location_id": loc.id,
                "inventory_quantity": qty,
            }
            if product.tracking == "lot":
                lot = Lot.create({
                    "name": "TON-DK-%s" % (product.default_code or product.id),
                    "product_id": product.id,
                    "company_id": company.id,
                })
                vals["lot_id"] = lot.id
            try:
                with self.env.cr.savepoint():
                    Quant.create(vals).action_apply_inventory()
            except Exception as exc:  # noqa: BLE001
                _logger.warning("dl_demo: seed tồn %s LỖI: %s",
                                product.display_name, exc)

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
            # Bắt buộc từ 2026-08-19: dòng gia công phải có Nhóm sản phẩm (nhóm
            # quyết định hệ thống hỏi thông số gì / KTV dùng mẫu nào). Suy thẳng
            # từ nhóm của SP đã xác định.
            "product_category_id": product.categ_id.id if product else False,
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
        truong_le_loi = self.ref("dl_demo.demo_customer_truong_le_loi")
        noithat_an_phat = self.ref("dl_demo.demo_customer_noithat_an_phat")

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

        # ---- Vài ĐƠN THƯƠNG MẠI đã lên đơn cho khách mới (đơn bán hàng thật) ----
        # Dưới ngưỡng 20tr → không vướng phê duyệt, cho ra đơn bán gọn.
        self._scenario(truong_le_loi, [L(ban_le, 300)], "ordered")    # 13,5tr
        self._scenario(noithat_an_phat, [L(ban_le, 400)], "ordered")  # 18tr

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
