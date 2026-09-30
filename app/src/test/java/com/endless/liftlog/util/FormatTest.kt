package com.endless.liftlog.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Duration

class FormatTest {
    @Test
    fun weights() {
        assertEquals("100", formatWeight(100.0))
        assertEquals("102.5", formatWeight(102.5))
        assertEquals("71.25", formatWeight(71.25))
        assertEquals("0", formatWeight(0.0))
    }

    @Test
    fun parsing() {
        assertEquals(82.5, parseDecimal("82,5")!!, 0.0)
        assertEquals(82.5, parseDecimal(" 82.5 ")!!, 0.0)
        assertNull(parseDecimal("abc"))
    }

    @Test
    fun clocks() {
        assertEquals("1:30", formatClock(90))
        assertEquals("0:05", formatClock(5))
        assertEquals("1:02:09", formatClock(3729))
    }

    @Test
    fun durations() {
        assertEquals("45 min", formatDuration(Duration.ofMinutes(45)))
        assertEquals("1 h 05 min", formatDuration(Duration.ofMinutes(65)))
    }

    @Test
    fun compact() {
        assertEquals("850", formatCompact(850.0))
        assertEquals("1.5k", formatCompact(1_500.0))
        assertEquals("2k", formatCompact(2_000.0))
        assertEquals("12k", formatCompact(12_300.0))
    }
}
