# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError


class ActivityPulseCancellation(models.Model):
    """
    هر بار اکتیویتی‌ای بدون ثبت انجام‌شدن (بدون بازخورد) لغو/حذف بشه، یک رکورد
    اینجا ثبت می‌شه — چه از پنل ما، چه از چت‌تر/کانبان بومی اودو — تا قابل
    گزارش‌گیری و پیگیری بمونه.
    """
    _name = 'activity.pulse.cancellation'
    _description = 'تاریخچه لغو اکتیویتی (بدون تکمیل)'
    _order = 'cancellation_date desc, id desc'

    user_id = fields.Many2one('res.users', string='مسئول اکتیویتی', required=True, index=True)
    cancelled_by = fields.Many2one('res.users', string='لغوکننده', required=True)
    res_model = fields.Char(string='مدل مبدأ')
    res_id = fields.Integer(string='شناسه رکورد مبدأ')
    res_name = fields.Char(string='رکورد مرتبط')
    activity_type_id = fields.Many2one('mail.activity.type', string='نوع اکتیویتی')
    summary = fields.Char(string='خلاصه')
    original_deadline = fields.Date(string='موعد در لحظه‌ی لغو')
    cancellation_date = fields.Date(string='تاریخ لغو', default=fields.Date.context_today)

    def get_user_cancellations(self, user_id):
        is_manager = self.env.user.has_group('activity_pulse.group_activity_pulse_manager')
        if not (is_manager or self.env.uid == user_id):
            raise AccessError('شما اجازه مشاهده این اطلاعات را ندارید.')

        from .jalali_utils import format_jalali
        excluded_models = self.env['mail.activity']._get_excluded_model_names()
        domain = [('user_id', '=', user_id)]
        if excluded_models:
            domain.append(('res_model', 'not in', excluded_models))
        records = self.search(domain)
        result = []
        for rec in records:
            result.append({
                'id': rec.id,
                'res_model': rec.res_model,
                'res_id': rec.res_id,
                'res_name': rec.res_name or '',
                'activity_type': rec.activity_type_id.name or '',
                'summary': rec.summary or '',
                'cancelled_by_name': rec.cancelled_by.name or '',
                'original_deadline_jalali': format_jalali(rec.original_deadline) if rec.original_deadline else '',
                'cancellation_date_jalali': format_jalali(rec.cancellation_date) if rec.cancellation_date else '',
            })
        return result
