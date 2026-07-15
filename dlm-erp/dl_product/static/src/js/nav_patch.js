/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const PRODUCT_ACTION = "dl_product.action_dl_product_home";
const PRICING_ACTION = "dl_product.action_dl_pricing_home";

function wireItem(items, key, actionXmlId) {
  const item = items && items.find((i) => i.key === key);
  if (item && !item.actionXmlId) {
    item.actionXmlId = actionXmlId;
  }
}

patch(DlHome.prototype, {
  setup() {
    super.setup(...arguments);
    wireItem(this.cards, "product", PRODUCT_ACTION);
    wireItem(this.cards, "pricing", PRICING_ACTION);
  },
});

patch(DlmRail.prototype, {
  setup() {
    super.setup(...arguments);
    wireItem(this.railItems, "product", PRODUCT_ACTION);
    wireItem(this.railItems, "pricing", PRICING_ACTION);
  },
});
