/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";
import { avatarInitial, avatarColor } from "@dl_base/js/avatar_letter";

const CHIPS = [
    { key: "all",        label: "Tất cả",       filter: null,                ctype: null },
    { key: "individual", label: "Cá nhân",      filter: "filter_individual", ctype: "individual" },
    { key: "company",    label: "Doanh nghiệp", filter: "filter_company",    ctype: "company" },
    { key: "dealer",     label: "Đại lý",       filter: "filter_dealer",     ctype: "dealer" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);


export class DlCustomerListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "khách hàng";
    }

    get dlFilterDropdowns() {
        return [
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "active", label: "Đang hợp tác" },
                    { name: "inactive", label: "Ngừng hợp tác" },
                ],
            },
            {
                key: "date",
                label: "Tất cả thời gian",
                filters: [
                    { name: "date_today", label: "Hôm nay" },
                    { name: "date_7days", label: "7 ngày qua" },
                    { name: "date_30days", label: "30 ngày qua" },
                ],
            },
        ];
    }

    _dlRenderChrome(root) {
        super._dlRenderChrome(root);
        this._renderAvatars(root);
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "res.partner",
            [["partner_role", "in", ["customer", "both"]]],
            ["partner_type"],
            ["partner_type"],
            // Đếm cả KH "Ngừng hợp tác" (active=False) để khớp với danh sách —
            // action mở KH đặt active_test:False nên pager hiện cả KH ngừng hợp tác.
            { context: { active_test: false } }
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.partner_type_count ?? 0;
            counts[g.partner_type] = n;
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
        return chip.key === "all" ? this.dlCounts.all : this.dlCounts[chip.ctype];
    }

    _afterChipbar(root, bar) {
        const sw = root.querySelector("nav.o_cp_switch_buttons");
        if (sw && sw.parentElement !== bar) {
            sw.classList.add("dl-view-switch");
            bar.appendChild(sw);
        }
    }

    _renderAvatars(root) {
        const records = this.model.root.records || [];
        const rows = root.querySelectorAll(".o_list_table tbody tr.o_data_row");
        rows.forEach((row, i) => {
            const cell = row.querySelector("td[name='avatar_128']");
            const nameCell = row.querySelector("td[name='name']");
            if (!cell || !nameCell) {
                return;
            }
            const rec = records[i];
            const hasPhoto = !!(rec && rec.data && rec.data.dlm_has_photo);

            if (hasPhoto) {
                cell.classList.add("dl-has-photo");
                const ava = cell.querySelector(".dl-letter-ava");
                if (ava) {
                    ava.remove();
                }
                return;
            }

            cell.classList.remove("dl-has-photo");
            const name = (nameCell.textContent || "").trim();
            let ava = cell.querySelector(".dl-letter-ava");
            if (!ava) {
                ava = document.createElement("span");
                ava.className = "dl-letter-ava";
                cell.appendChild(ava);
            }
            const c = avatarColor(name);
            ava.textContent = avatarInitial(name);
            ava.style.background = c.bg;
            ava.style.color = c.fg;
        });
    }
}

registry.category("views").add("dl_customer_list", {
    ...listView,
    Controller: DlCustomerListController,
});
