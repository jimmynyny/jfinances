package com.daedalustcg.jfinances.app

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.ActivityResultLauncher
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.components.PrimaryButton
import com.daedalustcg.jfinances.components.SmallButton
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.models.Item
import com.daedalustcg.jfinances.kit.models.JSON
import com.daedalustcg.jfinances.kit.models.LinkToken
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.plaid.link.OpenPlaidLink
import com.plaid.link.configuration.LinkTokenConfiguration
import com.plaid.link.result.LinkExit
import com.plaid.link.result.LinkResult
import com.plaid.link.result.LinkSuccess
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

/**
 * Plaid Link in the app (docs/30 "Link on the phones"): a link token from the
 * server (`platform: android`, so Plaid returns an OAuth bank's login to this
 * app by package name), Link over the current screen, then the exchange (a
 * new connection, through the server's duplicate guard, which may ask a
 * question first) or update-complete (a re-link, or adding accounts). The
 * phone never sees an access token. iOS's PlaidLink.swift is the twin.
 */
class LinkFlow(private val model: AppModel, private val scope: CoroutineScope) {
    /**
     * The duplicate guard's 409: nothing was exchanged, so nothing is billed,
     * until the answer is yes. `confirm` is the answer that lets it through, or
     * null when nothing does (the existing connection is the way in).
     */
    class Question(val code: String, val message: String, val confirm: String?, val publicToken: String, val metadata: JsonElement?, val sessionId: String) {
        val title: String
            get() = when (code) {
                "link.overlap" -> "Some of these are already connected"
                "link.same_institution" -> "Another login at this bank?"
                else -> "Already connected"
            }
        val yes: String get() = if (confirm == "overlap") "Connect anyway" else "Yes, connect it"
    }

    /** Fetching a token, or finishing after Link: the button spins. */
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
    var question by mutableStateOf<Question?>(null)
    private var pending: LinkToken? = null

    fun start(launcher: ActivityResultLauncher<LinkTokenConfiguration>, token: suspend () -> LinkToken) {
        scope.launch {
            busy = true
            error = null
            try {
                val t = token()
                pending = t
                launcher.launch(LinkTokenConfiguration.Builder().token(t.link_token).build())
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                model.handle(e)
                error = e.description
            } catch (e: Exception) {
                error = "Couldn't open the bank's window. ${e.message ?: ""}".trim()
            } finally {
                busy = false
            }
        }
    }

    fun result(r: LinkResult, onDone: (String) -> Unit) {
        when (r) {
            is LinkSuccess -> succeeded(r, onDone)
            is LinkExit -> {
                pending = null
                r.error?.let { error = it.displayMessage ?: it.errorMessage }
            }
        }
    }

    private fun succeeded(s: LinkSuccess, onDone: (String) -> Unit) {
        val t = pending ?: return
        pending = null
        scope.launch {
            busy = true
            try {
                if (t.mode == "update") {
                    val item = ApiClient.linkUpdateComplete(t.link_session_id)
                    model.changed()
                    onDone("${item.name} updated; sync queued")
                } else {
                    val metadata = runCatching { JSON.parseToJsonElement(s.metadata.metadataJson) }.getOrNull()
                    exchange(s.publicToken, metadata, t.link_session_id, null, onDone)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                model.handle(e)
                error = e.description
            } finally {
                busy = false
            }
        }
    }

    /** The exchange, or the guard's question. A public token lasts 30 minutes. */
    private suspend fun exchange(publicToken: String, metadata: JsonElement?, sessionId: String, confirm: String?, onDone: (String) -> Unit) {
        try {
            val item = ApiClient.linkExchange(publicToken, metadata, sessionId, confirm)
            model.changed()
            onDone("Connected ${item.name}; first sync queued")
        } catch (e: ApiError.LinkGuard) {
            question = Question(e.code, e.serverMessage, e.confirm, publicToken, metadata, sessionId)
        }
    }

    /** Yes to the guard's question: exchange with the answer it named. */
    fun answer(q: Question, onDone: (String) -> Unit) {
        question = null
        val confirm = q.confirm ?: return
        scope.launch {
            busy = true
            try {
                exchange(q.publicToken, q.metadata, q.sessionId, confirm, onDone)
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                model.handle(e)
                error = e.description
            } finally {
                busy = false
            }
        }
    }
}

/** The guard's question and the error, beside a Link button. */
@Composable
private fun LinkFlowDialogs(flow: LinkFlow, onDone: (String) -> Unit) {
    flow.question?.let { q ->
        AlertDialog(
            onDismissRequest = { flow.question = null },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text(q.title, style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = { Text(q.message, style = JFFont.sans(14f), color = JF.ink2) },
            confirmButton = {
                if (q.confirm != null) {
                    TextButton(onClick = { flow.answer(q, onDone) }) {
                        Text(q.yes, style = JFFont.sans(15f, JFFont.Weight.Semibold), color = if (q.confirm == "overlap") JF.neg else JF.accentText)
                    }
                }
            },
            dismissButton = { TextButton(onClick = { flow.question = null }) { Text("Cancel", style = JFFont.sans(15f), color = JF.ink) } },
        )
    }
    flow.error?.let { e ->
        AlertDialog(
            onDismissRequest = { flow.error = null },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text("Couldn't connect", style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = { Text(e, style = JFFont.sans(14f), color = JF.ink2) },
            confirmButton = { TextButton(onClick = { flow.error = null }) { Text("OK", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.accentText) } },
        )
    }
}

/** "Connect a bank": asks what kind (the product plan, docs/30 "Products"), then Link. */
@Composable
fun ConnectBankButton(onLinked: (String) -> Unit, modifier: Modifier = Modifier) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    val flow = remember { LinkFlow(model, scope) }
    val done by rememberUpdatedState(onLinked)
    val launcher = rememberLauncherForActivityResult(OpenPlaidLink()) { flow.result(it) { done(it) } }
    var choosing by remember { mutableStateOf(false) }
    PrimaryButton(if (flow.busy) "Opening…" else "Connect a bank", { choosing = true }, modifier, enabled = !flow.busy, working = flow.busy)
    if (choosing) {
        AlertDialog(
            onDismissRequest = { choosing = false },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text("What are you connecting?", style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = {
                Text(
                    "Checking, savings, credit cards, mortgages and loans (brokerage accounts at the same bank come along if you select them); or brokerage, 401(k), IRA and 529 accounts.",
                    style = JFFont.sans(14f), color = JF.ink2,
                )
            },
            confirmButton = {
                TextButton(onClick = { choosing = false; flow.start(launcher) { ApiClient.linkToken("banking") } }) {
                    Text("Bank, card or loan", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.accentText)
                }
            },
            dismissButton = {
                TextButton(onClick = { choosing = false; flow.start(launcher) { ApiClient.linkToken("investments") } }) {
                    Text("Investment or retirement", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.accentText)
                }
            },
        )
    }
    LinkFlowDialogs(flow, onLinked)
}

/**
 * "Re-link" (a broken login, expiring consent) or "Add accounts" (a healthy
 * connection): Link in update mode. Same connection, nothing new billed.
 */
@Composable
fun RelinkButton(item: Item, onDone: (String) -> Unit) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    val flow = remember(item.id) { LinkFlow(model, scope) }
    val done by rememberUpdatedState(onDone)
    val launcher = rememberLauncherForActivityResult(OpenPlaidLink()) { flow.result(it) { done(it) } }
    SmallButton(
        if (flow.busy) "Opening…" else if (item.needsRelink) "Re-link" else "Add accounts",
        { flow.start(launcher) { ApiClient.relinkToken(item.id) } },
        primary = item.needsRelink || item.new_accounts_at != null,
        enabled = !flow.busy,
    )
    LinkFlowDialogs(flow, onDone)
}
