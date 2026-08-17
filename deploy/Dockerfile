FROM odoo:17.0

USER root

# Chỉ python-docx là thiếu trong image gốc (dl_sale import dưới tên 'docx').
# reportlab / PIL / lxml / psycopg2 / dateutil / markupsafe đã có sẵn trong odoo:17.0.
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Font tiếng Việt cho PDF/Word xuất ra từ dl_sale, dl_purchase.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

USER odoo
