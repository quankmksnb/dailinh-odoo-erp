/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
  {
    key: "products",
    name: "Sản phẩm",
    desc: "Sản phẩm gia công / Thương mại",
    icon: "fa-cube",
    actionXmlId: "dl_product.action_dl_product_full",
  },
  {
    key: "materials",
    name: "Vật tư",
    desc: "Vật tư / Bán thành phẩm",
    icon: "fa-industry",
    actionXmlId: "dl_product.action_dl_material_full",
  },
  {
    key: "categories",
    name: "Danh mục sản phẩm",
    desc: "Quản lý danh mục Sản phẩm / Vật tư",
    icon: "fa-cubes",
    actionXmlId: "dl_product.action_dl_category_full",
  },
];

export class DlProductHome extends Component {
  static template = "dl_product.DlProductHome";
  static props = { ...standardActionServiceProps };

  setup() {
    this.actionService = useService("action");
    this.cards = CARDS;
  }

  openCard(actionXmlId) {
    if (!actionXmlId) {
      return;
    }
    // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
    this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
  }
}

registry.category("actions").add("dl_product.DlProductHome", DlProductHome);
