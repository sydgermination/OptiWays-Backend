package com.optiways.data.model

import com.google.gson.annotations.SerializedName

data class RouteRequest(
    val originLat: Double,
    val originLng: Double,
    val destLat: Double,
    val destLng: Double,
    val profile: String,
    val departureTime: String? = null,
    val isStudent: Boolean = false,
    val isPwd: Boolean = false
)

data class RouteResponse(
    @SerializedName("route_id")        val routeId: String,
    @SerializedName("total_duration")  val totalDurationMinutes: Int,
    @SerializedName("total_fare")      val totalFare: Double,
    @SerializedName("currency")        val currency: String = "PHP",
    @SerializedName("legs")            val legs: List<RouteLeg>,
    @SerializedName("tags")            val tags: List<String>,
    @SerializedName("localized_tips")  val localizedTips: List<String>,
    @SerializedName("polyline_points") val polylinePoints: List<LatLngPoint>,
    @SerializedName("discount_applied")val discountApplied: Double = 0.0,
    @SerializedName("original_fare")   val originalFare: Double = 0.0,
    @SerializedName("transfers")       val transfers: Int = 0
)

data class RouteLeg(
    @SerializedName("step_number")   val stepNumber: Int,
    @SerializedName("instruction")   val instruction: String,
    @SerializedName("mode")          val mode: String,
    @SerializedName("duration_min")  val durationMinutes: Int,
    @SerializedName("fare")          val fare: Double,
    @SerializedName("from_stop")     val fromStop: String,
    @SerializedName("to_stop")       val toStop: String,
    @SerializedName("distance_m")    val distanceMeters: Double,
    @SerializedName("is_accessible") val isAccessible: Boolean = true,
    @SerializedName("is_lit")        val isLit: Boolean = true,
    @SerializedName("is_24hr")       val is24hr: Boolean = false,
    @SerializedName("from_lat")      val fromLat: Double = 0.0,
    @SerializedName("from_lng")      val fromLng: Double = 0.0,
    @SerializedName("to_lat")        val toLat: Double = 0.0,
    @SerializedName("to_lng")        val toLng: Double = 0.0
) {
    val transitMode: TransitMode get() = when (mode.uppercase()) {
        "WALK"       -> TransitMode.WALK
        "JEEPNEY"    -> TransitMode.JEEPNEY
        "UV_EXPRESS" -> TransitMode.UV_EXPRESS
        "BUS"        -> TransitMode.BUS
        "MRT"        -> TransitMode.MRT
        "LRT"        -> TransitMode.LRT
        "TRICYCLE"   -> TransitMode.TRICYCLE
        "P2P"        -> TransitMode.P2P
        else         -> TransitMode.WALK
    }
}

data class LatLngPoint(
    val lat: Double,
    val lng: Double
)

enum class TransitMode(val label: String, val emoji: String, val colorHex: String) {
    WALK("Walk", "🚶", "#4CAF50"),
    JEEPNEY("Jeepney", "🚌", "#FF9800"),
    UV_EXPRESS("UV Express", "🚐", "#2196F3"),
    BUS("Bus", "🚍", "#9C27B0"),
    MRT("MRT", "🚇", "#F44336"),
    LRT("LRT", "🚈", "#009688"),
    TRICYCLE("Tricycle", "🛺", "#FF5722"),
    P2P("P2P Bus", "🚎", "#607D8B")
}
