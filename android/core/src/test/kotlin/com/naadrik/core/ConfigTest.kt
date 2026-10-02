package com.naadrik.core

import com.naadrik.core.config.Config
import com.naadrik.core.config.ConfigException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ConfigTest {
    private val text = TestSupport.configText

    @Test
    fun `shared config loads`() {
        val config = TestSupport.config
        assertEquals(3, config.objects.maxObjects)
        assertEquals(listOf(0, 2, 4, 7, 9), config.pitch.scale)
        assertEquals(1.0, config.priority.classImportance["person"])
        assertTrue(config.instruments.presence.level > 0.0)
    }

    @Test
    fun `unknown key is rejected`() {
        val broken = text.replace("  near_hz: 8.0", "  near_hz: 8.0\n  near_hz_typo: 3")
        val error = assertFailsWith<ConfigException> { Config.parse(broken) }
        assertTrue("config.pulse: unknown key" in error.message!!)
    }

    @Test
    fun `missing key is rejected`() {
        val broken = text.lines().filterNot { it.trimStart().startsWith("duty_cycle:") }.joinToString("\n")
        assertFailsWith<ConfigException> { Config.parse(broken) }
    }

    @Test
    fun `presence cannot be switched off`() {
        val broken = text.replace(Regex("(presence:[\\s\\S]*?level:) [0-9.]+"), "$1 0.0")
        val error = assertFailsWith<ConfigException> { Config.parse(broken) }
        assertTrue("audible" in error.message!!)
    }

    @Test
    fun `wrong type is rejected`() {
        assertFailsWith<ConfigException> { Config.parse(text.replace("sample_rate: 48000", "sample_rate: fast")) }
    }
}
