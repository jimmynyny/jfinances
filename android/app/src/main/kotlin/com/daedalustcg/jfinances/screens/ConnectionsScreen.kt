package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.ConnectBankButton
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.RelinkButton
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.Loader
import com.daedalustcg.jfinances.components.QuietButton
import com.daedalustcg.jfinances.components.RuledList
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.SmallButton
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.models.Item
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.BadgeTone
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.screens.edit.AddOfflineSheet
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * The household's bank connections, as the dashboard's Settings → connections:
 * each with its status and last sync; sync one or all now, connect a new bank,
 * re-link or add accounts to one, unlink one. Offline accounts are added here
 * too. Connecting runs Plaid Link in the app (docs/30 "Link on the phones").
 */
@Composable
fun ConnectionsScreen(onBack: () -> Unit) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<String?>(null) }
    var removing by remember { mutableStateOf<Item?>(null) }
    var adding by remember { mutableStateOf(false) }

    fun run(key: String, work: suspend () -> String) {
        scope.launch {
            busy = key
            try {
                model.toast(work())
                model.changed()
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                model.handle(e)
                model.toast(e.description)
            } catch (e: Exception) {
                model.toast(e.message ?: "Something went wrong.")
            } finally {
                busy = null
            }
        }
    }

    Screen("Connections", inline = true, onBack = onBack) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            QuietButton(if (busy == "sync") "Queuing…" else "Sync everything", {
                if (busy == null) run("sync") { ApiClient.syncAll(); "Sync queued for every connection" }
            }, Modifier.weight(1f))
            QuietButton(if (busy == "prices") "Refreshing…" else "Refresh prices", {
                if (busy == null) run("prices") { if (ApiClient.refreshPrices()) "Market prices refreshing" else "Prices already refreshing" }
            }, Modifier.weight(1f))
        }
        ConnectBankButton(onLinked = { model.toast(it) })
        Loader(height = 240.dp, load = { ApiClient.items() }) { items ->
            val live = items.filter { it.status != "removed" }
            Panel("connections", flush = true, actions = { Fine("${live.size} linked") }) {
                if (live.isEmpty()) Fine("No connections yet. Connect a bank, card, loan or brokerage.", Modifier.padding(16.dp))
                RuledList(live) { item -> ConnectionRow(item, busy, onSync = {
                    run("sync-${item.id}") { if (ApiClient.syncItem(item.id)) "Sync queued" else "Sync already queued" }
                }, onUnlink = { removing = item }) }
            }
        }
        QuietButton("Add an offline account", { adding = true })
        Fine("An offline account is one no bank reports: a home, a car, cash, another asset or another debt. Its value is what you enter, or a monthly market estimate for a home or car.")
    }
    if (adding) AddOfflineSheet(onDismiss = { adding = false }, onAdded = { model.toast("Added ${it.name}") })
    removing?.let { item ->
        AlertDialog(
            onDismissRequest = { removing = null },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text("Unlink ${item.name}?", style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = {
                Text(
                    "This disconnects ${item.name} and ends its monthly connection fee. Its ${item.account_count} accounts and their history stay but stop updating. " +
                        "Connecting it again later starts a new connection, billed again; to change which accounts it covers, use Add accounts instead.",
                    style = JFFont.sans(14f), color = JF.ink2,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    removing = null
                    run("remove-${item.id}") { ApiClient.removeItem(item.id); "Unlinked ${item.name}" }
                }) { Text("Unlink", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.neg) }
            },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Keep it", style = JFFont.sans(15f), color = JF.ink) } },
        )
    }
}

private fun tone(status: String) = when (status) {
    "active" -> BadgeTone.Good
    "login_required", "pending_expiration" -> BadgeTone.Warn
    "error" -> BadgeTone.Bad
    else -> BadgeTone.Neutral
}

@Composable
private fun ConnectionRow(item: Item, busy: String?, onSync: () -> Unit, onUnlink: () -> Unit) {
    val model = LocalAppModel.current
    Column(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(item.name, style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    Fine("· ${item.account_count} account${if (item.account_count == 1) "" else "s"}")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Badge(item.statusLabel + (item.error_code?.let { " · $it" } ?: ""), tone(item.status))
                    if (item.new_accounts_at != null) Badge("new accounts available", BadgeTone.Accent)
                }
                item.error_message?.takeIf { it.isNotEmpty() }?.let { Fine(it) }
                item.transactions_status?.takeIf { it != "HISTORICAL_UPDATE_COMPLETE" }?.let {
                    Fine("history still loading (${it.lowercase().replace('_', ' ')})")
                }
                Fine("synced ${Fmt.relative(item.last_synced_at)} · ${item.products.joinToString(", ")}")
            }
            if (busy == "sync-${item.id}" || busy == "remove-${item.id}") {
                CircularProgressIndicator(Modifier.size(18.dp), color = JF.ink3, strokeWidth = 2.dp)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            SmallButton("Sync now", onSync, enabled = busy == null)
            RelinkButton(item, onDone = { model.toast(it) })
            Spacer(Modifier.weight(1f))
            SmallButton("Unlink", onUnlink, destructive = true, enabled = busy == null)
        }
    }
}
