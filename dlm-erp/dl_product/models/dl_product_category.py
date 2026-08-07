from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    """PROD-01 — dl.product.category [kế thừa product.category].

    Nhóm sản phẩm cơ khí — kế thừa mở rộng ``product.category`` để giữ tương
    thích hệ sinh thái Odoo (Inventory, Accounting).

    Data Model §4.2 PROD-01 chỉ định nghĩa 2 field mở rộng: ``bom_template_id``
    (→ TECH-04 dl.bom.template) và ``active``.

    Ghi chú kiến trúc: field ``bom_template_id`` trỏ tới model dl.bom.template
    (TECH-04) thuộc module dl_technical — nằm ở LAYER TRÊN dl_product. Vì
    dl_product không (và không được) depends dl_technical, FK category→BOM mẫu
    được khai báo bên dl_technical (đúng chiều phụ thuộc), KHÔNG khai ở đây.
    ``category_kind`` của thiết kế cũ đã BỎ (không có trong Data Model mới —
    phân loại giờ nằm ở product_kind cấp sản phẩm, không cần cấp category).

    ``dl_branch`` KHÔNG phải category_kind quay lại: nó là field DẪN XUẤT từ
    vị trí trong cây (nằm dưới gốc "Thành phẩm" hay "Vật tư" của
    material_category_data.xml) — người dùng không nhập tay, chỉ chọn nhóm cha.
    Dùng để tách danh mục input (vật tư) / output (thành phẩm) trên các màn
    CRUD và làm domain chặn cứng Nhóm theo Loại SP (product_kind).
    """

    _inherit = "product.category"

    active = fields.Boolean(string="Đang sử dụng", default=True)

    dl_branch = fields.Selection(
        [
            ("finished", "Thành phẩm"),
            ("material", "Vật tư"),
            ("other", "Khác"),
        ],
        string="Nhánh danh mục",
        compute="_compute_dl_branch",
        store=True,
        help="Suy ra từ cây nhóm: nằm dưới gốc 'Thành phẩm' hay 'Vật tư'. "
             "'Khác' = nhóm hệ thống Odoo hoặc nhóm chưa gắn vào 2 gốc chuẩn.",
    )

    @api.depends("parent_path")
    def _compute_dl_branch(self):
        finished = self.env.ref("dl_product.categ_root_finished", raise_if_not_found=False)
        material = self.env.ref("dl_product.categ_root_material", raise_if_not_found=False)
        for rec in self:
            ancestor_ids = [int(x) for x in (rec.parent_path or "").split("/") if x]
            if finished and finished.id in ancestor_ids:
                rec.dl_branch = "finished"
            elif material and material.id in ancestor_ids:
                rec.dl_branch = "material"
            else:
                rec.dl_branch = "other"

    @api.constrains("parent_id")
    def _check_branch_products(self):
        """Chặn kéo nhóm (kèm nhóm con) sang nhánh khác khi trong nhóm đã có
        sản phẩm sai loại — giữ bất biến: nhánh Thành phẩm chỉ chứa SP gia
        công/thương mại, nhánh Vật tư chỉ chứa vật tư/bán thành phẩm."""
        # Lúc nạp data XML / -u module (install_mode): KHÔNG chặn — DB cũ có
        # thể còn sản phẩm nằm sai nhóm từ trước, việc dọn thuộc về migration
        # (post-migrate 17.0.2.3.0), không được làm fail cả quá trình update.
        if self.env.context.get("install_mode"):
            return
        Product = self.env["product.product"].sudo().with_context(active_test=False)
        wrong_kinds = {
            "finished": ("material", "material_processed"),
            "material": ("manufactured", "trading"),
        }
        for rec in self:
            kinds = wrong_kinds.get(rec.dl_branch)
            if not kinds:
                continue
            bad = Product.search(
                [("categ_id", "child_of", rec.id), ("product_kind", "in", kinds)],
                limit=1,
            )
            if bad:
                raise ValidationError(_(
                    "Không thể chuyển nhóm '%s' sang nhánh %s — sản phẩm '%s' "
                    "trong nhóm thuộc loại không khớp nhánh này."
                ) % (rec.display_name, dict(rec._fields["dl_branch"].selection).get(rec.dl_branch),
                     bad.display_name))

    @api.constrains("active")
    def _dlm_check_archive_active_products(self):
        """LK-11 / CAT-02 — chặn lưu trữ (archive) nhóm còn sản phẩm ĐANG HOẠT
        ĐỘNG thuộc nhóm (kể cả nhóm con). Tránh làm 'mất' sản phẩm active khỏi
        cây danh mục. Bỏ qua lúc nạp data/-u (install_mode) như constrain nhánh."""
        if self.env.context.get("install_mode"):
            return
        Product = self.env["product.product"].sudo().with_context(active_test=False)
        for rec in self:
            if rec.active:
                continue
            count = Product.search_count([
                ("categ_id", "child_of", rec.id),
                ("dlm_lifecycle_state", "=", "active"),
            ])
            if count:
                raise ValidationError(_(
                    "Không thể lưu trữ nhóm '%s' — còn %s sản phẩm đang hoạt "
                    "động thuộc nhóm (kể cả nhóm con). Hãy chuyển nhóm hoặc "
                    "Ngừng các sản phẩm đó trước."
                ) % (rec.display_name, count))

    @api.onchange("parent_id")
    def _onchange_dlm_depth_warning(self):
        """LK-13 (§5.2) — cảnh báo MỀM (không chặn) khi tạo nhóm sâu quá ngưỡng
        (mặc định 3 cấp dưới gốc). Nhóm quá mịn khiến BOM mẫu/họ tham số nở tràn;
        chỉ nhắc, xưởng vẫn có thể cần ngoại lệ. Ngưỡng lấy từ ir.config_parameter
        dl_product.category_max_depth."""
        if not self.parent_id:
            return
        try:
            max_depth = int(self.env["ir.config_parameter"].sudo().get_param(
                "dl_product.category_max_depth", 3))
        except (TypeError, ValueError):
            max_depth = 3
        # parent_path của nhóm cha gồm cả gốc → số cấp của nhóm MỚI dưới gốc =
        # số id trong parent_path của cha (gốc tính là cấp 0).
        ancestor_ids = [
            x for x in (self.parent_id.parent_path or "").split("/") if x]
        new_depth = len(ancestor_ids)
        if new_depth > max_depth:
            return {"warning": {
                "title": _("Nhóm quá sâu"),
                "message": _(
                    "Nhóm mới sẽ nằm ở cấp %(depth)s dưới gốc (khuyến nghị tối đa "
                    "%(max)s cấp). BOM mẫu tham số chỉ nên gắn ở cấp 'Họ kết cấu' "
                    "— nhóm quá mịn khiến mẫu nở tràn. Cân nhắc dùng THAM SỐ "
                    "(kích thước) thay vì tách thêm nhóm con.",
                    depth=new_depth, max=max_depth),
            }}
