package com.daedalustcg.jfinances.kit.storage

import com.daedalustcg.jfinances.BuildConfig
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Which jfinances the phone talks to. Each environment has a dashboard
 * hostname (behind Cloudflare Access: where linking starts) and an API
 * hostname (no Access: where the phone's own token is accepted). docs/40 §5.
 */
@Serializable
enum class Server(val label: String, val dashboard: String, val api: String) {
    @SerialName("production")
    PRODUCTION("Production", "https://jfinances.sellingtcg.com", "https://jfinances-api.sellingtcg.com"),

    @SerialName("sandbox")
    SANDBOX("Sandbox", "https://jfinances-sandbox.sellingtcg.com", "https://jfinances-sandbox-api.sellingtcg.com"),

    /**
     * A developer's own server, reached from an emulator over `adb reverse`
     * (Scripts/emu-tour.sh). Offered by debug builds only; a release build
     * also refuses its plain HTTP (network_security_config).
     */
    @SerialName("local")
    LOCAL("Local", "http://127.0.0.1:8000", "http://127.0.0.1:8001");

    val apiHost: String get() = api.substringAfter("://").substringBefore(":").substringBefore("/")

    companion object {
        /** What the sign-in screen offers. */
        val choices: List<Server> get() = if (BuildConfig.LOCAL_SERVER) entries else listOf(PRODUCTION, SANDBOX)
    }
}

object AppConfig {
    /**
     * The server bounces the link to `jfinances://linked?code=…&nonce=…`;
     * widgets open `jfinances://overview` and friends.
     */
    const val SCHEME = "jfinances"

    /** Which server the sign-in screen offers first (BuildConfig.DEFAULT_SERVER). */
    val defaultServer: Server
        get() = Server.entries.firstOrNull { it.name.equals(BuildConfig.DEFAULT_SERVER, ignoreCase = true) }
            ?: Server.PRODUCTION
}
