package com.daedalustcg.jfinances.app

import android.app.Activity
import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Build
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import androidx.core.net.toUri
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.models.RedeemResponse
import com.daedalustcg.jfinances.kit.storage.Prefs
import com.daedalustcg.jfinances.kit.storage.Server
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64

sealed class LinkError(message: String) : Exception(message) {
    data object CouldNotStart : LinkError("Couldn't open the sign-in window.")
    data object BadCallback : LinkError("Sign-in came back without a valid code. Try again.")
}

/**
 * Linking, end to end (docs/40 §5): open the dashboard's link endpoint in a
 * Custom Tab, where Cloudflare Access does the login; catch the bounce to
 * `jfinances://linked?code=…&nonce=…`; check it answers this attempt; trade
 * the code for this phone's token on the API hostname.
 *
 * ⚠ PKCE (RFC 7636): any Android app can claim the `jfinances` scheme, so the
 * redirect is not private. The nonce sent is the SHA-256 of a secret verifier
 * kept here; only the verifier redeems the code, and it never goes in a URL.
 * The attempt is kept in preferences, so it survives Android ending the app
 * while the browser is open, for fifteen minutes: time to fetch an emailed
 * code. The code the server mints at the end lives two minutes.
 */
object LinkService {
    private const val PENDING = "jf.link.pending"
    private const val TTL_MS = 15 * 60_000L

    /** Not ephemeral: an Access session already open in the browser makes linking one tap instead of an emailed code. */
    fun start(activity: Activity, server: Server): Boolean {
        val verifier = makeVerifier()
        val challenge = challenge(verifier)
        Prefs.setString(PENDING, listOf(server.name, verifier, challenge, System.currentTimeMillis().toString()).joinToString(" "))
        val url = server.dashboard.toUri().buildUpon()
            .path("/api/v1/mobile/link")
            .appendQueryParameter("nonce", challenge)
            .appendQueryParameter("method", "S256")
            .appendQueryParameter("name", deviceName)
            .build()
        val dark = (activity.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
            android.content.res.Configuration.UI_MODE_NIGHT_YES
        val bar = if (dark) 0xFF161719.toInt() else 0xFFFFFFFF.toInt()
        val tab = CustomTabsIntent.Builder()
            .setShowTitle(true)
            .setShareState(CustomTabsIntent.SHARE_STATE_OFF)
            .setDefaultColorSchemeParams(CustomTabColorSchemeParams.Builder().setToolbarColor(bar).build())
            .build()
        return try {
            tab.launchUrl(activity, url)
            true
        } catch (e: ActivityNotFoundException) {
            Prefs.setString(PENDING, "")
            false
        }
    }

    /** The redirect: it must answer the attempt this phone started. */
    suspend fun complete(callback: Uri): Pair<RedeemResponse, Server> {
        val parts = Prefs.string(PENDING, "").split(" ")
        Prefs.setString(PENDING, "")
        if (parts.size != 4) throw LinkError.BadCallback
        val (serverName, verifier, challenge, startedAt) = parts
        val server = Server.entries.firstOrNull { it.name == serverName } ?: throw LinkError.BadCallback
        val fresh = System.currentTimeMillis() - (startedAt.toLongOrNull() ?: 0L) < TTL_MS
        val code = callback.getQueryParameter("code")
        val back = callback.getQueryParameter("nonce")
        if (!fresh || code.isNullOrEmpty() || back != challenge) throw LinkError.BadCallback
        return ApiClient.redeem(server, code, verifier, deviceName) to server
    }

    /** 64 characters from RFC 7636's unreserved set: 384 bits. */
    private fun makeVerifier(): String {
        val bytes = ByteArray(48).also { SecureRandom().nextBytes(it) }
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }

    /** BASE64URL(SHA-256(verifier)), unpadded: 43 characters. */
    fun challenge(verifier: String): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()))

    /** What Settings → phones on the dashboard calls this phone. */
    val deviceName: String
        get() {
            val maker = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
            val model = if (Build.MODEL.startsWith(Build.MANUFACTURER, ignoreCase = true)) Build.MODEL else "$maker ${Build.MODEL}"
            return "$model · Android ${Build.VERSION.RELEASE}"
        }
}
