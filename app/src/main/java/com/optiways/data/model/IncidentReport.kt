package com.optiways.data.model

import com.google.firebase.firestore.DocumentId
import com.google.firebase.firestore.GeoPoint
import com.google.firebase.firestore.ServerTimestamp
import java.util.Date

data class IncidentReport(
    @DocumentId
    val reportId: String = "",
    val reporterId: String = "",
    val reporterName: String = "",
    val reporterTrustScore: Double = 0.0,
    val type: String = IncidentType.TRAFFIC.name,
    val description: String = "",
    val location: GeoPoint = GeoPoint(0.0, 0.0),
    val locationLabel: String = "",

    // Moderation
    val status: String = ReportStatus.PENDING.name,
    val upvotes: Int = 0,
    val upvotedBy: List<String> = emptyList(),
    val downvotes: Int = 0,
    val downvotedBy: List<String> = emptyList(),

    @ServerTimestamp
    val createdAt: Date? = null,
    val expiresAt: Date? = null,
    val isActive: Boolean = true
) {
    val incidentType: IncidentType get() =
        IncidentType.values().find { it.name == type } ?: IncidentType.TRAFFIC

    val reportStatus: ReportStatus get() =
        ReportStatus.values().find { it.name == status } ?: ReportStatus.PENDING
}

enum class IncidentType(
    val label: String,
    val emoji: String,
    val description: String
) {
    ROAD_CRASH(
        label = "Road Crash",
        emoji = "🚨",
        description = "Vehicle collision or accident"
    ),
    ROAD_CLOSURE(
        label = "Road Closure",
        emoji = "🚧",
        description = "Road blocked or closed"
    ),
    TRAFFIC(
        label = "Heavy Traffic",
        emoji = "🚗",
        description = "Unusually heavy traffic congestion"
    ),
    TRAIN_DELAY(
        label = "Train Delay",
        emoji = "🚆",
        description = "MRT/LRT service delay or stoppage"
    )
}

enum class ReportStatus(val label: String) {
    PENDING("Pending"),        // Not yet visible to others
    VERIFIED("Verified"),      // ≥2 upvotes OR trusted reporter
    REJECTED("Rejected"),      // Flagged as false
    EXPIRED("Expired")         // Auto-expired after 2 hours
}
