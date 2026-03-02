package com.optiways.data.remote

import com.optiways.data.model.RouteResponse
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Query

interface CsaApiService {

    @GET("route")
    suspend fun getRoute(
        @Query("origin_lat")      originLat: Double,
        @Query("origin_lng")      originLng: Double,
        @Query("dest_lat")        destLat: Double,
        @Query("dest_lng")        destLng: Double,
        @Query("profile")         profile: String,
        @Query("departure_time")  departureTime: String? = null,
        @Query("is_student")      isStudent: Boolean = false,
        @Query("is_pwd")          isPwd: Boolean = false
    ): Response<RouteResponse>

    @GET("health")
    suspend fun healthCheck(): Response<Map<String, String>>
}
