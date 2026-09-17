# -*- coding: utf-8 -*-
import logging
import requests

_logger = logging.getLogger(__name__)

KAVENEGAR_LOOKUP_URL = 'https://api.kavenegar.com/v1/%s/verify/lookup.json'


def normalize_kavenegar_phone(number):
    """
    شماره را به فرمت بین‌المللی موردنیاز کاوه‌نگار تبدیل می‌کند:
    ۰۹۱۲۱۲۳۴۵۶۷ → ۹۸۹۱۲۱۲۳۴۵۶۷
    (پورت مستقیم از تابع normalize_kavenegar_phone در پروژه PHP شما)
    """
    number = str(number or '').strip().replace(' ', '').replace('-', '')
    if number.startswith('+98'):
        number = '98' + number[3:]
    elif number.startswith('0'):
        number = '98' + number[1:]
    elif not number.startswith('98'):
        number = '98' + number
    return number


def send_kavenegar_lookup(api_key, receptor, template, tokens=None):
    """
    ارسال پیامک با سرویس Lookup کاوه‌نگار (الگوی از پیش تأییدشده).
    (پورت مستقیم از تابع send_kavenegar_lookup در پروژه PHP شما)

    :param api_key: کلید API (از تنظیمات اودو خوانده می‌شود)
    :param receptor: شماره موبایل گیرنده
    :param template: نام الگوی از پیش تأییدشده در پنل کاوه‌نگار
    :param tokens: دیکشنری مثل {'token': 'نام', 'token2': '...', 'token3': '...'}
    :return: dict {'success': bool, 'error': str|None, 'raw': dict|None}
    """
    tokens = tokens or {}

    if not api_key or 'XXXX' in api_key:
        return {
            'success': False,
            'error': 'کلید API کاوه‌نگار هنوز در تنظیمات اودو وارد نشده است.',
            'raw': None,
        }

    phone = normalize_kavenegar_phone(receptor)
    if not phone.isdigit() or len(phone) != 12:
        return {'success': False, 'error': 'شماره موبایل نامعتبر است: %s' % receptor, 'raw': None}

    url = KAVENEGAR_LOOKUP_URL % api_key
    params = {'receptor': phone, 'template': template}
    params.update(tokens)

    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
    except requests.RequestException as exc:
        _logger.warning('Kavenegar connection error: %s', exc)
        return {'success': False, 'error': 'خطای اتصال به کاوه‌نگار: %s' % exc, 'raw': None}
    except ValueError:
        return {'success': False, 'error': 'پاسخ نامعتبر از سرویس کاوه‌نگار', 'raw': None}

    status = (data.get('return') or {}).get('status')
    if status == 200:
        return {'success': True, 'error': None, 'raw': data}

    message = (data.get('return') or {}).get('message', 'خطای نامشخص از سرویس پیامک کاوه‌نگار')
    status_text = ' (کد وضعیت: %s)' % status if status is not None else ''
    return {'success': False, 'error': message + status_text, 'raw': data}
