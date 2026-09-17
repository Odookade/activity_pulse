# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class ActivityPulseExtensionRequest(models.Model):
    """
    درخواست تمدید موعد یک اکتیویتی. کاربر مسئول درخواست می‌ده، سازنده‌ی
    اکتیویتی تأیید/رد می‌کنه. با تأیید، موعد واقعاً تغییر می‌کنه ولی موعد
    اصلی همیشه اینجا ثبت‌شده می‌مونه تا تاریخچه/KPI هیچ‌وقت تاخیر واقعی رو
    گم نکنه.
    """
    _name = 'activity.pulse.extension.request'
    _description = 'درخواست تمدید موعد اکتیویتی'
    _order = 'create_date desc'

    activity_id = fields.Many2one('mail.activity', string='اکتیویتی', required=True, ondelete='cascade')
    requested_by = fields.Many2one('res.users', string='درخواست‌دهنده', required=True)
    approver_id = fields.Many2one('res.users', string='تأییدکننده (سازنده اکتیویتی)', required=True)
    reason = fields.Text(string='دلیل درخواست', required=True)

    # موعدِ فعلی در لحظه‌ی ثبت این درخواست (ممکنه خودش هم قبلاً یک‌بار تمدید شده باشه)
    previous_deadline = fields.Date(string='موعد قبل از این درخواست', required=True)
    # موعدِ واقعاً اولیه‌ای که این اکتیویتی از ابتدا داشته (برای همیشه ثابت می‌مونه)
    true_original_deadline = fields.Date(string='موعد اصلی (اولین موعد تعیین‌شده)', required=True)
    requested_deadline = fields.Date(string='موعد پیشنهادی', required=True)

    state = fields.Selection([
        ('pending', 'در انتظار بررسی'),
        ('approved', 'تأییدشده'),
        ('rejected', 'ردشده'),
    ], default='pending', string='وضعیت', required=True)
    decision_note = fields.Text(string='توضیح تصمیم')
    decision_date = fields.Datetime(string='تاریخ تصمیم')

    # اسنپ‌شات برای نمایش حتی بعد از اینکه اکتیویتی انجام/حذف بشه
    res_name = fields.Char(string='رکورد مرتبط')
    activity_summary = fields.Char(string='خلاصه اکتیویتی')

    # پیامی که موقع ثبت درخواست برای تأییدکننده توی Discuss ارسال شد؛ وقتی
    # تصمیم گرفته بشه (تأیید/رد)، همین پیام خودکار خوانده‌شده علامت می‌خوره
    # تا صندوق پستی کاربر با موارد قدیمی و دیگه بی‌ربط شلوغ نمونه.
    notification_message_id = fields.Many2one('mail.message', string='پیام نوتیف مرتبط')

    def _get_true_original_deadline(self, activity):
        """موعد واقعاً اولیه رو با دنبال کردن زنجیره‌ی تمدیدهای قبلی همین اکتیویتی پیدا می‌کنه."""
        prior = self.sudo().search([
            ('activity_id', '=', activity.id),
            ('state', '=', 'approved'),
        ], order='create_date asc', limit=1)
        return prior.true_original_deadline if prior else activity.date_deadline

    def _mark_notification_read(self):
        """پیام نوتیفی که موقع ایجاد این درخواست ارسال شده رو برای تأییدکننده خوانده‌شده می‌کنه."""
        if self.notification_message_id:
            try:
                self.notification_message_id.sudo().set_message_done()
            except Exception:
                pass

    def action_approve(self, decision_note=''):
        self.ensure_one()
        if self.env.uid != self.approver_id.id:
            raise AccessError('فقط سازنده‌ی اکتیویتی می‌تواند این درخواست را تأیید کند.')
        if self.state != 'pending':
            raise UserError('این درخواست قبلاً بررسی شده است.')

        activity = self.activity_id.sudo()
        activity.write({'date_deadline': self.requested_deadline})
        self.write({
            'state': 'approved',
            'decision_note': decision_note or '',
            'decision_date': fields.Datetime.now(),
        })
        self._mark_notification_read()
        self._notify_requester('تأیید شد', decision_note)
        self._log_to_chatter(
            'موعد اکتیویتی «%s» طبق درخواست تمدید، تأیید و به‌روزرسانی شد.' % (self.activity_summary or '')
        )
        return True

    def action_reject(self, decision_note=''):
        self.ensure_one()
        if self.env.uid != self.approver_id.id:
            raise AccessError('فقط سازنده‌ی اکتیویتی می‌تواند این درخواست را رد کند.')
        if self.state != 'pending':
            raise UserError('این درخواست قبلاً بررسی شده است.')

        self.write({
            'state': 'rejected',
            'decision_note': decision_note or '',
            'decision_date': fields.Datetime.now(),
        })
        self._mark_notification_read()
        self._notify_requester('رد شد', decision_note)
        return True

    def _notify_requester(self, result_label, decision_note):
        partner = self.requested_by.partner_id
        if not partner:
            return
        body = 'درخواست تمدید موعد شما برای «%s» %s.' % (self.activity_summary or '', result_label)
        if decision_note:
            body += '<br/>توضیح: %s' % decision_note
        self.env['mail.thread'].sudo().message_notify(
            partner_ids=partner.ids,
            subject='نتیجه‌ی درخواست تمدید موعد',
            body=body,
        )

    def _log_to_chatter(self, message):
        try:
            act = self.activity_id.sudo()
            if not act.res_model or not act.res_id:
                return
            doc = self.env[act.res_model].sudo().browse(act.res_id)
            if doc.exists() and hasattr(doc, 'message_post'):
                doc.message_post(body=message)
        except Exception:
            pass

    def get_my_pending_requests(self):
        """درخواست‌های در انتظار بررسیِ کاربر جاری (به‌عنوان سازنده‌ی اکتیویتی)."""
        requests = self.search([('approver_id', '=', self.env.uid), ('state', '=', 'pending')])
        result = []
        from .jalali_utils import format_jalali
        for req in requests:
            activity = req.activity_id.sudo()
            result.append({
                'id': req.id,
                'res_model': activity.res_model if activity else False,
                'res_id': activity.res_id if activity else False,
                'requested_by_name': req.requested_by.name,
                'res_name': req.res_name or '',
                'activity_summary': req.activity_summary or '',
                'reason': req.reason,
                'previous_deadline_jalali': format_jalali(req.previous_deadline),
                'requested_deadline_jalali': format_jalali(req.requested_deadline),
                'create_date': req.create_date,
            })
        return result
