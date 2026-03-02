package com.optiways.data.model

import com.google.firebase.firestore.DocumentId
import com.google.firebase.firestore.ServerTimestamp
import java.util.Date

data class UserProfile(
    @DocumentId
    val uid: String = "",
    val displayName: String = "",
    val email: String = "",
    val photoUrl: String = "",
    val preferredProfile: String = CommuterProfile.DEFAULT.apiKey,
    val isStudent: Boolean = false,
    val isPwd: Boolean = false,

    // Gamification
    val points: Int = 0,
    val trustScore: Double = 0.0,       // 0.0–1.0; trusted if > 0.7
    val verifiedReports: Int = 0,
    val totalReports: Int = 0,
    val helpfulVotes: Int = 0,

    @ServerTimestamp
    val createdAt: Date? = null,

    @ServerTimestamp
    val lastActiveAt: Date? = null
) {
    val rank: UserRank get() = when {
        points >= 5000 -> UserRank.OPTIMASTER
        points >= 2000 -> UserRank.PATHFINDER
        points >= 500  -> UserRank.NAVIGATOR
        else           -> UserRank.COMMUTER
    }

    val isTrusted: Boolean get() = trustScore >= 0.7 || verifiedReports >= 10
}

enum class UserRank(
    val label: String,
    val emoji: String,
    val minPoints: Int,
    val badgeColor: String
) {
    COMMUTER("Commuter", "🚶", 0, "#78909C"),
    NAVIGATOR("Navigator", "🧭", 500, "#42A5F5"),
    PATHFINDER("PathFinder", "🗺️", 2000, "#AB47BC"),
    OPTIMASTER("OptiMaster", "⭐", 5000, "#FFA726")
}
