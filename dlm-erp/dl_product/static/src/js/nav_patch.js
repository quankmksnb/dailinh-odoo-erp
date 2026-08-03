/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const PRODUCT_ACTION = "dl_product.action_dl_product_home";
const PRICING_ACTION = "dl_product.action_dl_pricing_home";

// Rail: dẹp hub Sản phẩm & Bảng giá thành mục con điều hướng thẳng.
// preferMenu → mở qua menu để lấy đúng action theo vai trò (bản đầy đủ / kỹ thuật
// / chỉ-đọc khác nhau), không trỏ cứng 1 action bị cấm.
const PRODUCT_CHILDREN = [
  {
    key: "products",
    name: "Sản phẩm",
    icon: "fa-cube",
    preferMenu: true,
    menuXmlIds: [
      "dl_product.menu_dl_product_full",
      "dl_product.menu_dl_product_tech",
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
    key: "categories",
    name: "Danh mục",
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
    key: "trading_price",
    name: "Bảng giá SP thương mại",
    icon: "fa-tags",
    preferMenu: true,
    menuXmlIds: ["dl_product.menu_dl_pricing_trading"],
  },
  {
    key: "material_price",
    name: "Bảng giá Vật tư",
    icon: "fa-list-alt",
    preferMenu: true,
    menuXmlIds: [
      "dl_product.menu_dl_pricing_material",
      "dl_product.menu_dl_pricing_material_view",
    ],
  },
];

// Home (fallback): giữ card mở hub như cũ.
function wireHomeCard(cards, key, actionXmlId) {
  const item = cards && cards.find((i) => i.key === key);
  if (item && !item.actionXmlId) {
    item.actionXmlId = actionXmlId;
  }
}

function wireRailChildren(items, key, children) {
  const item = items && items.find((i) => i.key === key);
  if (item) {
    item.children = children;
  }
}

patch(DlHome.prototype, {
  setup() {
    super.setup(...arguments);
    wireHomeCard(this.cards, "product", PRODUCT_ACTION);
    wireHomeCard(this.cards, "pricing", PRICING_ACTION);
  },
});

patch(DlmRail.prototype, {
  setup() {
    super.setup(...arguments);
    wireRailChildren(this.railItems, "product", PRODUCT_CHILDREN);
    wireRailChildren(this.railItems, "pricing", PRICING_CHILDREN);
  },
});
