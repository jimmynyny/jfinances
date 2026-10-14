package com.daedalustcg.jfinances.kit.storage

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import com.daedalustcg.jfinances.kit.models.JSON
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.Serializable

/** What linking leaves on the phone: the token, which server issued it, and who it belongs to. */
@Serializable
data class Credential(
    val token: String,
    val server: Server,
    val email: String,
    val displayName: String? = null,
    /** Epoch milliseconds. */
    val linkedAt: Long = System.currentTimeMillis(),
)

/**
 * The credential, encrypted with an AES-GCM key that never leaves the
 * Android Keystore, in no-backup storage. The app and its widgets are one
 * process here, so this one store serves both (iOS shares a Keychain group).
 *
 * ⚠ The key needs no unlock: a widget refreshes on a locked phone, which is
 * exactly when it is looked at. Credential-encrypted storage still keeps it
 * sealed until the first unlock after boot, as iOS's AfterFirstUnlock. The
 * file is never backed up or moved to a new phone (data_extraction_rules), and
 * the key could not follow it anyway: a restored phone signs in again.
 */
object Keychain {
    private const val KEY_ALIAS = "jfinances.credential"
    private const val IV_BYTES = 12
    private lateinit var file: AtomicFile

    @Volatile private var loaded = false
    @Volatile private var cached: Credential? = null

    fun init(context: Context) {
        file = AtomicFile(File(context.noBackupFilesDir, "credential.bin"))
    }

    fun read(): Credential? {
        if (loaded) return cached
        synchronized(this) {
            if (!loaded) {
                cached = runCatching { decrypt(file.readFully()) }.getOrNull()
                loaded = true
            }
            return cached
        }
    }

    fun write(credential: Credential): Boolean = synchronized(this) {
        runCatching {
            val sealed = encrypt(JSON.encodeToString(Credential.serializer(), credential).toByteArray())
            val out = file.startWrite()
            try {
                out.write(sealed)
                file.finishWrite(out)
            } catch (e: Exception) {
                file.failWrite(out)
                throw e
            }
            cached = credential
            loaded = true
        }.isSuccess
    }

    fun delete() = synchronized(this) {
        file.delete()
        cached = null
        loaded = true
    }

    private fun encrypt(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        return cipher.iv + cipher.doFinal(plain)
    }

    private fun decrypt(sealed: ByteArray): Credential {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, IV_BYTES))
        val plain = cipher.doFinal(sealed, IV_BYTES, sealed.size - IV_BYTES)
        return JSON.decodeFromString(Credential.serializer(), String(plain))
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }
}
