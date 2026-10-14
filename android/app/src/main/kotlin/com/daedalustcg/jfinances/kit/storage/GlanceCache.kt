package com.daedalustcg.jfinances.kit.storage

import android.content.Context
import android.util.AtomicFile
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.models.Glance
import com.daedalustcg.jfinances.kit.models.JSON
import java.io.File
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable

/**
 * The last glance, on disk, so a widget drawn while offline shows the last
 * known figures with their age rather than an empty box, and so several
 * widgets refreshing together share one request.
 */
@Serializable
data class CachedGlance(
    val glance: Glance,
    /** Epoch milliseconds. */
    val fetchedAt: Long = System.currentTimeMillis(),
    /** Which server it came from: a phone relinked elsewhere must not show the other environment's numbers. */
    val server: Server,
)

object GlanceCache {
    private lateinit var file: AtomicFile

    /** Widgets refreshing together wait for one request instead of making four. */
    private val fetching = Mutex()

    fun init(context: Context) {
        file = AtomicFile(File(context.cacheDir, "glance.json"))
    }

    fun load(): CachedGlance? {
        val cached = runCatching { JSON.decodeFromString(CachedGlance.serializer(), String(file.readFully())) }.getOrNull()
            ?: return null
        // A different (or no) credential: the cache belongs to someone else.
        val cred = Keychain.read() ?: return null
        return cached.takeIf { it.server == cred.server }
    }

    fun save(cached: CachedGlance) {
        runCatching {
            val out = file.startWrite()
            try {
                out.write(JSON.encodeToString(CachedGlance.serializer(), cached).toByteArray())
                file.finishWrite(out)
            } catch (e: Exception) {
                file.failWrite(out)
                throw e
            }
        }
    }

    fun clear() = file.delete()

    /**
     * The cached glance when it is younger than [maxAgeMs], else a fresh one
     * (saved). Falls back to the cache, however old, when the fetch fails;
     * the error is returned beside it so the caller can say "as of".
     */
    suspend fun fetch(maxAgeMs: Long): Pair<CachedGlance?, ApiError?> = fetching.withLock {
        val cached = load()
        if (cached != null && System.currentTimeMillis() - cached.fetchedAt < maxAgeMs) return cached to null
        val cred = Keychain.read() ?: return null to ApiError.NotLinked
        try {
            val fresh = CachedGlance(ApiClient.glance(), System.currentTimeMillis(), cred.server)
            save(fresh)
            fresh to null
        } catch (e: ApiError) {
            if (e.tokenIsDead) clear()
            (if (e.tokenIsDead) null else cached) to e
        }
    }
}

/** Starts the kit's stores; the Application calls it before anything reads them. */
object Kit {
    fun init(context: Context) {
        Keychain.init(context)
        GlanceCache.init(context)
        Prefs.init(context)
    }
}
