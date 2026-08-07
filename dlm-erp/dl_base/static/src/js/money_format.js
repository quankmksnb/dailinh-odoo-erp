/** @odoo-module **/

import { localization } from "@web/core/l10n/localization";

// ─────────────────────────────────────────────────────────────────────────────
// Định dạng tiền DÙNG CHUNG — group hàng nghìn LIVE ngay khi gõ (mỗi 3 số 1 dấu
// phân tách). Dấu phân tách lấy từ ngôn ngữ hiện hành (vi_VN → "."), nên khớp
// với cách Odoo hiển thị số ở chế độ đọc.
//
// Tiền trong DLM-ERP là VNĐ (số nguyên, 0 phần thập phân), nên ở đây chỉ xử lý
// phần nguyên: mọi ký tự không phải chữ số bị bỏ, giữ dấu trừ đứng đầu.
//
// Dùng cho:
//   • widget field `dl_money` (money_field.js) — form Odoo chuẩn.
//   • các ô <input> thủ công trong component OWL (vd pricing_config).
// ─────────────────────────────────────────────────────────────────────────────

export function thousandsSep() {
    return localization.thousandsSep || ".";
}

// Chèn dấu phân tách vào chuỗi CHỈ gồm chữ số (phần nguyên), mỗi 3 số từ phải.
function groupDigits(digits, sep) {
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
}

// Số (Number) → chuỗi đã group, để đổ giá trị ban đầu vào ô nhập.
export function formatMoney(value) {
    if (value === null || value === undefined || value === "" || Number.isNaN(value)) {
        return "";
    }
    const neg = value < 0;
    const digits = String(Math.trunc(Math.abs(Number(value))));
    const grouped = groupDigits(digits, thousandsSep());
    return (neg ? "-" : "") + grouped;
}

// Chuỗi người dùng gõ ("1.000.000", "1 000 000"…) → Number nguyên.
export function parseMoney(str) {
    if (typeof str === "number") {
        return str;
    }
    const s = String(str == null ? "" : str).trim();
    const neg = s.startsWith("-");
    const digits = (s.match(/\d/g) || []).join("");
    if (!digits) {
        return 0;
    }
    const n = parseInt(digits, 10);
    return neg ? -n : n;
}

// Định dạng lại value của một <input> TẠI CHỖ, giữ nguyên vị trí con trỏ theo
// đúng "ranh giới chữ số" (số chữ số bên trái con trỏ không đổi trước/sau khi
// chèn dấu phân tách). Đây là phần lõi tạo hiệu ứng gõ-tới-đâu-chấm-tới-đó.
export function regroupMoneyInput(input) {
    const sep = thousandsSep();
    const raw = input.value;
    const caret = input.selectionStart ?? raw.length;

    const neg = raw.trimStart().startsWith("-");
    // Số chữ số nằm bên trái con trỏ — dùng để đặt lại con trỏ sau khi format.
    const digitsLeft = (raw.slice(0, caret).match(/\d/g) || []).length;

    let digits = (raw.match(/\d/g) || []).join("");
    // Bỏ số 0 vô nghĩa ở đầu (giữ lại "0" nếu người dùng chỉ gõ toàn số 0).
    digits = digits.replace(/^0+(?=\d)/, "");

    const grouped = groupDigits(digits, sep);
    const newVal = (neg && grouped ? "-" : "") + grouped;
    if (newVal === raw) {
        return; // Không đổi → không đụng vào con trỏ.
    }
    input.value = newVal;

    // Đặt lại con trỏ ngay sau chữ số thứ `digitsLeft` trong chuỗi mới.
    let count = 0;
    let pos = newVal.length;
    for (let i = 0; i < newVal.length; i++) {
        if (count >= digitsLeft) {
            pos = i;
            break;
        }
        if (/\d/.test(newVal[i])) {
            count++;
        }
    }
    input.setSelectionRange(pos, pos);
}

// Handler tiện dụng cho t-on-input trong template OWL.
export function onMoneyInput(ev) {
    regroupMoneyInput(ev.target);
}
