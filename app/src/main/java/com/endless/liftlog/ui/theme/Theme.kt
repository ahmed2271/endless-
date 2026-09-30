package com.endless.liftlog.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Neutral greys plus a single blue accent. Amber is reserved for personal records.
private val Accent = Color(0xFF2F6BFF)
private val AccentDark = Color(0xFF7FA3FF)
private val Record = Color(0xFFC98A00)
private val RecordDark = Color(0xFFFFC857)

private val LightColors = lightColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE6EDFF),
    onPrimaryContainer = Color(0xFF0A2A80),
    secondary = Color(0xFF3C4250),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFEDEFF3),
    onSecondaryContainer = Color(0xFF1B1F27),
    tertiary = Record,
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFF1CF),
    onTertiaryContainer = Color(0xFF4A3300),
    background = Color.White,
    onBackground = Color(0xFF111418),
    surface = Color.White,
    onSurface = Color(0xFF111418),
    surfaceVariant = Color(0xFFF1F3F6),
    onSurfaceVariant = Color(0xFF626876),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFF7F8FA),
    surfaceContainer = Color(0xFFF3F4F7),
    surfaceContainerHigh = Color(0xFFEDEFF3),
    surfaceContainerHighest = Color(0xFFE6E9EE),
    outline = Color(0xFFC9CDD5),
    outlineVariant = Color(0xFFE4E7EC),
    error = Color(0xFFD93025),
    onError = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = AccentDark,
    onPrimary = Color(0xFF071B52),
    primaryContainer = Color(0xFF1C2A4D),
    onPrimaryContainer = Color(0xFFD9E3FF),
    secondary = Color(0xFFC3C8D2),
    onSecondary = Color(0xFF1B1F27),
    secondaryContainer = Color(0xFF262A31),
    onSecondaryContainer = Color(0xFFE3E6EC),
    tertiary = RecordDark,
    onTertiary = Color(0xFF3B2800),
    tertiaryContainer = Color(0xFF3A2C0A),
    onTertiaryContainer = Color(0xFFFFE3A3),
    background = Color(0xFF0F1114),
    onBackground = Color(0xFFE8EAED),
    surface = Color(0xFF0F1114),
    onSurface = Color(0xFFE8EAED),
    surfaceVariant = Color(0xFF1E2126),
    onSurfaceVariant = Color(0xFF9AA0AB),
    surfaceContainerLowest = Color(0xFF0B0D10),
    surfaceContainerLow = Color(0xFF15181C),
    surfaceContainer = Color(0xFF1A1D22),
    surfaceContainerHigh = Color(0xFF212429),
    surfaceContainerHighest = Color(0xFF2A2E34),
    outline = Color(0xFF454A53),
    outlineVariant = Color(0xFF2C3036),
    error = Color(0xFFFF7A70),
    onError = Color(0xFF3B0A06),
)

private val base = Typography()

private val LiftLogTypography = Typography(
    displaySmall = base.displaySmall.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp),
    headlineMedium = base.headlineMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.25).sp),
    headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
    titleLarge = base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
    titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    titleSmall = base.titleSmall.copy(fontWeight = FontWeight.Medium),
    bodyLarge = base.bodyLarge,
    bodyMedium = base.bodyMedium,
    bodySmall = base.bodySmall,
    labelLarge = base.labelLarge.copy(fontWeight = FontWeight.SemiBold),
    labelMedium = base.labelMedium,
    labelSmall = base.labelSmall.copy(letterSpacing = 0.6.sp),
)

private val LiftLogShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(14.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

/** Tabular (fixed-width) digits so numbers don't jitter while they change. */
val TabularNumbers = TextStyle(fontFeatureSettings = "tnum")

@Composable
fun LiftLogTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = LiftLogTypography,
        shapes = LiftLogShapes,
        content = content,
    )
}
