
const PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
];

const PERSIAN_WEEKDAYS = [
    "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه",
];

function toJalali(gy, gm, gd) {
    const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    let jy;
    let gy2;
    if (gy > 1600) {
        jy = 979;
        gy2 = gy - 1600;
    } else {
        jy = 0;
        gy2 = gy - 621;
    }
    const gy2Adj = gm > 2 ? gy2 + 1 : gy2;
    let days =
        365 * gy2 +
        Math.floor((gy2Adj + 3) / 4) -
        Math.floor((gy2Adj + 99) / 100) +
        Math.floor((gy2Adj + 399) / 400) -
        80 +
        gd +
        g_d_m[gm - 1];
    jy += 33 * Math.floor(days / 12053);
    days %= 12053;
    jy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
        jy += Math.floor((days - 1) / 365);
        days = (days - 1) % 365;
    }
    let jm, jd;
    if (days < 186) {
        jm = 1 + Math.floor(days / 31);
        jd = 1 + (days % 31);
    } else {
        jm = 7 + Math.floor((days - 186) / 30);
        jd = 1 + ((days - 186) % 30);
    }
    return { jy, jm, jd };
}

const PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];


export function toPersianDigits(value) {
    return String(value).replace(/[0-9]/g, (d) => PERSIAN_DIGITS[parseInt(d, 10)]);
}

export function getCurrentJalaliYearMonth() {
    const now = new Date();
    const { jy, jm } = toJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
    return { jy, jm };
}

export function toGregorian(jy, jm, jd) {
    let gy;
    if (jy <= 979) {
        gy = 621;
    } else {
        gy = 1600;
        jy = jy - 979;
    }
    let days =
        365 * jy +
        Math.floor(jy / 33) * 8 +
        Math.floor(((jy % 33) + 3) / 4) +
        78 +
        jd +
        (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
    gy += 400 * Math.floor(days / 146097);
    days %= 146097;
    let leap = true;
    if (days >= 36525) {
        days -= 1;
        gy += 100 * Math.floor(days / 36524);
        days %= 36524;
        if (days >= 365) {
            days += 1;
        } else {
            leap = false;
        }
    }
    gy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days >= 366) {
        leap = false;
        days -= 1;
        gy += Math.floor(days / 365);
        days %= 365;
    }
    let gd = days + 1;
    const salA = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gm;
    for (gm = 1; gm < 13; gm++) {
        const v = salA[gm];
        if (gd <= v) break;
        gd -= v;
    }
    return { gy, gm, gd };
}

export function gregorianStringToJalali(dateStr) {
    if (!dateStr) return null;
    const [gy, gm, gd] = dateStr.split("-").map((x) => parseInt(x, 10));
    return toJalali(gy, gm, gd);
}

export function jalaliToGregorianString(jy, jm, jd) {
    const { gy, gm, gd } = toGregorian(jy, jm, jd);
    const pad = (n) => String(n).padStart(2, "0");
    return `${gy}-${pad(gm)}-${pad(gd)}`;
}

export { PERSIAN_MONTHS };

export function formatJalaliDateTime(date) {
    const { jy, jm, jd } = toJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
    const weekday = PERSIAN_WEEKDAYS[date.getDay()];
    const dateStr = toPersianDigits(`${weekday} ${jd} ${PERSIAN_MONTHS[jm - 1]} ${jy}`);
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    const ss = String(date.getSeconds()).padStart(2, "0");
    const timeStr = `${hh}:${mm}:${ss}`;
    return { dateStr, timeStr };
}
