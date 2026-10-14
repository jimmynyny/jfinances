package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.Route
import com.daedalustcg.jfinances.components.ErrorNote
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.LargeTitle
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.Skeleton
import com.daedalustcg.jfinances.components.TopBar
import com.daedalustcg.jfinances.components.TopBarHeight
import com.daedalustcg.jfinances.components.TxnRow
import com.daedalustcg.jfinances.components.tabBarSpace
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.api.TxnQuery
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.Readout
import com.daedalustcg.jfinances.kit.ui.Rule
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Every transaction, newest first, by day: search, filter by account or
 * category, and scroll for more.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActivityScreen() {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var search by rememberSaveable { mutableStateOf("") }
    var accountId by rememberSaveable { mutableStateOf<String?>(null) }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    val rows = remember { mutableStateListOf<Txn>() }
    var total by remember { mutableIntStateOf(0) }
    var page by remember { mutableIntStateOf(1) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var accounts by remember { mutableStateOf<List<Account>>(emptyList()) }
    var categories by remember { mutableStateOf<List<String>>(emptyList()) }
    var refreshing by remember { mutableStateOf(false) }

    suspend fun reload() {
        loading = true
        page = 1
        try {
            val r = ApiClient.transactions(TxnQuery(q = search, accountId = accountId, category = category, page = 1))
            rows.clear()
            rows.addAll(r.transactions)
            total = r.total
            error = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiError) {
            model.handle(e)
            error = e.description
        } finally {
            loading = false
        }
    }

    suspend fun more() {
        if (loading || rows.size >= total) return
        loading = true
        val next = page + 1
        try {
            val r = ApiClient.transactions(TxnQuery(q = search, accountId = accountId, category = category, page = next))
            page = next
            val seen = rows.map { it.id }.toSet()
            rows.addAll(r.transactions.filter { it.id !in seen })
            total = r.total
        } catch (e: CancellationException) {
            throw e
        } catch (_: ApiError) {
        } finally {
            loading = false
        }
    }

    LaunchedEffect(search, accountId, category, model.refreshToken) {
        if (search.isNotEmpty()) delay(300)
        reload()
    }
    LaunchedEffect(Unit) {
        accounts = runCatching { ApiClient.accounts() }.getOrNull()?.filter { it.is_hidden != true && !it.isManual } ?: emptyList()
        categories = runCatching { ApiClient.categories() }.getOrNull() ?: emptyList()
    }

    val days by remember { derivedStateOf { rows.groupBy { it.date.take(10) }.toList() } }
    val list = rememberLazyListState()
    val scrolled by remember { derivedStateOf { list.firstVisibleItemIndex > 0 || list.firstVisibleItemScrollOffset > 0 } }
    val pastTitle by remember { derivedStateOf { list.firstVisibleItemIndex > 0 || list.firstVisibleItemScrollOffset > 100 } }
    val top = WindowInsets.statusBars.asPaddingValues().calculateTopPadding() + TopBarHeight
    val pull = rememberPullToRefreshState()

    Box(Modifier.fillMaxSize().background(JF.page)) {
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = {
                scope.launch {
                    refreshing = true
                    model.pullToRefresh()
                    refreshing = false
                }
            },
            state = pull,
            modifier = Modifier.padding(top = top),
            indicator = {
                PullToRefreshDefaults.Indicator(state = pull, isRefreshing = refreshing, modifier = Modifier.align(Alignment.TopCenter), containerColor = JF.panel, color = JF.ink3)
            },
        ) {
            LazyColumn(state = list, contentPadding = PaddingValues(bottom = tabBarSpace())) {
                item(key = "title") { Box(Modifier.padding(horizontal = JF.gutter)) { LargeTitle("Activity") } }
                item(key = "search") {
                    SearchField(search, { search = it }, "Merchant, name, or note", Modifier.padding(horizontal = JF.gutter).padding(top = 12.dp, bottom = 10.dp))
                }
                item(key = "filters") {
                    Row(Modifier.padding(horizontal = JF.gutter).padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterMenu(
                            text = accounts.firstOrNull { it.id == accountId }?.name ?: "all accounts",
                            active = accountId != null,
                            options = listOf<Pair<String?, String>>(null to "All accounts") + accounts.map { a ->
                                a.id to "${a.institution_name?.let { "$it: " } ?: ""}${a.name}${a.mask?.let { " ··$it" } ?: ""}"
                            },
                            onPick = { accountId = it },
                        )
                        FilterMenu(
                            text = category?.let { Category.label(it) } ?: "all categories",
                            active = category != null,
                            options = listOf<Pair<String?, String>>(null to "All categories") + categories.map { it to Category.label(it) },
                            onPick = { category = it },
                        )
                    }
                }
                if (error != null && rows.isEmpty()) {
                    item(key = "error") { Box(Modifier.padding(horizontal = JF.gutter)) { ErrorNote(error!!) { scope.launch { reload() } } } }
                }
                for ((day, txs) in days) {
                    stickyHeader(key = "h$day") {
                        Row(
                            Modifier.fillMaxWidth().background(JF.page).padding(horizontal = JF.gutter, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(Fmt.dayHeading(day), style = JFFont.mono(12f, JFFont.Weight.Medium), color = JF.ink2, modifier = Modifier.weight(1f))
                            val out = txs.filter { it.amount > 0 }.sumOf { it.amount }
                            if (out > 0) MoneyText(out, cents = false, size = 11f)
                        }
                    }
                    item(key = "d$day") {
                        Column(
                            Modifier
                                .padding(horizontal = JF.gutter)
                                .padding(bottom = 12.dp)
                                .fillMaxWidth()
                                .background(JF.panel)
                                .border(1.dp, JF.line, RectangleShape),
                        ) {
                            txs.forEachIndexed { i, tx ->
                                Box(Modifier.fillMaxWidth().clickable { model.push(Route.TxnDetail(tx)) }.padding(horizontal = 16.dp)) {
                                    TxnRow(tx)
                                }
                                if (tx.id == rows.lastOrNull()?.id) LaunchedEffect(tx.id) { more() }
                                if (i < txs.size - 1) Rule(Modifier.padding(start = 58.dp))
                            }
                        }
                    }
                }
                if (loading && rows.isEmpty()) item(key = "skeleton") { Box(Modifier.padding(horizontal = JF.gutter)) { Skeleton(300.dp) } }
                if (!loading && rows.isEmpty() && error == null) {
                    item(key = "none") { Fine("No transactions match.", Modifier.fillMaxWidth().padding(top = 40.dp), textAlign = TextAlign.Center) }
                }
                if (loading && rows.isNotEmpty()) {
                    item(key = "more") {
                        Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(Modifier.size(20.dp), color = JF.ink3, strokeWidth = 2.dp)
                        }
                    }
                }
                if (rows.isNotEmpty() && rows.size >= total) {
                    item(key = "count") { Fine("$total transactions", Modifier.fillMaxWidth().padding(vertical = 16.dp), textAlign = TextAlign.Center) }
                }
            }
        }
        TopBar("Activity", showTitle = pastTitle, scrolled = scrolled, onBack = null)
    }
}

/** The search field under the title, as iOS's searchable drawer. */
@Composable
private fun SearchField(value: String, onChange: (String) -> Unit, prompt: String, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .height(40.dp)
            .background(JF.panel2, RoundedCornerShape(10.dp))
            .border(1.dp, JF.line, RoundedCornerShape(10.dp))
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Filled.Search, contentDescription = null, tint = JF.ink3, modifier = Modifier.size(18.dp))
        Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
            if (value.isEmpty()) Text(prompt, style = JFFont.sans(15f), color = JF.ink3, maxLines = 1)
            BasicTextField(
                value = value,
                onValueChange = onChange,
                singleLine = true,
                textStyle = JFFont.sans(15f).copy(color = JF.ink),
                cursorBrush = SolidColor(JF.accent),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (value.isNotEmpty()) {
            Icon(
                Icons.Filled.Cancel,
                contentDescription = "Clear",
                tint = JF.ink3,
                modifier = Modifier.size(18.dp).clickable { onChange("") },
            )
        }
    }
}

/** A filter chip that opens a menu, as iOS's Menu on the Activity filters. */
@Composable
private fun FilterMenu(text: String, active: Boolean, options: List<Pair<String?, String>>, onPick: (String?) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        Row(
            Modifier
                .heightIn(min = 30.dp)
                .background(if (active) JF.accent else JF.panel)
                .border(1.dp, if (active) JF.accent else JF.line, RectangleShape)
                .clickable { open = true }
                .padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(text, style = JFFont.mono(12f, JFFont.Weight.Medium), color = if (active) JF.accentInk else JF.ink2, maxLines = 1, modifier = Modifier.widthIn(max = 170.dp))
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = null, tint = if (active) JF.accentInk else JF.ink2, modifier = Modifier.size(14.dp))
        }
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            containerColor = JF.panel,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.heightIn(max = 420.dp),
        ) {
            options.forEach { (value, label) ->
                DropdownMenuItem(
                    text = { Text(label, style = JFFont.sans(15f), color = JF.ink, maxLines = 1) },
                    onClick = {
                        open = false
                        onPick(value)
                    },
                )
            }
        }
    }
}

/** One transaction in full, including which account it belongs to. */
@Composable
fun TxnDetailScreen(tx: Txn, onBack: () -> Unit) {
    Screen(tx.title, inline = true, onBack = onBack) {
        Panel(if (tx.pending) "pending" else "posted") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Readout(label = if (tx.amount < 0) "money in" else "money out", value = Fmt.money(kotlin.math.abs(tx.amount), currency = tx.currency), size = 40f)
                Text(Fmt.day(tx.date)?.format(Fmt.longDay) ?: tx.date, style = JFFont.mono(12f), color = JF.ink3)
            }
        }
        Panel("details") {
            KeyValueRow("merchant") { Text(tx.merchant_name ?: "—") }
            KeyValueRow("description") { Text(tx.name) }
            KeyValueRow("category") { Text(Category.label(tx.category)) }
            tx.category_detailed?.let { KeyValueRow("bank category") { Text(Category.label(it, primary = tx.category_primary)) } }
            tx.payment_channel?.let { KeyValueRow("channel") { Text(it) } }
            tx.authorized_date?.takeIf { it != tx.date }?.let { KeyValueRow("authorized") { Text(Fmt.date(it, year = true)) } }
            tx.notes?.takeIf { it.isNotEmpty() }?.let { KeyValueRow("note") { Text(it) } }
        }
        Panel("account") {
            KeyValueRow("account") { Text(tx.account_name ?: "—") }
            tx.institution_name?.let { KeyValueRow("institution") { Text(it) } }
            tx.account_mask?.let { KeyValueRow("number") { Text("··$it", style = JFFont.mono(14f)) } }
        }
    }
}
