
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Dialog } from "@web/core/dialog/dialog";
import { formatJalaliDateTime, getCurrentJalaliYearMonth, PERSIAN_MONTHS } from "./jalali_date_utils";
import { JalaliDateInput } from "./jalali_date_input";

class ActivityFeedbackDialog extends Component {
    static template = "activity_pulse.PanelFeedbackDialog";
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

class ExtensionRequestDialog extends Component {
    static template = "activity_pulse.ExtensionRequestDialog";
    static components = { Dialog, JalaliDateInput };
    static props = ["activity", "onConfirm", "close"];

    setup() {
        this.state = useState({ newDate: this.props.activity.date_deadline || "", reason: "" });
    }

    onDateChange(newDate) {
        this.state.newDate = newDate;
    }

    onConfirmClick() {
        if (!this.state.newDate || !this.state.reason.trim()) {
            return;
        }
        this.props.onConfirm(this.state.newDate, this.state.reason.trim());
        this.props.close();
    }
}

class RejectRequestDialog extends Component {
    static template = "activity_pulse.RejectRequestDialog";
    static components = { Dialog };
    static props = ["request", "onConfirm", "close"];

    setup() {
        this.state = useState({ note: "" });
    }

    onConfirmClick() {
        this.props.onConfirm(this.state.note.trim());
        this.props.close();
    }
}

class RejectQualityDialog extends Component {
    static template = "activity_pulse.RejectQualityDialog";
    static components = { Dialog, JalaliDateInput };
    static props = ["review", "onConfirm", "close"];

    setup() {
        this.state = useState({ newDeadline: "", reason: "" });
    }

    onDateChange(newDate) {
        this.state.newDeadline = newDate;
    }

    onConfirmClick() {
        if (!this.state.reason.trim() || !this.state.newDeadline) {
            return;
        }
        this.props.onConfirm(this.state.reason.trim(), this.state.newDeadline);
        this.props.close();
    }
}

class ApproveRewardDialog extends Component {
    static template = "activity_pulse.ApproveRewardDialog";
    static components = { Dialog };
    static props = ["reward", "currencyIcon", "currencyName", "onConfirm", "close"];

    setup() {
        this.state = useState({ amount: this.props.reward.amount });
    }

    onConfirmClick() {
        if (!this.state.amount || this.state.amount <= 0) {
            return;
        }
        this.props.onConfirm(parseInt(this.state.amount, 10));
        this.props.close();
    }
}

class ManualDepositDialog extends Component {
    static template = "activity_pulse.ManualDepositDialog";
    static components = { Dialog };
    static props = ["users", "currencyName", "currencyIcon", "onConfirm", "close"];

    setup() {
        this.state = useState({
            userId: this.props.users.length ? this.props.users[0].id : false,
            amount: 100,
            description: "",
        });
    }

    onDepositUserChange(ev) {
        this.state.userId = parseInt(ev.target.value, 10);
    }

    onConfirmClick() {
        if (!this.state.userId || !this.state.amount || this.state.amount <= 0) {
            return;
        }
        this.props.onConfirm(this.state.userId, parseInt(this.state.amount, 10), this.state.description.trim());
        this.props.close();
    }
}

class SimpleReasonDialog extends Component {
    static template = "activity_pulse.SimpleReasonDialog";
    static components = { Dialog };
    static props = ["title", "message", "onConfirm", "close"];

    setup() {
        this.state = useState({ reason: "" });
    }

    onConfirmClick() {
        this.props.onConfirm(this.state.reason.trim());
        this.props.close();
    }
}

export class ActivityPulsePanel extends Component {
    static template = "activity_pulse.Panel";
    static components = { Dialog, JalaliDateInput };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.notification = useService("notification");

        const { jy, jm } = getCurrentJalaliYearMonth();

        this.state = useState({
            loading: true,
            isManager: false,
            view: "grid", 
            team: [],
            teamCategories: [],
            categoryFilter: 'all', 
            teamSearchQuery: '',
            selectedUser: null, 
            activities: [],
            detailLoading: false,
            historyData: { history: [], average_delay_days: 0, count: 0 },
            historyLoading: false,
            cancelledData: [],
            cancelledLoading: false,
            kpi: null,
            kpiLoading: false,
            kpiPeriodType: "month", 
            kpiYear: jy,
            kpiMonth: jm,
            pendingApprovalsCount: 0,
            pendingApprovals: [],
            approvalsLoading: false,
            pendingQualityCount: 0,
            pendingQualityReviews: [],
            qualityLoading: false,
            wallet: null, 
            walletLoading: false,
            pendingRewardsCount: 0,
            pendingRewards: [],
            rewardsLoading: false,
            storeItems: [],
            storeLoading: false,
            pendingOrdersCount: 0,
            pendingOrders: [],
            ordersLoading: false,
            myOrders: [],
            myOrdersLoading: false,
        });
        this.persianMonths = PERSIAN_MONTHS;
        this.currentJalaliYear = jy;

        onWillStart(() => this.init());
    }

    async init() {
        this.state.isManager = await this.orm.call("mail.activity", "is_activity_pulse_manager", [[]]);
        if (this.state.isManager) {
            await this.loadTeamSummary();
            this.state.view = "grid";
        } else {
            this.state.selectedUser = { id: user.userId, name: user.name };
            await Promise.all([this.loadUserActivities(false), this.loadKpi()]);
            this.state.view = "detail";
        }
        const tasks = [this.loadPendingApprovalsCount(), this.loadPendingQualityCount(), this.loadWallet()];
        if (this.state.isManager) {
            tasks.push(this.loadPendingRewardsCount(), this.loadPendingOrdersCount());
        }
        await Promise.all(tasks);
        this.state.loading = false;
    }

    async loadWallet() {
        this.state.walletLoading = true;
        const userId = this.state.selectedUser ? this.state.selectedUser.id : user.userId;
        this.state.wallet = await this.orm.call("activity.pulse.wallet.transaction", "get_wallet_summary", [
            [], userId,
        ]);
        this.state.walletLoading = false;
    }

    async loadPendingRewardsCount() {
        const list = await this.orm.call(
            "activity.pulse.wallet.transaction", "get_my_pending_reward_approvals", [[]]
        );
        this.state.pendingRewardsCount = list.length;
    }

    async loadPendingOrdersCount() {
        const list = await this.orm.call("activity.pulse.store.order", "get_my_pending_orders", [[]]);
        this.state.pendingOrdersCount = list.length;
    }

    async loadPendingApprovalsCount() {
        const list = await this.orm.call("activity.pulse.extension.request", "get_my_pending_requests", [[]]);
        this.state.pendingApprovalsCount = list.length;
    }

    async loadPendingQualityCount() {
        const list = await this.orm.call("activity.pulse.quality_review", "get_my_pending_reviews", [[]]);
        this.state.pendingQualityCount = list.length;
    }

    async loadTeamSummary() {
        const result = await this.orm.call("mail.activity", "get_activity_pulse_team_summary", [[]]);
        this.state.team = result.members;
        this.state.teamCategories = result.categories;
    }

    get filteredTeam() {
        let list = this.state.team;
        if (this.state.categoryFilter === "uncategorized") {
            list = list.filter((m) => !m.category_ids.length);
        } else if (this.state.categoryFilter !== "all") {
            list = list.filter((m) => m.category_ids.includes(this.state.categoryFilter));
        }
        const query = this.state.teamSearchQuery.trim().toLowerCase();
        if (query) {
            list = list.filter((m) => m.user_name.toLowerCase().includes(query));
        }
        return list;
    }

    onTeamSearchInput(ev) {
        this.state.teamSearchQuery = ev.target.value;
    }

    setCategoryFilter(catId) {
        this.state.categoryFilter = catId;
    }

    openCategoryManager() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "activity.pulse.category",
            views: [[false, "list"], [false, "form"]],
            target: "new",
        }, {
            onClose: () => this.loadTeamSummary(),
        });
    }

    async loadUserActivities(userId) {
        this.state.detailLoading = true;
        this.state.activities = await this.orm.call("mail.activity", "get_dashboard_activities", [[], userId]);
        this.state.detailLoading = false;
    }

    async loadKpi() {
        this.state.kpiLoading = true;
        this.state.kpi = await this.orm.call("activity.pulse.history", "get_user_kpi_dashboard", [
            [],
            this.state.selectedUser.id,
            this.state.kpiPeriodType,
            this.state.kpiYear,
            this.state.kpiPeriodType === "month" ? this.state.kpiMonth : false,
        ]);
        this.state.kpiLoading = false;
    }

    async onKpiPeriodTypeChange(newType) {
        this.state.kpiPeriodType = newType;
        await this.loadKpi();
    }

    async onKpiYearChange(ev) {
        this.state.kpiYear = parseInt(ev.target.value, 10);
        await this.loadKpi();
    }

    async onKpiMonthChange(ev) {
        this.state.kpiMonth = parseInt(ev.target.value, 10);
        await this.loadKpi();
    }

    get kpiYearOptions() {
        const y = this.currentJalaliYear;
        return [y, y - 1, y - 2];
    }

    async openUser(member) {
        this.state.selectedUser = { id: member.user_id, name: member.user_name };
        this.state.view = "detail";
        await Promise.all([this.loadUserActivities(member.user_id), this.loadKpi(), this.loadWallet()]);
    }

    async backToGrid() {
        this.state.view = "grid";
        await this.loadTeamSummary();
    }

    async showHistory() {
        this.state.view = "history";
        this.state.historyLoading = true;
        this.state.historyData = await this.orm.call("activity.pulse.history", "get_user_history", [
            [],
            this.state.selectedUser.id,
        ]);
        this.state.historyLoading = false;
    }

    backToDetail() {
        this.state.view = "detail";
    }

    async showCancelled() {
        this.state.view = "cancelled";
        this.state.cancelledLoading = true;
        const result = await this.orm.call("activity.pulse.cancellation", "get_user_cancellations", [
            [],
            this.state.selectedUser.id,
        ]);
        this.state.cancelledData = result;
        this.state.cancelledLoading = false;
    }

    get jalaliNow() {
        return formatJalaliDateTime(new Date());
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

    async onDeadlineChange(activity, newDate) {
        if (!newDate) {
            return;
        }
        try {
            await this.orm.call("mail.activity", "action_update_deadline_dashboard", [
                [activity.id],
                newDate,
            ]);
            this.notification.add("موعد اکتیویتی به‌روزرسانی شد", { type: "success" });
            await this.refreshCurrentView();
        } catch (err) {
            this.notification.add("خطا در به‌روزرسانی موعد", { type: "danger" });
        }
    }

    async followUp(activity, ev) {
        if (ev) ev.stopPropagation();
        try {
            await this.orm.call("mail.activity", "action_follow_up_dashboard", [[activity.id]]);
            this.notification.add("پیام پیگیری در Discuss برای کاربر ارسال شد", { type: "success" });
        } catch (err) {
            this.notification.add("ارسال پیام پیگیری ناموفق بود", { type: "danger" });
        }
    }

    async sendSms(activity, ev) {
        if (ev) ev.stopPropagation();
        try {
            const result = await this.orm.call("mail.activity", "action_send_sms_dashboard", [[activity.id]]);
            if (result.success) {
                this.notification.add("پیامک با موفقیت برای کاربر ارسال شد", { type: "success" });
            } else {
                this.notification.add(result.error || "ارسال پیامک ناموفق بود", { type: "danger" });
            }
        } catch (err) {
            this.notification.add("خطا در برقراری ارتباط با سرویس پیامک", { type: "danger" });
        }
    }

    markDone(activity, ev) {
        if (ev) ev.stopPropagation();
        this.dialogService.add(ActivityFeedbackDialog, {
            activity,
            onConfirm: async (feedback) => {
                await this.orm.call("mail.activity", "action_done_with_feedback_dashboard", [
                    [activity.id],
                    feedback,
                ]);
                this.notification.add("اکتیویتی انجام‌شده ثبت شد", { type: "success" });
                await this.refreshCurrentView();
            },
        });
    }

    _isAuxiliaryView(view) {
        return ["approvals", "quality_reviews", "rewards", "store", "store_orders", "my_orders"].includes(view);
    }

    async showApprovals() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "approvals";
        this.state.approvalsLoading = true;
        this.state.pendingApprovals = await this.orm.call(
            "activity.pulse.extension.request", "get_my_pending_requests", [[]]
        );
        this.state.approvalsLoading = false;
    }

    backFromApprovals() {
        this.state.view = this.viewBeforeApprovals || (this.state.isManager ? "grid" : "detail");
    }

    async approveRequest(req) {
        try {
            await this.orm.call("activity.pulse.extension.request", "action_approve", [[req.id]]);
            this.notification.add("درخواست تأیید و موعد به‌روزرسانی شد", { type: "success" });
            await this.showApprovals();
            await this.loadPendingApprovalsCount();
            await this.refreshCurrentView();
        } catch (err) {
            this.notification.add("خطا در تأیید درخواست", { type: "danger" });
        }
    }

    rejectRequest(req) {
        this.dialogService.add(RejectRequestDialog, {
            request: req,
            onConfirm: async (note) => {
                try {
                    await this.orm.call("activity.pulse.extension.request", "action_reject", [[req.id], note]);
                    this.notification.add("درخواست رد شد", { type: "info" });
                    await this.showApprovals();
                    await this.loadPendingApprovalsCount();
                } catch (err) {
                    this.notification.add("خطا در رد درخواست", { type: "danger" });
                }
            },
        });
    }

    async showQualityReviews() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "quality_reviews";
        this.state.qualityLoading = true;
        this.state.pendingQualityReviews = await this.orm.call(
            "activity.pulse.quality_review", "get_my_pending_reviews", [[]]
        );
        this.state.qualityLoading = false;
    }

    async approveQuality(review) {
        try {
            await this.orm.call("activity.pulse.quality_review", "action_approve", [[review.id]]);
            this.notification.add("کیفیت انجام کار تأیید شد", { type: "success" });
            await this.showQualityReviews();
            await this.loadPendingQualityCount();
        } catch (err) {
            this.notification.add("خطا در تأیید", { type: "danger" });
        }
    }

    rejectQuality(review) {
        this.dialogService.add(RejectQualityDialog, {
            review,
            onConfirm: async (reason, newDeadline) => {
                try {
                    await this.orm.call("activity.pulse.quality_review", "action_reject", [
                        [review.id], reason, newDeadline,
                    ]);
                    this.notification.add("کیفیت رد شد و اکتیویتی جدید برای انجامِ دوباره ثبت شد", { type: "info" });
                    await this.showQualityReviews();
                    await this.loadPendingQualityCount();
                    await this.refreshCurrentView();
                } catch (err) {
                    this.notification.add("خطا در ثبت رد", { type: "danger" });
                }
            },
        });
    }

    // ============ پاداش ============
    async showRewards() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "rewards";
        this.state.rewardsLoading = true;
        this.state.pendingRewards = await this.orm.call(
            "activity.pulse.wallet.transaction", "get_my_pending_reward_approvals", [[]]
        );
        this.state.rewardsLoading = false;
    }

    approveReward(reward) {
        this.dialogService.add(ApproveRewardDialog, {
            reward,
            currencyIcon: this.state.wallet ? this.state.wallet.currency_icon : "🪙",
            currencyName: this.state.wallet ? this.state.wallet.currency_name : "سکه",
            onConfirm: async (amount) => {
                try {
                    await this.orm.call("activity.pulse.wallet.transaction", "action_approve_reward", [
                        [reward.id], amount,
                    ]);
                    this.notification.add("پاداش واریز شد", { type: "success" });
                    await this.showRewards();
                    await this.loadPendingRewardsCount();
                } catch (err) {
                    this.notification.add("خطا در واریز پاداش", { type: "danger" });
                }
            },
        });
    }

    rejectReward(reward) {
        this.dialogService.add(SimpleReasonDialog, {
            title: "رد پاداش",
            message: "این پاداش واریز نمی‌شه. دلیل رو (اختیاری) بنویس:",
            onConfirm: async (reason) => {
                try {
                    await this.orm.call("activity.pulse.wallet.transaction", "action_reject_reward", [
                        [reward.id], reason,
                    ]);
                    this.notification.add("پاداش رد شد", { type: "info" });
                    await this.showRewards();
                    await this.loadPendingRewardsCount();
                } catch (err) {
                    this.notification.add("خطا در رد پاداش", { type: "danger" });
                }
            },
        });
    }

    // ============ فروشگاه ============
    async showStore() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "store";
        this.state.storeLoading = true;
        this.state.storeItems = await this.orm.call("activity.pulse.store.item", "get_store_items", [[]]);
        this.state.storeLoading = false;
    }

    async purchaseItem(item) {
        if (!this.state.wallet || this.state.wallet.balance < item.price) {
            this.notification.add("موجودی کافی نیست", { type: "warning" });
            return;
        }
        try {
            await this.orm.call("activity.pulse.store.order", "action_purchase", [[], item.id]);
            this.notification.add("خرید ثبت شد و در انتظار تکمیل توسط مدیره", { type: "success" });
            await this.loadWallet();
        } catch (err) {
            this.notification.add("خطا در ثبت خرید", { type: "danger" });
        }
    }

    async showStoreOrders() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "store_orders";
        this.state.ordersLoading = true;
        this.state.pendingOrders = await this.orm.call(
            "activity.pulse.store.order", "get_my_pending_orders", [[]]
        );
        this.state.ordersLoading = false;
    }

    async showMyOrders() {
        if (!this._isAuxiliaryView(this.state.view)) {
            this.viewBeforeApprovals = this.state.view;
        }
        this.state.view = "my_orders";
        this.state.myOrdersLoading = true;
        this.state.myOrders = await this.orm.call("activity.pulse.store.order", "get_my_orders", [[]]);
        this.state.myOrdersLoading = false;
    }

    async printReceipt(order) {
        await this.actionService.doAction("activity_pulse.action_report_store_receipt", {
            additionalContext: { active_ids: [order.id] },
        });
    }

    async openManualDeposit() {
        const users = await this.orm.call("mail.activity", "get_activity_pulse_users", [[]]);
        this.dialogService.add(ManualDepositDialog, {
            users,
            currencyName: this.state.wallet ? this.state.wallet.currency_name : "",
            currencyIcon: this.state.wallet ? this.state.wallet.currency_icon : "",
            onConfirm: async (userId, amount, description) => {
                try {
                    await this.orm.call("activity.pulse.wallet.transaction", "action_manual_deposit", [
                        [],
                        userId,
                        amount,
                        description,
                    ]);
                    this.notification.add("سکه با موفقیت واریز شد", { type: "success" });
                    if (this.state.selectedUser && this.state.selectedUser.id === userId) {
                        await this.loadWallet();
                    }
                } catch (err) {
                    this.notification.add("خطا در واریز سکه", { type: "danger" });
                }
            },
        });
    }

    async fulfillOrder(order) {
        try {
            await this.orm.call("activity.pulse.store.order", "action_fulfill", [[order.id]]);
            this.notification.add("سفارش تکمیل شد", { type: "success" });
            await this.showStoreOrders();
            await this.loadPendingOrdersCount();
        } catch (err) {
            this.notification.add("خطا در تکمیل سفارش", { type: "danger" });
        }
    }

    rejectOrder(order) {
        this.dialogService.add(SimpleReasonDialog, {
            title: "رد سفارش",
            message: "این سفارش رد می‌شه و مبلغش به کاربر برمی‌گرده. دلیل رو (اختیاری) بنویس:",
            onConfirm: async (reason) => {
                try {
                    await this.orm.call("activity.pulse.store.order", "action_reject", [[order.id], reason]);
                    this.notification.add("سفارش رد شد و مبلغ برگشت داده شد", { type: "info" });
                    await this.showStoreOrders();
                    await this.loadPendingOrdersCount();
                } catch (err) {
                    this.notification.add("خطا در رد سفارش", { type: "danger" });
                }
            },
        });
    }

    requestExtension(activity, ev) {
        if (ev) ev.stopPropagation();
        this.dialogService.add(ExtensionRequestDialog, {
            activity,
            onConfirm: async (newDate, reason) => {
                try {
                    await this.orm.call("mail.activity", "action_request_extension_dashboard", [
                        [activity.id],
                        newDate,
                        reason,
                    ]);
                    this.notification.add("درخواست تمدید برای سازنده‌ی اکتیویتی ارسال شد", { type: "success" });
                    await this.refreshCurrentView();
                } catch (err) {
                    this.notification.add("ثبت درخواست ناموفق بود", { type: "danger" });
                }
            },
        });
    }

    async refreshCurrentView() {
        if (this.state.view === "detail") {
            await Promise.all([
                this.loadUserActivities(this.state.isManager ? this.state.selectedUser.id : false),
                this.loadKpi(),
            ]);
        }
        if (this.state.isManager) {
            await this.loadTeamSummary();
        }
    }
}

registry.category("actions").add("activity_pulse.panel", ActivityPulsePanel);
