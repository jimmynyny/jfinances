package com.daedalustcg.jfinances.screens.edit

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.components.ChoiceField
import com.daedalustcg.jfinances.components.Field
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.FormSheet
import com.daedalustcg.jfinances.components.MenuField
import com.daedalustcg.jfinances.components.MenuItem
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.JSONBody
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.Panel
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

private fun words(c: String) = c.lowercase().replace('_', ' ').trim()

/**
 * One transaction's category, note and whether it counts as business, as the
 * dashboard's transaction drawer edits them (PATCH /transactions/{id}). A new
 * category typed here is kept in the bank's style (HOME_REPAIRS) and one that
 * reads like an existing one is that one, so names never split.
 */
@Composable
fun TxnEditSheet(tx: Txn, onDismiss: () -> Unit, onSaved: (Txn) -> Unit) {
    var categories by remember { mutableStateOf<List<String>>(emptyList()) }
    /** The chosen category key; "" is the bank's own. */
    var pick by remember { mutableStateOf(tx.user_category ?: "") }
    var typed by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf(tx.notes ?: "") }
    /** account | business | personal */
    var business by remember { mutableStateOf(if (tx.business == true) "business" else if (tx.business == false) "personal" else "account") }
    LaunchedEffect(Unit) { categories = runCatching { ApiClient.categories() }.getOrDefault(emptyList()) }

    /** The category to send (null keeps the bank's), and whether it is new. */
    fun resolved(): Pair<String?, Boolean> {
        val t = typed.trim().replace(Regex("\\s+"), " ")
        if (t.isNotEmpty()) {
            categories.firstOrNull { words(it) == words(t) }?.let { return it to false }
            return t.uppercase().replace(' ', '_') to true
        }
        return (if (pick.isEmpty()) null else pick) to false
    }

    val bankLabel = "the bank's (${Category.label(tx.category_primary)})"
    val current = when {
        typed.isNotBlank() -> "new: ${words(typed)}"
        pick.isEmpty() -> bankLabel
        else -> Category.label(pick)
    }
    val options = buildList {
        add(MenuItem(bankLabel, { pick = ""; typed = "" }))
        val seen = HashSet<String>()
        categories.sortedBy { words(it) }.filter { seen.add(words(it)) }.forEach { c -> add(MenuItem(Category.label(c), { pick = c; typed = "" })) }
    }
    val (resolvedKey, isNew) = resolved()

    FormSheet(title = tx.title, onDismiss = onDismiss, save = {
        val body = JSONBody()
        val (cat, _) = resolved()
        if (cat != tx.user_category) body["user_category"] = if (cat == null) JsonNull else JsonPrimitive(cat)
        val note = notes.trim()
        if (note != (tx.notes ?: "")) body["notes"] = JSONBody.text(note)
        val flag: Boolean? = when (business) { "business" -> true; "personal" -> false; else -> null }
        if (flag != tx.business) body["business"] = JSONBody.flag(flag)
        if (!body.isEmpty) onSaved(ApiClient.patchTransaction(tx.id, body))
    }) {
        Panel("category") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                MenuField("category", current, options)
                Field(
                    "or a new category", typed, { typed = it }, placeholder = "e.g. home repairs",
                    help = when {
                        typed.isBlank() -> null
                        isNew -> "Adds “${words(typed)}” as a new category."
                        else -> "“${Category.label(resolvedKey)}” is already a category; it will be used."
                    },
                )
                Fine("Filing this teaches a rule: new transactions from ${tx.title} on this account take the same category.")
            }
        }
        Panel("note") {
            Field("note", notes, { notes = it }, placeholder = "Anything worth remembering")
        }
        Panel("use") {
            val accountSays = if (tx.is_business == true && tx.business == null) "business" else if (tx.business == null) "personal" else "as it is"
            ChoiceField(
                "business or personal",
                listOf("account" to "account's ($accountSays)", "business" to "business", "personal" to "personal"),
                business,
                { business = it },
                help = "Business is kept out of personal Insights. \"Account's\" follows the account's own setting.",
            )
        }
    }
}
