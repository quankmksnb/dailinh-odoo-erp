/** @odoo-module **/
// ============================================================
//  DL Quote Approval List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_quote_approval_list" (quote_approval_views.xml).
//  Phần RIÊNG: chip lọc theo trạng thái yêu cầu duyệt có số đếm (Tất cả ·
//  Chờ duyệt · Đã duyệt · Từ chối · Đã hủy). Chip bật/tắt filter sẵn trong
//  search view nên đồng bộ với bộ lọc gốc của Odoo.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useEffect } from "@odoo/owl";
import { formatMonetary } from "@web/views/fields/formatters";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "pending", label: "Chờ duyệt" },
    { key: "approved", label: "Đã duyệt" },
    { key: "rejected", label: "Từ chối" },
    { key: "cancelled", label: "Đã hủy" },
];
const STATE_KEYS = ["pending", "approved", "rejected", "cancelled"];

export class DlQuoteApprovalListController extends DlListBaseController {
    setup() {
        super.setup();
        // Tổng giá trị hàng chờ theo bộ lọc hiện tại (review UX inbox #f3).
        // q_amount_total là related non-stored → readGroup không sum được; đọc
        // qua searchRead trên đúng domain rồi cộng ở client (hàng chờ duyệt nhỏ).
        useEffect(
            () => {
                this._refreshQueueTotal();
            },
            () => [JSON.stringify(this.model.root.domain)]
        );
    }

    async _refreshQueueTotal() {
        const domain = this.model.root.domain || [];
        const rows = await this.orm.searchRead(
            "dl.pricing.approval.request",
            domain,
            ["q_amount_total", "q_currency_id"]
        );
        let sum = 0;
        let currencyId = false;
        for (const r of rows) {
            sum += r.q_amount_total || 0;
            if (!currencyId && r.q_currency_id) {
                currencyId = r.q_currency_id[0];
            }
        }
        this.dlAmountText = `Tổng giá trị chờ: ${formatMonetary(sum, { currencyId })}`;
        const el =
            this.rootRef.el && this.rootRef.el.querySelector(".dl-list-amount");
        if (el) {
            el.textContent = this.dlAmountText;
        }
    }

    _renderFooter(root) {
        super._renderFooter(root);
        const footer = root.querySelector(".dl-list-footer");
        if (!footer) {
            return;
        }
        let amt = footer.querySelector(".dl-list-amount");
        if (!amt) {
            amt = document.createElement("span");
            amt.className = "dl-list-amount";
            const count = footer.querySelector(".dl-list-count");
            if (count) {
                count.after(amt);
            } else {
                footer.appendChild(amt);
            }
        }
        amt.textContent = this.dlAmountText || "";
        // Màn có chipbar nên base ẩn số đếm; nhưng footer vẫn phải hiện để show
        // ô "Tổng giá trị chờ" — bật lại tường minh.
        footer.style.display = "";
    }

    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "yêu cầu";
    }

    async _loadCounts() {
        // Chỉ đếm yêu cầu duyệt BÁO GIÁ — khớp domain của action màn này.
        const groups = await this.orm.readGroup(
            "dl.pricing.approval.request",
            [["request_type", "=", "quote_over_threshold"]],
            ["state"],
            ["state"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.state_count ?? 0;
            counts[g.state] = n;
            total += n;
        }
        counts.all = total;
        this.dlCounts = counts;
    }

    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && STATE_KEYS.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._stateFilters().find((i) => i.isActive);
        return active ? active.name : "all";
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
        if (key !== "all") {
            const it = items.find((i) => i.name === key);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }
}

registry.category("views").add("dl_quote_approval_list", {
    ...listView,
    Controller: DlQuoteApprovalListController,
});
