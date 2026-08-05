/** @odoo-module **/
// ============================================================
//  Field widget "dl_drawing_upload" — ô upload rõ ràng cho field
//  Many2one(ir.attachment) `attachment_id` của dl.drawing.
//  Widget many2one mặc định chỉ là 1 ô nhỏ (phải hover đúng chỗ mới thấy) →
//  thay bằng dropzone bấm-để-chọn khi rỗng, và khối tên file + xem/tải/thay/xóa
//  khi đã có file. KHÔNG đổi model/logic: vẫn set đúng attachment_id.
// ============================================================

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { FileUploader } from "@web/views/fields/file_handler";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class DrawingUploadField extends Component {
    static template = "dl_technical.DrawingUploadField";
    static components = { FileUploader };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
    }

    get value() {
        const v = this.props.record.data[this.props.name];
        // Many2one dạng [id, display_name].
        return Array.isArray(v) ? { id: v[0], name: v[1] } : false;
    }
    get filename() {
        return this.value ? this.value.name : "";
    }
    get isImage() {
        return /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(this.filename);
    }
    get isPdf() {
        return /\.pdf$/i.test(this.filename);
    }
    get imageUrl() {
        return `/web/image/${this.value.id}`;
    }
    get inlineUrl() {
        return `/web/content/${this.value.id}?download=false`;
    }
    get downloadUrl() {
        return `/web/content/${this.value.id}?download=true`;
    }
    get pdfViewerUrl() {
        const file = encodeURIComponent(`/web/content/${this.value.id}`);
        return `/web/static/lib/pdfjs/web/viewer.html?file=${file}`;
    }

    // Upload → tạo ir.attachment rồi gán vào attachment_id. Chạy được cả khi
    // bản vẽ còn là bản ghi MỚI chưa lưu (res_id = 0).
    async onUploaded(file) {
        const [attId] = await this.orm.create("ir.attachment", [{
            name: file.name,
            datas: file.data,
            mimetype: file.type || false,
            res_model: this.props.record.resModel,
            res_id: this.props.record.resId || 0,
        }]);
        await this.props.record.update({ [this.props.name]: [attId, file.name] });
    }

    async onRemove() {
        await this.props.record.update({ [this.props.name]: false });
    }
}

export const drawingUploadField = {
    component: DrawingUploadField,
    displayName: "Upload bản vẽ",
    supportedTypes: ["many2one"],
};

registry.category("fields").add("dl_drawing_upload", drawingUploadField);
