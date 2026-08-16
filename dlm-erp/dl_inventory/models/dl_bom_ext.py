# -*- coding: utf-8 -*-
"""Nổ BOM thành nhu cầu vật tư (bù trừ BTP tồn kho) cho màn Điều phối."""

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

# Chặn đệ quy BOM vô hạn (lá chắn lúc tạo không cứu được BOM lỗi có sẵn trong DB).
_MAX_DEPTH = 5


class DlBomExplosion(models.Model):
    _inherit = "dl.bom"

    # ------------------------------------------------------------------
    # API công khai
    # ------------------------------------------------------------------
    def _dlm_explode_requirements(self, qty, location=None):
        """{product: số cần} để làm `qty` đơn vị SP của BOM này; location=None ⇒ nổ thô, không bù trừ BTP."""
        return self._dlm_explode_report(qty, location=location)["requirements"]

    def _dlm_explode_report(self, qty, location=None):
        """Bản đầy đủ: nhu cầu vật tư + BTP dùng lại + cảnh báo (BTP thiếu BOM, phế liệu lọt định mức)."""
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
        """Đệ quy: cộng nhu cầu của BOM này vào `report`, bù trừ BTP tồn theo tầng (`_taken` = sổ BTP đã dùng)."""
        self.ensure_one()
        chain_label = " → ".join(
            "%s (%s)" % (bom.display_name, bom.product_id.display_name)
            for bom in (_chain + [self]))
        if self in _chain:
            # BOM quay lại chính nó — chặn ngay tầng lặp đầu tiên.
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

        # Chia số lượng đầu ra: BOM có thể khai nguyên liệu cho nhiều đơn vị.
        factor = qty / (self.product_qty or 1.0)
        chain = _chain + [self]

        for line in self.line_ids:
            material = line.material_id
            if material.dlm_is_scrap:
                # Phế liệu không phải đầu vào — ghi nhận cảnh báo rồi đi tiếp.
                report["scrap"] |= material
                continue

            # effective_qty đã gồm hao hụt — không nhân hao hụt lần nữa.
            need = line.effective_qty * factor
            if need <= 0:
                continue

            if material.product_kind != "material_processed":
                _accumulate(report["requirements"], material, need)
                continue

            # Bán thành phẩm: có sẵn thì dùng lại, thiếu bao nhiêu mới nổ tiếp.
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
                # BTP thiếu BOM con: ghi thẳng thành nhu cầu + gắn cờ cảnh báo.
                _accumulate(report["requirements"], material, shortage)
                report["btp_no_bom"] |= material
                continue
            child_bom._dlm_explode_into(
                shortage, location, report, _taken=_taken, _chain=chain)

    # ------------------------------------------------------------------
    # Trợ giúp
    # ------------------------------------------------------------------
    def _dlm_btp_available(self, btp, location, _taken):
        """Số BTP còn lấy được, đã trừ phần các dòng trước của lần nổ này giữ."""
        if not location:
            return 0.0
        on_hand = self.env["stock.quant"]._dlm_available_qty(btp, location)
        return max(0.0, on_hand - _taken.get(btp.id, 0.0))


def _accumulate(bucket, product, qty):
    """Cộng dồn vào dict, làm tròn theo ĐVT mặt hàng (số đi thẳng vào phiếu kho)."""
    rounding = product.uom_id.rounding or 0.01
    bucket[product] = float_round(
        bucket.get(product, 0.0) + qty, precision_rounding=rounding)
