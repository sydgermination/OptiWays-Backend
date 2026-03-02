package com.optiways.data.repository

import com.optiways.data.model.RouteResponse
import com.optiways.data.remote.CsaApiService
import com.optiways.util.Resource
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RouteRepository @Inject constructor(
    private val apiService: CsaApiService
) {
    suspend fun getRoute(
        originLat: Double,
        originLng: Double,
        destLat: Double,
        destLng: Double,
        profile: String,
        departureTime: String? = null,
        isStudent: Boolean = false,
        isPwd: Boolean = false
    ): Resource<RouteResponse> {
        return try {
            val response = apiService.getRoute(
                originLat = originLat,
                originLng = originLng,
                destLat = destLat,
                destLng = destLng,
                profile = profile,
                departureTime = departureTime,
                isStudent = isStudent,
                isPwd = isPwd
            )
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Routing failed: ${response.message()}")
            }
        } catch (e: Exception) {
            Resource.Error(e.message ?: "Network error. Check your connection.")
        }
    }
}
