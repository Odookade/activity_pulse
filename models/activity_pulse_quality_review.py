# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class ActivityPulseQualityReview(models.Model):
    """
    وقتی یه اکتیویتیِ محول‌شده (نه خودساخته) «انجام شد» می‌خوره، این رکورد
    ساخته می‌شه تا محول‌کننده بتونه کیفیتش رو تأیید/رد کنه. تکمیلِ خودِ کار
    هیچ‌وقت معطل این بررسی نمی‌مونه — این صرفاً یک لایه‌ی بازبینیِ بعد از
    انجام است.
    """
    _name = 'activity.pulse.quality_review'
    _description = 'بررسی کیفیت انجام‌کار'
    _order = 'create_date desc'

    history_id = fields.Many2one('activity.pulse.history', string='رکورد تاریخچه',
                                  required=True, ondelete='cascade')
    performed_by = fields.Many2one('res.users', string='انجام‌دهنده کار', required=True)
    approver_id = fields.Many2one('res.users', string='محول‌کننده (تأییدکننده)', required=True)
    state = fields.Selection([
        ('pending', 'در انتظار بررسی'),
        ('approved', 'تأییدشده'),
        ('rejected', 'ردشده'),
    ], default='pending', string='وضعیت', required=True)
    rejection_reason = fields.Text(string='دلیل رد')
    decision_date = fields.Datetime(string='تاریخ تصمیم')
    new_activity_id = fields.Many2one('mail.activity', string='اکتیویتی جدید (در صورت رد)')

    # اسنپ‌شات برای نمایش سریع در لیست، بدون نیاز به join با history
    res_name = fields.Char(string='رکورد مرتبط')
    activity_summary = fields.Char(string='خلاصه')

    # پیامی که موقع ایجاد این بررسی برای محول‌کننده توی Discuss ارسال شد؛ وقتی
    # تصمیم گرفته بشه (تأیید/رد)، همین پیام خودکار خوانده‌شده علامت می‌خوره تا
    # صندوق پستی کاربر با موارد قدیمی و دیگه بی‌ربط شلوغ نمونه.
    notification_message_id = fields.Many2one('mail.message', string='پیام نوتیف مرتبط')

    def _mark_notification_read(self):
        if self.notification_message_id:
            try:
                self.notification_message_id.sudo().set_message_done()
            except Exception:
                pass

    def action_approve(self):
        self.ensure_one()
        if self.env.uid != self.approver_id.id:
            raise AccessError('فقط محول‌کننده‌ی این کار می‌تواند تأییدش کند.')
        if self.state != 'pending':
            raise UserError('این مورد قبلاً بررسی شده است.')
        self.write({'state': 'approved', 'decision_date': fields.Datetime.now()})
        self._mark_notification_read()
        self._maybe_create_pending_reward()
        return True

    def _maybe_create_pending_reward(self):
        """
        اگر شرایط پاداش برقرار باشه، یک تراکنش «در انتظار تأیید پاداش» می‌سازه:
        - محول‌کننده (کسی که همین الان تأیید کرد) باید عضو گروه مدیریتی باشه
          (تا دو همکار عادی نتونن با تبانی برای هم پاداش بسازن)
        - کار نباید با تاخیر انجام شده باشه (delay_days > 0 یعنی دیرکرد)
        این پاداش خودش هنوز به موجودی اضافه نمی‌شه؛ باید از صفِ «تأیید پاداش‌ها»
        توسط یک مدیر تأیید نهایی بشه (لایه‌ی حسابرسیِ مستقل دوم).
        """
        history = self.history_id.sudo()
        is_approver_manager = self.approver_id.has_group('activity_pulse.group_activity_pulse_manager')
        was_on_time = history.delay_days is not None and history.delay_days <= 0
        if not (is_approver_manager and was_on_time):
            return

        icp = self.env['ir.config_parameter'].sudo()
        default_amount = int(icp.get_param('activity_pulse.coins_per_activity', '10') or 10)

        self.env['activity.pulse.wallet.transaction'].sudo().create({
            'user_id': self.performed_by.id,
            'amount': default_amount,
            'type': 'earn',
            'state': 'pending',
            'description': 'پاداش انجامِ به‌موقع: %s' % (self.activity_summary or self.res_name or ''),
            'quality_review_id': self.id,
        })

    def action_reject(self, reason, new_deadline):
        self.ensure_one()
        if self.env.uid != self.approver_id.id:
            raise AccessError('فقط محول‌کننده‌ی این کار می‌تواند ردش کند.')
        if self.state != 'pending':
            raise UserError('این مورد قبلاً بررسی شده است.')
        if not reason or not reason.strip():
            raise UserError('لطفاً دلیل رد را بنویسید.')
        if not new_deadline:
            raise UserError('لطفاً موعد جدید را مشخص کنید.')

        history = self.history_id.sudo()
        history.write({
            'quality_rejected': True,
            'quality_rejection_reason': reason.strip(),
        })

        ir_model = self.env['ir.model'].sudo()._get(history.res_model)
        new_activity = self.env['mail.activity'].sudo().create({
            'res_model_id': ir_model.id,
            'res_id': history.res_id,
            'activity_type_id': history.activity_type_id.id,
            'summary': history.summary,
            'user_id': history.user_id.id,
            'date_deadline': new_deadline,
        })

        self.write({
            'state': 'rejected',
            'rejection_reason': reason.strip(),
            'decision_date': fields.Datetime.now(),
            'new_activity_id': new_activity.id,
        })
        self._mark_notification_read()

        partner = history.user_id.partner_id
        if partner:
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject='کیفیت انجام کار تأیید نشد',
                body=(
                    'کیفیت انجامِ «%s» توسط %s تأیید نشد.<br/>دلیل: %s<br/>'
                    'یک اکتیویتی جدید با همان مشخصات و موعد جدید براتون ثبت شد.'
                ) % (
                    history.summary or history.res_name or '',
                    self.env.user.name,
                    reason.strip(),
                ),
            )
        return True

    def get_my_pending_reviews(self):
        """موارد در انتظار بررسیِ کاربر جاری (به‌عنوان محول‌کننده)."""
        from .jalali_utils import format_jalali
        excluded_models = self.env['mail.activity']._get_excluded_model_names()
        reviews = self.search([('approver_id', '=', self.env.uid), ('state', '=', 'pending')])
        result = []
        for r in reviews:
            # sudo عمدی: مالکیتِ این بررسی از قبل با فیلتر approver_id تأیید شده،
            # پس خواندن رکورد تاریخچه‌ی مرتبط (که ممکنه مالکش کاربر دیگه‌ای باشه)
            # نباید به قانون دسترسیِ «فقط تاریخچه‌ی خودت» بخوره.
            history = r.history_id.sudo()
            if history and excluded_models and history.res_model in excluded_models:
                continue  # این مدل مستثناست، توی صف بررسی کیفیت نشون داده نمی‌شه
            result.append({
                'id': r.id,
                'res_model': history.res_model if history else False,
                'res_id': history.res_id if history else False,
                'res_name': r.res_name or '',
                'activity_summary': r.activity_summary or '',
                'performed_by_name': r.performed_by.name,
                'original_deadline_jalali': format_jalali(history.original_deadline) if history else '',
                'completion_date_jalali': format_jalali(history.completion_date) if history else '',
                'feedback': history.feedback if history else '',
            })
        return result
