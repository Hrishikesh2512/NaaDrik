package com.naadrik.core.config

class ConfigException(
    message: String,
) : Exception(message)

internal fun require(
    condition: Boolean,
    message: String,
) {
    if (!condition) throw ConfigException(message)
}

/**
 * A mapping from the YAML file that records which keys were read, so that unknown keys
 * (usually typos) fail loudly instead of being ignored, exactly like the Python loader.
 */
internal class YamlSection(
    private val data: Map<*, *>,
    private val path: String,
) {
    private val used = mutableSetOf<String>()

    fun raw(key: String): Any? {
        if (!data.containsKey(key)) throw ConfigException("$path: missing key(s) [$key]")
        used += key
        return data[key]
    }

    fun double(key: String): Double =
        when (val value = raw(key)) {
            is Int, is Long, is Double, is Float -> (value as Number).toDouble()
            else -> fail(key, "a number", value)
        }

    fun int(key: String): Int =
        when (val value = raw(key)) {
            is Int -> value
            is Long -> value.toInt()
            else -> fail(key, "an integer", value)
        }

    fun bool(key: String): Boolean = raw(key) as? Boolean ?: fail(key, "true or false", data[key])

    fun string(key: String): String = raw(key) as? String ?: fail(key, "a string", data[key])

    fun stringOrNull(key: String): String? =
        when (val value = raw(key)) {
            null -> null
            is String -> value
            else -> fail(key, "a string or null", value)
        }

    fun device(key: String): String? =
        when (val value = raw(key)) {
            null -> null
            is String -> value
            is Int, is Long -> value.toString()
            else -> fail(key, "a device name, index or null", value)
        }

    fun doubles(key: String): List<Double> = list(key).map { (it as? Number)?.toDouble() ?: fail(key, "a list of numbers", it) }

    fun ints(key: String): List<Int> = list(key).map { (it as? Int) ?: fail(key, "a list of integers", it) }

    fun strings(key: String): List<String> = list(key).map { (it as? String) ?: fail(key, "a list of strings", it) }

    fun doubleMap(key: String): Map<String, Double> {
        val value = raw(key) as? Map<*, *> ?: fail(key, "a mapping", data[key])
        return value.entries.associate { (k, v) ->
            k.toString() to ((v as? Number)?.toDouble() ?: fail("$key.$k", "a number", v))
        }
    }

    fun <T> section(
        key: String,
        factory: YamlSection.() -> T,
    ): T {
        val value = raw(key) as? Map<*, *> ?: fail(key, "a mapping", data[key])
        return YamlSection(value, "$path.$key").factory()
    }

    fun <T> build(block: YamlSection.() -> T): T {
        val result = block()
        val unknown =
            data.keys
                .map { it.toString() }
                .filter { it !in used }
                .sorted()
        if (unknown.isNotEmpty()) throw ConfigException("$path: unknown key(s) $unknown")
        return result
    }

    private fun list(key: String): List<*> = raw(key) as? List<*> ?: fail(key, "a list", data[key])

    private fun fail(
        key: String,
        expected: String,
        value: Any?,
    ): Nothing = throw ConfigException("$path.$key must be $expected, got $value")
}

/** Reads a nested section and rejects any keys the factory did not consume. */
internal fun <T> YamlSection.child(
    key: String,
    factory: YamlSection.() -> T,
): T = section(key) { build { factory() } }
