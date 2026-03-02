package com.optiways.data.repository

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import com.google.firebase.firestore.FirebaseFirestore
import com.optiways.data.model.UserProfile
import com.optiways.util.Resource
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.tasks.await
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val auth: FirebaseAuth,
    private val firestore: FirebaseFirestore
) {
    val currentUser: FirebaseUser? get() = auth.currentUser

    val authState: Flow<FirebaseUser?> = callbackFlow {
        val listener = FirebaseAuth.AuthStateListener { trySend(it.currentUser) }
        auth.addAuthStateListener(listener)
        awaitClose { auth.removeAuthStateListener(listener) }
    }

    suspend fun login(email: String, password: String): Resource<FirebaseUser> {
        return try {
            val result = auth.signInWithEmailAndPassword(email, password).await()
            Resource.Success(result.user!!)
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Login failed")
        }
    }

    suspend fun register(email: String, password: String, displayName: String): Resource<FirebaseUser> {
        return try {
            val result = auth.createUserWithEmailAndPassword(email, password).await()
            val user = result.user!!

            // Create user profile in Firestore
            val profile = UserProfile(
                uid = user.uid,
                displayName = displayName,
                email = email
            )
            firestore.collection("user_profiles")
                .document(user.uid)
                .set(profile)
                .await()

            Resource.Success(user)
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Registration failed")
        }
    }

    fun logout() = auth.signOut()

    suspend fun getUserProfile(uid: String): Resource<UserProfile> {
        return try {
            val doc = firestore.collection("user_profiles").document(uid).get().await()
            val profile = doc.toObject(UserProfile::class.java)
            if (profile != null) Resource.Success(profile)
            else Resource.Error("Profile not found")
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Failed to load profile")
        }
    }

    suspend fun updateCommuterProfile(uid: String, profileKey: String) {
        firestore.collection("user_profiles")
            .document(uid)
            .update("preferredProfile", profileKey)
            .await()
    }
}
