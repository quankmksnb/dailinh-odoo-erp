/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

const CHIPS = [
    { key: "all",      label: "Tất cả", filter: null,             type: null },
    { key: "sale",     label: "Bán",    filter: "filter_sale",     type: "sale" },
    { key: "purchase", label: "Mua",    filter: "filter_purchase", type: "purchase" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

export class DlVatListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "loại thuế";
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "account.tax",
            [],
            ["type_tax_use"],
            ["type_tax_use"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.type_tax_use_count ?? 0;
            counts[g.type_tax_use] = n;
            total += n;
        }
        counts.all = total;
        this.dlCounts = counts;
    }

    _typeFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && FILTER_NAMES.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._typeFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        const chip = CHIPS.find((c) => c.filter === active.name);
        return chip ? chip.key : "all";
    }

    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._typeFilters();
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        const chip = CHIPS.find((c) => c.key === key);
        if (chip && chip.filter) {
            const it = items.find((i) => i.name === chip.filter);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }

    _chipCount(chip) {
        return chip.key === "all" ? this.dlCounts.all : this.dlCounts[chip.type];
    }
}

registry.category("views").add("dl_vat_list", {
    ...listView,
    Controller: DlVatListController,
});
