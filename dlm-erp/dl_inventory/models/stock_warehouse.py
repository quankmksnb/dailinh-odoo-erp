# -*- coding: utf-8 -*-
"""K2 — Cấu trúc kho Đại Linh: MỘT kho, ba khu.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §4 và §5.

Đại Linh là MỘT nhà xưởng ⇒ đúng một ``stock.warehouse``. Ba "kho" theo cách gọi
của doanh nghiệp là ba ``stock.location`` con:

    DL (kho)
    ├── DL/NHAN          Khu nhập hàng                    ← khu 1
    │   ├── DL/NHAN/QC       Chờ kiểm hàng                  (= wh_input_stock_loc_id)
    │   ├── DL/NHAN/KHO      Vật tư & hàng thương mại       (= lot_stock_id)
    │   └── DL/NHAN/TRA      Chờ trả NCC
    ├── DL/XUONG         Kho nhà máy sản xuất             ← khu 2
    │   ├── DL/XUONG/BTP     Bán thành phẩm
    │   └── DL/XUONG/PL      Phế liệu chờ bán
    └── DL/TP            Kho thành phẩm                   ← khu 3

KHÔNG tạo kho mới: Odoo `stock` đã dựng sẵn ``stock.warehouse0`` khi cài. Ở đây
chỉ ĐỔI TÊN/MÃ và bố trí lại vị trí — tạo warehouse thứ hai sẽ biến mọi luân
chuyển nội bộ thành liên kho.

Toàn bộ seed nằm trong MỘT hàm ``_dlm_setup_inventory_layout`` vì ba bước phụ
thuộc thứ tự chặt chẽ (vị trí → loại hoạt động → tuyến nhận hàng); tách ra ba
lệnh gọi XML thì chỉ cần đảo dòng là hỏng mà không lỗi nào nổ.
"""

from odoo import _, api, fields, models

# Vị trí TỰ TẠO thêm (ngoài 2 vị trí Odoo đã có sẵn: Input và Stock).
# (hậu tố xml_id, tên hiển thị, usage, khoá vị trí cha)
#
# ⚠️ Ba khu đều là 'internal', KHÔNG phải 'view', dù chúng chỉ dùng để gom nhóm.
# Lý do: _compute_complete_name của Odoo BỎ tiền tố cha với vị trí 'view'
# (complete_name = chính tên nó) ⇒ khu 'view' sẽ hiện "Khu nhập hàng/Chờ kiểm
# hàng", mất luôn "DL/" và lệch hẳn với hai khu còn lại. Chỉ vị trí GỐC của kho
# (do Odoo tạo, tên "DL") mới là 'view'.
_DLM_NEW_LOCATIONS = [
    ("nhan", "Khu nhập hàng", "internal", "wh_view"),
    ("nhan_tra", "Chờ trả NCC", "internal", "nhan"),
    ("xuong", "Kho nhà máy sản xuất", "internal", "wh_view"),
    ("xuong_btp", "Bán thành phẩm", "internal", "xuong"),
    ("xuong_pl", "Phế liệu chờ bán", "internal", "xuong"),
    ("tp", "Kho thành phẩm", "internal", "wh_view"),
]

# Loại hoạt động TỰ TẠO thêm. Ba loại native (nhận/giao/chuyển kho) chỉ đổi tên.
# (hậu tố xml_id, tên, code, mã seq, khoá vị trí nguồn, khoá vị trí đích, thứ tự)
#
# Số phiếu theo đúng quy ước Odoo: <mã kho>/<mã loại>/<số> → "DL/KC/00001".
# ⚠️ ĐỪNG tự đặt prefix kiểu "KC/2026/": stock.picking.type.write() GHI ĐÈ prefix
# về công thức trên mỗi lần `sequence_code` được ghi, nên prefix tự chế sẽ âm
# thầm bị revert — và override _get_sequence_values() cũng không cứu được.
_DLM_NEW_PICKING_TYPES = [
    ("picking_type_qc", "Kiểm & cất hàng", "internal", "KC",
     "nhan_qc", "nhan_kho", 12),
    ("picking_type_vendor_return", "Trả hàng NCC", "outgoing", "TR",
     "nhan_tra", "suppliers", 14),
    ("picking_type_scrap_sale", "Bán phế liệu", "outgoing", "BPL",
     "xuong_pl", "customers", 60),
    # 🔜 Hai loại dưới đây dành cho Lệnh sản xuất (B2) — seed sẵn để B2 chỉ việc
    # dùng, CHƯA có màn hình nào ở B1.
    ("picking_type_mo_issue", "Xuất vật tư sản xuất", "internal", "XSX",
     "xuong", "production", 30),
    ("picking_type_mo_receipt", "Nhập thành phẩm", "internal", "NTP",
     "production", "tp", 32),
]

# Ba loại hoạt động Odoo tạo sẵn — chỉ Việt hoá tên + gắn mã seq.
# (tên field trên warehouse, tên hiển thị, mã seq)
_DLM_NATIVE_PICKING_TYPES = [
    ("in_type_id", "Nhận hàng NCC", "NH"),
    ("out_type_id", "Giao hàng khách", "GH"),
    ("int_type_id", "Chuyển kho nội bộ", "CK"),
]


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    # ── Bước 2 của luồng nhận hàng dùng loại hoạt động RIÊNG ─────────────────
    def get_rules_dict(self):
        """Nhận hàng 2 bước: chặng ``Chờ kiểm → đã nhận`` dùng loại hoạt động
        "Kiểm & cất hàng" thay cho "Chuyển kho nội bộ" mặc định của Odoo.

        Override ở tầng này (thay vì vá tay stock.rule sau khi tạo) để cấu hình
        BỀN: mỗi lần Odoo dựng lại tuyến vẫn ra đúng loại hoạt động.
        """
        result = super().get_rules_dict()
        qc_type = self.env.ref(
            "dl_inventory.picking_type_qc", raise_if_not_found=False)
        if not qc_type:
            # Lần cài đầu, loại hoạt động chưa seed xong ⇒ giữ mặc định Odoo;
            # _dlm_setup_reception_route() sẽ dựng lại tuyến ngay sau đó.
            return result
        for warehouse in self:
            routings = result.get(warehouse.id, {}).get("two_steps") or []
            if len(routings) > 1:
                old = routings[1]
                routings[1] = self.Routing(
                    old.from_loc, old.dest_loc, qc_type, old.action)
        return result

    # ── Seed — gọi từ data/stock_inventory_layout.xml ────────────────────────
    # @api.model bắt buộc: <function> không truyền ids, mà call_kw chỉ bỏ qua
    # tham số ids với method mang api='model' (không thì IndexError khi nạp).
    @api.model
    def _dlm_setup_inventory_layout(self):
        """Dựng toàn bộ bố cục kho. Idempotent: chạy lại mỗi lần
        ``-u dl_inventory`` không nhân bản gì."""
        warehouse = self._dlm_main_warehouse()
        if not warehouse:
            return False
        locations = warehouse._dlm_setup_locations()
        warehouse._dlm_setup_picking_types(locations)
        warehouse._dlm_setup_reception_route(locations)
        warehouse._dlm_setup_lot_sequence()
        return True

    def _dlm_setup_lot_sequence(self):
        """Số lô do ĐẠI LINH tự sinh (không dùng số lô in trên chứng từ NCC):
        ``LO/2026/00001``.

        Tự sinh vì số của NCC không có định dạng thống nhất, dễ trùng giữa các
        NCC và dễ gõ sai — mà lô là mắt xích truy vết hàng lỗi. Số của NCC (nếu
        có) ghi vào ô Tham chiếu nội bộ của lô.

        Ghi bằng Python chứ không phải <record>: bản ghi gốc
        ``stock.sequence_production_lots`` mang noupdate=True nên XML bị bỏ qua.
        """
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
        # 🔴 THỨ TỰ QUAN TRỌNG: write 'code' làm Odoo đổi tên vị trí CHA của
        # lot_stock_id thành mã kho (_update_name_and_code). Phải làm TRƯỚC khi
        # chuyển lot_stock_id vào dưới DL/NHAN, không thì DL/NHAN bị đổi tên
        # thành "DL". ⚠️ Cùng lý do: ĐỔI MÃ KHO SAU NÀY sẽ đổi tên DL/NHAN —
        # chỉ sai nhãn (dữ liệu nguyên vẹn), đổi lại tên là xong.
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
                # Ép lại CẤU TRÚC (vị trí cha + usage) nếu lệch thiết kế — đây
                # là phần seed sở hữu. KHÔNG đụng `name`: người dùng có thể đã
                # đổi tên khu cho hợp cách gọi ở xưởng.
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

        # Hai vị trí Odoo đã có sẵn: Việt hoá tên + chuyển vào khu 1.
        # active_test=False vì Chờ kiểm hàng (wh_input_stock_loc_id) đang bị lưu
        # trữ khi kho còn ở chế độ nhận hàng 1 bước.
        qc_location = self.with_context(active_test=False).wh_input_stock_loc_id
        if qc_location:
            qc_location.write({
                "name": "Chờ kiểm hàng", "location_id": locations["nhan"].id})
            locations["nhan_qc"] = qc_location
            to_stamp.append({
                "xml_id": "dl_inventory.stock_location_nhan_qc",
                "record": qc_location, "noupdate": True})
        self.lot_stock_id.write({
            "name": "Vật tư & hàng thương mại",
            "location_id": locations["nhan"].id})
        locations["nhan_kho"] = self.lot_stock_id
        to_stamp.append({
            "xml_id": "dl_inventory.stock_location_nhan_kho",
            "record": self.lot_stock_id, "noupdate": True})

        if to_stamp:
            self.env["ir.model.data"]._update_xmlids(to_stamp)

        # RS-07 — Hai khu QUÁ CẢNH cấm kiểm kê tay. Cả hai đều là `internal`
        # (đúng thiết kế §4.1, để giữ tiền tố DL/) nên màn Kiểm kê vốn hứng
        # chúng: gõ "Tồn thực đếm = 0" ở khu Chờ trả NCC là 8 cây thép gỉ biến
        # khỏi sổ trong khi phiếu trả nháp vẫn treo ở màn Mua hàng — mất sạch
        # bằng chứng khiếu nại mà không lỗi nào nổ. Số ở hai khu này chỉ được
        # đổi qua phiếu (nhận / kiểm / trả).
        for key in ("nhan_qc", "nhan_tra"):
            if locations.get(key):
                locations[key].dlm_no_inventory = True

        # Vị trí đối tác & vị trí ẢO Sản xuất — Odoo tạo sẵn, KHÔNG tự dựng.
        # Sản xuất không có XML ID (Odoo lưu qua ir.property theo công ty) nên
        # phải tra theo usage.
        locations["suppliers"] = self.env.ref("stock.stock_location_suppliers")
        locations["customers"] = self.env.ref("stock.stock_location_customers")
        locations["production"] = self.env["stock.location"].search([
            ("usage", "=", "production"),
            ("company_id", "in", (self.company_id.id, False)),
        ], limit=1)
        return locations

    def _dlm_setup_picking_types(self, locations):
        """Việt hoá 3 loại hoạt động native + tạo 5 loại riêng của Đại Linh."""
        self.ensure_one()
        for field_name, name, sequence_code in _DLM_NATIVE_PICKING_TYPES:
            picking_type = self.with_context(active_test=False)[field_name]
            if picking_type:
                picking_type.write({"name": name, "sequence_code": sequence_code})
        # Chuyển kho nội bộ bị Odoo tạo ở trạng thái lưu trữ khi kho chưa bật
        # nhiều vị trí. Mô hình 3 khu SỐNG bằng chuyển kho ⇒ bật tường minh,
        # không trông vào việc cờ group được bật đúng thời điểm nào.
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
                # Ghi lại sequence_code (kể cả khi không đổi) để Odoo chuẩn hoá
                # prefix về "<mã kho>/<mã loại>/" — vá các bản ghi đã sinh ra
                # với prefix tự chế ở phiên bản trước.
                existing.write({"sequence_code": sequence_code})
                continue
            source = locations.get(src_key)
            destination = locations.get(dest_key)
            if not source or not destination:
                # Thiếu vị trí ẢO Sản xuất (DB dựng thiếu) — bỏ qua loại hoạt
                # động đó thay vì tạo bản ghi trỏ vào hư không.
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
        return True

    def _dlm_setup_reception_route(self, locations):
        """Bật nhận hàng 2 bước: NCC → Chờ kiểm → (kiểm đạt) → đã nhận.

        Chạy SAU khi "Kiểm & cất hàng" đã tồn tại, để tuyến sinh ra trỏ đúng
        loại hoạt động đó (xem get_rules_dict).
        """
        self.ensure_one()
        if self.reception_steps != "two_steps":
            self.write({"reception_steps": "two_steps"})
        else:
            # Đã two_steps từ trước (vd -u lần 2): tuyến cũ đang trỏ loại hoạt
            # động mặc định ⇒ ép dựng lại để áp get_rules_dict.
            route_vals = self._create_or_update_route()
            if route_vals:
                self.write(route_vals)

        # Giao hàng đi từ KHO THÀNH PHẨM, không phải vị trí tồn mặc định.
        if locations.get("tp") and self.out_type_id:
            self.out_type_id.default_location_src_id = locations["tp"]
        # Chuyển kho nội bộ mặc định: vật tư từ khu nhập ra xưởng (luồng chiếm
        # phần lớn số lần chuyển kho).
        if locations.get("nhan_kho") and locations.get("xuong") and self.int_type_id:
            self.int_type_id.write({
                "default_location_src_id": locations["nhan_kho"].id,
                "default_location_dest_id": locations["xuong"].id,
            })
        return True

    def _dlm_main_warehouse(self):
        """Kho duy nhất của Đại Linh. Ưu tiên bản ghi seed của Odoo; nếu DB đã
        đổi khác thì lấy kho đầu tiên — KHÔNG tạo mới (§3.1: một kho)."""
        warehouse = self.env.ref("stock.warehouse0", raise_if_not_found=False)
        if warehouse:
            return warehouse
        return self.env["stock.warehouse"].search([], limit=1)


class StockLocation(models.Model):
    _inherit = "stock.location"

    # RS-07 — Khu quá cảnh: số chỉ đổi qua phiếu, không kiểm kê tay.
    # Là FIELD chứ không phải danh sách XML ID viết cứng trong domain: domain
    # của act_window được eval KHÔNG có `ref()`, và Admin còn phải mở/khoá được
    # khu khác về sau mà không phải sửa code.
    dlm_no_inventory = fields.Boolean(
        string="Không kiểm kê tay", default=False,
        help="Khu quá cảnh (Chờ kiểm, Chờ trả NCC): tồn chỉ đổi qua phiếu kho. "
             "Kiểm kê tay ở đây sẽ xoá hàng mà chứng từ đang tham chiếu tới.")

    def _dlm_location(self, xml_id):
        """Tra vị trí kho theo XML ID, báo lỗi RÕ nếu chưa seed.

        Dùng cho module sau (Lệnh sản xuất — B2) thay vì tự search theo tên:
        thiếu vị trí thì phải nổ ngay lúc gọi, không im lặng tạo move sai chỗ.
        """
        location = self.env.ref(xml_id, raise_if_not_found=False)
        if not location:
            raise ValueError(
                _("Chưa seed vị trí kho '%s'. Chạy lại: -u dl_inventory") % xml_id)
        return location
