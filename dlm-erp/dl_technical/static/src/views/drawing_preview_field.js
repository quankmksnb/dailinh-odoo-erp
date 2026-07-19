/** @odoo-module **/
// ============================================================
//  Field widget "dl_drawing_preview" — preview bản vẽ kỹ thuật cạnh dòng BOM.
//  Gắn vào field Many2one(ir.attachment) `drawing_attachment_id` của dl.bom.
//  Dựng URL theo ID attachment THẬT (bản vẽ đã upload/đã lưu) nên preview
//  chạy được cả khi BOM còn là bản ghi mới CHƯA lưu (màn "+ Tạo BOM" từ SP)
//  — khác widget image/pdf_viewer chuẩn vốn cần id của chính bản ghi BOM.
// ============================================================

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class DrawingPreviewField extends Component {
    static template = "dl_technical.DrawingPreviewField";

    get attachmentId() {
        const val = this.props.record.data[this.props.name];
        // Many2one dạng [id, display_name] — lấy id.
        return Array.isArray(val) ? val[0] : false;
    }
    get mimetype() {
        return this.props.record.data.drawing_mimetype || "";
    }
    get filename() {
        return this.props.record.data.drawing_filename || "";
    }
    get isImage() {
        return (
            this.mimetype.startsWith("image/") ||
            /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(this.filename)
        );
    }
    get isPdf() {
        return this.mimetype === "application/pdf" || /\.pdf$/i.test(this.filename);
    }
    get imageUrl() {
        return `/web/image/${this.attachmentId}`;
    }
    get inlineUrl() {
        return `/web/content/${this.attachmentId}?download=false`;
    }
    get downloadUrl() {
        return `/web/content/${this.attachmentId}?download=true`;
    }
    // Nhúng PDF qua PDF.js viewer của Odoo — hiển thị INLINE ngay trên màn,
    // không kích hoạt tải về (khác iframe trỏ thẳng /web/content). Giống hệt
    // cách widget "pdf_viewer" chuẩn dựng URL.
    get pdfViewerUrl() {
        const file = encodeURIComponent(`/web/content/${this.attachmentId}`);
        return `/web/static/lib/pdfjs/web/viewer.html?file=${file}`;
    }
}

export const drawingPreviewField = {
    component: DrawingPreviewField,
    supportedTypes: ["many2one"],
};

registry.category("fields").add("dl_drawing_preview", drawingPreviewField);
