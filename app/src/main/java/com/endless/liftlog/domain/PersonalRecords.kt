package com.endless.liftlog.domain

import java.time.Instant

/** A working set considered for PR detection. */
data class PrCandidate(
    val setId: Long,
    val sessionId: Long,
    val weight: Double,
    val reps: Int,
    val achievedAt: Instant,
)

data class DetectedPr(
    val candidate: PrCandidate,
    val estimatedOneRepMax: Double,
    val isWeightRecord: Boolean,
    val isE1rmRecord: Boolean,
)

/** Current best lift for an exercise. */
data class BestLift(
    val weight: Double,
    val reps: Int,
    val achievedAt: Instant,
)

object PersonalRecords {
    private const val EPSILON = 1e-6

    /**
     * Walks an exercise's working sets in the order they were performed and returns every set
     * that beat the best weight or best estimated 1RM seen before it.
     *
     * The first session in which an exercise appears only establishes the baseline, so nothing in
     * it is flagged: a PR has to beat a previous best.
     */
    fun detect(setsInOrder: List<PrCandidate>): List<DetectedPr> {
        val valid = setsInOrder.filter { it.reps > 0 && it.weight >= 0.0 }
        if (valid.isEmpty()) return emptyList()
        val baselineSession = valid.first().sessionId
        var bestWeight = 0.0
        var bestE1rm = 0.0
        val records = mutableListOf<DetectedPr>()
        for (set in valid) {
            val e1rm = estimatedOneRepMax(set.weight, set.reps)
            if (set.sessionId != baselineSession) {
                val weightRecord = set.weight > bestWeight + EPSILON
                val e1rmRecord = e1rm > bestE1rm + EPSILON
                if (weightRecord || e1rmRecord) {
                    records += DetectedPr(set, e1rm, weightRecord, e1rmRecord)
                }
            }
            if (set.weight > bestWeight) bestWeight = set.weight
            if (e1rm > bestE1rm) bestE1rm = e1rm
        }
        return records
    }

    /** Heaviest set (ties broken by more reps, then earliest). */
    fun heaviest(sets: List<PrCandidate>): BestLift? = sets
        .filter { it.reps > 0 }
        .sortedWith(
            compareByDescending<PrCandidate> { it.weight }
                .thenByDescending { it.reps }
                .thenBy { it.achievedAt },
        )
        .firstOrNull()
        ?.let { BestLift(it.weight, it.reps, it.achievedAt) }

    /** Set with the best estimated one-rep max (ties broken by earliest). */
    fun bestEstimated(sets: List<PrCandidate>): BestLift? = sets
        .filter { it.reps > 0 }
        .sortedWith(
            compareByDescending<PrCandidate> { estimatedOneRepMax(it.weight, it.reps) }
                .thenBy { it.achievedAt },
        )
        .firstOrNull()
        ?.let { BestLift(it.weight, it.reps, it.achievedAt) }
}
