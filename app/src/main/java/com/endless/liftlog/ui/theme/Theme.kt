package com.endless.liftlog.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.endless.liftlog.R
import com.endless.liftlog.data.db.MuscleGroup

// Manrope is a variable font: each weight below is one instance of the same file.
val Manrope = FontFamily(
    Font(R.font.manrope, FontWeight.Normal),
    Font(R.font.manrope, FontWeight.Medium),
    Font(R.font.manrope, FontWeight.SemiBold),
    Font(R.font.manrope, FontWeight.Bold),
    Font(R.font.manrope, FontWeight.ExtraBold),
)

/** Colors that Material's scheme doesn't have a slot for. */
@Immutable
data class ExtendedColors(
    /** Card background, lifted off the screen background. */
    val card: Color,
    /** Background for inputs and quiet chips placed on a card. */
    val field: Color,
    val success: Color,
    val onSuccess: Color,
    val successContainer: Color,
    val onSuccessContainer: Color,
    val heroGradient: List<Color>,
    val isDark: Boolean,
)

private val LightExtended = ExtendedColors(
    card = Color.White,
    field = Color(0xFFF0F2F7),
    success = Color(0xFF16A34A),
    onSuccess = Color.White,
    successContainer = Color(0xFFDCFCE7),
    onSuccessContainer = Color(0xFF14532D),
    heroGradient = listOf(Color(0xFF4F46E5), Color(0xFF7C3AED)),
    isDark = false,
)

private val DarkExtended = ExtendedColors(
    card = Color(0xFF171A26),
    field = Color(0xFF222636),
    success = Color(0xFF22C55E),
    onSuccess = Color(0xFF052E16),
    successContainer = Color(0xFF123222),
    onSuccessContainer = Color(0xFFBBF7D0),
    heroGradient = listOf(Color(0xFF4F46E5), Color(0xFF7C3AED)),
    isDark = true,
)

val LocalExtendedColors = staticCompositionLocalOf { LightExtended }

/** `MaterialTheme.extended.card` etc. */
val MaterialTheme.extended: ExtendedColors
    @Composable
    @ReadOnlyComposable
    get() = LocalExtendedColors.current

private val LightColors = lightColorScheme(
    primary = Color(0xFF4F46E5),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE5E4FF),
    onPrimaryContainer = Color(0xFF1E1A6B),
    secondary = Color(0xFF475069),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE6E8F0),
    onSecondaryContainer = Color(0xFF1A1F2E),
    tertiary = Color(0xFFD97706),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFEF3C7),
    onTertiaryContainer = Color(0xFF78350F),
    background = Color(0xFFF3F4F8),
    onBackground = Color(0xFF0F1222),
    surface = Color(0xFFF3F4F8),
    onSurface = Color(0xFF0F1222),
    surfaceVariant = Color(0xFFE6E8F0),
    onSurfaceVariant = Color(0xFF5B6175),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFF8F9FC),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFFFFFFF),
    surfaceContainerHighest = Color(0xFFE6E9F0),
    inverseSurface = Color(0xFF1C2033),
    inverseOnSurface = Color(0xFFF1F2F8),
    outline = Color(0xFFC3C8D6),
    outlineVariant = Color(0xFFE4E7EF),
    error = Color(0xFFDC2626),
    onError = Color.White,
    errorContainer = Color(0xFFFEE2E2),
    onErrorContainer = Color(0xFF7F1D1D),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9C97FF),
    onPrimary = Color(0xFF17135A),
    primaryContainer = Color(0xFF2D2A78),
    onPrimaryContainer = Color(0xFFE3E1FF),
    secondary = Color(0xFFC0C6DA),
    onSecondary = Color(0xFF1A1F2E),
    secondaryContainer = Color(0xFF2A3043),
    onSecondaryContainer = Color(0xFFE2E6F3),
    tertiary = Color(0xFFFBBF24),
    onTertiary = Color(0xFF3B2A00),
    tertiaryContainer = Color(0xFF3D2C07),
    onTertiaryContainer = Color(0xFFFDE68A),
    background = Color(0xFF0B0D14),
    onBackground = Color(0xFFECEEF6),
    surface = Color(0xFF0B0D14),
    onSurface = Color(0xFFECEEF6),
    surfaceVariant = Color(0xFF222636),
    onSurfaceVariant = Color(0xFF9AA1B8),
    surfaceContainerLowest = Color(0xFF080A10),
    surfaceContainerLow = Color(0xFF12141E),
    surfaceContainer = Color(0xFF171A26),
    surfaceContainerHigh = Color(0xFF1E2230),
    surfaceContainerHighest = Color(0xFF282D3F),
    inverseSurface = Color(0xFFE6E8F2),
    inverseOnSurface = Color(0xFF1A1D2A),
    outline = Color(0xFF3D4459),
    outlineVariant = Color(0xFF262B3B),
    error = Color(0xFFF87171),
    onError = Color(0xFF450A0A),
    errorContainer = Color(0xFF4C1515),
    onErrorContainer = Color(0xFFFECACA),
)

private fun style(size: Int, line: Int, weight: FontWeight, tracking: Double = 0.0) = TextStyle(
    fontFamily = Manrope,
    fontWeight = weight,
    fontSize = size.sp,
    lineHeight = line.sp,
    letterSpacing = tracking.sp,
)

private val LiftLogTypography = Typography(
    displayLarge = style(52, 60, FontWeight.ExtraBold, -1.0),
    displayMedium = style(44, 52, FontWeight.ExtraBold, -0.8),
    displaySmall = style(36, 44, FontWeight.ExtraBold, -0.6),
    headlineLarge = style(30, 38, FontWeight.ExtraBold, -0.5),
    headlineMedium = style(26, 34, FontWeight.ExtraBold, -0.4),
    headlineSmall = style(22, 30, FontWeight.Bold, -0.2),
    titleLarge = style(20, 28, FontWeight.Bold, -0.1),
    titleMedium = style(16, 22, FontWeight.Bold),
    titleSmall = style(14, 20, FontWeight.Bold),
    bodyLarge = style(16, 24, FontWeight.Medium),
    bodyMedium = style(14, 20, FontWeight.Medium),
    bodySmall = style(12, 16, FontWeight.Medium),
    labelLarge = style(14, 20, FontWeight.Bold),
    labelMedium = style(12, 16, FontWeight.Bold),
    labelSmall = style(11, 14, FontWeight.Bold, 0.4),
)

private val LiftLogShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(30.dp),
)

/** Tabular (fixed-width) digits so numbers don't jitter while they change. */
val TabularNumbers = TextStyle(fontFeatureSettings = "tnum")

/** A distinct, readable accent per muscle group, used for exercise avatars. */
fun muscleColor(group: MuscleGroup): Color = when (group) {
    MuscleGroup.CHEST -> Color(0xFFEF4444)
    MuscleGroup.BACK -> Color(0xFF3B82F6)
    MuscleGroup.SHOULDERS -> Color(0xFFF97316)
    MuscleGroup.BICEPS -> Color(0xFF8B5CF6)
    MuscleGroup.TRICEPS -> Color(0xFFEC4899)
    MuscleGroup.FOREARMS -> Color(0xFFB45309)
    MuscleGroup.QUADS -> Color(0xFF10B981)
    MuscleGroup.HAMSTRINGS -> Color(0xFF14B8A6)
    MuscleGroup.GLUTES -> Color(0xFFF43F5E)
    MuscleGroup.CALVES -> Color(0xFF06B6D4)
    MuscleGroup.CORE -> Color(0xFFEAB308)
    MuscleGroup.FULL_BODY -> Color(0xFF6366F1)
    MuscleGroup.OTHER -> Color(0xFF64748B)
}

@Composable
fun LiftLogTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    CompositionLocalProvider(LocalExtendedColors provides if (darkTheme) DarkExtended else LightExtended) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColors else LightColors,
            typography = LiftLogTypography,
            shapes = LiftLogShapes,
            content = content,
        )
    }
}
