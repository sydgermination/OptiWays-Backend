package com.optiways.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// OptiWays brand colors — inspired by Philippine flag blue & red with modern transit palette
val OptiBlue = Color(0xFF1565C0)
val OptiBlueLight = Color(0xFF1E88E5)
val OptiBlueDark = Color(0xFF0D47A1)
val OptiOrange = Color(0xFFFF6D00)
val OptiOrangeLight = Color(0xFFFF9100)
val OptiGold = Color(0xFFFFD600)
val OptiGreen = Color(0xFF2E7D32)
val OptiRed = Color(0xFFC62828)

val OptiSurface = Color(0xFFF8FAFB)
val OptiBackground = Color(0xFFEEF2F7)
val OptiSurfaceDark = Color(0xFF1A1D23)
val OptiBackgroundDark = Color(0xFF111318)

private val LightColorScheme = lightColorScheme(
    primary = OptiBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD6E4FF),
    onPrimaryContainer = OptiBlueDark,
    secondary = OptiOrange,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFFFE0B2),
    onSecondaryContainer = Color(0xFF7A3800),
    tertiary = OptiGreen,
    onTertiary = Color.White,
    background = OptiBackground,
    onBackground = Color(0xFF1A1D23),
    surface = OptiSurface,
    onSurface = Color(0xFF1A1D23),
    surfaceVariant = Color(0xFFE3EAF4),
    onSurfaceVariant = Color(0xFF44474F),
    error = OptiRed,
    onError = Color.White
)

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF90B4FF),
    onPrimary = Color(0xFF002E6D),
    primaryContainer = OptiBlueDark,
    onPrimaryContainer = Color(0xFFD6E4FF),
    secondary = OptiOrangeLight,
    onSecondary = Color(0xFF4A1800),
    secondaryContainer = Color(0xFF7A3800),
    onSecondaryContainer = Color(0xFFFFDBCA),
    tertiary = Color(0xFF6FCF6F),
    onTertiary = Color(0xFF003A00),
    background = OptiBackgroundDark,
    onBackground = Color(0xFFE2E2E9),
    surface = OptiSurfaceDark,
    onSurface = Color(0xFFE2E2E9),
    surfaceVariant = Color(0xFF252932),
    onSurfaceVariant = Color(0xFFC4C7D0),
    error = Color(0xFFFF8A8A),
    onError = Color(0xFF690005)
)

@Composable
fun OptiWaysTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.primary.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = OptiWaysTypography,
        content = content
    )
}
