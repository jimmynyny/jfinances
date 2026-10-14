@file:OptIn(ExperimentalSerializationApi::class)

package com.daedalustcg.jfinances.kit.models

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * The server sends money and quantities as decimal strings ("1234.56") and
 * ratios as numbers (docs/80). These take either, so a model can say
 * `val amount: Flex = 0.0` and not care which arrived.
 *
 * Doubles are fine here: this side only formats and draws. The arithmetic
 * that matters (sums, balances) is done in `numeric` on the server.
 */
object FlexSerializer : KSerializer<Double> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("Flex", PrimitiveKind.DOUBLE)

    override fun deserialize(decoder: Decoder): Double =
        flexValue(decoder) ?: 0.0

    override fun serialize(encoder: Encoder, value: Double) = encoder.encodeDouble(value)
}

/** [FlexSerializer], where null (or a missing key) means "not known" rather than zero. */
object FlexOptSerializer : KSerializer<Double?> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("FlexOpt", PrimitiveKind.DOUBLE)

    override fun deserialize(decoder: Decoder): Double? = flexValue(decoder)

    override fun serialize(encoder: Encoder, value: Double?) {
        if (value == null) encoder.encodeNull() else encoder.encodeDouble(value)
    }
}

private fun flexValue(decoder: Decoder): Double? {
    val json = decoder as? JsonDecoder ?: return decoder.decodeDouble()
    return when (val e = json.decodeJsonElement()) {
        is JsonNull -> null
        is JsonPrimitive -> e.doubleOrNull ?: e.contentOrNull?.toDoubleOrNull()
        else -> throw SerializationException("expected a number or a decimal string")
    }
}

typealias Flex = @Serializable(with = FlexSerializer::class) Double
typealias FlexOpt = @Serializable(with = FlexOptSerializer::class) Double?

/** A number out of an untyped point (net worth by kind: one key per group). */
fun JsonObject.number(key: String): Double {
    val e = this[key] as? JsonPrimitive ?: return 0.0
    return e.doubleOrNull ?: e.contentOrNull?.toDoubleOrNull() ?: 0.0
}

fun JsonObject.string(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

/**
 * One decoder for everything. A missing optional field decodes as null, and an
 * unknown one is ignored: an older or newer server should still draw.
 */
val JSON = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
}
