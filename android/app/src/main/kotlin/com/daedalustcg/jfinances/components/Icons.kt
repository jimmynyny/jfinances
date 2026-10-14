package com.daedalustcg.jfinances.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.CallReceived
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.NorthEast
import androidx.compose.material.icons.filled.PriorityHigh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Build
import androidx.compose.material.icons.outlined.Business
import androidx.compose.material.icons.outlined.Category
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material.icons.outlined.DirectionsCar
import androidx.compose.material.icons.outlined.Flight
import androidx.compose.material.icons.outlined.Handyman
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.MedicalServices
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.Restaurant
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material.icons.outlined.SmartDisplay
import androidx.compose.ui.graphics.vector.ImageVector
import com.daedalustcg.jfinances.app.AppTab

/** The tab bar's glyphs: the nearest Material symbols to the iOS app's SF Symbols. */
val AppTab.icon: ImageVector
    get() = when (this) {
        AppTab.Overview -> GridFill
        AppTab.Accounts -> Icons.Filled.AccountBalance
        AppTab.Activity -> ListFill
        AppTab.Insights -> Icons.Filled.BarChart
        AppTab.Settings -> Icons.Filled.Settings
    }

/** A glyph for a primary category, for list rows (Category.symbol on iOS). */
fun categoryIcon(key: String?): ImageVector = when (key ?: "") {
    "INCOME" -> Icons.AutoMirrored.Filled.CallReceived
    "TRANSFER_IN", "TRANSFER_OUT" -> Icons.Filled.SwapHoriz
    "PAYMENT", "LOAN_PAYMENTS" -> Icons.Outlined.CreditCard
    "BANK_FEES" -> Icons.Outlined.AccountBalance
    "ENTERTAINMENT" -> Icons.Outlined.SmartDisplay
    "FOOD_AND_DRINK" -> Icons.Outlined.Restaurant
    "GENERAL_MERCHANDISE" -> Icons.Outlined.ShoppingBag
    "HOME_IMPROVEMENT" -> Icons.Outlined.Handyman
    "MEDICAL" -> Icons.Outlined.MedicalServices
    "PERSONAL_CARE" -> Icons.Outlined.AutoAwesome
    "GENERAL_SERVICES" -> Icons.Outlined.Build
    "GOVERNMENT_AND_NON_PROFIT" -> Icons.Outlined.Business
    "TRANSPORTATION" -> Icons.Outlined.DirectionsCar
    "TRAVEL" -> Icons.Outlined.Flight
    "RENT_AND_UTILITIES" -> Icons.Outlined.Home
    "LOAN_DISBURSEMENTS" -> Icons.Outlined.Payments
    else -> Icons.Outlined.Category
}

/** An alert's glyph: price, duplicate, large. */
fun alertIcon(kind: String): ImageVector = when (kind) {
    "price" -> Icons.Filled.NorthEast
    "duplicate" -> Icons.Filled.ContentCopy
    else -> Icons.Filled.PriorityHigh
}
