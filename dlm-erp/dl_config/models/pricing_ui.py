# -*- coding: utf-8 -*-
"""Cầu nối dữ liệu cho màn OWL Cấu hình Báo giá.

Màn OWL thao tác trực tiếp trên các model quy tắc V3 qua ORM (searchRead/create/
write + gọi action). Model này chỉ cung cấp một điểm bootstrap: quyền sửa theo
vai trò + các danh sách phục vụ dropdown (category, vật tư, công đoạn, người
duyệt). Không giữ dữ liệu — mọi quy tắc vẫn nằm ở model riêng của nó.
"""

from odoo import api, fields, models


class DlPricingUi(models.TransientModel):
    _name = "dl.pricing.ui"
    _description = "Bootstrap dữ liệu cho màn Cấu hình Báo giá"

    @api.model
    def _has(self, *codes):
        return any(self.env.user.has_group("dl_base.dl_group_%s" % c) for c in codes)

    @api.model
    def get_bootstrap(self):
        Category = self.env["product.category"].sudo()
        Product = self.env["product.product"].sudo()
        Operation = self.env["dl.pricing.operation"].sudo()
        Complexity = self.env["dl.pricing.complexity.level"].sudo()

        # Người duyệt hợp lệ: CEO / Trưởng KD / Admin đang hoạt động.
        approver_group_ids = []
        for code in ("ceo", "sales_manager", "admin"):
            group = self.env.ref("dl_base.dl_group_%s" % code, raise_if_not_found=False)
            if group:
                approver_group_ids.append(group.id)
        approvers = self.env["res.users"].sudo().search([
            ("active", "=", True), ("share", "=", False),
            ("groups_id", "in", approver_group_ids),
        ], order="name")

        return {
            "perms": {
                "waste": self._has("tech", "accountant", "admin"),
                "operation": self._has("tech", "accountant", "admin"),
                "cost": self._has("accountant", "tech", "admin"),
                "profit": self._has("ceo", "admin"),
                "discount": self._has("sales_manager", "ceo", "admin"),
                "approval": self._has("ceo", "sales_manager", "admin"),
                # Ma trận phê duyệt: chỉ Giám đốc/Admin được thêm/sửa (mục 8).
                "matrix": self._has("ceo", "admin"),
                "master": self._has("tech", "accountant", "admin"),
            },
            "options": {
                "categories": [
                    {"id": c.id, "name": c.display_name}
                    for c in Category.search([], order="complete_name", limit=500)
                ],
                "products": [
                    {"id": p.id, "name": p.display_name}
                    for p in Product.search([], order="name", limit=1000)
                ],
                "operations": [
                    {"id": o.id, "name": o.name, "code": o.code}
                    for o in Operation.search([("active", "=", True)], order="sequence")
                ],
                "complexity": [
                    {"id": x.id, "name": x.name, "factor": x.factor}
                    for x in Complexity.search([("active", "=", True)], order="sequence")
                ],
                "approvers": [{"id": u.id, "name": u.name} for u in approvers],
            },
        }
