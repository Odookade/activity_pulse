# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class ActivityPulseStoreItem(models.Model):
    """آیتم‌های قابل‌خرید با سکه‌ی سازمانی. فقط مدیران می‌سازن/ویرایش می‌کنن."""
    _name = 'activity.pulse.store.item'
    _description = 'آیتم فروشگاه پایش اکتیویتی'
    _order = 'sequence, id'

    name = fields.Char(string='نام آیتم', required=True)
    description = fields.Text(string='توضیحات')
    price = fields.Integer(string='قیمت (سکه)', required=True)
    image = fields.Image(string='تصویر', max_width=256, max_height=256)
    sequence = fields.Integer(string='ترتیب', default=10)
    active = fields.Boolean(default=True)

    def get_store_items(self):
        """لیست آیتم‌های فعال، برای نمایش توی فروشگاه پنل."""
        items = self.search([('active', '=', True)])
        return [{
            'id': i.id,
            'name': i.name,
            'description': i.description or '',
            'price': i.price,
            'has_image': bool(i.image),
        } for i in items]


class ActivityPulseStoreOrder(models.Model):
    """
    سفارش خریدِ یک کاربر. لحظه‌ی خرید، سکه‌ها بلافاصله کسر می‌شن (تا کسی
    نتونه با موجودی یکسان چندبار همون سکه رو خرج کنه)، ولی خودِ آیتم (مثلاً
    یک روز مرخصی) هنوز باید توسط یک مدیر واقعاً «تحویل داده بشه». اگر مدیر رد
    کنه، سکه‌ها به‌صورت خودکار برمی‌گردن.
    """
    _name = 'activity.pulse.store.order'
    _description = 'سفارش فروشگاه پایش اکتیویتی'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='خریدار', required=True)
    item_id = fields.Many2one('activity.pulse.store.item', string='آیتم', required=True)
    item_name = fields.Char(string='نام آیتم (اسنپ‌شات)')
    price_paid = fields.Integer(string='قیمت پرداخت‌شده')
    state = fields.Selection([
        ('pending', 'در انتظار تحویل'),
        ('fulfilled', 'تحویل‌شده'),
        ('rejected', 'ردشده (سکه برگشت داده شد)'),
    ], default='pending', string='وضعیت', required=True)
    fulfilled_by = fields.Many2one('res.users', string='تکمیل‌شده توسط')
    decision_date = fields.Datetime(string='تاریخ تصمیم')
    note = fields.Text(string='یادداشت')

    def action_purchase(self, item_id):
        """کاربر جاری یک آیتم رو با سکه می‌خره — کسر فوری موجودی."""
        item = self.env['activity.pulse.store.item'].sudo().browse(item_id)
        if not item.exists() or not item.active:
            raise UserError('این آیتم دیگر در دسترس نیست.')

        Wallet = self.env['activity.pulse.wallet.transaction'].sudo()
        summary = Wallet.get_wallet_summary(self.env.uid)
        if summary['balance'] < item.price:
            raise UserError('موجودی کیف پول شما کافی نیست.')

        order = self.sudo().create({
            'user_id': self.env.uid,
            'item_id': item.id,
            'item_name': item.name,
            'price_paid': item.price,
            'state': 'pending',
        })
        spend_tx = Wallet.create({
            'user_id': self.env.uid,
            'amount': -item.price,
            'type': 'spend',
            'state': 'approved',
            'description': 'خرید: %s' % item.name,
            'store_order_id': order.id,
        })

        # اطلاع به همه‌ی مدیران که یک سفارش جدید منتظر تحویله
        manager_group = self.env.ref('activity_pulse.group_activity_pulse_manager')
        managers = self.env['res.users'].sudo().search([
            ('groups_id', 'in', [manager_group.id]),
        ])
        partners = managers.mapped('partner_id')
        if partners:
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=partners.ids,
                subject='سفارش جدید در فروشگاه پایش اکتیویتی',
                body='کاربر «%s» آیتم «%s» را خریداری کرد و در انتظار تحویل است.' % (
                    self.env.user.name, item.name,
                ),
            )
        return {'success': True, 'order_id': order.id}

    def get_my_pending_orders(self):
        """فقط مدیران: سفارش‌های در انتظار تحویل (از همه‌ی کاربران)."""
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران به این بخش دسترسی دارند.')
        orders = self.sudo().search([('state', '=', 'pending')])
        return [{
            'id': o.id,
            'user_name': o.user_id.name,
            'item_name': o.item_name,
            'price_paid': o.price_paid,
        } for o in orders]

    def get_my_orders(self):
        """
        تاریخچه‌ی سفارش‌های خرید کاربر جاری از فروشگاه، با همه‌ی وضعیت‌ها
        (در انتظار/تحویل‌شده/ردشده)، تا هرکس بتونه سفارش‌های قبلی خودش
        و نتیجه‌ی هرکدوم رو ببینه.
        """
        from .jalali_utils import format_jalali
        state_label_map = {
            'pending': 'در انتظار تحویل',
            'fulfilled': 'تحویل‌شده',
            'rejected': 'ردشده',
        }
        state_color_map = {'pending': 'yellow', 'fulfilled': 'green', 'rejected': 'red'}
        orders = self.sudo().search([('user_id', '=', self.env.uid)])
        return [{
            'id': o.id,
            'item_name': o.item_name,
            'price_paid': o.price_paid,
            'state': o.state,
            'state_label': state_label_map.get(o.state, ''),
            'color': state_color_map.get(o.state, 'yellow'),
            'note': o.note or '',
            'can_print_receipt': o.state == 'fulfilled',
            'create_date_jalali': format_jalali(fields.Date.to_date(o.create_date)) if o.create_date else '',
            'decision_date_jalali': format_jalali(fields.Date.to_date(o.decision_date)) if o.decision_date else '',
        } for o in orders]

    def action_fulfill(self):
        self.ensure_one()
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران می‌توانند سفارش را تحویل‌شده علامت بزنند.')
        if self.state != 'pending':
            raise UserError('این سفارش قبلاً نهایی شده است.')
        self.write({
            'state': 'fulfilled',
            'fulfilled_by': self.env.uid,
            'decision_date': fields.Datetime.now(),
        })
        self._notify_user('سفارش «%s» شما تحویل داده شد.' % (self.item_name or ''))
        return True

    def action_reject(self, reason=''):
        self.ensure_one()
        if not self.env.user.has_group('activity_pulse.group_activity_pulse_manager'):
            raise AccessError('فقط مدیران می‌توانند سفارش را رد کنند.')
        if self.state != 'pending':
            raise UserError('این سفارش قبلاً نهایی شده است.')
        self.write({
            'state': 'rejected',
            'fulfilled_by': self.env.uid,
            'decision_date': fields.Datetime.now(),
            'note': reason or '',
        })
        # برگشت خودکار سکه‌ها
        self.env['activity.pulse.wallet.transaction'].sudo().create({
            'user_id': self.user_id.id,
            'amount': self.price_paid,
            'type': 'refund',
            'state': 'approved',
            'description': 'برگشت وجه: %s' % (self.item_name or ''),
            'store_order_id': self.id,
        })
        self._notify_user(
            'سفارش «%s» شما رد شد و سکه‌هایتان برگشت داده شد.' % (self.item_name or '')
            + (' دلیل: %s' % reason if reason else '')
        )
        return True

    def _notify_user(self, message):
        partner = self.user_id.partner_id
        if partner:
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject='به‌روزرسانی سفارش فروشگاه',
                body=message,
            )
