package com.cctr.export.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * 同步 Figma「Quiet Paper & Indigo Ink (v4)」极简桌面/移动端统一色板与字号规范。
 */
object CctrColors {
    val BgCanvas = Color(0xFFF6F7FB)
    val BgSurface = Color(0xFFFFFFFF)
    val BgSubtle = Color(0xFFEEF1F7)
    val BorderHairline = Color(0xFFE2E8F0)
    val InkPrimary = Color(0xFF0F172A)
    val InkSecondary = Color(0xFF475569)
    val InkMuted = Color(0xFF64748B)
    val AccentBlue = Color(0xFF4338CA)
    val AccentSoft = Color(0xFFEEF2FF)
    val Success = Color(0xFF059669)
    val SuccessSoft = Color(0xFFECFDF5)
    val Danger = Color(0xFFDC2626)
    val DangerSoft = Color(0xFFFEF2F2)
}

private val LightColorScheme = lightColorScheme(
    primary = CctrColors.AccentBlue,
    onPrimary = Color.White,
    primaryContainer = CctrColors.AccentSoft,
    onPrimaryContainer = CctrColors.AccentBlue,
    secondary = CctrColors.Success,
    onSecondary = Color.White,
    background = CctrColors.BgCanvas,
    onBackground = CctrColors.InkPrimary,
    surface = CctrColors.BgSurface,
    onSurface = CctrColors.InkPrimary,
    surfaceVariant = CctrColors.BgSubtle,
    onSurfaceVariant = CctrColors.InkSecondary,
    outline = CctrColors.BorderHairline,
    error = CctrColors.Danger
)

private val CctrTypography = Typography(
    titleLarge = TextStyle(fontSize = 19.sp, fontWeight = FontWeight.Bold, color = CctrColors.InkPrimary),
    titleMedium = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary),
    bodyMedium = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Normal, color = CctrColors.InkPrimary),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkSecondary),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Normal, color = CctrColors.InkMuted)
)

@Composable
fun CctrMinimalTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        typography = CctrTypography,
        content = content
    )
}
