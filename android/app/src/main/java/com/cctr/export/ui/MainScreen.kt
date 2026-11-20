package com.cctr.export.ui

import android.content.Intent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.TaskAlt
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.cctr.export.core.AnswerVariant
import com.cctr.export.core.ExportFormat
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: MainViewModel) {
    val state by vm.state.collectAsState()

    Scaffold(
        containerColor = CctrColors.BgCanvas,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(containerColor = CctrColors.BgSurface),
                title = {
                    Text(
                        text = when (state.activeTab) {
                            0 -> "融智导出 Studio"
                            1 -> "校验日志与进度"
                            else -> "导出记录"
                        },
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = CctrColors.InkPrimary
                    )
                },
                actions = {
                    if (state.practices.isNotEmpty()) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            modifier = Modifier.padding(end = 12.dp)
                        ) {
                            Surface(color = CctrColors.SuccessSoft, shape = RoundedCornerShape(999.dp)) {
                                Text(
                                    text = "✓ ${state.username}",
                                    color = CctrColors.Success,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                                )
                            }
                            Surface(
                                color = CctrColors.BgSubtle,
                                shape = RoundedCornerShape(999.dp),
                                modifier = Modifier.clickable { vm.signOut() }
                            ) {
                                Text(
                                    text = "换号",
                                    color = CctrColors.InkSecondary,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                                )
                            }
                        }
                    } else {
                        Surface(
                            color = CctrColors.SuccessSoft,
                            shape = RoundedCornerShape(999.dp),
                            modifier = Modifier.padding(end = 14.dp)
                        ) {
                            Text(
                                text = "ONNX 自动识别",
                                color = CctrColors.Success,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                            )
                        }
                    }
                }
            )
        },
        bottomBar = {
            NavigationBar(containerColor = CctrColors.BgSurface, tonalElevation = 0.dp) {
                listOf(
                    Triple(0, "导出工作台", Icons.Outlined.Home),
                    Triple(1, "任务进度", Icons.Outlined.TaskAlt),
                    Triple(2, "本地文件", Icons.Outlined.FolderOpen)
                ).forEach { (idx, label, icon) ->
                    NavigationBarItem(
                        selected = state.activeTab == idx,
                        onClick = { vm.setTab(idx) },
                        icon = { Icon(icon, contentDescription = label) },
                        label = { Text(label, fontSize = 11.sp, fontWeight = FontWeight.Medium) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = CctrColors.AccentBlue,
                            selectedTextColor = CctrColors.AccentBlue,
                            indicatorColor = CctrColors.AccentSoft,
                            unselectedIconColor = CctrColors.InkMuted,
                            unselectedTextColor = CctrColors.InkMuted
                        )
                    )
                }
            }
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(CctrColors.BgCanvas)
        ) {
            when (state.activeTab) {
                0 -> WorkspaceTab(vm, state)
                1 -> ProgressAndLogTab(vm, state)
                else -> LocalFilesTab(state)
            }
        }
    }
}

@Composable
private fun WorkspaceTab(vm: MainViewModel, state: MainUiState) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // 3-step segmented pills
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(1 to "1. 账号", 2 to "2. 练习", 3 to "3. 导出").forEach { (step, title) ->
                val active = state.wizardStep == step
                val done = state.wizardStep > step
                val bg = when {
                    active -> CctrColors.AccentBlue
                    done -> CctrColors.SuccessSoft
                    else -> CctrColors.BgSurface
                }
                val fg = when {
                    active -> Color.White
                    done -> CctrColors.Success
                    else -> CctrColors.InkMuted
                }
                Surface(
                    color = bg,
                    shape = RoundedCornerShape(10.dp),
                    border = if (!active && !done) BorderStroke(1.dp, CctrColors.BorderHairline) else null,
                    modifier = Modifier.weight(1f).clickable { vm.setWizardStep(step) }
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(vertical = 8.dp)) {
                        Text(title, color = fg, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }

        when (state.wizardStep) {
            1 -> LoginStepCard(vm, state)
            2 -> PracticeStepCard(vm, state)
            else -> ExportSettingsStepCard(vm, state)
        }
    }
}

@Composable
private fun LoginStepCard(vm: MainViewModel, state: MainUiState) {
    val fieldColors = OutlinedTextFieldDefaults.colors(
        focusedContainerColor = CctrColors.BgSurface,
        unfocusedContainerColor = CctrColors.BgSubtle,
        focusedBorderColor = CctrColors.AccentBlue,
        unfocusedBorderColor = CctrColors.BorderHairline
    )

    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("连接融智云考账号", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)

            OutlinedTextField(
                value = state.schoolCode,
                onValueChange = vm::updateSchoolCode,
                label = { Text("学校代码（如 u101441）") },
                singleLine = true,
                shape = RoundedCornerShape(10.dp),
                colors = fieldColors,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = state.username,
                onValueChange = vm::updateUsername,
                label = { Text("学号 / 平台账号") },
                singleLine = true,
                shape = RoundedCornerShape(10.dp),
                colors = fieldColors,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = state.password,
                onValueChange = vm::updatePassword,
                label = { Text("登录密码") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                shape = RoundedCornerShape(10.dp),
                colors = fieldColors,
                modifier = Modifier.fillMaxWidth()
            )

            // 验证码自动识别卡片
            Surface(
                color = CctrColors.BgSubtle,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("图形验证码（端侧自动识别）", fontSize = 12.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkPrimary)
                        Surface(
                            color = if (state.captchaAutoRecognized) CctrColors.SuccessSoft else CctrColors.BgSurface,
                            shape = RoundedCornerShape(999.dp)
                        ) {
                            Text(
                                text = state.captchaStatus,
                                color = if (state.captchaAutoRecognized) CctrColors.Success else CctrColors.InkMuted,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                            )
                        }
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = state.captchaCode,
                            onValueChange = vm::updateCaptchaCode,
                            placeholder = { Text("自动识别中") },
                            singleLine = true,
                            textStyle = androidx.compose.ui.text.TextStyle(
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 15.sp,
                                letterSpacing = 2.sp
                            ),
                            shape = RoundedCornerShape(8.dp),
                            colors = fieldColors,
                            modifier = Modifier.weight(1f)
                        )

                        Box(
                            contentAlignment = Alignment.Center,
                            modifier = Modifier
                                .width(116.dp)
                                .height(48.dp)
                                .clip(RoundedCornerShape(8.dp))
                                .background(Color.White)
                                .border(1.dp, CctrColors.BorderHairline, RoundedCornerShape(8.dp))
                                .clickable { vm.loadCaptcha() }
                        ) {
                            when {
                                state.captchaLoading -> CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                                state.captchaBitmap != null -> Image(
                                    bitmap = state.captchaBitmap!!.asImageBitmap(),
                                    contentDescription = "验证码图片",
                                    contentScale = ContentScale.Fit,
                                    modifier = Modifier.fillMaxSize().padding(4.dp)
                                )
                                else -> Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Outlined.Refresh, contentDescription = null, tint = CctrColors.InkMuted, modifier = Modifier.size(16.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("点击重试", fontSize = 11.sp, color = CctrColors.InkMuted)
                                }
                            }
                        }
                    }
                    Text("点击右侧验证码图片可刷新重识，识别结果可直接修改。", fontSize = 11.sp, color = CctrColors.InkMuted)
                }
            }

            state.loginError?.let { err ->
                Surface(color = CctrColors.DangerSoft, shape = RoundedCornerShape(8.dp), modifier = Modifier.fillMaxWidth()) {
                    Text(err, color = CctrColors.Danger, fontSize = 12.sp, modifier = Modifier.padding(10.dp))
                }
            }

            Button(
                onClick = { vm.loginAndLoadPractices() },
                enabled = !state.loginBusy,
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(containerColor = CctrColors.AccentBlue),
                modifier = Modifier.fillMaxWidth().height(48.dp)
            ) {
                if (state.loginBusy) {
                    CircularProgressIndicator(color = Color.White, modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text("登录并获取练习", fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun PracticeStepCard(vm: MainViewModel, state: MainUiState) {
    Surface(
        color = CctrColors.BgSurface,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, CctrColors.BorderHairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("已选练习（${state.selectedPracticeIds.size}/${state.practices.size}）", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text(
                    text = if (state.selectedPracticeIds.size == state.practices.size) "取消全选" else "全选",
                    color = CctrColors.AccentBlue,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clickable { vm.toggleSelectAllPractices() }.padding(4.dp)
                )
            }

            Column(
                modifier = Modifier.fillMaxWidth().heightIn(max = 390.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                state.practices.forEach { p ->
                    val checked = p.id in state.selectedPracticeIds
                    Surface(
                        color = if (checked) CctrColors.AccentSoft else CctrColors.BgSubtle,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth().clickable { vm.togglePractice(p.id) }
                    ) {
                        Row(modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(
                                checked = checked,
                                onCheckedChange = { vm.togglePractice(p.id) },
                                colors = CheckboxDefaults.colors(checkedColor = CctrColors.AccentBlue)
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text(p.practiceName, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkPrimary)
                                val countText = p.questionCount?.let { "$it 题 · " } ?: ""
                                Text("${countText}${p.lessonName}", fontSize = 11.sp, color = CctrColors.InkMuted)
                            }
                        }
                    }
                }
            }

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = { vm.setWizardStep(1) }, modifier = Modifier.weight(1f).height(46.dp), shape = RoundedCornerShape(10.dp)) {
                    Text("返回账号")
                }
                Button(
                    onClick = { vm.proceedToExportSettings() },
                    colors = ButtonDefaults.buttonColors(containerColor = CctrColors.AccentBlue),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.weight(2f).height(46.dp)
                ) {
                    Text("下一步：导出设置", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun ExportSettingsStepCard(vm: MainViewModel, state: MainUiState) {
    val context = LocalContext.current

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (state.exporting || state.exportResult != null || state.exportError != null) {
            val res = state.exportResult
            val err = state.exportError
            val cardBg = when {
                err != null -> CctrColors.DangerSoft
                res != null -> CctrColors.SuccessSoft
                else -> CctrColors.AccentSoft
            }
            val borderCol = when {
                err != null -> CctrColors.Danger.copy(alpha = 0.3f)
                res != null -> CctrColors.Success.copy(alpha = 0.35f)
                else -> CctrColors.AccentBlue.copy(alpha = 0.3f)
            }
            Surface(
                color = cardBg,
                shape = RoundedCornerShape(14.dp),
                border = BorderStroke(1.dp, borderCol),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    when {
                        state.exporting -> {
                            Text("⏳ 正在生成导出文件…", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = CctrColors.AccentBlue)
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = CctrColors.AccentBlue)
                            Text(state.exportProgressText, fontSize = 12.sp, color = CctrColors.InkSecondary)
                        }
                        err != null -> {
                            Text("✕ 导出失败：$err", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.Danger)
                        }
                        res != null -> {
                            Text("✓ 已完成导出：${res.name}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = CctrColors.Success)
                            Text(
                                "${res.sizeBytes / 1024} KB · 共 ${res.questionCount} 题 · 已保存至 Download/CCTRExport；当前仍保持登录，可直接切换格式再次导出。",
                                fontSize = 11.5.sp,
                                color = CctrColors.InkSecondary
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(
                                    onClick = { openExportedFile(context, File(res.path)) },
                                    colors = ButtonDefaults.buttonColors(containerColor = CctrColors.AccentBlue),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text("打开文件", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                                }
                                OutlinedButton(
                                    onClick = { vm.setTab(2) },
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text("查看全部导出", fontSize = 12.sp)
                                }
                            }
                        }
                    }
                }
            }
        }

        Surface(
            color = CctrColors.BgSurface,
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.dp, CctrColors.BorderHairline),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("答案模式与导出格式", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AnswerVariant.entries.forEach { variant ->
                        val sel = state.answerVariant == variant
                        Surface(
                            color = if (sel) CctrColors.AccentBlue else CctrColors.BgSubtle,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.weight(1f).clickable { vm.setAnswerVariant(variant) }
                        ) {
                            Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(vertical = 9.dp)) {
                                Text(variant.label, color = if (sel) Color.White else CctrColors.InkSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ExportFormat.entries.forEach { fmt ->
                        val sel = state.exportFormat == fmt
                        Surface(
                            color = if (sel) CctrColors.AccentSoft else CctrColors.BgSurface,
                            border = BorderStroke(if (sel) 1.5.dp else 1.dp, if (sel) CctrColors.AccentBlue else CctrColors.BorderHairline),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.weight(1f).height(82.dp).clickable { vm.setExportFormat(fmt) }
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(fmt.label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = if (sel) CctrColors.AccentBlue else CctrColors.InkPrimary)
                                Spacer(Modifier.height(2.dp))
                                Text(fmt.subtitle, fontSize = 11.sp, color = CctrColors.InkMuted, maxLines = 2)
                            }
                        }
                    }
                }

                if (state.chapters.isNotEmpty()) {
                    Text("章节筛选（不勾选即全部导出）", fontSize = 12.sp, fontWeight = FontWeight.Medium, color = CctrColors.InkSecondary)
                    Column(
                        modifier = Modifier.fillMaxWidth().heightIn(max = 104.dp).verticalScroll(rememberScrollState())
                    ) {
                        state.chapters.forEach { ch ->
                            val sel = ch.id in state.selectedChapterIds
                            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().clickable { vm.toggleChapter(ch.id) }) {
                                Checkbox(checked = sel, onCheckedChange = { vm.toggleChapter(ch.id) })
                                Text(ch.name, fontSize = 12.sp, color = CctrColors.InkPrimary)
                            }
                        }
                    }
                }

                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().clickable { vm.setSmartPagination(!state.smartPagination) }) {
                    Checkbox(checked = state.smartPagination, onCheckedChange = vm::setSmartPagination)
                    Text("智能防隔页分页（小题不跨页 · 超长题后换页）", fontSize = 12.sp, color = CctrColors.InkPrimary)
                }

                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().clickable { vm.setPracticedOnly(!state.practicedOnly) }) {
                    Checkbox(checked = state.practicedOnly, onCheckedChange = vm::setPracticedOnly)
                    Text("仅导出已练习题目（默认全量拉取）", fontSize = 12.sp, color = CctrColors.InkPrimary)
                }

                Surface(color = CctrColors.SuccessSoft, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                    Text(
                        if (state.smartPagination) "✓ 统一 10.5pt 字号 · 防隔页分页开启 · A4 18mm 留白"
                        else "✓ 统一 10.5pt 字号 · 紧凑连排省纸 · A4 18mm 留白",
                        color = CctrColors.Success,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
                    )
                }

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = { vm.setWizardStep(2) }, modifier = Modifier.weight(1f).height(46.dp), shape = RoundedCornerShape(10.dp)) {
                        Text("重选练习")
                    }
                    Button(
                        onClick = { vm.startExport() },
                        enabled = !state.exporting,
                        colors = ButtonDefaults.buttonColors(containerColor = CctrColors.AccentBlue),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.weight(2f).height(46.dp)
                    ) {
                        Text(if (state.exporting) "正在导出…" else "开始无损导出", fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun ProgressAndLogTab(vm: MainViewModel, state: MainUiState) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Surface(
            color = CctrColors.BgSurface,
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, CctrColors.BorderHairline),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text(if (state.exporting) "正在执行无损导出" else "最近任务与校验日志", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Text("清空", color = CctrColors.InkMuted, fontSize = 12.sp, modifier = Modifier.clickable { vm.clearLogs() }.padding(4.dp))
                }
                if (state.exporting) LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = CctrColors.AccentBlue)
                Text(state.exportProgressText.ifBlank { "尚无进行中的导出任务" }, fontSize = 13.sp, color = CctrColors.InkSecondary)
                state.exportError?.let { Text("错误：$it", color = CctrColors.Danger, fontSize = 12.sp) }
            }
        }

        Surface(
            color = CctrColors.BgSurface,
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, CctrColors.BorderHairline),
            modifier = Modifier.fillMaxWidth().weight(1f)
        ) {
            LazyColumn(modifier = Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(state.logs.reversed()) { line ->
                    Text(line, fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = CctrColors.InkSecondary)
                }
            }
        }
    }
}

private fun openExportedFile(context: android.content.Context, file: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val mime = if (file.name.endsWith(".zip", true)) "application/zip" else "application/pdf"
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, mime)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    runCatching { context.startActivity(Intent.createChooser(intent, "打开导出文件")) }
}

@Composable
private fun LocalFilesTab(state: MainUiState) {
    val context = LocalContext.current
    if (state.savedFiles.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("暂无已导出文件（导出后会同步存至 Download/CCTRExport）", color = CctrColors.InkMuted, fontSize = 13.sp)
        }
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        items(state.savedFiles) { file ->
            Surface(
                color = CctrColors.BgSurface,
                shape = RoundedCornerShape(12.dp),
                border = BorderStroke(1.dp, CctrColors.BorderHairline),
                modifier = Modifier.fillMaxWidth().clickable { openExportedFile(context, file) }
            ) {
                Row(modifier = Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Description, contentDescription = null, tint = CctrColors.AccentBlue)
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(file.name, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CctrColors.InkPrimary)
                        Text("${file.length() / 1024} KB · 点击查看或分享", fontSize = 11.sp, color = CctrColors.InkMuted)
                    }
                }
            }
        }
    }
}
