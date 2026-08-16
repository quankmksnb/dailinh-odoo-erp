"""Helpers to build paragraphs/tables matching Report 4.0_TDS.docx house style."""
import copy
from docx.oxml import parse_xml
from docx.oxml.ns import nsmap, qn

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = f'xmlns:w="{W}"'

HDR_FILL = "0f6e56"       # dark green header
HDR_BORDER = "0f6e56"
BODY_BORDER = "cccccc"
BODY_TEXT = "333333"
GROUP_FILL = "d9ebe4"     # light green band for group rows
TABLE_W = 9360            # dxa, matches existing tables


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _runs(text, bold=False, color=BODY_TEXT, sz=20, italic=False, mono=False):
    """Build <w:r> runs; text may contain \n which becomes <w:br/>."""
    rpr = []
    if bold:
        rpr.append('<w:b w:val="1"/><w:bCs w:val="1"/>')
    if italic:
        rpr.append('<w:i w:val="1"/><w:iCs w:val="1"/>')
    if mono:
        rpr.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>')
    if color:
        rpr.append(f'<w:color w:val="{color}"/>')
    rpr.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>')
    rpr.append('<w:rtl w:val="0"/>')
    rpr = "".join(rpr)
    parts = str(text).split("\n")
    out = []
    for i, part in enumerate(parts):
        if i:
            out.append(f'<w:r><w:rPr>{rpr}</w:rPr><w:br/></w:r>')
        if part:
            out.append(f'<w:r><w:rPr>{rpr}</w:rPr>'
                       f'<w:t xml:space="preserve">{esc(part)}</w:t></w:r>')
    if not out:
        out.append(f'<w:r><w:rPr>{rpr}</w:rPr></w:r>')
    return "".join(out)


def para(text="", style=None, bold=False, sz=22, color=None, italic=False,
         mono=False, bullet=False, space_before=None):
    """Return a <w:p> element."""
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if space_before is not None:
        ppr.append(f'<w:spacing w:before="{space_before}" w:lineRule="auto"/>')
    if bullet:
        ppr.append('<w:ind w:left="360" w:hanging="180"/>')
    ppr = f"<w:pPr>{''.join(ppr)}<w:rPr/></w:pPr>"
    body = "" if style and not text else _runs(
        ("•  " + text) if bullet else text,
        bold=bold, color=color, sz=sz, italic=italic, mono=mono)
    if style and text:
        # headings: let the style drive size/colour, only carry the text
        body = f'<w:r><w:rPr><w:rtl w:val="0"/></w:rPr>' \
               f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
    return parse_xml(f'<w:p {NS}>{ppr}{body}</w:p>')


def _tc(text, width, *, header=False, group=False, bold=False, span=None,
        mono=False, align_left=True):
    fill = HDR_FILL if header else (GROUP_FILL if group else "ffffff")
    border = HDR_BORDER if header else BODY_BORDER
    color = "ffffff" if header else BODY_TEXT
    b = header or group or bold
    tcpr = [f'<w:tcW w:w="{width}" w:type="dxa"/>']
    if span:
        tcpr.append(f'<w:gridSpan w:val="{span}"/>')
    tcpr.append(
        f'<w:tcBorders>'
        f'<w:top w:color="{border}" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:left w:color="{border}" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:bottom w:color="{border}" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:right w:color="{border}" w:space="0" w:sz="4" w:val="single"/>'
        f'</w:tcBorders>')
    tcpr.append(f'<w:shd w:fill="{fill}" w:val="clear"/>')
    tcpr.append('<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="120" w:type="dxa"/>'
                '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar>')
    tcpr.append('<w:vAlign w:val="center"/>')
    runs = _runs(text, bold=b, color=color, sz=20, mono=mono)
    return (f'<w:tc><w:tcPr>{"".join(tcpr)}</w:tcPr>'
            f'<w:p><w:pPr><w:rPr/></w:pPr>{runs}</w:p></w:tc>')


def table(headers, rows, widths, mono_cols=(), banner=None):
    """rows: list of (list-of-cells) or ('GROUP', 'text') tuples.

    banner: dòng tiêu đề gộp hết chiều ngang, đặt TRÊN dòng header — đúng lối các
    bảng "Data Constraints & Conditions" đã có sẵn trong tài liệu.
    """
    total = sum(widths)
    scale = TABLE_W / total
    widths = [int(round(w * scale)) for w in widths]
    widths[-1] += TABLE_W - sum(widths)

    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    tblpr = (
        f'<w:tblPr><w:tblW w:w="{TABLE_W}" w:type="dxa"/><w:jc w:val="left"/>'
        f'<w:tblBorders>'
        f'<w:top w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:left w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:bottom w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:right w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:insideH w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'<w:insideV w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
        f'</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblLook w:val="0400"/></w:tblPr>')

    trs = []
    if banner:
        cells = _tc(banner, TABLE_W, header=True, span=len(widths))
        trs.append('<w:tr><w:trPr><w:cantSplit w:val="0"/>'
                   f'<w:tblHeader w:val="1"/></w:trPr>{cells}</w:tr>')
    if headers:
        cells = "".join(_tc(h, w, header=True) for h, w in zip(headers, widths))
        trs.append('<w:tr><w:trPr><w:cantSplit w:val="0"/>'
                   f'<w:tblHeader w:val="1"/></w:trPr>{cells}</w:tr>')
    for row in rows:
        if isinstance(row, tuple) and row and row[0] == "GROUP":
            cells = _tc(row[1], TABLE_W, group=True, span=len(widths))
        else:
            cells = "".join(
                _tc(c, w, mono=(i in mono_cols))
                for i, (c, w) in enumerate(zip(row, widths)))
        trs.append('<w:tr><w:trPr><w:cantSplit w:val="0"/>'
                   f'<w:tblHeader w:val="0"/></w:trPr>{cells}</w:tr>')
    return parse_xml(f'<w:tbl {NS}>{tblpr}<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')


def note_box(label, text):
    """1x1 callout box like the existing Note/Guidance boxes."""
    return table(None, [[f"{label}\n{text}"]], [100])
