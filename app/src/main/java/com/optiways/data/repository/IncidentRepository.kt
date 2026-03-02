package com.optiways.data.repository

import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.GeoPoint
import com.google.firebase.firestore.Query
import com.optiways.data.model.IncidentReport
import com.optiways.data.model.ReportStatus
import com.optiways.util.GeoUtils
import com.optiways.util.Resource
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.tasks.await
import java.util.Calendar
import java.util.Date
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class IncidentRepository @Inject constructor(
    private val firestore: FirebaseFirestore
) {
    private val reportsCollection = firestore.collection("incident_reports")

    /** Submit a new incident report */
    suspend fun submitReport(
        reporterId: String,
        reporterName: String,
        reporterTrustScore: Double,
        type: String,
        description: String,
        lat: Double,
        lng: Double,
        locationLabel: String
    ): Resource<String> {
        return try {
            val expiresAt = Calendar.getInstance().apply {
                add(Calendar.HOUR, 2)
            }.time

            // If reporter is trusted, verify immediately
            val initialStatus = if (reporterTrustScore >= 0.7) {
                ReportStatus.VERIFIED.name
            } else {
                ReportStatus.PENDING.name
            }

            val report = IncidentReport(
                reporterId = reporterId,
                reporterName = reporterName,
                reporterTrustScore = reporterTrustScore,
                type = type,
                description = description,
                location = GeoPoint(lat, lng),
                locationLabel = locationLabel,
                status = initialStatus,
                expiresAt = expiresAt
            )

            val docRef = reportsCollection.add(report).await()
            Resource.Success(docRef.id)
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Failed to submit report")
        }
    }

    /** Upvote a report — triggers moderation check */
    suspend fun upvoteReport(reportId: String, userId: String): Resource<Unit> {
        return try {
            val docRef = reportsCollection.document(reportId)

            firestore.runTransaction { transaction ->
                val snapshot = transaction.get(docRef)
                val report = snapshot.toObject(IncidentReport::class.java)!!
                val upvotedBy = report.upvotedBy.toMutableList()

                if (userId in upvotedBy) return@runTransaction // already voted

                upvotedBy.add(userId)
                val newUpvotes = upvotedBy.size

                // Moderation: verify if >= 2 upvotes
                val newStatus = if (newUpvotes >= 2) ReportStatus.VERIFIED.name else report.status

                transaction.update(docRef, mapOf(
                    "upvotedBy" to upvotedBy,
                    "upvotes" to newUpvotes,
                    "status" to newStatus
                ))
            }.await()

            // Award points to reporter if newly verified
            Resource.Success(Unit)
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Failed to upvote")
        }
    }

    /** Get verified reports near a location (within radiusKm) */
    fun getVerifiedReportsNearby(lat: Double, lng: Double, radiusKm: Double = 5.0): Flow<List<IncidentReport>> {
        return callbackFlow {
            val listener = reportsCollection
                .whereEqualTo("status", ReportStatus.VERIFIED.name)
                .whereEqualTo("isActive", true)
                .orderBy("createdAt", Query.Direction.DESCENDING)
                .limit(50)
                .addSnapshotListener { snapshot, error ->
                    if (error != null) {
                        close(error)
                        return@addSnapshotListener
                    }
                    val reports = snapshot?.documents
                        ?.mapNotNull { it.toObject(IncidentReport::class.java) }
                        ?.filter { report ->
                            val distance = GeoUtils.haversineDistance(
                                lat, lng,
                                report.location.latitude,
                                report.location.longitude
                            )
                            distance <= radiusKm
                        } ?: emptyList()
                    trySend(reports)
                }
            awaitClose { listener.remove() }
        }
    }

    /** Get all reports by a specific user */
    fun getUserReports(uid: String): Flow<List<IncidentReport>> = callbackFlow {
        val listener = reportsCollection
            .whereEqualTo("reporterId", uid)
            .orderBy("createdAt", Query.Direction.DESCENDING)
            .addSnapshotListener { snapshot, error ->
                if (error != null) { close(error); return@addSnapshotListener }
                val reports = snapshot?.documents
                    ?.mapNotNull { it.toObject(IncidentReport::class.java) }
                    ?: emptyList()
                trySend(reports)
            }
        awaitClose { listener.remove() }
    }
}
