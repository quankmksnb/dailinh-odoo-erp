{
    "name": "DL-Inventory",
    "version": "17.0.9.4.0",
    "summary": "Kho Đại Linh — 1 kho, 4 khu, nhận hàng 2 bước có kiểm hàng",
    "description": """
Phân hệ Kho (Giai đoạn B1). Đặc tả: docs/Thiet_ke_phan_he_kho.md

Đã có (K1–K5):
  • Vai trò THỦ KHO (dl_base.dl_group_warehouse) + ACL + record rule + RBAC.
  • Bố cục kho: MỘT stock.warehouse, bốn khu (Nhập / Kho nhà máy sản xuất /
    Xưởng sản xuất / Thành phẩm); 9 loại hoạt động; nhận hàng 2 BƯỚC (về khu
    Chờ kiểm rồi mới cất) — nền cho bước QC.
  • Số lô do Đại Linh TỰ SINH (LO/2026/00001), tự điền khi nhận hàng; lô mang
    theo NCC + ngày nhập + phiếu nguồn.
  • Màn Tồn kho (chỉ-đọc, không có cột giá) và Lô hàng.
  • Kiểm hàng NCC: ghi Đạt/Loại + lý do ngay trên dòng phiếu, hàng loại sang
    khu Chờ trả NCC và sinh phiếu Trả hàng NCC ở trạng thái NHÁP giao cho Mua
    hàng. Tách bạch "NCC giao thiếu" (backorder) với "NCC giao hàng kém" (loại).

Thêm ở K6:
  • Chuyển kho nội bộ với 2 preset tuyến hay dùng (vật tư ra xưởng, gom phế
    liệu — preset "sang kho thành phẩm" đã bỏ ở K9).
  • Giao hàng khách gắn với dl.sale.order: nút Tạo phiếu giao trên đơn (KHÔNG
    tự sinh lúc chốt đơn), chip tình trạng giao, và khoá đưa đơn về nháp khi
    đã phát sinh phiếu giao.
  • Màn Trả hàng NCC cho bộ phận Mua hàng, kèm lý do loại gộp từ các dòng.

Thêm ở K7:
  • Màn Phế liệu: cân thực tế (chế độ kiểm kê) + nút Bán phế liệu, luôn kèm
    dải chú thích "tiền bán phế liệu không phải lợi nhuận tăng thêm".
  • Báo cáo đối chiếu thu hồi theo tháng: dự toán (từ BOM) vs cân thực tế —
    vòng phản hồi cho biết định mức hao hụt đặt đúng hay sai.

Thêm ở K14 (khả dụng thật):
  • Mọi chỗ hỏi "còn lấy được bao nhiêu" nay TRỪ phần phiếu khác đang giữ chỗ
    (stock.quant._dlm_available_qty — một nguồn sự thật cho cả 3 chỗ đọc).
    Trước đó đọc tồn thực ⇒ hai phiếu cùng thấy đủ trên một lô hàng.
  • Màn Tồn kho: 2 cột "Đang giữ chỗ" / "Còn lấy được" hiện mặc định, bấm để
    xem PHIẾU và ĐƠN nào đang giữ.
  • Câu cảnh báo thiếu hàng tách "hết sạch" khỏi "bị phiếu khác giữ hết" —
    hai ca phải làm hai việc khác nhau.

Thêm ở K8:
  • Màn Kiểm kê chung: chế độ kiểm kê native của stock.quant trên mọi vị trí
    nội bộ, nút [Kiểm kê] trên màn Tồn kho. Thủ kho áp được số đếm dù KHÔNG có
    group_stock_manager (§8.3) — nâng quyền có kiểm vai trò ở _apply_inventory,
    vá luôn cùng lỗ hổng cho màn Phế liệu K7.
  • Hàng đợi phiếu: gom mọi phiếu `assigned` thủ kho phụ trách; mỗi dòng mở
    bằng ĐÚNG form chuyên biệt của loại (định tuyến ở picking_todo.js). Thủ kho
    land thẳng vào đây thay vì màn Tồn kho.

Thêm ở K15 (tách kho khỏi xưởng + chữ ký nhận hàng):
  • Cây vị trí tách CHỖ CẤT khỏi CHỖ LÀM. "Kho nhà máy sản xuất" (DL/KHOSX) nay
    là khu gom nhóm thuần chứa Kho nguyên vật liệu + Phế liệu chờ bán; DL/XUONG
    đổi tên thành "Xưởng sản xuất" và trở thành ô LÁ — chỗ công nhân làm việc.
    Vai trò kép cũ (vừa chứa hàng vừa làm cha) từng buộc K11 phải vá bằng luật;
    tách ra thì lỗ `child_of` đóng lại bằng cấu trúc.
  • Ô "Bán thành phẩm" GỘP vào Kho nguyên vật liệu (migration dời tồn rồi lưu
    trữ ô cũ). Đánh đổi đã chốt: đếm vật tư thô lẫn BTP, đổi lại một ô để tìm.
  • Phiếu chuyển kho ra Xưởng sản xuất cần HAI chữ ký, chặn cứng: thủ kho
    [Bàn giao ra xưởng] → bên Kỹ thuật [Xác nhận đã nhận] mới hoàn tất. Chưa ký
    thì hàng vẫn thuộc Kho nguyên vật liệu. Thủ kho CỐ Ý không ký nhận được.

Thêm ở K13 (đầu ra cho nhánh gia công):
  • Màn Nhập thành phẩm (loại [8] NTP, kéo từ B2 về B1): xưởng làm xong thì ghi
    nhận vào Kho thành phẩm (hàng gia công) hoặc Kho nguyên vật liệu (bán thành
    phẩm). Nhập TAY — KHÔNG nổ BOM, KHÔNG trừ vật tư.
  • Dòng sản phẩm dùng chung (Hạng A, `consu`) NAY LÊN phiếu giao hàng. Trước đó
    đơn Hạng A — loại đơn phổ biến nhất — không có chứng từ giao nào và tình
    trạng giao đứng yên "Chưa giao" kể cả khi hàng đã lên xe.

Thêm ở K16 (một mẻ = một chứng từ; bỏ % thu hồi phế liệu):
  • Loại [8] đổi thành "Nhập kho từ xưởng" và ghi TRỌN một mẻ: hàng làm ra +
    phế liệu cân được (nguồn ẢO Sản xuất) và vật tư đã dùng / trả lại (nguồn
    THẬT là Xưởng). Đóng lỗ "thép ma" của K13: 100 cây thép đã thành 10 cái bàn
    nay rời sổ Xưởng thay vì nằm lại vĩnh viễn.
  • KHÔNG còn ô vị trí trên màn: vị trí suy từ vai trò dòng + mặt hàng. Chọn
    nhầm nguồn = Xưởng cho thành phẩm là ghi tồn ÂM ở chỗ đang có 0, mà Odoo
    không chặn tồn âm nội bộ nên nó hỏng im lặng.
  • Hai bước ĐẢO CHIỀU so với K15: Kỹ thuật lập & bàn giao → Thủ kho đếm thực
    tế, sửa số nếu lệch, rồi ký nhận. Quyền ghi của Kỹ thuật khoá đúng loại
    phiếu này bằng ir.rule, không mở ACL toàn bộ. Loại NTP đặt
    create_backorder='never' — khai 100 nhận 98 thì 2 cái còn ở xưởng.
  • Phiếu cấp vật tư: cờ "Cấp bổ sung ngoài định mức" + lý do BẮT BUỘC, kèm
    bảng đối chiếu "định mức BOM / đã cấp / cộng dồn" khi phiếu gắn đơn. Đây là
    mối nối duy nhất giữa Kho và định mức của Kỹ thuật.
  • BỎ cách tính % thu hồi phế liệu (người dùng chốt 2026-08-13): gỡ màn Đối
    chiếu thu hồi + model `dl.scrap.recovery.report`, gỡ preset "Gom phế liệu"
    (phế liệu khai trên phiếu mẻ). 🔴 Giá vốn vật tư KHÔNG còn được trừ tiền
    phế liệu ⇒ giá chào khách cao lên; migration dl_technical 17.0.2.3.0 đưa
    `recovery_value` của BOM cũ về 0 để hai đường tính giá không lệch nhau.

Thêm ở K17 (bằng chứng hàng loại):
  • Ảnh chụp hàng lỗi đính theo TỪNG DÒNG bị loại trên phiếu kiểm (nút máy ảnh
    chỉ hiện ở dòng có số Loại > 0), rồi tự có mặt ở phiếu Trả hàng NCC và phiếu
    Hoá phế liệu. Trước đó tất cả những gì Mua hàng cầm đi đòi NCC là một
    dropdown lý do — NCC chối là hết đường.
  • Bằng chứng KHOÁ sau khi xác nhận kiểm, chặn ở tầng server chứ không chỉ
    readonly trên view: ảnh thêm được sau khi biết NCC cãi gì thì không còn là
    bằng chứng. Cần bổ sung muộn thì đính vào chatter, tách khỏi bản gốc.
  • Thiếu ảnh chỉ CẢNH BÁO (dải vàng gọi đích danh mặt hàng), cố ý không chặn
    xác nhận — chặn thì thủ kho ca đêm chụp bừa cho qua cổng.
  • Biên bản hàng không đạt (PDF) trên phiếu Trả hàng NCC: gom lý do + số lượng
    + SỐ LÔ + ảnh bằng chứng vào một tờ ký được, hai chỗ ký. Dựng thuần Python
    bằng reportlab, dùng lại font tiếng Việt đã đăng ký ở dl_sale — KHÔNG
    wkhtmltopdf. Bản in được lưu thành đính kèm + ghi chatter: ba tháng sau còn
    trả lời được "hôm đó đưa NCC đúng cái gì".
    🔴 CỐ Ý KHÔNG CÓ GIÁ — biên bản nói về HÀNG; in số tiền trước khi đàm phán
    là tự chốt mức giảm trừ hộ NCC.
  • Nút [Gửi biên bản qua email] gửi thẳng cho NCC: dựng biên bản rồi mở trình
    soạn thư đã đính sẵn file và điền sẵn NCC, người gửi đọc lại mới bấm Gửi
    (cùng khuôn gửi báo giá của dl_sale). SMTP lấy từ odoo.conf.
    🔴 Nút GỬI hẹp hơn nút IN: in là việc của kho (kẹp vào hàng lúc xe NCC tới
    lấy) nên không khoá vai trò; còn gửi là mở đầu cuộc đàm phán giảm trừ, chỉ
    Mua hàng/Admin/CEO — chặn ở TẦNG SERVER chứ không chỉ `groups` trên view.
    Thư cũng KHÔNG CÓ GIÁ, cùng luật với tờ biên bản.

Thêm ở K15–K16 (kiểm tra kho & điều phối đơn hàng):
  • Nổ BOM thành nhu cầu vật tư (dl.bom._dlm_explode_requirements): bù trừ BTP
    theo tầng — có sẵn cụm hàn thì dùng, chỉ nổ BOM con cho ĐÚNG phần thiếu.
    Trước đó BOM chỉ được dùng để tính TIỀN, chưa ai từng hỏi nó SỐ LƯỢNG.
  • Màn "Điều phối đơn hàng" của Thủ kho: một nút, ba nhánh hàng (đặt riêng /
    SKU gia công / thương mại), sinh phiếu giao cho phần lấy được ngay + MỘT
    phiếu cấp vật tư cho cả đơn + đẩy phần thiếu sang Mua hàng.
  • 🔴 KHÔNG tạo loại hoạt động thứ 10: phiếu Chuyển kho ra Xưởng đã có sẵn hai
    chữ ký (K15) và bảng đối chiếu định mức (K16). Thêm loại mới là chép lại
    bốn cơ chế để chúng lệch nhau về sau.
  • Bảng đối chiếu định mức nay dùng CHUNG hàm nổ BOM: trước đó nó chỉ cộng một
    tầng nên khi xưởng được cấp THÉP (vì hết BTP) thì bảng so thép với khung
    bàn — hai mặt hàng khác nhau, cả hai dòng đều 0.

KHÔNG dựng lại tầng "hub" (màn lưới thẻ trung chuyển): tầng đó đã bị gỡ khỏi cả
hệ thống, điều hướng đi thẳng qua submenu rail.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    # ⚠️ dl_sale làm dl_inventory chuyển từ nhánh song song sang SAU dl_sale
    # trong thứ tự cài (K6 _inherit dl.sale.order). Khai tường minh, không dựa
    # vào phụ thuộc bắc cầu — xem bảng đồ thị phụ thuộc ở CLAUDE.md.
    "depends": ["dl_base", "dl_product", "dl_partner", "dl_sale", "stock"],
    "data": [
        # ACL phải nạp trước mọi thứ chạm dữ liệu.
        "security/ir.model.access.csv",
        "security/groups_stock_link.xml",
        # Seed bố cục kho — TẠO loại hoạt động (picking_type_qc, ...).
        "data/stock_inventory_layout.xml",
        # ⚠️ Nạp SAU seed: rule neo vào sequence_code của loại hoạt động ở trên.
        "security/ir_rule.xml",
        "data/rbac_features.xml",
        # Mẫu thư gửi NCC — nạp TRƯỚC view: action tra bằng env.ref.
        "data/vendor_return_mail_template.xml",
        "views/picking_views.xml",
        "views/transfer_views.xml",
        "views/fg_receipt_views.xml",
        "views/delivery_views.xml",
        "views/vendor_return_views.xml",
        # Dialog gộp Tải về / Gửi biên bản trên phiếu Trả hàng NCC.
        "wizard/vendor_return_export_wizard_views.xml",
        # K12 — nạp TRƯỚC stock_quant_views.xml: nút [Chuyển thành phế liệu]
        # trên màn Tồn kho gọi action trả về form khai ở đây.
        "views/to_scrap_views.xml",
        "views/stock_quant_views.xml",
        "views/stock_lot_views.xml",
        "views/scrap_views.xml",
        # K16 — màn Điều phối (tree/form riêng cho Thủ kho, KHÔNG có cột tiền).
        "views/dispatch_views.xml",
        # Kế thừa form dl.sale.order ⇒ nạp sau khi action phiếu giao đã có.
        "views/sale_order_views_ext.xml",
        # menus.xml nạp CUỐI: menuitem tham chiếu action khai ở các file trên.
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # SCSS — token & mixin dùng chung ở dl_base nạp trước theo thứ tự
            # phụ thuộc; đây chỉ còn style theo màn của dl_inventory.
            "dl_inventory/static/src/scss/stock_list.scss",
            "dl_inventory/static/src/js/nav_patch.js",
            # Định tuyến hàng đợi phiếu (K8): mỗi dòng mở đúng form chuyên biệt.
            "dl_inventory/static/src/js/picking_todo.js",
            # Chipbar trạng thái cho màn Nhận hàng / Kiểm hàng.
            "dl_inventory/static/src/views/picking_list_controller.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
