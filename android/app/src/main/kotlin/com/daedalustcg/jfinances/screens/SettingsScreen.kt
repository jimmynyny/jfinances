package com.daedalustcg.jfinances.screens

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import com.daedalustcg.jfinances.BuildConfig
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.QuietButton
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.kit.storage.Server
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.BadgeTone
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.Rule
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.coroutines.launch

private val linkedFormat = DateTimeFormatter.ofPattern("MMM d, yyyy 'at' h:mm a", Locale.US)

@Composable
fun SettingsScreen() {
    val model = LocalAppModel.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var confirmUnlink by remember { mutableStateOf(false) }
    Screen("Settings") {
        val cred = model.credential
        if (cred != null) {
            Panel("signed in") {
                KeyValueRow("person") { Text(model.me?.display_name ?: cred.displayName ?: cred.email) }
                KeyValueRow("email") { Text(cred.email, style = JFFont.mono(13f)) }
                KeyValueRow("server") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (cred.server == Server.SANDBOX) Badge("sandbox", BadgeTone.Warn)
                        Text(cred.server.apiHost, style = JFFont.mono(12f))
                    }
                }
                KeyValueRow("linked") {
                    Text(Instant.ofEpochMilli(cred.linkedAt).atZone(ZoneId.systemDefault()).format(linkedFormat), style = JFFont.mono(13f))
                }
            }
            Panel("privacy") {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("Blur numbers", style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink)
                            Fine("For screenshots: every figure in the app blurs.")
                        }
                        Switch(
                            checked = model.blur,
                            onCheckedChange = { model.setBlurNumbers(it) },
                            colors = SwitchDefaults.colors(
                                checkedTrackColor = JF.accent,
                                checkedThumbColor = JF.panel,
                                uncheckedTrackColor = JF.panel2,
                                uncheckedThumbColor = JF.ink3,
                                uncheckedBorderColor = JF.line,
                            ),
                        )
                    }
                    Rule()
                    Text(
                        "This phone is read-only: it can see everything on the dashboard and change nothing. It never talks to a bank.",
                        style = JFFont.sans(13f),
                        color = JF.ink2,
                    )
                }
            }
            Panel("widgets") {
                Text(
                    "Touch and hold the home screen, tap Widgets, and pick jFinances: net worth, this month, coming up, or one account. Touch and hold a widget to change what it shows.",
                    style = JFFont.sans(13f),
                    color = JF.ink2,
                )
            }
            QuietButton("Open the dashboard", {
                context.startActivity(Intent(Intent.ACTION_VIEW, cred.server.dashboard.toUri()))
            })
            QuietButton("Unlink this phone", { confirmUnlink = true }, destructive = true)
        }
        Fine("jFinances ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})", Modifier.fillMaxWidth().padding(top = 8.dp), textAlign = TextAlign.Center)
    }
    if (confirmUnlink) {
        AlertDialog(
            onDismissRequest = { confirmUnlink = false },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text("Unlink this phone?", style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = { Text("Its token is revoked and the widgets go blank. Sign in again any time.", style = JFFont.sans(14f), color = JF.ink2) },
            confirmButton = {
                TextButton(onClick = {
                    confirmUnlink = false
                    scope.launch { model.unlink() }
                }) { Text("Unlink", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.neg) }
            },
            dismissButton = {
                TextButton(onClick = { confirmUnlink = false }) { Text("Cancel", style = JFFont.sans(15f), color = JF.ink) }
            },
        )
    }
}
