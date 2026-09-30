package com.endless.liftlog.domain

/**
 * Estimated one-rep max using the Epley formula: `weight × (1 + reps / 30)`.
 * A single rep is taken at face value.
 */
fun estimatedOneRepMax(weight: Double, reps: Int): Double = when {
    reps <= 0 || weight <= 0.0 -> 0.0
    reps == 1 -> weight
    else -> weight * (1.0 + reps / 30.0)
}
