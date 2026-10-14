package com.daedalustcg.jfinances.kit.ui

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Currency
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToLong

/**
 * Formatting, as the web's lib/format and the iOS kit's Fmt: money with a
 * currency sign and grouping, compact money for tight places, and plain dates.
 */
object Fmt {
    private val locale = Locale.US
    private const val MINUS = "−"

    fun money(v: Double, cents: Boolean = true, currency: String = "USD"): String {
        val f = NumberFormat.getCurrencyInstance(locale)
        f.currency = runCatching { Currency.getInstance(currency) }.getOrDefault(Currency.getInstance("USD"))
        f.minimumFractionDigits = if (cents) 2 else 0
        f.maximumFractionDigits = if (cents) 2 else 0
        return f.format(v)
    }

    /** "+$1,234.00" / "−$1,234.00" (a real minus sign). */
    fun signed(v: Double, cents: Boolean = true, currency: String = "USD"): String {
        val body = money(abs(v), cents, currency)
        return when {
            v > 0 -> "+$body"
            v < 0 -> MINUS + body
            else -> body
        }
    }

    /** "$1.09M", "$54.3k", "$812" for tight places (widgets, chart axes). */
    fun compact(v: Double, currency: String = "USD"): String {
        val a = abs(v)
        val sign = if (v < 0) MINUS else ""
        val sym = if (currency == "USD") "$" else "$currency "
        fun trim(x: Double, digits: Int): String {
            var s = fixed(x, digits)
            if (s.contains('.')) s = s.trimEnd('0').trimEnd('.')
            return s
        }
        return when {
            a >= 1_000_000_000 -> "$sign$sym${trim(a / 1_000_000_000, 2)}B"
            a >= 1_000_000 -> "$sign$sym${trim(a / 1_000_000, if (a >= 10_000_000) 1 else 2)}M"
            a >= 10_000 -> "$sign$sym${trim(a / 1000, if (a >= 100_000) 0 else 1)}k"
            a >= 1000 -> "$sign$sym${trim(a / 1000, 2)}k"
            else -> "$sign$sym${a.roundToLong()}"
        }
    }

    /** 0.0123 -> "1.2%"; `ratio = false` when the value is already a percent. */
    fun pct(v: Double?, digits: Int = 1, ratio: Boolean = true, signed: Boolean = false): String {
        if (v == null) return "—"
        val p = if (ratio) v * 100 else v
        val s = fixed(abs(p), digits) + "%"
        if (signed) return if (p > 0) "+$s" else if (p < 0) MINUS + s else s
        return if (p < 0) MINUS + s else s
    }

    /**
     * `%.Nf` as iOS's String(format:) does it: the double's exact binary value,
     * ties to even. (Java's Formatter rounds the shortest decimal form half up,
     * so 1.075 would read "1.08" here and "1.07" on the iPhone.)
     */
    fun fixed(x: Double, digits: Int): String =
        if (x.isFinite()) BigDecimal(x).setScale(digits, RoundingMode.HALF_EVEN).toPlainString() else x.toString()

    fun number(v: Double, digits: Int = 0): String {
        val f = NumberFormat.getNumberInstance(locale)
        f.minimumFractionDigits = digits
        f.maximumFractionDigits = digits
        return f.format(v)
    }

    // ------------------------------------------------------------------ dates

    private val zone: ZoneId get() = ZoneId.systemDefault()
    private val monthDay = DateTimeFormatter.ofPattern("MMM d", locale)
    private val monthDayYear = DateTimeFormatter.ofPattern("MMM d, yyyy", locale)
    private val weekdayMonthDay = DateTimeFormatter.ofPattern("EEE, MMM d", locale)
    private val weekdayMonthDayYear = DateTimeFormatter.ofPattern("EEE, MMM d, yyyy", locale)
    private val monthOnly = DateTimeFormatter.ofPattern("MMM", locale)
    val longDay: DateTimeFormatter = DateTimeFormatter.ofPattern("EEEE, MMMM d, yyyy", locale)
    val axisDay: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d", locale)
    val axisMonthYear: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM yy", locale)

    fun today(): LocalDate = LocalDate.now(zone)

    /** "2026-10-14" (or a timestamp starting with one) as a calendar day. */
    fun day(iso: String?): LocalDate? {
        if (iso == null || iso.length < 10) return null
        return runCatching { LocalDate.parse(iso.substring(0, 10)) }.getOrNull()
    }

    fun isoDay(date: LocalDate): String = date.toString()

    fun timestamp(iso: String?): Instant? {
        if (iso == null) return null
        runCatching { return OffsetDateTime.parse(iso).toInstant() }
        runCatching { return Instant.parse(iso) }
        return day(iso)?.atStartOfDay(zone)?.toInstant()
    }

    /** "Oct 14", or "Oct 14, 2025" when it is not this year. */
    fun date(iso: String?, year: Boolean? = null): String {
        val d = day(iso) ?: return "—"
        val showYear = year ?: (d.year != today().year)
        return d.format(if (showYear) monthDayYear else monthDay)
    }

    /** "Today", "Yesterday", "Mon, Oct 12". */
    fun dayHeading(iso: String): String {
        val d = day(iso) ?: return iso
        val today = today()
        return when (d) {
            today -> "Today"
            today.minusDays(1) -> "Yesterday"
            today.plusDays(1) -> "Tomorrow"
            else -> d.format(if (d.year == today.year) weekdayMonthDay else weekdayMonthDayYear)
        }
    }

    /** "3 min ago", "2 h ago", "Oct 4". */
    fun relative(iso: String?): String {
        val t = timestamp(iso) ?: return "—"
        return relative(t.toEpochMilli(), iso)
    }

    fun relative(epochMs: Long, iso: String? = null): String {
        val s = (System.currentTimeMillis() - epochMs) / 1000.0
        return when {
            s < 60 -> "just now"
            s < 3600 -> "${(s / 60).toInt()} min ago"
            s < 86_400 -> "${(s / 3600).toInt()} h ago"
            s < 7 * 86_400 -> "${(s / 86_400).toInt()} d ago"
            else -> date(iso ?: Instant.ofEpochMilli(epochMs).atZone(zone).toLocalDate().toString())
        }
    }

    /** Days from today to `iso` (negative = past). */
    fun daysUntil(iso: String): Int? {
        val d = day(iso) ?: return null
        return ChronoUnit.DAYS.between(today(), d).toInt()
    }

    fun monthLabel(iso: String): String = day(iso)?.format(monthOnly) ?: iso
}

/**
 * Category keys as the dashboard says them ("FOOD_AND_DRINK" -> "food and
 * drink"; a detailed key loses its primary's prefix).
 */
object Category {
    fun label(key: String?, primary: String? = null): String {
        if (key.isNullOrEmpty()) return "uncategorized"
        if (key == "OTHER") return "other"
        if (key == "PAYMENT") return "payments"
        var k: String = key
        if (primary != null && key.startsWith(primary + "_")) k = key.substring(primary.length + 1)
        return k.lowercase().replace('_', ' ')
    }
}

/** The pixel layer (docs/70): square cells with a gap, each one lit or off. */
object Cells {
    /**
     * Average values into `n` buckets, oldest to newest; the last bucket
     * keeps the true last value.
     */
    fun downsample(values: List<Double>, n: Int): List<Double> {
        val finite = values.filter { it.isFinite() }
        if (finite.size <= n || n <= 0) return finite
        val out = MutableList(n) { b ->
            val lo = (b * finite.size) / n
            val hi = max(lo + 1, ((b + 1) * finite.size) / n)
            finite.subList(lo, hi).sum() / (hi - lo)
        }
        out[out.size - 1] = finite.last()
        return out
    }

    /**
     * Split `total` cells across shares so they sum exactly (largest
     * remainder); a positive share never rounds to nothing while a larger
     * one can spare a cell.
     */
    fun allocate(shares: List<Double>, total: Int): List<Int> {
        val pos = shares.map { if (it.isFinite() && it > 0) it else 0.0 }
        val sum = pos.sum()
        if (sum <= 0 || total <= 0) return pos.map { 0 }
        val exact = pos.map { it / sum * total }
        val counts = exact.map { kotlin.math.floor(it).toInt() }.toMutableList()
        var left = total - counts.sum()
        val order = exact.indices.sortedByDescending { exact[it] - kotlin.math.floor(exact[it]) }
        var k = 0
        while (left > 0 && k < order.size) {
            counts[order[k]] += 1
            left -= 1
            k += 1
        }
        for (i in counts.indices) {
            if (pos[i] > 0 && counts[i] == 0) {
                val donor = counts.indices.filter { counts[it] > 1 }.maxByOrNull { counts[it] }
                if (donor != null) {
                    counts[donor] -= 1
                    counts[i] = 1
                }
            }
        }
        return counts
    }
}
