package com.optiways.data.repository

import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.optiways.data.model.UserProfile
import com.optiways.util.Resource
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.tasks.await
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GamificationRepository @Inject constructor(
    private val firestore: FirebaseFirestore
) {
    companion object {
        const val POINTS_VERIFIED_REPORT = 50
        const val POINTS_UPVOTE_GIVEN = 5
        const val POINTS_ROUTE_COMPLETED = 10
    }

    suspend fun awardPoints(uid: String, points: Int, reason: String): Resource<Unit> {
        return try {
            val profileRef = firestore.collection("user_profiles").document(uid)
            firestore.runTransaction { transaction ->
                val profile = transaction.get(profileRef).toObject(UserProfile::class.java)!!
                val newPoints = profile.points + points
                val newVerified = if (reason == "VERIFIED_REPORT") profile.verifiedReports + 1
                                  else profile.verifiedReports

                // Recalculate trust score (verified_reports / total_reports)
                val newTotal = if (reason == "VERIFIED_REPORT") profile.totalReports + 1
                               else profile.totalReports
                val newTrust = if (newTotal > 0) newVerified.toDouble() / newTotal else 0.0

                transaction.update(profileRef, mapOf(
                    "points" to newPoints,
                    "verifiedReports" to newVerified,
                    "totalReports" to newTotal,
                    "trustScore" to newTrust.coerceIn(0.0, 1.0)
                ))
            }.await()
            Resource.Success(Unit)
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Failed to award points")
        }
    }

    /** Top 20 contributors leaderboard */
    fun getLeaderboard(): Flow<List<UserProfile>> = callbackFlow {
        val listener = firestore.collection("user_profiles")
            .orderBy("points", Query.Direction.DESCENDING)
            .limit(20)
            .addSnapshotListener { snapshot, error ->
                if (error != null) { close(error); return@addSnapshotListener }
                val users = snapshot?.documents
                    ?.mapNotNull { it.toObject(UserProfile::class.java) }
                    ?: emptyList()
                trySend(users)
            }
        awaitClose { listener.remove() }
    }
}
