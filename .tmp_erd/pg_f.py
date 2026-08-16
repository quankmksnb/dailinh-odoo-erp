# -*- coding: utf-8 -*-
"""Sub-ERD F — Inventory (E30–E37).

Nguồn: §2 Group F (E30–E37) · §3.4 Inventory branch · §4.7 (kèm "Bảy điểm phải giải
thích được khi bảo vệ trang F") · §4.9 seam S4–S8, S10 · §5 ghi chú 1–3, 5.

Bảy điểm của §4.7 được hiện thực trên trang này như sau:
  1. STOCK_LOCATION đệ quy ................ hình thoi `parent_of` + note_loc
  2. STOCK_DOCUMENT tự tham chiếu ......... hình thoi `originates_from` + note_origin
  3. cặp 1—1 Nhận hàng → Kiểm & cất ....... chú thích trên chính hình thoi đó (ràng buộc,
                                            không phải cấu trúc ⇒ không vẽ hộp lớp con)
  4. HAI vai tới STOCK_LOCATION ........... `from_location` / `to_location` + note_roles
  5. LINE ↔ LOT là N:M CÓ THUỘC TÍNH ...... hộp thuộc tính treo trên hình thoi `assigns`
  6. STOCK_BALANCE khoá tổ hợp 3 quan hệ .. `adjusted_by` chạy ngược chiều trực giác;
                                            cạnh phiếu→dòng để ĐƠN (partial) + note_adj
  7. SCRAP_RECONCILIATION dẫn xuất ........ hộp nét đứt tím + 3 cạnh suy diễn
"""
from erd_lib import Page, LEGEND_TEXT, E_DERIV, E_ATTR


def build():
    p = Page(6, 'F. Kho - nhap, kiem, cat, giao, phe lieu', 3050, 2450)
    p.title('Sub-ERD F &#8212; Inventory: Kho &#183; Vị trí &#183; Phiếu kho &#183; '
            'Lô &#183; Tồn kho',
            'Sở hữu: WAREHOUSE · STOCK_LOCATION · OPERATION_TYPE · STOCK_DOCUMENT(+LINE) · '
            'LOT · STOCK_BALANCE · SCRAP_RECONCILIATION <i>(derived)</i>&#160;—&#160;'
            'entity biên: SUPPLIER · CUSTOMER · USER (A) · SALES_ORDER (D) · ITEM · UOM (B) · '
            'BOM_MATERIAL_LINE (C)')

    # ================================================== cấu hình kho (trái)
    p.entity('wh', 'WAREHOUSE', 150, 260)
    p.entity('ot', 'OPERATION TYPE', 720, 260)
    p.entity('loc', 'STOCK LOCATION', 150, 680)

    p.rel('r_defines', 'defines', 470, 252)
    p.link('wh', 'r_defines', '1')
    p.link('r_defines', 'ot', 'N', total=True)

    p.rel('r_wh_loc', 'contains', 185, 460)
    p.link('wh', 'r_wh_loc', '1')
    p.link('r_wh_loc', 'loc', 'N', total=True)

    # đệ quy: khu → vị trí con (§5-2)
    p.rel('r_parent', 'parent_of', 30, 840)
    p.link('loc', 'r_parent', '1', exit_=('0.2', '1'), entry=('0.5', '0'))
    p.link('r_parent', 'loc', 'N', exit_=('1', '0.5'), entry=('0.6', '1'),
           pts=[(276, 877)])

    # ================================================== chứng từ kho (giữa)
    p.entity('user', 'USER  (A)', 1030, 170, kind='ext')
    p.entity('supp', 'SUPPLIER  (A)', 1290, 170, kind='ext')
    p.entity('cust', 'CUSTOMER  (A)', 1550, 170, kind='ext')
    p.entity('so', 'SALES ORDER  (D)', 1810, 170, kind='ext')

    p.entity('doc', 'STOCK DOCUMENT', 1150, 760)

    p.rel('r_classif', 'classifies', 760, 500, w=190)
    p.link('ot', 'r_classif', '1', exit_=('0.2', '1'))
    p.link('r_classif', 'doc', 'N', entry=('0', '0.4'), total=True)

    p.rel('r_hand', 'handles', 1045, 430)
    p.link('user', 'r_hand', '1')
    p.link('r_hand', 'doc', 'N', entry=('0.1', '0'))

    p.rel('r_deliv', 'delivers', 1305, 430)
    p.link('supp', 'r_deliv', '1')
    p.link('r_deliv', 'doc', 'N', entry=('0.35', '0'))

    p.rel('r_recv', 'receives', 1565, 430)
    p.link('cust', 'r_recv', '1')
    p.link('r_recv', 'doc', 'N', entry=('0.6', '0'))

    p.rel('r_rel', 'releases', 1825, 430)
    p.link('so', 'r_rel', '1')
    p.link('r_rel', 'doc', 'N', entry=('0.85', '0'))

    # đệ quy: phiếu nhận gốc — xương sống truy vết đối ngoại (§4.7-2, §4.7-3)
    p.rel('r_origin', 'originates_from\n<i>(phiếu nhận gốc)</i>', 1470, 620, w=200, h=90)
    p.link('doc', 'r_origin', '1', exit_=('1', '0.2'), entry=('0', '0.8'))
    p.link('r_origin', 'doc', '1', exit_=('0', '0.2'), entry=('0.9', '0'),
           pts=[(1339, 657)])

    # ================================================== dòng phiếu (weak)
    p.entity('line', 'STOCK DOCUMENT LINE', 1130, 1180, kind='weak', w=250)

    # ⚠ §4.7-6: KHÔNG total ở đầu dòng phiếu — dòng điều chỉnh kiểm kê không có phiếu cha
    p.rel('r_contains', 'contains', 1185, 950, ident=True)
    p.link('doc', 'r_contains', '1')
    p.link('r_contains', 'line', 'N')

    # hai vai khác nhau tới cùng một thực thể (§4.7-4, §5-3)
    p.rel('r_from', 'from_location\n<i>vai: nguồn</i>', 700, 1150, w=190, h=90)
    p.link('line', 'r_from', 'N', exit_=('0', '0.4'), total=True)
    p.link('r_from', 'loc', '1', exit_=('0', '0.5'), entry=('0.8', '1'),
           pts=[(430, 1187), (430, 760)])

    p.rel('r_to', 'to_location\n<i>vai: đích</i>', 700, 1320, w=190, h=90)
    p.link('line', 'r_to', 'N', exit_=('0', '0.9'), total=True)
    p.link('r_to', 'loc', '1', exit_=('0', '0.5'), entry=('0.4', '1'),
           pts=[(500, 1357), (500, 800)])

    # ================================================== lô & truy vết (phải)
    p.entity('lot', 'LOT', 1720, 940)
    p.entity('item', 'ITEM + 4 lớp con  (B)', 2200, 1180, kind='ext')
    p.entity('uom', 'UNIT OF MEASURE  (B)', 2200, 1400, kind='ext')

    # N:M CÓ THUỘC TÍNH — cố ý không tách thực thể yếu (§4.7-5)
    p.rel('r_assigns', 'assigns', 1470, 1050)
    p.link('line', 'r_assigns', 'M', exit_=('1', '0.2'))
    p.link('r_assigns', 'lot', 'N', entry=('0', '0.8'))
    p.attrs('a_assigns', 'thuộc tính của quan hệ', [
        'Quantity per lot <i>(số lượng theo lô)</i>',
    ], 1440, 1150, w=230)
    p.attach('r_assigns', 'a_assigns')

    p.rel('r_moves', 'moves', 1800, 1172)
    p.link('line', 'r_moves', 'N', total=True)
    p.link('r_moves', 'item', '1')

    p.rel('r_meas', 'measured_in', 1800, 1392, w=190)
    p.link('line', 'r_meas', 'N', exit_=('1', '0.9'), total=True)
    p.link('r_meas', 'uom', '1')

    p.rel('r_lot_item', 'identifies_batch_of', 2050, 932, w=200)
    p.link('lot', 'r_lot_item', 'N')
    p.link('r_lot_item', 'item', '1', entry=('0.2', '0'), total=False)

    p.rel('r_lot_sup', 'supplied_by', 2050, 700, w=190)
    p.link('lot', 'r_lot_sup', 'N', exit_=('0.8', '0'))
    p.link('r_lot_sup', 'supp', '1', entry=('0.5', '0'), exit_=('0.5', '0'),
           pts=[(2120, 120), (1395, 120)])

    # ba thuộc tính truy vết đóng dấu MỘT LẦN ở phiếu nhận đầu tiên (§2/E35)
    p.rel('r_stamp', 'stamped_by_receipt', 1470, 880, w=200)
    p.link('lot', 'r_stamp', 'N', entry=('1', '0.5'))
    p.link('r_stamp', 'doc', '1', exit_=('0', '0.5'), entry=('1', '0.7'))

    # ================================================== tồn kho
    p.entity('bal', 'STOCK BALANCE', 1080, 1700)

    # §4.7-6: chiều NGƯỢC trực giác — kiểm kê là trạng thái đếm trên tồn kho, đếm xong
    # mới sinh chuyển động điều chỉnh (dòng phiếu KHÔNG có phiếu cha)
    p.rel('r_adjust', 'adjusted_by', 1140, 1450, w=190)
    p.link('bal', 'r_adjust', '1', exit_=('0.3', '0'))
    p.link('r_adjust', 'line', 'N', entry=('0.1', '1'))

    p.rel('r_holds', 'holds', 700, 1692)
    p.link('bal', 'r_holds', 'N', total=True)
    p.link('r_holds', 'loc', '1', exit_=('0', '0.5'), entry=('1', '0.8'),
           pts=[(600, 1729), (600, 726)])

    p.rel('r_stocked', 'stocked_as', 1600, 1692, w=190)
    p.link('bal', 'r_stocked', 'N', total=True)
    p.link('r_stocked', 'item', '1', exit_=('1', '0.5'), entry=('1', '0.5'),
           pts=[(2470, 1729), (2470, 1209)])

    p.rel('r_held', 'held_as', 1420, 1600, w=190)
    p.link('bal', 'r_held', 'N', exit_=('1', '0.5'), entry=('0', '0.5'),
           total=True)
    p.link('r_held', 'lot', '1', exit_=('1', '0.5'), entry=('0', '0.8'),
           pts=[(1680, 1637), (1680, 986)])

    # ================================================== đối chiếu phế liệu (dẫn xuất)
    p.entity('scrap', 'SCRAP RECOVERY\nRECONCILIATION  <i>(derived)</i>',
             1750, 2100, kind='derived', w=280, h=64)
    p.entity('bml', 'BOM MATERIAL LINE  (C)', 2100, 2270, kind='ext')

    # ba quan hệ suy diễn; SCRAP ở đầu "một" vì là bản tổng hợp theo THÁNG (§4.7-7)
    p.rel('r_actual', 'actual_from', 1450, 2092, derived=True, w=190)
    p.edge('scrap', 'r_actual', '1', E_DERIV)
    p.edge('r_actual', 'line', 'N', E_DERIV, exit_=('0', '0.5'),
           entry=('0.9', '1'), pts=[(1400, 2129), (1400, 1300)])

    p.rel('r_scopes', 'scopes_period', 2200, 2092, derived=True, w=190)
    p.edge('scrap', 'r_scopes', '1', E_DERIV)
    p.edge('r_scopes', 'so', 'N', E_DERIV, exit_=('1', '0.5'),
           entry=('1', '0.5'), pts=[(2880, 2129), (2880, 199)])

    p.rel('r_est', 'estimates_from', 1820, 2260, derived=True, w=190)
    p.edge('scrap', 'r_est', 'M', E_DERIV, exit_=('0.4', '1'))
    p.edge('r_est', 'bml', 'N', E_DERIV)

    # ================================================== thuộc tính
    p.attrs('a_wh', 'WAREHOUSE', [
        '<u>Warehouse code</u> (<b>DL</b> &#8212; đúng MỘT thể hiện)',
        'Warehouse name',
        '<b>Reception mode</b>: two-step (receive &#8594; inspect &amp; put away)',
        'Root location of the location tree',
        'Default operation types',
    ], 60, 120, w=330)
    p.attach('wh', 'a_wh')

    p.attrs('a_ot', 'OPERATION TYPE', [
        '<u>Operation code</u> (NH · KC · CK · GH · TR · BPL)',
        'Operation name · Display order',
        'Direction: incoming / outgoing / internal',
        'Default source &amp; destination location',
        '<i>XSX · NTP đã seed nhưng thuộc sub-ERD G</i>',
    ], 700, 120, w=320)
    p.attach('ot', 'a_ot')

    p.attrs('a_loc', 'STOCK LOCATION', [
        'Không có mã &#8212; định danh bởi <u>đường dẫn đầy đủ</u>',
        'Location name · <b>Parent location (đệ quy)</b>',
        'Usage kind: internal / partner / virtual',
        'Full path (DL / Khu nhập hàng / Vật tư…)',
        '<b>Nằm dưới khu phế liệu?</b> (báo cáo duyệt cây con)',
    ], 60, 940, w=330)
    p.attach('loc', 'a_loc')

    p.attrs('a_doc', 'STOCK DOCUMENT', [
        '<u>Document number</u> DL/&lt;operation&gt;/00001',
        'Operation type &#8212; <b>thuộc tính phân lớp</b>',
        'Partner: NCC khi nhập · KH khi xuất',
        'Scheduled date · Effective date · Source document',
        '<b>Origin receipt</b> (tự tham chiếu)',
        'Linked sales order <i>(chỉ phiếu giao)</i> · Thủ kho phụ trách',
        'Total quantity · <b>Rejected total</b>',
        'Inspection outcome · Aggregated rejection reasons',
        'Blocked flag + inline blocking message',
        'Draft → Waiting → Ready → Done ‖ Cancelled',
    ], 700, 830, w=330)
    p.attach('doc', 'a_doc')

    p.attrs('a_line', 'STOCK DOCUMENT LINE <i>(weak)</i>', [
        '<u>(Stock document, Item, Line sequence)</u>',
        'Item · Unit of measure · Demanded quantity',
        '<b>Passed quantity</b> <i>(chính là done-qty, chỉ đổi nhãn)</i>',
        '<b>Rejected quantity</b> + rejection reason bắt buộc',
        'Rejection note <i>(bắt buộc khi lý do = Khác)</i>',
        'Source &amp; destination location',
        '<b>is-adjustment flag</b> &#8212; dòng kiểm kê không có phiếu cha,',
        '&#160;&#160;định danh bởi <i>(Item, Location, Timestamp)</i>',
    ], 900, 1280, w=330)
    p.attach('line', 'a_line')

    p.attrs('a_lot', 'LOT', [
        '<u>Lot number</u> LO/2026/00001 <i>(Đại Linh tự sinh)</i>',
        'Item · <b>Supplier</b> · <b>Receipt date</b>',
        '<b>Originating receipt document</b>',
        "Supplier's own lot number <i>(tham chiếu, free text)</i>",
        '<i>Ba thuộc tính đậm: chỉ-ghi-một-lần</i>',
    ], 1980, 780, w=300)
    p.attach('lot', 'a_lot')

    p.attrs('a_bal', 'STOCK BALANCE', [
        'Không có mã &#8212; <u>(Item, Location, Lot)</u>',
        'On-hand · Reserved · Available quantity',
        'Supplier &amp; receipt date <i>(thừa kế từ lô)</i>',
        '<i>Lớp kiểm kê:</i> counted quantity · count-entered flag',
        '&#160;&#160;difference vs. system',
        '<i>Lớp phế liệu:</i> scrap unit price · line value',
        '&#160;&#160;<b>đây là giá BÁN, không phải giá vốn</b> &#8212;',
        '&#160;&#160;nên thủ kho được xem (§8.3)',
        'Không nhập trực tiếp: dòng sinh/mất theo chứng từ',
    ], 1000, 1830, w=340)
    p.attach('bal', 'a_bal')

    p.attrs('a_scrap', 'SCRAP RECOVERY RECONCILIATION', [
        '<b>Dẫn xuất &#8212; không có khoá lưu trữ</b>, một dòng / <u>tháng</u>',
        'Period (month)',
        'Actual quantity into the scrap zone',
        'Quantity sold out of it',
        '<b>Estimated quantity</b> <i>(từ BOM của đơn đã chốt trong kỳ)</i>',
        'Difference · Verdict: Short / Matches / Over estimate',
    ], 2400, 2230, w=300)
    p.attach('scrap', 'a_scrap')

    # ================================================== ghi chú
    p.note('<b>⚠ Chỗ dễ vẽ sai nhất của trang F (§4.7-6)</b><br/>'
           'Cạnh <b>contains → STOCK DOCUMENT LINE</b> là <b>đường ĐƠN</b> '
           '(tham gia <i>bộ phận</i>), <b>không</b> phải đường kép &#8212; '
           'dù dòng phiếu là thực thể yếu.<br/>'
           'Lý do: <b>dòng điều chỉnh kiểm kê không có phiếu cha</b>. Odoo 17 '
           'áp kết quả kiểm kê bằng cách sinh thẳng chuyển động '
           '<i>is-adjustment</i>, <b>không</b> tạo phiếu. Đối ứng là vị trí ảo '
           '<i>Điều chỉnh kiểm kê</i> &#8658; hàng không tự sinh ra hay biến mất, '
           'kể cả khi sửa sai.<br/>'
           'Những dòng đó định danh bằng <i>(Item, Location, Timestamp)</i>.',
           60, 1100, w=560, h=210)

    p.note('<b>Hai vai tới cùng một thực thể (§4.7-4, §5-3)</b><br/>'
           '<b>STOCK_DOCUMENT_LINE → STOCK_LOCATION</b> xuất hiện <b>hai lần</b>: '
           '<i>từ vị trí</i> và <i>tới vị trí</i>. Elmasri bắt buộc đặt '
           '<b>tên vai (role name)</b> khi hai quan hệ nối cùng một cặp thực thể '
           '&#8212; thiếu tên vai là <b>sơ đồ sai nghĩa</b>, không chỉ là thiếu nhãn.',
           60, 1340, w=560, h=150)

    p.note('<b>STOCK BALANCE &#8212; khoá tổ hợp từ BA quan hệ</b><br/>'
           'Không có khoá riêng: định danh bởi <b>(ITEM, LOCATION, LOT)</b> '
           '&#8658; cả ba cạnh <i>stocked_as · holds · held_as</i> đều là '
           '<b>tham gia toàn bộ</b> phía tồn kho.<br/>'
           '<b>Kiểm kê là một trạng thái đếm, không phải chứng từ</b> (§0.2-6) '
           '&#8658; nó <i>không</i> có hộp riêng trên sơ đồ. Vì thế quan hệ '
           '<b>adjusted_by chạy ngược chiều trực giác</b>: tồn kho <i>sinh ra</i> '
           'dòng chuyển động, chứ không phải ngược lại.',
           60, 1520, w=560, h=190)

    p.legend(LEGEND_TEXT, 60, 1740, w=560, h=340)

    p.note('<b>KHÔNG xuất hiện trên trang F &#8212; và vì sao</b><br/>'
           '&#8226; <b>Kiểm kê</b> &#8212; là trạng thái đếm trên STOCK_BALANCE '
           '(§0.2-6), không phải chứng từ.<br/>'
           '&#8226; <b>Chi tiết dòng phiếu theo lô</b> &#8212; đã diễn tả đủ bằng '
           'quan hệ N:M có thuộc tính (§4.7-5).<br/>'
           '&#8226; <b>Tuyến nhập 2 bước · nhóm cung ứng</b> &#8212; cơ chế nội bộ '
           'sinh ra cặp 1—1 <i>Nhận → Kiểm</i>, không phải dữ liệu nghiệp vụ.<br/>'
           '&#8226; <b>XSX · NTP</b> &#8212; đã seed nhưng thuộc sub-ERD G (§4.8).<br/>'
           '&#8226; <b>Sáu lớp con của Phiếu kho</b> &#8212; xem ghi chú bên phải.',
           60, 2110, w=560, h=210)

    p.note('<b>Ký hiệu riêng trang F</b><hr size="1"/>'
           '&#9633; Hộp <b>nét đứt tím</b> &#8212; thực thể <b>dẫn xuất</b> '
           '(derived): không lưu trữ, tính lại mỗi lần đọc.<br/>'
           '&#9671; Hình thoi <b>nét đứt tím</b> + cạnh nét đứt tím &#8212; '
           '<b>quan hệ suy diễn</b>: dữ liệu đọc lại từ nơi khác, không có khoá ngoại.<br/>'
           '<i>Khác với đường chấm tím ở chú giải chung</i> &#8212; đường chấm là '
           '<i>tham chiếu mềm / snapshot</i> (sub-ERD D).',
           650, 2110, w=320, h=210)

    p.note('<b>Tự tham chiếu = xương sống truy vết đối ngoại (§4.7-2, 3)</b><br/>'
           'Phiếu <b>Kiểm &amp; cất</b> và phiếu <b>Trả hàng NCC</b> đều neo về '
           '<b>phiếu Nhận hàng</b>, <i>không</i> neo vào nhau &#8658; khiếu nại NCC '
           'luôn quy được về <b>lần giao hàng</b> đã gây ra nó.<br/>'
           '<b>Ràng buộc trên quan hệ này:</b> <i>mỗi phiếu Nhận hàng sinh đúng MỘT '
           'phiếu Kiểm &amp; cất.</i> Đây là <b>ràng buộc, không phải cấu trúc</b> '
           '&#8212; nếu để hệ thống gộp theo mặc định (theo vị trí + loại hoạt động, '
           '<b>không</b> theo đối tác), hai phiếu nhận của hai NCC sẽ gộp thành một '
           'phiếu kiểm và phiếu trả hàng sẽ <b>ghi sai tên NCC</b>.',
           2250, 130, w=500, h=210)

    p.note('<b>Vì sao KHÔNG vẽ hộp cho 6 lớp con của Phiếu kho (§0.2-3, §5-1)</b><br/>'
           'Nhận hàng · Kiểm &amp; cất · Chuyển kho · Giao hàng · Trả hàng NCC · '
           'Bán phế liệu <b>dùng chung đúng một bộ thuộc tính</b>, chỉ khác tuyến đi '
           'và quy trình.<br/>'
           'Bản thân <b>thuộc tính phân lớp lại là một thực thể</b> '
           '(<b>OPERATION_TYPE</b>) &#8658; chuyên biệt hoá ở đây được xác định bởi '
           '<b>quan hệ <i>classifies</i></b>, vẽ thêm 6 hộp rỗng chỉ làm sơ đồ ồn.',
           2250, 370, w=500, h=200)

    p.note('<b>Cây vị trí &#8212; và vì sao phế liệu là vị trí THẬT (§4.7-1)</b><br/>'
           '3 khu × 5 vị trí con, quan hệ đệ quy <i>parent_of</i>.<br/>'
           'Cả ba khu đều khai là vị trí <b>nội bộ</b> (không phải <i>view</i>) &#8212; '
           'khu <i>view</i> sẽ mất tiền tố <code>DL/</code> trên đường dẫn hiển thị.<br/>'
           'Khu <b>Phế liệu chờ bán</b> (<code>DL/XUONG/PL</code>) là vị trí nội bộ '
           'thật, <b>không</b> dùng vị trí phế liệu ảo của Odoo: phế liệu là '
           '<b>tài sản bán lại được đã trừ trước vào giá vốn</b> lúc báo giá, nên '
           'phải <b>cân được, đếm được, bán được</b>.',
           2530, 830, w=340, h=250)

    p.note('<b>Vòng phản hồi phế liệu (§4.7-7) &#8212; đọc đúng nghĩa</b><br/>'
           'So <b>dự toán thu hồi</b> (từ định mức của các đơn đã chốt trong kỳ) với '
           '<b>cân thực tế</b> (hàng vào khu phế liệu).<br/>'
           'Tiền bán phế liệu <b>không phải lãi thêm</b> &#8212; giá trị thu hồi đã bị '
           'trừ trước vào giá vốn lúc báo giá. Vậy nên:<br/>'
           '&#8226; thu hồi <b>ít hơn</b> dự toán = <b>đang lỗ ngầm</b>;<br/>'
           '&#8226; thu hồi <b>nhiều hơn</b> = định mức hao hụt đặt quá tay.<br/>'
           'Số thực tế đọc từ <b>STOCK_DOCUMENT_LINE</b>, <b>không</b> từ '
           'STOCK_BALANCE: tồn kho là ảnh chụp hiện tại, không có chiều thời gian '
           'để chia kỳ.<br/>'
           'Đây chính là seam <b>S10</b> đóng vòng về quan hệ '
           '<i>recovers_as_scrap</i> ở sub-ERD B (§4.3).',
           2530, 1500, w=340, h=290)

    return p
