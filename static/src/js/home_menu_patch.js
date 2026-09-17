

import { patch } from "@web/core/utils/patch";
import { ActivityDashboardWidget } from "./activity_dashboard_widget";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";

patch(HomeMenu.components, { ActivityDashboardWidget });
