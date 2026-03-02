package com.optiways.ui.gamification

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.optiways.data.model.UserProfile
import com.optiways.data.repository.AuthRepository
import com.optiways.data.repository.GamificationRepository
import com.optiways.util.Resource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

data class DashboardUiState(
    val isLoading: Boolean = true,
    val currentUser: UserProfile? = null,
    val leaderboard: List<UserProfile> = emptyList()
)

@HiltViewModel
class GamificationViewModel @Inject constructor(
    private val gamificationRepository: GamificationRepository,
    private val authRepository: AuthRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(DashboardUiState())
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()

    init {
        loadCurrentUser()
        observeLeaderboard()
    }

    private fun loadCurrentUser() {
        viewModelScope.launch {
            val uid = authRepository.currentUser?.uid ?: return@launch
            when (val result = authRepository.getUserProfile(uid)) {
                is Resource.Success -> _uiState.update { it.copy(currentUser = result.data) }
                else -> {}
            }
        }
    }

    private fun observeLeaderboard() {
        viewModelScope.launch {
            gamificationRepository.getLeaderboard()
                .catch { /* handle error */ }
                .collect { users ->
                    _uiState.update { it.copy(isLoading = false, leaderboard = users) }
                }
        }
    }
}
