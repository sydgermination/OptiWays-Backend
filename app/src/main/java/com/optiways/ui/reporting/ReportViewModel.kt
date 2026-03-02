package com.optiways.ui.reporting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.optiways.data.model.IncidentType
import com.optiways.data.repository.AuthRepository
import com.optiways.data.repository.GamificationRepository
import com.optiways.data.repository.IncidentRepository
import com.optiways.util.Resource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ReportUiState(
    val isLoading: Boolean = false,
    val isSuccess: Boolean = false,
    val errorMessage: String? = null,
    val selectedType: IncidentType = IncidentType.TRAFFIC
)

@HiltViewModel
class ReportViewModel @Inject constructor(
    private val incidentRepository: IncidentRepository,
    private val authRepository: AuthRepository,
    private val gamificationRepository: GamificationRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReportUiState())
    val uiState: StateFlow<ReportUiState> = _uiState.asStateFlow()

    fun selectType(type: IncidentType) {
        _uiState.update { it.copy(selectedType = type) }
    }

    fun submitReport(
        description: String,
        lat: Double,
        lng: Double,
        locationLabel: String
    ) {
        viewModelScope.launch {
            val user = authRepository.currentUser ?: return@launch
            _uiState.update { it.copy(isLoading = true) }

            // Load trust score first
            val trustScore = when (val profile = authRepository.getUserProfile(user.uid)) {
                is Resource.Success -> profile.data.trustScore
                else -> 0.0
            }

            val result = incidentRepository.submitReport(
                reporterId = user.uid,
                reporterName = user.displayName ?: "Anonymous",
                reporterTrustScore = trustScore,
                type = _uiState.value.selectedType.name,
                description = description,
                lat = lat,
                lng = lng,
                locationLabel = locationLabel
            )

            when (result) {
                is Resource.Success -> {
                    // Award points for submitting (10 pts; 50 awarded on verification)
                    gamificationRepository.awardPoints(user.uid, 10, "SUBMITTED_REPORT")
                    _uiState.update { it.copy(isLoading = false, isSuccess = true) }
                }
                is Resource.Error -> _uiState.update { it.copy(isLoading = false, errorMessage = result.message) }
                else -> {}
            }
        }
    }

    fun upvoteReport(reportId: String) {
        viewModelScope.launch {
            val uid = authRepository.currentUser?.uid ?: return@launch
            incidentRepository.upvoteReport(reportId, uid)
            gamificationRepository.awardPoints(uid, GamificationRepository.POINTS_UPVOTE_GIVEN, "UPVOTE_GIVEN")
        }
    }

    fun reset() = _uiState.update { ReportUiState() }
}
