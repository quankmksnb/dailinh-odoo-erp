/** @odoo-module **/
// ============================================================
//  Widget "dl_m2m_binary_preview" — many2many_binary nhưng bấm vào ảnh thì
//  mở popup xem full-size thay vì tải file về máy (chỉ ảnh; file khác vẫn
//  tải như cũ). Dùng cho attachment_ids ở dòng RFQ (Sales đính kèm ảnh,
//  Kỹ thuật cần xem nhanh để triage).
// ============================================================

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import {
    Many2ManyBinaryField,
    many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class DlImagePreviewDialog extends Component {
    static template = "dl_technical.DlImagePreviewDialog";
    static components = { Dialog };
    static props = {
        title: String,
        url: String,
        downloadUrl: String,
        close: Function,
    };
}

export class DlM2MBinaryPreviewField extends Many2ManyBinaryField {
    static template = "dl_technical.DlM2MBinaryPreviewField";

    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    isImage(file) {
        return (file.mimetype || "").startsWith("image/");
    }

    onAttachmentClick(file, ev) {
        if (!this.isImage(file)) {
            return; // file khác ảnh: giữ nguyên hành vi tải về mặc định.
        }
        ev.preventDefault();
        this.dialogService.add(DlImagePreviewDialog, {
            title: file.name,
            url: `/web/image/${file.id}`,
            downloadUrl: this.getUrl(file.id),
        });
    }
}

export const dlM2MBinaryPreviewField = {
    ...many2ManyBinaryField,
    component: DlM2MBinaryPreviewField,
};

registry.category("fields").add("dl_m2m_binary_preview", dlM2MBinaryPreviewField);
