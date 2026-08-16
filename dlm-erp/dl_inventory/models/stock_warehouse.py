# -*- coding: utf-8 -*-
"""Cấu trúc kho Đại Linh: MỘT kho `DL`, bốn khu con; seed toàn bộ bố cục ở `_dlm_setup_inventory_layout`."""

from odoo import _, api, fields, models

# Vị trí tự tạo thêm (hậu tố xml_id, tên, usage, khoá cha). Đều 'internal' để
# giữ tiền tố "DL/". THỨ TỰ = thứ tự tạo: khu cha phải đứng TRƯỚC con.
_DLM_NEW_LOCATIONS = [
    ("nhan", "Khu nhập hàng", "internal", "wh_view"),
    ("nhan_tra", "Chờ trả nhà cung cấp", "internal", "nhan"),
    ("khosx", "Kho nhà máy sản xuất", "internal", "wh_view"),
    ("xuong_pl", "Phế liệu chờ bán", "internal", "khosx"),
    # Ô LÁ, không còn con. Đổi tên bản ghi cũ là việc của migration — vòng lặp không ghi đè `name`.
    ("xuong", "Xưởng sản xuất", "internal", "wh_view"),
    ("tp", "Kho thành phẩm", "internal", "wh_view"),
]

# Loại hoạt động tự tạo (3 loại native chỉ đổi tên). Số phiếu = <mã kho>/<mã loại>/<số>.
# ĐỪNG tự đặt prefix: stock.picking.type.write() ghi đè prefix về công thức này mỗi lần ghi.
_DLM_NEW_PICKING_TYPES = [
    ("picking_type_qc", "Kiểm & cất hàng", "internal", "KC",
     "nhan_qc", "nhan_kho", 12),
    ("picking_type_vendor_return", "Trả hàng nhà cung cấp", "outgoing", "TR",
     "nhan_tra", "suppliers", 14),
    ("picking_type_scrap_sale", "Bán phế liệu", "outgoing", "BPL",
     "xuong_pl", "customers", 60),
    # Hoá phế liệu: mặt hàng vào ≠ ra; vị trí mặc định chỉ đúng dòng VÀO, dòng ra
    # do action dựng. Mã HPL (BPL đã là Bán phế liệu — tránh đọc nhầm).
    ("picking_type_to_scrap", "Chuyển thành phế liệu", "internal", "HPL",
     "inventory_adj", "xuong_pl", 62),
    # Hai loại dưới dành cho Lệnh sản xuất (B2), seed sẵn. `xuong` nay là ô LÁ ⇒
    # chỉ tiêu thụ được thứ ĐÃ bàn giao ra sàn (siết có chủ ý).
    ("picking_type_mo_issue", "Xuất vật tư sản xuất", "internal", "XSX",
     "xuong", "production", 30),
    # Nhập kho từ xưởng = chứng từ TRỌN MẺ; vị trí đầu phiếu chỉ là mặc định,
    # mỗi dòng tự mang vị trí theo vai trò (stock_move._dlm_workshop_route).
    ("picking_type_mo_receipt", "Nhập kho từ xưởng", "internal", "NTP",
     "production", "tp", 32),
]

# Ba loại hoạt động Odoo tạo sẵn — chỉ Việt hoá tên + gắn mã seq.
# (tên field trên warehouse, tên hiển thị, mã seq)
_DLM_NATIVE_PICKING_TYPES = [
    ("in_type_id", "Nhận hàng nhà cung cấp", "NH"),
    ("out_type_id", "Giao hàng khách", "GH"),
    ("int_type_id", "Chuyển kho nội bộ", "CK"),
]


_DLM_NATIVE_LOCATIONS = [
    ("stock.stock_location_locations", "Physical Locations", "Vị trí thực tế"),
    ("stock.stock_location_locations_partner", "Partners", "Đối tác"),
    ("stock.stock_location_locations_virtual", "Virtual Locations", "Vị trí ảo"),
    ("stock.stock_location_suppliers", "Vendors", "Nhà cung cấp"),
    ("stock.stock_location_customers", "Customers", "Khách hàng"),
    ("stock.stock_location_inter_wh", "Inter-company transit",
     "Trung chuyển liên công ty"),
]

# Ba vị trí ảo Odoo tạo theo công ty, KHÔNG có XML ID ⇒ tra bằng usage (+ scrap_location).
# (usage, scrap_location, tên gốc, tên Việt)
_DLM_NATIVE_VIRTUAL_LOCATIONS = [
    ("production", False, "Production", "Sản xuất"),
    ("inventory", False, "Inventory adjustment", "Điều chỉnh tồn kho"),
    # Cố ý không đặt là "Phế liệu": đã có ô thật "Phế liệu chờ bán"; đây là nơi hàng bị xoá sổ.
    ("inventory", True, "Scrap", "Hàng huỷ bỏ"),
]


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    # ── Bước 2 của luồng nhận hàng dùng loại hoạt động riêng ─────────────────
    def get_rules_dict(self):
        """Nhận hàng 2 bước: chặng Chờ kiểm → đã nhận dùng loại "Kiểm & cất hàng" thay "Chuyển kho nội bộ"."""
        result = super().get_rules_dict()
        qc_type = self.env.ref(
            "dl_inventory.picking_type_qc", raise_if_not_found=False)
        if not qc_type:
            # Lần cài đầu, loại hoạt động chưa seed ⇒ giữ mặc định Odoo.
            return result
        for warehouse in self:
            routings = result.get(warehouse.id, {}).get("two_steps") or []
            if len(routings) > 1:
                old = routings[1]
                routings[1] = self.Routing(
                    old.from_loc, old.dest_loc, qc_type, old.action)
        return result

    # ── Seed — gọi từ data/stock_inventory_layout.xml ────────────────────────
    # @api.model bắt buộc: <function> không truyền ids.
    @api.model
    def _dlm_setup_inventory_layout(self):
        """Dựng toàn bộ bố cục kho; idempotent (chạy lại -u không nhân bản)."""
        warehouse = self._dlm_main_warehouse()
        if not warehouse:
            return False
        locations = warehouse._dlm_setup_locations()
        self.env["stock.location"]._dlm_setup_native_location_names()
        warehouse._dlm_setup_picking_types(locations)
        warehouse._dlm_setup_reception_route(locations)
        warehouse._dlm_setup_lot_sequence()
        return True

    def _dlm_setup_lot_sequence(self):
        """Số lô do Đại Linh tự sinh (LO/2026/00001); ghi bằng Python vì bản ghi gốc mang noupdate=True."""
        sequence = self.env.ref(
            "stock.sequence_production_lots", raise_if_not_found=False)
        if sequence and sequence.prefix != "LO/%(year)s/":
            sequence.sudo().write({
                "name": "Số lô Đại Linh",
                "prefix": "LO/%(year)s/",
                "padding": 5,
            })
        return True

    def _dlm_setup_locations(self):
        """Đổi tên/mã kho và dựng cây vị trí 3 khu. Trả về dict khoá → vị trí."""
        self.ensure_one()
        # THỨ TỰ: write 'code' làm Odoo đổi tên vị trí cha của lot_stock ⇒ phải
        # làm TRƯỚC khi dời lot_stock vào khu cha (không thì khu đó bị đổi thành "DL").
        if self.code != "DL" or self.name != "Kho Đại Linh":
            self.write({"name": "Kho Đại Linh", "code": "DL"})

        Location = self.env["stock.location"]
        locations = {"wh_view": self.view_location_id}
        to_stamp = []

        for key, name, usage, parent_key in _DLM_NEW_LOCATIONS:
            xml_id = "dl_inventory.stock_location_%s" % key
            existing = self.env.ref(xml_id, raise_if_not_found=False)
            if existing:
                locations[key] = existing
                # Ép lại cấu trúc (cha + usage) nếu lệch; KHÔNG đụng `name` (user có thể đã đổi).
                structure = {}
                if existing.usage != usage:
                    structure["usage"] = usage
                if existing.location_id != locations[parent_key]:
                    structure["location_id"] = locations[parent_key].id
                if structure:
                    existing.write(structure)
                continue
            locations[key] = Location.create({
                "name": name,
                "usage": usage,
                "location_id": locations[parent_key].id,
                "company_id": self.company_id.id,
            })
            to_stamp.append({
                "xml_id": xml_id, "record": locations[key], "noupdate": True})

        # Hai vị trí Odoo có sẵn: Việt hoá tên + chuyển vào khu 1 (active_test=False vì có thể đang lưu trữ).
        qc_location = self.with_context(active_test=False).wh_input_stock_loc_id
        if qc_location:
            qc_location.write({
                "name": "Chờ kiểm hàng", "location_id": locations["nhan"].id})
            locations["nhan_qc"] = qc_location
            to_stamp.append({
                "xml_id": "dl_inventory.stock_location_nhan_qc",
                "record": qc_location, "noupdate": True})
        # "Kho nguyên vật liệu" (= lot_stock_id) nằm dưới Kho nhà máy sản xuất;
        # chứa cả vật tư thô lẫn BTP. Giữ xml_id `nhan_kho` (migration/test neo vào);
        # `name` ghi đè mỗi -u vì là bản ghi Odoo tạo, không phải seed của mình.
        self.lot_stock_id.write({
            "name": "Kho nguyên vật liệu",
            "location_id": locations["khosx"].id})
        locations["nhan_kho"] = self.lot_stock_id
        to_stamp.append({
            "xml_id": "dl_inventory.stock_location_nhan_kho",
            "record": self.lot_stock_id, "noupdate": True})

        if to_stamp:
            self.env["ir.model.data"]._update_xmlids(to_stamp)

        # Khu quá cảnh + khu gom nhóm: cấm kiểm kê/chọn tay. Số chỉ đổi qua phiếu.
        # Gồm cả "khosx" (container) vì chọn khu cha là với tay vào ô con qua child_of.
        for key in ("nhan", "nhan_qc", "nhan_tra", "khosx"):
            if locations.get(key):
                locations[key].dlm_no_inventory = True

        # Lấy hàng FIFO: cố ý KHÔNG cấu hình — Odoo mặc định đã fifo. Lá chắn là
        # TEST (test_kho_vat_tu_lay_hang_theo_fifo), không phải dòng config vô hiệu.
        # (FIFO = chiến lược lấy hàng của `stock` lõi, không phải định giá tồn.)

        # Vị trí đối tác & ảo Sản xuất — Odoo tạo sẵn; Sản xuất không có XML ID nên tra theo usage.
        locations["suppliers"] = self.env.ref("stock.stock_location_suppliers")
        locations["customers"] = self.env.ref("stock.stock_location_customers")
        locations["production"] = self.env["stock.location"].search([
            ("usage", "=", "production"),
            ("company_id", "in", (self.company_id.id, False)),
        ], limit=1)
        # Vị trí ảo "Điều chỉnh tồn": bản lề phiếu Hoá phế liệu. scrap_location=False
        # BẮT BUỘC vì usage 'inventory' có 2 vị trí — tránh chọn nhầm vị trí huỷ bỏ.
        locations["inventory_adj"] = self.env["stock.location"].search([
            ("usage", "=", "inventory"),
            ("scrap_location", "=", False),
            ("company_id", "in", (self.company_id.id, False)),
        ], limit=1)
        return locations

    def _dlm_setup_picking_types(self, locations):
        """Việt hoá 3 loại hoạt động native + tạo 6 loại riêng của Đại Linh."""
        self.ensure_one()
        # Ghi `name` cho TỪNG ngôn ngữ đang bật: bản dịch vi_VN của `stock` sẽ thắng nếu chỉ ghi en_US.
        langs = self.env["res.lang"].get_installed()
        for field_name, name, sequence_code in _DLM_NATIVE_PICKING_TYPES:
            picking_type = self.with_context(active_test=False)[field_name]
            if not picking_type:
                continue
            picking_type.write({"name": name, "sequence_code": sequence_code})
            for lang_code, _lang_name in langs:
                translated = picking_type.with_context(lang=lang_code)
                if translated.name != name:
                    translated.write({"name": name})
        # Chuyển kho nội bộ bị Odoo lưu trữ khi kho chưa bật nhiều vị trí ⇒ bật tường minh.
        if self.int_type_id and not self.int_type_id.active:
            self.int_type_id.active = True

        PickingType = self.env["stock.picking.type"]
        Sequence = self.env["ir.sequence"].sudo()
        to_stamp = []
        for (key, name, code, sequence_code,
                src_key, dest_key, sequence) in _DLM_NEW_PICKING_TYPES:
            xml_id = "dl_inventory.%s" % key
            existing = self.env.ref(xml_id, raise_if_not_found=False)
            if existing:
                # Ghi lại sequence_code để Odoo chuẩn hoá prefix về "<mã kho>/<mã loại>/".
                existing.write({"sequence_code": sequence_code})
                continue
            source = locations.get(src_key)
            destination = locations.get(dest_key)
            if not source or not destination:
                # Thiếu vị trí ảo (DB dựng thiếu) ⇒ bỏ qua thay vì tạo bản ghi trỏ vào hư không.
                continue
            picking_type = PickingType.create({
                "name": name,
                "code": code,
                "sequence_code": sequence_code,
                "warehouse_id": self.id,
                "company_id": self.company_id.id,
                "default_location_src_id": source.id,
                "default_location_dest_id": destination.id,
                "sequence": sequence,
                "sequence_id": Sequence.create({
                    "name": "%s Trình tự %s" % (self.name, sequence_code),
                    "prefix": "%s/%s/" % (self.code, sequence_code),
                    "padding": 5,
                    "company_id": self.company_id.id,
                }).id,
            })
            to_stamp.append({
                "xml_id": xml_id, "record": picking_type, "noupdate": True})
        if to_stamp:
            self.env["ir.model.data"]._update_xmlids(to_stamp)

        # Phiếu [8] KHÔNG sinh phiếu bù (create_backorder='never'); đặt ở đây để vá bản ghi cũ mặc định 'ask'.
        fg_type = self.env.ref(
            "dl_inventory.picking_type_mo_receipt", raise_if_not_found=False)
        if fg_type and fg_type.create_backorder != "never":
            fg_type.create_backorder = "never"
        return True

    def _dlm_setup_reception_route(self, locations):
        """Bật nhận hàng 2 bước (NCC → Chờ kiểm → đã nhận); chạy sau khi "Kiểm & cất hàng" đã tồn tại."""
        self.ensure_one()
        if self.reception_steps != "two_steps":
            self.write({"reception_steps": "two_steps"})
        else:
            # Đã two_steps từ trước: ép dựng lại tuyến để áp get_rules_dict.
            route_vals = self._create_or_update_route()
            if route_vals:
                self.write(route_vals)

        # Giao hàng đi từ KHO THÀNH PHẨM, không phải vị trí tồn mặc định.
        if locations.get("tp") and self.out_type_id:
            self.out_type_id.default_location_src_id = locations["tp"]
        # Chuyển kho mặc định: Kho nguyên vật liệu → Xưởng; là chặng bắt buộc, mang chữ ký nhận của Kỹ thuật.
        if locations.get("nhan_kho") and locations.get("xuong") and self.int_type_id:
            self.int_type_id.write({
                "default_location_src_id": locations["nhan_kho"].id,
                "default_location_dest_id": locations["xuong"].id,
            })
        return True

    def _dlm_main_warehouse(self):
        """Kho duy nhất của Đại Linh; ưu tiên bản seed Odoo, không tạo mới."""
        warehouse = self.env.ref("stock.warehouse0", raise_if_not_found=False)
        if warehouse:
            return warehouse
        return self.env["stock.warehouse"].search([], limit=1)


class StockLocation(models.Model):
    _inherit = "stock.location"

    # Khu quá cảnh/gom nhóm: số chỉ đổi qua phiếu, không kiểm kê tay. Là FIELD
    # để domain eval được (không có ref) + Admin mở/khoá khu khác không phải sửa code.
    dlm_no_inventory = fields.Boolean(
        string="Không kiểm kê tay", default=False,
        help="Ô không được chọn tay trên phiếu và không được đếm tay. Hai loại: "
             "khu QUÁ CẢNH (Chờ kiểm, Chờ trả nhà cung cấp) — tồn ở đó đang gắn với "
             "chứng từ đang mở; và khu GOM NHÓM (Khu nhập hàng, Kho nhà máy "
             "sản xuất) — chọn khu cha là với tay được vào mọi ô con.")

    @api.model
    def _dlm_setup_native_location_names(self):
        """Việt hoá tên vị trí Odoo tạo sẵn; idempotent, chỉ ghi khi tên còn đúng bản tiếng Anh gốc."""
        for xml_id, source_name, name in _DLM_NATIVE_LOCATIONS:
            location = self.env.ref(xml_id, raise_if_not_found=False)
            if location and location.name == source_name:
                location.sudo().write({"name": name})

        for usage, is_scrap, source_name, name in _DLM_NATIVE_VIRTUAL_LOCATIONS:
            locations = self.with_context(active_test=False).search([
                ("usage", "=", usage),
                ("scrap_location", "=", is_scrap),
                ("name", "=", source_name),
                ("company_id", "in", (self.env.company.id, False)),
            ])
            if locations:
                locations.sudo().write({"name": name})
        return True

    def _dlm_location(self, xml_id):
        """Tra vị trí kho theo XML ID, báo lỗi rõ nếu chưa seed."""
        location = self.env.ref(xml_id, raise_if_not_found=False)
        if not location:
            raise ValueError(
                _("Chưa seed vị trí kho '%s'. Chạy lại: -u dl_inventory") % xml_id)
        return location

    @api.model
    def _dlm_virtual_location(self, usage):
        """Vị trí ảo Odoo theo usage ('production'/'inventory') — tra bằng usage vì không có XML ID."""
        location = self.search([
            ("usage", "=", usage),
            ("company_id", "in", (self.env.company.id, False)),
        ], limit=1)
        if not location:
            raise ValueError(_(
                "Không tìm thấy vị trí ảo '%s' của Odoo — DB dựng thiếu."
            ) % usage)
        return location
