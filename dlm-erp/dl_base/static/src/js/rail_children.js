/** @odoo-module **/

// ─────────────────────────────────────────────────────────────────────────────
// API DÙNG CHUNG để module nghiệp vụ gắn submenu vào rail.
//
// Vì sao có file này: hàm `wireRailChildren` trước đây được COPY nguyên xi vào
// 4 file nav_patch.js (dl_config / dl_product / dl_technical / dl_sale) — sửa
// hành vi rail phải sửa cả 4 chỗ. CLAUDE.md cấm copy thêm bản thứ 5, nên
// dl_inventory dùng bản dùng chung này.
//
// 4 bản cũ CHƯA chuyển sang đây (chúng đang chạy đúng; đổi là mở rộng phạm vi
// vô cớ). Khi nào đụng tới chúng vì lý do khác thì chuyển dần.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Gắn danh sách mục con vào một nhóm của rail.
 *
 * @param {Array} items - this.railItems trong DlmRail
 * @param {string} key - khoá nhóm (vd "inventory")
 * @param {Array} children - mục con, mỗi mục {key, name, icon, menuXmlIds, preferMenu}
 */
export function wireRailChildren(items, key, children) {
  const item = items && items.find((i) => i.key === key);
  if (item) {
    item.children = children;
  }
}
