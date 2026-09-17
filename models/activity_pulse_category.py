# -*- coding: utf-8 -*-
from odoo import models, fields


class ActivityPulseCategory(models.Model):
    """
    دسته‌بندی کاربران توسط مدیر، صرفاً برای مرتب‌سازی/فیلتر بهتر باکس‌های
    گرید تیم در پنل (مثلاً «فروش»، «پشتیبانی»، «تولید محتوا» و ...).
    یک کاربر می‌تونه توی چند دسته هم‌زمان باشه.
    """
    _name = 'activity.pulse.category'
    _description = 'دسته‌بندی کاربران پایش اکتیویتی'
    _order = 'sequence, name'

    name = fields.Char(string='نام دسته', required=True)
    sequence = fields.Integer(string='ترتیب نمایش', default=10)
    user_ids = fields.Many2many(
        'res.users', 'activity_pulse_category_user_rel', 'category_id', 'user_id',
        string='اعضای این دسته',
        domain=[('share', '=', False)],
    )
    member_count = fields.Integer(string='تعداد اعضا', compute='_compute_member_count')

    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.user_ids)
