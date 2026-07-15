/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
  {
    key: "trading_price",
    name: "Bảng giá Sản phẩm thương mại",
    desc: "Giá bán SP thương mại (lst_price) — Kế toán cập nhật",
    icon: "fa-tags",
    actionXmlId: "dl_product.action_dl_product_pricing",
  },
  {
    key: "material_price",
    name: "Bảng giá Vật tư",
    desc: "Giá NCC theo vật tư / SP thương mại + duyệt giá",
    icon: "fa-list-alt",
    actionXmlId: "dl_product.action_dl_supplierinfo_full",
  },
];

export class DlPricingHome extends Component {
  static template = "dl_product.DlPricingHome";
  static props = { ...standardActionServiceProps };

  setup() {
    this.actionService = useService("action");
    this.cards = CARDS;
  }

  openCard(actionXmlId) {
    if (!actionXmlId) {
      return;
    }
    this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
  }
}

registry.category("actions").add("dl_product.DlPricingHome", DlPricingHome);