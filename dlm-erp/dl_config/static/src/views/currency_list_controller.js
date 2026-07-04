/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

// filter: tên filter trong search view. key "all" = không lọc trạng thái.
const CHIPS = [
    { key: "all",      label: "Tất cả",   filter: null },
    { key: "active",   label: "Đang dùng", filter: "filter_active" },
    { key: "inactive", label: "Đã ẩn",    filter: "filter_inactive" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

export class DlCurrencyListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "loại tiền";
    }

    // active_test:false để đếm cả bản ghi đã ẩn (giống context của action).
    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "res.currency",
            [],
            ["active"],
            ["active"],
            { context: { active_test: false } }
        );
        const counts = { active: 0, inactive: 0 };
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? 0;
            counts[g.active ? "active" : "inactive"] = n;
            total += n;
        }
        counts.all = total;
        this.dlCounts = counts;
    }

    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && FILTER_NAMES.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._stateFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        const chip = CHIPS.find((c) => c.filter === active.name);
        return chip ? chip.key : "all";
    }

    // Single-select: tắt hết filter trạng thái rồi bật 1
    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._stateFilters();
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
        return chip.key === "all" ? this.dlCounts.all : this.dlCounts[chip.key];
    }
}

registry.category("views").add("dl_currency_list", {
    ...listView,
    Controller: DlCurrencyListController,
});
