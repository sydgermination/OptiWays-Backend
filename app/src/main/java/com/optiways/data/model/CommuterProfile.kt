package com.optiways.data.model

import androidx.compose.ui.graphics.Color

enum class CommuterProfile(
    val displayName: String,
    val apiKey: String,
    val description: String,
    val emoji: String
) {
    DEFAULT(
        displayName = "Standard",
        apiKey = "default",
        description = "Fastest route optimized for speed",
        emoji = "🗺️"
    ),
    NIGHT_SHIFT(
        displayName = "Night-Shift (BPO)",
        apiKey = "night_shift",
        description = "Well-lit paths, 24hr terminals, post-2AM safe routes",
        emoji = "🌙"
    ),
    STUDENT(
        displayName = "Student",
        apiKey = "student",
        description = "Lowest fare, 20% discount, university gate stops",
        emoji = "🎓"
    ),
    ACCESSIBLE(
        displayName = "Accessible (PWD/Elderly)",
        apiKey = "accessible",
        description = "No stairs, elevator-only, accessible stations",
        emoji = "♿"
    )
}
