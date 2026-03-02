package com.optiways.ui.navigation

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.location.*
import com.optiways.data.model.RouteLeg
import com.optiways.data.model.RouteResponse
import com.optiways.util.Constants
import com.optiways.util.GeoUtils
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

data class NavigationUiState(
    val isLoading: Boolean = true,
    val currentLat: Double = Constants.PH_CENTER_LAT,
    val currentLng: Double = Constants.PH_CENTER_LNG,
    val currentStepIndex: Int = 0,
    val route: RouteResponse? = null,
    val distanceToNextStep: Double = 0.0,
    val isArrived: Boolean = false,
    val errorMessage: String? = null
) {
    val currentLeg: RouteLeg? get() = route?.legs?.getOrNull(currentStepIndex)
    val nextLeg: RouteLeg? get() = route?.legs?.getOrNull(currentStepIndex + 1)
    val totalSteps: Int get() = route?.legs?.size ?: 0
    val progressFraction: Float get() = if (totalSteps == 0) 0f else currentStepIndex.toFloat() / totalSteps
}

@HiltViewModel
class NavigationViewModel @Inject constructor(
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(NavigationUiState())
    val uiState: StateFlow<NavigationUiState> = _uiState.asStateFlow()

    private val fusedLocationClient: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(context)

    private val locationRequest = LocationRequest.Builder(
        Priority.PRIORITY_HIGH_ACCURACY,
        Constants.LOCATION_UPDATE_INTERVAL_MS
    ).apply {
        setMinUpdateIntervalMillis(Constants.LOCATION_FASTEST_INTERVAL_MS)
    }.build()

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let { location ->
                onLocationUpdate(location)
            }
        }
    }

    fun setRoute(route: RouteResponse) {
        _uiState.update { it.copy(route = route, isLoading = false) }
        startLocationUpdates()
    }

    @SuppressLint("MissingPermission")
    private fun startLocationUpdates() {
        fusedLocationClient.requestLocationUpdates(locationRequest, locationCallback, null)
    }

    private fun onLocationUpdate(location: Location) {
        val state = _uiState.value
        val currentLeg = state.currentLeg ?: return

        // Calculate distance to the end of the current leg
        val distanceToEnd = GeoUtils.haversineDistance(
            location.latitude, location.longitude,
            currentLeg.toLat, currentLeg.toLng
        ) * 1000 // convert to meters

        // Advance step if within arrival radius
        val newStepIndex = if (distanceToEnd <= Constants.ARRIVAL_RADIUS_METERS) {
            state.currentStepIndex + 1
        } else {
            state.currentStepIndex
        }

        val isArrived = newStepIndex >= state.totalSteps

        _uiState.update {
            it.copy(
                currentLat = location.latitude,
                currentLng = location.longitude,
                distanceToNextStep = distanceToEnd,
                currentStepIndex = if (isArrived) it.currentStepIndex else newStepIndex,
                isArrived = isArrived
            )
        }
    }

    fun stopNavigation() {
        fusedLocationClient.removeLocationUpdates(locationCallback)
    }

    override fun onCleared() {
        super.onCleared()
        stopNavigation()
    }
}
