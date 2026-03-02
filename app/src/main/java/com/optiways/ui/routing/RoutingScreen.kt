package com.optiways.ui.routing

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.*
import com.optiways.data.model.CommuterProfile
import com.optiways.data.model.IncidentType
import com.optiways.ui.components.RouteResultCard
import com.optiways.ui.reporting.ReportBottomSheet
import com.optiways.util.Constants

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RoutingScreen(
    onNavigate: (String) -> Unit,
    onOpenDashboard: () -> Unit,
    onLogout: () -> Unit,
    viewModel: RoutingViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    var showReportSheet by remember { mutableStateOf(false) }
    var originText by remember { mutableStateOf("") }
    var destText by remember { mutableStateOf("") }

    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(
            LatLng(uiState.originLat, uiState.originLng),
            Constants.DEFAULT_ZOOM
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("OptiWays", fontWeight = FontWeight.ExtraBold)
                },
                actions = {
                    IconButton(onClick = onOpenDashboard) {
                        Icon(Icons.Default.EmojiEvents, "Dashboard")
                    }
                    IconButton(onClick = onLogout) {
                        Icon(Icons.Default.Logout, "Logout")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        floatingActionButton = {
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                // Report FAB
                FloatingActionButton(
                    onClick = { showReportSheet = true },
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                    contentColor = MaterialTheme.colorScheme.onErrorContainer,
                    modifier = Modifier.size(48.dp),
                    shape = CircleShape
                ) {
                    Icon(Icons.Default.Warning, contentDescription = "Report Incident")
                }
                // Search Route FAB
                ExtendedFloatingActionButton(
                    onClick = viewModel::searchRoute,
                    icon = { Icon(Icons.Default.Search, "Search") },
                    text = { Text("Find Route") },
                    containerColor = MaterialTheme.colorScheme.primary
                )
            }
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            // Google Map
            GoogleMap(
                modifier = Modifier.fillMaxSize(),
                cameraPositionState = cameraPositionState,
                uiSettings = MapUiSettings(zoomControlsEnabled = false)
            ) {
                // Draw route polyline
                uiState.routeResult?.polylinePoints?.let { points ->
                    if (points.size >= 2) {
                        Polyline(
                            points = points.map { LatLng(it.lat, it.lng) },
                            color = MaterialTheme.colorScheme.primary,
                            width = 8f
                        )
                    }
                }

                // Draw incident markers
                uiState.nearbyReports.forEach { report ->
                    Marker(
                        state = MarkerState(
                            position = LatLng(
                                report.location.latitude,
                                report.location.longitude
                            )
                        ),
                        title = report.incidentType.label,
                        snippet = report.description.take(50)
                    )
                }
            }

            // Search Panel (top overlay)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp)
                    .align(Alignment.TopStart)
            ) {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    elevation = CardDefaults.cardElevation(8.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        // Origin
                        OutlinedTextField(
                            value = originText,
                            onValueChange = { originText = it },
                            placeholder = { Text("🟢 Starting point") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            shape = RoundedCornerShape(10.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                unfocusedBorderColor = Color.Transparent,
                                focusedBorderColor = MaterialTheme.colorScheme.primary
                            )
                        )

                        HorizontalDivider(modifier = Modifier.padding(horizontal = 8.dp))

                        // Destination
                        OutlinedTextField(
                            value = destText,
                            onValueChange = { destText = it },
                            placeholder = { Text("🟠 Where to?") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            shape = RoundedCornerShape(10.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                unfocusedBorderColor = Color.Transparent,
                                focusedBorderColor = MaterialTheme.colorScheme.primary
                            )
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Profile Selector
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(CommuterProfile.values()) { profile ->
                        val isSelected = uiState.selectedProfile == profile
                        FilterChip(
                            selected = isSelected,
                            onClick = { viewModel.setCommuterProfile(profile) },
                            label = { Text("${profile.emoji} ${profile.displayName}") },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = MaterialTheme.colorScheme.primary,
                                selectedLabelColor = MaterialTheme.colorScheme.onPrimary
                            )
                        )
                    }
                }
            }

            // Loading indicator
            if (uiState.isLoading) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.Center)
                ) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }
            }

            // Error snackbar
            uiState.errorMessage?.let { error ->
                Snackbar(
                    modifier = Modifier
                        .padding(16.dp)
                        .align(Alignment.BottomStart),
                    action = {
                        TextButton(onClick = viewModel::clearRoute) { Text("Dismiss") }
                    }
                ) { Text(error) }
            }

            // Route Result Card
            AnimatedVisibility(
                visible = uiState.routeResult != null,
                modifier = Modifier.align(Alignment.BottomCenter),
                enter = slideInVertically(initialOffsetY = { it }),
                exit = slideOutVertically(targetOffsetY = { it })
            ) {
                uiState.routeResult?.let { route ->
                    RouteResultCard(
                        route = route,
                        onStartNavigation = { onNavigate(route.routeId) },
                        onDismiss = viewModel::clearRoute
                    )
                }
            }
        }
    }

    // Report bottom sheet
    if (showReportSheet) {
        ReportBottomSheet(
            onDismiss = { showReportSheet = false },
            currentLat = uiState.originLat,
            currentLng = uiState.originLng
        )
    }
}
