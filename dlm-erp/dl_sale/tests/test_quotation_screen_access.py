# -*- coding: utf-8 -*-
"""L2 Integration test cho SCR-23..32 (FDS): các màn RFQ/Báo giá/Phê duyệt
báo giá/Đơn bán hàng chưa có test L2 riêng về "hiển thị đúng + ẩn/hiện theo
vai trò + kết quả điều hướng". Các file đã có (test_dl_quotation_unit.py,
test_rfq_suggestion.py, test_rfq_resolve_workspace.py,
test_dl_pricing_approval_request.py/test_pricing_approval_request_unit.py...)
phủ kỹ NGHIỆP VỤ tính giá/phê duyệt — file này KHÔNG lặp lại, chỉ canh ranh
giới ĐỌC/GHI/TẠO ở cấp ACL (ir.model.access.csv), menu (groups= trên
<menuitem>) và domain action, giống test_bom_screen_access.py/
test_product_screen_access.py.

SCR-23 Tạo RFQ (menu_rfq_create, action_dl_quotation_request_create) — BA/
Trưởng KD/Admin có trong menu VÀ có ACL perm_create=1; CEO/Kỹ thuật không có
trong menu VÀ ACL perm_create=0 — loại trừ là THẬT ở cả hai tầng, không phải
chỉ ẩn menu.

SCR-24 Tất cả RFQ (menu_rfq_all, action_dl_quotation_request) — cả 5 vai trò
(CEO/Admin/BA/Kỹ thuật/Trưởng KD) đọc được, đúng khai báo menu (đã được canh
tổng quát ở test_menu_role_declaration.py — ở đây canh sâu hơn: CEO chỉ đọc
(1,0,0,0) trong khi BA/Trưởng KD ghi được nhưng không xoá, Kỹ thuật ghi được
nhưng không tạo mới).

SCR-25 RFQ cần xử lý (menu_rfq_my, action_dl_quotation_request_my) — menu chỉ
khai Kỹ thuật + Admin (BA/Trưởng KD/CEO dù đọc được model vẫn không thấy mục
này). Domain thật của action CHỈ lọc request_type='manufactured' — KHÔNG lọc
theo received_by/kỹ thuật viên hiện tại như tên "cần xử lý" gợi ý; đây là
hàng đợi CHUNG của cả đội Kỹ thuật, không phải "việc của riêng tôi". Bộ lọc
mặc định search_default_to_process chỉ là context tìm kiếm (bỏ được), không
phải domain cứng.

SCR-26 Chi tiết RFQ — dl.quotation.request.line có ACL LỆCH với header: BA/
Trưởng KD unlink được DÒNG (perm_unlink=1) dù không unlink được RFQ HEADER
(perm_unlink=0) — hai model khác ACL dù cùng một "màn hình" theo mắt người
dùng.

SCR-27/28 Danh sách/Chi tiết báo giá (dl.quotation) — Kỹ thuật hoàn toàn
KHÔNG có dòng ACL nào (khác RFQ, nơi Kỹ thuật vẫn đọc/ghi được) — đọc thẳng
sẽ AccessError ngay từ bước đọc, không chỉ bị ẩn menu (menu_dl_sale_quotation
cũng loại tường minh bằng "-dl_base.dl_group_tech"). Trái ngược
dl.quotation.request (CEO chỉ đọc), CEO ở đây có FULL CRUD trên dl.quotation
— còn Trưởng KD ngược lại chỉ ĐỌC (perm_write=0): duyệt/gửi khách của Trưởng
KD đi qua các action Python tự sudo(), không phải ghi trực tiếp qua ACL.
Field chi phí (total_cost, gross_profit, cost_breakdown_html... trên header;
material_cost, operation_cost, adjustment_cost, total_cost... trên dòng) có
groups=_COST_GROUPS THẬT ở cấp field Python (không chỉ ẩn ở arch view) —
_COST_GROUPS = CEO + Admin + Trưởng KD, KHÔNG PHẢI "chỉ CEO" như cách đọc chữ
"CEO sees cost columns for management only" của FDS dễ gây hiểu lầm; đọc
đúng theo comment nguồn ("Trưởng KD, CEO, Admin") thì khớp.

SCR-29/30 Phê duyệt báo giá — domain của action_dl_quote_approval CHỈ lọc
request_type='quote_over_threshold'; model dl.pricing.approval.request còn 5
loại yêu cầu khác (profit_config, discount_config, quote_discount,
quote_below_floor, matrix_config) dùng CHUNG model nhưng KHÔNG lọt vào màn
này — đây là domain action, không phải ir.rule (không có rule nào theo
request_type trong pricing_record_rules.xml). BA/Kỹ thuật có ACL đọc được
NHƯNG không ghi được (không duyệt/từ chối được) bất kỳ loại yêu cầu nào.
Admin có ACL FULL CRUD trên model nhưng KHÔNG có trong groups= của
menu_dl_sale_quote_approval — Admin không thấy màn Phê duyệt báo giá dù kỹ
thuật có quyền, đúng chủ đích ("Admin là vai trò kỹ thuật, không duyệt báo
giá") — business rule chặn admin duyệt quote_over_threshold/matrix_config đã
được test_admin_bypasses_commercial_but_not_quote_or_matrix (dl_config) canh,
không lặp lại ở đây. Các field q_total_cost/q_gross_profit/... (dl_sale/
models/pricing_approval_ext.py) cũng groups=_COST_GROUPS ở cấp field — NHƯNG
`risk_summary` (cột "Rủi ro") thì KHÔNG: view xml gắn groups= trên <field>
trong tree (ẩn cột), và comment nguồn ghi "cột này cũng gắn
groups=_COST_GROUPS" — nhưng field Python risk_summary thật sự không có
tham số groups= nào. BA (ACL đọc=1 trên model) gọi read()/fields_get() thẳng
vẫn thấy được chữ "Dưới giá sàn"/"Vượt trần chiết khấu" — rò rỉ tín hiệu giá
vốn ra ngoài phạm vi _COST_GROUPS, lệch với đúng ý đồ ghi trong comment.

SCR-31/32 Đơn bán hàng (dl.sale.order) — tra riêng ir.model.access.csv của
dl_sale tưởng Kỹ thuật không có ACL nào (giống dl.quotation), NHƯNG
dl_inventory (phụ thuộc bắc cầu qua dl_purchase trong lệnh cài test) bổ sung
access_dl_sale_order_tech cấp Kỹ thuật ĐỌC (không ghi/tạo/xoá) — Kỹ thuật vẫn
bị ẩn khỏi menu_dl_sale_order nên không thấy màn này trên sidebar, nhưng đọc
thẳng qua ORM/RPC vẫn được, không AccessError như suy đoán ban đầu chỉ tra
một file ACL. Khác dl.quotation, ở đây Trưởng KD có ACL ghi/tạo đầy đủ (không
chỉ đọc) — không có sự bất đối xứng CEO/Trưởng KD như ở màn Báo giá.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

_COST_HEADER_FIELDS = (
    "total_cost", "effective_markup", "floor_amount", "gross_profit",
    "list_markup", "floor_markup", "cost_material_total",
    "cost_operation_total", "cost_adjustment_total", "cost_breakdown_html",
    "target_markup", "below_floor",
)
_COST_LINE_FIELDS = (
    "material_cost", "operation_cost", "adjustment_cost", "total_cost",
)
_COST_APPROVAL_FIELDS = (
    "q_total_cost", "q_target_markup", "q_effective_markup",
    "q_floor_amount", "q_below_floor", "q_gross_profit", "q_list_markup",
    "q_floor_markup", "q_cost_material_total", "q_cost_operation_total",
    "q_cost_adjustment_total", "q_cost_breakdown_html",
)


def _user(env, group_xmlid, login):
    return env["res.users"].create({
        "name": login,
        "login": login,
        "groups_id": [(6, 0, [
            env.ref("base.group_user").id,
            env.ref(group_xmlid).id,
        ])],
    })


def _menu_visible(env, user, menu_xmlid):
    menu = env.ref(menu_xmlid)
    visible = env["ir.ui.menu"].with_user(user)._visible_menu_ids()
    return menu.id in visible


def _domain_of(env, action_xmlid):
    """Domain THẬT của action, đọc thẳng từ record — test sẽ đỏ nếu domain
    trong XML bị sửa lệch, thay vì chép tay domain rồi tự kiểm tra chính nó."""
    action = env.ref(action_xmlid)
    return safe_eval(action.domain or "[]")


# ============================================================
# SCR-23 — Tạo RFQ (menu_rfq_create, action_dl_quotation_request_create)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuotationRequestCreateAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr23_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr23_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr23_test")
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr23_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr23_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn Tạo RFQ", "partner_role": "customer",
            "mobile": "0900002301",
        })
        cls.categ = cls.env["product.category"].create({
            "name": "Nhóm test màn Tạo RFQ",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })

    def _vals(self, name):
        return {
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": name,
                "product_category_id": self.categ.id,
                "quantity": 1.0,
                "dimension_note": "Kích thước test",
            })],
        }

    def test_ba_can_create_rfq(self):
        """TC-INT-TestQuotationRequestCreateAccess-001: BA (trong menu_rfq_create)
        tạo được RFQ mới — khớp ACL access_dl_quotation_request_ba perm_create=1.
        """
        rfq = self.env["dl.quotation.request"].with_user(self.ba).create(
            self._vals("SP test SCR23 001"))
        self.assertTrue(rfq.id)

    def test_sales_manager_can_create_rfq(self):
        """TC-INT-TestQuotationRequestCreateAccess-002: Trưởng KD (trong
        menu_rfq_create) cũng tạo được RFQ.
        """
        rfq = self.env["dl.quotation.request"].with_user(self.sm).create(
            self._vals("SP test SCR23 002"))
        self.assertTrue(rfq.id)

    def test_admin_can_create_rfq(self):
        """TC-INT-TestQuotationRequestCreateAccess-003: Admin (trong
        menu_rfq_create) tạo được RFQ.
        """
        rfq = self.env["dl.quotation.request"].with_user(self.admin).create(
            self._vals("SP test SCR23 003"))
        self.assertTrue(rfq.id)

    def test_ceo_cannot_create_rfq_at_acl_level(self):
        """TC-INT-TestQuotationRequestCreateAccess-004: CEO không có trong
        menu_rfq_create VÀ cũng bị chặn thật ở ACL (access_dl_quotation_
        request_ceo perm_create=0) — loại trừ không chỉ là ẩn menu, comment
        trong menus.xml ("mở được nhưng không lưu nổi") đúng với ACL thật.
        """
        with self.assertRaises(AccessError):
            self.env["dl.quotation.request"].with_user(self.ceo).create(
                self._vals("SP test SCR23 004"))

    def test_technician_cannot_create_rfq_at_acl_level(self):
        """TC-INT-TestQuotationRequestCreateAccess-005: Kỹ thuật cũng không
        có trong menu_rfq_create VÀ bị chặn ở ACL (access_dl_quotation_
        request_tech perm_create=0) — Kỹ thuật chỉ XỬ LÝ RFQ có sẵn, không
        tạo RFQ mới.
        """
        with self.assertRaises(AccessError):
            self.env["dl.quotation.request"].with_user(self.tech).create(
                self._vals("SP test SCR23 005"))

    def test_menu_create_visible_only_to_ba_sm_admin(self):
        """TC-INT-TestQuotationRequestCreateAccess-006: menu_rfq_create chỉ
        hiện cho BA/Trưởng KD/Admin — CEO và Kỹ thuật không thấy mục này dù
        họ đọc được model dl.quotation.request (loại trừ ở TẦNG MENU, cộng
        thêm ACL đã canh ở các ca trên).
        """
        self.assertTrue(_menu_visible(self.env, self.ba, "dl_technical.menu_rfq_create"))
        self.assertTrue(_menu_visible(self.env, self.sm, "dl_technical.menu_rfq_create"))
        self.assertTrue(_menu_visible(self.env, self.admin, "dl_technical.menu_rfq_create"))
        self.assertFalse(_menu_visible(self.env, self.ceo, "dl_technical.menu_rfq_create"))
        self.assertFalse(_menu_visible(self.env, self.tech, "dl_technical.menu_rfq_create"))


# ============================================================
# SCR-24 — Quản lý RFQ / Tất cả RFQ (menu_rfq_all, action_dl_quotation_request)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuotationRequestListAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr24_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr24_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr24_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr24_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr24_test")
        cls.purchasing = _user(cls.env, "dl_base.dl_group_purchasing", "pur_scr24_test")
        cls.warehouse = _user(cls.env, "dl_base.dl_group_warehouse", "wh_scr24_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn Tất cả RFQ", "partner_role": "customer",
            "mobile": "0900002401",
        })
        cls.categ = cls.env["product.category"].create({
            "name": "Nhóm test màn Tất cả RFQ",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })
        cls.rfq = cls.env["dl.quotation.request"].create({
            "customer_id": cls.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "SP test SCR24",
                "product_category_id": cls.categ.id,
                "quantity": 1.0,
                "dimension_note": "Kích thước test",
            })],
        })

    def test_all_five_declared_roles_can_read_list(self):
        """TC-INT-TestQuotationRequestListAccess-001: cả 5 vai trò khai trong
        menu_rfq_all (CEO/Admin/BA/Kỹ thuật/Trưởng KD) đều đọc được RFQ —
        khớp ACL perm_read=1 của cả 5 dòng trong ir.model.access.csv.
        """
        for user in (self.ceo, self.admin, self.ba, self.tech, self.sm):
            name = self.rfq.with_user(user).read(["name"])[0]["name"]
            self.assertEqual(name, self.rfq.name)

    def test_ceo_is_read_only_on_rfq(self):
        """TC-INT-TestQuotationRequestListAccess-002: CEO chỉ đọc (ACL
        1,0,0,0) — sửa/xoá RFQ đã có đều AccessError, đúng chú thích trong
        quotation_request_views.xml về quyền CEO.
        """
        with self.assertRaises(AccessError):
            self.rfq.with_user(self.ceo).write({"description": "CEO sửa"})
        with self.assertRaises(AccessError):
            self.rfq.with_user(self.ceo).unlink()

    def test_technician_can_write_but_not_create_or_unlink_rfq(self):
        """TC-INT-TestQuotationRequestListAccess-003: Kỹ thuật ghi được RFQ
        đã có (cần để xử lý dòng qua wizard) nhưng không tạo RFQ mới, không
        xoá — khớp ACL access_dl_quotation_request_tech (1,1,0,0).
        """
        self.rfq.with_user(self.tech).write({"description": "Kỹ thuật ghi chú"})
        self.assertEqual(self.rfq.description, "Kỹ thuật ghi chú")
        with self.assertRaises(AccessError):
            self.env["dl.quotation.request"].with_user(self.tech).create({
                "customer_id": self.customer.id,
                "line_ids": [(0, 0, {
                    "product_type": "manufactured",
                    "product_name": "SP lạ Kỹ thuật tạo",
                    "quantity": 1.0,
                    "dimension_note": "x",
                })],
            })
        with self.assertRaises(AccessError):
            self.rfq.with_user(self.tech).unlink()

    def test_ba_and_sales_manager_can_write_not_unlink_rfq(self):
        """TC-INT-TestQuotationRequestListAccess-004: BA/Trưởng KD ghi/tạo
        được RFQ nhưng không xoá hẳn (ACL perm_unlink=0 cho cả hai).
        """
        for user in (self.ba, self.sm):
            self.rfq.with_user(user).write({"description": "Sửa bởi %s" % user.login})
            with self.assertRaises(AccessError):
                self.rfq.with_user(user).unlink()

    def test_purchasing_and_warehouse_have_no_access(self):
        """TC-INT-TestQuotationRequestListAccess-005: Mua hàng/Thủ kho không
        có dòng ACL nào cho dl.quotation.request — không đọc được, không chỉ
        bị ẩn menu.
        """
        with self.assertRaises(AccessError):
            self.rfq.with_user(self.purchasing).read(["name"])
        with self.assertRaises(AccessError):
            self.rfq.with_user(self.warehouse).read(["name"])


# ============================================================
# SCR-25 — RFQ cần xử lý (menu_rfq_my, action_dl_quotation_request_my)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuotationRequestMyQueueAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr25_test")
        cls.other_tech = _user(cls.env, "dl_base.dl_group_tech", "tech2_scr25_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr25_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr25_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr25_test")
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr25_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn RFQ cần xử lý", "partner_role": "customer",
            "mobile": "0900002501",
        })
        cls.categ = cls.env["product.category"].create({
            "name": "Nhóm test màn RFQ cần xử lý",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })
        cls.manufactured_rfq = cls.env["dl.quotation.request"].create({
            "customer_id": cls.customer.id,
            "request_type": "manufactured",
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "SP gia công test SCR25",
                "product_category_id": cls.categ.id,
                "quantity": 1.0,
                "dimension_note": "Kích thước test",
            })],
        })
        cls.trading_product = cls.env["product.product"].create({
            "name": "SP thương mại test SCR25", "product_kind": "trading",
        })
        cls.trading_rfq = cls.env["dl.quotation.request"].create({
            "customer_id": cls.customer.id,
            "request_type": "trading",
            "trading_line_ids": [(0, 0, {
                "product_type": "trading",
                "resolved_product_id": cls.trading_product.id,
                "quantity": 1.0,
                "product_price": 100000.0,
            })],
        })

    def test_menu_my_queue_visible_only_to_tech_and_admin(self):
        """TC-INT-TestQuotationRequestMyQueueAccess-001: menu_rfq_my chỉ khai
        Kỹ thuật + Admin — BA/Trưởng KD/CEO KHÔNG thấy mục này dù cả ba đều
        đọc được model dl.quotation.request (ca này canh phần "không thấy",
        khác test_menu_role_declaration.py chỉ canh phần "vai trò khai ra
        phải thấy thật").
        """
        self.assertTrue(_menu_visible(self.env, self.tech, "dl_technical.menu_rfq_my"))
        self.assertTrue(_menu_visible(self.env, self.admin, "dl_technical.menu_rfq_my"))
        self.assertFalse(_menu_visible(self.env, self.ba, "dl_technical.menu_rfq_my"))
        self.assertFalse(_menu_visible(self.env, self.sm, "dl_technical.menu_rfq_my"))
        self.assertFalse(_menu_visible(self.env, self.ceo, "dl_technical.menu_rfq_my"))

    def test_domain_filters_by_request_type_only(self):
        """TC-INT-TestQuotationRequestMyQueueAccess-002: domain thật của
        action_dl_quotation_request_my chỉ có điều kiện
        request_type='manufactured' — RFQ gia công lọt vào, RFQ thương mại bị
        loại, đọc thẳng domain từ action (không suy đoán tên field).
        """
        domain = _domain_of(self.env, "dl_technical.action_dl_quotation_request_my")
        found = self.env["dl.quotation.request"].search(
            domain + [("id", "in", [self.manufactured_rfq.id, self.trading_rfq.id])]).ids
        self.assertIn(self.manufactured_rfq.id, found)
        self.assertNotIn(self.trading_rfq.id, found)

    def test_domain_is_not_scoped_to_current_technician(self):
        """TC-INT-TestQuotationRequestMyQueueAccess-003: domain KHÔNG lọc
        theo received_by/kỹ thuật viên hiện tại — một RFQ gia công CHƯA ai
        tiếp nhận (received_by rỗng) vẫn nằm trong domain khi tra bởi BẤT KỲ
        Kỹ thuật viên nào, chứng minh "RFQ cần xử lý" là hàng đợi CHUNG của
        đội Kỹ thuật, không phải danh sách việc riêng đã gán cho từng người
        — khác cách hiểu "assigned to me" mà tên màn hình dễ gợi ý.
        """
        self.assertFalse(self.manufactured_rfq.received_by)
        domain = _domain_of(self.env, "dl_technical.action_dl_quotation_request_my")
        for user in (self.tech, self.other_tech):
            found = self.env["dl.quotation.request"].with_user(user).search(
                domain + [("id", "=", self.manufactured_rfq.id)])
            self.assertEqual(found.id, self.manufactured_rfq.id)


# ============================================================
# SCR-26 — Chi tiết RFQ (dl.quotation.request.line, header khác ACL với dòng)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuotationRequestDetailAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr26_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr26_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr26_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr26_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn Chi tiết RFQ", "partner_role": "customer",
            "mobile": "0900002601",
        })
        cls.categ = cls.env["product.category"].create({
            "name": "Nhóm test màn Chi tiết RFQ",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })
        cls.rfq = cls.env["dl.quotation.request"].create({
            "customer_id": cls.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "SP test SCR26",
                "product_category_id": cls.categ.id,
                "quantity": 1.0,
                "dimension_note": "Kích thước test",
            })],
        })
        cls.line = cls.rfq.line_ids[0]

    def test_ceo_is_read_only_on_rfq_line(self):
        """TC-INT-TestQuotationRequestDetailAccess-001: CEO chỉ đọc được
        dòng RFQ, giống header (ACL access_dl_quotation_request_line_ceo
        1,0,0,0).
        """
        with self.assertRaises(AccessError):
            self.line.with_user(self.ceo).write({"dimension_note": "CEO sửa"})

    def test_ba_and_sales_manager_can_unlink_line_despite_header_blocked(self):
        """TC-INT-TestQuotationRequestDetailAccess-002: BA/Trưởng KD unlink
        được DÒNG RFQ (access_dl_quotation_request_line_ba/sm perm_unlink=1)
        — LỆCH với header dl.quotation.request nơi cả hai vai trò đều
        perm_unlink=0 (TestQuotationRequestListAccess-004). Hai model khác
        ACL dù cùng thuộc một "màn hình" theo mắt người dùng.
        """
        for user in (self.ba, self.sm):
            extra_line = self.env["dl.quotation.request.line"].create({
                "quotation_request_id": self.rfq.id,
                "product_type": "manufactured",
                "product_name": "Dòng phụ để xoá (%s)" % user.login,
                "product_category_id": self.categ.id,
                "quantity": 1.0,
                "dimension_note": "x",
            })
            extra_line.with_user(user).unlink()
            self.assertFalse(extra_line.exists())

    def test_technician_can_write_but_not_create_or_unlink_line(self):
        """TC-INT-TestQuotationRequestDetailAccess-003: Kỹ thuật ghi được
        dòng đã có (điền kết quả xử lý) nhưng không tạo dòng mới, không xoá
        (ACL access_dl_quotation_request_line_tech 1,1,0,0). Dùng
        supplement_note vì đây là field trung lập — không nằm trong
        _SALES_ONLY_LINE_FIELDS (Sales sở hữu) cũng không nằm trong
        _TECH_ONLY_LINE_FIELDS, nên business-rule write() không chặn thêm
        ngoài ACL.
        """
        self.line.with_user(self.tech).write({"supplement_note": "Kỹ thuật ghi chú"})
        with self.assertRaises(AccessError):
            self.env["dl.quotation.request.line"].with_user(self.tech).create({
                "quotation_request_id": self.rfq.id,
                "product_type": "manufactured",
                "product_name": "Dòng lạ Kỹ thuật tạo",
                "quantity": 1.0,
            })
        with self.assertRaises(AccessError):
            self.line.with_user(self.tech).unlink()


# ============================================================
# SCR-27/28 — Danh sách/Chi tiết báo giá (dl.quotation)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuotationListDetailAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr2728_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr2728_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr2728_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr2728_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr2728_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn Báo giá", "partner_role": "customer",
            "mobile": "0900002701",
        })
        cls.quotation = cls.env["dl.quotation"].create({
            "partner_id": cls.customer.id,
        })

    def test_technician_has_no_acl_access_at_all(self):
        """TC-INT-TestQuotationListDetailAccess-001: Kỹ thuật KHÔNG có dòng
        ACL nào cho dl.quotation (ir.model.access.csv của dl_sale không có
        access_dl_quotation_tech) — đọc thẳng bằng ORM AccessError ngay từ
        bước đọc, không chỉ bị ẩn menu. Đây là điểm khác dl.quotation.request
        (nơi Kỹ thuật vẫn đọc/ghi được, chỉ không tạo mới).
        """
        with self.assertRaises(AccessError):
            self.quotation.with_user(self.tech).read(["name"])

    def test_menu_quotation_excludes_technician_explicitly(self):
        """TC-INT-TestQuotationListDetailAccess-002: menu_dl_sale_quotation
        khai "-dl_base.dl_group_tech" tường minh trong groups= (không chỉ
        thiếu, mà LOẠI TRỪ chủ đích) — Kỹ thuật không thấy menu "Báo giá"
        trong khi CEO/BA/Trưởng KD/Admin đều thấy.
        """
        self.assertFalse(_menu_visible(self.env, self.tech, "dl_sale.menu_dl_sale_quotation"))
        for user in (self.ceo, self.ba, self.sm, self.admin):
            self.assertTrue(_menu_visible(self.env, user, "dl_sale.menu_dl_sale_quotation"))

    def test_ceo_has_full_crud_on_quotation(self):
        """TC-INT-TestQuotationListDetailAccess-003: CEO có FULL CRUD trên
        dl.quotation (access_dl_quotation_ceo 1,1,1,1) — TRÁI NGƯỢC với
        dl.quotation.request nơi CEO chỉ đọc (1,0,0,0). Không có quy tắc
        chung "CEO luôn chỉ xem" xuyên suốt hệ thống, phải tra đúng ACL từng
        model.
        """
        quo = self.env["dl.quotation"].with_user(self.ceo).create({
            "partner_id": self.customer.id})
        quo.with_user(self.ceo).write({"note": "CEO sửa"})
        quo.with_user(self.ceo).unlink()
        self.assertFalse(quo.exists())

    def test_sales_manager_is_read_only_on_quotation(self):
        """TC-INT-TestQuotationListDetailAccess-004: Trưởng KD chỉ ĐỌC được
        dl.quotation (access_dl_quotation_sm 1,0,0,0) — ngược với dl.
        quotation.request nơi Trưởng KD ghi/tạo được đầy đủ. "Duyệt nội bộ"/
        "Gửi khách hàng" của Trưởng KD hoạt động được là nhờ action Python tự
        sudo() (xem action_approve trong dl_quotation.py), không phải quyền
        ghi trực tiếp qua ACL.
        """
        with self.assertRaises(AccessError):
            self.quotation.with_user(self.sm).write({"note": "Trưởng KD sửa"})
        with self.assertRaises(AccessError):
            self.env["dl.quotation"].with_user(self.sm).create({
                "partner_id": self.customer.id})
        # Đối chứng: chặn ghi không kéo theo chặn đọc.
        self.quotation.with_user(self.sm).read(["name"])

    def test_ba_can_write_and_create_but_not_unlink_quotation(self):
        """TC-INT-TestQuotationListDetailAccess-005: BA ghi/tạo được báo giá
        (access_dl_quotation_ba 1,1,1,0) nhưng không xoá hẳn.
        """
        quo = self.env["dl.quotation"].with_user(self.ba).create({
            "partner_id": self.customer.id})
        quo.with_user(self.ba).write({"note": "BA sửa"})
        with self.assertRaises(AccessError):
            quo.with_user(self.ba).unlink()


# ============================================================
# SCR-28 — Hiển thị cột chi phí theo vai trò (dl.quotation / dl.quotation.line)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale", "dl_security")
class TestQuotationCostFieldVisibility(TransactionCase):
    """FDS: "CEO sees cost columns for management only". Đọc đúng comment
    nguồn (_COST_GROUPS trong dl_quotation.py: "Trưởng KD, CEO, Admin") thì
    "management" = cả ba vai trò này, KHÔNG PHẢI chỉ CEO — test dưới đây canh
    đúng bộ ba đó bằng fields_get()+with_user(), giống test_cost_field_
    visibility_security.py (GB-06) đã làm cho dl.bom/dl.bom.line.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr28_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr28_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr28_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr28_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test cột chi phí báo giá", "partner_role": "customer",
            "mobile": "0900002801",
        })
        cls.quotation = cls.env["dl.quotation"].create({
            "partner_id": cls.customer.id,
        })
        cls.line = cls.env["dl.quotation.line"].create({
            "quotation_id": cls.quotation.id,
            "name": "Dòng test cột chi phí",
        })

    def test_ba_cannot_see_header_cost_fields(self):
        """TC-INT-TestQuotationCostFieldVisibility-001: BA gọi fields_get()
        trên các field chi phí ở HEADER báo giá, kỳ vọng không field nào
        được trả về.
        """
        visible = self.quotation.with_user(self.ba).fields_get(list(_COST_HEADER_FIELDS))
        self.assertEqual(visible, {}, "BA không được thấy field chi phí header báo giá")

    def test_sales_manager_can_see_header_cost_fields(self):
        """TC-INT-TestQuotationCostFieldVisibility-002: Trưởng KD được thấy
        đủ field chi phí ở header — đúng ý "management" trong _COST_GROUPS.
        """
        visible = self.quotation.with_user(self.sm).fields_get(list(_COST_HEADER_FIELDS))
        self.assertEqual(set(visible.keys()), set(_COST_HEADER_FIELDS))

    def test_ceo_and_admin_can_see_header_cost_fields(self):
        """TC-INT-TestQuotationCostFieldVisibility-003: CEO và Admin cũng
        thấy đủ field chi phí ở header (cùng nhóm _COST_GROUPS với Trưởng
        KD).
        """
        for user in (self.ceo, self.admin):
            visible = self.quotation.with_user(user).fields_get(list(_COST_HEADER_FIELDS))
            self.assertEqual(set(visible.keys()), set(_COST_HEADER_FIELDS))

    def test_ba_cannot_see_line_cost_fields(self):
        """TC-INT-TestQuotationCostFieldVisibility-004: BA gọi fields_get()
        trên field chi phí DÒNG báo giá (material_cost/operation_cost/
        adjustment_cost/total_cost), kỳ vọng không field nào được trả về —
        đối tượng khác dl.quotation.line của GB-06 (đó là dl.bom.line).
        """
        visible = self.line.with_user(self.ba).fields_get(list(_COST_LINE_FIELDS))
        self.assertEqual(visible, {}, "BA không được thấy field chi phí dòng báo giá")

    def test_sales_manager_can_see_line_cost_fields(self):
        """TC-INT-TestQuotationCostFieldVisibility-005: Trưởng KD thấy đủ
        field chi phí dòng báo giá.
        """
        visible = self.line.with_user(self.sm).fields_get(list(_COST_LINE_FIELDS))
        self.assertEqual(set(visible.keys()), set(_COST_LINE_FIELDS))


# ============================================================
# SCR-29/30 — Phê duyệt báo giá (dl.pricing.approval.request)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestQuoteApprovalScreenAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr2930_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr2930_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr2930_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr2930_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr2930_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test Phê duyệt báo giá", "partner_role": "customer",
            "mobile": "0900002901",
        })
        cls.quotation = cls.env["dl.quotation"].create({
            "partner_id": cls.customer.id,
        })
        cls.quote_request = cls.env["dl.pricing.approval.request"].create({
            "request_type": "quote_over_threshold",
            "reason": "Vượt ngưỡng giá trị (test)",
            "approval_level": "sales_manager",
            "res_model": "dl.quotation",
            "res_id": cls.quotation.id,
            "company_id": cls.env.company.id,
        })
        cls.config_request = cls.env["dl.pricing.approval.request"].create({
            "request_type": "profit_config",
            "reason": "Đổi cấu hình lợi nhuận (test)",
            "company_id": cls.env.company.id,
        })

    def test_action_domain_shows_only_quote_over_threshold(self):
        """TC-INT-TestQuoteApprovalScreenAccess-001: domain thật của
        action_dl_quote_approval chỉ lọc request_type='quote_over_threshold'
        — yêu cầu duyệt loại khác (profit_config, discount_config,
        quote_discount, quote_below_floor, matrix_config) dùng CHUNG model
        nhưng không lọt vào màn "Phê duyệt báo giá", đọc thẳng domain từ
        action.
        """
        domain = _domain_of(self.env, "dl_sale.action_dl_quote_approval")
        found = self.env["dl.pricing.approval.request"].search(
            domain + [("id", "in", [self.quote_request.id, self.config_request.id])]).ids
        self.assertIn(self.quote_request.id, found)
        self.assertNotIn(self.config_request.id, found)

    def test_ba_and_technician_can_read_but_not_resolve_any_request(self):
        """TC-INT-TestQuoteApprovalScreenAccess-002: BA/Kỹ thuật có ACL đọc
        (perm_read=1) NHƯNG không ghi được (perm_write=0) — không duyệt/từ
        chối được bất kỳ loại yêu cầu nào, kể cả loại quote_over_threshold
        hiện trên màn Phê duyệt báo giá lẫn loại cấu hình khác.
        """
        for user in (self.ba, self.tech):
            self.quote_request.with_user(user).read(["state"])
            with self.assertRaises(AccessError):
                self.quote_request.with_user(user).write({"reason": "sửa trái phép"})

    def test_menu_excludes_admin_despite_full_acl(self):
        """TC-INT-TestQuoteApprovalScreenAccess-003: menu_dl_sale_quote_
        approval chỉ khai CEO + Trưởng KD (+ nhóm động dl_group_op_quote_
        approve) — Admin KHÔNG có trong groups= dù ACL access_dl_pricing_
        appr_req_admin cấp FULL CRUD (1,1,1,1) trên model. Admin không thấy
        màn "Phê duyệt báo giá" dù có đủ quyền model — đúng chủ đích ("Admin
        là vai trò kỹ thuật, không duyệt báo giá") ghi trong menus.xml.
        """
        self.assertTrue(_menu_visible(self.env, self.ceo, "dl_sale.menu_dl_sale_quote_approval"))
        self.assertTrue(_menu_visible(self.env, self.sm, "dl_sale.menu_dl_sale_quote_approval"))
        self.assertFalse(_menu_visible(self.env, self.admin, "dl_sale.menu_dl_sale_quote_approval"))
        self.assertFalse(_menu_visible(self.env, self.ba, "dl_sale.menu_dl_sale_quote_approval"))
        self.assertFalse(_menu_visible(self.env, self.tech, "dl_sale.menu_dl_sale_quote_approval"))

    def test_ba_cannot_see_approval_cost_fields(self):
        """TC-INT-TestQuoteApprovalScreenAccess-004: field q_total_cost/
        q_gross_profit/... trên màn Chi tiết yêu cầu duyệt (SCR-30, dl_sale/
        models/pricing_approval_ext.py) cũng gắn groups=_COST_GROUPS ở cấp
        field Python — BA gọi fields_get() không thấy field nào trong nhóm
        này, giống hệt cơ chế ở form Báo giá gốc.
        """
        visible = self.quote_request.with_user(self.ba).fields_get(list(_COST_APPROVAL_FIELDS))
        self.assertEqual(visible, {}, "BA không được thấy field chi phí trên yêu cầu duyệt")

    def test_sales_manager_can_see_approval_cost_fields(self):
        """TC-INT-TestQuoteApprovalScreenAccess-005: Trưởng KD (người duyệt
        chính của màn này) thấy đủ field chi phí trên yêu cầu duyệt.
        """
        visible = self.quote_request.with_user(self.sm).fields_get(list(_COST_APPROVAL_FIELDS))
        self.assertEqual(set(visible.keys()), set(_COST_APPROVAL_FIELDS))

    def test_risk_summary_leaks_below_floor_signal_to_ba(self):
        """TC-INT-TestQuoteApprovalScreenAccess-006: SAI LỆCH thật so với ý
        đồ trong comment nguồn (pricing_approval_ext.py, dòng cạnh
        risk_summary: "cột này cũng gắn groups=_COST_GROUPS nên không lộ ra
        ngoài phạm vi được xem giá vốn") — field Python `risk_summary` thực
        tế KHÔNG có tham số groups= nào (chỉ view tree gắn groups= để ẩn
        CỘT, không chặn field). BA có ACL đọc (1,0,0,0) trên model vẫn gọi
        fields_get()/read() thẳng thấy được field này, và nếu báo giá dưới
        giá sàn thì đọc được cả chữ "Dưới giá sàn" — lộ tín hiệu giá vốn ra
        ngoài phạm vi Trưởng KD/CEO/Admin dù con số below_floor gốc vẫn được
        chắn đúng (q_below_floor có groups=_COST_GROUPS thật).
        """
        self.quotation.sudo().write({"below_floor": True})
        visible = self.quote_request.with_user(self.ba).fields_get(["risk_summary"])
        self.assertIn(
            "risk_summary", visible,
            "risk_summary không có groups= ở cấp field nên BA vẫn thấy được qua fields_get()")
        value = self.quote_request.with_user(self.ba).read(["risk_summary"])[0]["risk_summary"]
        self.assertIn("Dưới giá sàn", value or "",
                       "BA đọc được tín hiệu giá vốn qua risk_summary dù bị chắn ở view")


# ============================================================
# SCR-31/32 — Đơn bán hàng (dl.sale.order)
# ============================================================
@tagged("post_install", "-at_install", "dl_sale")
class TestSaleOrderScreenAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ceo = _user(cls.env, "dl_base.dl_group_ceo", "ceo_scr3132_test")
        cls.admin = _user(cls.env, "dl_base.dl_group_admin", "admin_scr3132_test")
        cls.ba = _user(cls.env, "dl_base.dl_group_ba", "ba_scr3132_test")
        cls.sm = _user(cls.env, "dl_base.dl_group_sales_manager", "sm_scr3132_test")
        cls.tech = _user(cls.env, "dl_base.dl_group_tech", "tech_scr3132_test")
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test màn Đơn bán hàng", "partner_role": "customer",
            "mobile": "0900003101",
        })
        cls.order = cls.env["dl.sale.order"].create({
            "partner_id": cls.customer.id,
        })

    def test_technician_can_read_but_not_write_sale_order(self):
        """TC-INT-TestSaleOrderScreenAccess-001: SAI LỆCH so với suy đoán ban
        đầu ("Kỹ thuật không có ACL nào cho dl.sale.order" — đúng nếu chỉ tra
        dl_sale/security/ir.model.access.csv) — thực tế dl_inventory (phụ
        thuộc bắc cầu qua dl_purchase) BỔ SUNG dòng access_dl_sale_order_tech
        (dl_inventory/security/ir.model.access.csv) cấp Kỹ thuật ĐỌC (1,0,0,0)
        trên dl.sale.order — không phải AccessError ngay từ bước đọc như các
        model khác (dl.quotation, dl.bom.../dl.drawing SM) mà bài test này
        ban đầu giả định theo lối suy diễn "không thấy dòng ACL trong file
        của module đang xét = không có quyền". Ghi/tạo/xoá vẫn AccessError
        (dòng ACL đó chỉ cấp perm_read=1).
        """
        self.order.with_user(self.tech).read(["name"])
        with self.assertRaises(AccessError):
            self.order.with_user(self.tech).write({"note": "Kỹ thuật sửa"})
        with self.assertRaises(AccessError):
            self.env["dl.sale.order"].with_user(self.tech).create({
                "partner_id": self.customer.id})

    def test_menu_order_excludes_technician(self):
        """TC-INT-TestSaleOrderScreenAccess-002: menu_dl_sale_order chỉ khai
        CEO/Admin/BA/Trưởng KD — Kỹ thuật không thấy mục "Đơn bán hàng" trên
        sidebar, MẶC DÙ ca 001 vừa xác nhận Kỹ thuật thực sự đọc được model
        (ACL của dl_inventory). Đây là ca "ẩn ở tầng menu, không phải ACL"
        đúng nghĩa — ngược lại ca 001 ban đầu tưởng là ACL chặn hoàn toàn.
        """
        for user in (self.ceo, self.admin, self.ba, self.sm):
            self.assertTrue(_menu_visible(self.env, user, "dl_sale.menu_dl_sale_order"))
        self.assertFalse(_menu_visible(self.env, self.tech, "dl_sale.menu_dl_sale_order"))

    def test_sales_manager_has_full_write_create_unlike_quotation_screen(self):
        """TC-INT-TestSaleOrderScreenAccess-003: KHÁC màn Báo giá (nơi Trưởng
        KD chỉ đọc), ở Đơn bán hàng Trưởng KD có ACL ghi/tạo đầy đủ
        (access_dl_sale_order_sm 1,1,1,0) — không có sự bất đối xứng CEO/
        Trưởng KD như ở dl.quotation.
        """
        order = self.env["dl.sale.order"].with_user(self.sm).create({
            "partner_id": self.customer.id})
        order.with_user(self.sm).write({"note": "Trưởng KD sửa"})
        with self.assertRaises(AccessError):
            order.with_user(self.sm).unlink()

    def test_ba_can_write_create_not_unlink(self):
        """TC-INT-TestSaleOrderScreenAccess-004: BA ghi/tạo được đơn bán
        hàng nhưng không xoá hẳn (access_dl_sale_order_ba 1,1,1,0).
        """
        order = self.env["dl.sale.order"].with_user(self.ba).create({
            "partner_id": self.customer.id})
        order.with_user(self.ba).write({"note": "BA sửa"})
        with self.assertRaises(AccessError):
            order.with_user(self.ba).unlink()

    def test_ceo_and_admin_full_crud(self):
        """TC-INT-TestSaleOrderScreenAccess-005: CEO và Admin có FULL CRUD
        trên dl.sale.order (access_dl_sale_order_ceo/admin đều 1,1,1,1).
        """
        for user in (self.ceo, self.admin):
            order = self.env["dl.sale.order"].with_user(user).create({
                "partner_id": self.customer.id})
            order.with_user(user).write({"note": "sửa bởi %s" % user.login})
            order.with_user(user).unlink()
            self.assertFalse(order.exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
