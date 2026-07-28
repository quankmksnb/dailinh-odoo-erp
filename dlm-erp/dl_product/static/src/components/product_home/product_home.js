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
    menuXmlIds: [
      "dl_product.menu_dl_product_full",
      "dl_product.menu_dl_product_tech",
      "dl_product.menu_dl_product_view",
    ],
  },
  {
    key: "materials",
    name: "Vật tư",
    desc: "Vật tư / Bán thành phẩm",
    icon: "fa-industry",
    menuXmlIds: [
      "dl_product.menu_dl_material_full",
      "dl_product.menu_dl_material_tech",
      "dl_product.menu_dl_material_view",
    ],
  },
  {
    key: "categories",
    name: "Danh mục",
    desc: "Quản lý Danh mục Sản phẩm và Vật tư",
    icon: "fa-cubes",
    menuXmlIds: [
      "dl_product.menu_dl_category_full",
      "dl_product.menu_dl_category_view",
    ],
  },
];

export class DlProductHome extends Component {
  static template = "dl_product.DlProductHome";
  static props = { ...standardActionServiceProps };

  setup() {
    this.menuService = useService("menu");
    this._dlmApp = this.menuService
      .getApps()
      .find((app) => app.xmlid === "dl_base.menu_dl_root");
  }

  get cards() {
    return CARDS.filter((card) => this._resolveCardMenu(card));
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

  _resolveCardMenu(card) {
    if (!this._dlmApp) return null;
    const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
    for (const xmlid of card.menuXmlIds || []) {
      const menu = this._findMenuByXmlId(tree, xmlid);
      if (menu && this._hasActionableMenu(menu)) return menu;
    }
    return null;
  }

  _hasActionableMenu(menu) {
    if (!menu) return false;
    if (menu.actionID) return true;
    return (menu.childrenTree || []).some((child) => this._hasActionableMenu(child));
  }

  openCard(card) {
    const menu = this._resolveCardMenu(card);
    if (menu) this.menuService.selectMenu(menu);
  }
}

registry.category("actions").add("dl_product.DlProductHome", DlProductHome);
