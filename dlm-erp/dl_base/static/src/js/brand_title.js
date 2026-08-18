/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

// tiêu đề tab
patch(WebClient.prototype, {
  setup() {
    super.setup();
    this.title.setParts({ zopenerp: "Đại Linh" });
  },
});
