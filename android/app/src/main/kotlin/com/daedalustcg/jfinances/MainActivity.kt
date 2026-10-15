package com.daedalustcg.jfinances

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.CompositionLocalProvider
import androidx.lifecycle.lifecycleScope
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.RootView
import com.daedalustcg.jfinances.kit.ui.JFTheme
import com.daedalustcg.jfinances.kit.ui.LocalBlurNumbers
import com.daedalustcg.jfinances.widgets.Widgets
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val model get() = (application as JFinancesApplication).model

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        if (BuildConfig.LOCAL_SERVER) debugSignIn(intent)
        if (savedInstanceState == null) intent?.data?.let { model.open(it) }
        lifecycleScope.launch { Widgets.publishPreviews(applicationContext) }
        setContent {
            JFTheme {
                CompositionLocalProvider(LocalAppModel provides model, LocalBlurNumbers provides model.blur) {
                    RootView()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (BuildConfig.LOCAL_SERVER) debugSignIn(intent)
        intent.data?.let { model.open(it) }
    }

    override fun onResume() {
        super.onResume()
        model.onResumed()
    }

    override fun onStop() {
        super.onStop()
        model.background()
    }

    /**
     * Emulator QA against a local server (Scripts/emu-tour.sh): a token for that
     * database stands in for the Access sign-in, as iOS's JF_DEBUG_TOKEN.
     * Debug builds only.
     */
    private fun debugSignIn(intent: Intent?) {
        val token = intent?.getStringExtra("jf_debug_token")?.takeIf { it.isNotBlank() } ?: return
        intent.removeExtra("jf_debug_token")
        model.debugSignIn(token)
    }
}
