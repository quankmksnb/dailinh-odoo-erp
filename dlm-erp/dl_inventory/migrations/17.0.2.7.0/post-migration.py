import logging
from collections import OrderedDict

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# RS-01 (docs/Ra_soat_phan_he_kho_2026-08-12.md) — vá dữ liệu sinh trước bản fix.
#
# Phiếu kiểm sinh trước bản này có thể đang GỘP hàng của nhiều phiếu nhận (nhiều
# NCC) vào một phiếu, do dòng kiểm không có nhóm cung ứng nên `_assign_picking`
# nhồi chung. Để nguyên thì: ô Nhà cung cấp trống, không truy được lô nào theo
# lần giao nào, và phiếu trả hàng sinh ra từ đó ghi SAI NCC.
#
# CHỈ tách phiếu CHƯA hoàn tất. Phiếu đã `done` đã ghi tồn kho và lô — tách ra
# là viết lại lịch sử kho, còn hại hơn cái sai nó đang mang.


def _receipt_of(move):
    """Phiếu NHẬN đứng trước dòng kiểm (rỗng nếu không truy được)."""
    return move.move_orig_ids.picking_id.filtered(
        lambda p: p.picking_type_id.code == "incoming")[:1]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Picking = env["stock.picking"]
    Group = env["procurement.group"]

    qc_pickings = Picking.search([
        ("picking_type_id.sequence_code", "=", "KC"),
        ("state", "not in", ("done", "cancel")),
    ])
    tach = 0
    for qc in qc_pickings:
        # OrderedDict để phiếu nhận ĐẦU TIÊN giữ nguyên số phiếu kiểm cũ —
        # thủ kho đang cầm giấy in số đó.
        theo_phieu = OrderedDict()
        for move in qc.move_ids:
            receipt = _receipt_of(move)
            theo_phieu[receipt] = theo_phieu.get(receipt, env["stock.move"]) | move
        if len(theo_phieu) < 2:
            continue

        def dong_nhom(receipt, moves):
            """Trả nhóm cung ứng của lần nhận này, tạo mới nếu chưa có."""
            group = moves.group_id[:1] or receipt.move_ids.group_id[:1]
            if not group and receipt:
                group = Group.create({
                    "name": receipt.name,
                    "partner_id": receipt.partner_id.id,
                })
            moves.write({"group_id": group.id})
            return group

        for receipt, moves in list(theo_phieu.items())[1:]:
            dong_nhom(receipt, moves)
            moi = Picking.create({
                "picking_type_id": qc.picking_type_id.id,
                "location_id": qc.location_id.id,
                "location_dest_id": qc.location_dest_id.id,
                "partner_id": receipt.partner_id.id,
                "origin": receipt.name or qc.origin,
                "scheduled_date": qc.scheduled_date,
            })
            moves.write({"picking_id": moi.id})
            moves.move_line_ids.write({"picking_id": moi.id})
            tach += 1
            _logger.info(
                "RS-01: tách %s khỏi %s (phiếu nhận %s)",
                moi.name, qc.name, receipt.name or "?")

        # Phiếu cũ giờ chỉ còn một nguồn — trả lại NCC và số phiếu gốc đã bị
        # `_assign_picking` xoá trắng lúc gộp.
        receipt_con_lai, moves_con_lai = list(theo_phieu.items())[0]
        if receipt_con_lai:
            dong_nhom(receipt_con_lai, moves_con_lai)
            qc.write({
                "partner_id": receipt_con_lai.partner_id.id,
                "origin": receipt_con_lai.name,
            })

    if tach:
        _logger.info("RS-01: đã tách %s phiếu kiểm bị gộp nhiều NCC.", tach)
