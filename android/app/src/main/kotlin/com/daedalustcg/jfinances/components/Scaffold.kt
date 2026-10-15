package com.daedalustcg.jfinances.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.outlined.ReportProblem
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.currentCompositeKeyHashCode
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.TabBarHeight
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.LocalPalette
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** The top bar's height under the status bar, and the large title's block below it. */
val TopBarHeight = 52.dp
private val LargeTitleHeight = 52.dp

/** Room kept under every screen for the floating tab bar. */
@Composable
fun tabBarSpace(): Dp = TabBarHeight + WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding() + 24.dp

/**
 * A tab's page: the desk-coloured background, panels in a column with the
 * dashboard's 16 dp gutter, pull to refresh, and a large title in the top row
 * that scrolls up into the bar (iOS's large titles). Blur lives in Settings.
 * `inline` screens (an account, a transaction) show their title in the bar
 * from the start, with a back button.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Screen(
    title: String,
    inline: Boolean = false,
    onBack: (() -> Unit)? = null,
    scroll: ScrollState = rememberScrollState(),
    content: @Composable ColumnScope.() -> Unit,
) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    val state = rememberPullToRefreshState()
    // A tab's root has nothing in the bar at rest, so its title takes the bar's row.
    val top = WindowInsets.statusBars.asPaddingValues().calculateTopPadding() + if (inline || onBack != null) TopBarHeight else 0.dp
    val titlePx = with(LocalDensity.current) { (LargeTitleHeight - 12.dp).toPx() }
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
            state = state,
            indicator = {
                PullToRefreshDefaults.Indicator(
                    state = state,
                    isRefreshing = refreshing,
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = top),
                    containerColor = JF.panel,
                    color = JF.ink3,
                )
            },
        ) {
            Column(
                Modifier
                    .fillMaxSize()
                    .verticalScroll(scroll)
                    .padding(top = top, bottom = tabBarSpace())
                    .padding(horizontal = JF.gutter),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (!inline) LargeTitle(title) else Spacer(Modifier.height(0.dp))
                content()
            }
        }
        val showTitle by remember(inline, titlePx) { derivedStateOf { inline || scroll.value > titlePx } }
        val scrolled by remember { derivedStateOf { scroll.value > 0 } }
        TopBar(title = title, showTitle = showTitle, scrolled = scrolled, onBack = onBack)
    }
}

@Composable
fun LargeTitle(title: String) {
    Box(Modifier.fillMaxWidth().height(LargeTitleHeight), contentAlignment = Alignment.BottomStart) {
        Text(title, style = JFFont.sans(30f, JFFont.Weight.Semibold), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * The bar over every screen: back (pushed screens) and the title once the
 * large one has scrolled away. Clear at rest; the page's colour once
 * content slides under it.
 */
@Composable
fun TopBar(title: String, showTitle: Boolean, scrolled: Boolean, onBack: (() -> Unit)?) {
    val page = JF.page
    Box(
        Modifier
            .fillMaxWidth()
            .background(
                if (scrolled) {
                    Brush.verticalGradient(0f to page.copy(alpha = 0.96f), 0.82f to page.copy(alpha = 0.9f), 1f to page.copy(alpha = 0f))
                } else {
                    Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent))
                },
            )
            .statusBarsPadding()
            .height(TopBarHeight + 8.dp)
            .padding(horizontal = JF.gutter),
    ) {
        Box(Modifier.fillMaxWidth().height(TopBarHeight)) {
            if (onBack != null) {
                GlassCircle(onClick = onBack, modifier = Modifier.align(Alignment.CenterStart), label = "Back") {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = null, tint = JF.ink, modifier = Modifier.size(28.dp))
                }
            }
            AnimatedVisibility(
                visible = showTitle,
                modifier = Modifier.align(Alignment.Center),
                enter = fadeIn(tween(160)),
                exit = fadeOut(tween(120)),
            ) {
                Text(
                    title,
                    style = JFFont.sans(17f, JFFont.Weight.Semibold),
                    color = JF.ink,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.widthIn(max = 230.dp),
                )
            }
        }
    }
}

/** iOS 26's floating glass: a soft fill, a hairline edge, a shadow in light mode. */
@Composable
fun Modifier.glass(shape: androidx.compose.ui.graphics.Shape): Modifier {
    val dark = LocalPalette.current.dark
    val fill = if (dark) Color(0xFF2A2B2F).copy(alpha = 0.97f) else Color(0xFFFFFFFF).copy(alpha = 0.96f)
    val edge = if (dark) Color.White.copy(alpha = 0.10f) else Color.Black.copy(alpha = 0.07f)
    return this
        .then(if (dark) Modifier else Modifier.shadow(10.dp, shape, ambientColor = Color.Black.copy(alpha = 0.10f), spotColor = Color.Black.copy(alpha = 0.16f)))
        .background(fill, shape)
        .border(0.5.dp, edge, shape)
}

@Composable
fun GlassCircle(onClick: () -> Unit, modifier: Modifier = Modifier, label: String, content: @Composable BoxScope.() -> Unit) {
    Box(
        modifier
            .size(44.dp)
            .glass(CircleShape)
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
        content = content,
    )
}

sealed interface LoadState<out T> {
    data object Loading : LoadState<Nothing>
    data class Failed(val message: String) : LoadState<Nothing>
    data class Loaded<T>(val value: T) : LoadState<T>
}

/**
 * Loads `T` when it appears and whenever `id` or the app's refresh token
 * changes; keeps showing the last value (dimmed) while a new one loads, and
 * routes API errors through the model so a dead token signs the phone out.
 * What it last showed is remembered by its place on screen, so a tab you come
 * back to shows its figures at once while they refresh, as on iOS.
 */
@Composable
fun <T> Loader(
    id: Any? = 0,
    height: Dp = 120.dp,
    load: suspend () -> T,
    content: @Composable (T) -> Unit,
) {
    val model = LocalAppModel.current
    val slot = currentCompositeKeyHashCode
    @Suppress("UNCHECKED_CAST")
    var state by remember { mutableStateOf((model.loaderMemory[slot] as? LoadState<T>) ?: LoadState.Loading) }
    var reloading by remember { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    LaunchedEffect(id, model.refreshToken, attempt) {
        if (state is LoadState.Loaded) reloading = true
        try {
            val value = load()
            state = LoadState.Loaded(value)
            model.loaderMemory[slot] = state
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiError) {
            model.handle(e)
            // keep the last good value on screen
            if (state !is LoadState.Loaded) state = LoadState.Failed(e.description)
        } catch (e: Exception) {
            if (state !is LoadState.Loaded) state = LoadState.Failed(e.message ?: "Something went wrong.")
        } finally {
            reloading = false
        }
    }
    when (val s = state) {
        LoadState.Loading -> Skeleton(height)
        is LoadState.Failed -> ErrorNote(s.message) { attempt += 1 }
        is LoadState.Loaded -> Box(Modifier.alpha(if (reloading) 0.55f else 1f)) { content(s.value) }
    }
}

@Composable
fun Skeleton(height: Dp) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(height)
            .background(JF.panel2)
            .semantics { contentDescription = "Loading" },
    )
}

@Composable
fun ErrorNote(message: String, retry: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().background(JF.negWash).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Outlined.ReportProblem, contentDescription = null, tint = JF.neg, modifier = Modifier.size(20.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(message, style = JFFont.sans(14f), color = JF.ink)
            if (retry != null) {
                Text(
                    "Try again",
                    style = JFFont.mono(12f, JFFont.Weight.Medium),
                    color = JF.accent,
                    modifier = Modifier.clickable(role = Role.Button, onClick = retry),
                )
            }
        }
    }
}

/** A row of mono chips, the dashboard's small segmented control. */
@Composable
fun <V> Chips(options: List<Pair<V, String>>, value: V, onChange: (V) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.border(1.dp, JF.line, RectangleShape)) {
        options.forEachIndexed { i, (v, label) ->
            val on = v == value
            Box(
                Modifier
                    .heightIn(min = 24.dp)
                    .background(if (on) JF.accent else JF.panel)
                    .clickable(role = Role.Tab) { onChange(v) }
                    .semantics { selected = on }
                    .padding(horizontal = 7.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(label, style = JFFont.mono(11f, JFFont.Weight.Medium), color = if (on) JF.accentInk else JF.ink2, maxLines = 1, softWrap = false)
            }
            if (i < options.size - 1) Box(Modifier.width(1.dp).height(24.dp).background(JF.line))
        }
    }
}

/** The dashboard's primary button: accent fill, square, a flat offset shadow. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, working: Boolean = false) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shift = if (pressed) 2.dp else 0.dp
    Box(modifier.fillMaxWidth().height(52.dp)) {
        Box(Modifier.fillMaxWidth().height(50.dp).offset(2.dp, 2.dp).background(JF.lineStrong))
        Row(
            Modifier
                .fillMaxWidth()
                .height(50.dp)
                .offset(shift, shift)
                .background(JF.accent)
                .border(1.dp, JF.lineStrong, RectangleShape)
                .clickable(interactionSource = interaction, indication = null, enabled = enabled, role = Role.Button, onClick = onClick),
            horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (working) CircularProgressIndicator(Modifier.size(18.dp), color = JF.accentInk, strokeWidth = 2.dp)
            Text(text, style = JFFont.sans(16f, JFFont.Weight.Semibold), color = JF.accentInk)
        }
    }
}

@Composable
fun QuietButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, destructive: Boolean = false) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Box(
        modifier
            .fillMaxWidth()
            .heightIn(min = 46.dp)
            .background(if (pressed) JF.panel2 else JF.panel)
            .border(1.dp, JF.line, RectangleShape)
            .clickable(interactionSource = interaction, indication = null, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = JFFont.sans(15f, JFFont.Weight.Medium), color = if (destructive) JF.neg else JF.ink)
    }
}

/** A note in the mono caption style, for "as of" lines and fine print. */
@Composable
fun Fine(text: String, modifier: Modifier = Modifier, textAlign: TextAlign? = null) {
    Text(text, modifier = modifier, style = JFFont.mono(11f), color = JF.ink3, textAlign = textAlign)
}

/** A mono text button, as the iOS screens' small links ("All 7 alerts"). */
@Composable
fun LinkText(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Text(
        text,
        style = JFFont.mono(12f, JFFont.Weight.Medium),
        color = if (enabled) JF.accent else JF.ink3,
        modifier = modifier.clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(vertical = 4.dp),
    )
}

val NoPadding = PaddingValues(0.dp)
