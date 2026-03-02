package com.optiways.util

object Constants {
    // Firestore collections
    const val COLLECTION_USERS = "user_profiles"
    const val COLLECTION_REPORTS = "incident_reports"
    const val COLLECTION_ROUTES = "saved_routes"

    // Gamification
    const val TRUST_THRESHOLD = 0.7
    const val UPVOTES_TO_VERIFY = 2
    const val REPORT_EXPIRY_HOURS = 2
    const val NEARBY_RADIUS_KM = 5.0

    // Navigation
    const val LOCATION_UPDATE_INTERVAL_MS = 3000L
    const val LOCATION_FASTEST_INTERVAL_MS = 1000L
    const val ARRIVAL_RADIUS_METERS = 50.0

    // Philippines bounding box
    const val PH_CENTER_LAT = 14.5995
    const val PH_CENTER_LNG = 120.9842
    const val DEFAULT_ZOOM = 13f

    // Nav routes
    const val NAV_AUTH = "auth"
    const val NAV_HOME = "home"
    const val NAV_ROUTING = "routing"
    const val NAV_NAVIGATION = "navigation/{routeId}"
    const val NAV_DASHBOARD = "dashboard"
    const val NAV_PROFILE = "profile"
}
