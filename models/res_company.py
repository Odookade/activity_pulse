# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    activity_pulse_excluded_model_ids = fields.Many2many(
        'ir.model',
        'activity_pulse_excluded_model_rel',
        'company_id',
        'model_id',
        string='ماژول‌های مستثنا از پایش اکتیویتی',
        help='اکتیویتی‌های مربوط به این مدل‌ها اصلاً توی داشبورد/تاریخچه/بررسی '
             'کیفیت پایش اکتیویتی حساب نمی‌شن.',
    )
