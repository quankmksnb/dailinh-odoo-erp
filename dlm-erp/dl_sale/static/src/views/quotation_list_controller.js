/** @odoo-module **/
// ============================================================
//  DL Quotation List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_quotation_list" (dùng ở quotation_views.xml).
//  Phần RIÊNG của báo giá: chip lọc theo TRẠNG THÁI có số đếm. Bấm chip =
//  bật/tắt filter sẵn trong search view nên đồng bộ hoàn toàn với bộ lọc
//  gốc của Odoo.
//
//  QUAN TRỌNG — single-select phải quản TẤT CẢ filter trạng thái (kể cả
//  composite open/closed/history + filter mặc định 'open' trên action), vì
//  mọi filter state nằm CHUNG một nhóm OR trong search view. Nếu chỉ tắt
//  vài filter, composite 'open' vẫn active ⇒ 'open OR draft' ⇒ chip không
//  lọc được (bug cũ chỉ quản 4 filter draft/sent/approved/rejected).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useEffect } from "@odoo/owl";
import { formatMonetary } from "@web/views/fields/formatters";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Tab phân đoạn (review UX list #f1): CHỈ 3 nhóm gộp + "Tất cả" làm thanh
// điều hướng chính, thay cho 10 chip phẳng khó quét. Trạng thái chi tiết dời
// vào dropdown "Trạng thái chi tiết" (dlFilterDropdowns) — chọn chi tiết thì
// bỏ segment (loại trừ nhau) vì mọi filter state nằm chung một nhóm OR.
// "open" = pipeline đang sống (= filter mặc định của action); "closed" = các
// kết cục đóng; "history" = superseded (bản cũ bị thay thế).
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "open", label: "Đang xử lý" },
    { key: "closed", label: "Đã đóng" },
    { key: "history", label: "Lịch sử phiên bản" },
];

// Trạng thái chi tiết đưa vào dropdown phụ. name trùng <filter> trong search view.
const DETAIL_FILTERS = [
    { name: "draft", label: "Nháp" },
    { name: "approved", label: "Đã duyệt nội bộ" },
    { name: "sent", label: "Đã gửi khách" },
    { name: "revision_requested", label: "Yêu cầu điều chỉnh" },
    { name: "accepted", label: "Khách đồng ý" },
    { name: "ordered", label: "Đã lên đơn" },
    { name: "rejected", label: "Từ chối" },
    { name: "expired", label: "Hết hiệu lực" },
    { name: "cancelled", label: "Đã hủy" },
    { name: "superseded", label: "Đã thay bản mới" },
];

// Toàn bộ filter trạng thái mà chip cần quản để single-select sạch — gồm cả
// composite (open/closed/history) lẫn từng trạng thái. Bấm 1 chip: tắt hết
// những cái đang active trong tập này rồi bật đúng 1.
const MANAGED_FILTERS = [
    "open", "closed", "history",
    "draft", "approved", "sent", "revision_requested",
    "accepted", "ordered", "rejected", "expired",
    "cancelled", "superseded",
];

export class DlQuotationListController extends DlListBaseController {
    setup() {
        super.setup();
        // Tổng giá trị pipeline theo bộ lọc hiện tại (review UX list #f4). Đếm
        // qua readGroup trên ĐÚNG domain đang xem (không chỉ trang hiện tại) —
        // recompute mỗi khi domain đổi (chip/dropdown/search).
        useEffect(
            () => {
                this._refreshPipelineTotal();
            },
            () => [JSON.stringify(this.model.root.domain)]
        );
    }

    async _refreshPipelineTotal() {
        const domain = this.model.root.domain || [];
        const res = await this.orm.readGroup(
            "dl.quotation",
            domain,
            ["amount_total:sum"],
            []
        );
        const sum = (res[0] && res[0].amount_total) || 0;
        const rec = this.model.root.records[0];
        const currencyId =
            rec && rec.data.currency_id ? rec.data.currency_id[0] : false;
        this.dlAmountText = `Tổng giá trị: ${formatMonetary(sum, { currencyId })}`;
        const el =
            this.rootRef.el && this.rootRef.el.querySelector(".dl-list-amount");
        if (el) {
            el.textContent = this.dlAmountText;
        }
    }

    // Chèn ô tổng giá trị vào footer (ngay sau số đếm bản ghi).
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
    }

    get dlChips() {
        return CHIPS;
    }

    get dlFilterDropdowns() {
        return [
            { key: "qstate", label: "Trạng thái chi tiết", filters: DETAIL_FILTERS },
        ];
    }

    get dlCountNoun() {
        return "báo giá";
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "dl.quotation",
            [],
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
        // Số đếm cho các chip gộp (đồng bộ đúng domain composite ở search view).
        const sum = (...keys) => keys.reduce((s, k) => s + (counts[k] || 0), 0);
        counts.open = sum(
            "draft", "approved", "sent", "revision_requested", "accepted", "ordered"
        );
        counts.closed = sum("rejected", "expired", "cancelled");
        counts.history = counts.superseded || 0;
        this.dlCounts = counts;
    }

    // Tất cả filter trạng thái trong search view (composite + từng state).
    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && MANAGED_FILTERS.includes(i.name)
        );
    }

    // Chip đang active = segment đang bật. Không filter nào → "Tất cả". Nếu đang
    // bật một trạng thái CHI TIẾT (từ dropdown) thì KHÔNG segment nào sáng ("") —
    // dropdown phản ánh lựa chọn đó. Mặc định action bật 'open' ⇒ "Đang xử lý".
    _activeChip() {
        const chipKeys = new Set(CHIPS.map((c) => c.key));
        const active = this._stateFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        return chipKeys.has(active.name) ? active.name : "";
    }

    // Single-select: tắt MỌI filter trạng thái đang active rồi bật đúng 1.
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

    // Dropdown "Trạng thái chi tiết" LOẠI TRỪ với segment: chọn chi tiết thì bỏ
    // hết segment (open/closed/history) đang bật rồi bật đúng trạng thái đó — nếu
    // không 'open OR draft' vẫn = open (mọi filter state chung nhóm OR).
    _onFilterDropdownChange(dd, value) {
        const sm = this.env.searchModel;
        for (const it of this._stateFilters()) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        if (value) {
            const it = this._stateFilters().find((i) => i.name === value);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }
}

registry.category("views").add("dl_quotation_list", {
    ...listView,
    Controller: DlQuotationListController,
});
