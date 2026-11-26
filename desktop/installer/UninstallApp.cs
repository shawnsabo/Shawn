using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace CCTRCloudSetup
{
    internal static class UninstallProgram
    {
        private const string UninstallRegPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CCTRCloudExport";
        private const string AppDisplayName = "融智云考 · 印务台";

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            bool quiet = false;
            bool purgeData = false;
            foreach (string a in args)
            {
                if (string.Equals(a, "--quiet", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(a, "/S", StringComparison.OrdinalIgnoreCase))
                {
                    quiet = true;
                }
                else if (string.Equals(a, "--purge-data", StringComparison.OrdinalIgnoreCase))
                {
                    purgeData = true;
                }
            }

            string installDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
            if (quiet)
            {
                PerformUninstall(installDir, purgeData, _ => { });
                ScheduleSelfDelete(installDir);
                return 0;
            }

            using (var form = new UninstallForm(installDir))
            {
                Application.Run(form);
            }
            return 0;
        }

        internal static void KillRunningApp()
        {
            foreach (var proc in Process.GetProcessesByName("CCTRCloudExportDesktop"))
            {
                try
                {
                    proc.Kill();
                    proc.WaitForExit(3000);
                }
                catch
                {
                }
            }
        }

        internal static void PerformUninstall(string installDir, bool purgeUserData, Action<string> log)
        {
            log("正在关闭运行中的桌面端进程...");
            KillRunningApp();

            string desktopShortcut = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                AppDisplayName + ".lnk"
            );
            TryDeleteFile(desktopShortcut, log);

            string startMenuDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                AppDisplayName
            );
            TryDeleteDir(startMenuDir, log);

            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(UninstallRegPath, false);
                log("已移除 Windows 系统卸载注册表项");
            }
            catch (Exception ex)
            {
                log("清理注册表提示: " + ex.Message);
            }

            string desktopExe = Path.Combine(installDir, "CCTRCloudExportDesktop.exe");
            TryDeleteFile(desktopExe, log);

            if (purgeUserData)
            {
                string userData = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    ".cctr_export"
                );
                TryDeleteDir(userData, log);
            }

            log("文件清理完成，退出后将自动删除安装目录。");
        }

        internal static void ScheduleSelfDelete(string installDir)
        {
            try
            {
                string selfExe = Process.GetCurrentProcess().MainModule != null
                    ? Process.GetCurrentProcess().MainModule.FileName
                    : Path.Combine(installDir, "Uninstall.exe");
                string cmd = string.Format(
                    "/c ping 127.0.0.1 -n 2 >nul & del /f /q \"{0}\" >nul 2>&1 & rmdir /s /q \"{1}\" >nul 2>&1",
                    selfExe,
                    installDir
                );
                Process.Start(new ProcessStartInfo("cmd.exe", cmd)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    WorkingDirectory = Path.GetTempPath(),
                });
            }
            catch
            {
            }
        }

        private static void TryDeleteFile(string path, Action<string> log)
        {
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                    log("已删除: " + path);
                }
            }
            catch (Exception ex)
            {
                log("删除跳过 " + path + ": " + ex.Message);
            }
        }

        private static void TryDeleteDir(string path, Action<string> log)
        {
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                    log("已移除目录: " + path);
                }
            }
            catch (Exception ex)
            {
                log("清理目录跳过 " + path + ": " + ex.Message);
            }
        }

        private sealed class UninstallForm : Form
        {
            private readonly string _installDir;
            private readonly CheckBox _chkPurge;
            private readonly TextBox _logBox;
            private readonly Button _btnUninstall;
            private readonly Button _btnCancel;
            private bool _finished;

            public UninstallForm(string installDir)
            {
                _installDir = installDir;
                Text = "卸载 - 融智云考 · 印务台";
                Size = new Size(520, 350);
                StartPosition = FormStartPosition.CenterScreen;
                FormBorderStyle = FormBorderStyle.FixedDialog;
                MaximizeBox = false;
                BackColor = Color.FromArgb(250, 249, 246);
                Font = new Font("Microsoft YaHei UI", 9.5f);

                var lblTitle = new Label
                {
                    Text = "确认卸载「融智云考 · 印务台」",
                    Font = new Font("Microsoft YaHei UI", 13f, FontStyle.Bold),
                    ForeColor = Color.FromArgb(20, 20, 19),
                    Location = new Point(22, 18),
                    AutoSize = true,
                };
                var lblPath = new Label
                {
                    Text = "安装路径：" + installDir,
                    ForeColor = Color.FromArgb(90, 90, 86),
                    Location = new Point(24, 52),
                    Size = new Size(455, 36),
                };
                _chkPurge = new CheckBox
                {
                    Text = "同时清理本地登录缓存、日志与配置目录 (%USERPROFILE%\\.cctr_export)",
                    Location = new Point(24, 92),
                    Size = new Size(460, 24),
                    ForeColor = Color.FromArgb(60, 60, 56),
                };
                _logBox = new TextBox
                {
                    Location = new Point(24, 126),
                    Size = new Size(456, 122),
                    Multiline = true,
                    ReadOnly = true,
                    ScrollBars = ScrollBars.Vertical,
                    BackColor = Color.White,
                    Text = "点击下方「确认卸载」将删除程序文件、快捷方式及系统卸载条目（默认保留已导出的 PDF/ZIP 文档）。",
                };
                _btnUninstall = new Button
                {
                    Text = "确认卸载",
                    Location = new Point(282, 262),
                    Size = new Size(98, 34),
                    BackColor = Color.FromArgb(185, 28, 28),
                    ForeColor = Color.White,
                    FlatStyle = FlatStyle.Flat,
                };
                _btnUninstall.FlatAppearance.BorderSize = 0;
                _btnCancel = new Button
                {
                    Text = "取消",
                    Location = new Point(390, 262),
                    Size = new Size(90, 34),
                    BackColor = Color.FromArgb(236, 234, 229),
                    FlatStyle = FlatStyle.Flat,
                };

                _btnCancel.Click += (s, e) => Close();
                _btnUninstall.Click += OnUninstallClick;

                Controls.AddRange(new Control[] { lblTitle, lblPath, _chkPurge, _logBox, _btnUninstall, _btnCancel });
            }

            private async void OnUninstallClick(object sender, EventArgs e)
            {
                if (_finished)
                {
                    ScheduleSelfDelete(_installDir);
                    Close();
                    return;
                }
                _btnUninstall.Enabled = false;
                _btnCancel.Enabled = false;
                _chkPurge.Enabled = false;
                _logBox.Clear();
                bool purge = _chkPurge.Checked;
                await Task.Run(() =>
                {
                    PerformUninstall(_installDir, purge, line =>
                    {
                        if (!IsDisposed)
                        {
                            BeginInvoke((Action)(() => _logBox.AppendText(line + Environment.NewLine)));
                        }
                    });
                });
                _finished = true;
                _btnUninstall.Text = "完成";
                _btnUninstall.BackColor = Color.FromArgb(20, 20, 19);
                _btnUninstall.Enabled = true;
                _logBox.AppendText(Environment.NewLine + "已成功卸载！点击「完成」即可自动清理残留目录。" + Environment.NewLine);
            }

            protected override void OnFormClosed(FormClosedEventArgs e)
            {
                if (_finished)
                {
                    ScheduleSelfDelete(_installDir);
                }
                base.OnFormClosed(e);
            }
        }
    }
}
