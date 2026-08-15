/** @odoo-module **/
// ============================================================
//  Danh sách Báo giá — thanh chip lọc theo trạng thái + ô tổng giá trị.
//  Gắn vào tree bằng js_class="dl_quotation_list" (khai ở quotation_views.xml),
//  dựng trên khung chung DlListBaseController. Bấm chip chỉ là bật/tắt các
//  <filter> có sẵn trong search view nên khớp hoàn toàn với bộ lọc gốc Odoo.
//
//  🔴 Chip là chọn-một, mà mọi filter trạng thái nằm chung một nhóm OR trong
//  search view. Nên khi bấm một chip phải tắt HẾT các filter trạng thái đang
//  bật (kể cả các chip gộp open/closed/history và filter mặc định 'open' của
//  action) rồi mới bật đúng một cái. Chỉ tắt vài cái thì 'open' còn sống,
//  thành 'open OR draft', chip không lọc được.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useEffect } from "@odoo/owl";
import { formatMonetary } from "@web/views/fields/formatters";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Thanh chip chính: gộp 10 trạng thái thành 3 nhóm + "Tất cả" cho dễ quét.
// Trạng thái lẻ dời vào dropdown "Trạng thái chi tiết" bên dưới.
//   open    = báo giá đang sống (trùng filter mặc định của action)
//   closed  = đã đóng (từ chối/hết hạn/huỷ)
//   history = bản cũ đã bị thay bản mới
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

// Tất cả filter trạng thái mà chip phải quản để chọn-một cho sạch — cả chip
// gộp lẫn từng trạng thái lẻ. Bấm 1 chip: tắt hết cái đang bật trong danh
// sách này rồi bật đúng 1.
const MANAGED_FILTERS = [
    "open", "closed", "history",
    "draft", "approved", "sent", "revision_requested",
    "accepted", "ordered", "rejected", "expired",
    "cancelled", "superseded",
];

export class DlQuotationListController extends DlListBaseController {
    setup() {
        super.setup();
        // Ô "Tổng giá trị" ở chân danh sách — cộng trên ĐÚNG bộ lọc đang xem
        // (không phải chỉ trang hiện tại), tính lại mỗi khi đổi chip/lọc/tìm.
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
        // Khung chung ẩn chân danh sách khi có chipbar; nhưng ở đây vẫn cần
        // chân để hiện ô "Tổng giá trị" — bật lại.
        footer.style.display = "";
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
        // Số đếm cho 3 chip gộp — cộng đúng theo cách search view gộp.
        const sum = (...keys) => keys.reduce((s, k) => s + (counts[k] || 0), 0);
        counts.open = sum(
            "draft", "approved", "sent", "revision_requested", "accepted", "ordered"
        );
        counts.closed = sum("rejected", "expired", "cancelled");
        counts.history = counts.superseded || 0;
        this.dlCounts = counts;
    }

    // Lấy các <filter> trạng thái trong search view (cả chip gộp lẫn lẻ).
    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && MANAGED_FILTERS.includes(i.name)
        );
    }

    // Chip nào đang sáng. Không lọc gì → "Tất cả". Đang bật một trạng thái lẻ
    // từ dropdown → không chip nào sáng (""). Mặc định action bật 'open'.
    _activeChip() {
        const chipKeys = new Set(CHIPS.map((c) => c.key));
        const active = this._stateFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        return chipKeys.has(active.name) ? active.name : "";
    }

    // Bấm chip: tắt mọi filter trạng thái đang bật rồi bật đúng 1.
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

    // Dropdown "Trạng thái chi tiết" loại trừ với chip gộp: chọn một trạng
    // thái lẻ thì tắt hết chip đang bật rồi bật đúng nó — nếu không 'open OR
    // draft' vẫn ra open (mọi filter chung nhóm OR).
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
