# -*- coding: utf-8 -*-
"""K15 — Nổ BOM thành nhu cầu vật tư.

Thiết kế: ``docs/Thiet_ke_luong_sau_don_hang_check_kho_dieu_phoi.md`` §5 và
``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §3.

Đây là cái phễu giữa "10 bộ bàn ghế" (ngôn ngữ của khách) và "25 cây thép hộp"
(ngôn ngữ của kho). Trước bản này, BOM chỉ được dùng để tính TIỀN
(``total_material_cost``, ``price_snapshot``) — chưa ai từng hỏi nó SỐ LƯỢNG,
nên hệ thống báo giá món hàng mà không biết có đủ vật tư để làm không.

🔴 **Vì sao file này ở `dl_inventory` chứ không phải `dl_technical`** như doc
B1.5 §5.1 ghi: ``dl_technical`` KHÔNG phụ thuộc ``stock`` (xem `__manifest__`),
mà bù trừ BTP theo tầng thì bắt buộc phải đọc ``stock.quant``. Đặt ở đây là chỗ
duy nhất nhìn thấy cả hai. Phần toán thuần của BOM vẫn nằm nguyên bên
``dl_technical`` — file này chỉ thêm một hành vi.

🔴 **Hai điểm doc ghi thiếu, phát hiện khi đối chiếu code:**

1. **Phải chia ``bom.product_qty``.** Công thức doc ghi ``can = effective_qty ×
   qty`` chỉ đúng khi BOM khai đầu ra = 1. ``product_qty`` là "Số lượng đầu ra"
   (``dl_bom_header_mixin.py:22``) — một BOM có thể mô tả nguyên liệu cho 6 ghế,
   và khi đó ``effective_qty`` của từng dòng là số cho CẢ 6. Engine giá đã chia
   đúng (``quotation_pricing_service.py:627``); thiếu phép chia ở đây là đòi gấp
   6 lần, và sai theo hướng MUA THỪA — tiền đã chi rồi mới có người phát hiện.
2. **Phải nhớ phần BTP đã trưng dụng giữa các dòng.** Doc §5.2 bẫy 6 nói "thứ tự
   chỉ đổi phân bổ, không đổi tổng nhu cầu" — điều đó chỉ đúng NẾU có sổ theo
   dõi. Không có thì hai dòng cùng ăn một BTP đều thấy "kho còn 8", cùng trừ 8,
   và tổng nhu cầu vật tư thô bị tính THIẾU. Sổ đó là ``_taken`` bên dưới.
"""

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

# Độ sâu tối đa khi đệ quy BOM. Lá chắn `_dlm_check_no_cycle` (dl_bom_line.py)
# chặn lúc TẠO, nhưng nó không cứu được BOM đã lỡ có trong DB trước khi lá chắn
# ra đời — mà một vòng lặp ở đây là treo cả tiến trình server.
_MAX_DEPTH = 5


class DlBomExplosion(models.Model):
    _inherit = "dl.bom"

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------
    def _dlm_explode_requirements(self, qty, location=None):
        """{product.product: số cần} để làm ``qty`` đơn vị sản phẩm của BOM này.

        ``location`` — khu để hỏi "BTP có sẵn không". Truyền None ⇒ KHÔNG bù trừ,
        nổ thẳng xuống đáy (dùng khi chỉ muốn biết định mức thô).

        Kết quả là **dict cộng dồn**, không phải list: cùng một cây thép nằm ở 3
        dòng và 2 tầng thì phải ra MỘT mục. Trả list là mỗi dòng tự thấy đủ mà
        tổng thì thiếu.
        """
        return self._dlm_explode_report(qty, location=location)["requirements"]

    def _dlm_explode_report(self, qty, location=None):
        """Bản đầy đủ: nhu cầu + những chỗ định mức không trả lời được.

        Trả về dict:
          ``requirements``  {product: số cần} — thứ phải có mặt ở kho
          ``btp_used``      {BTP: số dùng lại từ tồn} — để màn nói "dùng 4 khung có sẵn"
          ``btp_no_bom``    recordset BTP thiếu BOM con ⇒ nhánh vật tư MẤT HẲN (DP-04)
          ``scrap``         recordset vật tư gắn cờ phế liệu lọt vào định mức (DP-09)

        🔴 Ba cảnh báo trả về chứ KHÔNG raise tại đây: màn Điều phối phải HIỆN
        ra được vấn đề thì người dùng mới sửa. Chặn cứng nằm ở
        ``action_dlm_dispatch`` — đúng quy ước "validate inline, không modal".
        """
        self.ensure_one()
        report = {
            "requirements": {},
            "btp_used": {},
            "btp_no_bom": self.env["product.product"].browse(),
            "scrap": self.env["product.product"].browse(),
        }
        if qty <= 0:
            return report
        self._dlm_explode_into(qty, location, report, _taken={}, _chain=[])
        return report

    # ------------------------------------------------------------------
    # Đệ quy
    # ------------------------------------------------------------------
    def _dlm_explode_into(self, qty, location, report, _taken, _chain):
        """Cộng nhu cầu của BOM này vào ``report`` (đệ quy theo tầng BTP).

        ``_taken`` — sổ BTP đã trưng dụng trong CHÍNH lần nổ này, dùng chung cho
        mọi nhánh đệ quy. Xem điểm 2 ở đầu file.
        ``_chain`` — chuỗi BOM đang mở, để câu lỗi nói được VÒNG LẶP Ở ĐÂU thay
        vì chỉ báo "quá sâu".
        """
        self.ensure_one()
        # Chuỗi nêu CẢ tên sản phẩm: mã BOM ("BOM-0118") không nói cho ai biết
        # phải đi sửa cái gì, mà đây là câu lỗi duy nhất người dùng nhìn thấy.
        chain_label = " → ".join(
            "%s (%s)" % (bom.display_name, bom.product_id.display_name)
            for bom in (_chain + [self]))
        if self in _chain:
            # Vòng lặp THẬT — bắt được ngay tầng đầu tiên lặp lại, không phải
            # chờ đủ 5 tầng. Câu lỗi nêu chuỗi vì "BOM nào" mới là thứ sửa được.
            raise UserError(_(
                "Định mức của \"%(product)s\" quay lại chính nó — không tính "
                "được nhu cầu vật tư.\n\nChuỗi định mức: %(chain)s"
            ) % {"product": self.product_id.display_name,
                 "chain": chain_label})
        if len(_chain) >= _MAX_DEPTH:
            raise UserError(_(
                "Định mức lồng nhau quá %(max)s tầng.\n\nChuỗi định mức: "
                "%(chain)s"
            ) % {"max": _MAX_DEPTH, "chain": chain_label})

        # 🔴 Chia số lượng đầu ra. Xem điểm 1 ở đầu file.
        factor = qty / (self.product_qty or 1.0)
        chain = _chain + [self]

        for line in self.line_ids:
            # ⚠️ Doc §5.2 bẫy 4 ("dòng mô tả không có material_id ⇒ bỏ qua") KHÔNG
            # áp dụng được: `material_id` là `required=True` + NOT NULL ở DB
            # (dl_bom_line_mixin.py:38). Không có dòng BOM nào không có vật tư,
            # nên nhánh bỏ qua đó là code chết — đã gỡ.
            material = line.material_id
            if material.dlm_is_scrap:
                # DP-09 — phế liệu không phải nguyên liệu đầu vào. Ghi nhận rồi
                # đi tiếp: chặn nằm ở tầng action, không phải ở đây.
                report["scrap"] |= material
                continue

            # `effective_qty` ĐÃ gồm hao hụt (`_compute_effective_qty` =
            # quantity × (1 + waste_rate/100)). Nhân thêm hệ số hao hụt lần nữa
            # là tính hao hụt hai lần, và giá thành đã dùng đúng con số này.
            need = line.effective_qty * factor
            if need <= 0:
                continue

            if material.product_kind != "material_processed":
                _accumulate(report["requirements"], material, need)
                continue

            # ── Bán thành phẩm: bù trừ theo tầng ────────────────────────────
            # Có sẵn cụm hàn thì lấy dùng, không ai tháo ra làm lại từ thép.
            available = self._dlm_btp_available(material, location, _taken)
            rounding = material.uom_id.rounding or 0.01
            use = min(need, available)
            if float_compare(use, 0.0, precision_rounding=rounding) > 0:
                _accumulate(report["requirements"], material, use)
                _accumulate(report["btp_used"], material, use)
                _taken[material.id] = _taken.get(material.id, 0.0) + use

            shortage = need - use
            if float_compare(shortage, 0.0, precision_rounding=rounding) <= 0:
                continue

            child_bom = self._standard_child_bom(material)
            if not child_bom:
                # DP-04 — không có định mức con thì nhánh vật tư của BTP này MẤT
                # HẲN khỏi nhu cầu: mua thiếu, xưởng đứng. Ghi BTP thành nhu cầu
                # để ít nhất người dùng thấy nó, kèm cờ.
                _accumulate(report["requirements"], material, shortage)
                report["btp_no_bom"] |= material
                continue
            child_bom._dlm_explode_into(
                shortage, location, report, _taken=_taken, _chain=chain)

    # ------------------------------------------------------------------
    # Trợ giúp
    # ------------------------------------------------------------------
    def _dlm_btp_available(self, btp, location, _taken):
        """Số BTP còn lấy được, đã trừ phần các dòng TRƯỚC của lần nổ này giữ.

        Dùng ``stock.quant._dlm_available_qty`` — đúng hàm ``action_assign`` gọi
        khi giữ chỗ (K14), nên số màn báo và số phiếu giữ được không lệch nhau.
        """
        if not location:
            return 0.0
        on_hand = self.env["stock.quant"]._dlm_available_qty(btp, location)
        return max(0.0, on_hand - _taken.get(btp.id, 0.0))


def _accumulate(bucket, product, qty):
    """Cộng dồn vào dict, làm tròn theo ĐVT của chính mặt hàng.

    Làm tròn ở đây (không phải lúc hiển thị) vì con số này đi thẳng vào
    ``product_uom_qty`` của phiếu kho: 2,9999999 cây thép là một dòng phiếu mà
    thủ kho không bao giờ tick xong được.
    """
    rounding = product.uom_id.rounding or 0.01
    bucket[product] = float_round(
        bucket.get(product, 0.0) + qty, precision_rounding=rounding)
