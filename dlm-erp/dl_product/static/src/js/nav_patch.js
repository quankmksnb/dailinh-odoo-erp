/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";

// Rail: nhóm Sản phẩm & Bảng giá xổ thành mục con điều hướng thẳng.
// preferMenu → mở qua menu để lấy đúng action theo vai trò (bản đầy đủ / kỹ thuật
// / chỉ-đọc khác nhau), không trỏ cứng 1 action bị cấm.
const PRODUCT_CHILDREN = [
  {
    key: "products",
    name: "Sản phẩm",
    icon: "fa-cube",
    preferMenu: true,
    // 1 mục "Sản phẩm" duy nhất, đúng action theo vai trò: Sales dùng
    // menu_dl_product_trading_ba (list đủ loại + create SP thương mại); Admin
    // full, Tech tech, CEO/Trưởng KD view. preferMenu chọn menu đầu user thấy.
    menuXmlIds: [
      "dl_product.menu_dl_product_full",
      "dl_product.menu_dl_product_tech",
      "dl_product.menu_dl_product_trading_ba",
      "dl_product.menu_dl_product_view",
    ],
  },
  {
    key: "materials",
    name: "Vật tư",
    icon: "fa-industry",
    preferMenu: true,
    menuXmlIds: [
      "dl_product.menu_dl_material_full",
      "dl_product.menu_dl_material_tech",
      "dl_product.menu_dl_material_view",
    ],
  },
  {
    // 1 mục duy nhất cho cả cây nhóm. Mục "Nhóm vật tư" riêng đã gỡ: nó chỉ là
    // cùng màn này lọc sẵn nhánh Vật tư, còn quyền ghi theo nhánh do record
    // rule quyết định chứ không do menu.
    key: "categories",
    name: "Nhóm sản phẩm",
    icon: "fa-cubes",
    preferMenu: true,
    menuXmlIds: [
      "dl_product.menu_dl_category_full",
      "dl_product.menu_dl_category_view",
    ],
  },
];

const PRICING_CHILDREN = [
  {
    // Hòm việc EX-13: vật tư thô chưa có giá NCC đang áp dụng. Chỉ Mua hàng/Admin
    // thấy (menuXmlIds → rail tự lọc RBAC như các mục khác). Đặt ĐẦU nhóm vì đây
    // là việc chủ động của Mua hàng.
    key: "needs_price",
    name: "Vật tư chờ định giá",
    icon: "fa-hourglass-half",
    preferMenu: true,
    menuXmlIds: ["dl_product.menu_dl_material_needs_price"],
  },
  {
    // Ngay sau hòm việc: mạch của Mua hàng là "vật tư nào chưa có giá" → "vào
    // nhập giá NCC cho nó". Bản trước chen Bảng giá SP thương mại vào giữa hai
    // bước đó. Đánh đổi: CEO/Trưởng KD chỉ thấy 2 mục ở nhóm này và bảng giá
    // SP thương mại (giá BÁN — thứ họ chốt) nay là mục thứ 2.
    key: "material_price",
    name: "Bảng giá Vật tư",
    icon: "fa-list-alt",
    preferMenu: true,
    menuXmlIds: [
      "dl_product.menu_dl_pricing_material",
      "dl_product.menu_dl_pricing_material_view",
    ],
  },
  {
    key: "trading_price",
    name: "Bảng giá sản phẩm thương mại",
    icon: "fa-tags",
    preferMenu: true,
    // 1 màn product-centric duy nhất; action tự lọc quyền theo vai trò
    // (Mua hàng/Admin sửa, quản lý chỉ xem).
    menuXmlIds: ["dl_product.menu_dl_pricing_trading"],
  },
];

function wireRailChildren(items, key, children) {
  const item = items && items.find((i) => i.key === key);
  if (item) {
    item.children = children;
  }
}

patch(DlmRail.prototype, {
  setup() {
    super.setup(...arguments);
    wireRailChildren(this.railItems, "product", PRODUCT_CHILDREN);
    wireRailChildren(this.railItems, "pricing", PRICING_CHILDREN);
    // Badge "Vật tư chờ định giá": số vật tư chưa có giá NCC áp dụng — cho Mua
    // hàng thấy ngay việc chờ mà không cần mở màn (giống badge "Phê duyệt").
    // Chỉ Mua hàng/Admin thấy mục con này nên vai trò khác không truy vấn thừa.
    const orm = useService("orm");
    this.registerBadge("needs_price", () =>
      orm.call("product.product", "get_needs_price_count", [])
    );
  },
});
