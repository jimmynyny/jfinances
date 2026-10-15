package com.daedalustcg.jfinances.app

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.offset
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import com.daedalustcg.jfinances.R
import com.daedalustcg.jfinances.kit.ui.JFFont
import kotlinx.coroutines.delay
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.daedalustcg.jfinances.components.ToastHost
import com.daedalustcg.jfinances.components.glass
import com.daedalustcg.jfinances.components.icon
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.LocalPalette
import com.daedalustcg.jfinances.screens.AccountDetailScreen
import com.daedalustcg.jfinances.screens.AccountsScreen
import com.daedalustcg.jfinances.screens.ActivityScreen
import com.daedalustcg.jfinances.screens.ConnectionsScreen
import com.daedalustcg.jfinances.screens.DrillScreen
import com.daedalustcg.jfinances.screens.InsightsScreen
import com.daedalustcg.jfinances.screens.LinkScreen
import com.daedalustcg.jfinances.screens.OverviewScreen
import com.daedalustcg.jfinances.screens.SettingsScreen
import com.daedalustcg.jfinances.screens.TxnDetailScreen

@Composable
fun RootView() {
    val model = LocalAppModel.current
    var splash by rememberSaveable { mutableStateOf(true) }
    LaunchedEffect(Unit) {
        delay(1100)
        splash = false
    }
    Box(Modifier.fillMaxSize().background(JF.page)) {
        Crossfade(targetState = model.isLinked, animationSpec = tween(200), label = "linked") { linked ->
            if (linked) MainTabs() else LinkScreen()
        }
        AnimatedVisibility(
            visible = model.toastText != null,
            modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = TabBarHeight + 28.dp),
            enter = fadeIn(tween(200)),
            exit = fadeOut(tween(200)),
        ) { ToastHost(model.toastText) }
        AnimatedVisibility(visible = splash, enter = fadeIn(tween(0)), exit = fadeOut(tween(350))) { SplashView() }
    }
}

/**
 * The first thing on screen after the system's icon: the app icon and the name,
 * for a moment while the first glance loads behind it (iOS's SplashView).
 */
@Composable
fun SplashView() {
    Box(
        Modifier.fillMaxSize().background(JF.page).semantics { contentDescription = "jFinances" },
        contentAlignment = Alignment.Center,
    ) {
        Image(
            painterResource(R.drawable.splash_icon),
            contentDescription = null,
            modifier = Modifier.size(112.dp).border(1.dp, JF.line, RoundedCornerShape(25.dp)),
        )
        Text(
            "jFinances",
            style = JFFont.sans(30f, JFFont.Weight.Semibold),
            color = JF.ink,
            modifier = Modifier.offset(y = 92.dp),
        )
    }
}

/** Five tabs, each with its own stack, under a floating tab bar (iOS 26's). */
@Composable
fun MainTabs() {
    val model = LocalAppModel.current
    val tabs = rememberSaveableStateHolder()
    Box(Modifier.fillMaxSize()) {
        val tab = model.tab
        tabs.SaveableStateProvider(tab.name) { TabStack(tab) }
        TabBar(Modifier.align(Alignment.BottomCenter))
    }
    BackHandler(enabled = model.stacks.getValue(model.tab).isNotEmpty()) { model.pop() }
}

@Composable
private fun TabStack(tab: AppTab) {
    val model = LocalAppModel.current
    val stack = model.stacks.getValue(tab)
    val screens = rememberSaveableStateHolder()
    AnimatedContent(
        targetState = stack.size to stack.lastOrNull(),
        transitionSpec = {
            val push = targetState.first > initialState.first
            val spec = tween<androidx.compose.ui.unit.IntOffset>(280)
            if (push) {
                slideInHorizontally(spec) { it } togetherWith slideOutHorizontally(spec) { -it / 3 }
            } else {
                slideInHorizontally(spec) { -it / 3 } togetherWith slideOutHorizontally(spec) { it }
            }
        },
        label = "stack",
    ) { (_, route) ->
        if (route == null) {
            screens.SaveableStateProvider("root") { TabRoot(tab) }
        } else {
            key(route) { screens.SaveableStateProvider(route.hashCode()) { RouteScreen(route) } }
        }
    }
    if (tab == AppTab.Accounts) {
        // A widget's link to one account: push it, from the last glance or the server.
        LaunchedEffect(model.pendingAccountId) {
            val id = model.pendingAccountId ?: return@LaunchedEffect
            model.pendingAccountId = null
            val known = model.glance?.accounts?.firstOrNull { it.id == id }
                ?: runCatching { ApiClient.accounts() }.getOrNull()?.firstOrNull { it.id == id }
            if (known != null) {
                stack.clear()
                stack.add(Route.AccountDetail(known))
            }
        }
    }
}

@Composable
private fun TabRoot(tab: AppTab) {
    when (tab) {
        AppTab.Overview -> OverviewScreen()
        AppTab.Accounts -> AccountsScreen()
        AppTab.Activity -> ActivityScreen()
        AppTab.Insights -> InsightsScreen()
        AppTab.Settings -> SettingsScreen()
    }
}

@Composable
private fun RouteScreen(route: Route) {
    val model = LocalAppModel.current
    when (route) {
        is Route.AccountDetail -> AccountDetailScreen(route.account, onBack = { model.pop() })
        is Route.TxnDetail -> TxnDetailScreen(route.tx, onBack = { model.pop() })
        is Route.Drill -> DrillScreen(route.target, onBack = { model.pop() })
        Route.Connections -> ConnectionsScreen(onBack = { model.pop() })
    }
}

val TabBarHeight = 62.dp

@Composable
fun TabBar(modifier: Modifier = Modifier) {
    val model = LocalAppModel.current
    val dark = LocalPalette.current.dark
    val pill = if (dark) Color.Black.copy(alpha = 0.38f) else Color.Black.copy(alpha = 0.06f)
    Row(
        modifier
            .navigationBarsPadding()
            .padding(start = 20.dp, end = 20.dp, bottom = 8.dp)
            .fillMaxWidth()
            .height(TabBarHeight)
            .glass(RoundedCornerShape(TabBarHeight / 2))
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(0.dp),
    ) {
        AppTab.entries.forEach { t ->
            val on = t == model.tab
            val tint = if (on) JF.accent else JF.ink
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(27.dp))
                    .background(if (on) pill else Color.Transparent)
                    .clickable(role = Role.Tab) { model.select(t) }
                    .semantics { selected = on },
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(t.icon, contentDescription = null, tint = tint, modifier = Modifier.size(25.dp))
                Text(t.title, style = TextStyle(fontSize = 10.sp, fontWeight = FontWeight.Medium, color = tint), maxLines = 1)
            }
        }
    }
}
