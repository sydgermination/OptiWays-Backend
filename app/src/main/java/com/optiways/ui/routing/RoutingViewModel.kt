package com.optiways.ui.routing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.location.FusedLocationProviderClient
import com.optiways.data.model.CommuterProfile
import com.optiways.data.model.IncidentReport
import com.optiways.data.model.RouteResponse
import com.optiways.data.model.UserProfile
import com.optiways.data.repository.AuthRepository
import com.optiways.data.repository.IncidentRepository
import com.optiways.data.repository.RouteRepository
import com.optiways.util.Constants
import com.optiways.util.Resource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

data class RoutingUiState(
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val routeResult: RouteResponse? = null,
    val selectedProfile: CommuterProfile = CommuterProfile.DEFAULT,
    val userProfile: UserProfile? = null,
    val nearbyReports: List<IncidentReport> = emptyList(),
    val originLat: Double = Constants.PH_CENTER_LAT,
    val originLng: Double = Constants.PH_CENTER_LNG,
    val destLat: Double = 0.0,
    val destLng: Double = 0.0,
    val originLabel: String = "",
    val destLabel: String = ""
)

@HiltViewModel
class RoutingViewModel @Inject constructor(
    private val routeRepository: RouteRepository,
    private val authRepository: AuthRepository,
    private val incidentRepository: IncidentRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(RoutingUiState())
    val uiState: StateFlow<RoutingUiState> = _uiState.asStateFlow()

    init {
        loadUserProfile()
        observeNearbyReports()
    }

    private fun loadUserProfile() {
        viewModelScope.launch {
            val uid = authRepository.currentUser?.uid ?: return@launch
            when (val result = authRepository.getUserProfile(uid)) {
                is Resource.Success -> {
                    val profile = result.data
                    val commuterProfile = CommuterProfile.values()
                        .find { it.apiKey == profile.preferredProfile } ?: CommuterProfile.DEFAULT
                    _uiState.update {
                        it.copy(userProfile = profile, selectedProfile = commuterProfile)
                    }
                }
                else -> {}
            }
        }
    }

    private fun observeNearbyReports() {
        viewModelScope.launch {
            _uiState.collectLatest { state ->
                incidentRepository.getVerifiedReportsNearby(state.originLat, state.originLng)
                    .collect { reports ->
                        _uiState.update { it.copy(nearbyReports = reports) }
                    }
            }
        }
    }

    fun setCommuterProfile(profile: CommuterProfile) {
        _uiState.update { it.copy(selectedProfile = profile) }
        viewModelScope.launch {
            authRepository.currentUser?.uid?.let { uid ->
                authRepository.updateCommuterProfile(uid, profile.apiKey)
            }
        }
    }

    fun setOrigin(lat: Double, lng: Double, label: String) {
        _uiState.update { it.copy(originLat = lat, originLng = lng, originLabel = label) }
    }

    fun setDestination(lat: Double, lng: Double, label: String) {
        _uiState.update { it.copy(destLat = lat, destLng = lng, destLabel = label) }
    }

    fun searchRoute() {
        val state = _uiState.value
        if (state.destLat == 0.0 && state.destLng == 0.0) {
            _uiState.update { it.copy(errorMessage = "Please select a destination") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null, routeResult = null) }
            val result = routeRepository.getRoute(
                originLat = state.originLat,
                originLng = state.originLng,
                destLat = state.destLat,
                destLng = state.destLng,
                profile = state.selectedProfile.apiKey,
                isStudent = state.userProfile?.isStudent ?: false,
                isPwd = state.userProfile?.isPwd ?: false
            )
            when (result) {
                is Resource.Success -> _uiState.update { it.copy(isLoading = false, routeResult = result.data) }
                is Resource.Error   -> _uiState.update { it.copy(isLoading = false, errorMessage = result.message) }
                else -> {}
            }
        }
    }

    fun clearRoute() = _uiState.update { it.copy(routeResult = null, errorMessage = null) }

    fun logout() = authRepository.logout()
}
