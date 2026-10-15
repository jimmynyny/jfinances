package com.daedalustcg.jfinances.screens

import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.components.Chips
import com.daedalustcg.jfinances.components.ErrorNote
import com.daedalustcg.jfinances.components.PrimaryButton
import com.daedalustcg.jfinances.kit.storage.AppConfig
import com.daedalustcg.jfinances.kit.storage.Server
import com.daedalustcg.jfinances.kit.ui.Caption
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import kotlinx.coroutines.delay

/**
 * Not linked yet: sign in through Cloudflare Access once, and the phone gets
 * its own read-only token (docs/40 §5).
 */
@Composable
fun LinkScreen() {
    val model = LocalAppModel.current
    val activity = LocalActivity.current ?: return
    var server by remember { mutableStateOf(AppConfig.defaultServer) }
    Column(
        Modifier
            .fillMaxSize()
            .background(JF.page)
            .statusBarsPadding()
            .navigationBarsPadding()
            .padding(horizontal = 24.dp),
    ) {
        Spacer(Modifier.weight(1f).heightIn(min = 40.dp))
        LogoMark(Modifier.size(96.dp))
        Text("jFinances", style = JFFont.sans(34f, JFFont.Weight.Semibold), color = JF.ink, modifier = Modifier.padding(top = 28.dp))
        Text(
            "The household's money, on your phone and your home screen.",
            style = JFFont.sans(17f),
            color = JF.ink2,
            modifier = Modifier.padding(top = 6.dp),
        )
        Spacer(Modifier.weight(1f).heightIn(min = 32.dp))
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Caption("server")
            Chips(Server.choices.map { it to it.label.lowercase() }, server, { server = it })
            PrimaryButton(
                if (model.linking) "Signing in…" else "Sign in",
                onClick = { model.startLink(activity, server) },
                enabled = !model.linking,
                working = model.linking,
                modifier = Modifier.padding(top = 8.dp),
            )
            model.linkError?.let { ErrorNote(it) }
            Text(
                "You sign in with the same emailed code as the dashboard. This phone can read everything and change nothing; unlink it any time from Settings on either side.",
                style = JFFont.mono(11f),
                color = JF.ink3,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
        Spacer(Modifier.weight(1f).heightIn(min = 24.dp))
    }
}

/** The app icon's motif, live: a pixel sparkline whose newest cell glows. */
@Composable
fun LogoMark(modifier: Modifier = Modifier) {
    val trace = remember { listOf(1, 2, 2, 4, 3, 5, 6, 6, 8) }
    var lit by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        for (i in 0..9) {
            lit = i
            delay(70)
        }
    }
    val off = JF.pixelOff
    val ink = JF.ink
    val accent = JF.accent
    Canvas(modifier.fillMaxWidth()) {
        val n = 9
        val pitch = size.width / n
        val cell = pitch * 0.82f
        for (c in 0 until n) {
            for (r in 0 until n) {
                val level = trace[c]
                val color = when {
                    c >= lit -> off
                    r == level -> if (c == n - 1) accent else ink
                    r < level -> ink.copy(alpha = if (level - r <= 2) 0.38f else 0.16f)
                    else -> off
                }
                drawRect(color, Offset(c * pitch, (n - 1 - r) * pitch), Size(cell, cell))
            }
        }
    }
}
