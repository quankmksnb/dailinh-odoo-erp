import base64
import io
import logging

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

# Danh tính pháp lý — chép từ hợp đồng nguyên tắc số 1604/2026/HĐNT TĐ-ĐL
# (`docs/tài liệu doanh nghiệp/`), là chứng từ có đủ tên đăng ký, địa chỉ và MST.
DLM_COMPANY_NAME = "Công ty TNHH Đầu tư và Sản xuất Đại Linh"
_DLM_IDENTITY = {
    "name": DLM_COMPANY_NAME,
    "street": "Tổ 15, xã Nam Trực",
    "city": "Ninh Bình",
    "phone": "0989 204710",
    "vat": "0601194984",
}

# Logo đầy đủ (chữ + biểu tượng) — nguồn duy nhất cho res.company.logo, và từ đó
# chảy ra trang đăng nhập, chứng từ PDF/Word gửi khách và ảnh đại diện công ty.
DLM_LOGO_PATH = "dl_base/static/img/dai_linh_logo.png"


class ResCompany(models.Model):
    _inherit = "res.company"

    # ==================================================================
    # Danh tính công ty
    # ==================================================================
    @api.model
    def _dlm_setup_identity(self):
        """Ghi tên pháp lý / địa chỉ / MST / logo Đại Linh lên công ty — chạy lại mỗi ``-u dl_base``.

        Cùng lý do với ``_dlm_enforce_vnd``: ``base.main_company`` mang
        ``noupdate=True`` nên ``<record>`` trỏ vào nó bị bỏ qua ở chế độ update.
        Hệ thống chỉ phục vụ MỘT doanh nghiệp nên danh tính do code sở hữu, y
        như cây kho ở ``dl_inventory/models/stock_warehouse.py``.
        """
        logo = self._dlm_logo_binary()
        country = self.env.ref("base.vn", raise_if_not_found=False)

        for company in self.sudo().search([]):
            values = {
                field: value for field, value in _DLM_IDENTITY.items()
                if company[field] != value
            }
            if country and company.country_id != country:
                values["country_id"] = country.id
            # Logo chỉ ghi đè khi công ty còn để trống hoặc còn logo mặc định của
            # Odoo (`uses_default_logo`) — quản trị viên cố ý tải logo khác lên
            # thì không bị mỗi lần `-u dl_base` đạp lại.
            if logo and company.uses_default_logo:
                values["logo"] = logo
            if not values:
                continue
            try:
                company.write(values)
            except UserError:
                _logger.error(
                    "DLM: KHÔNG ghi được danh tính lên công ty %s.", company.name)
            else:
                _logger.info(
                    "DLM: đã đặt danh tính công ty theo %s.", DLM_COMPANY_NAME)

    @api.model
    def _dlm_logo_binary(self):
        """Đọc file logo trong ``dl_base/static/img`` ra base64; None nếu chưa đặt file vào repo."""
        try:
            path = file_path(DLM_LOGO_PATH)
        except (FileNotFoundError, ValueError):
            _logger.warning(
                "DLM: chưa có file logo %s — công ty giữ nguyên logo hiện tại.",
                DLM_LOGO_PATH)
            return None
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read())

    # ==================================================================
    # Đầu trang chứng từ PDF (báo giá, đơn mua, biên bản hàng không đạt)
    # ==================================================================
    def _dlm_pdf_logo(self, height):
        """Logo công ty dưới dạng flowable reportlab, giữ đúng tỉ lệ; None nếu chưa có logo."""
        self.ensure_one()
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image

        raw = base64.b64decode(self.logo) if self.logo else None
        if not raw:
            return None
        try:
            width_px, height_px = ImageReader(io.BytesIO(raw)).getSize()
        except Exception:  # noqa: BLE001 — logo hỏng không được chặn xuất chứng từ
            return None
        if not height_px:
            return None
        return Image(io.BytesIO(raw), mask="auto",
                     width=height * width_px / height_px, height=height)

    def _dlm_pdf_letterhead(self, name_style, body_style, width, logo_height=None):
        """Khối đầu trang dùng chung cho mọi chứng từ gửi ra ngoài: logo trái, thông tin công ty phải."""
        self.ensure_one()
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        address = ", ".join(filter(None, [self.street, self.city]))
        info = [Paragraph(self.name or "", name_style)]
        for text in filter(None, [
            ("Địa chỉ: " + address) if address else "",
            ("Mã số thuế: " + self.vat) if self.vat else "",
            " | ".join(filter(None, [
                ("ĐT: " + self.phone) if self.phone else "",
                ("Email: " + self.email) if self.email else ""])),
        ]):
            info.append(Paragraph(text, body_style))

        # 13mm: logo là lockup NGANG (tỉ lệ ~4,8:1) nên cao hơn nữa là nuốt mất
        # bề ngang dành cho tên pháp nhân bên phải — tên công ty dài 40 ký tự.
        logo = self._dlm_pdf_logo(logo_height or 13 * mm)
        if logo is None:
            # Chưa có logo thì vẫn phải ra đủ thông tin công ty, không để trống đầu trang.
            return info + [Spacer(1, 4 * mm)]

        gap = 6 * mm
        head = Table(
            [[logo, info]],
            colWidths=[logo.drawWidth + gap, width - logo.drawWidth - gap])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.HexColor("#0F6B3A")),
        ]))
        return [head, Spacer(1, 4 * mm)]

    # ==================================================================
    # Tiền tệ
    # ==================================================================
    @api.model
    def _dlm_enforce_vnd(self):
        """Ép mọi công ty dùng VNĐ — chạy LẠI ở mỗi lần ``-u dl_base``.

        Không giao được việc này cho ``<record>`` trong data: cả
        ``base.main_company`` lẫn ``base.VND`` đều có ``ir.model.data.noupdate =
        True``, nên record trỏ vào chúng bị BỎ QUA ở chế độ update — file data
        chỉ có tác dụng đúng lần cài đầu tiên. Trong khi đó cài ``account`` sau
        đó lại đặt tiền tệ công ty theo hệ thống tài khoản mặc định (USD).

        Hậu quả nếu lệch: giá NCC nhập bằng VNĐ còn hệ quy chiếu của engine là
        USD ⇒ mọi báo giá chết ở QTE-007 (P0 cố ý không quy đổi tiền tệ, xem
        ``quotation_pricing_service._check_measure_compatibility``).
        """
        vnd = self.env.ref("base.VND")
        if not vnd.active:
            vnd.active = True
        for company in self.sudo().search([("currency_id", "!=", vnd.id)]):
            try:
                company.write({"currency_id": vnd.id})
                _logger.info(
                    "DLM: đã đặt tiền tệ công ty %s về VNĐ.", company.name)
            except UserError:
                # account chặn đổi tiền tệ khi đã có bút toán. KHÔNG để việc này
                # làm hỏng cả lần update — nêu rõ để người vận hành xử lý tay.
                _logger.error(
                    "DLM: KHÔNG đổi được tiền tệ công ty %s sang VNĐ (đã có bút "
                    "toán kế toán). Báo giá sẽ chết ở QTE-007 tới khi xử lý.",
                    company.name)
