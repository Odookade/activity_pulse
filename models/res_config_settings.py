# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    activity_pulse_kavenegar_api_key = fields.Char(
        string='کلید API کاوه‌نگار',
        config_parameter='activity_pulse.kavenegar_api_key',
    )
    activity_pulse_kavenegar_template = fields.Char(
        string='نام الگوی پیامک (Template)',
        config_parameter='activity_pulse.kavenegar_template',
        default='odooactivty',
    )
    activity_pulse_excluded_model_ids = fields.Many2many(
        related='company_id.activity_pulse_excluded_model_ids',
        readonly=False,
        string='ماژول‌های مستثنا از پایش اکتیویتی',
    )
    activity_pulse_currency_name = fields.Char(
        string='نام ارز سازمانی',
        config_parameter='activity_pulse.currency_name',
        default='سکه',
    )
    activity_pulse_currency_icon = fields.Char(
        string='آیکون ارز (اموجی یا نماد کوتاه)',
        config_parameter='activity_pulse.currency_icon',
        default='🪙',
    )
    activity_pulse_coins_per_activity = fields.Integer(
        string='مقدار پیش‌فرض پاداش هر اکتیویتی',
        config_parameter='activity_pulse.coins_per_activity',
        default=10,
    )
