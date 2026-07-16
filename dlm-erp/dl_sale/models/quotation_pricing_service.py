from psycopg2 import IntegrityError

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

# ---------------------------------------------------------------------------
# Mã lỗi nghiệp vụ (đặc tả §12 / §17.6). Giữ mã trong thông báo để hỗ trợ và
# đội test đối chiếu nhanh với tài liệu. Để plain string (không bọc _() ở cấp
# module — _() phải chạy trong ngữ cảnh có cursor).
# ---------------------------------------------------------------------------
QTE_001 = "QTE-001: Chỉ RFQ đã xử lý xong (Đã xác nhận) mới được tạo báo giá."
QTE_002 = "QTE-002: Sản phẩm gia công '%s' chưa có BOM đã xác nhận/khóa."
QTE_003 = "QTE-003: Vật tư '%s' chưa có bảng giá đã duyệt và đang áp dụng."
QTE_004 = "QTE-004: Không thể tính bán thành phẩm '%s' — kiểm tra BOM con hoặc vòng lặp."
QTE_007 = "QTE-007: Không thể quy đổi định mức '%s' sang đơn vị/tiền tệ giá vật tư (P0 chưa hỗ trợ quy đổi)."
QTE_008 = "QTE-008: RFQ này đã có báo giá — hãy mở báo giá hiện có hoặc tạo revision."
QTE_009 = "QTE-009: Sản phẩm thương mại '%s' chưa có giá bán hợp lệ (Giá bán phải > 0)."
QTE_INFEASIBLE = (
    "Không thể tạo báo giá: RFQ còn dòng đánh dấu 'Không khả thi'. "
    "Sales cần xác nhận lại phạm vi trước khi tạo báo giá."
)


class DlQuotationPricingService(models.AbstractModel):
    """Dịch vụ tính giá & tạo báo giá từ RFQ (đặc tả §17.4/§17.5).

    Tách khỏi model action để kiểm thử độc lập và tái sử dụng khi tính lại báo
    giá ở phase sau. P0: chỉ tính giá nền (list_price thương mại + chi phí vật
    tư BOM/đơn vị) và chiết khấu/VAT header nhập tay. Chưa gồm công đoạn, điều
    chỉnh chi phí, markup (P1) — thiết kế snapshot đã chừa chỗ.
    """

    _name = "dl.quotation.pricing.service"
    _description = "Dịch vụ tính giá báo giá"

    # ------------------------------------------------------------------
    # Điều phối chính
    # ------------------------------------------------------------------
    def create_from_rfq(self, rfq):
        """Tạo đúng một báo giá draft từ một RFQ đã confirmed, trong một
        transaction. Bất kỳ lỗi nào cũng rollback: không để RFQ 'quoted' mà
        thiếu báo giá."""
        rfq.ensure_one()
        context = self._build_context(rfq)
        self._validate_rfq(rfq, context)

        # sudo cho phần ghi dữ liệu: người bấm là Sales (BA) có thể không có
        # quyền write các field chi phí (groups=) hay model price.component —
        # nhưng quyền TẠO báo giá đã được kiểm ở action_create_quotation.
        Quotation = self.env["dl.quotation"].sudo()

        # Chống trùng ở cấp DB (Decision C7): partial unique index bắt lỗi race
        # condition. Bọc savepoint + flush để IntegrityError bung ra ngay đây và
        # dịch thành lỗi thân thiện, thay vì vỡ ở lần commit ngoài cùng.
        try:
            with self.env.cr.savepoint():
                quotation = Quotation.create(self._prepare_header_vals(rfq, context))
                for rfq_line in rfq.line_ids:
                    self._create_quotation_line(quotation, rfq_line, context)
                quotation.flush_recordset()
        except IntegrityError:
            raise UserError(QTE_008)

        # Chỉ chuyển RFQ sang 'quoted' sau khi báo giá + dòng đã tạo xong.
        rfq.sudo().write({"status": "quoted"})

        return {
            "type": "ir.actions.act_window",
            "name": _("Báo giá"),
            "res_model": "dl.quotation",
            "view_mode": "form",
            "res_id": quotation.id,
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Ngữ cảnh & kiểm tra
    # ------------------------------------------------------------------
    def _build_context(self, rfq):
        """Chốt company/currency/pricing_date và các tỷ lệ header cho lần tính
        giá. P0: discount_pct/vat_pct nhập tay ở header (mặc định 0); P1 sẽ tự
        lấy từ discount rule theo nhóm khách."""
        company = self.env.company
        return {
            "company": company,
            "currency": company.currency_id,
            "pricing_date": fields.Date.context_today(rfq),
            "discount_pct": 0.0,
            "vat_pct": 0.0,
        }

    def _validate_rfq(self, rfq, context):
        if rfq.status != "confirmed":
            raise UserError(QTE_001)

        existing = self.env["dl.quotation"].sudo().search(
            [
                ("quotation_request_id", "=", rfq.id),
                ("state", "!=", "cancelled"),
            ],
            limit=1,
        )
        if existing:
            raise UserError(QTE_008)

        if any(line.is_infeasible for line in rfq.line_ids):
            raise UserError(QTE_INFEASIBLE)

        if not rfq.line_ids:
            raise UserError(_("RFQ chưa có dòng sản phẩm nào để báo giá."))

        for line in rfq.line_ids:
            self._validate_line(line, context)

    def _validate_line(self, rfq_line, context):
        if rfq_line.quantity <= 0:
            raise UserError(_("Số lượng dòng '%s' phải lớn hơn 0.")
                            % (rfq_line.product_name or rfq_line.display_name))

        if rfq_line.product_type == "trading":
            product = rfq_line.resolved_product_id
            if not product:
                raise UserError(_("Dòng thương mại '%s' chưa có sản phẩm xác định.")
                                % (rfq_line.product_name or "?"))
            if float_is_zero(product.list_price, precision_rounding=0.01) or product.list_price < 0:
                raise UserError(QTE_009 % product.display_name)
        else:
            bom = rfq_line.resolved_bom_id
            if not bom or bom.status not in ("confirmed", "locked"):
                raise UserError(QTE_002 % (
                    rfq_line.resolved_product_id.display_name
                    if rfq_line.resolved_product_id else rfq_line.product_name or "?"))
            if bom.product_qty <= 0 or not bom.line_ids:
                raise UserError(QTE_004 % bom.display_name)

    # ------------------------------------------------------------------
    # Chuẩn bị header & line
    # ------------------------------------------------------------------
    def _prepare_header_vals(self, rfq, context):
        return {
            "partner_id": rfq.customer_id.id,
            "quotation_request_id": rfq.id,
            "company_id": context["company"].id,
            "currency_id": context["currency"].id,
            "pricing_date": context["pricing_date"],
            "date_order": context["pricing_date"],
            "discount_pct": context["discount_pct"],
            "vat_pct": context["vat_pct"],
            "state": "draft",
        }

    def _create_quotation_line(self, quotation, rfq_line, context):
        if rfq_line.product_type == "trading":
            vals, comp_specs = self._price_trading(rfq_line, context)
        else:
            vals, comp_specs = self._price_manufactured(rfq_line, context)

        vals.update(
            quotation_id=quotation.id,
            rfq_line_id=rfq_line.id,
            qty=rfq_line.quantity,
        )
        line = self.env["dl.quotation.line"].sudo().create(vals)

        Component = self.env["dl.quotation.price.component"].sudo()
        for spec in comp_specs:
            spec.update(quotation_id=quotation.id, quotation_line_id=line.id)
            Component.create(spec)
        return line

    # ------------------------------------------------------------------
    # Tính giá dòng thương mại (Decision B4)
    # ------------------------------------------------------------------
    def _price_trading(self, rfq_line, context):
        product = rfq_line.resolved_product_id
        qty = rfq_line.quantity
        base_price = product.list_price  # snapshot list_price tại thời điểm tạo

        vals = {
            "name": product.display_name,
            "line_type": "trading",
            "product_id": product.id,
            "base_price": base_price,
            "price_unit": base_price,
            "total_cost": 0.0,      # hàng thương mại không đi qua cost engine
            "material_cost": 0.0,
            "floor_price": 0.0,
        }
        comp_specs = [{
            "component_type": "trading_base",
            "source_model": "product.product",
            "source_id": product.id,
            "source_revision": 0,
            "material_id": product.id,
            "qty": qty,
            "unit_price": base_price,
            "amount": qty * base_price,
        }]
        return vals, comp_specs

    # ------------------------------------------------------------------
    # Tính giá dòng gia công (Decision A2 + §5.2 chia product_qty)
    # ------------------------------------------------------------------
    def _price_manufactured(self, rfq_line, context):
        bom = rfq_line.resolved_bom_id
        qty = rfq_line.quantity
        unit_cost, unit_specs = self._bom_material_cost(bom, context, visited=frozenset())

        # P0: chưa có markup/công đoạn/điều chỉnh → giá bán nền = chi phí vật tư
        # trên một đơn vị. base_price/price_unit sẽ được P1 cộng markup.
        vals = {
            "name": rfq_line.resolved_product_id.display_name or rfq_line.product_name,
            "line_type": "manufactured",
            "product_id": rfq_line.resolved_product_id.id,
            "bom_id": bom.id,
            "material_cost": unit_cost,
            "total_cost": unit_cost,
            "base_price": unit_cost,
            "price_unit": unit_cost,
            "floor_price": 0.0,     # P1: total_cost × (1 + min_markup/100)
        }

        comp_specs = []
        for spec in unit_specs:
            # unit_specs tính cho MỘT đơn vị đầu ra — nhân số lượng RFQ để ra
            # cấu phần theo cả dòng.
            comp_specs.append({
                "component_type": spec["component_type"],
                "source_model": spec["source_model"],
                "source_id": spec["source_id"],
                "source_revision": spec["source_revision"],
                "material_id": spec["material_id"],
                "qty": spec["qty"] * qty,
                "unit_price": spec["unit_price"],
                "amount": spec["amount"] * qty,
            })
        return vals, comp_specs

    def _bom_material_cost(self, bom, context, visited):
        """Chi phí vật tư để sản xuất MỘT đơn vị đầu ra của ``bom``.

        Trả về (unit_cost, specs) với specs là danh sách cấu phần vật tư đã quy
        về một đơn vị đầu ra. Đệ quy cho bán thành phẩm và chia product_qty của
        BOM con (§5.2) — không dùng thẳng total_material_cost của BOM con.
        Phát hiện vòng lặp BOM (QTE-004).
        """
        if bom.id in visited:
            raise UserError(QTE_004 % bom.display_name)
        visited = visited | {bom.id}

        if bom.product_qty <= 0 or not bom.line_ids:
            raise UserError(QTE_004 % bom.display_name)

        specs = []
        total_output_cost = 0.0  # chi phí cho product_qty đơn vị đầu ra
        for bl in bom.line_ids:
            material = bl.material_id
            if not material:
                raise UserError(QTE_004 % bom.display_name)

            if material.product_kind == "material_processed":
                child = self.env["dl.bom"].sudo().search(
                    [
                        ("product_id", "=", material.id),
                        ("status", "in", ("confirmed", "locked")),
                    ],
                    order="version desc",
                    limit=1,
                )
                if not child:
                    raise UserError(QTE_004 % material.display_name)
                unit_price, _child_specs = self._bom_material_cost(child, context, visited)
                spec_base = {
                    "component_type": "processed_material",
                    "source_model": "dl.bom",
                    "source_id": child.id,
                    "source_revision": child.version,
                }
            else:
                self._check_measure_compatibility(bl, material, context)
                seller = material.seller_ids.filtered("is_applied")[:1]
                if not seller or seller.price <= 0:
                    raise UserError(QTE_003 % material.display_name)
                unit_price = seller.price
                spec_base = {
                    "component_type": "material",
                    "source_model": "product.supplierinfo",
                    "source_id": seller.id,
                    "source_revision": 0,
                }

            amount = bl.effective_qty * unit_price  # cho product_qty đầu ra
            total_output_cost += amount
            spec_base.update(
                material_id=material.id,
                qty=bl.effective_qty,
                unit_price=unit_price,
                amount=amount,
            )
            specs.append(spec_base)

        unit_cost = total_output_cost / bom.product_qty
        # Quy specs về một đơn vị đầu ra.
        for spec in specs:
            spec["qty"] /= bom.product_qty
            spec["amount"] /= bom.product_qty
        return unit_cost, specs

    def _check_measure_compatibility(self, bom_line, material, context):
        """Decision C8: P0 chưa quy đổi UoM/tiền tệ — nếu không tương thích thì
        chặn cứng (QTE-007) thay vì nhân trực tiếp gây sai số âm thầm."""
        seller = material.seller_ids.filtered("is_applied")[:1]
        # Đơn vị mua khác đơn vị tính vật tư ⇒ giá NCC không cùng đơn vị định mức.
        if material.uom_id and material.uom_po_id and material.uom_id != material.uom_po_id:
            raise UserError(QTE_007 % material.display_name)
        if seller and seller.currency_id and seller.currency_id != context["currency"]:
            raise UserError(QTE_007 % material.display_name)


class DlQuotationRequest(models.Model):
    """Bridge trong dl_sale (Decision §17.7): dl_sale depends dl_technical và
    kế thừa dl.quotation.request để thêm action tạo báo giá + link ngược. Model
    gốc RFQ (dl_technical) KHÔNG import ngược dl.quotation → tránh vòng phụ thuộc.
    """

    _inherit = "dl.quotation.request"

    # Link ngược để mở nhanh báo giá đã tạo. Không lưu (search-based) — chiều
    # sở hữu link nằm ở dl.quotation.quotation_request_id (Decision review #2).
    quotation_id = fields.Many2one(
        "dl.quotation",
        string="Báo giá",
        compute="_compute_quotation_id",
    )

    def _compute_quotation_id(self):
        Quotation = self.env["dl.quotation"].sudo()
        for rec in self:
            rec.quotation_id = Quotation.search(
                [
                    ("quotation_request_id", "=", rec.id),
                    ("state", "!=", "cancelled"),
                ],
                limit=1,
            )

    def action_create_quotation(self):
        """Nút 'Tạo báo giá' trên RFQ đã confirmed (§17.5)."""
        self.ensure_one()
        user = self.env.user
        if not self.env.su and not (
            user.has_group("dl_base.dl_group_ba")
            or user.has_group("dl_base.dl_group_sales_manager")
            or user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Sales, Trưởng KD hoặc Admin được tạo báo giá."))
        return self.env["dl.quotation.pricing.service"].create_from_rfq(self)

    def action_open_quotation(self):
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_("RFQ này chưa có báo giá."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "dl.quotation",
            "view_mode": "form",
            "res_id": self.quotation_id.id,
            "target": "current",
        }
