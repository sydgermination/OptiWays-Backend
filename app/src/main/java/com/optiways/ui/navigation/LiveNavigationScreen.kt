package com.optiways.ui.navigation

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.*
import com.optiways.util.GeoUtils

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveNavigationScreen(
    routeId: String,
    onNavigationEnd: () -> Unit,
    viewModel: NavigationViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(
            LatLng(uiState.currentLat, uiState.currentLng), 17f
        )
    }

    // Follow user's position
    LaunchedEffect(uiState.currentLat, uiState.currentLng) {
        cameraPositionState.position = CameraPosition.fromLatLngZoom(
            LatLng(uiState.currentLat, uiState.currentLng), 17f
        )
    }

    // Arrival dialog
    if (uiState.isArrived) {
        AlertDialog(
            onDismissRequest = {},
            icon = { Text("🎉", fontSize = 40.sp) },
            title = { Text("You've Arrived!", fontWeight = FontWeight.Bold) },
            text = { Text("You have reached your destination. Great commute!") },
            confirmButton = {
                Button(onClick = {
                    viewModel.stopNavigation()
                    onNavigationEnd()
                }) {
                    Text("Done")
                }
            }
        )
    }

    Box(modifier = Modifier.fillMaxSize()) {
        // Map
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = cameraPositionState,
            uiSettings = MapUiSettings(
                zoomControlsEnabled = false,
                myLocationButtonEnabled = true,
                compassEnabled = true
            ),
            properties = MapProperties(isMyLocationEnabled = true)
        ) {
            // Route polyline
            uiState.route?.polylinePoints?.let { points ->
                if (points.size >= 2) {
                    Polyline(
                        points = points.map { LatLng(it.lat, it.lng) },
                        color = MaterialTheme.colorScheme.primary,
                        width = 10f
                    )
                }
            }
        }

        // Top navigation instruction card
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.TopCenter)
                .padding(16.dp)
        ) {
            uiState.currentLeg?.let { leg ->
                Card(
                    shape = RoundedCornerShape(20.dp),
                    elevation = CardDefaults.cardElevation(8.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = leg.transitMode.emoji,
                            fontSize = 36.sp
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = leg.instruction,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimary,
                            textAlign = TextAlign.Center
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            text = GeoUtils.formatDistance(uiState.distanceToNextStep),
                            style = MaterialTheme.typography.displaySmall,
                            fontWeight = FontWeight.ExtraBold,
                            color = MaterialTheme.colorScheme.onPrimary
                        )
                    }
                }
            }

            // Next step preview
            uiState.nextLeg?.let { next ->
                Spacer(Modifier.height(8.dp))
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f)
                    )
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(text = "Then: ", style = MaterialTheme.typography.labelMedium)
                        Text(text = next.transitMode.emoji)
                        Spacer(Modifier.width(6.dp))
                        Text(
                            text = next.instruction,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }

        // Bottom progress panel
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter),
            shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
            elevation = CardDefaults.cardElevation(12.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                // Progress bar
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "Step ${uiState.currentStepIndex + 1} of ${uiState.totalSteps}",
                        style = MaterialTheme.typography.labelMedium
                    )
                    uiState.route?.let { route ->
                        Text(
                            text = GeoUtils.formatDuration(route.totalDurationMinutes),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = uiState.progressFraction,
                    modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.height(16.dp))

                // End navigation button
                OutlinedButton(
                    onClick = {
                        viewModel.stopNavigation()
                        onNavigationEnd()
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Default.Close, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("End Navigation")
                }
            }
        }
    }
}
