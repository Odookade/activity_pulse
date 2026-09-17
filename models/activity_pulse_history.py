# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError


class ActivityPulseHistory(models.Model):
    """
    هر بار اکتیویتی‌ای «انجام‌شده» علامت بخوره (از هرجای اودو، نه فقط پنل ما)،
    یک رکورد اینجا ثبت می‌شه. چون خودِ mail.activity بعد از انجام‌شدن حذف
    می‌شه (رفتار بومی اودو)، بدون این مدل هیچ تاریخچه‌ای برای محاسبه
    تاخیر/بهره‌وری نمی‌موند.
    """
    _name = 'activity.pulse.history'
    _description = 'تاریخچه انجام اکتیویتی (برای محاسبه بهره‌وری)'
    _order = 'completion_date asc, id asc'

    user_id = fields.Many2one('res.users', string='مسئول', required=True, index=True)
    res_model = fields.Char(string='مدل مبدأ')
    res_id = fields.Integer(string='شناسه رکورد مبدأ')
    res_name = fields.Char(string='رکورد مرتبط')
    activity_type_id = fields.Many2one('mail.activity.type', string='نوع اکتیویتی')
    summary = fields.Char(string='خلاصه')
    original_deadline = fields.Date(string='موعد اولیه')
    completion_date = fields.Date(string='تاریخ انجام', default=fields.Date.context_today)
    delay_days = fields.Integer(string='روزهای تاخیر (منفی یعنی زودتر از موعد)')
    feedback = fields.Text(string='بازخورد')
    had_extension = fields.Boolean(string='آیا موعدش تمدید تأییدشده داشته؟')
    extension_days = fields.Integer(string='تعداد روز تمدیدشده')
    extension_reason = fields.Text(string='دلیل تمدید')
    quality_rejected = fields.Boolean(string='کیفیتش توسط محول‌کننده رد شده؟')
    quality_rejection_reason = fields.Text(string='دلیل رد کیفیت')

    def get_user_history(self, user_id):
        """
        فقط مدیر یا خودِ کاربر: تاریخچه انجام اکتیویتی‌ها به ترتیب انجام،
        همراه با میانگین روزهای تاخیر/زودتر بودن.
        """
        is_manager = self.env.user.has_group('activity_pulse.group_activity_pulse_manager')
        if not (is_manager or self.env.uid == user_id):
            raise AccessError('شما اجازه مشاهده تاریخچه این کاربر را ندارید.')

        excluded_models = self.env['mail.activity']._get_excluded_model_names()
        domain = [('user_id', '=', user_id)]
        if excluded_models:
            domain.append(('res_model', 'not in', excluded_models))
        records = self.search(domain, order='completion_date asc, id asc')
        from .jalali_utils import format_jalali

        history = []
        total_delay = 0
        for rec in records:
            history.append({
                'id': rec.id,
                'res_model': rec.res_model,
                'res_id': rec.res_id,
                'res_name': rec.res_name or '',
                'activity_type': rec.activity_type_id.name or '',
                'summary': rec.summary or '',
                'original_deadline_jalali': format_jalali(rec.original_deadline) if rec.original_deadline else '',
                'completion_date_jalali': format_jalali(rec.completion_date) if rec.completion_date else '',
                'delay_days': rec.delay_days,
                'had_extension': rec.had_extension,
                'extension_days': rec.extension_days,
                'extension_reason': rec.extension_reason or '',
                'quality_rejected': rec.quality_rejected,
                'quality_rejection_reason': rec.quality_rejection_reason or '',
            })
            total_delay += rec.delay_days

        count = len(records)
        avg_delay = round(total_delay / count, 1) if count else 0
        return {
            'history': history,
            'average_delay_days': avg_delay,
            'count': count,
        }

    def get_user_kpi_dashboard(self, user_id, period_type='month', jyear=None, jmonth=None):
        """
        داشبورد KPI بالای پنل هر کاربر. فقط مدیر یا خودِ کاربر.
        period_type: 'month' یا 'year' — پیش‌فرض ماه جاری شمسی.
        """
        from .jalali_utils import today_jalali, jalali_month_range, jalali_year_range, PERSIAN_MONTHS
        from .mail_activity import STATE_COLOR_MAP

        is_manager = self.env.user.has_group('activity_pulse.group_activity_pulse_manager')
        if not (is_manager or self.env.uid == user_id):
            raise AccessError('شما اجازه مشاهده گزارش این کاربر را ندارید.')

        cur_jy, cur_jm, _ = today_jalali()
        jyear = jyear or cur_jy

        if period_type == 'year':
            start, end = jalali_year_range(jyear)
            period_label = 'سال %d' % jyear
            jmonth = None
        else:
            jmonth = jmonth or cur_jm
            start, end = jalali_month_range(jyear, jmonth)
            period_label = '%s %d' % (PERSIAN_MONTHS[jmonth - 1], jyear)

        excluded = self.env.company.sudo().activity_pulse_excluded_model_ids.mapped('model')
        records_domain = [
            ('user_id', '=', user_id),
            ('completion_date', '>=', start),
            ('completion_date', '<=', end),
        ]
        if excluded:
            records_domain.append(('res_model', 'not in', excluded))
        records = self.search(records_domain)
        count = len(records)
        delays = records.mapped('delay_days')
        avg_delay = round(sum(delays) / count, 1) if count else 0
        on_time_count = len([d for d in delays if d <= 0])
        on_time_rate = round((on_time_count / count) * 100, 1) if count else 0
        max_delay = max(delays) if delays else 0
        min_delay = min(delays) if delays else 0

        # وضعیت اکتیویتی‌های بازِ فعلی (لحظه‌ای، مستقل از بازه انتخابی)
        # sudo عمدی: مدیر باید همه‌ی اکتیویتی‌های باز رو ببینه، حتی اونایی که خودش
        # دنبال‌کننده/محول‌کننده‌ی رکورد مبدأشون نیست.
        activity_model = self.env['mail.activity'].sudo() if is_manager else self.env['mail.activity']
        domain = [('user_id', '=', user_id)]
        if excluded:
            domain.append(('res_model', 'not in', excluded))
        open_activities = activity_model.search(domain)
        open_counts = {'red': 0, 'yellow': 0, 'green': 0}
        for act in open_activities:
            open_counts[STATE_COLOR_MAP.get(act.state, 'green')] += 1

        return {
            'period_type': period_type,
            'period_label': period_label,
            'jyear': jyear,
            'jmonth': jmonth,
            'completed_count': count,
            'average_delay_days': avg_delay,
            'on_time_rate': on_time_rate,
            'max_delay_days': max_delay,
            'min_delay_days': min_delay,
            'open_red': open_counts['red'],
            'open_yellow': open_counts['yellow'],
            'open_green': open_counts['green'],
        }
