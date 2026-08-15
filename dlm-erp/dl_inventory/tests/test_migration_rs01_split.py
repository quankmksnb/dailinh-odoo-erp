# -*- coding: utf-8 -*-
"""L2 (TransactionCase, PostgreSQL thật) cho migration RS-01
(migrations/17.0.2.7.0/post-migration.py): vá dữ liệu phiếu kiểm sinh trước
bản fix, khi hàng của nhiều phiếu nhận (nhiều NCC) bị gộp vào một phiếu.

Migration script không nằm trong package `models`/`tests` bình thường (tên
thư mục "17.0.2.7.0" và tên file "post-migration.py" không phải identifier
Python hợp lệ). Odoo tự nạp bằng importlib theo đường dẫn file khi upgrade,
không qua `import` thường. Test này nạp lại đúng cách đó rồi gọi thẳng
`migrate(cr, version)`.

Trước bản fix (RS-01 trong stock_move.py::_action_confirm/_key_assign_picking),
QC move không có group_id khi push sinh dòng kiểm, nên `_assign_picking` gộp
nhầm nhiều NCC vào một phiếu kiểm. Test này dựng lại đúng trạng thái hỏng đó
bằng cách ghi tay move_ids.picking_id (bỏ qua toàn bộ logic RS-01 hiện tại) để
mô phỏng dữ liệu cũ, chứ không phải test hành vi tạo phiếu bình thường (đã có
ở test_qc_receipt.py::test_hai_ncc_ra_hai_phieu_kiem_rieng)."""
import importlib.util
import os

from .common import DlInventoryCase

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "17.0.2.7.0",
    "post-migration.py")


def _load_migrate():
    spec = importlib.util.spec_from_file_location(
        "dl_inventory_post_migration_17_0_2_7_0", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate


class TestMigrationRs01Split(DlInventoryCase):

    def setUp(self):
        super().setUp()
        self.vendor_b = self.env["res.partner"].create({"name": "NCC Tôn (test)"})

    def _broken_merged_qc(self):
        """2 phiếu nhận từ 2 NCC khác nhau, mỗi phiếu tự sinh phiếu kiểm riêng
        (đúng RS-01 hiện tại), sau đó cố ý gộp thủ công move của phiếu kiểm B
        vào phiếu kiểm A để mô phỏng đúng dữ liệu hỏng migration cần vá."""
        receipt_a = self._make_receipt(qty=50.0)
        self._receive(receipt_a, qty=50.0)
        receipt_b = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": self.vendor_b.id,
            "location_id": self.loc_vendors.id,
            "location_dest_id": self.loc_qc.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": 30.0,
                "product_uom": self.material.uom_id.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
            })],
        })
        receipt_b.action_confirm()
        receipt_b.action_assign()
        self._receive(receipt_b, qty=30.0)

        # _receive() (button_validate) đã tự sinh lô cho từng move (K3
        # _dlm_autofill_lot_names), cần để phiếu kiểm sau đó validate được
        # (QC-03/RS-11 chặn nếu thiếu số lô).
        qc_a = self._qc_picking(receipt_a)
        qc_b = self._qc_picking(receipt_b)
        self.assertTrue(qc_a and qc_b and qc_a != qc_b,
                         "Tiền điều kiện sai: 2 phiếu nhận phải tự sinh 2 "
                         "phiếu kiểm RIÊNG (đúng RS-01 hiện tại) trước khi "
                         "test tự gộp lại để mô phỏng dữ liệu cũ.")

        # Ghi tay: dồn move + move_line của qc_b sang qc_a, mô phỏng đúng bug
        # gộp NCC trước bản fix. qc_b coi như rỗng sau bước này.
        qc_b.move_ids.write({"picking_id": qc_a.id})
        qc_b.move_ids.move_line_ids.write({"picking_id": qc_a.id})
        qc_a.invalidate_recordset()
        return receipt_a, receipt_b, qc_a, qc_b

    def test_phieu_kiem_gop_hai_ncc_duoc_tach_lai_dung(self):
        """TC-INT-TestMigrationRs01Split-001: migrate() tách phiếu kiểm gộp
        2 NCC thành 2 phiếu riêng, phiếu gốc trả lại đúng NCC và số phiếu của
        phiếu nhận đầu tiên."""
        receipt_a, receipt_b, qc_a, qc_b = self._broken_merged_qc()
        self.assertEqual(len(qc_a.move_ids), 2,
                          "Tiền điều kiện: qc_a phải đang gộp cả 2 move (mô "
                          "phỏng bug).")
        qc_a_name_before = qc_a.name

        migrate = _load_migrate()
        migrate(self.env.cr, "17.0.2.7.0")
        self.env.flush_all()
        qc_a.invalidate_recordset()

        # qc_a chỉ còn giữ move của phiếu nhận đầu tiên (receipt_a), số phiếu
        # không đổi (thủ kho đang cầm giấy in số đó).
        self.assertEqual(qc_a.name, qc_a_name_before)
        self.assertEqual(len(qc_a.move_ids), 1)
        self.assertEqual(qc_a.move_ids.product_uom_qty, 50.0)
        self.assertEqual(qc_a.partner_id, self.vendor)

        # Tìm phiếu kiểm mới được tách ra cho receipt_b.
        moi = self.env["stock.picking"].search([
            ("picking_type_id", "=", qc_a.picking_type_id.id),
            ("id", "!=", qc_a.id),
            ("id", "!=", qc_b.id),
            ("origin", "=", receipt_b.name),
        ])
        self.assertEqual(len(moi), 1,
                          "Phải tách ra ĐÚNG 1 phiếu kiểm mới cho receipt_b.")
        self.assertEqual(moi.partner_id, self.vendor_b)
        self.assertEqual(moi.move_ids.product_uom_qty, 30.0)

    def test_phieu_kiem_da_done_khong_bi_dong_vao(self):
        """TC-INT-TestMigrationRs01Split-002: phiếu kiểm đã `done` không bị
        tách dù đang gộp nhiều NCC. Viết lại lịch sử kho đã ghi nhận còn hại
        hơn cái sai đang mang (theo đúng comment trong migration script)."""
        receipt_a, receipt_b, qc_a, qc_b = self._broken_merged_qc()
        qc_a.action_dlm_pass_all()
        qc_a.action_dlm_validate_qc()
        self.assertEqual(qc_a.state, "done")
        move_count_before = len(qc_a.move_ids)

        migrate = _load_migrate()
        migrate(self.env.cr, "17.0.2.7.0")
        self.env.flush_all()
        qc_a.invalidate_recordset()

        self.assertEqual(len(qc_a.move_ids), move_count_before,
                          "Phiếu đã done không được tách — lịch sử kho giữ "
                          "nguyên.")

    def test_phieu_kiem_mot_ncc_khong_bi_dong_toi(self):
        """TC-INT-TestMigrationRs01Split-003: phiếu kiểm chỉ có 1 NCC (đúng
        RS-01 hiện tại, không phải dữ liệu hỏng) không bị migration đụng
        tới."""
        receipt = self._make_receipt(qty=20.0)
        qc = self._qc_picking(receipt)
        name_before = qc.name
        partner_before = qc.partner_id

        migrate = _load_migrate()
        migrate(self.env.cr, "17.0.2.7.0")
        self.env.flush_all()
        qc.invalidate_recordset()

        self.assertEqual(qc.name, name_before)
        self.assertEqual(qc.partner_id, partner_before)
        self.assertEqual(len(qc.move_ids), 1)
