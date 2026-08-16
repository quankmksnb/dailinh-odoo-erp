import re
import xml.etree.ElementTree as ET

p = r"D:/FPTU/do_van_an/dailinh-odoo-erp/docs/high-level-architecture.drawio"
with open(p, encoding="utf-8") as f:
    s = f.read()
before = len(s)
counts = {}

for cid in ["nginx", "e1", "e2", "e3", "e4", "ZIEwa1C49jYvmm0YW89o-12"]:
    s, n = re.subn(r'\n\s*<mxCell id="' + re.escape(cid) + r'"[^>]*>.*?</mxCell>', "", s, flags=re.S)
    counts["del " + cid] = n

s, counts["pres parent"] = re.subn(r'id="pres" parent="1"', 'id="pres" parent="app"', s)
s, counts["odoo parent"] = re.subn(r'id="odoo" parent="1"', 'id="odoo" parent="app"', s)

s, counts["pres geom"] = re.subn(r'<mxGeometry height="460" width="280" x="40" y="160"',
                                 '<mxGeometry height="460" width="280" x="30" y="50"', s)
s, counts["odoo geom"] = re.subn(r'<mxGeometry height="490" width="400" x="700" y="140"',
                                 '<mxGeometry height="490" width="400" x="370" y="50"', s)
s, counts["data geom"] = re.subn(r'<mxGeometry height="350" width="300" x="1180" y="220"',
                                 '<mxGeometry height="350" width="300" x="1220" y="300"', s)
s, counts["laptop geom"] = re.subn(r'<mxGeometry height="55" width="66\.48" x="147" y="60"',
                                   '<mxGeometry height="55" width="66.48" x="140" y="330"', s)

s, counts["pres value"] = re.subn(
    r'value="&lt;b&gt;Trình duyệt — Presentation tier&lt;/b&gt;&lt;br&gt;End user · SPA \(JS / HTML / CSS\)"',
    'value="&lt;b&gt;Presentation tier&lt;/b&gt;&lt;br&gt;Web client · SPA (OWL 2)"', s)
s, counts["odoo value"] = re.subn(
    r'value="&lt;b&gt;Odoo 17 Application — Business Logic&lt;/b&gt;&lt;br&gt;Odoo server \(Python\)"',
    'value="&lt;b&gt;Business Logic&lt;/b&gt;&lt;br&gt;Odoo server (Python)"', s)
s, counts["laptop value"] = re.subn(
    r'(id="ZIEwa1C49jYvmm0YW89o-11"[^>]*?)value=""',
    r'\1value="&lt;b&gt;End user&lt;/b&gt;&lt;br&gt;Trình duyệt"', s)

app_cell = '''
        <mxCell id="app" parent="1" style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#6c8ebf;verticalAlign=top;spacingTop=8;fontSize=16;" value="&lt;b&gt;Odoo 17 Application&lt;/b&gt;" vertex="1">
          <mxGeometry height="570" width="800" x="360" y="100" as="geometry" />
        </mxCell>'''
anchor = '<mxCell id="1" parent="0" />'
assert anchor in s
s = s.replace(anchor, anchor + app_cell, 1)

edges = '''        <mxCell id="u1" edge="1" parent="1" source="ZIEwa1C49jYvmm0YW89o-11" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.4;exitDx=0;exitDy=0;entryX=0;entryY=0.42;entryDx=0;entryDy=0;" target="app" value="HTTPS">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="u2" edge="1" parent="1" source="app" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=0;exitY=0.52;exitDx=0;exitDy=0;entryX=1;entryY=0.65;entryDx=0;entryDy=0;" target="ZIEwa1C49jYvmm0YW89o-11" value="lần đầu: HTML + assets · sau đó: JSON">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="p1" edge="1" parent="1" source="pres" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.3;exitDx=0;exitDy=0;entryX=0;entryY=0.35;entryDx=0;entryDy=0;" target="ctrl" value="JSON-RPC">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="p2" edge="1" parent="1" source="ctrl" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=0;exitY=0.7;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;" target="pres" value="JSON response">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
'''
assert "      </root>" in s
s = s.replace("      </root>", edges + "      </root>", 1)

bad = [k for k, v in counts.items() if v != 1]
assert not bad, f"unexpected counts: {bad} -> {counts}"
ET.fromstring(s)

with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print(f"OK — all {len(counts)} edits applied once each, size {before} -> {len(s)} bytes, XML valid")
