# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools
from .jalali_utils import format_jalali

STATE_LABEL_MAP = {
    'overdue': 'دارای تاخیر',
    'today': 'امروز',
    'planned': 'برنامه‌ریزی‌شده',
}


class ActivityPulseLine(models.Model):
    """
    مدل گزارشی (SQL View) و غیرقابل‌ویرایش، مخصوص پنل مدیریتی.
    عمداً به‌جای استفاده مستقیم از mail.activity، یک مدل مجزا ساختیم تا هیچ‌گونه
    قانون امنیتی (ir.rule) جدیدی روی خودِ مدل اصلی mail.activity اعمال نشه —
    چون آن مدل در سرتاسر اودو (چت‌تر، کانبان‌ها، منوی Activities) استفاده می‌شه
    و دستکاری امنیتش می‌تونه رفتار بقیه ماژول‌ها رو به‌هم بریزه.
    """
    _name = 'activity.pulse.line'
    _description = 'ردیف گزارش داشبورد اکتیویتی'
    _auto = False
    _order = 'date_deadline asc'

    activity_id = fields.Many2one('mail.activity', string='اکتیویتی', readonly=True)
    user_id = fields.Many2one('res.users', string='مسئول', readonly=True)
    res_model = fields.Char(string='مدل مبدأ', readonly=True)
    res_id = fields.Integer(string='شناسه رکورد مبدأ', readonly=True)
    res_name = fields.Char(string='رکورد مرتبط', readonly=True)
    activity_type_id = fields.Many2one('mail.activity.type', string='نوع اکتیویتی', readonly=True)
    summary = fields.Char(string='خلاصه', readonly=True)
    date_deadline = fields.Date(string='موعد', readonly=True)
    state = fields.Selection(
        [('overdue', 'دارای تاخیر'), ('today', 'امروز'), ('planned', 'برنامه‌ریزی‌شده')],
        string='وضعیت', readonly=True,
    )
    delay_days = fields.Integer(string='روزهای تاخیر', readonly=True)

    date_deadline_jalali = fields.Char(string='موعد (شمسی)', compute='_compute_jalali')
    state_label = fields.Char(string='برچسب وضعیت', compute='_compute_jalali')

    def _compute_jalali(self):
        for rec in self:
            rec.date_deadline_jalali = format_jalali(rec.date_deadline) if rec.date_deadline else ''
            rec.state_label = STATE_LABEL_MAP.get(rec.state, '')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    act.id AS id,
                    act.id AS activity_id,
                    act.user_id AS user_id,
                    act.res_model AS res_model,
                    act.res_id AS res_id,
                    act.res_name AS res_name,
                    act.activity_type_id AS activity_type_id,
                    COALESCE(act.summary, '') AS summary,
                    act.date_deadline AS date_deadline,
                    CASE
                        WHEN act.date_deadline < CURRENT_DATE THEN 'overdue'
                        WHEN act.date_deadline = CURRENT_DATE THEN 'today'
                        ELSE 'planned'
                    END AS state,
                    GREATEST((CURRENT_DATE - act.date_deadline), 0) AS delay_days
                FROM mail_activity act
            )
        """ % self._table)

    def is_activity_pulse_manager(self):
        return self.env.user.has_group('activity_pulse.group_activity_pulse_manager') or \
            self.env.user.has_group('base.group_system')

    def get_employee_summary(self):
        """برای مدیر: خلاصه‌ی تعداد اکتیویتی هر کاربر (قرمز/زرد/سبز) برای نمایش باکس‌ها"""
        if not self.is_activity_pulse_manager():
            return []
        lines = self.search_read([], ['user_id', 'state'])
        summary = {}
        for line in lines:
            if not line['user_id']:
                continue
            uid_, uname = line['user_id']
            entry = summary.setdefault(uid_, {
                'user_id': uid_, 'user_name': uname,
                'red': 0, 'yellow': 0, 'green': 0, 'total': 0,
            })
            entry['total'] += 1
            if line['state'] == 'overdue':
                entry['red'] += 1
            elif line['state'] == 'today':
                entry['yellow'] += 1
            else:
                entry['green'] += 1
        result = list(summary.values())
        result.sort(key=lambda e: (-e['red'], -e['yellow'], e['user_name']))
        return result

    def get_dashboard_activities(self, user_id=False):
        """
        بدون user_id: اکتیویتی‌های کاربر جاری.
        با user_id: فقط اگر کاربر جاری مدیر باشه، اکتیویتی‌های اون کاربر خاص رو برمی‌گردونه.
        """
        is_manager = self.is_activity_pulse_manager()
        target_user_id = user_id if (user_id and is_manager) else self.env.uid
        lines = self.search([('user_id', '=', target_user_id)], order='date_deadline asc')
        result = []
        for line in lines:
            result.append({
                'id': line.id,
                'activity_id': line.activity_id.id,
                'res_model': line.res_model,
                'res_id': line.res_id,
                'res_name': line.res_name or '',
                'activity_type': line.activity_type_id.name or '',
                'summary': line.summary or '',
                'date_deadline': line.date_deadline.strftime('%Y-%m-%d') if line.date_deadline else False,
                'date_deadline_jalali': line.date_deadline_jalali,
                'state': line.state,
                'state_label': line.state_label,
                'color': {'overdue': 'red', 'today': 'yellow', 'planned': 'green'}.get(line.state, 'green'),
                'delay_days': line.delay_days,
            })
        return result

    def action_update_deadline(self, activity_id, new_date):
        """
        تغییر موعد یک اکتیویتی. مستقیم روی خودِ مدل اصلی mail.activity عمل می‌کنه
        و از قوانین دسترسی طبیعی خودِ اودو تبعیت می‌کنه (هیچ bypass امنیتی‌ای اینجا نیست).
        """
        activity = self.env['mail.activity'].browse(activity_id)
        activity.write({'date_deadline': new_date})
        return True

    def action_send_discuss_reminder(self, activity_id):
        """ارسال پیام یادآوری در Discuss به کاربر مسئول اکتیویتی"""
        activity = self.env['mail.activity'].browse(activity_id)
        activity.ensure_one()
        partner = activity.user_id.partner_id
        if not partner:
            return False
        channel_info = self.env['discuss.channel'].channel_get([partner.id])
        channel = self.env['discuss.channel'].browse(channel_info['id'])
        body = 'سلام %s،<br/>لطفاً وضعیت انجام فعالیت «%s» (%s) رو گزارش بدید.' % (
            activity.user_id.name or '',
            activity.res_name or '',
            activity.summary or activity.activity_type_id.name or '',
        )
        channel.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def action_open_source_record(self):
        """باز کردن مستقیم رکورد مبدأ (لید، تسک، فاکتور و ...) با کلیک روی دکمه"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'target': 'current',
        }
