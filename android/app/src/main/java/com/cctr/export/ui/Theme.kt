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
 * Editorial Atelier（瑞士印务工坊 · 纸墨与精密仪器美学）统一色彩与排印规范。
 */
object CctrColors {
    val BgCanvas = Color(0xFFF4F3EF)      // 典藏石纹底框
    val BgSurface = Color(0xFFFFFFFF)     // 纯白印张表层
    val BgSheetSoft = Color(0xFFFAF9F6)   // 柔光米白纸面
    val BgSubtle = Color(0xFFEAE7E0)      // 凹槽轨道底座
    val BorderHairline = Color(0xFFE2DFD7)
    val LineStrong = Color(0xFFCBC7BD)

    val InkPrimary = Color(0xFF141413)    // 哑光碳黑（兼作主操作底色）
    val InkSecondary = Color(0xFF57544E)
    val InkMuted = Color(0xFF8A867E)

    val AccentSeal = Color(0xFFC83E2B)    // 校对朱批红
    val AccentSealSoft = Color(0xFFFAF0EE)
    val StatusOk = Color(0xFF1E6B4E)      // 深林墨绿
    val StatusOkSoft = Color(0xFFEDF5F1)
}

private val LightColorScheme = lightColorScheme(
    primary = CctrColors.InkPrimary,
    onPrimary = CctrColors.BgSheetSoft,
    primaryContainer = CctrColors.BgSubtle,
    onPrimaryContainer = CctrColors.InkPrimary,
    secondary = CctrColors.StatusOk,
    onSecondary = Color.White,
    background = CctrColors.BgCanvas,
    onBackground = CctrColors.InkPrimary,
    surface = CctrColors.BgSurface,
    onSurface = CctrColors.InkPrimary,
    surfaceVariant = CctrColors.BgSubtle,
    onSurfaceVariant = CctrColors.InkSecondary,
    outline = CctrColors.BorderHairline,
    error = CctrColors.AccentSeal
)

private val CctrTypography = Typography(
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary),
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
