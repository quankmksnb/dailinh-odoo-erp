/** @odoo-module **/

// ============================================================================
//  Nguồn điều hướng dùng CHUNG cho Trang chủ (DlHome) và Rail (DlmRail).
//
//  Nguyên tắc phân quyền (RBAC): KHÔNG hardcode vai trò. Mỗi entry khai báo một
//  hoặc nhiều xmlid menu; card/rail-item CHỈ hiện khi có ÍT NHẤT một menu nằm
//  trong cây menu mà menuService trả về — vốn đã được Odoo lọc theo res.groups
//  (ir.ui.menu.load_menus) và tự ẩn menu rỗng. User không có quyền ⇒ menu vắng
//  mặt ⇒ entry biến mất hoàn toàn.
//
//  ENTRIES chỉ là TRÌNH BÀY + trỏ menu (icon/màu/mô tả + action launcher tuỳ
//  chọn). Danh sách xmlid trong "menus" là để CHECK QUYỀN (có mặt trong cây) và
//  làm đích mở mặc định — KHÔNG phải khai báo quyền.
// ============================================================================

export const DLM_ROOT_XMLID = "dl_base.menu_dl_root";

// Thứ tự entry = thứ tự card trên Trang chủ và item trên Rail.
//   menus  : ưu tiên trái→phải; menu accessible đầu tiên = đích mở mặc định.
//   action : (tuỳ chọn) xmlid launcher curated → click mở thẳng action này.
//   expand : (tuỳ chọn) rail xổ menu con của menu (module chưa có launcher).
const ENTRIES = [
    {
        key: "customer",
        name: "Khách hàng",
        icon: "fa-users",
        color: "#5b53d6",
        subtitle: "Danh bạ khách hàng & liên hệ",
        menus: ["dl_partner.menu_dl_sale_customer"],
    },
    {
        key: "supplier",
        name: "NCC / Thầu phụ",
        icon: "fa-truck",
        color: "#0d9488",
        subtitle: "Nhà cung cấp & thầu phụ",
        menus: ["dl_partner.menu_dl_sale_supplier", "dl_partner.menu_dl_sale_supplier_readonly"],
    },
    {
        key: "quotation",
        name: "Báo giá",
        icon: "fa-file-text-o",
        color: "#2563eb",
        subtitle: "Yêu cầu báo giá & Báo giá",
        menus: ["dl_sale.menu_dl_sale_quotation", "dl_technical.menu_rfq_parent"],
        action: "dl_sale.action_dl_quotation_home",
    },
    {
        key: "product",
        name: "Sản phẩm",
        icon: "fa-cube",
        color: "#1b9e6f",
        subtitle: "Thành phẩm, bán thành phẩm & nhóm SP",
        menus: ["dl_product.menu_dl_product_root"],
        expand: true,
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        icon: "fa-cogs",
        color: "#7c3aed",
        subtitle: "BOM, bản vẽ & công thức tham số",
        menus: ["dl_base.menu_dl_technical"],
        action: "dl_technical.action_dl_technical_home",
    },
    {
        key: "material",
        name: "Vật tư",
        icon: "fa-cubes",
        color: "#d38a1e",
        subtitle: "Danh mục vật tư & bảng giá",
        menus: ["dl_base.menu_dl_material"],
        expand: true,
    },
    {
        key: "config",
        name: "Cấu hình",
        icon: "fa-sliders",
        color: "#4a5568",
        subtitle: "Tham số giá, phân quyền & danh mục dùng chung",
        menus: ["dl_base.menu_dl_config"],
        action: "dl_config.action_dl_config_home",
    },
];

/**
 * Node menu con ĐẦU TIÊN (duyệt sâu) có action. Cần vì menuService.selectMenu của
 * Odoo 17 KHÔNG tự dẫn vào menu con — gọi selectMenu trên menu không có action sẽ
 * không làm gì. Menu cha (vd Sản phẩm/Vật tư) phải tự tìm màn con hợp lệ để mở.
 * childrenTree đã lọc theo RBAC nên node trả về luôn là màn user được phép.
 */
export function firstActionable(node) {
    if (!node) {
        return null;
    }
    if (node.actionID) {
        return node;
    }
    for (const child of node.childrenTree || []) {
        const found = firstActionable(child);
        if (found) {
            return found;
        }
    }
    return null;
}

// Lập chỉ mục mọi menu (mọi độ sâu) trong app DLM theo xmlid. Chỉ chứa menu
// user ĐƯỢC PHÉP (menuService đã lọc theo res.groups).
function buildMenuIndex(menuService) {
    const index = {};
    const root = menuService.getApps().find((app) => app.xmlid === DLM_ROOT_XMLID);
    if (!root) {
        return index;
    }
    const walk = (node) => {
        for (const child of node.childrenTree || []) {
            if (child.xmlid) {
                index[child.xmlid] = child;
            }
            walk(child);
        }
    };
    walk(menuService.getMenuAsTree(root.id));
    return index;
}

/**
 * Danh sách card/điều hướng mà user hiện tại ĐƯỢC PHÉP truy cập.
 *
 * @param {object} menuService  service "menu" của web client
 * @returns {Array<{key, name, icon, color, subtitle, action, node, target, expand}>}
 *          - action : xmlid launcher curated (nếu có) → doAction; ngược lại null
 *          - node   : node menu mốc (dùng để xổ con ở rail khi expand)
 *          - target : menu con đầu tiên có action → selectMenu (khi không launcher)
 */
export function getModules(menuService) {
    const index = buildMenuIndex(menuService);
    const cards = [];
    for (const e of ENTRIES) {
        const node = e.menus.map((xmlid) => index[xmlid]).find(Boolean);
        if (!node) {
            continue; // không menu nào accessible ⇒ ẩn card
        }
        const action = e.action || null;
        cards.push({
            key: e.key,
            name: e.name,
            icon: e.icon,
            color: e.color,
            subtitle: e.subtitle,
            action,
            node,
            target: action ? null : firstActionable(node),
            expand: !!e.expand,
        });
    }
    return cards;
}
