# -*- coding: utf-8 -*-
import re
import logging
from odoo import models, fields, api
from odoo.exceptions import AccessError, UserError
from .kavenegar_service import send_kavenegar_lookup
from .jalali_utils import format_jalali, format_jalali_slash

_logger = logging.getLogger(__name__)

# نگاشت وضعیت بومی اودو (overdue/today/planned) به رنگ ویجت
STATE_COLOR_MAP = {
    'overdue': 'red',
    'today': 'yellow',
    'planned': 'green',
}

# نام فارسی وضعیت‌ها برای نمایش در ویجت
STATE_LABEL_MAP = {
    'overdue': 'دارای تاخیر',
    'today': 'امروز',
    'planned': 'برنامه‌ریزی‌شده',
}


def strip_html(html_text):
    return re.sub(r'<[^<]+?>', '', html_text or '').strip()


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def _get_display_summary(self, act):
        """
        متن توضیحات نمایشی یک اکتیویتی: اول فیلد Summary، اگه خالی بود از
        فیلد Note (یادداشت)، و در نهایت از نوع اکتیویتی. این متد در همه‌ی
        جاهایی که یک «توضیح» برای اکتیویتی لازمه (تاریخچه، لغو، بررسی کیفیت،
        درخواست تمدید) استفاده می‌شه تا همه‌جا یکسان و کامل باشه — چون خیلی
        از کاربرها توضیح رو توی Note می‌نویسن، نه Summary.
        """
        return act.summary or strip_html(act.note) or (act.activity_type_id.name or '')

    def _get_excluded_model_names(self):
        """
        نام فنی مدل‌هایی که مدیر از Settings مستثنا کرده — اکتیویتی‌های این
        مدل‌ها اصلاً نباید توی داشبورد/تاریخچه/بررسی کیفیت پایش اکتیویتی
        حساب بشن.
        """
        return self.env.company.sudo().activity_pulse_excluded_model_ids.mapped('model')

    def _get_excluded_domain(self):
        """قطعه‌دامنه‌ی آماده برای اضافه‌شدن به search() تا مدل‌های مستثنا حذف بشن."""
        excluded = self._get_excluded_model_names()
        return [('res_model', 'not in', excluded)] if excluded else []

    def _format_activity(self, act, today):
        delay_days = (today - act.date_deadline).days if act.date_deadline else 0
        summary = self._get_display_summary(act)
        can_edit = self.is_activity_pulse_manager() or act.create_uid.id == self.env.uid

        ExtensionRequest = self.env['activity.pulse.extension.request'].sudo()
        approved_ext = ExtensionRequest.search([
            ('activity_id', '=', act.id), ('state', '=', 'approved'),
        ], order='create_date asc', limit=1)
        pending_ext = ExtensionRequest.search([
            ('activity_id', '=', act.id), ('state', '=', 'pending'),
        ], limit=1)

        return {
            'id': act.id,
            'res_model': act.res_model,
            'res_id': act.res_id,
            'res_name': act.res_name or '',
            'activity_type': act.activity_type_id.name or '',
            'summary': summary,
            'user_id': act.user_id.id,
            'user_name': act.user_id.name,
            'create_uid': act.create_uid.id,
            'can_edit': can_edit,
            'date_deadline': act.date_deadline.strftime('%Y-%m-%d') if act.date_deadline else False,
            'date_deadline_jalali': format_jalali(act.date_deadline),
            'state': act.state,
            'state_label': STATE_LABEL_MAP.get(act.state, ''),
            'color': STATE_COLOR_MAP.get(act.state, 'green'),
            'delay_days': delay_days if act.state == 'overdue' else 0,
            'had_extension': bool(approved_ext),
            'extension_days': (act.date_deadline - approved_ext.true_original_deadline).days
                               if (approved_ext and act.date_deadline) else 0,
            'has_pending_extension_request': bool(pending_ext),
        }

    def get_my_dashboard_activities(self):
        """
        اکتیویتی‌های باز کاربر جاری، فرمت‌شده برای ویجت داشبورد (فاز ۱).
        عمداً فیلتر «ماژول‌های مستثنا» اینجا اعمال نمی‌شه — کاربر باید بتونه
        فعالیت‌های خودش رو، حتی از ماژول‌های مستثنا، توی همین ویجت ببینه و
        انجام بده؛ استثنا فقط باعث می‌شه این فعالیت‌ها توی پنل مدیریتی،
        تاریخچه، و بررسی کیفیت حساب نشن.
        """
        activities = self.search(
            [('user_id', '=', self.env.uid)],
            order='date_deadline asc, id asc',
        )
        today = fields.Date.context_today(self)
        return [self._format_activity(act, today) for act in activities]

    def is_activity_pulse_manager(self):
        """آیا کاربر جاری عضو گروه مدیریتی ماژول است؟ (نه گروه‌های عمومی اودو)"""
        return self.env.user.has_group('activity_pulse.group_activity_pulse_manager')

    def get_activity_pulse_users(self):
        """فقط برای اعضای گروه مدیریتی: لیست کاربران داخلی برای فیلتر پنل."""
        if not self.is_activity_pulse_manager():
            return []
        users = self.env['res.users'].search(
            [('active', '=', True), ('share', '=', False)], order='name'
        )
        return [{'id': u.id, 'name': u.name} for u in users]

    def get_dashboard_activities(self, target_user_id=False):
        """
        اکتیویتی‌های پنل مدیریتی (فاز ۲).
        نکته امنیتی: کنترل دسترسی اینجا و صرفاً داخل همین متد انجام می‌شود؛
        هیچ ir.rule سراسری روی مدل mail.activity برای «خواندن» تغییر نکرده است.
        - کاربر عادی: همیشه فقط اکتیویتی‌های خودش، حتی اگر target_user_id غیر از خودش باشد.
        - عضو گروه مدیریتی: می‌تواند با دادن target_user_id، اکتیویتی‌های هر کاربری را ببیند —
          حتی اگر خودش دنبال‌کننده/محول‌کننده‌ی آن رکورد نباشد (به همین دلیل عمداً sudo
          می‌کنیم؛ در غیر این صورت قانون بومی «فقط رکوردهایی که به سند مرتبط دسترسی داری»
          جلوی دیدنِ اکتیویتی‌های بقیه رو برای مدیر هم می‌گرفت).
        """
        is_manager = self.is_activity_pulse_manager()
        if is_manager and target_user_id:
            uid = target_user_id
        else:
            uid = self.env.uid
        activity_model = self.sudo() if is_manager else self
        activities = activity_model.search(
            [('user_id', '=', uid)] + self._get_excluded_domain(), order='date_deadline asc, id asc'
        )
        today = fields.Date.context_today(self)
        return [self._format_activity(act, today) for act in activities]

    def write(self, vals):
        """
        هر بار موعد یک اکتیویتی تغییر کنه (چه از پنل ما، چه از هرجای دیگه اودو)،
        یک پیام توی چت‌تر رکورد مبدأ ثبت می‌کنیم تا رد این تغییر همیشه بمونه —
        صرف‌نظر از اینکه ir.rule جلوش رو گرفته باشه یا نه (لایه دفاعی دوم).
        """
        if 'date_deadline' in vals:
            excluded_models = self._get_excluded_model_names()
            old_deadlines = {act.id: act.date_deadline for act in self}
            result = super().write(vals)
            for act in self:
                if act.res_model in excluded_models:
                    continue
                self._log_activity_change_to_chatter(
                    act,
                    'ویرایش موعد',
                    'کاربر «%s» موعدِ اکتیویتی «%s» (مسئول: %s) را از %s به %s تغییر داد.' % (
                        self.env.user.name,
                        act.summary or (act.activity_type_id.name or ''),
                        act.user_id.name or '',
                        format_jalali(old_deadlines.get(act.id)) if old_deadlines.get(act.id) else '—',
                        format_jalali(act.date_deadline) if act.date_deadline else '—',
                    ),
                )
            return result
        return super().write(vals)

    def unlink(self):
        """
        لغوِ خام (بدون ثبت بازخورد) رو هم توی چت‌تر رکورد مبدأ لاگ می‌کنیم، هم
        به‌صورت ساختاریافته در activity.pulse.cancellation ثبت می‌کنیم (تا قابل
        نمایش توی پنل باشه). اگر این حذف بخشی از فرایند «انجام شد»
        (action_feedback) باشه، از طریق context علامت‌گذاری شده و اینجا هیچ‌کدوم
        ثبت نمی‌شه (چون برای اون حالت، خودِ تاریخچه در activity.pulse.history
        ثبت می‌شه).
        """
        if not self.env.context.get('activity_pulse_skip_cancel_log'):
            excluded_models = self._get_excluded_model_names()
            today = fields.Date.context_today(self)
            cancellation_vals = []
            for act in self:
                if act.res_model in excluded_models:
                    continue
                display_summary = self._get_display_summary(act)
                self._log_activity_change_to_chatter(
                    act,
                    'لغو اکتیویتی',
                    'کاربر «%s» اکتیویتی «%s» (مسئول: %s) را بدون ثبت انجام‌شدن لغو/حذف کرد.' % (
                        self.env.user.name,
                        display_summary,
                        act.user_id.name or '',
                    ),
                )
                cancellation_vals.append({
                    'user_id': act.user_id.id,
                    'cancelled_by': self.env.uid,
                    'res_model': act.res_model,
                    'res_id': act.res_id,
                    'res_name': act.res_name or '',
                    'activity_type_id': act.activity_type_id.id,
                    'summary': display_summary,
                    'original_deadline': act.date_deadline,
                    'cancellation_date': today,
                })
            if cancellation_vals:
                self.env['activity.pulse.cancellation'].sudo().create(cancellation_vals)
        return super().unlink()

    def _log_activity_change_to_chatter(self, act, label, message):
        """پست پیام روی چت‌تر رکورد مبدأ (اگه مدلش mail.thread باشه)."""
        try:
            if not act.res_model or not act.res_id:
                return
            doc = self.env[act.res_model].sudo().browse(act.res_id)
            if doc.exists() and hasattr(doc, 'message_post'):
                doc.message_post(body=message)
        except Exception:
            _logger.exception('Activity Pulse: failed to log "%s" to chatter', label)

    def action_feedback(self, *args, **kwargs):
        """
        این متد بومی اودو، هروقت اکتیویتی «انجام‌شده» علامت بخوره صدا زده می‌شه —
        چه از پنل ما، چه از چت‌تر، چه از کانبان هر جای دیگه اودو. قبل از اجرای
        رفتار اصلی (که در نهایت اکتیویتی رو حذف می‌کنه)، یک رکورد تاریخچه ثبت
        می‌کنیم تا بشه بعداً تاخیر/بهره‌وری هر کاربر رو محاسبه کرد.

        نکته مهم درباره دسترسی: از نسخه‌ای که ir.rule سراسری روی mail.activity
        اضافه شد (ویرایش/لغو فقط برای سازنده یا مدیر)، «انجام شد» عمداً از این
        محدودیت معاف است — چون این یک عمل مجاز و مورد انتظار برای خودِ کاربر
        مسئول است (تکمیل کار با ثبت بازخورد)، برخلاف ویرایش موعد یا لغوِ خام
        بدون بازخورد که باید فقط دست سازنده/مدیر باشه. برای همین مرحله نهایی
        رو با sudo انجام می‌دیم تا محدودیت جدید مانع تکمیل کار توسط خودِ کاربر
        نشه.
        """
        feedback = kwargs.get('feedback')
        if feedback is None and args:
            feedback = args[0]
        today = fields.Date.context_today(self)
        excluded_models = self._get_excluded_model_names()
        ExtensionRequest = self.env['activity.pulse.extension.request'].sudo()
        history_vals = []
        counted_activities = self.browse()
        for act in self:
            if act.res_model in excluded_models:
                continue  # این مدل مستثناست: نه تاریخچه، نه بررسی کیفیت
            # اگه این اکتیویتی قبلاً تمدید تأییدشده داشته، تاخیر رو نسبت به موعد
            # *اصلیِ* اولیه حساب می‌کنیم، نه موعد تمدیدشده — تا تاخیر واقعی هیچ‌وقت
            # از چشم پنهون نمونه، حتی اگه با دلیل موجه تمدید گرفته باشه.
            approved_ext = ExtensionRequest.search([
                ('activity_id', '=', act.id),
                ('state', '=', 'approved'),
            ], order='create_date asc', limit=1)
            true_original = approved_ext.true_original_deadline if approved_ext else act.date_deadline
            delay = (today - true_original).days if true_original else 0
            extension_days = (act.date_deadline - true_original).days if (act.date_deadline and true_original) else 0
            history_vals.append({
                'user_id': act.user_id.id,
                'res_model': act.res_model,
                'res_id': act.res_id,
                'res_name': act.res_name or '',
                'activity_type_id': act.activity_type_id.id,
                'summary': self._get_display_summary(act),
                'original_deadline': true_original,
                'completion_date': today,
                'delay_days': delay,
                'feedback': feedback or '',
                'had_extension': bool(approved_ext),
                'extension_days': extension_days if approved_ext else 0,
                'extension_reason': approved_ext.reason if approved_ext else '',
            })
            counted_activities |= act
        if history_vals:
            created_history = self.env['activity.pulse.history'].sudo().create(history_vals)
            # اگه سازنده‌ی اکتیویتی با کاربر مسئولش فرق داشته باشه، یک بررسی
            # کیفیتِ غیرمسدودکننده برای سازنده می‌سازیم. خودِ انجام‌شدن هیچ‌وقت
            # معطل این بررسی نمی‌مونه — این فقط یک لایه‌ی حسابرسیِ بعد از اتمامه.
            QualityReview = self.env['activity.pulse.quality_review'].sudo()
            for act, hist in zip(counted_activities, created_history):
                if act.create_uid and act.create_uid.id != act.user_id.id:
                    review = QualityReview.create({
                        'history_id': hist.id,
                        'performed_by': act.user_id.id,
                        'approver_id': act.create_uid.id,
                        'res_name': act.res_name or '',
                        'activity_summary': hist.summary,
                    })
                    partner = act.create_uid.partner_id
                    if partner:
                        notif_msg = self.env['mail.thread'].sudo().message_notify(
                            partner_ids=partner.ids,
                            subject='بررسی کیفیت انجام اکتیویتی',
                            body='کاربر «%s» اکتیویتی «%s» را انجام‌شده اعلام کرد. لطفاً کیفیت کار را بررسی و تأیید/رد کنید.<br/>بازخورد: %s' % (
                                act.user_id.name or '', review.activity_summary, feedback or '(بدون توضیح)',
                            ),
                        )
                        review.notification_message_id = notif_msg.id
        return super(MailActivity, self.sudo().with_context(activity_pulse_skip_cancel_log=True)).action_feedback(*args, **kwargs)

    def action_done_with_feedback_dashboard(self, feedback=''):
        """
        معادل دکمه Done بومی اودو، همراه با ثبت اجباری بازخورد/کامنت.
        فقط خودِ کاربر مسئول یا مدیر می‌تواند این عمل را انجام دهد (نه هر کسی).
        اکتیویتی همیشه فوراً «انجام‌شده» ثبت می‌شه (معطل هیچ تأییدی نمی‌مونه)؛
        بررسی کیفیت (در صورت نیاز) به‌صورت جدا و بعد از انجام، در پس‌زمینه اتفاق
        می‌افته — به جزئیاتش داخل action_feedback نگاه کنید.
        """
        self.ensure_one()
        is_manager = self.is_activity_pulse_manager()
        record = self.sudo()  # تا خواندنِ فیلدها به قانونِ دیدِ سند مبدأ گیر نکنه
        if not (is_manager or record.user_id.id == self.env.uid):
            raise AccessError('شما اجازه انجام این اکتیویتی را ندارید.')
        return record.action_feedback(feedback=feedback or '')

    def action_request_extension_dashboard(self, requested_deadline, reason):
        """
        ثبت درخواست تمدید موعد توسط کاربر مسئول. پیام به سازنده‌ی اکتیویتی
        (create_uid) ارسال می‌شه تا تأیید/رد کنه.
        """
        self.ensure_one()
        record = self.sudo()
        if record.user_id.id != self.env.uid:
            raise AccessError('فقط کاربر مسئولِ این اکتیویتی می‌تواند درخواست تمدید ثبت کند.')
        if not reason or not reason.strip():
            raise UserError('لطفاً دلیل درخواست را بنویسید.')
        if not record.create_uid:
            raise UserError('برای این اکتیویتی سازنده‌ی مشخصی ثبت نشده است.')

        ExtensionRequest = self.env['activity.pulse.extension.request'].sudo()
        true_original = ExtensionRequest._get_true_original_deadline(record)
        req = ExtensionRequest.create({
            'activity_id': record.id,
            'requested_by': self.env.uid,
            'approver_id': record.create_uid.id,
            'reason': reason.strip(),
            'previous_deadline': record.date_deadline,
            'true_original_deadline': true_original,
            'requested_deadline': requested_deadline,
            'res_name': record.res_name or '',
            'activity_summary': self._get_display_summary(record),
        })

        partner = record.create_uid.partner_id
        if partner:
            notif_msg = self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject='درخواست تمدید موعد اکتیویتی',
                body='کاربر «%s» برای اکتیویتی «%s» درخواست تمدید موعد داده است.<br/>دلیل: %s' % (
                    self.env.user.name, req.activity_summary, req.reason,
                ),
            )
            req.notification_message_id = notif_msg.id
        return True

    def get_activity_pulse_team_summary(self):
        """
        فقط برای مدیران: خلاصه‌ی هر کارمند (تعداد قرمز/زرد/سبز) برای نمایش باکس‌ها.
        همه‌ی کاربران فعال نشون داده می‌شن (حتی اونایی که هیچ اکتیویتی بازی ندارن)،
        و اطلاعات دسته‌بندی هرکدوم هم برمی‌گرده تا بشه فیلتر/گروه‌بندی کرد.
        کارمندانی که تاخیر بیشتری دارن اول لیست میان.
        """
        if not self.is_activity_pulse_manager():
            raise AccessError('فقط اعضای گروه مدیریتی به این بخش دسترسی دارند.')

        users = self.env['res.users'].sudo().search([('active', '=', True), ('share', '=', False)])
        # sudo عمدی: مدیر باید همه‌ی اکتیویتی‌های موجود رو ببینه، حتی اونایی که خودش
        # دنبال‌کننده/محول‌کننده‌ی رکورد مبدأشون نیست.
        activities = self.sudo().search([('user_id', 'in', users.ids)] + self._get_excluded_domain())

        counts = {u.id: {'red': 0, 'yellow': 0, 'green': 0} for u in users}
        for act in activities:
            color = STATE_COLOR_MAP.get(act.state, 'green')
            counts[act.user_id.id][color] += 1

        Category = self.env['activity.pulse.category'].sudo()
        categories = Category.search([], order='sequence, name')
        user_category_map = {}
        for cat in categories:
            for u in cat.user_ids:
                user_category_map.setdefault(u.id, []).append(cat.id)

        result = []
        for u in users:
            c = counts[u.id]
            result.append({
                'user_id': u.id,
                'user_name': u.name,
                'red': c['red'],
                'yellow': c['yellow'],
                'green': c['green'],
                'total': c['red'] + c['yellow'] + c['green'],
                'category_ids': user_category_map.get(u.id, []),
            })
        result.sort(key=lambda r: (-r['red'], -r['yellow'], r['user_name']))

        return {
            'members': result,
            'categories': [{'id': cat.id, 'name': cat.name} for cat in categories],
        }

    def action_update_deadline_dashboard(self, new_deadline):
        """
        ویرایش سریع موعد اکتیویتی از داخل پنل.
        عمداً محدود به «سازنده اکتیویتی» یا «مدیر» است — کاربر مسئولِ اکتیویتی
        (کسی که کار براش تعریف شده) نباید بتونه موعد خودش رو جابه‌جا کنه، تا این
        قابلیت برای فرار از وضعیت «تاخیر» سوءاستفاده نشه.
        """
        self.ensure_one()
        is_manager = self.is_activity_pulse_manager()
        record = self.sudo()  # تا خواندنِ create_uid به قانونِ دیدِ سند مبدأ گیر نکنه
        if not (is_manager or record.create_uid.id == self.env.uid):
            raise AccessError('فقط سازنده این اکتیویتی یا مدیر می‌تواند موعد آن را ویرایش کند.')
        record.write({'date_deadline': new_deadline})
        today = fields.Date.context_today(self)
        return self._format_activity(record, today)

    def action_follow_up_dashboard(self):
        """ارسال پیام پیگیری به کاربر مسئول از طریق Discuss (فقط مدیران)."""
        self.ensure_one()
        if not self.is_activity_pulse_manager():
            raise AccessError('فقط مدیران می‌توانند پیگیری ارسال کنند.')
        record = self.sudo()
        partner = record.user_id.partner_id
        if not partner:
            return False
        subject = 'پیگیری اکتیویتی: %s' % (record.res_name or record.activity_type_id.name or '')
        body = (
            'سلام %s،<br/>لطفاً وضعیت اکتیویتی «%s» مربوط به «%s» را که موعدش '
            'رسیده یا گذشته گزارش دهید.'
        ) % (
            record.user_id.name or '',
            self._get_display_summary(record),
            record.res_name or '',
        )
        self.env['mail.thread'].sudo().message_notify(
            partner_ids=partner.ids,
            subject=subject,
            body=body,
        )
        return True

    def action_send_sms_dashboard(self):
        """
        ارسال پیامک یادآوری به کاربر مسئول از طریق سرویس Lookup کاوه‌نگار (فقط مدیران).
        خروجی: {'success': bool, 'error': str|None} تا فرانت بتونه پیام مناسب نشون بده.
        """
        self.ensure_one()
        if not self.is_activity_pulse_manager():
            raise AccessError('فقط مدیران می‌توانند پیامک ارسال کنند.')
        record = self.sudo()

        partner = record.user_id.partner_id
        phone = partner.mobile or partner.phone
        if not phone:
            return {'success': False, 'error': 'برای کاربر «%s» شماره موبایلی ثبت نشده است.' % (record.user_id.name or '')}

        icp = self.env['ir.config_parameter'].sudo()
        api_key = icp.get_param('activity_pulse.kavenegar_api_key', '')
        template = icp.get_param('activity_pulse.kavenegar_template', 'odooactivty')

        tokens = {
            'token10': record.user_id.name or '',
            'token20': record.res_name or record.activity_type_id.name or '',
            'token': format_jalali_slash(record.date_deadline) if record.date_deadline else '',
        }
        result = send_kavenegar_lookup(api_key, phone, template, tokens)
        return {'success': result['success'], 'error': result['error']}
