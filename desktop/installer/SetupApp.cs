using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace CCTRCloudSetup
{
    internal static class SetupProgram
    {
        private const string AppDisplayName = "融智云考 · 印务台";
        private const string AppVersion = "4.2.0";
        private const string UninstallRegPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CCTRCloudExport";

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            bool quiet = false;
            string customDir = "";
            bool noLaunch = false;
            foreach (string a in args)
            {
                if (string.Equals(a, "--quiet", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(a, "/S", StringComparison.OrdinalIgnoreCase))
                {
                    quiet = true;
                }
                else if (a.StartsWith("--dir=", StringComparison.OrdinalIgnoreCase))
                {
                    customDir = a.Substring(6).Trim('"');
                }
                else if (string.Equals(a, "--no-launch", StringComparison.OrdinalIgnoreCase))
                {
                    noLaunch = true;
                }
            }

            string defaultDir = !string.IsNullOrWhiteSpace(customDir)
                ? customDir
                : Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs",
                    "CCTRCloudExport"
                );

            if (quiet)
            {
                string err = null;
                try
                {
                    RunInstall(defaultDir, !noLaunch, !noLaunch, true, _ => { }, _ => { });
                    return 0;
                }
                catch (Exception ex)
                {
                    err = ex.ToString();
                    Console.Error.WriteLine(err);
                    return 1;
                }
            }

            using (var form = new SetupForm(defaultDir))
            {
                Application.Run(form);
            }
            return 0;
        }

        internal static void ExtractGzipResource(string resourceName, string targetPath, Action<int> progressPct)
        {
            Assembly asm = Assembly.GetExecutingAssembly();
            using (Stream raw = asm.GetManifestResourceStream(resourceName))
            {
                if (raw == null)
                {
                    throw new InvalidOperationException("安装包内缺少资源：" + resourceName);
                }
                Directory.CreateDirectory(Path.GetDirectoryName(targetPath));
                using (var gz = new GZipStream(raw, CompressionMode.Decompress))
                using (var fs = new FileStream(targetPath, FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 1024))
                {
                    byte[] buffer = new byte[1024 * 1024];
                    long totalRead = 0;
                    int read;
                    while ((read = gz.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        fs.Write(buffer, 0, read);
                        totalRead += read;
                        if (raw.CanSeek && raw.Length > 0)
                        {
                            int pct = (int)Math.Min(99, (raw.Position * 100L) / raw.Length);
                            progressPct(pct);
                        }
                    }
                }
            }
        }

        internal static void CreateShortcut(string shortcutPath, string targetPath, string arguments, string description, string iconPath)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(shortcutPath));
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null)
            {
                return;
            }
            dynamic shell = Activator.CreateInstance(shellType);
            dynamic shortcut = shell.CreateShortcut(shortcutPath);
            shortcut.TargetPath = targetPath;
            if (!string.IsNullOrEmpty(arguments))
            {
                shortcut.Arguments = arguments;
            }
            shortcut.WorkingDirectory = Path.GetDirectoryName(targetPath);
            shortcut.Description = description;
            if (!string.IsNullOrEmpty(iconPath))
            {
                shortcut.IconLocation = iconPath + ",0";
            }
            shortcut.Save();
        }

        internal static string CheckAndPrepareEnvironment(string exePath, Action<string> log)
        {
            if (!Environment.Is64BitOperatingSystem)
            {
                throw new PlatformNotSupportedException("当前仅支持 64 位 Windows 10/11 操作系统。");
            }
            log("✓ 系统架构校验通过：64 位 Windows");

            string configDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".cctr_export"
            );
            Directory.CreateDirectory(configDir);
            log("✓ 本地配置目录就绪：" + configDir);

            string docDir = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string exportDir = !string.IsNullOrWhiteSpace(docDir)
                ? Path.Combine(docDir, "CCTRExport")
                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "CCTRExport");
            try
            {
                Directory.CreateDirectory(exportDir);
                log("✓ 默认导出目录就绪：" + exportDir);
            }
            catch (Exception ex)
            {
                log("! 文档目录访问受限（导出时将自动回退至用户目录）：" + ex.Message);
            }

            bool sysVcInstalled = false;
            try
            {
                using (RegistryKey rk = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"))
                {
                    sysVcInstalled = rk != null && Convert.ToInt32(rk.GetValue("Installed", 0)) == 1;
                }
            }
            catch
            {
            }
            log(sysVcInstalled
                ? "✓ 系统已安装 VC++ 2015-2022 (x64) 运行库（程序同时内置独立私有一致版本）"
                : "✓ 目标机未预装系统 VC++ 运行库，将使用安装包内置的私有一致版 VC++ 14.44 全套运行库");

            string edgePath = FindBrowserExe("msedge.exe", @"Microsoft\Edge\Application\msedge.exe");
            string chromePath = FindBrowserExe("chrome.exe", @"Google\Chrome\Application\chrome.exe");
            if (!string.IsNullOrEmpty(edgePath))
            {
                log("✓ 检测到系统 Edge 渲染内核：" + edgePath);
            }
            else if (!string.IsNullOrEmpty(chromePath))
            {
                log("✓ 检测到系统 Chrome 渲染内核：" + chromePath);
            }
            else
            {
                log("• 未检测到外部 Edge/Chrome，软件将自动使用内置 QtWebEngine Chromium 渲染内核导出无损 PDF");
            }

            if (File.Exists(exePath))
            {
                string reportFile = Path.Combine(Path.GetTempPath(), "cctr_self_check_" + Guid.NewGuid().ToString("N") + ".txt");
                try
                {
                    log("正在执行离线环境全模块实机自检 (DLL / OCR / QtWebEngine / SOCKS5)...");
                    var psi = new ProcessStartInfo(exePath, "--self-check=\"" + reportFile + "\"")
                    {
                        CreateNoWindow = true,
                        UseShellExecute = false,
                        WindowStyle = ProcessWindowStyle.Hidden,
                        WorkingDirectory = Path.GetDirectoryName(exePath),
                    };
                    using (var proc = Process.Start(psi))
                    {
                        if (proc == null || !proc.WaitForExit(120000))
                        {
                            throw new TimeoutException("环境自检超时，请检查杀毒软件是否拦截子进程。");
                        }
                        if (proc.ExitCode != 0)
                        {
                            throw new InvalidOperationException("环境自检返回异常状态码：" + proc.ExitCode);
                        }
                    }
                    string summary = File.Exists(reportFile) ? File.ReadAllText(reportFile).Trim() : "SELF_CHECK_OK";
                    log("✓ 运行环境自检全部通过：" + summary);
                    return summary;
                }
                finally
                {
                    try { if (File.Exists(reportFile)) File.Delete(reportFile); } catch { }
                }
            }
            return "ENV_READY";
        }

        private static string FindBrowserExe(string exeName, string relSubPath)
        {
            string[] roots =
            {
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            };
            foreach (string root in roots)
            {
                if (string.IsNullOrEmpty(root)) continue;
                string p = Path.Combine(root, relSubPath);
                if (File.Exists(p)) return p;
            }
            return "";
        }

        internal static void RunInstall(
            string installDir,
            bool createDesktop,
            bool createStartMenu,
            bool runEnvSetup,
            Action<int> onProgress,
            Action<string> log
        )
        {
            log("正在准备安装目录：" + installDir);
            foreach (var proc in Process.GetProcessesByName("CCTRCloudExportDesktop"))
            {
                try
                {
                    proc.Kill();
                    proc.WaitForExit(3000);
                    log("已关闭旧版本正在运行的进程");
                }
                catch
                {
                }
            }

            Directory.CreateDirectory(installDir);
            string desktopExe = Path.Combine(installDir, "CCTRCloudExportDesktop.exe");
            string uninstallExe = Path.Combine(installDir, "Uninstall.exe");

            onProgress(5);
            log("正在释放主程序与内置全套运行环境 (Python / PySide6 / VC++ / OCR / SOCKS5)...");
            ExtractGzipResource("app.gz", desktopExe, p => onProgress(5 + (int)(p * 0.72)));

            onProgress(80);
            log("正在写入独立卸载程序 Uninstall.exe...");
            ExtractGzipResource("uninstall.gz", uninstallExe, _ => { });

            onProgress(85);
            if (createDesktop)
            {
                string deskLnk = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    AppDisplayName + ".lnk"
                );
                CreateShortcut(deskLnk, desktopExe, "", AppDisplayName, desktopExe);
                log("✓ 已创建桌面快捷方式");
            }

            if (createStartMenu)
            {
                string menuDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                    AppDisplayName
                );
                CreateShortcut(Path.Combine(menuDir, AppDisplayName + ".lnk"), desktopExe, "", AppDisplayName, desktopExe);
                CreateShortcut(Path.Combine(menuDir, "一键自检运行环境.lnk"), desktopExe, "--self-check", "检测桌面版运行环境与导出组件", desktopExe);
                CreateShortcut(Path.Combine(menuDir, "卸载 " + AppDisplayName + ".lnk"), uninstallExe, "--uninstall", "卸载 " + AppDisplayName, uninstallExe);
                log("✓ 已创建「开始」菜单快捷方式与卸载入口");
            }

            onProgress(90);
            long sizeKb = new FileInfo(desktopExe).Length / 1024L + 128L;
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallRegPath))
            {
                key.SetValue("DisplayName", AppDisplayName);
                key.SetValue("DisplayVersion", AppVersion);
                key.SetValue("Publisher", "CCTRCloud Export");
                key.SetValue("InstallLocation", installDir);
                key.SetValue("DisplayIcon", desktopExe);
                key.SetValue("UninstallString", "\"" + uninstallExe + "\" --uninstall");
                key.SetValue("QuietUninstallString", "\"" + uninstallExe + "\" --uninstall --quiet");
                key.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, sizeKb), RegistryValueKind.DWord);
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
            log("✓ 已注册到 Windows「应用和功能」卸载列表");

            if (runEnvSetup)
            {
                onProgress(94);
                CheckAndPrepareEnvironment(desktopExe, log);
            }

            onProgress(100);
            log("全部安装与环境配置已完成！可直接启动使用。");
        }

        private sealed class SetupForm : Form
        {
            private readonly TextBox _txtDir;
            private readonly CheckBox _chkEnv;
            private readonly CheckBox _chkDesktop;
            private readonly CheckBox _chkMenu;
            private readonly CheckBox _chkLaunch;
            private readonly ProgressBar _progress;
            private readonly TextBox _logBox;
            private readonly Button _btnEnvOnly;
            private readonly Button _btnInstall;
            private readonly Button _btnBrowse;
            private bool _installed;
            private string _installedExe = "";

            public SetupForm(string defaultDir)
            {
                Text = "融智云考 · 印务台 v" + AppVersion + " 安装程序";
                Size = new Size(600, 490);
                StartPosition = FormStartPosition.CenterScreen;
                FormBorderStyle = FormBorderStyle.FixedDialog;
                MaximizeBox = false;
                BackColor = Color.FromArgb(250, 249, 246);
                Font = new Font("Microsoft YaHei UI", 9.5f);

                var headerPanel = new Panel
                {
                    Location = new Point(0, 0),
                    Size = new Size(600, 76),
                    BackColor = Color.FromArgb(20, 20, 19),
                };
                var lblTitle = new Label
                {
                    Text = "融智云考 · 印务台 安装向导",
                    Font = new Font("Microsoft YaHei UI", 14f, FontStyle.Bold),
                    ForeColor = Color.FromArgb(250, 249, 246),
                    Location = new Point(22, 13),
                    AutoSize = true,
                };
                var lblSub = new Label
                {
                    Text = "完整独立绿色环境安装包 · 自带 OCR / PDF 内核 / SOCKS 代理与标准 Uninstall 卸载",
                    Font = new Font("Microsoft YaHei UI", 9f),
                    ForeColor = Color.FromArgb(205, 202, 194),
                    Location = new Point(24, 44),
                    AutoSize = true,
                };
                headerPanel.Controls.AddRange(new Control[] { lblTitle, lblSub });

                var lblDir = new Label
                {
                    Text = "安装目录（默认无需管理员权限）：",
                    Location = new Point(22, 92),
                    AutoSize = true,
                    ForeColor = Color.FromArgb(50, 50, 46),
                };
                _txtDir = new TextBox
                {
                    Text = defaultDir,
                    Location = new Point(22, 118),
                    Size = new Size(446, 26),
                };
                _btnBrowse = new Button
                {
                    Text = "浏览...",
                    Location = new Point(478, 117),
                    Size = new Size(84, 28),
                    BackColor = Color.FromArgb(236, 234, 229),
                    FlatStyle = FlatStyle.Flat,
                };
                _btnBrowse.Click += (s, e) =>
                {
                    using (var fbd = new FolderBrowserDialog { SelectedPath = _txtDir.Text })
                    {
                        if (fbd.ShowDialog() == DialogResult.OK)
                        {
                            _txtDir.Text = fbd.SelectedPath;
                        }
                    }
                };

                _chkEnv = new CheckBox
                {
                    Text = "一键配置与自检完整运行环境（内置 VC++2022 / OCR / QtWebEngine / 代理支持）",
                    Location = new Point(22, 156),
                    Size = new Size(540, 24),
                    Checked = true,
                };
                _chkDesktop = new CheckBox
                {
                    Text = "创建桌面快捷方式",
                    Location = new Point(22, 182),
                    Size = new Size(260, 24),
                    Checked = true,
                };
                _chkMenu = new CheckBox
                {
                    Text = "注册「开始」菜单与 Windows 系统卸载入口 (Uninstall)",
                    Location = new Point(22, 208),
                    Size = new Size(540, 24),
                    Checked = true,
                };
                _chkLaunch = new CheckBox
                {
                    Text = "安装完成后立即启动软件",
                    Location = new Point(290, 182),
                    Size = new Size(270, 24),
                    Checked = true,
                };

                _progress = new ProgressBar
                {
                    Location = new Point(22, 242),
                    Size = new Size(540, 18),
                    Minimum = 0,
                    Maximum = 100,
                };

                _logBox = new TextBox
                {
                    Location = new Point(22, 270),
                    Size = new Size(540, 126),
                    Multiline = true,
                    ReadOnly = true,
                    ScrollBars = ScrollBars.Vertical,
                    BackColor = Color.White,
                    Text = "就绪：点击「一键安装并配置环境」即可完成安装与本机环境自检。" + Environment.NewLine,
                };

                _btnEnvOnly = new Button
                {
                    Text = "仅检测/修复环境",
                    Location = new Point(22, 408),
                    Size = new Size(146, 36),
                    BackColor = Color.FromArgb(236, 234, 229),
                    FlatStyle = FlatStyle.Flat,
                };
                _btnEnvOnly.Click += OnEnvOnlyClick;

                _btnInstall = new Button
                {
                    Text = "一键安装并配置环境",
                    Location = new Point(378, 408),
                    Size = new Size(184, 36),
                    BackColor = Color.FromArgb(20, 20, 19),
                    ForeColor = Color.White,
                    FlatStyle = FlatStyle.Flat,
                    Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold),
                };
                _btnInstall.FlatAppearance.BorderSize = 0;
                _btnInstall.Click += OnInstallClick;

                Controls.AddRange(new Control[]
                {
                    headerPanel, lblDir, _txtDir, _btnBrowse,
                    _chkEnv, _chkDesktop, _chkMenu, _chkLaunch,
                    _progress, _logBox, _btnEnvOnly, _btnInstall
                });
            }

            private void AppendLog(string msg)
            {
                if (IsDisposed) return;
                BeginInvoke((Action)(() =>
                {
                    _logBox.AppendText(msg + Environment.NewLine);
                }));
            }

            private async void OnEnvOnlyClick(object sender, EventArgs e)
            {
                _btnEnvOnly.Enabled = false;
                _btnInstall.Enabled = false;
                string exeCandidate = Path.Combine(_txtDir.Text.Trim(), "CCTRCloudExportDesktop.exe");
                await Task.Run(() =>
                {
                    try
                    {
                        CheckAndPrepareEnvironment(exeCandidate, AppendLog);
                    }
                    catch (Exception ex)
                    {
                        AppendLog("✗ 环境检测失败：" + ex.Message);
                    }
                });
                _btnEnvOnly.Enabled = true;
                _btnInstall.Enabled = true;
            }

            private async void OnInstallClick(object sender, EventArgs e)
            {
                if (_installed)
                {
                    if (_chkLaunch.Checked && File.Exists(_installedExe))
                    {
                        Process.Start(new ProcessStartInfo(_installedExe) { UseShellExecute = true });
                    }
                    Close();
                    return;
                }

                string dir = _txtDir.Text.Trim();
                if (string.IsNullOrEmpty(dir))
                {
                    MessageBox.Show("请选择有效的安装目录。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }

                _btnInstall.Enabled = false;
                _btnEnvOnly.Enabled = false;
                _btnBrowse.Enabled = false;
                _txtDir.Enabled = false;
                _logBox.Clear();

                bool desk = _chkDesktop.Checked;
                bool menu = _chkMenu.Checked;
                bool env = _chkEnv.Checked;
                bool ok = false;

                await Task.Run(() =>
                {
                    try
                    {
                        RunInstall(
                            dir,
                            desk,
                            menu,
                            env,
                            pct =>
                            {
                                if (!IsDisposed)
                                {
                                    BeginInvoke((Action)(() => _progress.Value = Math.Max(0, Math.Min(100, pct))));
                                }
                            },
                            AppendLog
                        );
                        ok = true;
                    }
                    catch (Exception ex)
                    {
                        AppendLog(Environment.NewLine + "✗ 安装过程出错：" + ex.Message);
                        if (!IsDisposed)
                        {
                            BeginInvoke((Action)(() =>
                                MessageBox.Show("安装失败：\n" + ex.Message, "安装错误", MessageBoxButtons.OK, MessageBoxIcon.Error)
                            ));
                        }
                    }
                });

                if (ok)
                {
                    _installed = true;
                    _installedExe = Path.Combine(dir, "CCTRCloudExportDesktop.exe");
                    _btnInstall.Text = _chkLaunch.Checked ? "完成并启动" : "完成";
                    _btnInstall.Enabled = true;
                    _btnEnvOnly.Enabled = true;
                }
                else
                {
                    _btnInstall.Enabled = true;
                    _btnEnvOnly.Enabled = true;
                    _btnBrowse.Enabled = true;
                    _txtDir.Enabled = true;
                }
            }
        }
    }
}
