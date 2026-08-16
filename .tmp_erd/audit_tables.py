# -*- coding: utf-8 -*-
"""Danh sách bảng TRONG BẢN VẼ (phys_data.GROUPS) vs model thật trong source."""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import phys_data as PD

drawn = set()
for g, n, ts in PD.GROUPS:
    drawn |= set(ts)
drawn |= set(PD.PERIPHERAL)
print('bang trong ban ve: %d' % len(drawn))

src = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))
models = {}
for r in src:
    if r['kind'] != 'Model':
        continue
    nm = r['name'] or (r['inherit'] if isinstance(r['inherit'], str) else None)
    if not nm:
        continue
    models.setdefault(nm, []).append(r)

print()
print('== Model co trong source ma BAN VE khong co hop ==')
for m in sorted(models):
    tb = m.replace('.', '_')
    if tb in drawn:
        continue
    own = any(r['name'] for r in models[m])
    nf = sum(len(r['fields']) for r in models[m])
    mods = sorted({r['module'] for r in models[m]})
    print('  %-36s %-9s fields=%-3s %s' % (
        tb, 'OWN' if own else 'inherit', nf, ','.join(mods)))

print()
print('== Hop trong ban ve ma source khong co model tuong ung ==')
srctb = {m.replace('.', '_') for m in models}
for tb in sorted(drawn):
    if tb in srctb:
        continue
    print('  %-36s %s' % (tb, 'core/M2M/rel' ))
