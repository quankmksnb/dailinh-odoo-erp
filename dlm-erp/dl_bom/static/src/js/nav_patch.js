/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const TECHNICAL_ACTION = "dl_bom.action_dl_technical_home";

function wireTechnical(items) {
    const item = items && items.find((i) => i.key === "technical");
    if (item && !item.actionXmlId) {
        item.actionXmlId = TECHNICAL_ACTION;
    }
}

patch(DlHome.prototype, {
    setup() {
        super.setup(...arguments);
        wireTechnical(this.navItems);
    },
});

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireTechnical(this.railItems);
    },
});
