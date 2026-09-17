/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { formatJalaliDateTime, toPersianDigits } from "./jalali_date_utils";

const REFRESH_INTERVAL_MS = 60 * 1000; // هر ۱ دقیقه لیست از سرور رفرش می‌شود
const CLOCK_INTERVAL_MS = 1000; // ساعت هر ثانیه تیک می‌خورد

/**
 * دیالوگ کوچک برای دریافت بازخورد/کامنت هنگام «انجام شد» کردن اکتیویتی
 */
class ActivityFeedbackDialog extends Component {
    static template = "activity_pulse.ActivityFeedbackDialog";
    static components = { Dialog };
    static props = ["activity", "onConfirm", "close"];

    setup() {
        this.state = useState({ feedback: "" });
        this.textareaRef = useRef("feedbackInput");
    }

    onConfirmClick() {
        this.props.onConfirm(this.state.feedback);
        this.props.close();
    }
}

export class ActivityDashboardWidget extends Component {
    static template = "activity_pulse.ActivityDashboardWidget";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.notification = useService("notification");

        this.state = useState({
            activities: [],
            loading: true,
            now: new Date(),
        });

        onWillStart(() => this.loadActivities());

        onMounted(() => {
            this.clockTimer = setInterval(() => {
                this.state.now = new Date();
            }, CLOCK_INTERVAL_MS);

            this.refreshTimer = setInterval(() => {
                this.loadActivities();
            }, REFRESH_INTERVAL_MS);
        });

        onWillUnmount(() => {
            clearInterval(this.clockTimer);
            clearInterval(this.refreshTimer);
        });
    }

    async loadActivities() {
        // نکته: آرگومان اول باید یک آرایه شامل «لیست شناسه‌ها» باشه (حتی خالی)
        // چون call_kw سمت سرور همیشه args[0] رو به‌عنوان ids می‌خونه.
        const activities = await this.orm.call("mail.activity", "get_my_dashboard_activities", [[]]);
        this.state.activities = activities;
        this.state.loading = false;
    }

    get jalaliNow() {
        return formatJalaliDateTime(this.state.now);
    }

    toFa(n) {
        return toPersianDigits(n);
    }

    get overdueCount() {
        return this.state.activities.filter((a) => a.color === "red").length;
    }

    get todayCount() {
        return this.state.activities.filter((a) => a.color === "yellow").length;
    }

    get plannedCount() {
        return this.state.activities.filter((a) => a.color === "green").length;
    }

    async openRecord(activity) {
        try {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: activity.res_model,
                res_id: activity.res_id,
                views: [[false, "form"]],
                target: "current",
            });
        } catch (err) {
            this.notification.add(
                "خلاصه اطلاعات این فعالیت همین‌جا در پنل موجود است.",
                { type: "warning", title: "دسترسی محدود" }
            );
        }
    }

    markDone(activity, ev) {
        // جلوگیری از باز شدن رکورد هنگام کلیک روی دکمه
        if (ev) {
            ev.stopPropagation();
        }
        this.dialogService.add(ActivityFeedbackDialog, {
            activity,
            onConfirm: async (feedback) => {
                await this.orm.call("mail.activity", "action_done_with_feedback_dashboard", [
                    [activity.id],
                    feedback,
                ]);
                this.notification.add("اکتیویتی با موفقیت انجام‌شده ثبت شد", {
                    type: "success",
                });
                await this.loadActivities();
            },
        });
    }
}
