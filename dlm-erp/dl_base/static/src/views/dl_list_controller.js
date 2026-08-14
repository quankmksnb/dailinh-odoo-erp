/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useEffect } from "@odoo/owl";
import { buildActionsMenu } from "../js/actions_menu";

export class DlListBaseController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dlCounts = {};
        onWillStart(async () => {
            await this._loadCounts();
        });

        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            this._dlRenderChrome(root);
        });
    }

    _dlRenderChrome(root) {
        this._relocateCreateButton(root);
        this._renderActionsMenu(root);
        this._renderFilterDropdowns(root);
        this._renderChipbar(root);
        this._renderFooter(root);
        this._wireSearchClear(root);
    }

    // ── Xoá trắng ô tìm kiếm ⇒ bỏ luôn điều kiện đang lọc ────────────────
    // Vì sao phải tự làm: Odoo giữ điều kiện tìm trong FACET (viên chip trong
    // thanh tìm kiếm), gõ chữ rồi Enter là chữ chuyển vào facet. Muốn bỏ lọc thì
    // bấm dấu × trên facet — nhưng giao diện DL ẩn toàn bộ facet
    // (global_cp.scss: `.o_searchview .o_searchview_facet { display: none }`)
    // để nhường chỗ cho chipbar riêng. Hệ quả: người dùng xoá chữ trong ô mà
    // danh sách vẫn lọc, không thấy gì để bấm, phải sang màn khác rồi quay lại.
    //
    // Chỉ gỡ facet loại "field" (do gõ chữ). KHÔNG đụng facet của filter/group_by
    // — đó là các chip trạng thái và nhóm-theo mà người dùng chọn riêng.
    _wireSearchClear(root) {
        const input = root.querySelector(".o_searchview input.o_searchview_input");
        if (!input || input.dataset.dlSearchClear) {
            return;
        }
        input.dataset.dlSearchClear = "1";
        const clearIfEmpty = () => {
            if (input.value.trim()) {
                return false;
            }
            const sm = this.env.searchModel;
            const groups = new Set(
                (sm.facets || [])
                    .filter((f) => f.type === "field")
                    .map((f) => f.groupId)
            );
            groups.forEach((groupId) => sm.deactivateGroup(groupId));
            return groups.size > 0;
        };
        input.addEventListener("input", clearIfEmpty);
        // Enter trên ô đã trống: người dùng xoá chữ rồi bấm Enter theo phản xạ.
        input.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && clearIfEmpty()) {
                ev.stopPropagation();
                ev.preventDefault();
            }
        });
        // Esc: lối thoát quen thuộc, cũng trả danh sách về đầy đủ.
        input.addEventListener("keydown", (ev) => {
            if (ev.key === "Escape") {
                input.value = "";
                clearIfEmpty();
            }
        });
    }

    get dlChips() {
        return [];
    }
    get dlCountNoun() {
        return "";
    }
    get dlFilterDropdowns() {
        return [];
    }
    async _loadCounts() {}
    _activeChip() {
        return "all";
    }
    _selectChip() {}
    _chipCount(chip) {
        return this.dlCounts[chip.key];
    }
    _afterChipbar() {}

    _relocateCreateButton(root) {
        const buttons = root.querySelector(".o_control_panel_main_buttons");
        const actions = root.querySelector(".o_control_panel_actions");
        if (buttons && actions && buttons.parentElement !== actions) {
            buttons.classList.add("dl-create-cluster");
            actions.appendChild(buttons);
        }
    }

    _renderActionsMenu(root) {
        const host =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_actions");
        buildActionsMenu(host, [
            { label: "Nhập dữ liệu", icon: "fa-upload", onClick: () => this._dlImport() },
            { label: "Xuất dữ liệu", icon: "fa-download", onClick: () => this.onExportData() },
        ]);
    }

    _dlImport() {
        const sm = this.env.searchModel;
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { model: sm.resModel, context: sm.context },
        });
    }

    // ── Filter dropdowns (external <select>) ──────────────────────────────
    // Chỉ hiện các filter thực sự có trong search view của action hiện tại —
    // cùng 1 js_class được nhiều action dùng lại với search view khác nhau
    // (VD: màn Sản phẩm lọc Gia công/Thương mại, màn Vật tư lọc Vật tư/BTP,
    // màn Bảng giá không có filter loại SP).
    _dlAvailableDropdowns() {
        const sm = this.env.searchModel;
        const available = new Set(
            sm.getSearchItems((i) => i.type === "filter").map((i) => i.name)
        );
        return this.dlFilterDropdowns
            .map((dd) => ({
                ...dd,
                filters: dd.filters.filter((f) => available.has(f.name)),
            }))
            .filter((dd) => dd.filters.length);
    }

    _renderFilterDropdowns(root) {
        const dropdowns = this._dlAvailableDropdowns();
        if (!dropdowns.length) {
            return;
        }
        const actions = root.querySelector(".o_control_panel_actions");
        if (!actions) {
            return;
        }

        let container = actions.querySelector(".dl-filter-group");
        if (!container) {
            container = document.createElement("div");
            container.className = "dl-filter-group";
            const createCluster = actions.querySelector(".dl-create-cluster");
            if (createCluster) {
                actions.insertBefore(container, createCluster);
            } else {
                actions.appendChild(container);
            }
        }

        for (const dd of dropdowns) {
            let select = container.querySelector(`select[data-dl-filter="${dd.key}"]`);
            if (!select) {
                select = document.createElement("select");
                select.className = "dl-filter-select";
                select.dataset.dlFilter = dd.key;

                const allOpt = document.createElement("option");
                allOpt.value = "";
                allOpt.textContent = dd.label;
                select.appendChild(allOpt);

                for (const f of dd.filters) {
                    const opt = document.createElement("option");
                    opt.value = f.name;
                    opt.textContent = f.label;
                    select.appendChild(opt);
                }

                select.addEventListener("change", () =>
                    this._onFilterDropdownChange(dd, select.value)
                );
                container.appendChild(select);
            }

            select.value = this._getActiveDropdownFilter(dd) || "";
        }
    }

    _getActiveDropdownFilter(dd) {
        const sm = this.env.searchModel;
        const names = dd.filters.map((f) => f.name);
        const items = sm.getSearchItems(
            (i) => i.type === "filter" && names.includes(i.name)
        );
        const active = items.find((i) => i.isActive);
        return active ? active.name : "";
    }

    _onFilterDropdownChange(dd, value) {
        const sm = this.env.searchModel;
        const names = dd.filters.map((f) => f.name);
        const items = sm.getSearchItems(
            (i) => i.type === "filter" && names.includes(i.name)
        );
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        if (value) {
            const it = items.find((i) => i.name === value);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }

    // ── Chipbar ────────────────────────────────────────────────────────────
    _renderChipbar(root) {
        if (!this.dlChips.length) {
            return;
        }
        const cp = root.querySelector(".o_control_panel");
        if (!cp) {
            return;
        }
        let bar = cp.querySelector(".dl-chipbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "dl-chipbar";
            for (const c of this.dlChips) {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "dl-chip";
                chip.dataset.key = c.key;
                chip.innerHTML =
                    '<span class="dl-chip-label"></span>' +
                    '<span class="dl-chip-count"></span>';
                chip.addEventListener("click", () => this._selectChip(c.key));
                bar.appendChild(chip);
            }
            cp.appendChild(bar);
        }
        const active = this._activeChip();
        for (const c of this.dlChips) {
            const chip = bar.querySelector(`.dl-chip[data-key="${c.key}"]`);
            if (!chip) {
                continue;
            }
            chip.querySelector(".dl-chip-label").textContent = c.label;
            const n = this._chipCount(c) ?? 0;
            chip.querySelector(".dl-chip-count").textContent = `· ${n}`;
            chip.classList.toggle("is-active", c.key === active);
        }
        this._afterChipbar(root, bar);
    }

    _renderFooter(root) {
        const renderer = root.querySelector(".o_list_renderer");
        if (!renderer) {
            return;
        }

        // Ẩn pager range "1-15 / N" mặc định ở control panel — thay bằng pager SỐ.
        const cpPager = root.querySelector(".o_cp_pager");
        if (cpPager) {
            cpPager.style.display = "none";
        }

        // Chế độ NHÓM: pager control-panel lúc này phân trang theo SỐ NHÓM (gây
        // nhầm là pager của nhóm cuối) → ẩn footer đếm; thay pager mặc định của
        // TỪNG nhóm bằng pager SỐ ở góc phải header nhóm.
        if (this.model.root.isGrouped) {
            const groupedFooter = renderer.querySelector(".dl-list-footer");
            if (groupedFooter) {
                groupedFooter.style.display = "none";
            }
            this._renderGroupNumberedPagers(root);
            return;
        }

        // List phẳng: dòng phân trang (footer) LUÔN hiện cho mọi màn — trống nếu
        // dưới 'limit', có pager SỐ nếu vượt. KHÔNG hiện tổng bản ghi nữa.
        let footer = renderer.querySelector(".dl-list-footer");
        if (!footer) {
            footer = document.createElement("div");
            footer.className = "dl-list-footer";
            const count = document.createElement("span");
            count.className = "dl-list-count";
            footer.appendChild(count);
            renderer.appendChild(footer);
        }
        const list = this.model.root;
        footer.querySelector(".dl-list-count").style.display = "none";

        let host = footer.querySelector(".dl-pager");
        if (!host) {
            host = document.createElement("div");
            host.className = "dl-pager";
            footer.appendChild(host);
        }
        // Sau khi load trang mới phải re-render CONTROLLER (không chỉ renderer)
        // để useEffect chạy lại _dlRenderChrome — nếu không, phần chrome chèn tay
        // (avatar chữ cái, chipbar…) sẽ mất khi chuyển trang. Giống pager gom nhóm.
        this._syncNumberedPager(host, list, async (offset, limit) => {
            await list.load({ offset, limit });
            this.render(true);
        });
        footer.style.display = "";
    }

    // Thay pager mặc định của MỖI nhóm bằng pager SỐ (khi list gom nhóm). Ghép
    // theo thứ tự: nhóm thứ i trong model ↔ dòng .o_group_header thứ i (renderer
    // duyệt list.groups đúng thứ tự) — chỉ áp dụng gom nhóm 1 cấp như các màn DL.
    _renderGroupNumberedPagers(root) {
        const groups = this.model.root.groups || [];
        const headers = root.querySelectorAll("tr.o_group_header");
        headers.forEach((header, i) => {
            const group = groups[i];
            const list = group && group.list;
            const flex = header.querySelector(".o_group_name .d-flex.align-items-center");
            if (!list || !flex) {
                return;
            }

            // Ẩn pager range mặc định của nhóm (native Odoo).
            const nativePager = header.querySelector(".o_pager");
            const nativeWrap = nativePager && nativePager.closest(".ms-auto");
            if (nativeWrap) {
                nativeWrap.style.display = "none";
            }

            // Nhóm đang GẬP chưa nạp sublist → list.limit có thể undefined;
            // fallback theo limit của list gốc, tránh chia cho 1 ra vô số trang.
            const limit = list.limit || this.model.root.limit || 80;
            const total = list.count || 0;
            const pageCount = Math.max(1, Math.ceil(total / limit));

            let host = flex.querySelector(":scope > .dl-group-pager");
            // Chỉ hiện pager khi nhóm ĐANG MỞ và có >1 trang (giống native
            // showGroupPager) — nhóm đang gập thì không phân trang.
            if (group.isFolded || pageCount <= 1) {
                if (host) {
                    host.remove();
                }
                return;
            }
            if (!host) {
                host = document.createElement("div");
                host.className = "dl-pager dl-group-pager";
                // Chặn click nổi lên header (kẻo bấm số trang lại gập/mở nhóm).
                host.addEventListener("click", (ev) => ev.stopPropagation());
                flex.appendChild(host);
            }
            this._syncNumberedPager(host, list, async (offset, lim) => {
                await list.load({ offset, limit: lim });
                this.render(true);
            });
        });
    }

    // Dựng lại nội dung pager SỐ cho 1 list (phẳng hoặc list của 1 nhóm).
    // Trả về true nếu có pager (>1 trang), false nếu ẩn.
    _syncNumberedPager(host, list, doLoad) {
        const limit = list.limit || 1;
        const total = list.count || 0;
        const pageCount = Math.max(1, Math.ceil(total / limit));
        if (pageCount <= 1) {
            host.innerHTML = "";
            host.style.display = "none";
            return false;
        }
        host.style.display = "";
        const current = Math.floor((list.offset || 0) / limit) + 1;
        this._mountNumberedPager(host, {
            current,
            pageCount,
            onSelect: (p) => {
                if (p < 1 || p > pageCount || p === current) {
                    return;
                }
                doLoad((p - 1) * limit, limit);
            },
        });
        return true;
    }

    _mountNumberedPager(host, { current, pageCount, onSelect }) {
        host.classList.add("dl-pager");
        host.innerHTML = "";
        const addBtn = (label, { page = null, active = false, disabled = false, nav = false }) => {
            const b = document.createElement("button");
            b.type = "button";
            b.className =
                "dl-pager-btn" + (active ? " is-active" : "") + (nav ? " dl-pager-nav" : "");
            b.textContent = label;
            b.disabled = disabled;
            b.addEventListener("click", (ev) => {
                ev.stopPropagation();
                if (page !== null && !disabled && !active) {
                    onSelect(page);
                }
            });
            host.appendChild(b);
        };
        addBtn("‹", { page: current - 1, disabled: current <= 1, nav: true });
        for (const it of this._dlPageItems(current, pageCount)) {
            if (it === "…") {
                const s = document.createElement("span");
                s.className = "dl-pager-ellipsis";
                s.textContent = "…";
                host.appendChild(s);
            } else {
                addBtn(String(it), { page: it, active: it === current });
            }
        }
        addBtn("›", { page: current + 1, disabled: current >= pageCount, nav: true });
    }

    // Dãy số trang có "…": luôn giữ trang 1, trang cuối và current ±1; thêm 2/3
    // (đầu) hoặc n-1/n-2 (cuối) cho đỡ trống.
    _dlPageItems(current, pageCount) {
        const set = new Set([1, pageCount, current, current - 1, current + 1]);
        if (current <= 3) {
            set.add(2);
            set.add(3);
        }
        if (current >= pageCount - 2) {
            set.add(pageCount - 1);
            set.add(pageCount - 2);
        }
        const pages = [...set].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b);
        const items = [];
        let prev = 0;
        for (const p of pages) {
            if (p - prev > 1) {
                items.push("…");
            }
            items.push(p);
            prev = p;
        }
        return items;
    }
}

// Generic DL list (dl_list): các màn không cần chip/đếm-noun riêng (VD Loại /
// Hình dạng đo lường). Kế thừa base để dùng CHUNG một footer + pager SỐ và ẩn
// pager range mặc định — tránh tình trạng mỗi màn một kiểu phân trang.
export class DlListController extends DlListBaseController {
    get dlCountNoun() {
        return "bản ghi";
    }
}

registry.category("views").add("dl_list", {
    ...listView,
    Controller: DlListController,
});
