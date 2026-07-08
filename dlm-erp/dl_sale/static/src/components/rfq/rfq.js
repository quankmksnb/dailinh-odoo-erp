/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const RFQS = [
    {
        id: "bg0048", code: "BG/2026/0048", partner: "Cty TNHH Nội thất Hoà Phát",
        date: "05/07/2026", state: "draft",
        lines: [
            { name: "Tủ bếp trên Acrylic", group: "Tủ bếp", size: "800×720", qty: 4, material: 2400000 },
            { name: "Tủ bếp dưới Acrylic", group: "Tủ bếp", size: "800×810", qty: 4, material: 3100000 },
        ],
    },
    {
        id: "bg0047", code: "BG/2026/0047", partner: "Đinh Thị Thúy",
        date: "04/07/2026", state: "sent",
        lines: [
            { name: "Cửa gỗ HDF sơn", group: "Cửa", size: "800×2100", qty: 6, material: 1850000 },
        ],
    },
    {
        id: "bg0046", code: "BG/2026/0046", partner: "Cty CP Hoàng Gia",
        date: "02/07/2026", state: "approved",
        lines: [
            { name: "Tủ áo 4 cánh MDF", group: "Tủ áo", size: "2000×2400", qty: 2, material: 8200000 },
            { name: "Kệ tivi treo tường", group: "Kệ", size: "1800×450", qty: 2, material: 2650000 },
        ],
    },
    {
        id: "bg0045", code: "BG/2026/0045", partner: "Cty TNHH Minh Anh",
        date: "01/07/2026", state: "draft",
        lines: [
            { name: "Bàn làm việc chân sắt", group: "Bàn", size: "1400×700", qty: 10, material: 1950000 },
        ],
    },
    {
        id: "bg0044", code: "BG/2026/0044", partner: "Trần Văn Hùng",
        date: "28/06/2026", state: "rejected",
        lines: [
            { name: "Vách ngăn CNC", group: "Vách ngăn", size: "1200×2400", qty: 3, material: 3400000 },
        ],
    },
];

const RATIO_ROWS = [
    { key: "material", label: "Vật tư", min: 55, max: 55, hint: "Cố định 55%" },
    { key: "labor", label: "Nhân công", min: 30, max: 35, hint: "30–35%" },
    { key: "risk", label: "Rủi ro", min: 0, max: 5, hint: "0–5%" },
    { key: "profit", label: "Lợi nhuận", min: 10, max: 15, hint: "10–15%" },
];

const STATE_LABELS = {
    draft: "Nháp", sent: "Đã gửi", approved: "Đã duyệt", rejected: "Từ chối",
};

const VAT_RATE = 0.08;

export class DlRfq extends Component {
    static template = "dl_sale.DlRfq";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.ratioRows = RATIO_ROWS;
        this.stateLabels = STATE_LABELS;
        this.rfqs = RFQS;

        this.state = useState({
            search: "",
            group: "",
            size: "",
            selectedId: RFQS[0].id,

            ratios: { material: 55, labor: 32, risk: 3, profit: 10 },

            exportMode: null,
        });
    }

    get groupOptions() {
        const s = new Set();
        this.rfqs.forEach((r) => r.lines.forEach((l) => s.add(l.group)));
        return [...s];
    }
    get sizeOptions() {
        const s = new Set();
        this.rfqs.forEach((r) => r.lines.forEach((l) => s.add(l.size)));
        return [...s];
    }

    get filteredRfqs() {
        const q = this.state.search.trim().toLowerCase();
        return this.rfqs.filter((r) => {
            if (q && !(`${r.code} ${r.partner}`.toLowerCase().includes(q))) {
                return false;
            }
            if (this.state.group && !r.lines.some((l) => l.group === this.state.group)) {
                return false;
            }
            if (this.state.size && !r.lines.some((l) => l.size === this.state.size)) {
                return false;
            }
            return true;
        });
    }

    get ratioSum() {
        const r = this.state.ratios;
        return r.material + r.labor + r.risk + r.profit;
    }
    get ratioValid() {
        return this.ratioSum === 100 && this.state.ratios.material > 0;
    }

    lineBreakdown(line) {
        const r = this.state.ratios;
        const matRatio = r.material > 0 ? r.material / 100 : 0.55;
        const unitTotal = Math.round(line.material / matRatio);
        return {
            material: line.material,
            labor: Math.round(unitTotal * r.labor / 100),
            risk: Math.round(unitTotal * r.risk / 100),
            profit: Math.round(unitTotal * r.profit / 100),
            unit: unitTotal,
            amount: unitTotal * line.qty,
        };
    }

    rfqTotals(rfq) {
        let material = 0, amount = 0, qty = 0;
        rfq.lines.forEach((l) => {
            const b = this.lineBreakdown(l);
            material += l.material * l.qty;
            amount += b.amount;
            qty += l.qty;
        });
        return { material, amount, qty };
    }

    rfqGroups(rfq) {
        const s = [...new Set(rfq.lines.map((l) => l.group))];
        return s.length > 1 ? "Nhiều nhóm" : s[0];
    }

    fmt(n) {
        return (n || 0).toLocaleString("vi-VN");
    }

    get selectedRfq() {
        return this.rfqs.find((r) => r.id === this.state.selectedId) || null;
    }
    selectRfq(id) {
        this.state.selectedId = id;
    }
    onRatioInput(key, ev) {
        const v = parseFloat(ev.target.value);
        this.state.ratios[key] = isNaN(v) ? 0 : v;
    }
    openExport(mode) {
        if (this.selectedRfq) {
            this.state.exportMode = mode;
        }
    }
    closeExport() {
        this.state.exportMode = null;
    }

    get exportDoc() {
        const rfq = this.selectedRfq;
        if (!rfq) {
            return null;
        }
        const lines = rfq.lines.map((l) => ({ ...l, b: this.lineBreakdown(l) }));
        const subtotal = lines.reduce((s, l) => s + l.b.amount, 0);
        const vat = Math.round(subtotal * VAT_RATE);
        return { rfq, lines, subtotal, vat, total: subtotal + vat };
    }
}

registry.category("actions").add("dl_sale.DlRfq", DlRfq);
