from odoo import api, fields, models

# Nhóm đo lường (kg/lít/m/m²) → MẶC ĐỊNH có hao hụt; nhóm "Đơn vị" → mặc định
# không. Đây chỉ là giá trị khởi tạo: Cây/Tấm nằm ở nhóm "Đơn vị" nhưng là hàng
# CẮT nên vẫn có hao hụt thật (mạch cắt, ba-via) — được bật tường minh trong
# dl_product/data/uom_data.xml. Đặt ở dl_base vì cả dl_product (logic định mức)
# và dl_config (màn quản lý ĐVT) đều đọc cờ này.
_DIVISIBLE_CATEG_XMLIDS = (
    "uom.product_uom_categ_kgm",   # Khối lượng
    "uom.product_uom_categ_vol",   # Thể tích
    "uom.uom_categ_length",        # Chiều dài
    "uom.uom_categ_surface",       # Bề mặt
)


class UomUom(models.Model):
    _inherit = "uom.uom"

    # Cờ nghiệp vụ TRỤC 1: vật tư dùng đơn vị này có hao hụt vật lý khi gia công
    # không ⇒ dòng BOM/form vật tư có hiện ô % hao hụt hay không.
    #
    # 🔴 KHÔNG gánh luôn việc "chỉ nhập số nguyên" — đó là TRỤC 2, và đã có sẵn
    # field `rounding` của Odoo lo (đặt 1.0 cho đơn vị không xé lẻ). Hai trục vuông
    # góc nhau: Cây vừa CÓ hao hụt (mạch cắt) vừa xuất NGUYÊN cây.
    #
    # computed-store nhưng readonly=False: tự điền theo nhóm khi tạo/-u, người
    # dùng vẫn sửa tay được; chỉ tính lại khi đổi Nhóm đơn vị.
    dlm_allow_waste = fields.Boolean(
        string="Có hao hụt",
        compute="_compute_dlm_allow_waste", store=True, readonly=False,
        help="Bật: vật tư dùng đơn vị này bị hao hụt khi gia công (kg/m/lít/m², "
             "và cả Cây/Tấm vì có mạch cắt) — dòng BOM có ô % hao hụt.\n"
             "Tắt: hàng đếm nguyên chiếc (cái/túi/hộp) — không khai hao hụt.\n"
             "Việc \"chỉ xuất số nguyên\" do ô Bước làm tròn lo, không phải ô này.")

    @api.depends("category_id")
    def _compute_dlm_allow_waste(self):
        ref = self.env.ref
        divisible = {
            categ.id for categ in
            (ref(x, raise_if_not_found=False) for x in _DIVISIBLE_CATEG_XMLIDS)
            if categ}
        for uom in self:
            uom.dlm_allow_waste = uom.category_id.id in divisible
