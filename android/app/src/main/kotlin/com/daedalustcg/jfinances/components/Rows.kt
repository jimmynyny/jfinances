package com.daedalustcg.jfinances.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.MoneyAlert
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.models.UpcomingCharge
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.BadgeTone
import com.daedalustcg.jfinances.kit.ui.BusinessMark
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.MoneyStyle
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.PixelMeter
import com.daedalustcg.jfinances.kit.ui.PixelSparkline
import com.daedalustcg.jfinances.kit.ui.Rule
import com.daedalustcg.jfinances.kit.ui.figure

/** An account: name, institution ··last4, balance, and a dot-matrix trend. */
@Composable
fun AccountRow(account: Account, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(account.name, style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (account.is_business == true) BusinessMark()
            }
            Text(account.subtitle, style = JFFont.mono(11f), color = JF.ink3, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (account.trendValues.size >= 2) PixelSparkline(account.trendValues, Modifier.size(54.dp, 18.dp))
        MoneyText(account.balance, cents = false, size = 15f, weight = JFFont.Weight.Medium, currency = account.currency)
    }
}

/** A transaction: category glyph, merchant, category · account, amount. */
@Composable
fun TxnRow(tx: Txn, modifier: Modifier = Modifier, showAccount: Boolean = true, showDate: Boolean = false) {
    Row(modifier.fillMaxWidth().padding(vertical = 9.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(30.dp).background(JF.panel2).border(1.dp, JF.line, RectangleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(categoryIcon(if (tx.category == "PAYMENT") "PAYMENT" else tx.category_primary), contentDescription = null, tint = JF.ink2, modifier = Modifier.size(16.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(tx.title, style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (tx.is_business == true) BusinessMark()
                if (tx.pending) Badge("pending", BadgeTone.Warn)
            }
            val parts = buildList {
                if (showDate) add(Fmt.date(tx.date))
                add(Category.label(tx.category))
                if (showAccount && tx.account_name != null) add(tx.account_name + (tx.account_mask?.let { " ··$it" } ?: ""))
            }
            Text(parts.joinToString(" · "), style = JFFont.mono(11f), color = JF.ink3, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        MoneyText(tx.amount, style = MoneyStyle.Flow, size = 15f, weight = JFFont.Weight.Medium, currency = tx.currency)
    }
}

/** An expected charge: when, what, how much. */
@Composable
fun UpcomingRow(item: UpcomingCharge) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        val day = when (Fmt.daysUntil(item.date)) {
            0 -> if (item.overdue) "due" else "today"
            1 -> "tomorrow"
            else -> Fmt.date(item.date)
        }
        Text(day, style = JFFont.mono(11f, JFFont.Weight.Medium), color = if (item.overdue) JF.neg else JF.ink2, modifier = Modifier.width(64.dp), maxLines = 1)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(item.label, style = JFFont.sans(14f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (item.is_business == true) BusinessMark()
            }
            Text(listOfNotNull(item.cadence, item.account_name).joinToString(" · "), style = JFFont.mono(11f), color = JF.ink3, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        MoneyText(item.amount, size = 14f, weight = JFFont.Weight.Medium)
    }
}

/** An alert, in words: what happened and by how much. */
@Composable
fun AlertRow(alert: MoneyAlert) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(30.dp).background(JF.accentWash), contentAlignment = Alignment.Center) {
            Icon(alertIcon(alert.kind), contentDescription = null, tint = JF.accent, modifier = Modifier.size(16.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(alert.merchant, style = JFFont.sans(14f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(explanation(alert), style = JFFont.sans(13f), color = JF.ink2, modifier = Modifier.figure(13f))
            Text(Fmt.date(alert.date), style = JFFont.mono(11f), color = JF.ink3)
        }
        MoneyText(alert.amount, size = 14f, weight = JFFont.Weight.Medium)
    }
}

private fun explanation(alert: MoneyAlert): String = when (alert.kind) {
    "price" -> alert.previous?.let { "Price went from ${Fmt.money(it)} to ${Fmt.money(alert.amount)}." } ?: "The price changed."
    "duplicate" -> "Charged twice within two days."
    else -> alert.usual?.let { usual ->
        if (alert.basis == "category") {
            "Far above the usual ${Category.label(alert.category)} charge of ${Fmt.money(usual)}."
        } else {
            "Far above the usual ${Fmt.money(usual)} here."
        }
    } ?: "Larger than usual."
}

/** A category with its share of the total as a meter. */
@Composable
fun ShareRow(label: String, amount: Double, share: Double, series: Int?) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = JFFont.sans(14f), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            MoneyText(amount, cents = false, size = 13f)
            Text(
                Fmt.pct(share, digits = 0),
                style = JFFont.mono(11f),
                color = JF.ink3,
                textAlign = TextAlign.End,
                maxLines = 1,
                modifier = Modifier.width(38.dp).figure(11f),
            )
        }
        PixelMeter(share, cells = 32, series = series, tone = com.daedalustcg.jfinances.kit.ui.MeterTone.Ink, height = 6f)
    }
}

/** Rows separated by 1 dp rules, inside a flush panel. */
@Composable
fun <T> RuledList(items: List<T>, onClick: ((T) -> Unit)? = null, row: @Composable (T) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        items.forEachIndexed { i, item ->
            Box(
                Modifier
                    .fillMaxWidth()
                    .then(if (onClick != null) Modifier.clickable { onClick(item) } else Modifier)
                    .padding(horizontal = 16.dp),
            ) { row(item) }
            if (i < items.size - 1) Rule(Modifier.padding(start = 16.dp))
        }
    }
}
