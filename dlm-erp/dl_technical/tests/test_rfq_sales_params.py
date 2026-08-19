"""Đề bài có cấu trúc ở dòng RFQ — Sales nhập thông số theo mẫu của nhóm.

Nhóm sản phẩm là chìa khoá định tuyến: nhóm nào có BOM mẫu tham số thì form hỏi
đúng các ô mẫu ấy khai, nhóm nào chưa có mẫu thì giữ luật cũ (mô tả HOẶC bản vẽ).
Số Sales gõ vào ô có nhãn thay cho việc regex đoán từ văn bản tự do, và cho phép
khớp CHÍNH XÁC cấu hình đã từng làm thay vì chấm điểm mờ theo tên.

Kiểm 4 nhóm: đồng bộ bộ thông số theo nhóm, các cổng chặn, ưu tiên số có cấu
trúc trong bộ dò khớp, và làn L1 (khớp chữ ký ⇒ workspace mồi sẵn SP + định mức).
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical")
class TestRfqSalesParams(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_root = cls.env.ref("dl_product.categ_root_finished")
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_meter = cls.env.ref("uom.product_uom_meter")

        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test thông số RFQ",
            "partner_role": "customer",
            # dl_partner: khách CÁ NHÂN phải có điện thoại, và số KHÔNG được trùng
            # giữa các khách ⇒ mỗi file test giữ một số riêng.
            "phone": "0989204715",
        })

        # Nhóm CÓ mẫu tham số (như "Bàn ghế sắt" ngoài đời).
        cls.categ_param = cls.env["product.category"].create({
            "name": "Bàn thép (test thông số)",
            "parent_id": cls.finished_root.id,
        })
        # Nhóm CHƯA có mẫu — giữ luật cũ.
        cls.categ_plain = cls.env["product.category"].create({
            "name": "Hàng lẻ (test thông số)",
            "parent_id": cls.finished_root.id,
        })

        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 25x25 (test thông số)",
            "product_kind": "material",
        })
        cls.generic = cls.env["product.product"].create({
            "name": "Bàn thép dùng chung (test thông số)",
            "categ_id": cls.categ_param.id,
            "product_kind": "manufactured",
        })

        cls.template = cls.env["dl.bom.template"].create({
            "name": "Mẫu Bàn thép (test thông số)",
            "product_category_id": cls.categ_param.id,
            "generic_product_id": cls.generic.id,
            "line_ids": [(0, 0, {
                "material_id": cls.material.id,
                "quantity": 1.0,
            })],
            "param_ids": [
                (0, 0, {"code": "D", "name": "Chiều dài", "dim_role": "length",
                        "sequence": 10, "default_value": 1200,
                        "value_min": 600, "value_max": 2400, "required": True}),
                (0, 0, {"code": "R", "name": "Chiều rộng", "dim_role": "width",
                        "sequence": 20, "default_value": 800,
                        "value_min": 300, "value_max": 1200, "required": True}),
            ],
        })
        cls.template.action_confirm()

    # ------------------------------------------------------------------
    # RFQ luôn phải tạo KÈM dòng: `_check_has_lines` chặn yêu cầu báo giá rỗng,
    # nên không tách được thành hai bước create.
    def _create_line(self, request_type="manufactured", **overrides):
        # Kiểu hàng (reference_product_id) là thứ quyết định bộ thông số — nhóm
        # chỉ còn là trục thương mại. Mặc định trỏ vào SP dùng chung có mẫu.
        line_vals = {
            "product_type": "manufactured",
            "product_name": "Bàn bán trú test",
            "product_category_id": self.categ_param.id,
            "reference_product_id": self.generic.id,
            "quantity": 1.0,
            "dimension_note": "",
        }
        line_vals.update(overrides)
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": request_type,
            "line_ids": [(0, 0, line_vals)],
        })
        return request.line_ids[0]

    def _param_commands(self, values):
        """Lệnh o2m mang sẵn số — giống hệt cái form Sales gửi xuống khi Lưu."""
        return [(0, 0, {
            "template_param_id": p.id,
            "sequence": p.sequence,
            "code": p.code,
            "name": p.name,
            "dim_role": p.dim_role,
            "value": values.get(p.code, 0.0),
            "value_min": p.value_min,
            "value_max": p.value_max,
            "required": p.required,
        }) for p in self.template.param_ids]

    def _make_line(self, values=None, **overrides):
        """Dòng gia công thuộc nhóm có mẫu, mang sẵn bộ thông số ``values``.

        Truyền số ngay trong create (không tạo rồi ghi sau): cổng chặn soi bộ
        tham số ngay lúc lưu, nên dòng thiếu số không tồn tại được — đúng như
        trên form."""
        if values is not None:
            overrides.setdefault("param_ids", self._param_commands(values))
        return self._create_line(**overrides)

    # ==================================================================
    # 1. Đồng bộ bộ thông số theo nhóm
    # ==================================================================
    def test_params_built_for_parametric_category(self):
        """Nhóm có mẫu ⇒ dòng tự có đúng bộ ô mẫu khai (không cần onchange)."""
        line = self._make_line({"D": 1200, "R": 400})
        self.assertTrue(line.has_parametric_template)
        self.assertEqual(sorted(line.param_ids.mapped("code")), ["D", "R"])
        self.assertEqual(
            line.param_ids.filtered(lambda p: p.code == "D").dim_role, "length")

    def test_params_empty_for_plain_category(self):
        """Nhóm chưa có mẫu ⇒ không hiện ô thông số nào."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            dimension_note="Kệ 4 tầng theo bản vẽ")
        self.assertFalse(line.has_parametric_template)
        self.assertFalse(line.param_ids)

    def test_params_not_prefilled_with_template_default(self):
        """Ô để TRỐNG, không mồi default_value của mẫu.

        Mặc định là con số của mẫu chứ không của khách; mồi vào thì mọi dòng
        thiếu kích thước cùng ra một định mức mà không ai thấy sai."""
        line = self._create_line(attachment_ids=[(0, 0, {
            "name": "ban-ve.pdf", "datas": b"MA=="})])
        self.assertEqual(set(line.param_ids.mapped("value")), {0.0})

    def test_clearing_kieu_hang_drops_params(self):
        """Bỏ Kiểu hàng ⇒ bộ ô rụng theo (số cũ mất, có chủ ý).

        Tham số chỉ có nghĩa trong họ của MỘT kiểu hàng; giữ số của mẫu cũ khi
        đã bỏ kiểu hàng là giữ một đề bài không còn ai đọc được.

        🔴 Từ 2026-08-19 khoá là KIỂU HÀNG chứ không phải nhóm: nhóm là trục
        thương mại, chứa nhiều kết cấu, không quyết định được bộ thông số."""
        line = self._make_line({"D": 1200, "R": 400},
                               dimension_note="Bàn 1200x400 theo mẫu cũ")
        line.reference_product_id = False
        self.assertFalse(line.param_ids)
        self.assertFalse(line.has_parametric_template)

    def test_template_change_keeps_values_by_code(self):
        """Mẫu thêm tham số mới ⇒ số đã gõ giữ nguyên theo MÃ, chỉ thêm ô trống.

        Đây là ca mà cơ chế giữ-theo-mã phục vụ: mẫu tiến hoá sau khi RFQ đã
        nhập, Sales không phải gõ lại từ đầu."""
        line = self._make_line({"D": 1200, "R": 400})
        self.template.param_ids = [(0, 0, {
            "code": "C", "name": "Chiều cao", "dim_role": "height",
            "sequence": 30, "required": False})]
        line._dlm_sync_params()
        self.assertEqual(sorted(line.param_ids.mapped("code")), ["C", "D", "R"])
        self.assertEqual(
            line.param_ids.filtered(lambda p: p.code == "D").value, 1200)
        self.assertEqual(
            line.param_ids.filtered(lambda p: p.code == "C").value, 0.0)

    def test_trading_line_has_no_params(self):
        """Dòng thương mại không đi qua định mức nên không có ô thông số."""
        product = self.env["product.product"].create({
            "name": "Hàng thương mại test thông số",
            "product_kind": "trading",
            "standard_price": 100.0,
            "list_price": 150.0,
        })
        line = self._create_line(
            request_type="trading",
            product_type="trading",
            product_name=False,
            product_category_id=False,
            resolved_product_id=product.id)
        self.assertFalse(line.param_ids)

    # ==================================================================
    # 2. Cổng chặn
    # ==================================================================
    def test_category_required_for_manufactured(self):
        with self.assertRaises(ValidationError):
            self._create_line(product_category_id=False,
                              dimension_note="1200x400")

    def test_missing_params_blocked_without_attachment(self):
        """Nhóm có mẫu + thiếu thông số bắt buộc + không bản vẽ ⇒ chặn."""
        with self.assertRaises(ValidationError):
            self._make_line({"D": 1200})   # thiếu R

    def test_missing_params_allowed_with_attachment(self):
        """Khách gửi bản vẽ đầy đủ là ca hợp lệ — Sales không phải đọc bản vẽ."""
        attachment = self.env["ir.attachment"].create({
            "name": "ban-ve.pdf", "datas": b"MA==",
        })
        line = self._create_line(attachment_ids=[(6, 0, attachment.ids)])
        self.assertTrue(line.has_missing_params, "Chưa điền số nào")
        line._check_manufactured_spec()   # không nổ vì đã có bản vẽ

    def test_complete_params_pass_without_description(self):
        """Điền đủ thông số ⇒ không bắt gõ thêm mô tả."""
        line = self._make_line({"D": 1200, "R": 400})
        self.assertFalse(line.has_missing_params)
        line._check_manufactured_spec()   # không nổ

    def test_plain_category_still_needs_note_or_attachment(self):
        """Nhóm chưa có mẫu giữ nguyên luật cũ — không nới lỏng theo."""
        with self.assertRaises(ValidationError):
            self._create_line(
                product_category_id=self.categ_plain.id,
            reference_product_id=False, dimension_note="")

    def test_out_of_range_is_warning_not_block(self):
        """Cỡ đặc biệt vẫn gửi được — Sales không có quyền phán cỡ nào làm được."""
        line = self._make_line({"D": 5000, "R": 400})   # D vượt max 2400
        self.assertTrue(line.has_out_of_range_params)
        line._check_manufactured_spec()   # KHÔNG chặn

    def test_negative_param_blocked(self):
        line = self._make_line({"D": 1200, "R": 400})
        with self.assertRaises(ValidationError):
            line.param_ids.filtered(lambda p: p.code == "D").value = -100

    def test_counted_uom_requires_integer_qty(self):
        """2,5 bộ bàn ghế là lỗi gõ — chặn trước khi vào báo giá."""
        with self.assertRaises(ValidationError):
            self._make_line({"D": 1200, "R": 400},
                            quantity=2.5, uom_id=self.uom_unit.id)

    def test_measured_uom_allows_fraction(self):
        """100,5 mét máng điện là con số hợp lệ."""
        line = self._make_line({"D": 1200, "R": 400},
                               quantity=100.5, uom_id=self.uom_meter.id)
        self.assertEqual(line.quantity, 100.5)

    def test_legacy_line_without_params_stays_valid(self):
        """Dòng CŨ (kiểu hàng được gắn mẫu SAU khi dòng đã tạo) không bị khoá cứng.

        Đây là ca migration: coi "không có ô nào" là "thiếu tất cả" sẽ chặn mọi
        thao tác sửa trên RFQ lịch sử và làm chính migration nổ giữa chừng."""
        legacy_product = self.env["product.product"].create({
            "name": "Hàng lẻ chưa có mẫu (test)",
            "categ_id": self.categ_plain.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        legacy_bom = self.env["dl.bom"].create({
            "product_id": legacy_product.id,
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 1.0})],
        })
        legacy_bom.action_confirm()

        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=legacy_product.id,
            dimension_note="Bàn 1200x400 (đơn cũ)")
        self.assertFalse(line.param_ids, "Lúc tạo, kiểu hàng chưa có mẫu")

        # Kiểu hàng được gắn mẫu tham số VỀ SAU.
        late = self.env["dl.bom.template"].create({
            "name": "Mẫu gắn muộn (test)",
            "product_category_id": self.categ_plain.id,
            "generic_product_id": legacy_product.id,
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 1.0})],
            "param_ids": [(0, 0, {
                "code": "D", "name": "Chiều dài", "required": True})],
        })
        late.action_confirm()
        line.invalidate_recordset()

        self.assertTrue(line.has_parametric_template)
        self.assertFalse(line.has_missing_params, "Dòng cũ không bị coi là thiếu")
        line._check_manufactured_spec()      # không nổ
        line.write({"quantity": 5.0})        # vẫn sửa được

    def test_empty_param_ids_still_seeded(self):
        """Truyền param_ids RỖNG không phải là đường né cổng chặn."""
        with self.assertRaises(ValidationError):
            self._create_line(param_ids=[])

    # ==================================================================
    # 3. Bộ dò khớp đọc số có cấu trúc
    # ==================================================================
    def test_structured_params_beat_regex_guess(self):
        """Số Sales gõ vào ô có nhãn THẮNG số đoán từ câu chữ."""
        line = self._make_line(
            {"D": 1200, "R": 400},
            dimension_note="tham khảo cái 9999x8888 hôm trước")
        dims = line._dlm_wanted_dimensions()
        self.assertEqual(dims["length"], 1200)
        self.assertEqual(dims["width"], 400)

    def test_regex_fallback_when_no_params(self):
        """Nhóm chưa có mẫu ⇒ vẫn đoán từ mô tả như trước (đường dự phòng)."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            dimension_note="Kệ 1400x830, cao 750")
        dims = line._dlm_wanted_dimensions()
        self.assertEqual(dims["length"], 1400)
        self.assertEqual(dims["width"], 830)

    def test_param_values_need_all_required(self):
        """Thiếu một ô ⇒ không trả bộ giá trị (chữ ký thiếu là chữ ký sai).

        Dòng thiếu số chỉ tồn tại được khi có bản vẽ thay thế — nên ca này dựng
        kèm đính kèm, đúng như ngoài đời."""
        partial = self._make_line(
            {"D": 1200},
            attachment_ids=[(0, 0, {"name": "bv.pdf", "datas": b"MA=="})])
        self.assertFalse(partial._dlm_param_values())
        self.assertTrue(self._make_line({"D": 1200, "R": 400})._dlm_param_values())

    # ==================================================================
    # 4. Làn L1 — khớp chữ ký cấu hình
    # ==================================================================
    def _generate_instance(self, values):
        """Định mức đã chốt cho một cấu hình (giả lập lần đặt trước)."""
        bom = self.template.generate_instance(self.generic, values)
        bom.write({"is_rfq_provisional": False, "rfq_source_line_id": False})
        bom.action_confirm()
        return bom

    def test_exact_match_finds_previous_config(self):
        """Đặt lại đúng cấu hình cũ ⇒ trỏ thẳng định mức đã có, không đoán."""
        bom = self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1200, "R": 400})
        self.assertEqual(line.exact_bom_id, bom)

    def test_exact_match_ignores_different_config(self):
        self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1500, "R": 400})
        self.assertFalse(line.exact_bom_id)

    def test_exact_match_skipped_when_out_of_range(self):
        """Cỡ ngoài miền phải để Kỹ thuật xem tận nơi, dù chữ ký có trùng.

        Định mức cũ được sinh khi cỡ đó CÒN hợp lệ, rồi mẫu mới siết miền lại
        (2400 → 1400). Đây là ca thật: mẫu đổi miền sau khi đã làm hàng."""
        bom = self._generate_instance({"D": 2000, "R": 400})
        self.assertTrue(bom.param_signature)
        self.template.param_ids.filtered(
            lambda p: p.code == "D").value_max = 1400
        line = self._make_line({"D": 2000, "R": 400})
        self.assertTrue(line.has_out_of_range_params)
        self.assertFalse(line.exact_bom_id)

    def test_workspace_prefills_from_exact_match(self):
        """Làn L1: workspace mở ra đã có sẵn SP + định mức ⇒ KTV chỉ gật."""
        bom = self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1200, "R": 400})
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})
        defaults = wizard.default_get(
            ["product_id", "manual_bom_id", "product_origin"])
        self.assertEqual(defaults.get("product_id"), self.generic.id)
        self.assertEqual(defaults.get("manual_bom_id"), bom.id)
        self.assertEqual(defaults.get("product_origin"), "exact_config")

    def test_param_panel_seeded_from_sales(self):
        """Panel tham số của KTV mồi sẵn số Sales nhập — hết phải gõ lại."""
        line = self._make_line({"D": 1500, "R": 600})
        wizard = self.env["dl.rfq.resolve.wizard"].create({
            "rfq_line_id": line.id, "product_id": self.generic.id})
        commands = wizard._dlm_param_panel_commands(self.template, line)
        seeded = {c[2]["code"]: c[2]["value"] for c in commands if c[0] == 0}
        self.assertEqual(seeded, {"D": 1500, "R": 600})

    def test_param_panel_empty_without_sales_values(self):
        """Sales bỏ trống ⇒ panel vẫn trống (KHÔNG lấy default của mẫu).

        Mồi mặc định vào đây thì mọi dòng thiếu kích thước cùng ra một định mức
        mà không ai thấy sai — đúng cái luật cũ giữ, và đổi lần này không nới."""
        line = self._create_line(attachment_ids=[(0, 0, {
            "name": "bv.pdf", "datas": b"MA=="})])   # có ô, chưa điền số nào
        wizard = self.env["dl.rfq.resolve.wizard"].create({
            "rfq_line_id": line.id, "product_id": self.generic.id})
        commands = wizard._dlm_param_panel_commands(self.template, line)
        self.assertEqual(
            {c[2]["value"] for c in commands if c[0] == 0}, {0.0})

    # ==================================================================
    # 5. Kỹ thuật KHÔNG phải quyết "sản phẩm nào" — hệ thống suy hộ
    # ==================================================================
    def _open_workspace(self, line):
        """Đúng đường Kỹ thuật bấm "Xử lý" — default_get chạy trong create()."""
        return self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({})

    def test_sales_pick_routes_to_that_product(self):
        """Sales chọn Kiểu hàng ⇒ đó CHÍNH LÀ sản phẩm, không đoán tiếp.

        Với họ có mẫu tham số thì kiểu hàng là SP dùng chung, nên mọi cỡ vẫn
        đổ về một mã — không bao giờ đẻ mã theo từng kích thước."""
        line = self._make_line({"D": 1500, "R": 600})
        product, origin = line._dlm_autoresolve_product()
        self.assertEqual(product, self.generic)
        self.assertEqual(origin, "sales_pick")
        wizard = self._open_workspace(line)
        self.assertEqual(wizard.product_id, self.generic)
        self.assertTrue(wizard.auto_selected)

    def test_exact_name_reuses_existing_product(self):
        """Trùng HỆT tên ⇒ dùng lại SP đó, không tạo trùng.

        Luật cũ chặn cứng rồi bảo KTV "quay lại chọn chính sản phẩm này" — nay
        hệ thống chọn hộ, KTV khỏi đi một vòng."""
        existing = self.env["product.product"].create({
            "name": "Kệ kho 4 tầng (test bậc thang)",
            "categ_id": self.categ_plain.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="  kệ kho 4 TẦNG (test bậc thang)  ",
            dimension_note="2400x600x2000")
        product, origin = line._dlm_autoresolve_product()
        self.assertEqual(product, existing, "Khác hoa-thường/khoảng trắng vẫn là một")
        self.assertEqual(origin, "name_match")

    def test_brand_new_product_created_from_sales_input(self):
        """Mới toanh ⇒ tự tạo SP TẠM mang đúng tên + nhóm Sales khai.

        Đây là thứ thay hẳn khối "Tạo sản phẩm mới": KTV mở workspace ra đã có
        sản phẩm, đi thẳng vào định mức."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Khung tủ điện hoàn toàn mới",
            dimension_note="800x600x2000")
        wizard = self._open_workspace(line)
        self.assertEqual(wizard.product_origin, "created")
        product = wizard.product_id
        self.assertEqual(product.name, "Khung tủ điện hoàn toàn mới",
                         "Tên lấy đúng của Sales")
        self.assertEqual(product.categ_id, self.categ_plain,
                         "Nhóm lấy đúng của Sales")
        self.assertEqual(product.product_kind, "manufactured")
        self.assertTrue(product.is_rfq_provisional, "Tạm cho tới khi chốt đơn")
        self.assertEqual(product.dlm_lifecycle_state, "draft")
        self.assertEqual(product.rfq_source_line_id, line)

    def test_similar_name_creates_but_keeps_warning_card(self):
        """Tên GẦN GIỐNG ⇒ vẫn tạo mới, nhưng thẻ nhắc "đã có món tương tự".

        🔴 Đây là chỗ trú mới của lá chắn tên gần giống. Luật cũ chặn cứng và
        bắt KTV tick xác nhận; luật mới không chặn nữa, nên nếu thẻ này tắt thì
        hệ thống âm thầm đẻ sản phẩm trùng nghĩa mà không ai biết."""
        self.env["product.product"].create({
            "name": "Kệ kho 4 tầng",
            "categ_id": self.categ_plain.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Kệ kho 4 tầng loại 2",   # gần giống, KHÔNG trùng hệt
            dimension_note="2400x600x2000")
        wizard = self._open_workspace(line)
        self.assertEqual(wizard.product_origin, "created")
        self.assertNotEqual(wizard.suggestion_state, "none",
                            "Phải còn thẻ nhắc dù đã tự tạo sản phẩm")
        self.assertEqual(wizard.suggested_product_id.name, "Kệ kho 4 tầng")

    def test_use_suggested_cleans_up_auto_created_product(self):
        """Bấm "Dùng món cũ" ⇒ sản phẩm tạm vừa tự tạo bị dọn ngay."""
        self.env["product.product"].create({
            "name": "Giá đỡ máy bơm",
            "categ_id": self.categ_plain.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Giá đỡ máy bơm loại 2",
            dimension_note="500x400")
        wizard = self._open_workspace(line)
        provisional = wizard.product_id
        self.assertTrue(provisional.is_rfq_provisional)

        wizard.action_use_suggested_product()

        self.assertEqual(wizard.product_id.name, "Giá đỡ máy bơm")
        self.assertFalse(provisional.exists(), "SP tạm phải bị dọn ngay")

    def test_autoresolve_is_idempotent(self):
        """Mở lại workspace KHÔNG đẻ thêm sản phẩm tạm thứ hai."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Khung tủ điện mở hai lần",
            dimension_note="800x600x2000")
        first = self._open_workspace(line).product_id
        second = self._open_workspace(line).product_id
        self.assertEqual(first, second)
        self.assertEqual(self.env["product.product"].search_count([
            ("rfq_source_line_id", "=", line.id)]), 1)

    def test_name_clash_with_btp_falls_back_to_manual(self):
        """Trùng tên với BÁN THÀNH PHẨM ⇒ trả tay cho KTV, không nổ.

        BTP không dùng làm sản phẩm của dòng được (khách không đặt bán thành
        phẩm) mà tạo mới cũng bị `_check_dlm_name_duplicate` chặn — nếu không
        có nhánh này thì mở workspace là ném lỗi."""
        # BTP phải thuộc nhánh VẬT TƯ (nhánh Thành phẩm bị chặn cứng).
        btp_categ = self.env["product.category"].create({
            "name": "BTP (test bậc thang)",
            "parent_id": self.env.ref("dl_product.categ_root_material").id,
        })
        self.env["product.product"].create({
            "name": "Cụm chân bàn hàn sẵn (test)",
            "categ_id": btp_categ.id,
            "product_kind": "material_processed",
        })
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Cụm chân bàn hàn sẵn (test)",
            dimension_note="600x600")
        product, origin = line._dlm_autoresolve_product()
        self.assertFalse(product)
        self.assertFalse(origin)
        wizard = self._open_workspace(line)   # không nổ
        self.assertFalse(wizard.product_id, "Để KTV tự gỡ ca hiếm này")

    def test_restore_auto_product_is_not_a_dead_end(self):
        """Bấm nhầm "Đổi sản phẩm" với món mới toanh ⇒ lấy lại được, KHÔNG đẻ thêm.

        🔴 Từ khi gỡ nút "Tạo sản phẩm mới" khỏi workspace, đây là đường DUY
        NHẤT để quay về. Không có nó thì KTV kẹt cứng giữa chừng: món chưa từng
        làm nên không có gì để chọn, mà cũng không còn cách tạo."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            product_name="Khung tủ điện quay lại được",
            dimension_note="800x600x2000")
        wizard = self._open_workspace(line)
        original = wizard.product_id
        self.assertEqual(wizard.product_origin, "created")

        wizard.action_change_product()
        self.assertFalse(wizard.product_id)

        wizard.action_restore_auto_product()
        self.assertEqual(wizard.product_id, original, "Phải là ĐÚNG bản cũ")
        self.assertEqual(wizard.product_origin, "created")
        self.assertEqual(self.env["product.product"].search_count([
            ("rfq_source_line_id", "=", line.id)]), 1,
            "Gọi lại bậc thang không được đẻ sản phẩm thứ hai")

    def test_workspace_has_no_product_creation_surface(self):
        """Workspace KHÔNG còn bất kỳ đường tạo sản phẩm nào cho Kỹ thuật.

        Khoá lại bằng test vì đây là ranh giới VAI TRÒ, không phải chi tiết kỹ
        thuật: khai sinh danh mục là việc hành chính, hệ thống làm ngầm từ tên +
        nhóm Sales khai. Ai thêm lại nút "Tạo sản phẩm" sẽ thấy test này đỏ."""
        Wizard = self.env["dl.rfq.resolve.wizard"]
        for gone in ("mode", "new_product_name", "new_product_category_id",
                     "confirm_not_just_size", "confirm_similar_name",
                     "name_dup_state", "new_product_blocking_template_id"):
            self.assertNotIn(gone, Wizard._fields, "Field %s phải bị gỡ" % gone)
        for gone in ("action_create_product", "action_use_duplicate_product"):
            self.assertFalse(hasattr(Wizard, gone), "Action %s phải bị gỡ" % gone)

    def test_change_product_clears_origin(self):
        """Bấm "Đổi sản phẩm" ⇒ xoá cả nhãn lý do (không còn là máy chọn)."""
        line = self._make_line({"D": 1500, "R": 600})
        wizard = self._open_workspace(line)
        self.assertTrue(wizard.product_origin)
        wizard.action_change_product()
        self.assertFalse(wizard.product_id)
        self.assertFalse(wizard.product_origin)
        self.assertFalse(wizard.auto_selected)

    def test_legacy_line_without_category_left_to_technician(self):
        """Dòng cũ chưa có nhóm ⇒ không suy được, mở ra vẫn cho chọn tay."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            reference_product_id=False,
            dimension_note="1200x800")
        line.invalidate_recordset()
        self.env.cr.execute(
            "UPDATE dl_quotation_request_line SET product_category_id = NULL "
            "WHERE id = %s", (line.id,))
        line.invalidate_recordset()
        product, origin = line._dlm_autoresolve_product()
        self.assertFalse(product)
        self.assertFalse(origin)

    # ==================================================================
    # 5b. Mẫu neo theo SẢN PHẨM — nhiều kết cấu trong cùng một nhóm
    # ==================================================================
    def _second_family(self):
        """Kết cấu THỨ HAI trong cùng nhóm thương mại `categ_param`."""
        generic2 = self.env["product.product"].create({
            "name": "Ghế băng khung thép (test)",
            "categ_id": self.categ_param.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        tmpl2 = self.env["dl.bom.template"].create({
            "name": "Mẫu Ghế băng (test)",
            "product_category_id": self.categ_param.id,
            "generic_product_id": generic2.id,
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 1.0})],
            "param_ids": [(0, 0, {
                "code": "D", "name": "Chiều dài ghế", "dim_role": "length",
                "value_min": 800, "value_max": 2400, "required": True})],
        })
        tmpl2.action_confirm()
        return generic2, tmpl2

    def test_two_parametric_templates_in_one_category(self):
        """🔴 Hai kết cấu khác nhau trong CÙNG nhóm, mỗi cái một mẫu.

        Mô hình cũ (mẫu neo theo NHÓM + unique(nhóm, version)) CẤM bản thứ hai —
        đó là lỗi kiến trúc đã sửa. Sổ đặt hàng thật có ít nhất 5 kết cấu trong
        nhóm "Bàn ghế học sinh"."""
        generic2, tmpl2 = self._second_family()
        self.assertEqual(self.generic._dlm_parametric_template(), self.template)
        self.assertEqual(generic2._dlm_parametric_template(), tmpl2)
        self.assertEqual(
            sorted(self.categ_param._dlm_parametric_generic_ids().ids),
            sorted((self.generic | generic2).ids))

    def test_params_follow_kieu_hang_not_category(self):
        """Cùng nhóm, đổi Kiểu hàng ⇒ bộ ô thông số đổi theo mẫu của kiểu đó."""
        generic2, _tmpl2 = self._second_family()
        line = self._make_line({"D": 1200, "R": 400})
        self.assertEqual(sorted(line.param_ids.mapped("code")), ["D", "R"])

        line.reference_product_id = generic2
        self.assertEqual(line.param_ids.mapped("code"), ["D"],
                         "Ghế băng chỉ hỏi chiều dài")
        self.assertEqual(line.param_ids.value, 1200, "Giữ số theo MÃ tham số")

    def test_version_numbering_is_per_product(self):
        """Hai họ trong cùng nhóm đánh số phiên bản ĐỘC LẬP, không tranh nhau."""
        generic2, tmpl2 = self._second_family()
        self.assertEqual(self.template.version, 1)
        self.assertEqual(tmpl2.version, 1, "Không bị đẩy thành version 2")

    # ==================================================================
    # 5c. Làn L0 — dòng tự chốt, không qua Kỹ thuật
    # ==================================================================
    def test_signature_match_autoresolves_line(self):
        """Đúng cấu hình đã duyệt ⇒ dòng tự chốt, RFQ lên thẳng Chờ tạo báo giá."""
        bom = self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1200, "R": 400})

        self.assertTrue(line.auto_resolved)
        self.assertEqual(line.resolved_bom_id, bom)
        self.assertEqual(line.resolved_product_id, self.generic)
        self.assertEqual(line.quotation_request_id.status, "confirmed")

    def test_new_size_does_not_autoresolve(self):
        """Cỡ MỚI phải qua Kỹ thuật — chưa ai duyệt định mức cho cỡ này."""
        self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1500, "R": 400})
        self.assertFalse(line.auto_resolved)
        self.assertFalse(line.resolved_bom_id)

    def test_draft_bom_never_autoresolves(self):
        """Chỉ định mức ĐÃ DUYỆT mới cho bỏ qua Kỹ thuật."""
        bom = self.template.generate_instance(self.generic, {"D": 1200, "R": 400})
        bom.write({"is_rfq_provisional": False, "rfq_source_line_id": False})
        self.assertEqual(bom.status, "draft")
        line = self._make_line({"D": 1200, "R": 400})
        self.assertFalse(line.auto_resolved)

    def test_sales_editing_size_drops_out_of_auto_lane(self):
        """🔴 Sales sửa kích thước sau khi dòng tự chốt ⇒ RỚT làn, về Kỹ thuật.

        Không có chiều này thì báo giá đi ra mang định mức của một cỡ khác, và
        không chỗ nào báo động."""
        self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1200, "R": 400})
        self.assertTrue(line.auto_resolved)

        line.param_ids.filtered(lambda p: p.code == "D").value = 1500

        self.assertFalse(line.auto_resolved, "Phải rớt khỏi làn tự động")
        self.assertFalse(line.resolved_bom_id)
        self.assertFalse(line.resolved_product_id)

    def test_autoresolve_does_not_override_technician(self):
        """Kỹ thuật đã chốt tay thì hệ thống KHÔNG ghi đè."""
        bom = self._generate_instance({"D": 1200, "R": 400})
        line = self._make_line({"D": 1500, "R": 400})   # cỡ mới, KT phải làm
        line.write({"resolved_product_id": self.generic.id,
                    "resolved_bom_id": bom.id})
        self.assertFalse(line.auto_resolved)

        line.write({"quantity": 9.0})

        self.assertEqual(line.resolved_bom_id, bom, "Kết quả của KTV giữ nguyên")
        self.assertFalse(line.auto_resolved)

    # ==================================================================
    # 5d. Danh sách Kiểu hàng cho Sales
    # ==================================================================
    def test_kieu_hang_hides_unusable_products(self):
        """SP không mẫu và không định mức nào là cái bẫy — không được hiện."""
        trap = self.env["product.product"].create({
            "name": "SP chưa có định mức nào (test)",
            "categ_id": self.categ_param.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        line = self._make_line({"D": 1200, "R": 400})
        self.assertIn(self.generic, line.reference_product_ids,
                      "SP dùng chung của mẫu phải chọn được dù chưa có instance")
        self.assertNotIn(trap, line.reference_product_ids)

    def test_kieu_hang_label_tells_which_behaviour(self):
        """Dropdown phải cho biết chọn xong sẽ ra gì."""
        catalog = self.env["product.product"].create({
            "name": "Bàn giáo viên cố định (test)",
            "categ_id": self.categ_param.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })
        std = self.env["dl.bom"].create({
            "product_id": catalog.id, "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": self.material.id, "quantity": 1.0})]})
        std.action_confirm()

        labelled = self.generic.with_context(dlm_show_bom_kind=True)
        self.assertIn("theo kích thước", labelled.display_name)
        self.assertIn("cỡ cố định",
                      catalog.with_context(dlm_show_bom_kind=True).display_name)
        # Không bật context thì tên giữ nguyên, không rò ra chỗ khác.
        self.assertNotIn("theo kích thước", self.generic.display_name)

    # ==================================================================
    # 6. Ranh giới vai trò — thông số là ĐỀ BÀI của Sales
    # ==================================================================
    def test_tech_cannot_edit_sales_params(self):
        """Kỹ thuật sửa được định mức, KHÔNG sửa được yêu cầu của khách."""
        line = self._make_line({"D": 1200, "R": 400})
        tech = self.env["res.users"].with_context(
            no_reset_password=True).create({
                "name": "KTV test thông số",
                "login": "ktv_test_params",
                "email": "ktv_test_params@example.com",
                "groups_id": [(6, 0, [self.env.ref("dl_base.dl_group_tech").id])],
            })
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            line.with_user(tech).write({"uom_id": self.uom_meter.id})

    def test_sales_editing_params_flags_review(self):
        """Sales đổi thông số sau khi KT đã chốt ⇒ dòng phải được xem lại.

        🔴 Phải chạy dưới user Sales THẬT: TransactionCase mặc định có
        `env.su = True`, mà cả cổng phân vai lẫn nhánh gắn cờ đều nằm sau
        `if not self.env.su` — chạy bằng env mặc định thì test xanh giả."""
        line = self._make_line({"D": 1200, "R": 400})
        bom = self._generate_instance({"D": 1200, "R": 400})
        line.write({"resolved_product_id": self.generic.id,
                    "resolved_bom_id": bom.id})
        self.assertFalse(line.needs_review)

        sales = self.env["res.users"].with_context(
            no_reset_password=True).create({
                "name": "Sales test thông số",
                "login": "sales_test_params",
                # _flag_needs_review ghi chatter ⇒ tác giả phải có email.
                "email": "sales_test_params@example.com",
                "groups_id": [(6, 0, [self.env.ref("dl_base.dl_group_ba").id])],
            })
        self.env.invalidate_all()
        param_d = line.param_ids.filtered(lambda p: p.code == "D")
        line.with_user(sales).write({
            "param_ids": [(1, param_d.id, {"value": 1500})]})
        self.assertTrue(
            line.needs_review,
            "Đổi 'Dài 1200 → 1500' làm định mức đã chốt sai hẳn")
