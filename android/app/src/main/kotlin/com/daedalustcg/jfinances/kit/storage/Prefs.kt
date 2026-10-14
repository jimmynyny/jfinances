package com.daedalustcg.jfinances.kit.storage

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.core.content.edit

/** Small choices that outlive the app (the iOS @AppStorage keys): ranges, scopes, the blur switch. */
object Prefs {
    private lateinit var prefs: SharedPreferences

    fun init(context: Context) {
        prefs = context.getSharedPreferences("jf", Context.MODE_PRIVATE)
    }

    fun string(key: String, default: String): String = prefs.getString(key, default) ?: default
    fun setString(key: String, value: String) = prefs.edit { putString(key, value) }
    fun bool(key: String, default: Boolean = false): Boolean = prefs.getBoolean(key, default)
    fun setBool(key: String, value: Boolean) = prefs.edit { putBoolean(key, value) }
}

/** A remembered string that writes through to [Prefs], as SwiftUI's `@AppStorage`. */
@Composable
fun rememberPref(key: String, default: String): MutableState<String> = remember(key) {
    PrefState(key, mutableStateOf(Prefs.string(key, default)))
}

private class PrefState(private val key: String, private val state: MutableState<String>) : MutableState<String> {
    override var value: String
        get() = state.value
        set(v) {
            if (v != state.value) Prefs.setString(key, v)
            state.value = v
        }

    override fun component1(): String = value
    override fun component2(): (String) -> Unit = { value = it }
}

