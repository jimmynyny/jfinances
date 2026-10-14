package com.daedalustcg.jfinances.widgets

import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.datastore.preferences.core.Preferences
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.state.getAppWidgetState
import androidx.glance.appwidget.state.updateAppWidgetState
import androidx.glance.state.PreferencesGlanceStateDefinition
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.PrimaryButton
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.storage.GlanceCache
import com.daedalustcg.jfinances.kit.ui.Caption
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.JFTheme
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.Rule
import kotlinx.coroutines.launch

/**
 * A widget's options, as iOS's Edit Widget: hide amounts for a home screen
 * others can see, and, for the account widget, which account. The account
 * list comes from the last glance, so it works offline.
 */
class WidgetConfigActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val appWidgetId = intent?.extras?.getInt(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
            ?: AppWidgetManager.INVALID_APPWIDGET_ID
        setResult(RESULT_CANCELED, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }
        val provider = AppWidgetManager.getInstance(this).getAppWidgetInfo(appWidgetId)?.provider?.className
        val (title, widget) = when (provider) {
            MonthReceiver::class.java.name -> "This month" to MonthWidget()
            UpcomingReceiver::class.java.name -> "Coming up" to UpcomingWidget()
            AccountReceiver::class.java.name -> "Account" to AccountWidget()
            else -> "Net worth" to NetWorthWidget()
        }
        setContent {
            JFTheme {
                Options(appWidgetId, title, widget, pickAccount = widget is AccountWidget)
            }
        }
    }

    @Composable
    private fun Options(appWidgetId: Int, title: String, widget: GlanceAppWidget, pickAccount: Boolean) {
        val scope = rememberCoroutineScope()
        val glanceId = remember { GlanceAppWidgetManager(this).getGlanceIdBy(appWidgetId) }
        var show by remember { mutableStateOf(true) }
        var accountId by remember { mutableStateOf<String?>(null) }
        val accounts: List<Account> = remember { GlanceCache.load()?.glance?.accounts ?: emptyList() }
        LaunchedEffect(glanceId) {
            val prefs: Preferences = getAppWidgetState(this@WidgetConfigActivity, PreferencesGlanceStateDefinition, glanceId)
            show = prefs[WidgetPrefs.SHOW_AMOUNTS] ?: true
            accountId = prefs[WidgetPrefs.ACCOUNT_ID] ?: accounts.firstOrNull()?.id
        }
        Column(
            Modifier
                .fillMaxSize()
                .background(JF.page)
                .statusBarsPadding()
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(JF.gutter),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(title, style = JFFont.sans(30f, JFFont.Weight.Semibold), color = JF.ink, modifier = Modifier.padding(top = 12.dp, bottom = 4.dp))
            Panel("options") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("Show amounts", style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink)
                        Fine("Off: dots instead of figures, for a home screen others can see.")
                    }
                    Switch(
                        checked = show,
                        onCheckedChange = { show = it },
                        colors = SwitchDefaults.colors(
                            checkedTrackColor = JF.accent,
                            checkedThumbColor = JF.panel,
                            uncheckedTrackColor = JF.panel2,
                            uncheckedThumbColor = JF.ink3,
                            uncheckedBorderColor = JF.line,
                        ),
                    )
                }
            }
            if (pickAccount) {
                Panel("account", flush = true) {
                    if (accounts.isEmpty()) Fine("Open jfinances and sign in first: the accounts come from it.", Modifier.padding(16.dp))
                    accounts.forEachIndexed { i, a ->
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { accountId = a.id }
                                .padding(horizontal = 16.dp, vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            val on = a.id == accountId
                            Box(
                                Modifier
                                    .size(16.dp)
                                    .border(1.5.dp, if (on) JF.accent else JF.ink3, CircleShape)
                                    .padding(3.5.dp)
                                    .background(if (on) JF.accent else Color.Transparent, CircleShape),
                            )
                            Column(Modifier.weight(1f)) {
                                Text(a.name, style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1)
                                Text(a.subtitle, style = JFFont.mono(11f), color = JF.ink3, maxLines = 1)
                            }
                        }
                        if (i < accounts.size - 1) Rule(Modifier.padding(start = 16.dp))
                    }
                }
            }
            Caption("tap the widget to open jfinances")
            PrimaryButton("Done", onClick = {
                scope.launch {
                    updateAppWidgetState(this@WidgetConfigActivity, glanceId) { prefs ->
                        prefs[WidgetPrefs.SHOW_AMOUNTS] = show
                        accountId?.let { prefs[WidgetPrefs.ACCOUNT_ID] = it }
                    }
                    widget.update(this@WidgetConfigActivity, glanceId)
                    setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
                    finish()
                }
            })
        }
    }
}
