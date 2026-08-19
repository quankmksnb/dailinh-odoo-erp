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
        line_vals = {
            "product_type": "manufactured",
            "product_name": "Bàn bán trú test",
            "product_category_id": self.categ_param.id,
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

    def test_switch_to_plain_category_drops_params(self):
        """Đổi sang nhóm chưa có mẫu ⇒ bộ ô rụng theo (số cũ mất, có chủ ý).

        Tham số chỉ có nghĩa trong họ sản phẩm của mẫu; giữ lại số của mẫu cũ
        khi đã sang nhóm khác là giữ một đề bài không còn ai đọc được."""
        line = self._make_line({"D": 1200, "R": 400},
                               dimension_note="Bàn 1200x400 theo mẫu cũ")
        line.product_category_id = self.categ_plain.id
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
                product_category_id=self.categ_plain.id, dimension_note="")

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
        """Dòng CŨ (nhóm gắn mẫu SAU khi dòng đã tạo) không bị khoá cứng.

        Đây là ca migration: coi "không có ô nào" là "thiếu tất cả" sẽ chặn mọi
        thao tác sửa trên RFQ lịch sử và làm chính migration nổ giữa chừng."""
        line = self._create_line(
            product_category_id=self.categ_plain.id,
            dimension_note="Bàn 1200x400 (đơn cũ)")
        self.assertFalse(line.param_ids)
        # Nhóm được gắn mẫu tham số về sau.
        late_generic = self.env["product.product"].create({
            "name": "Hàng lẻ dùng chung (test)",
            "categ_id": self.categ_plain.id,
            "product_kind": "manufactured",
        })
        late = self.env["dl.bom.template"].create({
            "name": "Mẫu gắn muộn (test)",
            "product_category_id": self.categ_plain.id,
            "generic_product_id": late_generic.id,
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
            ["product_id", "manual_bom_id", "exact_config_match", "mode"])
        self.assertEqual(defaults.get("product_id"), self.generic.id)
        self.assertEqual(defaults.get("manual_bom_id"), bom.id)
        self.assertTrue(defaults.get("exact_config_match"))

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
    # 5. Ranh giới vai trò — thông số là ĐỀ BÀI của Sales
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
