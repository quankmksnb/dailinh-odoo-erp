from psycopg2 import IntegrityError
from markupsafe import escape

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_round

# ---------------------------------------------------------------------------
# Mã lỗi nghiệp vụ (đặc tả §12 / §17.6). Giữ mã trong thông báo để hỗ trợ và
# đội test đối chiếu nhanh với tài liệu. Để plain string (không bọc _() ở cấp
# module — _() phải chạy trong ngữ cảnh có cursor).
# ---------------------------------------------------------------------------
QTE_001 = "QTE-001: Chỉ RFQ đã xử lý xong (Đã xác nhận) mới được tạo báo giá."
QTE_002 = "QTE-002: Sản phẩm gia công '%s' chưa có BOM đã xác nhận/khóa."
QTE_003 = (
    "QTE-003: Vật tư '%s' chưa có bảng giá đã duyệt, đang áp dụng và còn "
    "hiệu lực tại ngày tạo báo giá."
)
QTE_004 = "QTE-004: Không thể tính bán thành phẩm '%s' — kiểm tra BOM con hoặc vòng lặp."
QTE_005 = "QTE-005: Chưa có cấu hình lợi nhuận (markup) đang áp dụng tại ngày báo giá."
QTE_007 = "QTE-007: Không thể quy đổi định mức '%s' sang đơn vị/tiền tệ giá vật tư (P0 chưa hỗ trợ quy đổi)."
QTE_008 = "QTE-008: RFQ này đã có báo giá — hãy mở báo giá hiện có hoặc tạo revision."
QTE_009 = "QTE-009: Sản phẩm thương mại '%s' chưa có giá bán hợp lệ (Giá bán phải > 0)."
QTE_INFEASIBLE = (
    "Không thể tạo báo giá: mọi dòng của RFQ đều 'Không khả thi' — không có "
    "sản phẩm nào để báo giá. Trao đổi lại với khách hàng hoặc Hủy RFQ."
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

        # Dòng không khả thi bị loại khỏi báo giá (đã kiểm ở _validate_rfq là còn
        # dòng làm được). Giữ lại để ghi chú minh bạch cho Sales/khách.
        excluded = rfq.line_ids.filtered(lambda l: l.is_infeasible)
        quotable = rfq.line_ids - excluded

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
                for rfq_line in quotable:
                    self._create_quotation_line(quotation, rfq_line, context)
                # Chốt cấu hình thương mại + đánh giá phê duyệt (§7–§8).
                self._apply_commercial_and_approval(quotation, context)
                quotation.flush_recordset()
        except IntegrityError:
            raise UserError(QTE_008)

        # Đánh dấu rule đã dùng trong snapshot để không cho sửa (mixin bảo vệ).
        for rule in (context.get("profit_rule"), context.get("discount_rule")):
            if rule and not rule.used_in_snapshot:
                rule.sudo().write({"used_in_snapshot": True})

        # Ghi chú minh bạch khi có dòng không khả thi bị loại khỏi báo giá.
        if excluded:
            names = ", ".join(excluded.mapped("product_name"))
            note = _(
                "Báo giá bỏ %(n)s dòng 'Không khả thi': %(names)s.",
                n=len(excluded), names=names)
            quotation.message_post(body=note)
            rfq.message_post(body=note)

        # Chỉ chuyển RFQ sang 'quoted' sau khi báo giá + dòng đã tạo xong.
        rfq.sudo().write({"status": "quoted"})

        open_quotation = {
            "type": "ir.actions.act_window",
            "name": _("Báo giá"),
            "res_model": "dl.quotation",
            # Khai báo tường minh 'views' (không chỉ 'view_mode'): action này
            # được nhét vào params.next của display_notification nên KHÔNG đi qua
            # clean_action ở server — client sẽ gọi doAction thẳng, và
            # _preprocessAction làm action.views.map() → vỡ nếu thiếu 'views'.
            "views": [(False, "form")],
            "view_mode": "form",
            "res_id": quotation.id,
            "target": "current",
        }
        # Toast xác nhận + hướng dẫn bước tiếp theo, tùy báo giá có cần duyệt
        # không: dưới ngưỡng thì gửi khách ngay, vượt ngưỡng thì chờ phê duyệt.
        if quotation.approval_required:
            message = _(
                "Đã tạo báo giá %(name)s. Giá trị vượt ngưỡng — cần phê duyệt "
                "(%(level)s) trước khi gửi khách.",
                name=quotation.name, level=quotation.approval_level or "")
        else:
            message = _(
                "Đã tạo báo giá %(name)s — sẵn sàng gửi khách hàng ngay.",
                name=quotation.name)
        if excluded:
            message += _(" (Đã bỏ %(n)s dòng không khả thi.)", n=len(excluded))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Tạo báo giá thành công"),
                "message": message,
                "next": open_quotation,
            },
        }

    # ------------------------------------------------------------------
    # Ngữ cảnh & kiểm tra
    # ------------------------------------------------------------------
    def _build_context(self, rfq):
        """Chốt company/currency/pricing_date và tải các cấu hình đang hiệu lực
        đúng công ty/ngày (§17.5): lợi nhuận (markup/giá sàn), chiết khấu theo
        nhóm khách, VAT & làm tròn. Các số này được snapshot vào báo giá."""
        company = self.env.company
        date = fields.Date.context_today(rfq)
        partner = rfq.customer_id

        profit_rule = self._active_profit_rule(company, date)
        discount_rule = self._active_discount_rule(company, date, partner)
        config = self.env["dl.pricing.config"].sudo().search([], limit=1)

        return {
            "company": company,
            "currency": company.currency_id,
            "pricing_date": date,
            "partner": partner,
            "profit_rule": profit_rule,
            "discount_rule": discount_rule,
            # discount_pct tự điền theo nhóm khách; vat/rounding từ cấu hình S02.
            "discount_pct": discount_rule.default_rate if discount_rule else 0.0,
            "vat_pct": config.vat_pct if config else 0.0,
            "rounding_to": config.rounding_to if config else 0,
        }

    def _active_rule_domain(self, company, date):
        """Domain lấy quy tắc đang áp dụng, đúng công ty và còn hiệu lực tại ngày."""
        return [
            ("state", "=", "active"),
            ("company_id", "=", company.id),
            ("valid_from", "<=", date),
            "|", ("valid_to", "=", False), ("valid_to", ">=", date),
        ]

    def _active_profit_rule(self, company, date):
        return self.env["dl.pricing.profit.rule"].sudo().search(
            self._active_rule_domain(company, date),
            order="valid_from desc, revision desc", limit=1)

    def _active_discount_rule(self, company, date, partner):
        group = partner.dlm_customer_group
        Discount = self.env["dl.pricing.discount.rule"].sudo()
        if not group:
            return Discount.browse()
        return Discount.search(
            self._active_rule_domain(company, date) + [("customer_group", "=", group)],
            order="valid_from desc, revision desc", limit=1)

    @staticmethod
    def _round_price(value, rounding_to):
        """Làm tròn giá bán mục tiêu tới bội số ``rounding_to`` (đ), ROUND_HALF_UP
        (§7.4). rounding_to = 0 ⇒ không làm tròn."""
        if not rounding_to or rounding_to <= 0:
            return value
        return float_round(value, precision_rounding=float(rounding_to),
                           rounding_method="HALF-UP")

    def _validate_rfq(self, rfq, context):
        if rfq.status != "confirmed":
            raise UserError(QTE_001)

        # Chặn tạo trùng chỉ khi RFQ còn báo giá ĐANG HIỆU LỰC. Báo giá đã đóng
        # (từ chối / hết hiệu lực / đã thay bản mới / đã hủy) không chặn — cho
        # phép báo giá lại từ RFQ (vd đổi vật liệu → BOM mới → báo giá mới).
        closed = list(self.env["dl.quotation"]._CLOSED_STATES)
        existing = self.env["dl.quotation"].sudo().search(
            [
                ("quotation_request_id", "=", rfq.id),
                ("state", "not in", closed),
            ],
            limit=1,
        )
        if existing:
            raise UserError(QTE_008)

        if not rfq.line_ids:
            raise UserError(_("RFQ chưa có dòng sản phẩm nào để báo giá."))

        # Dòng "Không khả thi" được TỰ LOẠI khỏi báo giá (không chặn cả RFQ):
        # báo giá đúng các dòng làm được, các dòng không khả thi vẫn nằm trên RFQ
        # làm bằng chứng "không nhận". Chỉ chặn khi KHÔNG còn dòng nào để báo giá.
        quotable = rfq.line_ids.filtered(lambda l: not l.is_infeasible)
        if not quotable:
            raise UserError(QTE_INFEASIBLE)

        for line in quotable:
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

        profit_rule = context["profit_rule"]
        if not profit_rule:
            raise UserError(QTE_005)

        # P1: chưa có công đoạn/điều chỉnh chi phí → giá thành = chi phí vật tư.
        # F/G/H (§6.1): giá mục tiêu = giá thành × (1 + markup); giá sàn = ×(1 +
        # min_markup); làm tròn giá bán trước chiết khấu.
        total_cost = unit_cost
        target_markup = profit_rule.target_markup
        min_markup = profit_rule.min_markup
        target_price = total_cost * (1 + target_markup / 100.0)
        price_unit = self._round_price(target_price, context["rounding_to"])
        floor_price = total_cost * (1 + min_markup / 100.0)

        vals = {
            "name": rfq_line.resolved_product_id.display_name or rfq_line.product_name,
            "line_type": "manufactured",
            "product_id": rfq_line.resolved_product_id.id,
            "bom_id": bom.id,
            # Dấu vết BOM tại thời điểm tạo báo giá (§5.2) — stamp scalar, không
            # related sống về bom.version.
            "bom_version": bom.version,
            "bom_approved_by": bom.approved_by.id,
            "bom_confirmed_date": bom.approved_date,
            "material_cost": unit_cost,
            "total_cost": total_cost,
            "base_price": target_price,
            "price_unit": price_unit,
            "floor_price": floor_price,
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
        # Cấu phần markup: giải trình phần lợi nhuận cộng thêm trên giá thành.
        comp_specs.append({
            "component_type": "markup",
            "source_model": "dl.pricing.profit.rule",
            "source_id": profit_rule.id,
            "source_revision": profit_rule.revision,
            "qty": qty,
            "unit_price": total_cost,          # cơ sở/đơn vị
            "rate": target_markup,
            "amount": (price_unit - total_cost) * qty,
        })
        return vals, comp_specs

    def _resolve_child_bom(self, material):
        """BOM dùng làm GIÁ VỐN CHUẨN của một bán thành phẩm.

        Trước đây chỉ lấy ``version desc`` bất kể loại BOM ⇒ một BOM **báo giá**
        (sinh khi xử lý RFQ cho một đơn cụ thể) có số version cao hơn sẽ THẮNG
        BOM chuẩn của chính bán thành phẩm đó — nghĩa là định mức riêng của đơn
        A âm thầm trở thành giá vốn cho đơn B. Sai lệch chỉ hiện ra ở tiền nên
        rất khó phát hiện.

        Thứ tự đúng (thiết kế §17.2):
          1. BOM chuẩn (``template``) đang là phiên bản hiện hành;
          2. BOM chuẩn mới nhất còn hiệu lực;
          3. chỉ khi bán thành phẩm CHƯA TỪNG có BOM chuẩn mới đành dùng BOM
             báo giá mới nhất (trường hợp dữ liệu chưa hoàn chỉnh).
        """
        Bom = self.env["dl.bom"].sudo()
        base = [
            ("product_id", "=", material.id),
            ("status", "in", ("confirmed", "locked")),
        ]
        standard = [("bom_type", "=", "template")]
        return (
            Bom.search(base + standard + [("is_current", "=", True)], limit=1)
            or Bom.search(base + standard, order="version desc", limit=1)
            or Bom.search(base, order="version desc", limit=1)
        )

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
                child = self._resolve_child_bom(material)
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
                seller = self._active_material_seller(material, context)
                if not seller or seller.price <= 0:
                    raise UserError(QTE_003 % material.display_name)
                self._check_measure_compatibility(bl, material, seller, context)
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

            # Thu hồi phế liệu (§5.3) — chỉ vật tư thô, trừ vào chi phí vật tư.
            if spec_base["component_type"] == "material":
                recovery = bl._dlm_recovery_value()
                if recovery:
                    total_output_cost -= recovery
                    scrap = material.dlm_scrap_product_id
                    specs.append({
                        "component_type": "recovery",
                        "source_model": "product.product",
                        "source_id": scrap.id if scrap else 0,
                        "source_revision": 0,
                        "material_id": scrap.id if scrap else material.id,
                        "qty": (bl.effective_qty - bl.quantity)
                        * material.dlm_recovery_rate / 100.0,
                        "unit_price": material._dlm_scrap_unit_price(),
                        "amount": -recovery,
                    })

        unit_cost = total_output_cost / bom.product_qty
        # Quy specs về một đơn vị đầu ra.
        for spec in specs:
            spec["qty"] /= bom.product_qty
            spec["amount"] /= bom.product_qty
        return unit_cost, specs

    @staticmethod
    def _active_material_seller(material, context):
        """Giá được chọn phải đã duyệt, đang áp dụng và hiệu lực tại ngày tính giá."""
        pricing_date = context["pricing_date"]
        return material.seller_ids.filtered(
            lambda seller: seller.is_applied
            and seller.approval_state == "approved"
            and seller._is_valid_on(pricing_date)
        )[:1]

    def _check_measure_compatibility(self, bom_line, material, seller, context):
        """Decision C8: P0 chưa quy đổi UoM/tiền tệ — nếu không tương thích thì
        chặn cứng (QTE-007) thay vì nhân trực tiếp gây sai số âm thầm."""
        # Đơn vị mua khác đơn vị tính vật tư ⇒ giá NCC không cùng đơn vị định mức.
        if material.uom_id and material.uom_po_id and material.uom_id != material.uom_po_id:
            raise UserError(QTE_007 % material.display_name)
        if seller and seller.currency_id and seller.currency_id != context["currency"]:
            raise UserError(QTE_007 % material.display_name)

    # ------------------------------------------------------------------
    # Chiết khấu/VAT header + đánh giá phê duyệt (§7–§8)
    # ------------------------------------------------------------------
    def _apply_commercial_and_approval(self, quotation, context):
        profit = context.get("profit_rule")

        # Snapshot markup mục tiêu đã dùng (phục vụ giải trình + đánh giá lại);
        # snapshot chiết khấu do reevaluate_quotation ghi.
        quotation.write({
            "target_markup": profit.target_markup if profit else 0.0,
        })

        # Cấu phần header chiết khấu/VAT (giải trình từng lớp tiền).
        Component = self.env["dl.quotation.price.component"].sudo()
        if quotation.discount_pct:
            Component.create({
                "quotation_id": quotation.id,
                "component_type": "discount",
                "rate": quotation.discount_pct,
                "amount": -quotation.discount_amount,
            })
        if quotation.vat_pct:
            Component.create({
                "quotation_id": quotation.id,
                "component_type": "vat",
                "rate": quotation.vat_pct,
                "amount": quotation.vat_amount,
            })

        self.reevaluate_quotation(
            quotation,
            reason=_("Báo giá %s phát sinh điều kiện cần phê duyệt.") % quotation.name,
        )

    def reevaluate_quotation(self, quotation, reason=None):
        """Đánh giá (lại) điều kiện phê duyệt cho một báo giá (§8, mục 7).

        Dùng chung cho lúc TẠO báo giá và khi báo giá THAY ĐỔI dữ liệu ảnh hưởng
        giá (chiết khấu, dòng, khách hàng): hủy kết quả duyệt cũ (pending lẫn
        approved) rồi đánh giá lại theo đúng logic lúc tạo — rule chiết khấu
        hiệu lực tại ngày tính giá, ma trận giá trị, cờ giá sàn.

        sudo vì người sửa (Sales) không có quyền trên các field chi phí
        (groups=) và model yêu cầu phê duyệt.
        """
        quotation.ensure_one()
        quotation = quotation.sudo()
        company = quotation.company_id or self.env.company
        date = quotation.pricing_date or fields.Date.context_today(quotation)
        discount = self._active_discount_rule(company, date, quotation.partner_id)

        # Cờ định tuyến phê duyệt.
        eps = 1e-6
        below = self._below_floor(quotation)
        above_default = bool(discount) and quotation.discount_pct > discount.default_rate + eps
        above_max = bool(discount) and quotation.discount_pct > discount.max_rate + eps

        evaluation = self.env["dl.pricing.approval.matrix"].sudo().evaluate_quotation(
            quotation.amount_before_vat,
            company=company,
            date=date,
            discount_above_default=above_default,
            discount_above_max=above_max,
            below_floor=below,
        )

        # Kết quả duyệt cũ hết giá trị khi dữ liệu giá đã đổi (mục 7) — hủy và
        # giữ lịch sử, không ghi đè.
        old_request = quotation.approval_request_id
        if old_request and old_request.state in ("pending", "approved"):
            old_request.action_cancel_on_change()

        quo_vals = {
            "discount_default_rate": discount.default_rate if discount else 0.0,
            "discount_max_rate": discount.max_rate if discount else 0.0,
            "below_floor": below,
            "discount_above_default": above_default,
            "discount_above_max": above_max,
            "approval_required": evaluation["required"],
            "approval_level": evaluation.get("level_label") or "",
            "approval_reasons": "\n".join(
                "• %s" % r for r in evaluation.get("reasons") or []),
        }
        if evaluation["required"]:
            reason = reason or _(
                "Báo giá %s thay đổi dữ liệu giá — đánh giá lại điều kiện phê duyệt."
            ) % quotation.name
            request = self.env["dl.pricing.approval.request"].sudo().open_quote_approval(
                quotation, evaluation, reason)
            quo_vals["approval_request_id"] = request.id
            quo_vals["approval_state"] = "pending"
        else:
            quo_vals["approval_request_id"] = False
            quo_vals["approval_state"] = "not_required"
        quotation.write(quo_vals)
        return evaluation

    def _below_floor(self, quotation):
        """Decision B5: phân bổ chiết khấu header về từng dòng gia công theo tỷ
        lệ thành tiền, so giá đơn vị sau chiết khấu với giá sàn của dòng."""
        untaxed = quotation.amount_untaxed
        disc_amount = quotation.discount_amount
        for line in quotation.line_ids:
            if line.line_type != "manufactured" or not line.qty or not line.floor_price:
                continue
            gross = line.qty * line.price_unit
            allocated = disc_amount * (gross / untaxed) if untaxed else 0.0
            net_unit = (gross - allocated) / line.qty
            if net_unit < line.floor_price:
                return True
        return False


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
    auto_quote_error = fields.Text(
        string="Lỗi tạo báo giá",
        readonly=True,
        copy=False,
        tracking=True,
    )
    auto_quote_failed_at = fields.Datetime(
        string="Thời điểm tạo báo giá lỗi",
        readonly=True,
        copy=False,
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

    def _attempt_create_quotation(self):
        """Tạo báo giá theo yêu cầu của Sales; trả về ``False`` khi lỗi nghiệp vụ."""
        result = False
        for rec in self:
            if rec.status != "confirmed" or rec.quotation_id:
                continue
            try:
                # Bao toàn bộ dịch vụ bằng savepoint để cả các cập nhật snapshot
                # sau khi tạo quote cũng được rollback nếu phát sinh UserError.
                with self.env.cr.savepoint():
                    result = self.env[
                        "dl.quotation.pricing.service"
                    ].create_from_rfq(rec)
            except UserError as error:
                message = str(error)
                old_message = rec.auto_quote_error
                rec.sudo().write({
                    "auto_quote_error": message,
                    "auto_quote_failed_at": fields.Datetime.now(),
                })
                if message != old_message:
                    rec.message_post(body=_(
                        "Sales chưa tạo được báo giá:<br/>%s"
                    ) % escape(message))
                continue

            rec.sudo().write({
                "auto_quote_error": False,
                "auto_quote_failed_at": False,
            })
            # quotation_id là field compute dựa trên search, không có dependency
            # trực tiếp. Làm mới cache để form/nút mở báo giá thấy liên kết ngay
            # trong cùng transaction vừa tạo.
            rec.invalidate_recordset(["quotation_id"])
        return result

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
        result = self._attempt_create_quotation()
        if result:
            return result
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "title": _("Chưa tạo được báo giá"),
                "message": self.auto_quote_error or _(
                    "Vui lòng kiểm tra dữ liệu giá và thử lại."),
                "sticky": True,
            },
        }

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

    def action_reopen_for_revision(self, note=None):
        """Mở lại RFQ đã 'Đã tạo báo giá' về 'Đang xử lý' để Kỹ thuật điều chỉnh
        BOM khi khách yêu cầu đổi vật liệu/kỹ thuật (gọi từ báo giá). sudo để
        Sales kích hoạt được — đây là chuyển tiếp luồng, không phải sửa nội dung
        yêu cầu."""
        for rec in self:
            if rec.status != "quoted":
                raise UserError(_(
                    "Chỉ mở lại RFQ đã tạo báo giá để điều chỉnh kỹ thuật."))
            rec.sudo().write({"status": "processing"})
            body = _("Mở lại RFQ để Kỹ thuật điều chỉnh BOM — khách yêu cầu đổi "
                     "vật liệu/kỹ thuật.")
            if note:
                body += "<br/>%s" % note
            rec.message_post(body=body)
        return True
