from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home


class DlWebHome(Home):
    """Luôn mở màn đăng nhập DLM-ERP bằng tiếng Việt."""

    @http.route()
    def web_login(self, redirect=None, **kw):
        request.session.context["lang"] = "vi_VN"
        if request.db:
            request.update_context(lang="vi_VN")
        response = super().web_login(redirect=redirect, **kw)
        # A successful authentication rebuilds the session context from the
        # user profile. Set Vietnamese again so the first redirected screen
        # already uses dd/mm/yyyy and the standard Vietnamese translations.
        request.session.context["lang"] = "vi_VN"
        if request.db:
            request.update_context(lang="vi_VN")
        return response
