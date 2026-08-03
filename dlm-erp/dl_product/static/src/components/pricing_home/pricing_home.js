/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
  {
    key: "trading_price",
    name: "Bảng giá SP thương mại",
    desc: "SP thương mại + giá NCC/giá bán/biên LN — Mua hàng gắn giá NCC",
    icon: "fa-tags",
    actionXmlId: "dl_product.action_dl_product_pricing",
    menuXmlIds: ["dl_product.menu_dl_pricing_trading"],
  },
  {
    key: "material_price",
    name: "Bảng giá Vật tư",
    desc: "Giá mua theo nhà cung cấp và thời gian hiệu lực",
    icon: "fa-list-alt",
    actionXmlId: "dl_product.action_dl_supplierinfo_material_full",
    menuXmlIds: [
      "dl_product.menu_dl_pricing_material",
      "dl_product.menu_dl_pricing_material_view",
    ],
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
    return CARDS.map((card) => {
      const menu = this._resolveCardMenu(card);
      if (!menu) {
        return null;
      }
      return {
        ...card,
        // The visible menu has already been filtered by Odoo according to the
        // current user's groups. Reusing its numeric action keeps the card in
        // sync with those permissions (editable for Accounting/Admin, read-only
        // for CEO/Sales Manager) and avoids resolving a forbidden XML ID.
        resolvedActionId: menu.actionID || card.actionXmlId,
      };
    }).filter(Boolean);
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

  openCard(actionId) {
    if (!actionId) {
      return;
    }
    this.actionService.doAction(actionId);
  }
}

registry.category("actions").add("dl_product.DlPricingHome", DlPricingHome);
