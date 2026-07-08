/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const QUOTE_HOME_ACTION = "dl_sale.action_dl_quotation_home";

function wireQuote(items) {
    const item = items && items.find((i) => i.key === "quotation");
    if (item) {
        item.actionXmlId = QUOTE_HOME_ACTION;
    }
}

patch(DlHome.prototype, {
    setup() {
        super.setup(...arguments);
        wireQuote(this.navItems);
    },
});

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireQuote(this.railItems);
    },
});
