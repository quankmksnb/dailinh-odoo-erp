/** @odoo-module **/
/**
 * Chữ cái + màu nền cho avatar đối tác, dùng chung cho danh sách Khách hàng và
 * NCC (và mọi màn cần sau này).
 *
 * Vì sao không lấy thẳng ký tự đầu: gần như MỌI pháp nhân Việt Nam đều mở đầu
 * bằng "Công ty". Danh sách NCC thực tế cho ra bốn dòng avatar chữ "C" giống
 * hệt nhau, mất sạch tác dụng phân biệt. Bỏ tiền tố pháp nhân rồi mới lấy chữ
 * cái thì "Công ty CP Thành Công" ra T, "Công ty TNHH Việt Hưng" ra V.
 *
 * Màu cũng băm từ phần tên đã bỏ tiền tố, nếu không thì mọi "Công ty ..." lại
 * dồn về cùng một màu.
 */

// Tiền tố bỏ qua khi tìm chữ cái. Xếp dài trước ngắn để "Công ty Cổ phần" được
// cắt trọn thay vì chỉ cắt "Công ty" rồi dừng ở "Cổ".
const NAME_PREFIXES = [
    "công ty cổ phần",
    "công ty tnhh mtv",
    "công ty tnhh",
    "công ty cp",
    "công ty",
    "cửa hàng",
    "doanh nghiệp tư nhân",
    "hộ kinh doanh",
    "tổng công ty",
    "cty tnhh",
    "cty cp",
    "cty",
    "tnhh mtv",
    "tnhh",
    "cp",
    "dntn",
    "hkd",
    "xưởng",
    "nhà máy",
    "tập đoàn",
    "chi nhánh",
];

const AVA_PALETTE = [
    { bg: "#dbe7ff", fg: "#1e4fa3" },
    { bg: "#e3f6e8", fg: "#1b7a3d" },
    { bg: "#fff1cc", fg: "#8a5a00" },
    { bg: "#ece0fb", fg: "#5b3fa0" },
    { bg: "#d9f2f4", fg: "#0f6b73" },
    { bg: "#fde2e4", fg: "#b23a48" },
];

/** Phần tên còn lại sau khi bỏ hết tiền tố pháp nhân ở đầu. */
export function significantName(name) {
    let rest = (name || "").trim();
    let changed = true;
    // Lặp: "Công ty TNHH Việt Hưng" phải bỏ cả hai tầng tiền tố.
    while (changed && rest) {
        changed = false;
        const lower = rest.toLowerCase();
        for (const prefix of NAME_PREFIXES) {
            if (lower.startsWith(prefix)) {
                const after = rest.slice(prefix.length).replace(/^[\s.,\-–—]+/, "");
                // Không cắt nếu phần còn lại rỗng — tên chỉ gồm mỗi tiền tố thì
                // thà hiện chữ của tiền tố còn hơn hiện dấu '?'.
                if (after) {
                    rest = after;
                    changed = true;
                }
                break;
            }
        }
    }
    return rest || (name || "").trim();
}

export function avatarInitial(name) {
    const rest = significantName(name);
    return rest ? rest[0].toUpperCase() : "?";
}

export function avatarColor(name) {
    const rest = significantName(name);
    let h = 0;
    for (let i = 0; i < rest.length; i++) {
        h = (h * 31 + rest.charCodeAt(i)) >>> 0;
    }
    return AVA_PALETTE[h % AVA_PALETTE.length];
}
