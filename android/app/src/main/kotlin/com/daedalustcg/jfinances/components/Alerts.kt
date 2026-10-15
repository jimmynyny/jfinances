package com.daedalustcg.jfinances.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.AppTab
import com.daedalustcg.jfinances.app.InsightsSection
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.models.MoneyAlert
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.Rule
import kotlinx.coroutines.launch

/**
 * Alerts, each dismissable with a tap, or all at once (Insights → Subscriptions
 * and the Overview). `limit`: how many to show (the Overview shows five), or
 * every one.
 */
@Composable
fun AlertsPanel(limit: Int?) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var dismissing by remember { mutableStateOf(false) }
    Loader(height = 120.dp, load = { ApiClient.alerts() }) { list ->
        Panel("alerts", flush = true, actions = {
            if (list.isNotEmpty()) {
                LinkText(if (dismissing) "Dismissing…" else "Dismiss all", {
                    scope.launch {
                        dismissing = true
                        try {
                            val n = ApiClient.dismissAllAlerts()
                            model.changed()
                            model.toast("Dismissed $n")
                        } catch (e: ApiError) {
                            model.handle(e)
                            model.toast(e.description)
                        } finally {
                            dismissing = false
                        }
                    }
                }, enabled = !dismissing)
            }
        }) {
            if (list.isEmpty()) Fine(if (limit == null) "No alerts in the last 60 days." else "No alerts.", Modifier.padding(16.dp))
            val shown = if (limit != null) list.take(limit) else list
            shown.forEachIndexed { i, a ->
                AlertMenuRow(a)
                if (i < shown.size - 1) Rule(Modifier.padding(start = 16.dp))
            }
            if (limit != null && list.size > limit) {
                LinkText("All ${list.size} alerts", {
                    model.insightsSection = InsightsSection.Subscriptions
                    model.select(AppTab.Insights)
                }, Modifier.padding(16.dp))
            }
        }
    }
}

/** An alert row that opens a menu with Dismiss. */
@Composable
private fun AlertMenuRow(alert: MoneyAlert) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth().clickable { open = true }.padding(horizontal = 16.dp)) {
        AlertRow(alert)
        DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = JF.panel, shape = RoundedCornerShape(8.dp)) {
            DropdownMenuItem(
                text = { Text("Dismiss", style = JFFont.sans(15f), color = JF.ink) },
                onClick = {
                    open = false
                    scope.launch {
                        try {
                            ApiClient.dismissAlert(alert.key)
                            model.changed()
                        } catch (e: ApiError) {
                            model.handle(e)
                            model.toast(e.description)
                        }
                    }
                },
            )
        }
    }
}
