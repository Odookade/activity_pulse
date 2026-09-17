import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import {
    PERSIAN_MONTHS,
    gregorianStringToJalali,
    jalaliToGregorianString,
    getCurrentJalaliYearMonth,
} from "./jalali_date_utils";


export class JalaliDateInput extends Component {
    static template = "activity_pulse.JalaliDateInput";
    static props = ["value", "onChange"];

    setup() {
        this.state = useState(this._buildStateFromProps());
        onWillUpdateProps((nextProps) => {
            if (nextProps.value !== this.props.value) {
                Object.assign(this.state, this._buildStateFromValue(nextProps.value));
            }
        });
    }

    _buildStateFromProps() {
        return this._buildStateFromValue(this.props.value);
    }

    _buildStateFromValue(value) {
        const parsed = value ? gregorianStringToJalali(value) : null;
        if (parsed) {
            return { jy: parsed.jy, jm: parsed.jm, jd: parsed.jd };
        }
        const { jy, jm } = getCurrentJalaliYearMonth();
        return { jy, jm, jd: 1 };
    }

    get years() {
        const { jy } = getCurrentJalaliYearMonth();
        const years = [];
        for (let y = jy - 3; y <= jy + 3; y++) years.push(y);
        return years;
    }

    get months() {
        return PERSIAN_MONTHS;
    }

    get days() {
        const days = [];
        for (let d = 1; d <= 31; d++) days.push(d);
        return days;
    }

    onPartChange() {
        const newValue = jalaliToGregorianString(this.state.jy, this.state.jm, this.state.jd);
        this.props.onChange(newValue);
    }

    onDayChange(ev) {
        this.state.jd = parseInt(ev.target.value, 10);
        this.onPartChange();
    }

    onMonthChange(ev) {
        this.state.jm = parseInt(ev.target.value, 10);
        this.onPartChange();
    }

    onYearChange(ev) {
        this.state.jy = parseInt(ev.target.value, 10);
        this.onPartChange();
    }
}
