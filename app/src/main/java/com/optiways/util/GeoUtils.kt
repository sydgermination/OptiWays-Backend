package com.optiways.util

import kotlin.math.*

object GeoUtils {

    /**
     * Haversine formula to calculate distance between two GPS coordinates.
     * Returns distance in kilometers.
     */
    fun haversineDistance(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val earthRadiusKm = 6371.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLng = Math.toRadians(lng2 - lng1)
        val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) *
                sin(dLng / 2).pow(2)
        val c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return earthRadiusKm * c
    }

    /**
     * Format distance for display (e.g. "50m" or "1.2km")
     */
    fun formatDistance(meters: Double): String {
        return if (meters < 1000) "${meters.toInt()}m"
        else String.format("%.1fkm", meters / 1000)
    }

    /**
     * Format duration in minutes to human-readable (e.g. "1 hr 25 min")
     */
    fun formatDuration(minutes: Int): String {
        return if (minutes < 60) "$minutes min"
        else {
            val hours = minutes / 60
            val mins = minutes % 60
            if (mins == 0) "$hours hr" else "$hours hr $mins min"
        }
    }

    /**
     * Format fare in Philippine Peso
     */
    fun formatFare(amount: Double): String = "₱${String.format("%.2f", amount)}"
}
