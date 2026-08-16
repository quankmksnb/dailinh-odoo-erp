# -*- coding: utf-8 -*-
"""Bảng 'Data Constraints & Conditions' — nhóm A, B, C.

Mỗi dòng: [Field / Action, Type, Validation / Rule]
Nguồn sự thật: _sql_constraints + @api.constrains + guard ở method hành động,
trích bằng .tmp_tds/survey_cons.py. Câu luật viết tiếng Anh; thông điệp người
dùng thật sự nhìn thấy được trích nguyên văn tiếng Việt trong ngoặc kép.
"""

DCC = {}

# ══════════════════════════════ NHÓM A ═══════════════════════════════════════

DCC["res_partner"] = [
    ["login (res_users)", "Format",
     "Odoo native. Regex [a-zA-Z0-9_] plus e-mail characters; enforced UNIQUE at DB level."],
    ["vat", "Format",
     "Vietnamese tax code: digits and '-' only, either 10 digits (0123456789) or 10-3 for a "
     "branch (0123456789-001). Rejected otherwise."],
    ["vat", "Uniqueness",
     "A tax code may not be reused by another customer UNLESS dlm_allow_dup_tax is ticked and a "
     "reason is recorded — the escape hatch exists because branches of one company legitimately "
     "share a tax code."],
    ["vat", "Conditional required",
     "Mandatory when partner_type = 'company'. A business customer without a tax code cannot be "
     "invoiced, so the record is refused."],
    ["email", "Format", "Must satisfy the standard e-mail pattern. Checked on the partner and "
     "again on every child contact (parent_id set)."],
    ["phone, mobile", "Format",
     "Vietnamese numbering: must start with 0 or +84 and hold 10–11 digits. Applied to the "
     "partner and to every child contact."],
    ["partner_type", "Conditional required",
     "Mandatory as soon as partner_role includes 'customer'. Suppliers are exempt."],
    ["partner_role", "Enum", "customer / supplier / both — see §3.3. Drives every ir.rule that "
     "separates the Customer screens from the Vendor screens."],
    ["dlm_customer_group", "Computed",
     "new / existing / loyal, derived from order history against a revenue threshold held in "
     "ir.config_parameter (default 150,000,000 ₫). Not free-text."],
    ["set_loyal_threshold()", "Action guard",
     "The loyalty threshold must be a non-negative number; anything else is refused."],
]

DCC["res_users"] = [
    ["login", "Uniqueness",
     "Odoo native. NOT NULL + UNIQUE — the login is the authentication key."],
    ["login, name", "Required",
     "dlm_create_user() refuses a blank full name or e-mail/login: “Họ tên và Email/Tên đăng "
     "nhập là bắt buộc.”"],
    ["login", "Uniqueness",
     "dlm_create_user() re-checks before insert and reports “Tên đăng nhập/email '…' đã tồn "
     "tại.” instead of letting the raw DB error surface."],
    ["dlm_set_active()", "Action guard",
     "A user may not deactivate the account they are currently logged in with — that would lock "
     "the operator out mid-session."],
    ["active", "Soft delete",
     "Accounts are archived (active = false), never deleted, so audit columns on historical "
     "records keep pointing at a real row."],
]

DCC["res_company"] = [
    ["currency_id", "Invariant",
     "_dlm_enforce_vnd() re-asserts VNĐ on every -u dl_base. It cannot be done with an XML "
     "<record> because both base.main_company and base.VND carry noupdate=\"True\", so a data "
     "record is skipped in update mode — while installing 'account' later resets the company "
     "currency to the chart's default (USD)."],
    ["currency_id", "Failure mode",
     "If accounting entries already exist Odoo refuses the currency change; the hook logs an "
     "error rather than aborting the whole upgrade. Left unfixed, every quotation dies at "
     "QTE-007 because supplier prices are in VNĐ while the engine's reference is USD (P0 "
     "deliberately performs no currency conversion)."],
]

DCC["res_country"] = [
    ["code", "Uniqueness", "Odoo native — ISO 3166-1 alpha-2, UNIQUE."],
    ["get_formview_action()", "Navigation only",
     "Overridden to open the saved DLM action so F5 and deep links keep the new UI. No priority "
     "is set, so the stock Odoo form stays the system-wide default — behaviour is unchanged."],
]

DCC["dl_rbac_feature"] = [
    ["code", "Uniqueness",
     "DB-level: UNIQUE(code) — “Mã chức năng phải là duy nhất.” The code is the lookup key used "
     "by the permission matrix."],
    ["category", "Enum required",
     "master / sales / approval / system, default 'system'. See §3.3."],
    ["model_id", "Optional FK",
     "May be empty for action-only screens that have no backing model; when empty, only special "
     "operations can be configured — CRUD toggles are refused."],
    ["set_crud()", "Action guard",
     "Refuses to configure View/Create/Edit/Delete on a feature whose model_id is empty."],
    ["create_role()", "Action guard",
     "Role name may not be blank and may not duplicate an existing role name."],
    ["delete_role()", "Action guard",
     "System roles cannot be deleted — only roles created by an administrator."],
]

DCC["dl_rbac_operation"] = [
    ["feature_id", "Referential",
     "NOT NULL, ON DELETE CASCADE — an operation cannot outlive the feature it qualifies."],
    ["code", "Uniqueness",
     "Unique within one feature: the pair (feature_id, code) identifies a special operation such "
     "as 'approve' or 'export'."],
    ["—", "Design note",
     "Quyền theo product_kind KHÔNG đặt được ở tầng ACL vì bốn loại mặt hàng dùng chung "
     "product.product; việc đó phải làm bằng ir.rule — xem §4."],
]

# ══════════════════════════════ NHÓM B ═══════════════════════════════════════

DCC["product_product"] = [
    ["default_code", "Format",
     "Regex ^[A-Z0-9\\-]+$ — upper-case letters, digits and hyphen only (CT-200, VT-001). "
     "Lower case is refused rather than silently up-cased."],
    ["default_code", "Uniqueness",
     "Rejected if the code already belongs to another product; the offending product is named "
     "in the message so the user can go and look."],
    ["default_code", "Auto-generated",
     "Not typed by hand: an ir.sequence per product_kind supplies the prefix — GC- gia công, "
     "TM- thương mại, VT- vật tư, BTP- bán thành phẩm."],
    ["categ_id, product_kind", "Cross-field",
     "The category branch must match the product kind: a 'finished' branch category cannot hold "
     "a material, and vice versa. Enforced both ways (see product_category below)."],
    ["name, product_kind", "Uniqueness",
     "Two active products of the same kind may not share a name — the message points at the "
     "existing product and asks the user to reuse it instead of creating a twin. Provisional RFQ "
     "products (is_rfq_provisional) are excluded from the check."],
    ["product_kind", "Enum required",
     "manufactured / trading / material / material_processed, default 'manufactured'. This is "
     "the discriminator that replaces the old separate tables."],
    ["dlm_lifecycle_state", "State machine",
     "draft → active → obsolete, default 'active'. A product marked obsolete cannot receive a "
     "new BOM (see dl_bom)."],
    ["action_lifecycle_activate()", "Action guard",
     "A provisional product created inside an RFQ can only be promoted to a real product when "
     "Engineering presses “Hoàn tất dòng” in the RFQ workspace — not directly from the product form."],
    ["_dlm_check_trading_activation()", "Action guard",
     "A trading product cannot be activated until its prerequisites are complete; the missing "
     "items are listed back to the user."],
]

DCC["product_template"] = [
    ["product_tmpl_id", "Delegation",
     "Odoo native _inherits. Every product_product row must reference exactly one "
     "product_template row; the ORM creates and deletes the template row automatically."],
    ["type", "Invariant",
     "Fixed at 'product' (storable) so Inventory tracks stock. The value comes from the stock "
     "module via selection_add, which is why dl_product must declare depends: ['stock'] even "
     "before any warehouse UI exists."],
    ["uom_id", "Required", "NOT NULL — every item must carry a unit of measure."],
]

DCC["product_category"] = [
    ["dl_branch", "Enum", "finished / material / other — see §3.3."],
    ["parent_id", "Cross-field",
     "A category cannot be moved to a branch that contradicts the products it already holds; the "
     "conflicting product is named in the message."],
    ["active", "Archive guard",
     "A category cannot be archived while active products still belong to it or to any of its "
     "children. The user is told how many and asked to move or discontinue them first."],
    ["bom_template_id", "Referential",
     "The default template BOM must belong to this very category, and must already be Confirmed "
     "or Locked — an unapproved draft cannot become a category default."],
    ["parent_id", "Structural",
     "Odoo native parent_path materialised tree; a cycle is refused by the ORM."],
]

DCC["product_supplierinfo"] = [
    ["price", "Range", "Must be strictly greater than 0."],
    ["date_start, date_end", "Date order",
     "The end date must be on or after the start date."],
    ["approval_state", "State machine",
     "draft → approved, default 'draft'. Only Accounting/Purchasing may approve."],
    ["is_applied", "Cross-field",
     "Only an APPROVED price list may be flagged as currently applied, and only while it is "
     "inside its validity window."],
    ["is_applied", "Uniqueness",
     "At most one applied price list per material at any time. Applying a second one is refused "
     "and names the price list that must be un-applied first."],
    ["currency_id", "Invariant",
     "A price list may only be applied if its currency equals the company currency (VNĐ). P0 "
     "performs no currency conversion, so a foreign-currency price would corrupt the costing."],
    ["_check_price_manager()", "Access guard",
     "Only Purchasing or Admin may operate on supplier prices."],
    ["action_set_applied()", "Action guard",
     "Refused unless the price list is approved and currently inside its validity window."],
]

DCC["uom_uom"] = [
    ["category_id", "Referential",
     "Odoo native. Conversion is only possible between units of the SAME category; the pricing "
     "engine relies on this to refuse incompatible measures (QTE-007)."],
    ["factor", "Range", "Odoo native — must be non-zero; defines conversion to the reference unit."],
]

DCC["dl_measurement_type"] = [
    ["code", "Uniqueness", "Lookup key of the physical quantity (mass, area, perimeter, volume, length)."],
    ["—", "Seed-only",
     "Bảng danh mục tĩnh, nạp bằng data XML và không có màn hình thêm/sửa cho người dùng cuối."],
]

DCC["dl_measurement_shape"] = [
    ["measurement_type_id", "Referential",
     "NOT NULL — every shape belongs to exactly one measurement type."],
    ["—", "Seed-only",
     "Hình dạng được nạp cố định qua data/measurement_shape_data.xml; người dùng không tạo thêm "
     "hình dạng mới vì mỗi hình gắn với một công thức tính đã lập trình sẵn."],
]

DCC["dl_measurement_shape_param"] = [
    ["shape_id", "Referential", "NOT NULL, ON DELETE CASCADE — parameters die with their shape."],
    ["code", "Uniqueness", "Unique within one shape; used as the variable name in the formula."],
    ["—", "Seed-only", "Nạp cùng bảng hình dạng, xem trên."],
]

# ══════════════════════════════ NHÓM C ═══════════════════════════════════════

DCC["dl_drawing"] = [
    ["drawing_code", "Uniqueness",
     "DB-level: UNIQUE(drawing_code) — “Mã bản vẽ đã tồn tại.”"],
    ["product_id, version", "Uniqueness",
     "DB-level: UNIQUE(product_id, version) — one drawing per product per version."],
    ["product_id", "Validation",
     "Only a manufactured or semi-finished product may carry a technical drawing; attaching one "
     "to a trading product or raw material is refused."],
    ["status", "State machine", "draft → confirmed → archived. See §3.3."],
    ["action_confirm()", "Action guard",
     "Only a draft may be confirmed, and a drawing file must already be attached."],
    ["action_archive()", "Action guard", "A drawing still in draft cannot be archived."],
    ["action_reset_draft()", "Action guard", "Only a confirmed drawing may be sent back to draft."],
]

DCC["dl.bom.header.mixin"] = [
    ["status", "State machine",
     "draft → confirmed → locked → archived, default 'draft'. Shared by dl_bom and "
     "dl_bom_template so both follow the same lifecycle."],
    ["version", "Uniqueness",
     "Not unique by itself — it participates in the composite unique key of each concrete table "
     "(see dl_bom and dl_bom_template)."],
    ["—", "Mixin note",
     "AbstractModel: KHÔNG sinh bảng. Các cột dưới đây tồn tại vật lý trên MỌI bảng kế thừa, "
     "nên ràng buộc ở đây áp dụng cho cả dl_bom lẫn dl_bom_template."],
]

DCC["dl_bom"] = [
    ["product_id, version, bom_type", "Uniqueness",
     "DB-level: UNIQUE(product_id, version, bom_type) — “Phiên bản BOM của sản phẩm đã tồn tại.”"],
    ["product_qty", "Range", "Output quantity must be strictly greater than 0."],
    ["product_id", "Validation",
     "A BOM cannot be created for a product whose lifecycle state is 'obsolete'."],
    ["bom_type", "Enum required", "template / quotation, default 'template'. See §3.3."],
    ["_dlm_check_drawing_policy()", "Action guard",
     "Workshop policy: a finished product must have a CONFIRMED drawing before its BOM can be "
     "confirmed."],
    ["_dlm_check_material_spec()", "Action guard",
     "Confirmation is refused while any component still lacks the specification needed to "
     "compute its quantity; the offending materials are listed."],
    ["_check_can_reset_draft()", "Action guard",
     "A BOM already consumed by a sales order can be neither edited nor reset to draft — the "
     "user must create a new version instead. This is what makes a quoted price reproducible."],
    ["action_lock() / action_archive()", "Action guard",
     "A provisional BOM belonging to an open RFQ cannot be locked or archived until the source "
     "RFQ line is completed or abandoned."],
    ["action_create_from_template()", "Action guard",
     "Only a draft BOM may be filled from a template, and the product must already have a category."],
]

DCC["dl.bom.line.mixin"] = [
    ["quantity", "Range", "Must be strictly greater than 0."],
    ["piece_count", "Range", "Must be greater than or equal to 1."],
    ["—", "Mixin note",
     "Dùng chung cho dl_bom_line và dl_bom_template_line — hai bảng dòng vì thế có cùng bộ cột "
     "số liệu và cùng luật kiểm tra."],
]

DCC["dl_bom_line"] = [
    ["bom_id", "Referential", "NOT NULL, ON DELETE CASCADE — lines die with their BOM."],
    ["material_id, bom_id", "Cycle guard",
     "A semi-finished component may not (even indirectly) consume the product the BOM is for. "
     "The check walks the whole BOM graph, so an indirect loop A → B → C → A is caught too."],
    ["quantity, piece_count", "Range", "Inherited from dl.bom.line.mixin — see above."],
]

DCC["dl_bom_operation_line"] = [
    ["bom_id", "Referential", "NOT NULL, ON DELETE CASCADE, INDEX."],
    ["operation_id", "Referential",
     "NOT NULL, ON DELETE RESTRICT — an operation still referenced by a BOM cannot be deleted."],
    ["base_qty", "Range", "May not be negative."],
    ["is_outsourced, partner_id", "Cross-field",
     "Choosing a subcontractor implies the operation is outsourced: setting partner_id without "
     "ticking is_outsourced is refused."],
    ["material_scope", "Enum required", "all / selected, default 'all'. See §3.3."],
    ["method, estimated_unit_cost", "Not stored",
     "Computed without store=True on purpose — they must reflect the pricing rule in force TODAY. "
     "Storing them would freeze an old unit cost onto an old BOM and drift from the engine."],
]

DCC["dl_bom_template"] = [
    ["product_category_id, version", "Uniqueness",
     "DB-level: UNIQUE(product_category_id, version) — one template per category per version."],
    ["generic_product_id, product_category_id", "Cross-field",
     "The shared product must belong to the same category as the template."],
    ["status", "State machine", "Inherited from dl.bom.header.mixin — draft → confirmed → locked."],
    ["—", "Referential",
     "Chỉ mẫu đã Xác nhận/Khóa mới được gán làm BOM mẫu mặc định của một nhóm sản phẩm "
     "(kiểm ở product_category.bom_template_id)."],
]

DCC["dl_bom_template_line"] = [
    ["bom_template_id", "Referential", "NOT NULL, ON DELETE CASCADE."],
    ["quantity, piece_count", "Range", "Inherited from dl.bom.line.mixin — see above."],
    ["—", "Design note",
     "Dòng mẫu có thể trỏ tới một sản phẩm cụ thể HOẶC chỉ tới một nhóm sản phẩm; khi áp mẫu, "
     "kỹ thuật viên chọn vật tư thật cho các dòng chỉ định theo nhóm."],
]

DCC["dl_bom_template_param"] = [
    ["bom_template_id, code", "Uniqueness",
     "DB-level: UNIQUE(bom_template_id, code) — parameter codes are unique inside one template."],
    ["value_min, value_max", "Range",
     "The minimum may not exceed the maximum; the parameter code is named in the message."],
    ["code, name", "Required", "NOT NULL — both the formula symbol and the human label are mandatory."],
    ["required", "Default", "TRUE — the parameter must be supplied when the template is applied."],
    ["dim_role", "Enum", "length / width / height / thickness / side / none, default 'none'."],
]

DCC["dl_bom_template_line_param_map"] = [
    ["template_line_id", "Referential", "NOT NULL, ON DELETE CASCADE, INDEX."],
    ["param_id", "Referential", "NOT NULL, ON DELETE CASCADE."],
    ["param_id, template_line_id", "Cross-field",
     "The mapping must use a parameter belonging to the SAME template as the material line — a "
     "cross-template mapping is refused."],
    ["target_field", "Enum required",
     "dim_length / dim_width / piece_count / quantity. A closed list, not a free expression."],
    ["factor, offset", "Computation",
     "Giá trị ghi vào ô đích = param_value × factor + offset. Cố tình KHÔNG dùng công thức tự do "
     "để số liệu còn kiểm chứng được."],
]

DCC["dl_quotation_request"] = [
    ["name", "Uniqueness",
     "DB-level: UNIQUE(name) — “Mã yêu cầu báo giá đã tồn tại.” Generated by ir.sequence."],
    ["deadline, requested_date", "Date order",
     "The deadline may not fall before the date the request was received."],
    ["status", "State machine",
     "new → processing → returned → supplemented → confirmed → quoted / cancelled. See §3.3."],
    ["action_receive()", "Action guard",
     "Only an RFQ in 'Mới' or 'Đã bổ sung' may be picked up for processing."],
    ["action_cancel()", "Action guard",
     "An RFQ that already produced a quotation, or is already cancelled, cannot be cancelled."],
    ["action_resubmit()", "Action guard",
     "Refused if nothing was actually supplemented — the user is told to edit the lines waiting "
     "for input first."],
    ["action_mark_quoted()", "Action guard",
     "Only a fully processed RFQ may be marked as quoted, and it is refused when EVERY line was "
     "found infeasible — there would be nothing to quote."],
    ["action_create_quotation()", "Access guard",
     "Only Sales, Sales Manager or Admin may turn an RFQ into a quotation."],
]

DCC["dl_quotation_request_line"] = [
    ["quantity", "Range", "Must be strictly greater than 0."],
    ["product_type", "Enum required", "manufactured / trading, default 'manufactured'."],
    ["product_type, product_name, resolved_product_id", "Conditional required",
     "A trading line must point at an existing product; a manufactured line must carry a product "
     "name. The required field flips with product_type."],
    ["product_type, product_name", "Uniqueness",
     "Two manufactured lines in the SAME request may not carry the same product name."],
    ["resolved_product_id, is_infeasible", "Mutual exclusion",
     "A line cannot simultaneously resolve to a product and be marked infeasible."],
    ["is_infeasible, infeasible_reason", "Conditional required",
     "Marking a line infeasible requires a reason."],
    ["resolved_product_id", "Referential",
     "The resolved product must already own a BOM in state Confirmed or Locked — otherwise the "
     "line cannot be priced."],
    ["product_type, resolved_bom_id", "Cross-field",
     "A trading line must not reference a BOM; a manufactured line's BOM must belong to the "
     "resolved product and be Confirmed or Locked."],
    ["unlink()", "CRUD guard",
     "A line that already carries an engineering result cannot be deleted — the user must press "
     "“Loại khỏi phạm vi”, which records the removal and notifies Engineering."],
    ["action_remove_from_scope()", "Action guard",
     "Scope cannot be changed once the RFQ has produced a quotation or was cancelled."],
]

DCC["dl_quotation_request_line_image"] = [
    ["line_id", "Referential", "NOT NULL, ON DELETE CASCADE — images die with their RFQ line."],
    ["image", "Storage",
     "Ảnh lưu qua ir.attachment của Odoo (Binary attachment=True), không nhét nhị phân vào cột "
     "của bảng này — xem §7 về quy ước tệp."],
    ["—", "Volume note",
     "Không giới hạn số ảnh mỗi dòng ở tầng CSDL; giới hạn kích thước tệp áp ở tầng ứng dụng."],
]
