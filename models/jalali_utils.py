# -*- coding: utf-8 -*-
"""
توابع تبدیل تقویم شمسی/میلادی، مشترک بین همه فایل‌های ماژول.
الگوریتم‌ها ریاضی و مستقل از هر کتابخانه بیرونی هستن (همون منطقی که پایه
کتابخانه‌های معتبری مثل jalaali-js هم هست).
"""
from datetime import date, timedelta

PERSIAN_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
]


def gregorian_to_jalali(gy, gm, gd):
    """تبدیل دقیق تاریخ میلادی به شمسی."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy2 = gy - 1600
    else:
        jy = 0
        gy2 = gy - 621
    gy2_adj = gy2 + 1 if gm > 2 else gy2
    days = (365 * gy2) + ((gy2_adj + 3) // 4) - ((gy2_adj + 99) // 100) + \
           ((gy2_adj + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    """تبدیل دقیق تاریخ شمسی به میلادی (معکوسِ تابع بالا)."""
    if jy <= 979:
        gy = 621
    else:
        gy = 1600
        jy = jy - 979
    days = (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd + \
           ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    gy += 400 * (days // 146097)
    days %= 146097
    leap = True
    if days >= 36525:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
        else:
            leap = False
    gy += 4 * (days // 1461)
    days %= 1461
    if days >= 366:
        leap = False
        days -= 1
        gy += days // 365
        days %= 365
    gd = days + 1
    sal_a = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for gm in range(1, 13):
        v = sal_a[gm]
        if gd <= v:
            break
        gd -= v
    return gy, gm, gd


PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'


def to_persian_digits(value):
    """تبدیل اعداد لاتین به فارسی — رفع مشکل جهتِ متن‌های ترکیبی عدد+فارسی."""
    return str(value).translate(str.maketrans('0123456789', PERSIAN_DIGITS))


def format_jalali(gdate):
    """فرمت خوانا مثل «۲۳ مهر ۱۴۰۴» از یک تاریخ میلادی (با اعداد فارسی)."""
    if not gdate:
        return ''
    jy, jm, jd = gregorian_to_jalali(gdate.year, gdate.month, gdate.day)
    return to_persian_digits('%d %s %d' % (jd, PERSIAN_MONTHS[jm - 1], jy))


def format_jalali_slash(gdate):
    """
    فرمت فشرده و بدون فاصله مثل «1404/04/26» — مخصوص جاهایی مثل توکن ساده‌ی
    کاوه‌نگار که فاصله/چندکلمه‌ای بودن مقدار رو قبول نمی‌کنه.
    """
    if not gdate:
        return ''
    jy, jm, jd = gregorian_to_jalali(gdate.year, gdate.month, gdate.day)
    return '%04d/%02d/%02d' % (jy, jm, jd)


def today_jalali():
    """(jy, jm, jd) امروز به شمسی."""
    today = date.today()
    return gregorian_to_jalali(today.year, today.month, today.day)


def jalali_month_range(jy, jm):
    """بازه میلادیِ یک ماه شمسیِ کامل: (تاریخ شروع، تاریخ پایان)."""
    start_y, start_m, start_d = jalali_to_gregorian(jy, jm, 1)
    start = date(start_y, start_m, start_d)
    next_jy, next_jm = (jy + 1, 1) if jm == 12 else (jy, jm + 1)
    ns_y, ns_m, ns_d = jalali_to_gregorian(next_jy, next_jm, 1)
    end = date(ns_y, ns_m, ns_d) - timedelta(days=1)
    return start, end


def jalali_year_range(jy):
    """بازه میلادیِ یک سال شمسیِ کامل."""
    start_y, start_m, start_d = jalali_to_gregorian(jy, 1, 1)
    start = date(start_y, start_m, start_d)
    end_y, end_m, end_d = jalali_to_gregorian(jy + 1, 1, 1)
    end = date(end_y, end_m, end_d) - timedelta(days=1)
    return start, end
