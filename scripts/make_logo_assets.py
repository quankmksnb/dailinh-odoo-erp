# -*- coding: utf-8 -*-
"""Sinh bộ ảnh thương hiệu Đại Linh từ MỘT file logo gốc.

Cách dùng (từ thư mục gốc repo, sau khi đã bật venv):

    python scripts/make_logo_assets.py <đường-dẫn-file-logo-gốc>

File gốc là ảnh lockup ngang "DL + DAI LINH ENGINEERING & MANUFACTURING" trên
nền trắng (png/jpg đều được). Script sinh ra:

    dlm-erp/dl_base/static/img/dai_linh_logo.png   lockup đầy đủ, đã cắt lề trắng
    dlm-erp/dl_base/static/img/dai_linh_mark.png   riêng biểu tượng DL, khung vuông
    dlm-erp/dl_base/static/description/icon.png    icon module (dùng lại mark)
    dlm-erp/dl_sale/static/description/icon.png    nt

Chạy lại được nhiều lần: mỗi lần ghi đè toàn bộ output.
"""

import os
import sys

from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMG_DIR = os.path.join(_ROOT, "dlm-erp", "dl_base", "static", "img")
_ICON_TARGETS = [
    os.path.join(_ROOT, "dlm-erp", "dl_base", "static", "description", "icon.png"),
    os.path.join(_ROOT, "dlm-erp", "dl_sale", "static", "description", "icon.png"),
]

# Pixel được coi là "có mực" khi lệch khỏi trắng quá ngưỡng này. Logo Đại Linh
# nằm trên nền trắng tinh nên 235 đủ rộng để bỏ qua nhiễu nén JPEG.
_WHITE = 235


def _ink_mask(image):
    """Trả về ảnh 1-bit: điểm sáng = có mực (khác nền trắng)."""
    grey = image.convert("L")
    return grey.point(lambda value: 255 if value < _WHITE else 0, mode="1")


def _trim(image):
    """Cắt sạch lề trắng quanh logo."""
    box = _ink_mask(image).getbbox()
    return image.crop(box) if box else image


def _column_ink(mask):
    """Số điểm có mực trên từng cột — dùng để dò khoảng trắng ngăn biểu tượng với chữ."""
    width, height = mask.size
    data = mask.load()
    return [sum(1 for y in range(height) if data[x, y]) for x in range(width)]


def _split_mark(logo):
    """Tách phần biểu tượng DL ở bên trái khỏi phần chữ.

    Cách dò: lockup có đúng một khoảng trắng rộng ngăn biểu tượng với chữ
    "DAI LINH". Tìm dải cột trống DÀI NHẤT nằm trong 60% bề ngang đầu tiên rồi
    cắt tại đó. Không tìm thấy thì trả về None để người dùng tự cắt tay.
    """
    mask = _ink_mask(logo)
    columns = _column_ink(mask)
    limit = int(len(columns) * 0.6)

    best_start = best_len = 0
    run_start = None
    for index in range(limit):
        if columns[index] == 0:
            run_start = index if run_start is None else run_start
        elif run_start is not None:
            if index - run_start > best_len:
                best_start, best_len = run_start, index - run_start
            run_start = None

    # Khoảng trắng thật phải đáng kể; dưới 3% bề ngang là khe giữa hai nét chữ.
    if best_len < len(columns) * 0.03:
        return None
    return logo.crop((0, 0, best_start, logo.size[1]))


def _square(image, size=512):
    """Đặt ảnh vào khung vuông nền trắng, canh giữa, cạnh `size` px."""
    trimmed = _trim(image)
    trimmed.thumbnail((size - 16, size - 16), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), "white")
    canvas.paste(
        trimmed,
        ((size - trimmed.size[0]) // 2, (size - trimmed.size[1]) // 2))
    return canvas


def main(source_path):
    if not os.path.exists(source_path):
        raise SystemExit("Không thấy file logo gốc: %s" % source_path)

    source = Image.open(source_path).convert("RGB")
    os.makedirs(_IMG_DIR, exist_ok=True)

    logo = _trim(source)
    logo_path = os.path.join(_IMG_DIR, "dai_linh_logo.png")
    logo.save(logo_path, "PNG")
    print("[logo]  %s  (%dx%d)" % (logo_path, logo.size[0], logo.size[1]))

    mark_source = _split_mark(logo)
    if mark_source is None:
        print("[mark]  KHÔNG dò được khoảng trắng ngăn biểu tượng với chữ — "
              "dùng tạm cả lockup làm mark, nên cắt tay lại cho đẹp.")
        mark_source = logo
    mark = _square(mark_source)
    mark_path = os.path.join(_IMG_DIR, "dai_linh_mark.png")
    mark.save(mark_path, "PNG")
    print("[mark]  %s  (512x512)" % mark_path)

    for target in _ICON_TARGETS:
        if not os.path.isdir(os.path.dirname(target)):
            continue
        mark.resize((256, 256), Image.LANCZOS).save(target, "PNG")
        print("[icon]  %s  (256x256)" % target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
