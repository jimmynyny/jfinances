package com.daedalustcg.jfinances.app

import android.app.Activity
import android.content.Context
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.CancellationSignal
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * The phone's own lock, for the app: fingerprint or face, with the screen
 * lock (PIN, pattern, password) as the fallback Android offers. The token
 * stays in the Keystore-sealed store either way; this only keeps the screens
 * from showing until the owner is there. iOS's Biometrics.swift is the twin;
 * this uses the platform prompt (API 30+), so no library is needed.
 */
object Biometrics {
    private const val ALLOWED = BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL

    /** Whether the phone can ask at all (a screen lock is set; a fingerprint, a face or the lock itself will do). */
    fun available(context: Context): Boolean =
        context.getSystemService(BiometricManager::class.java)?.canAuthenticate(ALLOWED) == BiometricManager.BIOMETRIC_SUCCESS

    /** "fingerprint or face", or "screen lock": how the switch and the prompt name it. */
    fun kind(context: Context): String {
        val m = context.getSystemService(BiometricManager::class.java) ?: return "screen lock"
        return if (m.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS) "fingerprint or face" else "screen lock"
    }

    /** Asks. False when cancelled, failed, or not available. */
    suspend fun authenticate(activity: Activity, title: String): Boolean {
        if (!available(activity)) return false
        return suspendCancellableCoroutine { cont ->
            val signal = CancellationSignal()
            cont.invokeOnCancellation { signal.cancel() }
            val prompt = BiometricPrompt.Builder(activity)
                .setTitle(title)
                .setAllowedAuthenticators(ALLOWED)
                .build()
            prompt.authenticate(signal, activity.mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    if (cont.isActive) cont.resume(true)
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    if (cont.isActive) cont.resume(false)
                }
            })
        }
    }
}
