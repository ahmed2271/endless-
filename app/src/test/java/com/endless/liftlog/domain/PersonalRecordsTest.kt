package com.endless.liftlog.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class PersonalRecordsTest {

    private var nextId = 1L

    private fun set(session: Long, weight: Double, reps: Int) = PrCandidate(
        setId = nextId++,
        sessionId = session,
        weight = weight,
        reps = reps,
        achievedAt = Instant.ofEpochSecond(nextId * 60),
    )

    @Test
    fun `first session only establishes a baseline`() {
        val sets = listOf(set(1, 60.0, 5), set(1, 80.0, 5), set(1, 100.0, 5))
        assertTrue(PersonalRecords.detect(sets).isEmpty())
    }

    @Test
    fun `heavier weight in a later session is a weight PR`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 102.5, 3))
        val records = PersonalRecords.detect(sets)
        assertEquals(1, records.size)
        assertTrue(records[0].isWeightRecord)
        assertEquals(102.5, records[0].candidate.weight, 0.0)
    }

    @Test
    fun `more reps at the same weight is an estimated 1RM PR only`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 100.0, 6))
        val record = PersonalRecords.detect(sets).single()
        assertFalse(record.isWeightRecord)
        assertTrue(record.isE1rmRecord)
    }

    @Test
    fun `matching the previous best is not a PR`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 100.0, 5), set(3, 90.0, 5))
        assertTrue(PersonalRecords.detect(sets).isEmpty())
    }

    @Test
    fun `each set that beats the running best is flagged`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 102.5, 5), set(2, 105.0, 5), set(2, 100.0, 5))
        val records = PersonalRecords.detect(sets)
        assertEquals(listOf(102.5, 105.0), records.map { it.candidate.weight })
    }

    @Test
    fun `zero-rep sets are ignored`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 200.0, 0))
        assertTrue(PersonalRecords.detect(sets).isEmpty())
    }

    @Test
    fun `best lifts`() {
        val sets = listOf(set(1, 100.0, 5), set(2, 110.0, 1), set(3, 105.0, 5))
        assertEquals(110.0, PersonalRecords.heaviest(sets)!!.weight, 0.0)
        // 105 × 5 → 122.5 beats 110 × 1 → 110.
        assertEquals(105.0, PersonalRecords.bestEstimated(sets)!!.weight, 0.0)
        assertNull(PersonalRecords.heaviest(emptyList()))
    }

    @Test
    fun `epley estimate`() {
        assertEquals(100.0, estimatedOneRepMax(100.0, 1), 1e-9)
        assertEquals(116.666, estimatedOneRepMax(100.0, 5), 1e-3)
        assertEquals(0.0, estimatedOneRepMax(100.0, 0), 0.0)
    }
}
