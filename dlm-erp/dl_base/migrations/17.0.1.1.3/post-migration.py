def migrate(cr, version):
    """Dùng tiếng Việt cho mọi tài khoản nội bộ hiện có."""
    cr.execute(
        """
        UPDATE res_partner AS partner
           SET lang = 'vi_VN'
          FROM res_users AS users
         WHERE users.partner_id = partner.id
           AND NOT users.share
        """
    )
