package com.optiways.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.optiways.ui.auth.AuthScreen
import com.optiways.ui.auth.AuthViewModel
import com.optiways.ui.gamification.DashboardScreen
import com.optiways.ui.navigation.LiveNavigationScreen
import com.optiways.ui.routing.RoutingScreen

@Composable
fun OptiWaysNavGraph(
    navController: NavHostController = rememberNavController()
) {
    val authViewModel: AuthViewModel = hiltViewModel()
    val isLoggedIn by authViewModel.isLoggedIn.collectAsState()

    NavHost(
        navController = navController,
        startDestination = if (isLoggedIn) "home" else "auth"
    ) {
        composable("auth") {
            AuthScreen(
                onAuthSuccess = {
                    navController.navigate("home") {
                        popUpTo("auth") { inclusive = true }
                    }
                }
            )
        }

        composable("home") {
            RoutingScreen(
                onNavigate = { routeId ->
                    navController.navigate("navigation/$routeId")
                },
                onOpenDashboard = {
                    navController.navigate("dashboard")
                },
                onLogout = {
                    navController.navigate("auth") {
                        popUpTo("home") { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = "navigation/{routeId}",
            arguments = listOf(navArgument("routeId") { type = NavType.StringType })
        ) { backStackEntry ->
            val routeId = backStackEntry.arguments?.getString("routeId") ?: ""
            LiveNavigationScreen(
                routeId = routeId,
                onNavigationEnd = { navController.popBackStack() }
            )
        }

        composable("dashboard") {
            DashboardScreen(
                onBack = { navController.popBackStack() }
            )
        }
    }
}
