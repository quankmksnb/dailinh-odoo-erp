# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1650, 1150
BG = (255, 255, 255)
NAVY = (30, 41, 59)
BLUE = (37, 99, 235)
GRAY = (100, 116, 139)
LIGHT_GRAY = (226, 232, 240)
DASH_GRAY = (148, 163, 184)

img = Image.new('RGB', (W, H), BG)
draw = ImageDraw.Draw(img)

FONT_DIR = 'C:/Windows/Fonts/'
f_title = ImageFont.truetype(FONT_DIR + 'segoeuib.ttf', 30)
f_box = ImageFont.truetype(FONT_DIR + 'segoeuib.ttf', 24)
f_box_sub = ImageFont.truetype(FONT_DIR + 'segoeui.ttf', 18)
f_label = ImageFont.truetype(FONT_DIR + 'segoeui.ttf', 18)
f_label_it = ImageFont.truetype(FONT_DIR + 'segoeuii.ttf', 17)


def text_wrapped(draw, font, fill, max_width, anchor_center, line_spacing=6):
    def _draw(text):
        lines = []
        for para in text.split('\n'):
            words = para.split(' ')
            cur = ''
            for w in words:
                test = (cur + ' ' + w).strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > max_width and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = test
            lines.append(cur)
        heights = [draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]
        total_h = sum(heights) + line_spacing * (len(lines) - 1)
        cx, cy = anchor_center
        y = cy - total_h / 2
        for l, h in zip(lines, heights):
            bbox = draw.textbbox((0, 0), l, font=font)
            lw = bbox[2] - bbox[0]
            x = cx - lw / 2
            draw.text((x, y), l, font=font, fill=fill)
            y += h + line_spacing
    return _draw


def rounded_box(box, fill, outline, width=3, radius=16, dashed=False):
    if not dashed:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
        return
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=None)
    x0, y0, x1, y1 = box
    dash, gap = 10, 8
    for yy in (y0, y1):
        x = x0
        while x < x1:
            draw.line([(x, yy), (min(x + dash, x1), yy)], fill=outline, width=width)
            x += dash + gap
    for xx in (x0, x1):
        y = y0
        while y < y1:
            draw.line([(xx, y), (xx, min(y + dash, y1))], fill=outline, width=width)
            y += dash + gap


def arrow(p0, p1, color, width=3, dashed=False, head=12):
    x0, y0 = p0
    x1, y1 = p1
    if dashed:
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(int(dist / 14), 1)
        for i in range(n):
            t0 = i / n
            t1 = t0 + 0.5 / n
            draw.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0),
                       (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)], fill=color, width=width)
    else:
        draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
    if head:
        angle = math.atan2(y1 - y0, x1 - x0)
        ax1 = x1 - head * math.cos(angle - 0.4)
        ay1 = y1 - head * math.sin(angle - 0.4)
        ax2 = x1 - head * math.cos(angle + 0.4)
        ay2 = y1 - head * math.sin(angle + 0.4)
        draw.polygon([(x1, y1), (ax1, ay1), (ax2, ay2)], fill=color)


draw.text((W / 2, 32), 'Sơ đồ ngữ cảnh hệ thống (Context Diagram) — DLM-ERP', font=f_title, fill=NAVY, anchor='mm')

BOX_W, BOX_H = 300, 110
cx, cy, r = 900, 570, 135

# Central process
draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(219, 234, 254), outline=BLUE, width=4)
text_wrapped(draw, f_title, NAVY, 210, (cx, cy - 12))('HỆ THỐNG\nDLM-ERP')
draw.text((cx, cy + 45), '(bán hàng, kỹ thuật, kho)', font=f_box_sub, fill=GRAY, anchor='mm')

# Top-center: Khách hàng
kh_box = (cx - BOX_W / 2, 110, cx + BOX_W / 2, 110 + BOX_H)
rounded_box(kh_box, LIGHT_GRAY, NAVY)
text_wrapped(draw, f_box, NAVY, BOX_W - 30, ((kh_box[0] + kh_box[2]) / 2, (kh_box[1] + kh_box[3]) / 2 - 12))('KHÁCH HÀNG')
draw.text(((kh_box[0] + kh_box[2]) / 2, kh_box[3] - 20), '(ngoài hệ thống, không có portal)', font=f_box_sub, fill=GRAY, anchor='mm')

# Left-upper: Người dùng nội bộ
nd_box = (60, 330, 60 + BOX_W, 330 + BOX_H)
rounded_box(nd_box, LIGHT_GRAY, NAVY)
text_wrapped(draw, f_box, NAVY, BOX_W - 30, ((nd_box[0] + nd_box[2]) / 2, (nd_box[1] + nd_box[3]) / 2 - 12))('NGƯỜI DÙNG NỘI BỘ')
draw.text(((nd_box[0] + nd_box[2]) / 2, nd_box[3] - 20), '8 vai trò (Admin, CEO, Sales...)', font=f_box_sub, fill=GRAY, anchor='mm')

# Left-lower: Nhà cung cấp (dashed, no direct electronic link)
ncc_box = (60, 860, 60 + BOX_W, 860 + BOX_H)
rounded_box(ncc_box, (241, 245, 249), DASH_GRAY, dashed=True)
text_wrapped(draw, f_box, GRAY, BOX_W - 30, ((ncc_box[0] + ncc_box[2]) / 2, (ncc_box[1] + ncc_box[3]) / 2 - 12))('NHÀ CUNG CẤP')
draw.text(((ncc_box[0] + ncc_box[2]) / 2, ncc_box[3] - 20), '(không kết nối điện tử trực tiếp)', font=f_box_sub, fill=GRAY, anchor='mm')

# Bottom-center: Máy chủ thư đi
mail_box = (cx - BOX_W / 2, H - 90 - BOX_H, cx + BOX_W / 2, H - 90)
rounded_box(mail_box, LIGHT_GRAY, NAVY)
text_wrapped(draw, f_box, NAVY, BOX_W - 30, ((mail_box[0] + mail_box[2]) / 2, (mail_box[1] + mail_box[3]) / 2 - 12))('MÁY CHỦ THƯ ĐI')
draw.text(((mail_box[0] + mail_box[2]) / 2, mail_box[3] - 20), '(SMTP, API-01)', font=f_box_sub, fill=GRAY, anchor='mm')

# --- Arrows: Người dùng <-> Hệ thống ---
arrow((nd_box[2], cy - 55), (cx - r * 0.9, cy - r * 0.35), BLUE, width=3)
draw.text(((nd_box[2] + cx) / 2 - 30, cy - 130), 'Đăng nhập; nhập RFQ, BOM,\nbáo giá, phiếu kho, cấu hình...', font=f_label, fill=NAVY, anchor='mm')

arrow((cx - r * 0.9, cy + r * 0.35), (nd_box[2], cy + 55), BLUE, width=3)
draw.text(((nd_box[2] + cx) / 2 - 10, cy + 130), 'Danh sách, báo cáo, cảnh báo,\nbadge phê duyệt', font=f_label, fill=NAVY, anchor='mm')

# --- Nhà cung cấp: chú thích, không có luồng điện tử (đường chấm ngắn, không mũi tên) ---
ncc_top_mid = ((ncc_box[0] + ncc_box[2]) / 2, ncc_box[1])
circle_target = (cx - r * 0.82, cy + r * 0.62)
arrow(ncc_top_mid, circle_target, DASH_GRAY, width=2, dashed=True, head=0)
draw.text((ncc_box[0], ncc_box[1] - 45),
          'Giá nhập, thông tin NCC do\nMua hàng nhập tay — không\ncó kênh điện tử',
          font=f_label_it, fill=GRAY, anchor='lm')

# --- Hệ thống -> Máy chủ thư đi ---
arrow((cx, cy + r), (cx, mail_box[1]), BLUE, width=3)
draw.text((cx + 210, (cy + r + mail_box[1]) / 2), 'Email báo giá (PDF/Word),\nemail đặt lại mật khẩu', font=f_label, fill=NAVY, anchor='mm')

# --- Máy chủ thư đi -> Khách hàng: đi vòng theo cạnh phải, ngoài biên hệ thống ---
path_x = W - 110
arrow((mail_box[2], mail_box[1] + 15), (path_x, mail_box[1] + 15), DASH_GRAY, width=2, dashed=True, head=0)
draw.line([(path_x, mail_box[1] + 15), (path_x, kh_box[3] + 15)], fill=DASH_GRAY, width=2)
arrow((path_x, kh_box[3] + 15), (kh_box[2], kh_box[3] + 15), DASH_GRAY, width=2, dashed=True)
draw.text((path_x + 8, cy), 'Chuyển email tới\nngười nhận\n(ngoài biên\nhệ thống)', font=f_label_it, fill=GRAY, anchor='lm')

# Legend
ly = H - 30
draw.line([(60, ly), (100, ly)], fill=BLUE, width=3)
draw.text((110, ly), 'Luồng dữ liệu qua giao diện hệ thống', font=f_label, fill=NAVY, anchor='lm')
xx = 560
while xx < 600:
    draw.line([(xx, ly), (xx + 12, ly)], fill=DASH_GRAY, width=2)
    xx += 22
draw.text((615, ly), 'Không kết nối điện tử trực tiếp / ngoài biên hệ thống', font=f_label, fill=GRAY, anchor='lm')

img.save('scratch_docx/context_diagram.png')
print('saved image')
