// Fulyn.exe: hosts Fulyn in its own window with its own taskbar identity, so it can be
// pinned like any Windows app. On start it runs ..\Fulyn.ps1 -Prepare (which starts Docker,
// Ollama and the containers), shows its progress, then loads http://localhost:3000.
//
// Written for the C# 5 compiler that ships with Windows (see Build-App.ps1).

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Fulyn
{
    static class Program
    {
        [DllImport("user32.dll")]
        static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        static extern bool SetProcessDpiAwarenessContext(IntPtr value);

        [DllImport("user32.dll")]
        static extern bool SetProcessDPIAware();

        [STAThread]
        static void Main()
        {
            bool isFirst;
            using (var mutex = new Mutex(true, "Fulyn.App.SingleInstance", out isFirst))
            {
                if (!isFirst)
                {
                    FocusExisting();
                    return;
                }
                // Render at the display's real resolution instead of being bitmap-stretched
                // by Windows on scaled displays (which blurs the logo, text and web content).
                if (!SetProcessDpiAwarenessContext(new IntPtr(-4))) // PER_MONITOR_AWARE_V2
                    SetProcessDPIAware();
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new MainForm());
            }
        }

        static void FocusExisting()
        {
            var current = Process.GetCurrentProcess();
            foreach (var process in Process.GetProcessesByName(current.ProcessName))
            {
                if (process.Id != current.Id && process.MainWindowHandle != IntPtr.Zero)
                {
                    ShowWindow(process.MainWindowHandle, 9); // SW_RESTORE
                    SetForegroundWindow(process.MainWindowHandle);
                    return;
                }
            }
        }
    }

    class MainForm : Form
    {
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        const string AppUrl = "http://localhost:3000/";
        static readonly Color Background = ColorTranslator.FromHtml("#0e1420");

        readonly string launcherDir;
        readonly string dataDir;
        readonly Panel splash = new Panel();
        readonly Label status = new Label();
        readonly Button retry = new Button();
        readonly WebView2 web = new WebView2();

        public MainForm()
        {
            launcherDir = Path.GetFullPath(Path.Combine(Application.StartupPath, ".."));
            dataDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Fulyn");
            Directory.CreateDirectory(dataDir);

            Text = "Fulyn";
            // The .ico holds 16-256px images, so the title bar and taskbar get a sharp size.
            var icoPath = Path.Combine(Application.StartupPath, "fulyn.ico");
            Icon = File.Exists(icoPath)
                ? new Icon(icoPath)
                : Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            BackColor = Background;
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(Scale_(1280), Scale_(860));
            MinimumSize = new Size(Scale_(480), Scale_(400));
            RestoreBounds_();

            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = Background;
            web.Visible = false;
            Controls.Add(web);

            BuildSplash();
            Controls.Add(splash);

            Shown += delegate { Prepare(); };
            FormClosing += delegate { SaveBounds(); };
        }

        void BuildSplash()
        {
            splash.Dock = DockStyle.Fill;
            splash.BackColor = Background;

            var logo = new PictureBox();
            logo.SizeMode = PictureBoxSizeMode.CenterImage;
            logo.BackColor = Background;

            var title = new Label();
            title.Text = "Fulyn";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 20);
            title.AutoSize = true;

            status.Text = "Starting...";
            status.ForeColor = ColorTranslator.FromHtml("#9aa7c2");
            status.Font = new Font("Segoe UI", 10);
            status.TextAlign = ContentAlignment.TopCenter;
            status.Size = new Size(Scale_(460), Scale_(64));

            retry.Text = "Try again";
            retry.Visible = false;
            retry.FlatStyle = FlatStyle.Flat;
            retry.ForeColor = Color.White;
            retry.Size = new Size(Scale_(110), Scale_(32));
            retry.Click += delegate { Prepare(); };

            splash.Controls.Add(logo);
            splash.Controls.Add(title);
            splash.Controls.Add(status);
            splash.Controls.Add(retry);

            int logoSize = 0;
            EventHandler layout = delegate
            {
                int size = Scale_(96);
                if (size != logoSize)
                {
                    // Downscale the 512px artwork with high-quality filtering for this DPI.
                    logoSize = size;
                    var old = logo.Image;
                    logo.Image = LoadLogo(size);
                    if (old != null) old.Dispose();
                    logo.Size = new Size(size, size);
                    status.Size = new Size(Scale_(460), Scale_(64));
                    retry.Size = new Size(Scale_(110), Scale_(32));
                }
                int cx = splash.ClientSize.Width / 2;
                int top = Math.Max(Scale_(20), splash.ClientSize.Height / 2 - Scale_(130));
                logo.Location = new Point(cx - size / 2, top);
                title.Location = new Point(cx - title.Width / 2, top + Scale_(108));
                status.Location = new Point(cx - status.Width / 2, top + Scale_(156));
                retry.Location = new Point(cx - retry.Width / 2, top + Scale_(220));
            };
            splash.Resize += layout;
            splash.HandleCreated += layout;
            DpiChanged += delegate { layout(this, EventArgs.Empty); };
        }

        int Scale_(int value)
        {
            return (int)Math.Round(value * DeviceDpi / 96.0);
        }

        Image LoadLogo(int size)
        {
            var bitmap = new Bitmap(size, size);
            var path = Path.Combine(Application.StartupPath, "icon.png");
            using (var g = Graphics.FromImage(bitmap))
            {
                g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality;
                g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
                g.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighQuality;
                g.Clear(Background);
                if (File.Exists(path))
                {
                    using (var source = Image.FromFile(path))
                        g.DrawImage(source, 0, 0, size, size);
                }
                else
                {
                    using (var icon = new Icon(Icon, 256, 256))
                        g.DrawIcon(icon, new Rectangle(0, 0, size, size));
                }
            }
            return bitmap;
        }

        // Windows 11: dark title bar in Fulyn's colours instead of the default white one.
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            SetWindowAttribute(20, 1);                                  // immersive dark mode
            SetWindowAttribute(35, ToColorRef(Background));             // caption colour
            SetWindowAttribute(36, ToColorRef(Color.White));            // caption text colour
            SetWindowAttribute(34, ToColorRef(ColorTranslator.FromHtml("#1b2438"))); // border
        }

        void SetWindowAttribute(int attribute, int value)
        {
            try { DwmSetWindowAttribute(Handle, attribute, ref value, sizeof(int)); }
            catch (Exception) { /* older Windows: keep the default title bar */ }
        }

        static int ToColorRef(Color color)
        {
            return color.R | (color.G << 8) | (color.B << 16);
        }

        void SetStatus(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(SetStatus), text); return; }
            status.Text = text;
        }

        // Runs ..\Fulyn.ps1 -Prepare in the background and follows its progress lines.
        void Prepare()
        {
            retry.Visible = false;
            SetStatus("Starting...");
            var script = Path.Combine(launcherDir, "Fulyn.ps1");
            var thread = new Thread(delegate ()
            {
                string error = null;
                try
                {
                    var info = new ProcessStartInfo(
                        Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe"),
                        "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" -Prepare");
                    info.UseShellExecute = false;
                    info.CreateNoWindow = true;
                    info.RedirectStandardOutput = true;
                    using (var process = Process.Start(info))
                    {
                        string line;
                        while ((line = process.StandardOutput.ReadLine()) != null)
                        {
                            if (line.StartsWith("STATUS: ")) SetStatus(line.Substring(8));
                            else if (line.StartsWith("ERROR: ")) error = line.Substring(7);
                        }
                        process.WaitForExit();
                        if (process.ExitCode != 0 && error == null)
                            error = "Fulyn could not start (exit code " + process.ExitCode + ").";
                    }
                }
                catch (Exception ex)
                {
                    error = "Could not run the launcher script: " + ex.Message;
                }
                BeginInvoke(new Action<string>(Prepared), error);
            });
            thread.IsBackground = true;
            thread.Start();
        }

        async void Prepared(string error)
        {
            if (error != null)
            {
                SetStatus(error + "\n\nLog: " + Path.Combine(launcherDir, @"logs\launcher.log"));
                retry.Visible = true;
                return;
            }
            SetStatus("Opening...");
            try
            {
                if (web.CoreWebView2 == null)
                {
                    var environment = await CoreWebView2Environment.CreateAsync(
                        null, Path.Combine(dataDir, "WebView2"));
                    await web.EnsureCoreWebView2Async(environment);
                    web.CoreWebView2.NewWindowRequested += OnNewWindow;
                    web.CoreWebView2.NavigationStarting += OnNavigationStarting;
                    web.CoreWebView2.DocumentTitleChanged += delegate { Text = "Fulyn"; };
                }
                web.Source = new Uri(AppUrl);
                web.Visible = true;
                splash.Visible = false;
            }
            catch (Exception ex)
            {
                SetStatus("The WebView2 runtime could not start: " + ex.Message);
                retry.Visible = true;
            }
        }

        static bool IsFulyn(string uri)
        {
            return uri.StartsWith("http://localhost:3000", StringComparison.OrdinalIgnoreCase)
                || uri.StartsWith("http://127.0.0.1:3000", StringComparison.OrdinalIgnoreCase);
        }

        // Links outside Fulyn open in the default browser.
        void OnNewWindow(object sender, CoreWebView2NewWindowRequestedEventArgs e)
        {
            e.Handled = true;
            if (IsFulyn(e.Uri)) web.CoreWebView2.Navigate(e.Uri);
            else OpenExternally(e.Uri);
        }

        void OnNavigationStarting(object sender, CoreWebView2NavigationStartingEventArgs e)
        {
            if (!IsFulyn(e.Uri) && !e.Uri.StartsWith("about:") && !e.Uri.StartsWith("data:"))
            {
                e.Cancel = true;
                OpenExternally(e.Uri);
            }
        }

        static void OpenExternally(string uri)
        {
            if (uri.StartsWith("http://") || uri.StartsWith("https://"))
                Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
        }

        // --- Remember window size and position ------------------------------------------

        string BoundsFile { get { return Path.Combine(dataDir, "window.txt"); } }

        void RestoreBounds_()
        {
            try
            {
                var parts = File.ReadAllText(BoundsFile).Split(',');
                var bounds = new Rectangle(int.Parse(parts[0]), int.Parse(parts[1]),
                                           int.Parse(parts[2]), int.Parse(parts[3]));
                if (Screen.AllScreens.Length > 0 && IsVisibleOnAnyScreen(bounds))
                {
                    StartPosition = FormStartPosition.Manual;
                    Bounds = bounds;
                }
                if (parts.Length > 4 && parts[4] == "max") WindowState = FormWindowState.Maximized;
            }
            catch (Exception)
            {
                // First run or unreadable file: use the defaults.
            }
        }

        static bool IsVisibleOnAnyScreen(Rectangle bounds)
        {
            foreach (var screen in Screen.AllScreens)
                if (screen.WorkingArea.IntersectsWith(bounds)) return true;
            return false;
        }

        void SaveBounds()
        {
            try
            {
                var b = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
                File.WriteAllText(BoundsFile, string.Join(",", new[] {
                    b.X.ToString(), b.Y.ToString(), b.Width.ToString(), b.Height.ToString(),
                    WindowState == FormWindowState.Maximized ? "max" : "normal" }));
            }
            catch (Exception)
            {
                // Not important enough to bother the user.
            }
        }
    }
}
