/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const CONFIG_ACTION = "dl_config.action_dl_config_home";

function wireConfig(items) {
    const item = items && items.find((i) => i.key === "config");
    if (item && !item.actionXmlId) {
        item.actionXmlId = CONFIG_ACTION;
    }
}

patch(DlHome.prototype, {
    setup() {
        super.setup(...arguments);
        wireConfig(this.cards);
    },
});

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireConfig(this.railItems);
    },
});
