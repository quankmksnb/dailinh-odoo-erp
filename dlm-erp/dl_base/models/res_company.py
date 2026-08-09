import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

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
