from datetime import timedelta

from psycopg2 import IntegrityError
from markupsafe import Markup, escape

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, float_round

# ---------------------------------------------------------------------------
# Các câu báo lỗi bung ra hộp thoại đỏ khi Sales bấm "Tạo báo giá" trên RFQ —
# mỗi câu chỉ đúng một nguyên nhân để người dùng biết phải đi sửa ở đâu.
# Giữ mã QTE-xxx ở đầu câu cho dễ tra cứu khi hỗ trợ người dùng.
# Không bọc _() ở đây: _() phải chạy khi đã có cursor, cấp module thì chưa có.
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
QTE_010 = "QTE-010: Công đoạn '%s' cần định mức cơ sở > 0 (theo kg/mét/m²)."
QTE_011 = (
    "QTE-011: Công đoạn '%s' chưa có đơn giá đã áp dụng, còn hiệu lực tại ngày "
    "tạo báo giá."
)
QTE_INFEASIBLE = (
    "Không thể tạo báo giá: mọi dòng của RFQ đều 'Không khả thi' — không có "
    "sản phẩm nào để báo giá. Trao đổi lại với khách hàng hoặc Hủy RFQ."
)


class DlQuotationPricingService(models.AbstractModel):
    """Bộ máy tính tiền đứng sau nút "Tạo báo giá" của màn RFQ.

    Không có màn hình riêng — Sales bấm một nút trên RFQ, toàn bộ file này chạy
    và đẻ ra bản báo giá nháp với đầy đủ số.

    Cách ra giá một sản phẩm gia công:
        tiền vật tư theo BOM (BOM lồng BOM thì đệ quy xuống bán thành phẩm)
      + tiền công đoạn  (cắt/hàn/sơn theo đơn vị, cộng phí setup chia theo lô)
      + chi phí chung   (overhead, đóng gói, giao gấp, đơn nhỏ, dự phòng)
      = giá thành → nhân markup ra giá chào, đồng thời tính giá sàn rồi làm tròn.
    Chiết khấu và VAT ở đầu báo giá thì Sales tự nhập, không tính ở đây.

    Tách riêng khỏi model để test được độc lập, không cần dựng cả form.
    """

    _name = "dl.quotation.pricing.service"
    _description = "Dịch vụ tính giá báo giá"

    # ------------------------------------------------------------------
    # Điều phối chính
    # ------------------------------------------------------------------
    def create_from_rfq(self, rfq):
        """Cửa vào chính: từ 1 RFQ đã xác nhận đẻ ra 1 báo giá nháp.

        Chạy trọn trong một transaction — hỏng ở bất kỳ bước nào là rollback
        sạch, tránh cảnh RFQ đã đánh dấu "đã báo giá" mà báo giá thì không có.
        Trả về action mở luôn báo giá vừa tạo kèm toast hướng dẫn bước sau."""
        rfq.ensure_one()
        context = self._build_context(rfq)
        self._validate_rfq(rfq, context)

        # Dòng không khả thi bị loại khỏi báo giá (đã kiểm ở _validate_rfq là còn
        # dòng làm được). Giữ lại để ghi chú minh bạch cho Sales/khách.
        excluded = rfq.line_ids.filtered(lambda l: l.is_infeasible)
        quotable = rfq.line_ids - excluded

        # Chạy trước một lượt để biết đơn này to hay nhỏ — khoản phụ phí "Đơn
        # hàng nhỏ" cần con số đó mới quyết được có áp hay không.
        # Đo bằng chi phí trực tiếp chứ không bằng giá bán: lấy giá bán thì
        # phụ phí lại làm đổi giá bán, thành vòng lặp.
        # Tiện thể cache luôn chi phí từng dòng để khỏi duyệt BOM hai lần.
        direct_cache = {}
        order_value = 0.0
        for rfq_line in quotable:
            if rfq_line.product_type == "trading":
                order_value += rfq_line.quantity * (
                    rfq_line.resolved_product_id.list_price or 0.0)
            else:
                dc = self._manufactured_direct_cost(rfq_line, context)
                direct_cache[rfq_line.id] = dc
                order_value += rfq_line.quantity * (
                    dc["material_unit"] + dc["operation_cost"])
        context["order_value"] = order_value
        context["direct_cache"] = direct_cache

        # sudo vì người bấm nút là Sales, không có quyền ghi các field giá vốn.
        # Quyền được tạo báo giá hay không đã kiểm ở action_create_quotation.
        Quotation = self.env["dl.quotation"].sudo()

        # Hai người bấm "Tạo báo giá" cùng lúc thì khoá chống trùng ở DB sẽ nổ.
        # Bọc savepoint + flush để lỗi đó bung ra ĐÚNG chỗ này và dịch thành
        # câu tiếng Việt dễ hiểu, thay vì vỡ ở tận lần commit cuối request.
        try:
            with self.env.cr.savepoint():
                quotation = Quotation.create(self._prepare_header_vals(rfq, context))
                for rfq_line in quotable:
                    self._create_quotation_line(quotation, rfq_line, context)
                # Điền chiết khấu/VAT rồi xét xem báo giá có phải xin duyệt không.
                self._apply_commercial_and_approval(quotation, context)
                quotation.flush_recordset()
        except IntegrityError:
            raise UserError(QTE_008)

        # Đóng dấu "đã dùng để báo giá" lên rule — từ giờ màn Cấu hình báo giá
        # không cho sửa rule này nữa, sửa được thì số báo giá cũ sẽ sai.
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
            # ⚠️ Phải khai 'views' chứ không chỉ 'view_mode': action này nằm
            # trong toast nên không đi qua bước chuẩn hoá ở server, client gọi
            # thẳng và sẽ vỡ khi thiếu 'views'.
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
    # Gom dữ liệu đầu vào & kiểm tra trước khi tính
    # ------------------------------------------------------------------
    def _build_context(self, rfq):
        """Nạp một lần toàn bộ cấu hình sẽ dùng để tính, rồi chuyền tay qua các
        hàm bên dưới.

        Chốt ngày tính giá ngay từ đây và mọi rule đều tra theo ngày đó — báo
        giá hôm nay không được đổi số vì mai có người sửa bảng giá. Các con số
        này cũng được chép vào báo giá để sau còn giải trình."""
        company = self.env.company
        date = fields.Date.context_today(rfq)
        partner = rfq.customer_id

        profit_rule = self._active_profit_rule(company, date)
        discount_rule = self._active_discount_rule(company, date, partner)
        config = self.env["dl.pricing.config"].sudo().search([], limit=1)

        # Các khoản phụ phí đang bật + số ngày còn lại tới hạn giao (để biết có
        # tính phụ phí "Giao gấp" không). RFQ không đặt hạn ⇒ None ⇒ bỏ qua
        # khoản giao gấp.
        adjustment_rules = self.env[
            "dl.pricing.cost.adjustment.rule"].sudo()._get_active_rules(company, date)
        delivery_days = None
        if rfq.deadline:
            delivery_days = (rfq.deadline - date).days

        return {
            "company": company,
            "currency": company.currency_id,
            "pricing_date": date,
            "partner": partner,
            "profit_rule": profit_rule,
            "discount_rule": discount_rule,
            # Chiết khấu tự điền theo nhóm khách; VAT và mức làm tròn lấy từ
            # màn Cấu hình báo giá.
            "discount_pct": discount_rule.default_rate if discount_rule else 0.0,
            "vat_pct": config.vat_pct if config else 0.0,
            "rounding_to": config.rounding_to if config else 0,
            "adjustment_rules": adjustment_rules,
            "delivery_days": delivery_days,
            # order_value + direct_cache do create_from_rfq điền ở lượt chạy trước.
        }

    def _active_rule_domain(self, company, date):
        """Điều kiện chung để lọc rule: đã bật, đúng công ty, còn hiệu lực tại
        ngày tính giá."""
        return [
            ("state", "=", "active"),
            ("company_id", "=", company.id),
            ("valid_from", "<=", date),
            "|", ("valid_to", "=", False), ("valid_to", ">=", date),
        ]

    def _active_profit_rule(self, company, date):
        """Rule lợi nhuận đang áp dụng — cho markup mục tiêu và markup tối
        thiểu (giá sàn). Không có rule nào thì không tính giá được (QTE-005)."""
        return self.env["dl.pricing.profit.rule"].sudo().search(
            self._active_rule_domain(company, date),
            order="valid_from desc, revision desc", limit=1)

    def _active_discount_rule(self, company, date, partner):
        """Bảng chiết khấu áp cho khách này — quyết định mức mặc định và trần.

        🔴 Không bao giờ được trả về rỗng khi hệ thống có rule: rỗng thì cờ
        "vượt trần" luôn False, Sales gõ chiết khấu bao nhiêu cũng không phát
        sinh phê duyệt. Nên có 2 lớp đỡ:
          1. khách chưa phân nhóm → coi là "Khách mới" (nhóm chặt nhất);
          2. nhóm đó chưa có bảng chiết khấu → lấy tạm bảng có trần THẤP NHẤT
             trong số đang hiệu lực, thà chặt còn hơn thả nổi."""
        group = partner.dlm_customer_group or "new"
        Discount = self.env["dl.pricing.discount.rule"].sudo()
        base_domain = self._active_rule_domain(company, date)
        rule = Discount.search(
            base_domain + [("customer_group", "=", group)],
            order="valid_from desc, revision desc", limit=1)
        if rule:
            return rule
        # Nhóm này chưa có bảng riêng → dùng tạm bảng chặt nhất. Nếu cả hệ
        # thống chưa có bảng nào thì đúng là công ty chưa đặt chính sách chiết
        # khấu — lúc đó mặc định 0% và không có trần, đó là chủ ý.
        return Discount.search(
            base_domain, order="max_rate asc, valid_from desc, revision desc", limit=1)

    @staticmethod
    def _round_price(value, rounding_to):
        """Làm tròn giá chào lên bội số cấu hình (vd bội số 1.000đ) cho số đẹp
        khi gửi khách. Cấu hình = 0 thì để nguyên."""
        if not rounding_to or rounding_to <= 0:
            return value
        return float_round(value, precision_rounding=float(rounding_to),
                           rounding_method="HALF-UP")

    @staticmethod
    def _ceil_price(value, rounding_to):
        """Làm tròn LÊN bội số cấu hình — dùng khi phải bảo đảm không tụt dưới sàn."""
        if not rounding_to or rounding_to <= 0:
            return value
        return float_round(value, precision_rounding=float(rounding_to),
                           rounding_method="UP")

    def _validate_rfq(self, rfq, context):
        """Soát RFQ trước khi tính: đủ điều kiện thì mới chạy, thiếu gì thì báo
        lỗi nêu đích danh chỗ phải sửa."""
        if rfq.status != "confirmed":
            raise UserError(QTE_001)

        # Chỉ chặn khi RFQ còn báo giá ĐANG SỐNG. Báo giá đã đóng thì cho báo
        # lại từ đầu — ví dụ khách chê vật liệu, Kỹ thuật sửa BOM, báo giá mới.
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

        # Dòng Kỹ thuật đánh "Không khả thi" thì tự bỏ ra khỏi báo giá chứ
        # không chặn cả RFQ — báo giá phần làm được, phần không nhận vẫn nằm
        # trên RFQ làm bằng chứng. Chỉ chặn khi không còn dòng nào để báo.
        quotable = rfq.line_ids.filtered(lambda l: not l.is_infeasible)
        if not quotable:
            raise UserError(QTE_INFEASIBLE)

        for line in quotable:
            self._validate_line(line, context)

    def _validate_line(self, rfq_line, context):
        """Soát một dòng RFQ: hàng thương mại phải có giá bán, hàng gia công
        phải có BOM đã xác nhận/khoá."""
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
    # Dựng phần đầu báo giá & từng dòng
    # ------------------------------------------------------------------
    def _prepare_header_vals(self, rfq, context):
        """Phần đầu báo giá: khách, RFQ nguồn, ngày, chiết khấu/VAT mặc định."""
        return {
            "partner_id": rfq.customer_id.id,
            "quotation_request_id": rfq.id,
            "company_id": context["company"].id,
            "currency_id": context["currency"].id,
            "pricing_date": context["pricing_date"],
            "date_order": context["pricing_date"],
            "validity_date": self._validity_date_for(context["pricing_date"]),
            "discount_pct": context["discount_pct"],
            "vat_pct": context["vat_pct"],
            "state": "draft",
        }

    def _validity_date_for(self, pricing_date):
        """Hạn hiệu lực = ngày báo giá + N ngày (mặc định 7).

        Giá thép trượt theo ngày nên cam kết giá dài là tự nhận rủi ro thị
        trường. Bảy ngày là hạn mặc định; đổi bằng tham số hệ thống
        `dl_sale.quotation_validity_days` chứ không sửa code."""
        return pricing_date + timedelta(days=self._validity_days())

    def _validity_days(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "dl_sale.quotation_validity_days")
        try:
            return max(1, int(raw)) if raw else 7
        except (TypeError, ValueError):
            return 7

    def _create_quotation_line(self, quotation, rfq_line, context):
        """Đẻ một dòng báo giá + các cấu phần giá của nó (dữ liệu nuôi bảng
        công thức ở trang Phân tích giá thành)."""
        if rfq_line.product_type == "trading":
            vals, comp_specs = self._price_trading(rfq_line, context)
        else:
            vals, comp_specs = self._price_manufactured(rfq_line, context)

        vals.update(
            quotation_id=quotation.id,
            rfq_line_id=rfq_line.id,
            qty=rfq_line.quantity,
            # Đơn vị khách đặt hàng theo — đi kèm số lượng, không suy lại từ
            # sản phẩm: RFQ là chỗ duy nhất biết khách hỏi "bộ" hay "mét".
            uom_id=rfq_line.uom_id.id,
        )
        line = self.env["dl.quotation.line"].sudo().create(vals)

        Component = self.env["dl.quotation.price.component"].sudo()
        for spec in comp_specs:
            spec.update(quotation_id=quotation.id, quotation_line_id=line.id)
            Component.create(spec)
        return line

    # ------------------------------------------------------------------
    # Hàng thương mại (mua về bán lại)
    # ------------------------------------------------------------------
    def _price_trading(self, rfq_line, context):
        """Hàng mua về bán lại: lấy thẳng giá bán trên hồ sơ sản phẩm, không
        qua giá thành/markup/giá sàn."""
        product = rfq_line.resolved_product_id
        qty = rfq_line.quantity
        base_price = product.list_price  # chụp lại giá bán tại thời điểm này

        vals = {
            "name": product.display_name,
            "line_type": "trading",
            "product_id": product.id,
            "base_price": base_price,
            "price_unit": base_price,
            "total_cost": 0.0,      # không tính giá thành cho hàng bán lại
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
    # Chi phí trực tiếp (vật tư + công) cho 1 sản phẩm
    # ------------------------------------------------------------------
    def _manufactured_direct_cost(self, rfq_line, context):
        """Vật tư + tiền công cho MỘT sản phẩm, chưa cộng phụ phí và chưa có lãi.

        Tách riêng vì lượt chạy đầu (đo đơn to/nhỏ) cần đúng con số này, và kết
        quả được cache lại để lượt tính chính khỏi duyệt BOM lần nữa."""
        bom = rfq_line.resolved_bom_id
        qty = rfq_line.quantity
        # Vật tư + tiền công tính theo đơn vị. BOM lồng BOM thì đệ quy xuống,
        # tiền công của bán thành phẩm tự nằm trong giá vốn của nó.
        # order_qty đi xuống tận dòng vật tư: giá vật tư có thể phụ thuộc TỔNG
        # số phải mua cho cả dòng (phần lấy từ kho theo giá lô, phần thiếu theo
        # giá mua mới) — tính trên 1 sp thì không biết lấy được bao nhiêu từ kho.
        material_unit, material_unit_repl, op_var_unit, unit_specs = \
            self._bom_unit_cost(bom, context, visited=frozenset(),
                                order_qty=qty)
        # Phí tính theo LÔ (setup máy…): trả một lần cho cả mẻ nên cộng một lần
        # rồi chia đều cho số lượng đặt — đặt càng nhiều càng rẻ trên đầu sp.
        batch_total, batch_specs = self._bom_batch_cost(bom, context)
        op_setup_unit = batch_total / qty if qty else 0.0
        return {
            "bom": bom,
            "qty": qty,
            "material_unit": material_unit,
            # Tiền vật tư nếu phải MUA LẠI TẤT CẢ theo giá hiện hành — nuôi giá
            # sàn. Bằng material_unit khi không có lớp trộn giá kho (dl_sale
            # chạy một mình).
            "material_unit_repl": material_unit_repl,
            "operation_cost": op_var_unit + op_setup_unit,
            "unit_specs": unit_specs,
            "batch_specs": batch_specs,
        }

    # ------------------------------------------------------------------
    # Hàng gia công: từ chi phí ra giá chào
    # ------------------------------------------------------------------
    def _price_manufactured(self, rfq_line, context):
        """Ra giá cho một dòng gia công: chi phí trực tiếp → cộng phụ phí →
        giá thành → nhân markup ra giá chào + tính giá sàn.

        Đồng thời sinh các cấu phần giá để trang Phân tích giá thành giải trình
        được từng đồng."""
        # Lấy lại chi phí đã tính ở lượt chạy đầu; gọi lẻ ngoài luồng (unit
        # test) thì không có cache nên tính thẳng.
        dc = context.get("direct_cache", {}).get(rfq_line.id)
        if dc is None:
            dc = self._manufactured_direct_cost(rfq_line, context)
        bom = dc["bom"]
        qty = dc["qty"]
        material_unit = dc["material_unit"]
        operation_cost = dc["operation_cost"]
        unit_specs = dc["unit_specs"]
        batch_specs = dc["batch_specs"]

        profit_rule = context["profit_rule"]
        if not profit_rule:
            raise UserError(QTE_005)

        # Cộng các khoản phụ phí (overhead, đóng gói, giao gấp, đơn nhỏ, dự
        # phòng) lên chi phí trực tiếp.
        direct_cost = material_unit + operation_cost
        adjustment_cost, adj_specs = self._apply_cost_adjustments(
            direct_cost, context, qty)

        # Ra 3 con số cuối: giá thành, giá chào (đã cộng lãi mục tiêu, làm
        # tròn) và giá sàn (lãi tối thiểu — bán dưới mức này phải xin duyệt).
        total_cost = direct_cost + adjustment_cost
        target_markup = profit_rule.target_markup
        min_markup = profit_rule.min_markup
        target_price = total_cost * (1 + target_markup / 100.0)

        # 🔴 GIÁ SÀN tính trên giá vật tư MUA LẠI, không trên giá vốn lô cũ.
        # Giá thành nói "đơn NÀY lãi bao nhiêu"; giá sàn giữ "lần SAU còn làm
        # được không". Lấy sàn theo lô cũ rẻ là mỗi vòng giá thép tăng lại tụt
        # một nấc biên, sổ vẫn lãi mà tiền thì hụt dần.
        direct_cost_repl = dc["material_unit_repl"] + operation_cost
        adjustment_cost_repl, _repl_specs = self._apply_cost_adjustments(
            direct_cost_repl, context, qty)
        total_cost_repl = direct_cost_repl + adjustment_cost_repl
        floor_price = total_cost_repl * (1 + min_markup / 100.0)

        # 🔴 Giá sàn là SÀN CỨNG, không phải cờ báo động.
        # Giá thành ăn theo lô cũ rẻ, còn sàn neo giá mua lại: hễ tồn kho rẻ hơn
        # giá mua lại quá (target − min) markup thì markup mục tiêu KHÔNG với tới
        # sàn, và mọi báo giá loại này tự động "dưới giá sàn" ⇒ phải xin duyệt.
        # Với thép trượt giá theo ngày thì đó là gần như mọi báo giá — cảnh báo
        # nổ liên tục thì thành nhiễu, và nhiễu thì không ai đọc.
        # Nâng lên đúng sàn là quyết định kinh doanh đúng: không bao giờ chào
        # dưới mức mua lại được hàng. Phần chênh do giữ hàng giá rẻ vẫn nằm
        # nguyên trong lãi thật, chỉ là không đem cho khách.
        price_unit = self._round_price(target_price, context["rounding_to"])
        if float_compare(price_unit, floor_price, precision_digits=2) < 0:
            # 🔴 Làm tròn phải theo hướng LÊN ở đây. `_round_price` dùng HALF-UP
            # nên 259.200 → 259.000, tức là nâng lên sàn xong lại rơi xuống dưới
            # sàn 200đ — sai mà nhìn như đúng. Ca này bắt buộc ceil.
            price_unit = self._ceil_price(floor_price, context["rounding_to"])

        vals = {
            "name": rfq_line.resolved_product_id.display_name or rfq_line.product_name,
            "line_type": "manufactured",
            "product_id": rfq_line.resolved_product_id.id,
            "bom_id": bom.id,
            # Chụp lại BOM đang dùng: chép giá trị, không trỏ sống về
            # bom.version — BOM lên bản mới thì báo giá cũ vẫn nhớ đúng bản.
            "bom_version": bom.version,
            "bom_approved_by": bom.approved_by.id,
            "bom_confirmed_date": bom.approved_date,
            "material_cost": material_unit,
            "operation_cost": operation_cost,
            "adjustment_cost": adjustment_cost,
            "total_cost": total_cost,
            # Giá thành nếu phải mua lại toàn bộ vật tư theo giá hiện hành —
            # hiện lên trang Phân tích giá thành để thấy phần "lãi giữ hàng".
            "replacement_cost": total_cost_repl,
            "base_price": target_price,
            "price_unit": price_unit,
            "floor_price": floor_price,
        }

        comp_specs = []
        for spec in unit_specs:
            # Các cấu phần trên đang tính cho 1 sản phẩm — nhân số lượng đặt để
            # ra con số của cả dòng.
            comp_specs.append({
                "component_type": spec["component_type"],
                "source_model": spec["source_model"],
                "source_id": spec["source_id"],
                "source_revision": spec["source_revision"],
                "material_id": spec.get("material_id", False),
                "qty": spec["qty"] * qty,
                "unit_price": spec["unit_price"],
                "rate": spec.get("rate", 0.0),
                "amount": spec["amount"] * qty,
                # KHÔNG nhân qty: hai con số này tính từ tổng nhu cầu của cả
                # dòng ngay từ đầu (xem need_factor ở _bom_unit_cost).
                "dlm_qty_from_stock": spec.get("dlm_qty_from_stock", 0.0),
                "dlm_qty_to_buy": spec.get("dlm_qty_to_buy", 0.0),
                "dlm_buy_price": spec.get("dlm_buy_price", 0.0),
                "dlm_price_note": spec.get("dlm_price_note", ""),
            })
        # Phí theo lô đã là tổng cho cả dòng rồi nên KHÔNG nhân qty nữa; cột
        # đơn giá chỉ để hiển thị phần chia trên đầu sản phẩm.
        for spec in batch_specs:
            spec["qty"] = qty
            spec["unit_price"] = spec["amount"] / qty if qty else 0.0
            comp_specs.append(spec)
        # Phụ phí đang tính trên đầu sản phẩm → nhân qty ra cả dòng.
        for spec in adj_specs:
            comp_specs.append({
                "component_type": "adjustment",
                "source_model": spec["source_model"],
                "source_id": spec["source_id"],
                "source_revision": spec["source_revision"],
                "material_id": False,
                "qty": qty,
                "unit_price": spec["unit_price"],
                "rate": spec["rate"],
                "amount": spec["amount"] * qty,
                "no_discount": spec["no_discount"],
            })
        # Dòng cuối bảng công thức: phần lãi cộng thêm trên giá thành.
        comp_specs.append({
            "component_type": "markup",
            "source_model": "dl.pricing.profit.rule",
            "source_id": profit_rule.id,
            "source_revision": profit_rule.revision,
            "qty": qty,
            "unit_price": total_cost,          # nền để tính lãi, trên 1 sp
            "rate": target_markup,
            "amount": (price_unit - total_cost) * qty,
        })
        return vals, comp_specs

    def _apply_cost_adjustments(self, direct_unit, context, qty):
        """Cộng các khoản phụ phí (overhead, đóng gói, giao gấp, đơn nhỏ, dự
        phòng) lên chi phí trực tiếp của 1 sản phẩm.

        Trả về (tổng phụ phí trên 1 sp, danh sách cấu phần để in ra bảng công
        thức).

        Thứ tự cộng đã được sắp sẵn: các khoản tiền cố định vào trước, các
        khoản tính theo % / hệ số vào sau. Nhờ vậy khoản % luôn nhân trên nền
        đã đủ, và kết quả KHÔNG đổi theo thứ tự khai báo rule trong màn cấu hình.

        Rule nào đã dùng thì đóng dấu lại — màn cấu hình sẽ khoá không cho sửa."""
        rules = context.get("adjustment_rules")
        if not rules:
            return 0.0, []
        order_value = context.get("order_value") or 0.0
        delivery_days = context.get("delivery_days")

        running = direct_unit
        adj_total = 0.0
        specs = []
        for rule in rules:
            if not rule.applies(order_value, delivery_days):
                continue
            amount = rule.adjustment_unit_amount(direct_unit, running, qty)
            if not amount:
                continue
            running += amount
            adj_total += amount
            if not rule.used_in_snapshot:
                rule.write({"used_in_snapshot": True})
            is_rate = rule.method in (
                "percent_direct", "percent_cost", "factor")
            specs.append({
                "source_model": "dl.pricing.cost.adjustment.rule",
                "source_id": rule.id,
                "source_revision": rule.revision,
                # Khoản theo %/hệ số: ghi tỷ lệ ở cột 'rate', bỏ trống đơn giá.
                "unit_price": 0.0 if is_rate else amount,
                "rate": rule.value if is_rate else 0.0,
                "amount": amount,
                "no_discount": rule.no_discount,
            })
        return adj_total, specs

    def _resolve_child_bom(self, material):
        """Chọn BOM nào làm giá vốn chuẩn cho một bán thành phẩm.

        🔴 Không được lấy "version cao nhất": một BOM báo giá sinh riêng cho
        đơn A có thể có version cao hơn BOM chuẩn, lấy nhầm thì định mức của đơn
        A âm thầm thành giá vốn cho đơn B. Sai kiểu này chỉ lệch ở tiền, rất khó
        thấy. Ưu tiên đúng là: BOM chuẩn hiện hành → BOM chuẩn mới nhất → cuối
        cùng mới đành lấy BOM báo giá (khi bán thành phẩm chưa từng có BOM chuẩn).

        Việc chọn dồn về một hàm duy nhất ở dl.bom để engine này và ảnh chụp
        dòng BOM luôn ra cùng một con số giá vốn."""
        return self.env["dl.bom"].sudo()._standard_child_bom(material)

    def _bom_unit_cost(self, bom, context, visited, order_qty=1.0):
        """Vật tư + tiền công (phần theo đơn vị) cho MỘT sản phẩm của BOM này.

        Trả về (tiền vật tư/sp, tiền vật tư mua-lại/sp, tiền công biến đổi/sp,
        danh sách cấu phần). Phần phí theo LÔ (setup) không tính ở đây mà ở
        _bom_batch_cost cho BOM ngoài cùng.

        ``order_qty`` là số sản phẩm của CẢ DÒNG báo giá — cần để biết tổng nhu
        cầu từng vật tư, vì giá vật tư có thể phụ thuộc lượng lấy được từ kho.

        BOM lồng BOM: gặp một bán thành phẩm thì gọi đệ quy xuống, giá vốn bán
        thành phẩm = vật tư + tiền công của chính nó, nên tiền công cắt/hàn/sơn
        của bán thành phẩm tự nằm trong đó. ``visited`` chặn BOM lồng vòng
        (A cần B, B cần A) — gặp là báo lỗi QTE-004."""
        if bom.id in visited:
            raise UserError(QTE_004 % bom.display_name)
        visited = visited | {bom.id}

        if bom.product_qty <= 0 or not bom.line_ids:
            raise UserError(QTE_004 % bom.display_name)

        specs = []
        total_output_cost = 0.0  # chi phí vật tư cho product_qty đơn vị đầu ra
        total_output_repl = 0.0  # nt, nhưng theo giá MUA LẠI (nuôi giá sàn)
        line_net = {}            # bl.id -> chi phí thuần dòng (cho product_qty)
        # Quy đổi "định mức cho cả mẻ" → "tổng nhu cầu của cả dòng báo giá".
        need_factor = order_qty / bom.product_qty if bom.product_qty else 0.0
        for bl in bom.line_ids:
            material = bl.material_id
            if not material:
                raise UserError(QTE_004 % bom.display_name)

            total_need = bl.effective_qty * need_factor
            if material.product_kind == "material_processed":
                # Dòng này là bán thành phẩm ⇒ đệ quy xuống BOM của nó.
                child = self._resolve_child_bom(material)
                if not child:
                    raise UserError(QTE_004 % material.display_name)
                child_mat, child_repl, child_op, _child_specs = \
                    self._bom_unit_cost(child, context, visited,
                                        order_qty=total_need)
                # Giá vốn bán thành phẩm = vật tư + tiền công của chính nó.
                unit_price = child_mat + child_op
                unit_price_repl = child_repl + child_op
                spec_base = {
                    "component_type": "processed_material",
                    "source_model": "dl.bom",
                    "source_id": child.id,
                    "source_revision": child.version,
                }
            else:
                # Vật tư thô mua ngoài. Giá do _material_unit_price quyết định:
                # bản gốc ở đây là giá NCC đang áp dụng; dl_purchase ghi đè để
                # trộn giá lô còn trong kho với giá mua mới cho phần thiếu.
                price_info = self._material_unit_price(
                    material, total_need, context, bom_line=bl)
                unit_price = price_info["unit_price"]
                unit_price_repl = price_info["replacement_price"]
                spec_base = {
                    "component_type": "material",
                    "source_model": price_info["source_model"],
                    "source_id": price_info["source_id"],
                    "source_revision": 0,
                    "dlm_price_note": price_info.get("note") or "",
                    "dlm_qty_from_stock": price_info.get("qty_from_stock", 0.0),
                    "dlm_qty_to_buy": price_info.get("qty_to_buy", 0.0),
                    "dlm_buy_price": price_info.get("buy_price", 0.0),
                }

            amount = bl.effective_qty * unit_price  # cho cả mẻ product_qty
            net = amount
            total_output_cost += amount
            total_output_repl += bl.effective_qty * unit_price_repl
            spec_base.update(
                material_id=material.id,
                qty=bl.effective_qty,
                unit_price=unit_price,
                amount=amount,
            )
            specs.append(spec_base)

            # 🔴 Không còn trừ tiền thu hồi phế liệu vào giá vốn nữa — công ty
            # chốt bỏ cách tính đó, tiền bán phế liệu thật để thành lãi ngoài.
            # Vì vậy engine không sinh cấu phần 'recovery'; báo giá cũ đã lưu
            # thì vẫn giữ nguyên, chỉ báo giá tính MỚI mới khác.
            line_net[bl.id] = net

        material_unit = total_output_cost / bom.product_qty
        material_unit_repl = total_output_repl / bom.product_qty
        # Quy các cấu phần vật tư về một đơn vị đầu ra.
        for spec in specs:
            spec["qty"] /= bom.product_qty
            spec["amount"] /= bom.product_qty

        # Tiền công (phần theo đơn vị) của chính BOM này — đã tính sẵn cho 1
        # sản phẩm nên không chia product_qty nữa.
        op_var_unit, op_specs = self._bom_operation_variable_cost(
            bom, context, material_unit, line_net)
        specs.extend(op_specs)
        return material_unit, material_unit_repl, op_var_unit, specs

    def _material_unit_price(self, material, total_need, context, bom_line=None):
        """Đơn giá một vật tư thô để tính giá thành — điểm nối cho lớp trộn giá kho.

        Bản gốc (dl_sale chạy một mình): giá bảng NCC đang áp dụng, và giá mua
        lại bằng đúng giá đó. `dl_purchase` ghi đè để lấy giá lô còn trong kho
        cho phần có sẵn và giá mua mới cho phần thiếu.

        Trả dict: unit_price (nuôi giá thành) · replacement_price (nuôi giá sàn)
        · source_model/source_id · note · qty_from_stock · qty_to_buy."""
        seller = self._active_material_seller(material, context)
        if not seller or seller.price <= 0:
            raise UserError(QTE_003 % material.display_name)
        if bom_line is not None:
            self._check_measure_compatibility(bom_line, material, seller, context)
        return {
            "unit_price": seller.price,
            "replacement_price": seller.price,
            "buy_price": seller.price,
            "source_model": "product.supplierinfo",
            "source_id": seller.id,
            "note": "",
            "qty_from_stock": 0.0,
            "qty_to_buy": total_need,
        }

    def _bom_operation_variable_cost(self, bom, context, material_unit, line_net):
        """Tiền công cắt/hàn/sơn cho MỘT sản phẩm (chưa gồm phí setup theo lô).

        Mỗi công đoạn tra đơn giá đang áp dụng tại ngày tính giá, y như cách
        tra giá NCC cho vật tư. Có công đoạn tính theo % giá vật liệu — khi đó
        ``line_net`` cho biết tiền vật liệu để lấy làm gốc %."""
        company = context["company"]
        date = context["pricing_date"]
        qty_out = bom.product_qty or 1.0
        Rule = self.env["dl.pricing.operation.rule"].sudo()

        op_unit = 0.0
        specs = []
        for op in bom.operation_line_ids:
            rule = Rule._get_active(op.operation_id, company, date)
            if not rule:
                raise UserError(QTE_011 % op.operation_id.display_name)
            if rule.method in ("per_kg", "per_meter", "per_sqm") and op.base_qty <= 0:
                raise UserError(QTE_010 % op.operation_id.display_name)

            # Gốc để tính % vật liệu: nếu công đoạn chỉ ăn theo vài dòng vật tư
            # đã chọn thì cộng riêng mấy dòng đó, còn lại lấy toàn bộ vật tư.
            if op.material_scope == "selected" and op.material_line_ids:
                base = sum(line_net.get(bl.id, 0.0)
                           for bl in op.material_line_ids) / qty_out
            else:
                base = material_unit

            amount = rule.variable_unit_amount(op.base_qty, base)
            # Đóng dấu rule đã dùng — màn cấu hình sẽ khoá không cho sửa.
            if not rule.used_in_snapshot:
                rule.write({"used_in_snapshot": True})
            if not amount:
                # Công đoạn tính trọn gói theo lô: phần theo đơn vị = 0, để
                # _bom_batch_cost lo, ở đây bỏ qua.
                continue
            op_unit += amount
            is_percent = rule.method == "percent_material"
            per_qty_method = rule.method in ("per_kg", "per_meter", "per_sqm")
            specs.append({
                "component_type": "operation",
                "source_model": "dl.pricing.operation.rule",
                "source_id": rule.id,
                "source_revision": rule.revision,
                "material_id": False,
                "qty": op.base_qty if per_qty_method else 1.0,
                # Công đoạn tính theo %: ghi tỷ lệ ở 'rate', bỏ trống đơn giá.
                "unit_price": 0.0 if is_percent else rule.price_rate,
                "rate": rule.price_rate if is_percent else 0.0,
                "amount": amount,
            })
        return op_unit, specs

    def _bom_batch_cost(self, bom, context):
        """Phí trả một lần cho cả mẻ: phí setup máy + công đoạn tính trọn gói
        theo lô. Cộng một lần rồi engine chia đều cho số lượng đặt.

        Chỉ tính ở BOM ngoài cùng — BOM lồng bên trong chỉ hỗ trợ tiền công
        theo đơn vị."""
        company = context["company"]
        date = context["pricing_date"]
        Rule = self.env["dl.pricing.operation.rule"].sudo()

        batch_total = 0.0
        specs = []
        for op in bom.operation_line_ids:
            rule = Rule._get_active(op.operation_id, company, date)
            if not rule:
                # Đã kiểm ở _bom_operation_variable_cost cho cùng BOM.
                raise UserError(QTE_011 % op.operation_id.display_name)
            batch = rule.setup_fee
            if rule.method == "per_batch":
                batch += rule.price_rate
            if not batch:
                continue
            batch_total += batch
            specs.append({
                "component_type": "operation_setup",
                "source_model": "dl.pricing.operation.rule",
                "source_id": rule.id,
                "source_revision": rule.revision,
                "material_id": False,
                "rate": 0.0,
                # amount là tổng cả lô; phần chia trên đầu sp điền ở _price_manufactured.
                "amount": batch,
            })
        return batch_total, specs

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
        """Chặn cứng khi đơn vị/tiền tệ không khớp nhau.

        Hệ thống chưa tự quy đổi đơn vị mua ↔ đơn vị định mức, hay ngoại tệ ↔
        tiền công ty. Thà báo lỗi QTE-007 bắt sửa dữ liệu còn hơn cứ nhân bừa
        rồi ra số sai mà không ai biết."""
        # Đơn vị mua khác đơn vị tính ⇒ giá NCC không cùng đơn vị với định mức.
        if material.uom_id and material.uom_po_id and material.uom_id != material.uom_po_id:
            raise UserError(QTE_007 % material.display_name)
        if seller and seller.currency_id and seller.currency_id != context["currency"]:
            raise UserError(QTE_007 % material.display_name)

    # ------------------------------------------------------------------
    # Chiết khấu/VAT ở đầu báo giá + xét có phải xin duyệt không
    # ------------------------------------------------------------------
    def _apply_commercial_and_approval(self, quotation, context):
        """Điền nốt phần thương mại ở đầu báo giá rồi chấm xem báo giá có phải
        đi xin phê duyệt không."""
        profit = context.get("profit_rule")

        # Lưu lại markup mục tiêu đã dùng để sau còn giải trình; chiết khấu do
        # reevaluate_quotation lưu.
        quotation.write({
            "target_markup": profit.target_markup if profit else 0.0,
        })

        # Ghi cấu phần chiết khấu/VAT để bảng công thức có đủ các lớp tiền.
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

    # ------------------------------------------------------------------
    # Tính lại giá theo thị trường hôm nay
    # ------------------------------------------------------------------
    def recompute_quotation(self, quotation, extend_validity=True, reason=None):
        """Tính lại toàn bộ tiền của một báo giá theo giá đầu vào HÔM NAY.

        Khác `create_from_rfq`: giữ nguyên bản ghi báo giá (số hiệu, khách,
        chiết khấu Sales đã nhập, lịch sử chatter) và chỉ dựng lại dòng + cấu
        phần. Dùng khi báo giá quá hạn mà khách mới chốt, hoặc khi Mua hàng vừa
        cập nhật giá nhà cung cấp cho vật tư đang thiếu.

        Trả dict chênh lệch để nơi gọi hiện lên màn."""
        quotation.ensure_one()
        Quotation = self.env["dl.quotation"]
        if quotation.state in Quotation._CLOSED_STATES or quotation.state == "ordered":
            raise UserError(_(
                "Báo giá %s đã đóng hoặc đã lên đơn — không tính lại được. "
                "Hãy tạo bản báo giá mới."
            ) % quotation.name)
        rfq = quotation.quotation_request_id
        if not rfq:
            raise UserError(_(
                "Báo giá %s không gắn yêu cầu báo giá nào nên không có định "
                "mức để tính lại."
            ) % quotation.name)

        quotation = quotation.sudo()
        truoc_cost = quotation.total_cost
        truoc_ban = quotation.amount_before_vat
        truoc_state = quotation.state

        context = self._build_context(rfq)
        quotable = rfq.line_ids.filtered(lambda l: not l.is_infeasible)
        if not quotable:
            raise UserError(QTE_INFEASIBLE)
        for line in quotable:
            self._validate_line(line, context)

        # Đo lại đơn to/nhỏ y như lượt tạo đầu — phụ phí "Đơn hàng nhỏ" phụ
        # thuộc con số này, và giá vật tư vừa đổi thì nó cũng đổi theo.
        direct_cache = {}
        order_value = 0.0
        for rfq_line in quotable:
            if rfq_line.product_type == "trading":
                order_value += rfq_line.quantity * (
                    rfq_line.resolved_product_id.list_price or 0.0)
            else:
                dc = self._manufactured_direct_cost(rfq_line, context)
                direct_cache[rfq_line.id] = dc
                order_value += rfq_line.quantity * (
                    dc["material_unit"] + dc["operation_cost"])
        context["order_value"] = order_value
        context["direct_cache"] = direct_cache

        # Dọn MỌI cấu phần, kể cả cấu phần chiết khấu/VAT ở đầu báo giá —
        # chúng không thuộc dòng nào nên unlink dòng không chạm tới, để lại thì
        # bảng công thức có hai lớp chiết khấu chồng nhau.
        self.env["dl.quotation.price.component"].sudo().search(
            [("quotation_id", "=", quotation.id)]).unlink()
        quotation.line_ids.unlink()

        vals = {"pricing_date": context["pricing_date"]}
        if extend_validity:
            vals["validity_date"] = self._validity_date_for(context["pricing_date"])
        quotation.write(vals)
        for rfq_line in quotable:
            self._create_quotation_line(quotation, rfq_line, context)
        self._apply_commercial_and_approval(quotation, context)
        quotation.flush_recordset()

        delta = {
            "cost_before": truoc_cost,
            "cost_after": quotation.total_cost,
            "price_before": truoc_ban,
            "price_after": quotation.amount_before_vat,
            "cost_pct": ((quotation.total_cost - truoc_cost) / truoc_cost * 100.0
                         if truoc_cost else 0.0),
        }
        # 🔴 Giá ĐỔI trên một báo giá ĐÃ GỬI KHÁCH ⇒ con số mới khách chưa từng
        # thấy. Giữ nguyên "Đã gửi"/"Khách đồng ý" là ghi nhận một sự đồng ý
        # không có thật, và cho phép lên đơn ở mức giá chưa ai chào. Đưa về Nháp
        # để buộc đi lại vòng gửi khách → khách đồng ý.
        # Giá KHÔNG đổi thì đây chỉ là gia hạn — không đụng trạng thái.
        delta["must_resend"] = bool(
            truoc_state in self._DA_GUI_KHACH_STATES
            and not float_is_zero(delta["price_after"] - truoc_ban,
                                  precision_digits=2))
        if delta["must_resend"]:
            # Chỉ đổi state; lý do đi vào chatter ở _recompute_note. `dl.quotation`
            # không có field lý-do-về-nháp (đó là field của dl.sale.order).
            quotation.write({"state": "draft"})
        # Số "phải mua" vừa đổi ⇒ mọi xác nhận giá mua trước đó hết hiệu lực.
        if hasattr(quotation, "recompute_quotation_clear_confirm"):
            quotation.recompute_quotation_clear_confirm()
        quotation.message_post(body=self._recompute_note(quotation, delta, reason))
        return delta

    # Trạng thái mà khách ĐÃ nhìn thấy con số. Đổi giá ở những trạng thái này
    # thì phải chào lại, không được sửa ngầm dưới chân khách.
    _DA_GUI_KHACH_STATES = ("approved", "sent", "accepted")

    @staticmethod
    def _fmt_vnd(value):
        return "{:,.0f}".format(value or 0.0).replace(",", ".")

    def _recompute_note(self, quotation, delta, reason=None):
        """Câu chatter sau khi tính lại — nói bằng SỐ, không nói "đã cập nhật"."""
        body = escape(reason or _("Đã tính lại giá theo giá đầu vào hôm nay."))
        body += Markup(
            "<ul>"
            "<li>Giá thành: <b>%(c1)s</b> → <b>%(c2)s</b> (%(pct)+.1f%%)</li>"
            "<li>Giá trước thuế: <b>%(p1)s</b> → <b>%(p2)s</b></li>"
            "<li>Hạn hiệu lực mới: <b>%(hh)s</b></li>"
            "</ul>%(gui_lai)s") % {
                "gui_lai": Markup(
                    "<p><b>Báo giá quay về Nháp</b> — khách chưa được chào mức "
                    "giá mới này. Gửi lại khách rồi mới lên đơn được.</p>"
                ) if delta.get("must_resend") else Markup(""),
                "c1": self._fmt_vnd(delta["cost_before"]),
                "c2": self._fmt_vnd(delta["cost_after"]),
                "pct": delta["cost_pct"],
                "p1": self._fmt_vnd(delta["price_before"]),
                "p2": self._fmt_vnd(delta["price_after"]),
                "hh": quotation.validity_date or "—",
            }
        return body

    def reevaluate_quotation(self, quotation, reason=None):
        """Chấm xem báo giá có phải xin phê duyệt không, và ở cấp nào.

        Gọi cả lúc tạo báo giá lẫn mỗi lần tiền đổi (Sales sửa chiết khấu/dòng/
        khách). Nếu đang có yêu cầu duyệt cũ thì huỷ đi rồi chấm lại từ đầu theo
        3 tín hiệu: giá trị đơn to hay nhỏ, chiết khấu vượt trần không, có bán
        dưới giá sàn không.

        sudo vì người sửa (Sales) không có quyền đọc field giá vốn hay ghi yêu
        cầu phê duyệt."""
        quotation.ensure_one()
        quotation = quotation.sudo()
        company = quotation.company_id or self.env.company
        date = quotation.pricing_date or fields.Date.context_today(quotation)
        discount = self._active_discount_rule(company, date, quotation.partner_id)

        # 3 tín hiệu quyết định có/không cần duyệt.
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

        # Tiền đã đổi thì yêu cầu duyệt cũ không còn đúng nữa — huỷ nó đi
        # (vẫn giữ lịch sử) rồi mở yêu cầu mới nếu cần.
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
        """Có dòng nào bị bán dưới giá sàn sau khi trừ chiết khấu không.

        Chiết khấu nhập ở đầu báo giá được rải xuống từng dòng theo tỷ lệ thành
        tiền, rồi so giá bán còn lại của từng dòng với giá sàn của dòng đó."""
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
    """Gắn thêm nút "Tạo báo giá" và link ngược cho RFQ.

    RFQ gốc định nghĩa ở dl_technical, không được biết tới dl.quotation (nếu
    không sẽ thành phụ thuộc vòng). Nên phần nối RFQ ↔ báo giá đặt ở đây, module
    dl_sale — module đứng sau, thấy được cả hai."""

    _inherit = "dl.quotation.request"

    # Nuôi nút mở nhanh báo giá đã tạo. Tìm bằng search chứ không lưu — chiều
    # sở hữu liên kết nằm ở dl.quotation.quotation_request_id.
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
        """Thử tạo báo giá; lỗi thì ghi lại lý do lên RFQ và trả về False chứ
        không ném ra ngoài (để nút còn hiện toast hướng dẫn)."""
        result = False
        for rec in self:
            if rec.status != "confirmed" or rec.quotation_id:
                continue
            try:
                # Bọc savepoint để nếu hỏng giữa chừng thì mọi thay đổi (kể cả
                # dấu "đã dùng" trên rule) đều được rollback sạch.
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
            # quotation_id tính bằng search, không tự làm mới. Ép tính lại để
            # nút "Mở báo giá" thấy ngay báo giá vừa tạo trong cùng phiên.
            rec.invalidate_recordset(["quotation_id"])
        return result

    def action_create_quotation(self):
        """Nút "Tạo báo giá" trên form RFQ đã xác nhận — kiểm quyền rồi gọi
        engine. Chỉ Sales / Trưởng KD / Admin được bấm."""
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
        """Nút "Mở báo giá" trên RFQ — nhảy sang báo giá đã tạo từ RFQ này."""
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
        """Kéo RFQ đã báo giá quay về "Đang xử lý" cho Kỹ thuật sửa BOM.

        Do nút "Chuyển Kỹ thuật sửa BOM" bên form Báo giá gọi sang khi khách
        đòi đổi vật liệu. sudo vì đây là chuyển tiếp luồng, Sales được phép kích
        hoạt dù không có quyền sửa RFQ."""
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
