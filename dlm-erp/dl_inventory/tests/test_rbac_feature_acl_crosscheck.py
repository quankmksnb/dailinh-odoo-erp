# -*- coding: utf-8 -*-
"""L2 (TransactionCase, PostgreSQL thật): đối chiếu 6 bản ghi `dl.rbac.feature`
khai trong data/rbac_features.xml (K1, dùng cho màn "Phân quyền" nội bộ) với
ACL thật (ir.model.access) của model tương ứng cho vai trò Thủ kho.

Trước đây chưa có test nào đối chiếu hai nguồn này. Một feature khai model_id
sai hoặc mồ côi (model không còn tồn tại, hoặc Thủ kho không thực sự có quyền
đọc model đó) sẽ khiến màn Phân quyền hiển thị sai mà không test nào bắt được.
"""
from .common import DlInventoryCase

# code: có model_id hoặc cố ý bỏ trống (kiểm kê/phế liệu không có model
# riêng, theo đúng comment trong rbac_features.xml).
_EXPECTED_FEATURES = {
    "stock_quant": "stock.quant",
    "stock_picking": "stock.picking",
    "stock_lot": "stock.lot",
    "stock_location": "stock.location",
    "stock_inventory": None,
    "stock_scrap": None,
}


class TestRbacFeatureAclCrosscheck(DlInventoryCase):

    def _features(self):
        return self.env["dl.rbac.feature"].sudo().search(
            [("code", "in", list(_EXPECTED_FEATURES))])

    def test_toan_bo_6_feature_kho_deu_ton_tai(self):
        """TC-INT-TestRbacFeatureAclCrosscheck-001: đủ 6 bản ghi K1, không thiếu và không
        trùng code (code_uniq).
        """
        features = self._features()
        self.assertEqual(
            sorted(features.mapped("code")), sorted(_EXPECTED_FEATURES))

    def test_model_id_dung_hoac_co_y_bo_trong(self):
        """TC-INT-TestRbacFeatureAclCrosscheck-002: model_id của mỗi feature khớp đúng
        model kỳ vọng, hoặc cố ý để trống (kiểm kê/phế liệu).
        """
        for feature in self._features():
            expected_model = _EXPECTED_FEATURES[feature.code]
            if expected_model is None:
                self.assertFalse(
                    feature.model_id,
                    "%s phải cố ý KHÔNG có model_id (dữ liệu nằm trên "
                    "stock.quant/stock.move lọc theo vị trí)." % feature.code)
            else:
                self.assertEqual(
                    feature.model_id.model, expected_model,
                    "%s khai sai model_id." % feature.code)

    def test_thu_kho_co_quyen_doc_moi_model_co_model_id(self):
        """TC-INT-TestRbacFeatureAclCrosscheck-003: bất biến chính, mọi feature K1 có
        model_id đều phải có ít nhất một dòng ir.model.access cấp quyền đọc cho
        dl_group_warehouse trên đúng model đó. Feature khai model_id mà Thủ kho không
        đọc được là feature mồ côi, màn Phân quyền sẽ hiện mục vô dụng.
        """
        group_warehouse = self.env.ref("dl_base.dl_group_warehouse")
        Access = self.env["ir.model.access"].sudo()
        for feature in self._features():
            if not feature.model_id:
                continue
            accesses = Access.search([
                ("model_id", "=", feature.model_id.id),
                ("group_id", "=", group_warehouse.id),
            ])
            self.assertTrue(
                accesses, "Feature %s (model %s) không có dòng "
                "ir.model.access nào cho dl_group_warehouse." % (
                    feature.code, feature.model_id.model))
            self.assertTrue(
                any(a.perm_read for a in accesses),
                "Feature %s (model %s): dl_group_warehouse có dòng ACL "
                "nhưng không dòng nào perm_read=True." % (
                    feature.code, feature.model_id.model))

    def test_khong_co_feature_stock_nao_ngoai_6_cai_da_biet(self):
        """TC-INT-TestRbacFeatureAclCrosscheck-004: không phát sinh thêm feature code tiền
        tố stock_ nào ngoài 6 cái đã khai. Đổi code nghĩa là sinh bản ghi mới và feature
        cũ thành mồ côi, đúng như cảnh báo trong comment của rbac_features.xml.
        """
        all_stock_features = self.env["dl.rbac.feature"].sudo().search(
            [("code", "like", "stock_%")])
        self.assertEqual(
            sorted(all_stock_features.mapped("code")),
            sorted(_EXPECTED_FEATURES))
