# -*- coding: utf-8 -*-
"""Nội dung §3 phần KHO (dl_inventory) cho Report 4.0_TDS.docx.

Số liệu lấy từ:
  - AST source dlm-erp/dl_inventory/models/*.py  (cột dlm_*)
  - information_schema của PostgreSQL 16 dbname=dlm_dev (cột [Native])
"""

# Header + độ rộng cột của bảng entity, khớp đúng các bảng đang có trong tài liệu
CH = ["Column", "Type", "PostgreSQL", "Constraints", "Notes"]
CW = [26, 17, 15, 20, 42]

GROUP_TITLE = "Inventory — Warehouse layout, Receiving, QC, Delivery, Scrap [dl_inventory]"

GROUP_LEAD = (
    "dl_inventory does not create any new storage table. It reuses Odoo's stock schema and "
    "adds 11 physical columns spread over 4 native tables, 2 columns on dl_sale_order, and one "
    "read-only SQL VIEW. Columns prefixed dlm_ are the ones added by this project; columns "
    "marked [Native] belong to Odoo 17 core and are listed only when they carry a foreign key "
    "or drive a business rule described in this document."
)

NOTE_NONSTORED = (
    "Not every ORM field becomes a column. A Selection/Float declared with compute= and without "
    "store=True is evaluated in memory on each read and has NO column in PostgreSQL. This "
    "distinction is applied strictly below — the ERD draws only real columns."
)

ENTITIES = [
    # ── 1 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_warehouse [Native]",
        desc=("Đại Linh operates a single physical plant, therefore the system keeps exactly ONE "
              "warehouse record — Odoo's built-in stock.warehouse0, renamed to code DL. Creating "
              "a second warehouse would turn every internal movement into an inter-warehouse "
              "transfer and break the 3-zone layout below."),
        meta="dl_inventory adds NO column here. It overrides get_rules_dict() only.",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL", "“Kho Đại Linh”"],
            ["code [Native]", "Char required", "VARCHAR(5)", "NOT NULL", "“DL” — prefix of every picking number"],
            ["view_location_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "Root location DL (usage = view)"],
            ["lot_stock_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "DL/NHAN/KHO — materials & trading goods"],
            ["wh_input_stock_loc_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "DL/NHAN/QC — goods awaiting inspection"],
            ["reception_steps [Native]", "Selection", "VARCHAR", "NOT NULL", "Set to two_steps: receive → inspect & put away"],
            ["company_id [Native]", "Many2one", "INTEGER", "FK → res_company, NOT NULL", "—"],
        ],
        extra=("get_rules_dict() is overridden so that leg 2 of the two-step reception route uses the "
               "dedicated “Kiểm & cất hàng” operation type instead of Odoo's generic internal transfer. "
               "Overriding at the rule-generation level (rather than patching stock_rule rows after "
               "install) keeps the configuration correct every time Odoo rebuilds the route."),
    ),
    # ── 2 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_location [Inherit]",
        desc=("The three “kho” the business talks about are three child locations of the single "
              "warehouse, seeded by dl_inventory: DL/NHAN (receiving), DL/XUONG (plant), DL/TP "
              "(finished goods). Seven internal locations in total."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL", "Zone / bin name"],
            ["complete_name [Native]", "Char computed", "VARCHAR", "stored", "e.g. DL/XUONG/PL"],
            ["location_id [Native]", "Many2one", "INTEGER", "FK → stock_location, ON DELETE CASCADE", "Parent location — self-referencing tree"],
            ["parent_path [Native]", "Char", "VARCHAR", "INDEX", "Materialised path (e.g. 1/4/9/). The scrap SQL VIEW matches the whole subtree with LIKE parent_path || '%' — see §3.1 dl_scrap_recovery_report"],
            ["usage [Native]", "Selection", "VARCHAR", "NOT NULL", "view / internal / supplier / customer / production / inventory"],
            ["warehouse_id [Native]", "Many2one computed", "INTEGER", "FK → stock_warehouse", "—"],
            ["scrap_location [Native]", "Boolean", "BOOL", "—", "Left FALSE on DL/XUONG/PL on purpose — scrap here is a sellable asset, not a write-off"],
            ["active [Native]", "Boolean", "BOOL", "DEFAULT TRUE", "Archive instead of delete"],
            ["company_id [Native]", "Many2one", "INTEGER", "FK → res_company", "—"],
            ["dlm_no_inventory", "Boolean", "BOOL", "DEFAULT FALSE",
             "Transit-zone flag, set by dl_inventory on DL/NHAN/QC and DL/NHAN/TRA. Manual "
             "inventory counting is refused on these locations server-side, not merely hidden "
             "from the screen: their stock is already referenced by an open inspection or "
             "vendor-return document, so a hand count would erase goods that a draft document "
             "still points at."],
        ],
        note=("Why the three zones are usage = 'internal', not 'view'",
              "Odoo's _compute_complete_name drops the parent prefix for 'view' locations, so a "
              "'view' zone would display “Khu nhập hàng/Chờ kiểm hàng” — losing the “DL/” prefix and "
              "becoming inconsistent with the other two zones. Only the warehouse root (created by "
              "Odoo, named DL) is 'view'."),
    ),
    # ── 3 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_picking_type [Native]",
        desc=("Eight operation types: 3 native ones renamed (NH receive / GH deliver / CK internal "
              "transfer) and 5 created by dl_inventory (KC inspect & put away, TR vendor return, "
              "BPL scrap sale, plus XSX / NTP seeded ahead for the future Manufacturing Order "
              "phase). The operation type is the discriminator that specialises stock_picking."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char translated", "JSONB", "NOT NULL", "Odoo 17 stores translations as JSONB"],
            ["sequence_code [Native]", "Char required", "VARCHAR", "NOT NULL", "NH / KC / CK / GH / TR / BPL / XSX / NTP — the key the code branches on"],
            ["code [Native]", "Selection required", "VARCHAR", "NOT NULL", "incoming / outgoing / internal"],
            ["warehouse_id [Native]", "Many2one", "INTEGER", "FK → stock_warehouse, ON DELETE CASCADE", "—"],
            ["sequence_id [Native]", "Many2one", "INTEGER", "FK → ir_sequence", "Produces the picking number DL/KC/00001"],
            ["default_location_src_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "—"],
            ["default_location_dest_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "—"],
            ["return_picking_type_id [Native]", "Many2one", "INTEGER", "FK → stock_picking_type", "Self-reference — reverse operation type"],
            ["use_create_lots [Native]", "Boolean", "BOOL", "—", "TRUE on NH: lot numbers are generated by Đại Linh, not copied from the vendor's document"],
            ["active [Native]", "Boolean", "BOOL", "DEFAULT TRUE", "—"],
        ],
        extra=("Do not hand-craft the sequence prefix. stock.picking.type.write() rewrites prefix from "
               "its own formula every time sequence_code is written, so a custom prefix such as "
               "“KC/2026/” is silently reverted."),
    ),
    # ── 4 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_picking [Inherit]",
        desc=("The warehouse document. One single table backs all six document kinds — receipt, "
              "inspection, internal transfer, delivery, vendor return, scrap sale — because they "
              "share exactly the same set of attributes. The discriminator is picking_type_id, "
              "i.e. specialisation is defined by a relationship rather than by a column."),
        meta="dl_inventory adds 4 physical columns; 10 further ORM fields are non-stored (see note).",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char", "VARCHAR", "—", "Document number, e.g. DL/KC/00001"],
            ["origin [Native]", "Char", "VARCHAR", "—", "Source document reference"],
            ["state [Native]", "Selection", "VARCHAR", "—", "draft / waiting / confirmed / assigned / done / cancel"],
            ["picking_type_id [Native]", "Many2one required", "INTEGER", "FK → stock_picking_type, NOT NULL, INDEX", "Determines the document kind"],
            ["partner_id [Native]", "Many2one", "INTEGER", "FK → res_partner", "Customer on delivery, vendor on receipt"],
            ["location_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL", "Source"],
            ["location_dest_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL", "Destination"],
            ["backorder_id [Native]", "Many2one", "INTEGER", "FK → stock_picking", "Self-reference — partial-delivery remainder"],
            ["group_id [Native]", "Many2one", "INTEGER", "FK → procurement_group", "Chains the 2 legs of the receipt route"],
            ["scheduled_date [Native]", "Datetime", "TIMESTAMP", "—", "—"],
            ["date_done [Native]", "Datetime", "TIMESTAMP", "—", "Set when the document is validated"],
            ["company_id [Native]", "Many2one", "INTEGER", "FK → res_company", "—"],
            ["dlm_origin_picking_id", "Many2one", "INTEGER", "FK → stock_picking, ON DELETE SET NULL, INDEX", "Vendor-return document → the inspection document it came from"],
            ["dlm_sale_order_id", "Many2one", "INTEGER", "FK → dl_sale_order, ON DELETE RESTRICT, INDEX", "Delivery document → sales order. RESTRICT: an order that has already shipped must not be deletable"],
            ["dlm_qty_rejected_total", "Float computed stored", "NUMERIC", "—", "Total rejected quantity; stored so the list view can sort and group on it"],
            ["dlm_qc_state", "Selection computed stored", "VARCHAR", "—", "none / pending / passed / has_reject — see §3.3"],
        ],
        note=("Fields WITHOUT a column (compute, no store=True)",
              "dlm_picking_kind, dlm_is_qc, dlm_return_count, dlm_qty_total, dlm_reject_summary, "
              "dlm_blocked, dlm_banner_level, dlm_banner_message, dlm_source_available_product_ids, "
              "dlm_orderable_product_ids. The last two are Many2many — because they are computed and "
              "not stored, Odoo does NOT create a relation table for them."),
    ),
    # ── 5 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_move [Inherit]",
        desc=("A line of a warehouse document: one product, one quantity, one source and one "
              "destination location. Also the table the scrap reconciliation VIEW reads, because "
              "it is the only one carrying a time dimension."),
        meta="dl_inventory adds 3 physical columns.",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL", "—"],
            ["product_id [Native]", "Many2one required", "INTEGER", "FK → product_product, NOT NULL, INDEX", "—"],
            ["product_uom [Native]", "Many2one required", "INTEGER", "FK → uom_uom, NOT NULL", "—"],
            ["product_uom_qty [Native]", "Float required", "NUMERIC", "NOT NULL", "Demand"],
            ["quantity [Native]", "Float", "NUMERIC", "—", "Quantity actually done"],
            ["picked [Native]", "Boolean", "BOOL", "—", "Odoo 17 replacement for the old “quantity_done”"],
            ["state [Native]", "Selection", "VARCHAR", "—", "draft / confirmed / assigned / done / cancel"],
            ["date [Native]", "Datetime required", "TIMESTAMP", "NOT NULL", "Period key of the scrap report (date_trunc('month', date))"],
            ["picking_id [Native]", "Many2one", "INTEGER", "FK → stock_picking, INDEX", "NULLABLE — inventory-adjustment moves have no parent document"],
            ["location_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL, INDEX", "—"],
            ["location_dest_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL, INDEX", "—"],
            ["is_inventory [Native]", "Boolean", "BOOL", "—", "TRUE = stock-count adjustment line"],
            ["company_id [Native]", "Many2one required", "INTEGER", "FK → res_company, NOT NULL, INDEX", "—"],
            ["dlm_qty_rejected", "Float", "NUMERIC", "DEFAULT 0.0", "Quantity failing inspection; moves to the “Chờ trả NCC” zone"],
            ["dlm_reject_reason", "Selection", "VARCHAR", "—", "defect / wrong_spec / wrong_item / other — see §3.3"],
            ["dlm_reject_note", "Char", "VARCHAR", "—", "Free-text detail of the rejection"],
        ],
        note=("picking_id is NULLABLE — and that is a modelling decision, not an oversight",
              "Odoo 17 _apply_inventory() creates stock_move rows with is_inventory = TRUE and NO "
              "parent picking. The relationship stock_picking → stock_move is therefore optional-to-many "
              "(0..1 : N), not one-to-many. Drawing it as mandatory is the single easiest mistake to "
              "make on the Inventory diagram."),
    ),
    # ── 6 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_move_line [Native]",
        desc=("Lot-level detail of a move. Carries the lot number when the product is lot-tracked. "
              "Used unchanged — dl_inventory adds no column."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["move_id [Native]", "Many2one", "INTEGER", "FK → stock_move, INDEX", "—"],
            ["picking_id [Native]", "Many2one", "INTEGER", "FK → stock_picking, INDEX", "—"],
            ["product_id [Native]", "Many2one", "INTEGER", "FK → product_product, ON DELETE CASCADE, INDEX", "—"],
            ["lot_id [Native]", "Many2one", "INTEGER", "FK → stock_lot", "The lot actually picked / received"],
            ["lot_name [Native]", "Char", "VARCHAR", "—", "Lot number typed on the document before the lot record exists"],
            ["quantity [Native]", "Float", "NUMERIC", "—", "—"],
            ["location_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL", "—"],
            ["location_dest_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, NOT NULL", "—"],
            ["company_id [Native]", "Many2one required", "INTEGER", "FK → res_company, NOT NULL, INDEX", "—"],
        ],
    ),
    # ── 7 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_quant [Native]",
        desc=("On-hand balance: quantity of one product, in one location, for one lot. Odoo "
              "maintains it automatically from validated moves — it is a snapshot, never written "
              "by hand except during a stock count."),
        meta=("dl_inventory declares 4 ORM fields here but adds ZERO columns — three are related= "
              "and one is compute=, none of them stored."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["product_id [Native]", "Many2one required", "INTEGER", "FK → product_product, ON DELETE RESTRICT, NOT NULL, INDEX", "—"],
            ["location_id [Native]", "Many2one required", "INTEGER", "FK → stock_location, ON DELETE RESTRICT, NOT NULL, INDEX", "—"],
            ["lot_id [Native]", "Many2one", "INTEGER", "FK → stock_lot, ON DELETE RESTRICT, INDEX", "—"],
            ["quantity [Native]", "Float", "NUMERIC", "—", "On hand"],
            ["reserved_quantity [Native]", "Float required", "NUMERIC", "NOT NULL", "Reserved for open documents"],
            ["inventory_quantity [Native]", "Float", "NUMERIC", "—", "Counted quantity (stock count)"],
            ["inventory_diff_quantity [Native]", "Float", "NUMERIC", "—", "Counted − on hand"],
            ["inventory_quantity_set [Native]", "Boolean", "BOOL", "—", "Distinguishes “counted 0” from “not counted”"],
            ["in_date [Native]", "Datetime required", "TIMESTAMP", "NOT NULL", "Entry date — drives FIFO removal"],
            ["company_id [Native]", "Many2one", "INTEGER", "FK → res_company", "—"],
        ],
        extra=("Non-stored ORM fields on this table: dlm_supplier_id (related lot_id.dlm_supplier_id), "
               "dlm_receipt_date (related lot_id.dlm_receipt_date), dlm_scrap_unit_price (related "
               "product_id.list_price), dlm_scrap_value (compute). They exist for the screens only."),
    ),
    # ── 8 ────────────────────────────────────────────────────────────────────
    dict(
        head="Table: stock_lot [Inherit]",
        desc=("A traceable batch. Lot numbers are generated by Đại Linh in the format LO/2026/00001 "
              "rather than copied from the vendor's paperwork, because vendor numbering has no "
              "consistent format, collides across vendors and is easy to mistype — and the lot is "
              "the link used to trace defective goods back to their supplier."),
        meta="dl_inventory adds 3 physical columns, 2 of them indexed.",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL", "Lot number LO/2026/00001"],
            ["ref [Native]", "Char", "VARCHAR", "—", "Vendor's own lot number, if any"],
            ["product_id [Native]", "Many2one required", "INTEGER", "FK → product_product, NOT NULL, INDEX", "—"],
            ["product_uom_id [Native]", "Many2one", "INTEGER", "FK → uom_uom", "—"],
            ["location_id [Native]", "Many2one", "INTEGER", "FK → stock_location", "—"],
            ["company_id [Native]", "Many2one required", "INTEGER", "FK → res_company, NOT NULL, INDEX", "—"],
            ["dlm_supplier_id", "Many2one readonly", "INTEGER", "FK → res_partner, ON DELETE SET NULL, INDEX", "Which vendor this lot came from — the traceability anchor"],
            ["dlm_receipt_date", "Date readonly", "DATE", "INDEX", "Receipt date; indexed because ageing reports filter on it"],
            ["dlm_receipt_picking_id", "Many2one readonly", "INTEGER", "FK → stock_picking, ON DELETE SET NULL", "The receipt document that created the lot"],
        ],
    ),
    # ── 9 ────────────────────────────────────────────────────────────────────
    dict(
        head="View: dl_scrap_recovery_report [SQL VIEW]",
        desc=("Monthly reconciliation of scrap: estimated at quotation time versus actually weighed "
              "in. This is the only feedback loop that tells the company whether the waste "
              "coefficient dlm_waste_rate — which goes straight into the price quoted to the "
              "customer — is set correctly."),
        meta=("_auto = False ⇒ this is a PostgreSQL VIEW, not a table. It has no PK sequence, no "
              "audit columns, and no INSERT/UPDATE path."),
        cols=[
            ["id", "Integer readonly", "INTEGER", "synthetic", "YEAR*100 + MONTH — deterministic surrogate key required by the ORM"],
            ["period", "Date readonly", "DATE", "—", "First day of the month, date_trunc('month', move.date)"],
            ["qty_in", "Float readonly", "NUMERIC", "—", "Scrap weighed INTO DL/XUONG/PL during the month"],
            ["qty_sold", "Float readonly", "NUMERIC", "—", "Scrap moved OUT of DL/XUONG/PL to a customer location"],
        ],
        note=("Three fields deliberately left OUT of the view",
              "qty_estimated, qty_diff and diff_level are computed in Python, not in SQL. The recovery "
              "formula lives on dl_bom_line (UoM → kg conversion via dlm_mass_per_unit, times the "
              "recovery ratio). Copying it into SQL would create a second copy of a formula that "
              "determines money — and the two copies would diverge at the first edit."),
        extra=("The view is a UNION of “months with scrap movement” and “months with sales orders”. "
               "Restricting it to months with movement would hide the most dangerous case of all — "
               "100 kg estimated, 0 kg weighed — because that month would produce no row at all. "
               "_depends is declared on stock.move, stock.location and dl.sale.order so that search() "
               "flushes the ORM cache before reading the view; without it, a just-validated document "
               "would be silently missing from the report."),
    ),
    # ── 10 ───────────────────────────────────────────────────────────────────
    dict(
        head="Table: dl_sale_order [extended by dl_inventory]",
        desc=("The sales order (defined in full earlier in this section) gains two stored columns "
              "so the delivery status can be filtered and grouped in the list view."),
        cols=[
            ["dlm_delivery_state", "Selection computed stored", "VARCHAR", "DEFAULT 'nothing'", "nothing / partial / done — see §3.3"],
            ["dlm_has_deliverable", "Boolean computed stored", "BOOL", "—", "FALSE when no line needs to ship through the warehouse, so the “Create delivery” button is hidden instead of failing on click"],
        ],
        extra=("dlm_picking_ids is a One2many (inverse of stock_picking.dlm_sale_order_id) and "
               "dlm_picking_count is a non-stored compute — neither creates a column. The link "
               "between a sales order and its delivery documents lives at ORDER level, not at line "
               "level."),
    ),
]
