/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const REQUESTS = [
    {
        id: "yc031", code: "YC/2026/0031", customer: "Cty TNHH Nội thất Hoà Phát",
        contact: "A. Dũng · 0901 234 567", date: "05/07/2026", group: "Tủ bếp",
        qty: 8, channel: "Website", state: "new",
        note: "Cần báo giá trọn bộ tủ bếp Acrylic cho căn hộ mẫu, giao trong tháng 8.",
    },
    {
        id: "yc030", code: "YC/2026/0030", customer: "Đinh Thị Thúy",
        contact: "0912 888 777", date: "04/07/2026", group: "Cửa",
        qty: 6, channel: "Zalo", state: "processing",
        note: "Cửa gỗ HDF sơn trắng cho nhà phố 3 tầng.",
    },
    {
        id: "yc029", code: "YC/2026/0029", customer: "Cty CP Hoàng Gia",
        contact: "P. Mua hàng · 024 3555 1234", date: "02/07/2026", group: "Tủ áo",
        qty: 4, channel: "Email", state: "quoted",
        note: "Tủ áo và kệ tivi cho dự án khách sạn, đã gửi báo giá BG/2026/0046.",
    },
    {
        id: "yc028", code: "YC/2026/0028", customer: "Cty TNHH Minh Anh",
        contact: "C. Lan · 0977 010 234", date: "30/06/2026", group: "Bàn",
        qty: 10, channel: "Điện thoại", state: "new",
        note: "Bàn làm việc chân sắt cho văn phòng 40 nhân sự.",
    },
    {
        id: "yc027", code: "YC/2026/0027", customer: "Trần Văn Hùng",
        contact: "0988 456 123", date: "27/06/2026", group: "Vách ngăn",
        qty: 3, channel: "Website", state: "closed",
        note: "Vách ngăn CNC — khách đã chốt đơn hàng khác.",
    },
];

const STATES = [
    { key: "new", label: "Mới" },
    { key: "processing", label: "Đang xử lý" },
    { key: "quoted", label: "Đã báo giá" },
    { key: "closed", label: "Đã đóng" },
];

export class DlCustomerRequest extends Component {
    static template = "dl_sale.DlCustomerRequest";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.requests = REQUESTS;
        this.states = STATES;
        this.stateLabels = Object.fromEntries(STATES.map((s) => [s.key, s.label]));

        this.state = useState({
            search: "",
            stateFilter: "",
            selectedId: REQUESTS[0].id,
        });
    }

    get filtered() {
        const q = this.state.search.trim().toLowerCase();
        return this.requests.filter((r) => {
            if (q && !(`${r.code} ${r.customer} ${r.group}`.toLowerCase().includes(q))) {
                return false;
            }
            if (this.state.stateFilter && r.state !== this.state.stateFilter) {
                return false;
            }
            return true;
        });
    }

    get selected() {
        return this.requests.find((r) => r.id === this.state.selectedId) || null;
    }
    select(id) {
        this.state.selectedId = id;
    }

    countByState(key) {
        return this.requests.filter((r) => r.state === key).length;
    }

    createRfq() {
        this.actionService.doAction("dl_sale.action_dl_rfq", { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dl_sale.DlCustomerRequest", DlCustomerRequest);
