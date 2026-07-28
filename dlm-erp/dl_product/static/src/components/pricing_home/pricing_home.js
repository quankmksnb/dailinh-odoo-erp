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
    menuXmlIds: ["dl_product.menu_dl_pricing_trading"],
  },
  {
    key: "material_price",
    name: "Bảng giá Vật tư",
    desc: "Danh sách Vật tư & giá bán",
    icon: "fa-list-alt",
    actionXmlId: "dl_product.action_dl_product_pricing_material",
    menuXmlIds: ["dl_product.menu_dl_pricing_material"],
  },
];

export class DlPricingHome extends Component {
  static template = "dl_product.DlPricingHome";
  static props = { ...standardActionServiceProps };

  setup() {
    this.actionService = useService("action");
    this.menuService = useService("menu");
    this._dlmApp = this.menuService
      .getApps()
      .find((app) => app.xmlid === "dl_base.menu_dl_root");
  }

  get cards() {
    return CARDS.filter((card) => this._resolveCardMenu(card));
  }

  _resolveCardMenu(card) {
    if (!this._dlmApp) return null;
    const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
    for (const xmlid of card.menuXmlIds || []) {
      const menu = this._findMenuByXmlId(tree, xmlid);
      if (menu?.actionID) return menu;
    }
    return null;
  }

  _findMenuByXmlId(node, xmlid) {
    if (!node) return null;
    if (node.xmlid === xmlid) return node;
    for (const child of node.childrenTree || []) {
      const found = this._findMenuByXmlId(child, xmlid);
      if (found) return found;
    }
    return null;
  }

  openCard(actionXmlId) {
    if (!actionXmlId) {
      return;
    }
    this.actionService.doAction(actionXmlId);
  }
}

registry.category("actions").add("dl_product.DlPricingHome", DlPricingHome);
