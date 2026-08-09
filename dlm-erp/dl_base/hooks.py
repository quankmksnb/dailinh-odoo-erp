from odoo import tools


def post_init_hook(env):
    """Nạp bản dịch chuẩn của Odoo ngay khi cài mới DLM-ERP.

    Chỉ đánh dấu ``vi_VN`` là active không đủ cho database mới: các module
    ``web``, ``mail`` đã được cài trước ``dl_base`` nên bản dịch của chúng chưa
    được import. Nạp ngôn ngữ tại đây để màn đăng nhập, chatter và nút chuẩn của
    Odoo không còn trộn tiếng Anh.
    """
    tools.load_language(env.cr, "vi_VN")

    # VND is archived by default in some Odoo databases. If it stays archived,
    # monetary widgets fall back to a generic 2-decimal number and omit the ₫
    # symbol even when business records already point to VND.
    env["res.company"]._dlm_enforce_vnd()
    env["res.users"].with_context(active_test=False).search(
        [("share", "=", False)]
    ).write({"lang": "vi_VN"})
