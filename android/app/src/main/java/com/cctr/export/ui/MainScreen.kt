package com.cctr.export.ui

import android.content.Context
import android.content.Intent
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.cctr.export.core.AnswerVariant
import com.cctr.export.core.ExportFormat
import com.cctr.export.core.PracticeItem
import java.io.File

@Composable
fun MainScreen(vm: MainViewModel) {
    val state by vm.state.collectAsState()
    val navTabs = listOf(
        Triple(0, "01", "工作台"),
        Triple(1, "02", "审校日志"),
        Triple(2, "03", "本地归档")
    )

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(CctrColors.BgCanvas)
    ) {
        val isTablet = maxWidth >= 600.dp
        val isExpanded = maxWidth >= 840.dp

        if (isTablet) {
            Row(modifier = Modifier.fillMaxSize()) {
                AtelierTabletRail(
                    vm = vm,
                    state = state,
                    navTabs = navTabs,
                    railWidth = if (isExpanded) 204.dp else 172.dp
                )
                Box(
                    modifier = Modifier
                        .width(1.dp)
                        .fillMaxHeight()
                        .background(CctrColors.BorderHairline)
                )
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .statusBarsPadding()
                        .navigationBarsPadding()
                ) {
                    if (state.activeTab == 0) {
                        AtelierStepperStrip(vm = vm, state = state, showSpec = isExpanded)
                    }
                    Box(
                        contentAlignment = Alignment.TopCenter,
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .imePadding()
                    ) {
                        MainStageBody(vm, state, isTablet = true, isExpanded = isExpanded)
                    }
                }
            }
        } else {
            Column(modifier = Modifier.fillMaxSize()) {
                AtelierPhoneTopBar(vm = vm, state = state)
                if (state.activeTab == 0) {
                    AtelierStepperStrip(vm = vm, state = state, showSpec = false)
                }
                Box(
                    contentAlignment = Alignment.TopCenter,
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .imePadding()
                ) {
                    MainStageBody(vm, state, isTablet = false, isExpanded = false)
                }
                AtelierPhoneBottomBar(vm = vm, state = state, navTabs = navTabs)
            }
        }
    }
}

@Composable
private fun MainStageBody(vm: MainViewModel, state: MainUiState, isTablet: Boolean, isExpanded: Boolean) {
    when (state.activeTab) {
        0 -> WorkspaceStage(vm, state, isTablet = isTablet, isExpanded = isExpanded)
        1 -> AuditLogsStage(vm, state, isTablet = isTablet)
        else -> ArchiveFilesStage(state, isTablet = isTablet)
    }
}

/* ── Custom Architectural Shell Components ──────────────────────────────── */

@Composable
private fun AtelierRegistrationMark(modifier: Modifier = Modifier.size(18.dp), color: Color = CctrColors.InkPrimary) {
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val sw = 1.5.dp.toPx()
        val leg = w * 0.24f
        val pad = w * 0.1f

        // 4 corner crop marks
        drawLine(color, Offset(pad, pad), Offset(pad + leg, pad), sw, StrokeCap.Square)
        drawLine(color, Offset(pad, pad), Offset(pad, pad + leg), sw, StrokeCap.Square)

        drawLine(color, Offset(w - pad, pad), Offset(w - pad - leg, pad), sw, StrokeCap.Square)
        drawLine(color, Offset(w - pad, pad), Offset(w - pad, pad + leg), sw, StrokeCap.Square)

        drawLine(color, Offset(pad, h - pad), Offset(pad + leg, h - pad), sw, StrokeCap.Square)
        drawLine(color, Offset(pad, h - pad), Offset(pad, h - pad - leg), sw, StrokeCap.Square)

        drawLine(color, Offset(w - pad, h - pad), Offset(w - pad - leg, h - pad), sw, StrokeCap.Square)
        drawLine(color, Offset(w - pad, h - pad), Offset(w - pad, h - pad - leg), sw, StrokeCap.Square)

        // Center crosshair
        val cSpan = w * 0.22f
        drawLine(color, Offset(w / 2f, h / 2f - cSpan), Offset(w / 2f, h / 2f + cSpan), sw)
        drawLine(color, Offset(w / 2f - cSpan, h / 2f), Offset(w / 2f + cSpan, h / 2f), sw)
    }
}

@Composable
private fun AtelierTabletRail(
    vm: MainViewModel,
    state: MainUiState,
    navTabs: List<Triple<Int, String, String>>,
    railWidth: Dp
) {
    Column(
        modifier = Modifier
            .width(railWidth)
            .fillMaxHeight()
            .background(CctrColors.BgSurface)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AtelierRegistrationMark(Modifier.size(16.dp))
                Text("融智印务台", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
            }
            Text("A4 TYPESETTING", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted, letterSpacing = 0.8.sp)
        }
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))

        Spacer(Modifier.height(10.dp))
        navTabs.forEach { (idx, code, label) ->
            val selected = state.activeTab == idx
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp)
                    .background(if (selected) CctrColors.BgSheetSoft else Color.Transparent)
                    .clickable { vm.setTab(idx) }
            ) {
                Box(
                    modifier = Modifier
                        .width(3.dp)
                        .height(22.dp)
                        .background(if (selected) CctrColors.InkPrimary else Color.Transparent)
                )
                Spacer(Modifier.width(13.dp))
                Text(
                    text = code,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = if (selected) CctrColors.InkPrimary else CctrColors.InkMuted,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal
                )
                Spacer(Modifier.width(9.dp))
                Text(
                    text = label,
                    fontSize = 13.sp,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
                    color = if (selected) CctrColors.InkPrimary else CctrColors.InkSecondary,
                    modifier = Modifier.weight(1f)
                )
                if (idx == 2 && state.savedFiles.isNotEmpty()) {
                    Surface(
                        color = CctrColors.BgSubtle,
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier.padding(end = 12.dp)
                    ) {
                        Text(
                            text = state.savedFiles.size.toString(),
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.SemiBold,
                            color = CctrColors.InkSecondary,
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp)
                        )
                    }
                }
            }
        }

        Spacer(Modifier.weight(1f))
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))

        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (state.practices.isNotEmpty()) {
                Surface(
                    color = CctrColors.StatusOkSoft,
                    border = BorderStroke(1.dp, CctrColors.StatusOk.copy(alpha = 0.28f)),
                    shape = RoundedCornerShape(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Box(modifier = Modifier.size(6.dp).background(CctrColors.StatusOk, CircleShape))
                            Text(state.username, fontSize = 11.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold, color = CctrColors.StatusOk, maxLines = 1)
                        }
                        Text(
                            text = "断开当前会话",
                            fontSize = 11.sp,
                            color = CctrColors.InkSecondary,
                            modifier = Modifier.clickable { vm.signOut() }
                        )
                    }
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("识别引擎", fontSize = 10.sp, color = CctrColors.InkMuted)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(modifier = Modifier.size(6.dp).background(CctrColors.StatusOk, CircleShape))
                    Text("ONNX 离线就绪", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkPrimary)
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("归档目录", fontSize = 10.sp, color = CctrColors.InkMuted)
                Text("Download/CCTRExport", fontSize = 10.5.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun AtelierPhoneTopBar(vm: MainViewModel, state: MainUiState) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(CctrColors.BgSurface)
            .statusBarsPadding()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
                .padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                AtelierRegistrationMark(Modifier.size(16.dp))
                Text(
                    text = when (state.activeTab) {
                        0 -> "融智云考 · 印务台"
                        1 -> "审校日志"
                        else -> "本地归档"
                    },
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = CctrColors.InkPrimary
                )
            }
            if (state.practices.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Surface(
                        color = CctrColors.StatusOkSoft,
                        border = BorderStroke(1.dp, CctrColors.StatusOk.copy(alpha = 0.25f)),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(5.dp),
                            modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp)
                        ) {
                            Box(modifier = Modifier.size(5.dp).background(CctrColors.StatusOk, CircleShape))
                            Text(state.username, fontSize = 10.5.sp, fontFamily = FontFamily.Monospace, color = CctrColors.StatusOk, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    Text(
                        text = "断开",
                        fontSize = 12.sp,
                        color = CctrColors.InkSecondary,
                        modifier = Modifier.clickable { vm.signOut() }.padding(horizontal = 4.dp, vertical = 4.dp)
                    )
                }
            } else {
                Surface(
                    color = CctrColors.BgSheetSoft,
                    border = BorderStroke(1.dp, CctrColors.BorderHairline),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(5.dp),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Box(modifier = Modifier.size(5.dp).background(CctrColors.StatusOk, CircleShape))
                        Text("ONNX 就绪", fontSize = 10.5.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary)
                    }
                }
            }
        }
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
    }
}

@Composable
private fun AtelierPhoneBottomBar(
    vm: MainViewModel,
    state: MainUiState,
    navTabs: List<Triple<Int, String, String>>
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(CctrColors.BgSurface)
            .navigationBarsPadding()
    ) {
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
        Row(modifier = Modifier.fillMaxWidth().height(52.dp)) {
            navTabs.forEach { (idx, code, label) ->
                val selected = state.activeTab == idx
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .clickable { vm.setTab(idx) },
                    contentAlignment = Alignment.Center
                ) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .width(42.dp)
                            .height(2.dp)
                            .background(if (selected) CctrColors.InkPrimary else Color.Transparent)
                    )
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(
                            text = code,
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            color = if (selected) CctrColors.InkPrimary else CctrColors.InkMuted
                        )
                        Text(
                            text = label,
                            fontSize = 12.5.sp,
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                            color = if (selected) CctrColors.InkPrimary else CctrColors.InkSecondary
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AtelierStepperStrip(vm: MainViewModel, state: MainUiState, showSpec: Boolean) {
    val steps = listOf(
        Triple(1, "01", "身份接入"),
        Triple(2, "02", "课程遴选"),
        Triple(3, "03", "版式付印")
    )
    Column(modifier = Modifier.fillMaxWidth().background(CctrColors.BgSheetSoft)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(40.dp)
                .padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp), modifier = Modifier.fillMaxHeight()) {
                steps.forEach { (step, num, title) ->
                    val active = state.wizardStep == step
                    val done = (step == 1 && state.practices.isNotEmpty() && state.wizardStep > 1) ||
                        (step < state.wizardStep)
                    val enabled = step == 1 || (step == 2 && state.practices.isNotEmpty()) ||
                        (step == 3 && state.practices.isNotEmpty() && state.selectedPracticeIds.isNotEmpty())
                    Box(
                        modifier = Modifier
                            .fillMaxHeight()
                            .alpha(if (enabled) 1f else 0.4f)
                            .clickable(enabled = enabled) { vm.setWizardStep(step) },
                        contentAlignment = Alignment.Center
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(
                                text = num,
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                                color = when {
                                    active -> CctrColors.InkPrimary
                                    done -> CctrColors.StatusOk
                                    else -> CctrColors.InkMuted
                                },
                                fontWeight = FontWeight.Medium
                            )
                            Text(
                                text = title,
                                fontSize = 12.5.sp,
                                fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
                                color = if (active) CctrColors.InkPrimary else CctrColors.InkSecondary
                            )
                        }
                        if (active) {
                            Box(
                                modifier = Modifier
                                    .align(Alignment.BottomCenter)
                                    .width(58.dp)
                                    .height(2.dp)
                                    .background(CctrColors.InkPrimary)
                            )
                        }
                    }
                }
            }
            if (showSpec) {
                Text(
                    text = "A4 · 18mm / 10.5pt",
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = CctrColors.InkMuted
                )
            }
        }
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
    }
}

/* ── Custom Atelier UI Primitives ───────────────────────────────────────── */

@Composable
private fun AtelierTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    placeholder: String,
    isPassword: Boolean = false,
    monospace: Boolean = false,
    modifier: Modifier = Modifier.fillMaxWidth(),
    trailing: (@Composable () -> Unit)? = null
) {
    var focused by remember { mutableStateOf(false) }
    var showSecret by remember { mutableStateOf(false) }

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(5.dp)) {
        if (label.isNotEmpty()) {
            Text(label, fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkSecondary)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .height(42.dp)
                .background(CctrColors.BgSurface, RoundedCornerShape(6.dp))
                .border(
                    width = 1.dp,
                    color = if (focused) CctrColors.InkPrimary else CctrColors.LineStrong,
                    shape = RoundedCornerShape(6.dp)
                )
                .padding(horizontal = 12.dp)
        ) {
            Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                if (value.isEmpty()) {
                    Text(placeholder, fontSize = 13.sp, color = CctrColors.InkMuted, maxLines = 1)
                }
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    singleLine = true,
                    cursorBrush = SolidColor(CctrColors.InkPrimary),
                    textStyle = TextStyle(
                        color = CctrColors.InkPrimary,
                        fontSize = if (monospace) 14.sp else 13.sp,
                        fontFamily = if (monospace) FontFamily.Monospace else FontFamily.Default,
                        fontWeight = if (monospace) FontWeight.SemiBold else FontWeight.Normal,
                        letterSpacing = if (monospace) 2.sp else 0.sp
                    ),
                    visualTransformation = if (isPassword && !showSecret) PasswordVisualTransformation() else VisualTransformation.None,
                    modifier = Modifier
                        .fillMaxWidth()
                        .onFocusChanged { focused = it.isFocused }
                        .semantics { contentDescription = label.ifEmpty { placeholder } }
                )
            }
            if (isPassword) {
                Spacer(Modifier.width(8.dp))
                Text(
                    text = if (showSecret) "隐藏" else "显示",
                    fontSize = 11.sp,
                    color = CctrColors.InkMuted,
                    modifier = Modifier.clickable { showSecret = !showSecret }.padding(horizontal = 4.dp, vertical = 4.dp)
                )
            }
            if (trailing != null) {
                Spacer(Modifier.width(8.dp))
                trailing()
            }
        }
    }
}

@Composable
private fun AtelierPrimaryButton(
    text: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    loading: Boolean = false,
    modifier: Modifier = Modifier.fillMaxWidth()
) {
    Surface(
        color = if (enabled) CctrColors.InkPrimary else CctrColors.InkPrimary.copy(alpha = 0.42f),
        shape = RoundedCornerShape(6.dp),
        modifier = modifier
            .height(42.dp)
            .clickable(enabled = enabled, onClick = onClick)
    ) {
        Row(
            modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            if (loading) {
                CircularProgressIndicator(color = CctrColors.BgSheetSoft, modifier = Modifier.size(16.dp), strokeWidth = 1.8.dp)
                Spacer(Modifier.width(8.dp))
            }
            Text(text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.BgSheetSoft, maxLines = 1)
        }
    }
}

@Composable
private fun AtelierGhostButton(
    text: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    modifier: Modifier = Modifier
) {
    Surface(
        color = CctrColors.BgSurface,
        border = BorderStroke(1.dp, CctrColors.LineStrong),
        shape = RoundedCornerShape(6.dp),
        modifier = modifier
            .height(42.dp)
            .alpha(if (enabled) 1f else 0.45f)
            .clickable(enabled = enabled, onClick = onClick)
    ) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(horizontal = 14.dp)) {
            Text(text, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkPrimary, maxLines = 1)
        }
    }
}

@Composable
private fun AtelierSquareCheck(checked: Boolean) {
    Surface(
        color = if (checked) CctrColors.InkPrimary else CctrColors.BgSurface,
        border = if (checked) null else BorderStroke(1.4.dp, CctrColors.LineStrong),
        shape = RoundedCornerShape(3.dp),
        modifier = Modifier.size(16.dp)
    ) {
        if (checked) {
            Canvas(modifier = Modifier.fillMaxSize().padding(3.dp)) {
                val p = Path().apply {
                    moveTo(size.width * 0.1f, size.height * 0.55f)
                    lineTo(size.width * 0.42f, size.height * 0.85f)
                    lineTo(size.width * 0.92f, size.height * 0.2f)
                }
                drawPath(
                    path = p,
                    color = CctrColors.BgSheetSoft,
                    style = Stroke(width = 1.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
                )
            }
        }
    }
}

@Composable
private fun AtelierSegmentedRow(
    labels: List<String>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit
) {
    Surface(
        color = CctrColors.BgSubtle,
        shape = RoundedCornerShape(7.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(modifier = Modifier.padding(3.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            labels.forEachIndexed { idx, lbl ->
                val sel = idx == selectedIndex
                Surface(
                    color = if (sel) CctrColors.BgSurface else Color.Transparent,
                    border = if (sel) BorderStroke(1.dp, CctrColors.BorderHairline) else null,
                    shape = RoundedCornerShape(5.dp),
                    modifier = Modifier.weight(1f).height(34.dp).clickable { onSelect(idx) }
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = lbl,
                            fontSize = 12.sp,
                            fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Normal,
                            color = if (sel) CctrColors.InkPrimary else CctrColors.InkSecondary,
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AtelierSwitchRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    val thumbOffset by animateDpAsState(targetValue = if (checked) 14.dp else 0.dp, label = "switchThumb")
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onCheckedChange(!checked) }
            .padding(vertical = 10.dp)
    ) {
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkPrimary)
            Text(subtitle, fontSize = 11.sp, color = CctrColors.InkMuted)
        }
        Box(
            modifier = Modifier
                .width(34.dp)
                .height(20.dp)
                .clip(RoundedCornerShape(999.dp))
                .background(if (checked) CctrColors.InkPrimary else CctrColors.LineStrong)
                .padding(2.dp)
        ) {
            Box(
                modifier = Modifier
                    .offset(x = thumbOffset)
                    .size(16.dp)
                    .background(CctrColors.BgSurface, CircleShape)
            )
        }
    }
}

/* ── Workspace Stage (3 Steps) ──────────────────────────────────────────── */

@Composable
private fun WorkspaceStage(vm: MainViewModel, state: MainUiState, isTablet: Boolean, isExpanded: Boolean) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = if (isTablet) 24.dp else 14.dp, vertical = if (isTablet) 22.dp else 16.dp)
    ) {
        when (state.wizardStep) {
            1 -> AuthStepView(vm, state, isExpanded = isExpanded)
            2 -> PracticePickerView(vm, state, isTablet = isTablet)
            else -> ExportBenchView(vm, state, isTablet = isTablet, isExpanded = isExpanded)
        }
    }
}

@Composable
private fun AuthStepView(vm: MainViewModel, state: MainUiState, isExpanded: Boolean) {
    if (isExpanded) {
        Row(
            modifier = Modifier.widthIn(max = 940.dp).fillMaxWidth().padding(top = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(44.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1.05f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("ISO 216 · A4 TYPESETTING", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted, letterSpacing = 0.8.sp)
                Text("无损题库印务与排版系统", fontSize = 26.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                Text(
                    "直连校内题库并逐题校验完整性，剥离 Word 智能标签与杂乱样式，按 10.5pt 标准生成印刷级 A4 讲义与分类归档。",
                    fontSize = 13.sp,
                    lineHeight = 20.sp,
                    color = CctrColors.InkSecondary
                )
                Spacer(Modifier.height(6.dp))
                Column(modifier = Modifier.fillMaxWidth()) {
                    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                    SpecLedgerLine("01", "版面基准", "ISO A4 · 四周 18 mm 留白")
                    SpecLedgerLine("02", "字号公式", "10.5pt 正文 · Wiris 0.86x")
                    SpecLedgerLine("03", "端侧能力", "ONNX 离线识码 · 防隔页分页")
                }
            }
            AtelierAuthSheet(vm, state, modifier = Modifier.width(400.dp))
        }
    } else {
        Column(
            modifier = Modifier.widthIn(max = 440.dp).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("ISO 216 · A4 TYPESETTING", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted, letterSpacing = 0.7.sp)
                Text("无损题库印务与排版系统", fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                Text("统一 10.5pt 字号与公式比例，导出直存 Download/CCTRExport", fontSize = 12.sp, color = CctrColors.InkSecondary)
            }
            AtelierAuthSheet(vm, state, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun SpecLedgerLine(no: String, key: String, value: String) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(no, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
            Text(key, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary, modifier = Modifier.width(72.dp))
            Text(value, fontSize = 11.5.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary)
        }
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
    }
}

@Composable
private fun AtelierAuthSheet(vm: MainViewModel, state: MainUiState, modifier: Modifier) {
    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = modifier
    ) {
        Column(modifier = Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("连接学校账号", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                Text("SESSION AUTH", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
            }
            Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))

            AtelierTextField(
                value = state.schoolCode,
                onValueChange = vm::updateSchoolCode,
                label = "学校代码",
                placeholder = "例如 u101441"
            )
            AtelierTextField(
                value = state.username,
                onValueChange = vm::updateUsername,
                label = "学号 / 账号",
                placeholder = "输入学号或登录账号"
            )
            AtelierTextField(
                value = state.password,
                onValueChange = vm::updatePassword,
                label = "密码",
                placeholder = "输入登录密码",
                isPassword = true
            )

            // Integrated graphic captcha bar
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("图形验证码", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkSecondary)
                    Text(
                        text = if (state.captchaAutoRecognized) "OCR · ${state.captchaCode}" else state.captchaStatus,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = if (state.captchaAutoRecognized) CctrColors.StatusOk else CctrColors.InkMuted
                    )
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(44.dp)
                        .background(CctrColors.BgSurface, RoundedCornerShape(6.dp))
                        .border(1.dp, CctrColors.LineStrong, RoundedCornerShape(6.dp))
                        .clip(RoundedCornerShape(6.dp))
                ) {
                    Box(modifier = Modifier.weight(1f).padding(horizontal = 12.dp), contentAlignment = Alignment.CenterStart) {
                        if (state.captchaCode.isEmpty()) {
                            Text("自动识码中", fontSize = 13.sp, color = CctrColors.InkMuted)
                        }
                        BasicTextField(
                            value = state.captchaCode,
                            onValueChange = vm::updateCaptchaCode,
                            singleLine = true,
                            cursorBrush = SolidColor(CctrColors.InkPrimary),
                            textStyle = TextStyle(
                                color = CctrColors.InkPrimary,
                                fontSize = 14.sp,
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.SemiBold,
                                letterSpacing = 2.5.sp
                            ),
                            modifier = Modifier.fillMaxWidth().semantics { contentDescription = "图形验证码" }
                        )
                    }
                    Box(modifier = Modifier.width(1.dp).fillMaxHeight().background(CctrColors.BorderHairline))
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier
                            .width(112.dp)
                            .fillMaxHeight()
                            .background(Color.White)
                            .clickable { vm.loadCaptcha() }
                    ) {
                        when {
                            state.captchaLoading -> CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 1.8.dp, color = CctrColors.InkPrimary)
                            state.captchaBitmap != null -> Image(
                                bitmap = state.captchaBitmap!!.asImageBitmap(),
                                contentDescription = "刷新验证码",
                                contentScale = ContentScale.Fit,
                                modifier = Modifier.fillMaxSize().padding(3.dp)
                            )
                            else -> Text("点击重试", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
                        }
                    }
                }
            }

            state.loginError?.let { err ->
                Surface(
                    color = CctrColors.AccentSealSoft,
                    border = BorderStroke(1.dp, CctrColors.AccentSeal.copy(alpha = 0.28f)),
                    shape = RoundedCornerShape(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(err, color = CctrColors.AccentSeal, fontSize = 12.sp, modifier = Modifier.padding(10.dp))
                }
            }

            AtelierPrimaryButton(
                text = if (state.loginBusy) "正在载入目录…" else "连接并载入题库",
                onClick = { vm.loginAndLoadPractices() },
                enabled = !state.loginBusy,
                loading = state.loginBusy
            )
        }
    }
}

@Composable
private fun PracticePickerView(vm: MainViewModel, state: MainUiState, isTablet: Boolean) {
    val kw = state.practiceSearch.trim()
    val filtered = remember(state.practices, kw) {
        if (kw.isEmpty()) state.practices
        else state.practices.filter {
            it.lessonName.contains(kw, ignoreCase = true) ||
                it.practiceName.contains(kw, ignoreCase = true) ||
                it.teacherName.contains(kw, ignoreCase = true)
        }
    }
    val selectedList = state.practices.filter { it.id in state.selectedPracticeIds }
    val estCount = selectedList.sumOf { it.questionCount ?: 0 }

    Column(
        modifier = Modifier.widthIn(max = if (isTablet) 960.dp else 640.dp).fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            AtelierTextField(
                value = state.practiceSearch,
                onValueChange = vm::updatePracticeSearch,
                label = "",
                placeholder = "按课程名称、练习或教师筛选…",
                modifier = Modifier.weight(1f)
            )
            AtelierGhostButton(
                text = if (state.selectedPracticeIds.size == state.practices.size && state.practices.isNotEmpty()) "清空" else "全选",
                onClick = { vm.toggleSelectAllPractices() }
            )
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = if (isTablet) 500.dp else 400.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (filtered.isEmpty()) {
                Surface(
                    color = CctrColors.BgSurface,
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, CctrColors.BorderHairline),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Box(modifier = Modifier.padding(32.dp), contentAlignment = Alignment.Center) {
                        Text("没有匹配的课程练习", fontSize = 13.sp, color = CctrColors.InkMuted)
                    }
                }
            } else if (isTablet) {
                filtered.chunked(2).forEach { pair ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        pair.forEach { p ->
                            Box(modifier = Modifier.weight(1f)) {
                                PracticeLedgerCard(
                                    item = p,
                                    checked = p.id in state.selectedPracticeIds,
                                    minHeight = 76.dp,
                                    onToggle = { vm.togglePractice(p.id) }
                                )
                            }
                        }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            } else {
                filtered.forEach { p ->
                    PracticeLedgerCard(
                        item = p,
                        checked = p.id in state.selectedPracticeIds,
                        minHeight = 0.dp,
                        onToggle = { vm.togglePractice(p.id) }
                    )
                }
            }
        }

        Surface(
            color = CctrColors.BgSurface,
            shape = RoundedCornerShape(8.dp),
            border = BorderStroke(1.dp, CctrColors.BorderHairline),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "已选 ${selectedList.size}/${state.practices.size} 项",
                        fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.SemiBold,
                        color = CctrColors.InkPrimary
                    )
                    Text(
                        text = if (estCount > 0) "约 $estCount 道题" else "请选择练习",
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = CctrColors.InkMuted
                    )
                }
                AtelierGhostButton(text = "返回", onClick = { vm.setWizardStep(1) })
                AtelierPrimaryButton(
                    text = "版式与付印 →",
                    onClick = { vm.proceedToExportSettings() },
                    enabled = state.selectedPracticeIds.isNotEmpty(),
                    modifier = Modifier.width(136.dp)
                )
            }
        }
    }
}

@Composable
private fun PracticeLedgerCard(
    item: PracticeItem,
    checked: Boolean,
    minHeight: Dp,
    onToggle: () -> Unit
) {
    Surface(
        color = if (checked) CctrColors.BgSheetSoft else CctrColors.BgSurface,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, if (checked) CctrColors.InkPrimary else CctrColors.BorderHairline),
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = minHeight)
            .clickable(onClick = onToggle)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .height(44.dp)
                    .background(if (checked) CctrColors.InkPrimary else Color.Transparent)
            )
            Row(
                modifier = Modifier.weight(1f).padding(horizontal = 12.dp, vertical = 11.dp),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(modifier = Modifier.padding(top = 2.dp)) {
                    AtelierSquareCheck(checked)
                }
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                        Text(
                            text = item.lessonName.ifBlank { item.practiceName },
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = CctrColors.InkPrimary,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f).padding(end = 6.dp)
                        )
                        item.questionCount?.let { cnt ->
                            Surface(color = CctrColors.BgSubtle, shape = RoundedCornerShape(4.dp)) {
                                Text(
                                    text = "${cnt}题",
                                    fontSize = 10.5.sp,
                                    fontFamily = FontFamily.Monospace,
                                    fontWeight = FontWeight.SemiBold,
                                    color = CctrColors.InkSecondary,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }
                    Text(
                        text = item.practiceName,
                        fontSize = 11.5.sp,
                        color = CctrColors.InkSecondary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

@Composable
private fun ExportBenchView(vm: MainViewModel, state: MainUiState, isTablet: Boolean, isExpanded: Boolean) {
    Column(
        modifier = Modifier.widthIn(max = if (isExpanded) 1040.dp else 640.dp).fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        ExportStatusBanner(vm, state)

        if (isExpanded) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(18.dp),
                verticalAlignment = Alignment.Top
            ) {
                Box(modifier = Modifier.weight(1.08f)) {
                    ExportParamsPanel(vm, state)
                }
                Box(modifier = Modifier.weight(0.92f)) {
                    A4SpecimenPanel(state)
                }
            }
        } else {
            ExportParamsPanel(vm, state)
            A4SpecimenPanel(state)
        }
    }
}

@Composable
private fun ExportStatusBanner(vm: MainViewModel, state: MainUiState) {
    val res = state.exportResult
    val err = state.exportError
    if (!state.exporting && res == null && err == null) return
    val context = LocalContext.current

    val bg = when {
        err != null -> CctrColors.AccentSealSoft
        res != null -> CctrColors.StatusOkSoft
        else -> CctrColors.BgSurface
    }
    val borderCol = when {
        err != null -> CctrColors.AccentSeal.copy(alpha = 0.3f)
        res != null -> CctrColors.StatusOk.copy(alpha = 0.3f)
        else -> CctrColors.BorderHairline
    }

    Surface(
        color = bg,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, borderCol),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                state.exporting -> {
                    Text("正在后台制版与校验…", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth().height(3.dp),
                        color = CctrColors.InkPrimary,
                        trackColor = CctrColors.BgSubtle
                    )
                    Text(state.exportProgressText, fontSize = 11.5.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary)
                }
                err != null -> {
                    Text("导出失败：$err", fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.AccentSeal)
                }
                res != null -> {
                    Text("已完成成稿：${res.name}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.StatusOk)
                    Text(
                        "${res.sizeBytes / 1024} KB · 共 ${res.questionCount} 题 · 已直存 Download/CCTRExport（当前仍保持登录）",
                        fontSize = 11.5.sp,
                        fontFamily = FontFamily.Monospace,
                        color = CctrColors.InkSecondary
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        AtelierPrimaryButton(
                            text = "打开成稿",
                            onClick = { openExportedFile(context, File(res.path)) },
                            modifier = Modifier.width(108.dp)
                        )
                        AtelierGhostButton(
                            text = "查看归档",
                            onClick = { vm.setTab(2) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ExportParamsPanel(vm: MainViewModel, state: MainUiState) {
    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("付印参数与范围", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                Text("${state.selectedPracticeIds.size} 项练习", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
            }
            Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("交付载体", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkSecondary)
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ExportFormat.entries.forEach { fmt ->
                        val sel = state.exportFormat == fmt
                        Surface(
                            color = if (sel) CctrColors.BgSurface else CctrColors.BgSheetSoft,
                            border = BorderStroke(1.dp, if (sel) CctrColors.InkPrimary else CctrColors.BorderHairline),
                            shape = RoundedCornerShape(6.dp),
                            modifier = Modifier.weight(1f).height(76.dp).clickable { vm.setExportFormat(fmt) }
                        ) {
                            Box(modifier = Modifier.fillMaxSize().padding(12.dp)) {
                                if (sel) {
                                    Box(modifier = Modifier.align(Alignment.TopEnd).size(6.dp).background(CctrColors.InkPrimary, CircleShape))
                                }
                                Column {
                                    Text(fmt.label, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                                    Spacer(Modifier.height(3.dp))
                                    Text(fmt.subtitle, fontSize = 11.sp, color = CctrColors.InkMuted, maxLines = 2)
                                }
                            }
                        }
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("答案批注版式", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkSecondary)
                val variants = AnswerVariant.entries
                AtelierSegmentedRow(
                    labels = variants.map {
                        when (it) {
                            AnswerVariant.WITH_ANSWERS_RED -> "朱批红标"
                            AnswerVariant.WITH_ANSWERS_PLAIN -> "墨字附答"
                            AnswerVariant.WITHOUT_ANSWERS -> "空白试卷"
                        }
                    },
                    selectedIndex = variants.indexOf(state.answerVariant).coerceAtLeast(0),
                    onSelect = { idx -> vm.setAnswerVariant(variants[idx]) }
                )
            }

            if (state.chapters.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("章节筛选（不勾选即全部导出）", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkSecondary)
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 104.dp)
                            .background(CctrColors.BgSheetSoft, RoundedCornerShape(6.dp))
                            .border(1.dp, CctrColors.BorderHairline, RoundedCornerShape(6.dp))
                            .verticalScroll(rememberScrollState())
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        state.chapters.forEach { ch ->
                            val sel = ch.id in state.selectedChapterIds
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth().clickable { vm.toggleChapter(ch.id) }.padding(vertical = 2.dp)
                            ) {
                                AtelierSquareCheck(sel)
                                Text(ch.name, fontSize = 12.sp, color = CctrColors.InkPrimary)
                            }
                        }
                    }
                }
            }

            Column {
                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                AtelierSwitchRow(
                    title = "智能防隔页分页",
                    subtitle = "小题整题不跨页拆散；超长单题页内接续后换页",
                    checked = state.smartPagination,
                    onCheckedChange = vm::setSmartPagination
                )
                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                AtelierSwitchRow(
                    title = "仅导出已练习题目",
                    subtitle = "关闭时全量拉取未练与已练全部题目并核对总数",
                    checked = state.practicedOnly,
                    onCheckedChange = vm::setPracticedOnly
                )
                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
            }

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                AtelierGhostButton(text = "重选练习", onClick = { vm.setWizardStep(2) }, modifier = Modifier.weight(1f))
                AtelierPrimaryButton(
                    text = if (state.exporting) "制版中…" else "开始生成并校验",
                    onClick = { vm.startExport() },
                    enabled = !state.exporting,
                    loading = state.exporting,
                    modifier = Modifier.weight(1.8f)
                )
            }
        }
    }
}

@Composable
private fun A4SpecimenPanel(state: MainUiState) {
    val showAnswer = state.answerVariant != AnswerVariant.WITHOUT_ANSWERS
    val redHighlight = state.answerVariant == AnswerVariant.WITH_ANSWERS_RED

    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("A4 实样校对台", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                Text("10.5PT UNIFORM", fontSize = 10.5.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold, color = CctrColors.StatusOk)
            }

            // Cutting mat + crop-marked specimen paper
            Surface(
                color = CctrColors.BgSubtle,
                shape = RoundedCornerShape(6.dp),
                border = BorderStroke(1.dp, CctrColors.BorderHairline),
                modifier = Modifier.fillMaxWidth()
            ) {
                Box(modifier = Modifier.padding(14.dp)) {
                    Surface(
                        color = Color.White,
                        shape = RoundedCornerShape(2.dp),
                        shadowElevation = 2.dp,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Box(modifier = Modifier.fillMaxWidth()) {
                            // 4 subtle crop marks via Canvas
                            Canvas(modifier = Modifier.matchParentSize()) {
                                val sw = 1.dp.toPx()
                                val m = 6.dp.toPx()
                                val len = 8.dp.toPx()
                                val col = CctrColors.LineStrong
                                drawLine(col, Offset(m, m), Offset(m + len, m), sw)
                                drawLine(col, Offset(m, m), Offset(m, m + len), sw)
                                drawLine(col, Offset(size.width - m, m), Offset(size.width - m - len, m), sw)
                                drawLine(col, Offset(size.width - m, m), Offset(size.width - m, m + len), sw)
                                drawLine(col, Offset(m, size.height - m), Offset(m + len, size.height - m), sw)
                                drawLine(col, Offset(m, size.height - m), Offset(m, size.height - m - len), sw)
                                drawLine(col, Offset(size.width - m, size.height - m), Offset(size.width - m - len, size.height - m), sw)
                                drawLine(col, Offset(size.width - m, size.height - m), Offset(size.width - m, size.height - m - len), sw)
                            }

                            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text("示例讲义 · 导论与计算", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                                    Text("210×297 mm", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
                                }
                                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text("第 1 题", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                                    Text("(2683548)", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
                                }
                                Text(
                                    "理想电偶极子远区辐射电场强度幅度与距离 r 的关系为（  ）。",
                                    fontSize = 11.5.sp,
                                    color = CctrColors.InkPrimary
                                )
                                Text("A. 与 r 成正比", fontSize = 11.5.sp, color = CctrColors.InkSecondary)
                                Text("B. 与 1/r² 成正比", fontSize = 11.5.sp, color = CctrColors.InkSecondary)
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(if (redHighlight) CctrColors.AccentSealSoft else Color.Transparent, RoundedCornerShape(3.dp))
                                ) {
                                    if (redHighlight) {
                                        Box(modifier = Modifier.width(2.5.dp).height(20.dp).background(CctrColors.AccentSeal))
                                        Spacer(Modifier.width(6.dp))
                                    }
                                    Text(
                                        "C. 与 1/r 成正比",
                                        fontSize = 11.5.sp,
                                        fontWeight = if (redHighlight) FontWeight.SemiBold else FontWeight.Normal,
                                        color = if (redHighlight) CctrColors.AccentSeal else CctrColors.InkSecondary,
                                        modifier = Modifier.padding(vertical = 2.dp)
                                    )
                                }
                                Text("D. 与 r² 成正比", fontSize = 11.5.sp, color = CctrColors.InkSecondary)

                                if (showAnswer) {
                                    Spacer(Modifier.height(2.dp))
                                    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                                    Surface(
                                        color = if (redHighlight) CctrColors.AccentSealSoft else CctrColors.BgCanvas,
                                        border = BorderStroke(1.dp, if (redHighlight) CctrColors.AccentSeal.copy(alpha = 0.28f) else CctrColors.BorderHairline),
                                        shape = RoundedCornerShape(3.dp)
                                    ) {
                                        Text(
                                            "答案 · C",
                                            fontSize = 10.sp,
                                            fontFamily = FontFamily.Monospace,
                                            fontWeight = FontWeight.SemiBold,
                                            color = if (redHighlight) CctrColors.AccentSeal else CctrColors.InkPrimary,
                                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                SpecimenMetaRow("版面规范", "ISO A4 · 四周 18 mm")
                SpecimenMetaRow("分页规则", if (state.smartPagination) "智能防隔页（小题整题不跨页）" else "紧凑连续分页")
                SpecimenMetaRow("输出目录", "Download/CCTRExport")
            }
        }
    }
}

@Composable
private fun SpecimenMetaRow(k: String, v: String) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(k, fontSize = 11.5.sp, color = CctrColors.InkMuted)
            Text(v, fontSize = 11.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
        }
        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
    }
}

/* ── Tabs 1 & 2: Audit Logs & Archive Files ─────────────────────────────── */

@Composable
private fun AuditLogsStage(vm: MainViewModel, state: MainUiState, isTablet: Boolean) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .then(if (isTablet) Modifier.widthIn(max = 960.dp) else Modifier)
                .fillMaxWidth()
                .padding(if (isTablet) 24.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("完整性核对、图片加载与制版日志", fontSize = 12.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary)
                AtelierGhostButton(text = "清空日志", onClick = { vm.clearLogs() })
            }
            Surface(
                color = CctrColors.BgSurface,
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, CctrColors.BorderHairline),
                modifier = Modifier.fillMaxWidth().weight(1f)
            ) {
                if (state.logs.isEmpty()) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("暂无运行与审校日志", fontSize = 12.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted)
                    }
                } else {
                    LazyColumn(modifier = Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        items(state.logs.reversed()) { line ->
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    text = line,
                                    fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace,
                                    color = if ("✗" in line || "失败" in line) CctrColors.AccentSeal else CctrColors.InkSecondary
                                )
                                Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(CctrColors.BorderHairline))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ArchiveFilesStage(state: MainUiState, isTablet: Boolean) {
    val context = LocalContext.current
    if (state.savedFiles.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
            Surface(
                color = CctrColors.BgSurface,
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, CctrColors.LineStrong),
                modifier = Modifier.widthIn(max = 520.dp).fillMaxWidth()
            ) {
                Box(modifier = Modifier.padding(36.dp), contentAlignment = Alignment.Center) {
                    Text("尚无本地归档成稿（导出后将直存 Download/CCTRExport）", fontSize = 12.5.sp, color = CctrColors.InkMuted)
                }
            }
        }
        return
    }
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        LazyColumn(
            modifier = Modifier
                .fillMaxHeight()
                .then(if (isTablet) Modifier.widthIn(max = 960.dp) else Modifier)
                .fillMaxWidth()
                .padding(if (isTablet) 24.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (isTablet) {
                items(state.savedFiles.chunked(2)) { pair ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        pair.forEach { file ->
                            Box(modifier = Modifier.weight(1f)) {
                                ArchiveFileRowCard(context, file)
                            }
                        }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            } else {
                items(state.savedFiles) { file ->
                    ArchiveFileRowCard(context, file)
                }
            }
        }
    }
}

@Composable
private fun ArchiveFileRowCard(context: Context, file: File) {
    val ext = file.extension.uppercase().ifBlank { "FILE" }
    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = Modifier.fillMaxWidth().clickable { openExportedFile(context, file) }
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Surface(
                color = CctrColors.BgSubtle,
                border = BorderStroke(1.dp, CctrColors.BorderHairline),
                shape = RoundedCornerShape(4.dp)
            ) {
                Text(
                    text = ext,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.SemiBold,
                    color = CctrColors.InkPrimary,
                    modifier = Modifier.padding(horizontal = 7.dp, vertical = 5.dp)
                )
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(file.name, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${file.length() / 1024} KB · 点击打开或分享成稿", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkMuted, maxLines = 1)
            }
        }
    }
}

private fun openExportedFile(context: Context, file: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val mime = if (file.name.endsWith(".zip", true)) "application/zip" else "application/pdf"
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, mime)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "打开导出成稿"))
}
