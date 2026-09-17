# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class ActivityPulseWalletTransaction(models.Model):
    """
    دفترکل کیف پول سازمانی. موجودی هر کاربر همیشه از روی جمع تراکنش‌های
    «تأییدشده»‌ی همون کاربر محاسبه می‌شه (نه یه عدد جدا که باید سینک بشه)،
    تا همیشه قابل ردیابی باشه که موجودی از کجا اومده.

    نوع تراکنش‌ها:
      - earn: پاداش عملکرد (از بررسی کیفیت تأییدشده)
      - spend: خرید از فروشگاه
      - refund: برگشتِ سکه (وقتی یه خرید رد بشه)
      - adjustment: اصلاح دستی توسط مدیر

    برای earn، تراکنش با state='pending' ساخته می‌شه و تا وقتی مدیر از صفِ
    «تأیید پاداش‌ها» تأییدش نکنه، توی موجودی حساب نمی‌شه — این یه لایه‌ی
    حسابرسیِ جدا و مستقل از خودِ تأیید کیفیته.
    """
    _name = 'activity.pulse.wallet.transaction'
    _description = 'تراکنش کیف پول سازمانی'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='کاربر', required=True, index=True)
    amount = fields.Integer(string='مقدار', required=True, help='برای برداشت/خرید عدد منفی وارد کنید')
    type = fields.Selection([
        ('earn', 'پاداش عملکرد'),
        ('spend', 'خرید از فروشگاه'),
        ('refund', 'برگشت وجه'),
        ('adjustment', 'اصلاح دستی'),
    ], string='نوع', required=True)
    state = fields.Selection([
        ('pending', 'در انتظار تأیید'),
        ('approved', 'تأییدشده'),
        ('rejected', 'ردشده'),
    ], string='وضعیت', default='approved', required=True)

    description = fields.Char(string='توضیح')
    quality_review_id = fields.Many2one('activity.pulse.quality_review', string='بررسی کیفیت مرتبط')
    store_order_id = fields.Many2one('activity.pulse.store.order', string='سفارش فروشگاه مرتبط')

    decided_by = fields.Many2one('res.users', string='تأییدکننده')
    decision_date = fields.Datetime(string='تاریخ تصمیم')
    decision_note = fields.Text(string='توضیح تصمیم')

    def get_my_wallet_summary(self):
        """موجودی + چند تراکنش آخرِ کاربر جاری (یا هر کاربری برای مدیر)."""
        return self.get_wallet_summary(self.env.uid)

    def get_wallet_summary(self, user_id):
        is_manager = self.env.user.has_group('activity_pulse.group_activity_pulse_manager')
        if not (is_manager or self.env.uid == user_id):
            raise AccessError('شما اجازه مشاهده کیف پول این کاربر را ندارید.')

        approved = self.sudo().search([('user_id', '=', user_id), ('state', '=', 'approved')])
        balance = sum(approved.mapped('amount'))

        recent = self.sudo().search(
            [('user_id', '=', user_id), ('state', '=', 'approved')],
            order='create_date desc', limit=10,
        )
        from .jalali_utils import format_jalali
        transactions = [{
            'id': t.id,
            'amount': t.amount,
            'type': t.type,
            'description': t.description or '',
            'date_jalali': format_jalali(fields.Date.to_date(t.create_date)) if t.create_date else '',
        } for t in recent]

        icp = self.env['ir.config_parameter'].sudo()
        return {
            'balance': balance,
            'currency_name': icp.get_param('activity_pulse.currency_name', 'سکه'),
            'currency_icon': icp.get_param('activity_pulse.currency_icon', '🪙'),
            'transactions': transactions,
        }

    def action_manual_deposit(self, user_id, amount, description=''):
        """
        واریز دستی سکه به کیف پول یک کاربر توسط مدیر — بدون نیاز به اینکه
        اکتیویتی یا بررسی کیفیتی پشتش باشه؛ برای وقتی مدیر می‌خواد هر زمان
        که خودش صلاح بدونه، مستقیم پاداش بده. تراکنش فوراً approved ثبت
        می‌شه (نه pending)، چون خودِ مدیر مستقیماً داره واریز می‌کنه.
        """
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران می‌توانند سکه واریز کنند.')
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            raise UserError('مقدار واریزی باید عددی مثبت باشد.')

        target_user = self.env['res.users'].sudo().browse(int(user_id))
        if not target_user.exists():
            raise UserError('کاربر موردنظر یافت نشد.')

        self.sudo().create({
            'user_id': target_user.id,
            'amount': amount,
            'type': 'adjustment',
            'state': 'approved',
            'description': description or 'واریز دستی توسط مدیر',
            'decided_by': self.env.uid,
            'decision_date': fields.Datetime.now(),
        })

        partner = target_user.partner_id
        if partner:
            icp = self.env['ir.config_parameter'].sudo()
            currency_name = icp.get_param('activity_pulse.currency_name', 'سکه')
            body = 'مبلغ %s %s توسط «%s» به کیف پول شما واریز شد.' % (
                amount, currency_name, self.env.user.name,
            )
            if description:
                body += '<br/>توضیح: %s' % description
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject='واریز به کیف پول سازمانی',
                body=body,
            )
        return True

    def get_my_pending_reward_approvals(self):
        """فقط مدیران: پاداش‌های در انتظار تأیید (از هر کارمندی، نه فقط زیردستان مستقیم)."""
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران به این بخش دسترسی دارند.')
        pending = self.sudo().search([('type', '=', 'earn'), ('state', '=', 'pending')])
        return [{
            'id': t.id,
            'user_name': t.user_id.name,
            'amount': t.amount,
            'description': t.description or '',
        } for t in pending]

    def action_approve_reward(self, amount=None):
        self.ensure_one()
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران می‌توانند پاداش را تأیید کنند.')
        if self.state != 'pending':
            raise UserError('این پاداش قبلاً بررسی شده است.')
        vals = {
            'state': 'approved',
            'decided_by': self.env.uid,
            'decision_date': fields.Datetime.now(),
        }
        if amount:
            vals['amount'] = int(amount)
        self.write(vals)
        self._notify_user('پاداش شما تأیید و به کیف پول واریز شد.')
        return True

    def action_reject_reward(self, reason=''):
        self.ensure_one()
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران می‌توانند پاداش را رد کنند.')
        if self.state != 'pending':
            raise UserError('این پاداش قبلاً بررسی شده است.')
        self.write({
            'state': 'rejected',
            'decided_by': self.env.uid,
            'decision_date': fields.Datetime.now(),
            'decision_note': reason or '',
        })
        self._notify_user('متأسفانه پاداش شما تأیید نشد.' + (' دلیل: %s' % reason if reason else ''))
        return True

    def _notify_user(self, message):
        partner = self.user_id.partner_id
        if partner:
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject='به‌روزرسانی کیف پول سازمانی',
                body=message,
            )
