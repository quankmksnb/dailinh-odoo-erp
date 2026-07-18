/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

const CHIPS = [
    { key: "all",       label: "Tất cả",     filter: null,              type: null },
    { key: "reference", label: "Tham chiếu", filter: "filter_reference", type: "reference" },
    { key: "bigger",    label: "Lớn hơn",    filter: "filter_bigger",    type: "bigger" },
    { key: "smaller",   label: "Nhỏ hơn",    filter: "filter_smaller",   type: "smaller" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

export class DlUomListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "đơn vị";
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "uom.uom",
            [],
            ["uom_type"],
            ["uom_type"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.uom_type_count ?? 0;
            counts[g.uom_type] = n;
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

    // Single-select: tắt hết filter loại rồi bật 1
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

    get dlFilterDropdowns() {
        return [
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "filter_active", label: "Đang dùng" },
                    { name: "filter_inactive", label: "Đã ẩn" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_uom_list", {
    ...listView,
    Controller: DlUomListController,
});
