// Local3D launcher - a thin supervisor, not an application.
//
// It (1) makes sure the pinned, official ComfyUI portable build and the model files are present (download + hash
// verification are delegated to curl.exe / tar.exe / huggingface_hub), (2) starts ComfyUI on a private localhost port,
// (3) opens the Local3D app in a chromeless Microsoft Edge window, and (4) tears everything down when that window
// closes. Every ComfyUI process lives in a Windows Job Object, so nothing is left behind even if this exe is killed.
//
// Built with the C# compiler that ships with Windows (no SDK needed): see scripts/build_launcher.ps1. C# 5 syntax.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Management;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Local3D")]
[assembly: AssemblyVersion("0.1.1.0")]
[assembly: AssemblyInformationalVersion("0.1.1")]
[assembly: AssemblyProduct("Local3D")]
[assembly: AssemblyCopyright("Copyright (c) 2026 Arash Sajjadi. MIT License.")]

namespace Local3D
{
    internal static class Program
    {
        public const string Version = "0.1.1";

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                Cli cli = new Cli(args);
                Ui.AutoYes = cli.Has("--yes");
                if (cli.Has("--version")) { Native.AttachConsole(-1); Console.WriteLine("Local3D " + Version); return 0; }   // stdout, never a dialog (CI-friendly)
                Env env = new Env();
                Ui.LogDir = env.LogDir;
                if (cli.Has("--diagnostics")) { Diagnostics_.Show(env); return 0; }
                bool created;
                using (Mutex single = new Mutex(true, "Local3D.Launcher.v1", out created))
                {
                    if (!created)
                    {
                        if (Session.ReopenWindow(env, cli)) return 0;
                        if (!Ui.AutoYes) Ui.Info("Local3D", "Local3D is already starting. Look for the Local3D window in the taskbar; the app opens there when it is ready.");
                        return 0;
                    }
                    return new Session(env, cli).Run();
                }
            }
            catch (Exception ex)
            {
                Ui.Error("Local3D could not start.", "Please try again. If it keeps failing, copy the details below into a bug report.", ex.ToString());
                return 1;
            }
        }
    }

    // ------------------------------------------------------------------------------------------------------------
    internal sealed class Cli
    {
        private readonly List<string> a;
        public Cli(string[] args) { a = new List<string>(args); }
        public bool Has(string flag) { return a.Contains(flag); }
        public string Value(string flag, string fallback)
        {
            int i = a.IndexOf(flag);
            return (i >= 0 && i + 1 < a.Count) ? a[i + 1] : fallback;
        }
    }

    // Paths + user settings. Environment variables win (handy for development), then settings.json, then defaults.
    internal sealed class Env
    {
        public string Root;        // folder that contains data\, scripts\, local3d_pack\
        public string DataDir;     // runtime, workspace, logs, browser profile
        public string ModelsDir;
        public string OutputDir;   // Documents\Local3D: generated models, reference pictures, and input pictures
        public string SettingsFile;
        public Dictionary<string, object> Runtime;

        public Env()
        {
            Root = FindRoot();
            string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            string defaultData = Path.Combine(local, "Local3D");
            SettingsFile = Path.Combine(defaultData, "settings.json");
            Dictionary<string, object> s = Json.ReadFileLenient(SettingsFile);
            DataDir = Pick("LOCAL3D_DATA_DIR", s, "dataDir", defaultData);
            ModelsDir = Pick("LOCAL3D_MODELS_DIR", s, "modelsDir", Path.Combine(DataDir, "models"));
            OutputDir = Pick("LOCAL3D_OUTPUT_DIR", s, "outputDir",
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Local3D"));
            Runtime = Json.ReadFile(Path.Combine(Root, "data", "runtime.json"));
            Directory.CreateDirectory(Path.Combine(DataDir, "logs"));
        }

        private static string Pick(string envName, Dictionary<string, object> s, string key, string fallback)
        {
            string e = Environment.GetEnvironmentVariable(envName);
            if (!string.IsNullOrEmpty(e)) return e;
            object v;
            if (s != null && s.TryGetValue(key, out v) && v is string && ((string)v).Length > 0) return (string)v;
            return fallback;
        }

        private static string FindRoot()
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            for (int i = 0; i < 4 && dir != null; i++)
            {
                if (File.Exists(Path.Combine(dir, "data", "runtime.json"))) return dir;
                DirectoryInfo p = Directory.GetParent(dir.TrimEnd('\\'));
                dir = p == null ? null : p.FullName;
            }
            throw new InvalidOperationException("Local3D files are incomplete (data\\runtime.json not found). Please reinstall Local3D.");
        }

        public void SaveSettings()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsFile));
            Dictionary<string, object> s = new Dictionary<string, object>();
            s["dataDir"] = DataDir; s["modelsDir"] = ModelsDir; s["outputDir"] = OutputDir;
            File.WriteAllText(SettingsFile, new JavaScriptSerializer().Serialize(s), new UTF8Encoding(false));
        }

        public string RuntimeDir { get { return Path.Combine(DataDir, "runtime", "ComfyUI_windows_portable"); } }
        public string Python { get { return Path.Combine(RuntimeDir, "python_embeded", "python.exe"); } }
        public string Workspace { get { return Path.Combine(DataDir, "workspace"); } }
        public string LogDir { get { return Path.Combine(DataDir, "logs"); } }
        public string RuntimeTag { get { return Json.Str(Runtime, "tag"); } }
    }

    internal static class Json
    {
        // settings.json is edited by hand: accept "D:\Models" (single backslashes) as well as "D:\\Models" and "D:/Models".
        public static Dictionary<string, object> ReadFileLenient(string path)
        {
            try
            {
                if (!File.Exists(path)) return new Dictionary<string, object>();
                string text = File.ReadAllText(path, Encoding.UTF8);
                try { return Parse(text) ?? new Dictionary<string, object>(); }
                catch { }
                string fixedText = System.Text.RegularExpressions.Regex.Replace(text, @"(?<!\\)\\(?!\\)", @"\\");
                return Parse(fixedText) ?? new Dictionary<string, object>();
            }
            catch { return new Dictionary<string, object>(); }
        }

        public static Dictionary<string, object> ReadFile(string path)
        {
            try
            {
                if (!File.Exists(path)) return new Dictionary<string, object>();
                return Parse(File.ReadAllText(path, Encoding.UTF8));
            }
            catch { return new Dictionary<string, object>(); }
        }
        public static Dictionary<string, object> Parse(string text)
        {
            JavaScriptSerializer js = new JavaScriptSerializer();
            js.MaxJsonLength = int.MaxValue;
            return js.DeserializeObject(text) as Dictionary<string, object>;
        }
        public static string Str(Dictionary<string, object> d, string k)
        {
            object v; return (d != null && d.TryGetValue(k, out v) && v != null) ? v.ToString() : "";
        }
        public static long Long(Dictionary<string, object> d, string k)
        {
            object v; long r;
            return (d != null && d.TryGetValue(k, out v) && v != null && long.TryParse(v.ToString(), out r)) ? r : 0;
        }
    }

    internal static class Log
    {
        private static readonly object gate = new object();
        public static string File_;
        public static void Write(string msg)
        {
            try
            {
                lock (gate)
                {
                    if (File_ != null) File.AppendAllText(File_, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + msg + Environment.NewLine);
                }
            }
            catch { }
        }
    }

    // ------------------------------------------------------------------------------------------------------------
    internal static class Ui
    {
        public static bool AutoYes;   // --yes: accept the default choice of every consent dialog (unattended installs, tests)
        public static string LogDir;  // shown in error dialogs
        public const string HelpUrl = "https://github.com/arashsajjadi/Local3D/blob/main/docs/TROUBLESHOOTING.md";

        public static Icon AppIcon()
        {
            try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { return null; }
        }

        public static void Info(string title, string text) { MessageBox.Show(text, title, MessageBoxButtons.OK, MessageBoxIcon.Information); }

        public static bool Confirm(string title, string text, string ok)
        {
            if (AutoYes) return true;
            return MessageBox.Show(text, title, MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK;
        }

        // Friendly summary -> suggested fix -> collapsible technical details.
        public static void Error(string summary, string suggestion, string details)
        {
            Log.Write("ERROR: " + summary + " | " + details);
            using (Form f = new Form())
            {
                f.Text = "Local3D";
                f.Icon = AppIcon();
                f.StartPosition = FormStartPosition.CenterScreen;
                f.FormBorderStyle = FormBorderStyle.FixedDialog;
                f.MaximizeBox = false; f.MinimizeBox = false;
                f.ClientSize = new Size(560, 176);
                Label s = new Label { Text = summary, Left = 16, Top = 14, Width = 528, Height = 40, Font = new Font(SystemFonts.MessageBoxFont, FontStyle.Bold) };
                Label g = new Label { Text = suggestion, Left = 16, Top = 56, Width = 528, Height = 64 };
                TextBox t = new TextBox { Text = details ?? "", Left = 16, Top = 182, Width = 528, Height = 150, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, Visible = false, WordWrap = false, AccessibleName = "Technical details" };
                Button more = new Button { Text = "Technical details", Left = 16, Top = 134, Width = 130, Height = 28 };
                Button logs = new Button { Text = "Open log folder", Left = 152, Top = 134, Width = 130, Height = 28, Enabled = !string.IsNullOrEmpty(LogDir) };
                Button help = new Button { Text = "Help online", Left = 288, Top = 134, Width = 100, Height = 28 };
                Button ok = new Button { Text = "Close", Left = 454, Top = 134, Width = 90, Height = 28, DialogResult = DialogResult.OK };
                more.Click += delegate
                {
                    t.Visible = !t.Visible;
                    f.ClientSize = new Size(560, t.Visible ? 348 : 176);
                };
                logs.Click += delegate { try { Process.Start("explorer.exe", Proc.Q(LogDir)); } catch { } };
                help.Click += delegate { try { Process.Start(HelpUrl); } catch { } };
                f.Controls.AddRange(new Control[] { s, g, t, more, logs, help, ok });
                f.AcceptButton = ok; f.CancelButton = ok;
                f.ShowDialog();
            }
        }
    }

    // Shown when the app window does not become ready in time: the person is never left watching a progress bar.
    internal static class StallDialog
    {
        // returns "retry", "repair", "diag" or "quit"
        public static string Ask(string details)
        {
            string result = "quit";
            using (Form f = new Form())
            {
                f.Text = "Local3D";
                f.Icon = Ui.AppIcon();
                f.StartPosition = FormStartPosition.CenterScreen;
                f.FormBorderStyle = FormBorderStyle.FixedDialog; f.MaximizeBox = false; f.MinimizeBox = false;
                f.ClientSize = new Size(600, 350);
                Label s = new Label { Text = "Local3D could not finish loading the interface.", Left = 16, Top = 14, Width = 568, Height = 26, Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 11f, FontStyle.Bold) };
                Label g = new Label { Left = 16, Top = 46, Width = 568, Height = 62,
                    Text = "The engine is running, but the app window did not become ready in time. Retry reopens the window. " +
                           "Repair interface resets only Local3D's own browser data (your models and results are not touched) and reopens it." };
                TextBox t = new TextBox { Text = (details ?? "").Replace("\r\n", "\n").Replace("\n", "\r\n"), Left = 16, Top = 112, Width = 568, Height = 180, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false, AccessibleName = "Technical details" };
                Button retry = new Button { Text = "Retry", Left = 16, Top = 304, Width = 100, Height = 30 };
                Button repair = new Button { Text = "Repair interface", Left = 124, Top = 304, Width = 130, Height = 30 };
                Button diag = new Button { Text = "Open diagnostics", Left = 262, Top = 304, Width = 130, Height = 30 };
                Button quit = new Button { Text = "Quit", Left = 484, Top = 304, Width = 100, Height = 30 };
                retry.Click += delegate { result = "retry"; f.Close(); };
                repair.Click += delegate { result = "repair"; f.Close(); };
                diag.Click += delegate { result = "diag"; f.Close(); };
                quit.Click += delegate { result = "quit"; f.Close(); };
                f.Controls.AddRange(new Control[] { s, g, t, retry, repair, diag, quit });
                f.AcceptButton = retry; f.CancelButton = quit;
                f.ShowDialog();
            }
            return result;
        }
    }

    // Small status window used during first run and startup. Closing it (or "Quit") shuts Local3D down.
    internal sealed class StatusForm : Form
    {
        private readonly Label title = new Label();
        private readonly Label status = new Label();
        private readonly Label detail = new Label();
        private readonly ProgressBar bar = new ProgressBar();
        private readonly Button quit = new Button();
        public volatile bool CancelRequested;
        public event Action Cancelled;

        public StatusForm()
        {
            Text = "Local3D";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            ClientSize = new Size(520, 168);
            Icon = Ui.AppIcon();
            title.Text = "Local3D";
            title.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 16f, FontStyle.Bold);
            title.SetBounds(18, 12, 480, 34);
            status.SetBounds(20, 54, 480, 22);
            status.Font = new Font(SystemFonts.MessageBoxFont, FontStyle.Regular);
            bar.SetBounds(20, 82, 480, 18);
            detail.SetBounds(20, 106, 480, 20);
            detail.ForeColor = SystemColors.GrayText;
            quit.Text = "Quit";
            quit.SetBounds(418, 130, 82, 26);
            quit.Click += delegate { CancelRequested = true; if (Cancelled != null) Cancelled(); Close(); };
            Label ver = new Label { Text = "v" + Program.Version, ForeColor = SystemColors.GrayText, Left = 20, Top = 134, Width = 200, Height = 18 };
            Controls.AddRange(new Control[] { title, status, bar, detail, quit, ver });
            FormClosing += delegate(object s, FormClosingEventArgs e)
            {
                if (e.CloseReason == CloseReason.UserClosing) { CancelRequested = true; if (Cancelled != null) Cancelled(); }
            };
        }

        public void Set(string text, string sub)
        {
            Post(delegate { status.Text = text; detail.Text = sub ?? ""; });
        }

        public void Progress(long done, long total)
        {
            Post(delegate
            {
                if (total <= 0) { bar.Style = ProgressBarStyle.Marquee; return; }
                bar.Style = ProgressBarStyle.Continuous;
                bar.Maximum = 1000;
                bar.Value = (int)Math.Max(0, Math.Min(1000, done * 1000 / total));
            });
        }

        public void Indeterminate() { Post(delegate { bar.Style = ProgressBarStyle.Marquee; }); }

        private void Post(MethodInvoker m)
        {
            if (IsDisposed || !IsHandleCreated) return;
            try { BeginInvoke(m); } catch { }
        }
    }

    // ------------------------------------------------------------------------------------------------------------
    internal static class Native
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr CreateJobObject(IntPtr a, string name);
        [DllImport("kernel32.dll")] public static extern bool SetInformationJobObject(IntPtr job, int cls, IntPtr info, uint len);
        [DllImport("kernel32.dll")] public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr proc);
        [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll")] public static extern bool AttachConsole(int pid);

        [StructLayout(LayoutKind.Sequential)]
        public struct BASIC { public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinWs, MaxWs; public uint ActiveLimit; public UIntPtr Affinity; public uint Priority, Sched; }
        [StructLayout(LayoutKind.Sequential)]
        public struct IOC { public ulong a, b, c, d, e, f; }
        [StructLayout(LayoutKind.Sequential)]
        public struct EXTENDED { public BASIC Basic; public IOC Io; public UIntPtr ProcMem, JobMem, PeakProc, PeakJob; }

        // Everything assigned to this job dies when the handle closes (i.e. when the launcher exits for any reason).
        public static IntPtr KillOnCloseJob()
        {
            IntPtr job = CreateJobObject(IntPtr.Zero, null);
            EXTENDED info = new EXTENDED();
            info.Basic.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            int size = Marshal.SizeOf(typeof(EXTENDED));
            IntPtr p = Marshal.AllocHGlobal(size);
            try { Marshal.StructureToPtr(info, p, false); SetInformationJobObject(job, 9, p, (uint)size); }
            finally { Marshal.FreeHGlobal(p); }
            return job;
        }
    }

    // ------------------------------------------------------------------------------------------------------------
    internal sealed class Session
    {
        private readonly Env env;
        private readonly Cli cli;
        private StatusForm form;
        private Process server;
        private Process browser;
        private IntPtr job = IntPtr.Zero;
        private int port;
        private string gpuClass = "legacy";   // blackwell (RTX 50) | ada (RTX 40) | legacy: picks the FLUX.2 weight format
        private volatile int exitCode;
        private readonly List<Process> children = new List<Process>();

        public Session(Env e, Cli c) { env = e; cli = c; }

        private string AppName
        {
            get
            {
                string a = cli.Value("--app", "image");
                if (a == "prompt") return "Local3D_Prompt_to_3D.app";
                if (a == "reference") return "Local3D_Reference_Pictures.app";
                return "Local3D_Image_to_3D.app";
            }
        }

        private string Url(int p)
        {
            return "http://127.0.0.1:" + p + "/?template=" + AppName + "&source=local3d_pack&mode=linear";
        }

        // A second launch just reopens a window for the running session.
        public static bool ReopenWindow(Env env, Cli cli)
        {
            Dictionary<string, object> s = Json.ReadFile(Path.Combine(env.DataDir, "session.json"));
            int p = (int)Json.Long(s, "port");
            if (p == 0 || !Http.Ok("http://127.0.0.1:" + p + "/system_stats")) return false;
            Session tmp = new Session(env, cli);
            tmp.OpenBrowser(p);
            return true;
        }

        public int Run()
        {
            Log.File_ = Path.Combine(env.LogDir, "launcher.log");
            Ui.LogDir = env.LogDir;
            Log.Write("Local3D " + Program.Version + " starting; data=" + env.DataDir);
            try { File.Delete(Path.Combine(env.DataDir, "session.json")); } catch { }   // left over from a crash: never reopen a dead port
            job = Native.KillOnCloseJob();
            form = new StatusForm();
            form.Cancelled += delegate { Shutdown(); };
            form.Shown += delegate { Thread t = new Thread(Work); t.IsBackground = true; t.SetApartmentState(ApartmentState.STA); t.Start(); };
            Application.Run(form);
            Shutdown();
            return exitCode;
        }

        private void Fail(int code, string summary, string suggestion, string details)
        {
            exitCode = code;
            Invoke(delegate { Ui.Error(summary, suggestion, details); return null; });
            Close();
        }

        private void Close() { try { form.BeginInvoke((MethodInvoker)delegate { form.Close(); }); } catch { } }

        // --- worker -------------------------------------------------------------------------------------------
        private void Work()
        {
            try
            {
                if (!CheckGpu()) return;
                if (!EnsureRuntime()) return;
                if (!EnsureModels()) return;
                if (!StartServer()) return;
                KillProfileBrowsers();   // a leftover window of ours would swallow the new one
                OpenBrowser(port);
                if (browser != null && !AwaitInterface()) return;
                form.Set("Local3D is running", browser != null ? "You can close this window; Local3D stops when the app window is closed."
                                                                : "Local3D is open in your web browser. Keep THIS window open and click Quit when you are done.");
                form.Progress(1, 1);
                if (browser != null)   // without a tracked app window the status window stays: it is the only way to quit
                    try { form.BeginInvoke((MethodInvoker)delegate { form.WindowState = FormWindowState.Minimized; form.ShowInTaskbar = false; form.Hide(); }); } catch { }
                WaitForExit();
            }
            catch (Exception ex)
            {
                Fail(1, "Local3D could not start.", "Please try again. If it keeps failing, copy the technical details into a bug report.", ex.ToString());
            }
            Close();
        }

        private bool CheckGpu()
        {
            form.Set("Checking your graphics card...", null);
            string o = Proc.Capture("nvidia-smi", "--query-gpu=name,memory.total,compute_cap --format=csv,noheader,nounits", 8000);
            Log.Write("GPU: " + (o ?? "(nvidia-smi unavailable)").Trim().Replace("\r", "").Replace("\n", " | "));
            string first = null;   // ComfyUI uses the first GPU
            if (!string.IsNullOrEmpty(o))
                foreach (string ln in o.Split('\n')) if (ln.Trim().IndexOf(',') > 0) { first = ln.Trim(); break; }
            if (first == null)
                return AskContinue("Local3D needs an NVIDIA graphics card (RTX 20-series or newer, 12 GB or more recommended) with an up-to-date driver, and none was found.\n\n" +
                    "Without one, 3D generation will fail or be extremely slow. Install the latest NVIDIA driver from nvidia.com and try again.\n\nContinue anyway?");
            long mib; string[] parts = first.Split(',');
            double cc = 0;
            bool haveCc = parts.Length > 2 && double.TryParse(parts[2].Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out cc);
            if (haveCc) gpuClass = cc >= 10 ? "blackwell" : (cc >= 8.9 ? "ada" : "legacy");
            Log.Write("GPU class: " + gpuClass);
            if (haveCc && cc < 7.5)
                return AskContinue("Your graphics card (" + parts[0].Trim() + ") is older than the RTX 20-series, which Local3D's 3D engine needs.\n\nContinue anyway? (It will most likely fail.)");
            if (parts.Length > 1 && long.TryParse(parts[1].Trim(), out mib) && mib < 11500 && !File.Exists(Path.Combine(env.DataDir, "vram-warned")))
            {
                Invoke(delegate
                {
                    Ui.Info("Local3D", "Your graphics card has " + (mib / 1024) + " GB of memory.\n\nLocal3D works best with 12 GB or more. Use the Fast quality setting; " +
                        "Balanced and Maximum may run out of GPU memory.");
                    return null;
                });
                try { File.WriteAllText(Path.Combine(env.DataDir, "vram-warned"), "1"); } catch { }
            }
            return true;
        }

        // Warning with "No" as the default (and for Esc): the person should have to choose to go on.
        private bool AskContinue(string text)
        {
            if (Ui.AutoYes) return true;   // unattended: continue (and let the engine report what it can)
            DialogResult r = (DialogResult)Invoke(delegate
            {
                return MessageBox.Show(text, "Local3D", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
            });
            if (r != DialogResult.Yes) { Close(); return false; }
            return true;
        }

        private object Invoke(Func<object> f) { object r = null; form.Invoke((MethodInvoker)delegate { r = f(); }); return r; }

        private static string Gb(long bytes) { return (bytes / 1e9).ToString("0.0") + " GB"; }

        private long FreeBytes(string path)
        {
            try
            {
                string root = Path.GetPathRoot(Path.GetFullPath(path));
                return new DriveInfo(root).AvailableFreeSpace;
            }
            catch { return long.MaxValue; }
        }

        private static string Sha256(string path)
        {
            using (SHA256 h = SHA256.Create())
            using (FileStream fs = File.OpenRead(path))
            {
                byte[] d = h.ComputeHash(fs);
                StringBuilder sb = new StringBuilder();
                foreach (byte b in d) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        // --- runtime ------------------------------------------------------------------------------------------
        private bool EnsureRuntime()
        {
            string marker = Path.Combine(env.DataDir, "runtime", "runtime.json");
            if (File.Exists(env.Python) && Json.Str(Json.ReadFile(marker), "tag") == env.RuntimeTag) return true;

            long size = Json.Long(env.Runtime, "size");
            long need = size + Json.Long(env.Runtime, "unpacked_size_estimate") + 1000000000L;
            string folder = Path.Combine(env.DataDir, "runtime");
            Directory.CreateDirectory(folder);
            if (FreeBytes(folder) < need)
            {
                Fail(2, "Not enough free disk space for the Local3D runtime.",
                    "Local3D needs about " + Gb(need) + " free on the drive that holds " + env.DataDir + ". Free some space and start Local3D again.",
                    "free=" + FreeBytes(folder) + " need=" + need);
                return false;
            }
            bool ok = (bool)Invoke(delegate
            {
                return Ui.Confirm("Local3D - first start",
                    "Local3D will download the ComfyUI runtime (" + Gb(size) + ") from github.com/Comfy-Org/ComfyUI and unpack it to:\n\n" + env.DataDir +
                    "\n\nIt is the official release, verified with a checksum. This happens once.", "Download");
            });
            if (!ok) { Close(); return false; }

            string archive = Path.Combine(folder, Json.Str(env.Runtime, "asset"));
            form.Set("Downloading the ComfyUI runtime (" + Gb(size) + ")", "From github.com/Comfy-Org/ComfyUI " + env.RuntimeTag);
            bool alreadyComplete = File.Exists(archive) && new FileInfo(archive).Length == size;   // e.g. an earlier run stopped before unpacking
            if (!alreadyComplete)
            {
                Process curl = Proc.Start("curl.exe", "-L --fail --retry 5 --retry-delay 3 --connect-timeout 30 --speed-limit 1000 --speed-time 60 -C - -s -S -o " + Proc.Q(archive) + " " + Proc.Q(Json.Str(env.Runtime, "url")), folder, null);
                AddChild(curl);
                while (!curl.HasExited)
                {
                    if (form.CancelRequested) { Proc.KillTree(curl); return false; }
                    long have = File.Exists(archive) ? new FileInfo(archive).Length : 0;
                    form.Progress(have, size);
                    form.Set("Downloading the ComfyUI runtime (" + Gb(size) + ")", Gb(have) + " of " + Gb(size));
                    Thread.Sleep(400);
                }
                if (curl.ExitCode != 0)
                {
                    Fail(3, "The runtime download did not finish.", "Check your internet connection and start Local3D again - the download resumes where it stopped.", "curl exit code " + curl.ExitCode);
                    return false;
                }
            }
            form.Set("Verifying the download...", "SHA-256 checksum");
            form.Indeterminate();
            string digest = Sha256(archive);
            if (!string.Equals(digest, Json.Str(env.Runtime, "sha256"), StringComparison.OrdinalIgnoreCase))
            {
                try { File.Delete(archive); } catch { }
                Fail(4, "The downloaded runtime failed its checksum and was deleted.", "Start Local3D again to download it again.", "expected " + Json.Str(env.Runtime, "sha256") + " got " + digest);
                return false;
            }
            form.Set("Unpacking the runtime...", "About a minute");
            string tmp = Path.Combine(folder, "_unpack");
            if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
            Directory.CreateDirectory(tmp);
            Process tar = Proc.Start("tar.exe", "-xf " + Proc.Q(archive) + " -C " + Proc.Q(tmp), folder, null);
            AddChild(tar);
            while (!tar.HasExited) { if (form.CancelRequested) { Proc.KillTree(tar); return false; } Thread.Sleep(300); }
            int unpackCode = tar.ExitCode;
            string sevenZip = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"7-Zip\7z.exe");
            if (unpackCode != 0 && File.Exists(sevenZip))   // an installed 7-Zip can read the archive when Windows' own tar cannot
            {
                Log.Write("tar.exe failed (" + unpackCode + "); trying 7-Zip");
                if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
                Directory.CreateDirectory(tmp);
                Process sz = Proc.Start(sevenZip, "x -y -o" + Proc.Q(tmp) + " " + Proc.Q(archive), folder, null);
                AddChild(sz);
                while (!sz.HasExited) { if (form.CancelRequested) { Proc.KillTree(sz); return false; } Thread.Sleep(300); }
                unpackCode = sz.ExitCode;
            }
            if (unpackCode != 0)
            {
                Fail(5, "The runtime could not be unpacked.",
                    "The drive may be full, or this Windows version cannot open .7z archives (Windows 11 or a fully updated Windows 10 is needed). " +
                    "Update Windows, or install the free 7-Zip, then start Local3D again. The download is kept.",
                    "unpack exit code " + unpackCode + ", folder " + folder);
                return false;
            }
            string target = Path.Combine(folder, "ComfyUI_windows_portable");
            if (Directory.Exists(target)) Directory.Delete(target, true);
            Directory.Move(Path.Combine(tmp, "ComfyUI_windows_portable"), target);
            Directory.Delete(tmp, true);
            File.Delete(archive);
            File.WriteAllText(marker, new JavaScriptSerializer().Serialize(new Dictionary<string, object> { { "tag", env.RuntimeTag } }));
            Log.Write("Runtime installed: " + env.RuntimeTag);
            return true;
        }

        // --- models -------------------------------------------------------------------------------------------
        private sealed class ModelState { public long DlCore, DlPrompt, NeedCore, NeedPrompt; public bool Ok; public string Raw; }

        // One call to the provisioning script's --check: what must be downloaded (missing) and what only needs hashing (unverified).
        private ModelState CheckModels(string modelsDir)
        {
            string script = Path.Combine(env.Root, "scripts", "provision_models.py");
            ModelState st = new ModelState();
            st.Raw = Proc.Capture(env.Python, Proc.Q(script) + " --models-dir " + Proc.Q(modelsDir) + " --gpu " + gpuClass + " --pack core --pack prompt --check --json", 120000);
            Dictionary<string, object> check = null;
            try { check = Json.Parse(st.Raw ?? "{}"); } catch { }
            object filesObj; System.Collections.IEnumerable files = null;
            if (check != null && check.TryGetValue("files", out filesObj)) files = filesObj as System.Collections.IEnumerable;
            if (files == null) return st;
            st.Ok = true;
            foreach (object o in files)
            {
                Dictionary<string, object> f = (Dictionary<string, object>)o;
                string status = Json.Str(f, "status");
                if (status == "ok") continue;
                bool core = Json.Str(f, "pack") == "core";
                long size = Json.Long(f, "size");
                if (core) st.NeedCore += size; else st.NeedPrompt += size;
                if (status == "missing") { if (core) st.DlCore += size; else st.DlPrompt += size; }
            }
            return st;
        }

        private bool EnsureModels()
        {
            string script = Path.Combine(env.Root, "scripts", "provision_models.py");
            form.Set("Checking model files...", null);
            form.Indeterminate();
            ModelState st = CheckModels(env.ModelsDir);
            if (!st.Ok)
            {
                Fail(1, "Local3D could not check its model files.", "Restart Local3D. If it keeps happening, open the log folder and send the log in a bug report.", st.Raw ?? "(the check produced no output)");
                return false;
            }
            string baseArgs = Proc.Q(script) + " --models-dir " + Proc.Q(env.ModelsDir) + " --gpu " + gpuClass;
            // the prompt pack is optional: once declined, only "Local3D.exe --models" and the Prompt/Reference shortcuts ask again
            string declined = Path.Combine(env.DataDir, "prompt-pack-declined");
            if (cli.Has("--models")) { try { File.Delete(declined); } catch { } }
            string app = cli.Value("--app", "image");
            bool needsPromptPack = app == "prompt" || app == "reference";
            bool askPrompt = st.DlPrompt > 0 && (needsPromptPack || !File.Exists(declined));
            bool wantPrompt = false;
            if (st.DlCore > 0 || askPrompt)
            {
                bool?[] result = new bool?[2];
                long[] cur = new long[] { st.DlCore, askPrompt ? st.DlPrompt : 0 };
                Func<string, long[]> rescan = delegate(string dir)
                {
                    ModelState again = CheckModels(dir);
                    return new long[] { again.DlCore, again.DlPrompt };
                };
                DialogResult dr = (DialogResult)Invoke(delegate { return ModelDialog.Ask(env, cur[0], cur[1], result, FreeBytes(env.ModelsDir), rescan); });
                if (dr != DialogResult.OK)
                {
                    if (st.DlCore > 0) { Close(); return false; }   // the core models are required
                    return true;                                    // only the optional pack was offered: "Not now"
                }
                wantPrompt = result[1] == true;
                if (askPrompt && !wantPrompt) { try { File.WriteAllText(declined, "1"); } catch { } }
                st = CheckModels(env.ModelsDir);   // the person may have chosen another folder
                if (!st.Ok) { Fail(1, "Local3D could not check its model files.", "Restart Local3D. If it keeps happening, open the log folder and send the log in a bug report.", st.Raw ?? ""); return false; }
            }
            else if (st.DlPrompt == 0 && st.NeedPrompt > 0) wantPrompt = true;   // present but not yet hashed (e.g. an existing ComfyUI folder)
            long total = st.NeedCore + (wantPrompt ? st.NeedPrompt : 0);
            if (total == 0) return true;
            string args = baseArgs + " --pack core" + (wantPrompt ? " --pack prompt" : "") + " --json";
            Dictionary<string, long> done = new Dictionary<string, long>();
            Dictionary<string, long> sizes = new Dictionary<string, long>();
            Dictionary<string, string> labels = new Dictionary<string, string>();
            long finished = 0; string phase = "";
            form.Set("Downloading model files (" + Gb(total) + ")", "Starting...");
            string err = "";
            int code = Proc.RunLines(env.Python, args, env.Root, delegate(string line)
            {
                if (!line.StartsWith("{")) return;
                Dictionary<string, object> ev;
                try { ev = Json.Parse(line); } catch { return; }
                string e = Json.Str(ev, "event"), id = Json.Str(ev, "id");
                if (e == "file_start") { sizes[id] = Json.Long(ev, "size"); labels[id] = Json.Str(ev, "label"); phase = "download"; }
                else if (e == "verify") phase = "verify";
                else if (e == "progress") done[id] = Json.Long(ev, "done");
                else if (e == "file_done") { finished += sizes.ContainsKey(id) ? sizes[id] : 0; done.Remove(id); phase = ""; }
                else if (e == "error") err = Json.Str(ev, "message") + "\n" + Json.Str(ev, "detail");
                long cur = finished;
                if (phase == "download") foreach (long d in done.Values) cur += d;
                else if (phase == "verify") foreach (string k in sizes.Keys) if (done.ContainsKey(k)) cur += sizes[k];
                if (cur > total) cur = total;
                string label = labels.ContainsKey(id) ? labels[id] : "";
                form.Progress(cur, total);
                form.Set(phase == "verify" ? "Verifying " + label : "Downloading model files (" + Gb(total) + ")",
                    Gb(cur) + " of " + Gb(total) + (label.Length > 0 && phase != "verify" ? "  -  " + label : ""));
            }, delegate { return form.CancelRequested; });
            if (form.CancelRequested) return false;
            if (code != 0)
            {
                string why = code == 2 ? "There is not enough free disk space for the model files." :
                             code == 3 ? "The model download was interrupted." :
                             code == 4 ? "A downloaded file failed its checksum and was discarded." : "The model files could not be prepared.";
                Fail(code, why, code == 3 ? "Check your internet connection and start Local3D again - finished files are kept and the rest resumes."
                                          : "Fix the problem and start Local3D again - finished files are kept.", err);
                return false;
            }
            return true;
        }

        // --- server -------------------------------------------------------------------------------------------
        private bool StartServer()
        {
            form.Set("Starting Local3D...", "Preparing the workspace");
            form.Indeterminate();
            Workspace.Prepare(env, gpuClass);
            port = FreePort();
            string rt = env.RuntimeDir;
            // NOT --disable-api-nodes: it makes ComfyUI send a Content-Security-Policy without blob: in connect-src, which
            // stops its own 3D viewer from loading a GLB's embedded textures (the model shows grey). The page and engine
            // were measured to make no outbound connections without it; cloud/telemetry hosts are blocked in the app window.
            string args = "-s ComfyUI\\main.py --windows-standalone-build --listen 127.0.0.1 --port " + port +
                " --disable-auto-launch --disable-all-custom-nodes --whitelist-custom-nodes local3d_pack" +
                " --base-directory " + Proc.Q(env.Workspace) + " --models-directory " + Proc.Q(env.ModelsDir) +
                " --input-directory " + Proc.Q(env.OutputDir) + " --output-directory " + Proc.Q(env.OutputDir);
            string extraEngine = Environment.GetEnvironmentVariable("LOCAL3D_ENGINE_ARGS");   // advanced / support: extra ComfyUI flags
            if (!string.IsNullOrEmpty(extraEngine)) { args += " " + extraEngine; Log.Write("extra engine args: " + extraEngine); }
            ProcessStartInfo psi = new ProcessStartInfo(env.Python, args);
            psi.WorkingDirectory = rt;
            psi.UseShellExecute = false; psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
            psi.EnvironmentVariables["HF_HUB_OFFLINE"] = "1";               // generation never needs the network
            psi.EnvironmentVariables["HF_HUB_DISABLE_TELEMETRY"] = "1";
            psi.EnvironmentVariables["DO_NOT_TRACK"] = "1";
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            server = new Process { StartInfo = psi };
            string logPath = Path.Combine(env.LogDir, "comfyui.log");
            try { if (File.Exists(logPath)) File.Copy(logPath, Path.Combine(env.LogDir, "comfyui.previous.log"), true); } catch { }   // keep the last run for bug reports
            StreamWriter sw = new StreamWriter(new FileStream(logPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false));
            sw.AutoFlush = true;
            DataReceivedEventHandler h = delegate(object s, DataReceivedEventArgs e)
            {
                if (e.Data == null) return;
                lock (sw) sw.WriteLine(e.Data);
                // Only a real failure: ComfyUI also prints "Ran out of memory ... retrying with tiled VAE", which it recovers from by itself.
                if (e.Data.IndexOf("retrying", StringComparison.OrdinalIgnoreCase) < 0 &&
                    (e.Data.IndexOf("OutOfMemoryError", StringComparison.OrdinalIgnoreCase) >= 0 || e.Data.IndexOf("CUDA out of memory", StringComparison.OrdinalIgnoreCase) >= 0))
                    OnOutOfMemory(e.Data, logPath);
            };
            server.OutputDataReceived += h; server.ErrorDataReceived += h;
            server.Start();
            if (!Native.AssignProcessToJobObject(job, server.Handle)) Log.Write("WARNING: could not assign the engine to the job object");
            server.BeginOutputReadLine(); server.BeginErrorReadLine();
            Log.Write("ComfyUI started, pid " + server.Id + ", port " + port);

            string sessionFile = Path.Combine(env.DataDir, "session.json");
            form.Set("Starting Local3D...", "Loading the interface");
            DateTime until = DateTime.Now.AddSeconds(240);
            while (DateTime.Now < until)
            {
                if (form.CancelRequested) return false;
                if (server.HasExited)
                {
                    Fail(6, "Local3D's engine stopped while starting.", "Restart Local3D. If it happens again, update your NVIDIA driver and see the troubleshooting guide.", Tail(logPath, 40));
                    return false;
                }
                if (Http.Ok("http://127.0.0.1:" + port + "/system_stats") && Http.Ok("http://127.0.0.1:" + port + "/"))   // engine health + the interface is served
                {
                    File.WriteAllText(sessionFile, "{\"port\":" + port + ",\"pid\":" + server.Id + "}");   // only now can a second launch reuse it
                    return true;
                }
                Thread.Sleep(500);
            }
            Fail(7, "Local3D's engine did not respond in time.", "Restart Local3D. If it happens again, see the troubleshooting guide.", Tail(logPath, 40));
            return false;
        }

        // GPU memory ran out: say what to do in plain words (once per minute), with the raw log one click away.
        private DateTime lastOom = DateTime.MinValue;
        private void OnOutOfMemory(string line, string logPath)
        {
            lock (this)
            {
                if ((DateTime.Now - lastOom).TotalSeconds < 60) return;
                lastOom = DateTime.Now;
            }
            Log.Write("ERROR: GPU out of memory | " + line);
            try
            {
                form.BeginInvoke((MethodInvoker)delegate
                {
                    Ui.Error("Not enough GPU memory for this setting.",
                        "Choose a lower Quality (Maximum, then Balanced, then Fast) or switch Model, close other programs that use the graphics card, and press Run again. " +
                        "Your picture and settings have not been changed.",
                        Tail(logPath, 40));
                });
            }
            catch { }
        }

        private static string Tail(string path, int n)
        {
            try
            {
                string[] lines = File.ReadAllLines(path);
                int from = Math.Max(0, lines.Length - n);
                StringBuilder sb = new StringBuilder();
                for (int i = from; i < lines.Length; i++) sb.AppendLine(lines[i]);
                return sb.ToString();
            }
            catch { return ""; }
        }

        private static int FreePort()
        {
            TcpListener l = new TcpListener(IPAddress.Loopback, 0);
            l.Start();
            int p = ((IPEndPoint)l.LocalEndpoint).Port;
            l.Stop();
            return p;
        }

        // --- browser window -----------------------------------------------------------------------------------
        public void OpenBrowser(int p)
        {
            string edge = EdgePath();
            string url = Url(p);
            if (edge == null)
            {
                Log.Write("Edge not found; opening the default browser");
                Process.Start(url);
                return;
            }
            string profile = ProfileDir;
            string a = "--app=" + Proc.Q(url) + " --user-data-dir=" + Proc.Q(profile) + " --window-size=1440,920 --no-first-run --no-default-browser-check --edge-skip-compat-layer-relaunch" +
                       " --disable-features=msEdgeSidebarV2,msShoppingAssistant --disable-sync" +
                       " --host-resolver-rules=\"MAP api.comfy.org ~NOTFOUND, MAP *.sentry.io ~NOTFOUND, MAP *.posthog.com ~NOTFOUND, MAP *.mixpanel.com ~NOTFOUND, MAP *.segment.io ~NOTFOUND, MAP *.amplitude.com ~NOTFOUND, MAP *.googletagmanager.com ~NOTFOUND\"";
            string extra = Environment.GetEnvironmentVariable("LOCAL3D_BROWSER_ARGS");   // developer hook, e.g. --remote-debugging-port=9333
            if (!string.IsNullOrEmpty(extra)) a += " " + extra;
            ProcessStartInfo psi = new ProcessStartInfo(edge, a);
            psi.UseShellExecute = false;
            browser = Process.Start(psi);
            if (job != IntPtr.Zero) Native.AssignProcessToJobObject(job, browser.Handle);   // the window dies with the launcher, never orphaned on a dead engine
            Log.Write("Edge app window opened, pid " + browser.Id);
        }

        // The frontend names its window after the open app ("... Local3D_Image_to_3D - ComfyUI"); the splash is only "ComfyUI".
        private bool InterfaceReady()
        {
            foreach (Process p in ProfileBrowsers())
                try { p.Refresh(); if (p.MainWindowTitle.IndexOf("Local3D", StringComparison.OrdinalIgnoreCase) >= 0) return true; } catch { }
            return false;
        }

        private static int ReadyTimeoutSeconds()
        {
            int n; string e = Environment.GetEnvironmentVariable("LOCAL3D_READY_TIMEOUT");   // test hook; default 90
            return (!string.IsNullOrEmpty(e) && int.TryParse(e, out n) && n > 0) ? n : 90;
        }

        // Starting engine -> health -> loading interface -> ready, every step bounded. Returns false when Local3D should quit.
        private bool AwaitInterface()
        {
            int stalls = 0;
            while (true)
            {
                form.Set("Starting Local3D...", "Loading the interface");
                form.Indeterminate();
                DateTime until = DateTime.Now.AddSeconds(ReadyTimeoutSeconds());
                bool seen = false;
                while (DateTime.Now < until)
                {
                    if (form.CancelRequested) return false;
                    if (server.HasExited) { Fail(6, "Local3D's engine stopped while the interface was loading.", "Restart Local3D. If it happens again, see the troubleshooting guide.", Tail(Path.Combine(env.LogDir, "comfyui.log"), 40)); return false; }
                    if (InterfaceReady()) { Log.Write("Interface ready"); return true; }
                    bool alive = WindowAlive();
                    if (alive) seen = true; else if (seen) { Log.Write("App window closed before the interface was ready"); return true; }   // the person closed it
                    Thread.Sleep(1000);
                }
                stalls++;
                string details = "Interface not ready after " + ReadyTimeoutSeconds() + " s (window title never named a Local3D app).\n\n--- launcher.log\n" +
                                 Tail(Path.Combine(env.LogDir, "launcher.log"), 15) + "\n--- comfyui.log\n" + Tail(Path.Combine(env.LogDir, "comfyui.log"), 25);
                Log.Write("ERROR: interface not ready in time (stall " + stalls + ")");
                string choice = Ui.AutoYes ? (stalls == 1 ? "repair" : "quit") : (string)Invoke(delegate { return StallDialog.Ask(details); });
                if (choice == "diag") { Invoke(delegate { Diagnostics_.Show(env); return null; }); choice = (string)Invoke(delegate { return StallDialog.Ask(details); }); }
                if (choice == "retry") { KillProfileBrowsers(); OpenBrowser(port); continue; }
                if (choice == "repair") { RepairInterface(); OpenBrowser(port); continue; }
                Close();
                return false;
            }
        }

        // Resets only what Local3D owns: its private browser profile and the frontend settings it writes. Never the person's Edge data.
        private void RepairInterface()
        {
            Log.Write("Repairing the interface: removing Local3D's browser profile and frontend settings");
            KillProfileBrowsers();
            Thread.Sleep(1500);
            for (int i = 0; i < 5; i++)
            {
                try { if (Directory.Exists(ProfileDir)) Directory.Delete(ProfileDir, true); break; }
                catch (Exception ex) { Log.Write("repair: " + ex.Message); Thread.Sleep(1000); }
            }
            try { File.Delete(Path.Combine(env.Workspace, @"user\default\comfy.settings.json")); } catch { }
            try { Workspace.Prepare(env, gpuClass); } catch (Exception ex) { Log.Write("repair: " + ex.Message); }
        }

        private string ProfileDir { get { return Path.Combine(env.DataDir, "browser-profile"); } }

        // Edge hands the window to a different process and the one we started exits within a second, so the started process
        // says nothing about the window. The browser is ours when its command line names Local3D's own profile folder.
        private List<Process> ProfileBrowsers()
        {
            List<Process> r = new List<Process>();
            try
            {
                using (ManagementObjectSearcher q = new ManagementObjectSearcher("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'"))
                    foreach (ManagementObject o in q.Get())
                    {
                        string cl = Convert.ToString(o["CommandLine"]);
                        if (cl != null && cl.IndexOf(ProfileDir, StringComparison.OrdinalIgnoreCase) >= 0)
                            try { r.Add(Process.GetProcessById(Convert.ToInt32(o["ProcessId"]))); } catch { }
                    }
            }
            catch (Exception ex) { Log.Write("WARNING: could not list browser processes: " + ex.Message); }
            return r;
        }

        private bool WindowAlive()
        {
            foreach (Process p in ProfileBrowsers()) { try { if (!p.HasExited) return true; } catch { } }
            return false;
        }

        // Only Local3D's own browser processes (its private profile), never the person's Edge.
        private void KillProfileBrowsers()
        {
            foreach (Process p in ProfileBrowsers()) { try { if (!p.HasExited) p.Kill(); } catch { } }
        }

        private static string EdgePath()
        {
            string[] keys = { @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe", @"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" };
            foreach (string k in keys)
            {
                object v = Registry.GetValue(k, "", null);
                if (v != null && File.Exists(v.ToString())) return v.ToString();
            }
            string pf = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe");
            return File.Exists(pf) ? pf : null;
        }

        private void WaitForExit()
        {
            if (browser == null) { while (!form.CancelRequested && !server.HasExited) Thread.Sleep(500); return; }
            int missing = 0;
            while (!server.HasExited)
            {
                if (WindowAlive()) missing = 0; else if (++missing >= 3) break;   // no browser process of ours for ~3 s: the window is closed
                Thread.Sleep(1000);
            }
            Log.Write(server.HasExited ? "Engine exited" : "App window closed");
            if (server.HasExited && WindowAlive())
                Invoke(delegate { Ui.Error("Local3D's engine stopped unexpectedly.", "Close the Local3D window and start Local3D again.", Tail(Path.Combine(env.LogDir, "comfyui.log"), 40)); return null; });
        }

        // --- shutdown -----------------------------------------------------------------------------------------
        private void AddChild(Process p)
        {
            lock (children) children.Add(p);
            if (job != IntPtr.Zero && !Native.AssignProcessToJobObject(job, p.Handle)) Log.Write("WARNING: could not assign a helper process to the job object");
        }

        private bool shuttingDown;
        private void Shutdown()
        {
            if (shuttingDown) return;
            shuttingDown = true;
            try { if (server != null && !server.HasExited) Proc.KillTree(server); } catch { }
            lock (children) foreach (Process p in children) { try { if (!p.HasExited) Proc.KillTree(p); } catch { } }
            try { File.Delete(Path.Combine(env.DataDir, "session.json")); } catch { }
            if (job != IntPtr.Zero) { Native.CloseHandle(job); job = IntPtr.Zero; }
            Log.Write("Shut down");
        }
    }

    // ------------------------------------------------------------------------------------------------------------
    internal static class Workspace
    {
        // Everything ComfyUI reads at startup that Local3D owns: the pack, the apps, and the frontend settings.
        public static void Prepare(Env env, string gpuClass)
        {
            string ws = env.Workspace;
            Directory.CreateDirectory(env.OutputDir);
            foreach (string d in new[] { "custom_nodes", "temp", @"user\default\workflows" }) Directory.CreateDirectory(Path.Combine(ws, d));

            string pack = Path.Combine(env.Root, "local3d_pack");
            string dest = Path.Combine(ws, "custom_nodes", "local3d_pack");
            // never recurse through a junction/symlink (a developer may link the repo's pack here): remove only the link
            if (Directory.Exists(dest))
                Directory.Delete(dest, (File.GetAttributes(dest) & FileAttributes.ReparsePoint) == 0);
            CopyDir(pack, dest, "variants");
            // apps that depend on the GPU's weight format (FLUX.2 klein): overlay the variant for this GPU class
            string variant = Path.Combine(pack, "variants", gpuClass);
            if (Directory.Exists(variant))
                foreach (string f in Directory.GetFiles(variant, "*.app.json")) File.Copy(f, Path.Combine(dest, "example_workflows", Path.GetFileName(f)), true);

            // the same apps appear in the Apps sidebar (switch between them without touching templates)
            string wf = Path.Combine(ws, @"user\default\workflows");
            foreach (string f in Directory.GetFiles(Path.Combine(dest, "example_workflows"), "*.app.json"))
            {
                string name = Path.GetFileName(f).Replace("Local3D_", "Local3D - ").Replace("_", " ");
                File.Copy(f, Path.Combine(wf, name), true);
            }

            // first-run sample picture so the Image app never opens on a missing file
            string samples = Path.Combine(env.Root, "assets", "examples");
            if (Directory.Exists(samples))
                foreach (string f in Directory.GetFiles(samples, "Local3D_example_*.*"))
                {
                    string t = Path.Combine(env.OutputDir, Path.GetFileName(f));
                    if (!File.Exists(t)) File.Copy(f, t);
                }

            // frontend defaults (merged, so a user's own choices are kept)
            string sp = Path.Combine(ws, @"user\default\comfy.settings.json");
            Dictionary<string, object> s = Json.ReadFile(sp);
            Dictionary<string, object> defaults = Json.ReadFile(Path.Combine(env.Root, "data", "frontend-settings.json"));
            foreach (KeyValuePair<string, object> kv in defaults) if (!kv.Key.StartsWith("_") && !s.ContainsKey(kv.Key)) s[kv.Key] = kv.Value;
            File.WriteAllText(sp, new JavaScriptSerializer().Serialize(s), new UTF8Encoding(false));
        }

        private static void CopyDir(string from, string to, string skipDir)
        {
            Directory.CreateDirectory(to);
            foreach (string f in Directory.GetFiles(from)) File.Copy(f, Path.Combine(to, Path.GetFileName(f)), true);
            foreach (string d in Directory.GetDirectories(from))
                if (!string.Equals(Path.GetFileName(d), skipDir, StringComparison.OrdinalIgnoreCase)) CopyDir(d, Path.Combine(to, Path.GetFileName(d)), skipDir);
        }
    }

    internal static class Http
    {
        public static bool Ok(string url)
        {
            try
            {
                HttpWebRequest r = (HttpWebRequest)WebRequest.Create(url);
                r.Timeout = 2000; r.Proxy = null;
                using (HttpWebResponse resp = (HttpWebResponse)r.GetResponse()) return (int)resp.StatusCode == 200;
            }
            catch { return false; }
        }
    }

    internal static class Proc
    {
        // Quote one command-line argument: backslashes in front of the closing quote must be doubled ("D:\" would escape it).
        public static string Q(string s)
        {
            int trailing = 0;
            for (int i = s.Length - 1; i >= 0 && s[i] == '\\'; i--) trailing++;
            return "\"" + s + new string('\\', trailing) + "\"";
        }

        // Helper processes that talk to the internet get the same opt-outs as the engine, and none of the ambient overrides.
        public static void Sanitize(ProcessStartInfo psi)
        {
            psi.EnvironmentVariables["HF_HUB_DISABLE_TELEMETRY"] = "1";
            psi.EnvironmentVariables["DO_NOT_TRACK"] = "1";
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            foreach (string k in new[] { "HF_HUB_OFFLINE", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN" })
                if (psi.EnvironmentVariables.ContainsKey(k)) psi.EnvironmentVariables.Remove(k);
        }

        public static Process Start(string file, string args, string workdir, Action<string> onLine)
        {
            ProcessStartInfo psi = new ProcessStartInfo(file, args);
            psi.UseShellExecute = false; psi.CreateNoWindow = true;
            if (workdir != null) psi.WorkingDirectory = workdir;
            return Process.Start(psi);
        }

        public static string Capture(string file, string args, int timeoutMs)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(file, args);
                psi.UseShellExecute = false; psi.CreateNoWindow = true; psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
                psi.StandardOutputEncoding = Encoding.UTF8;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                Sanitize(psi);
                using (Process p = Process.Start(psi))
                {
                    StringBuilder o = new StringBuilder();
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) lock (o) o.AppendLine(e.Data); };
                    p.ErrorDataReceived += delegate { };
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();
                    if (!p.WaitForExit(timeoutMs)) { try { p.Kill(); } catch { } return null; }   // the timeout really applies now
                    p.WaitForExit();                                                              // flush the output handlers
                    lock (o) return o.ToString();
                }
            }
            catch { return null; }
        }

        public static int RunLines(string file, string args, string workdir, Action<string> onLine, Func<bool> cancel)
        {
            ProcessStartInfo psi = new ProcessStartInfo(file, args);
            psi.UseShellExecute = false; psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.WorkingDirectory = workdir;
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            Sanitize(psi);
            using (Process p = Process.Start(psi))
            {
                StringBuilder err = new StringBuilder();
                p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) { Log.Write("provision: " + e.Data); } };
                p.BeginErrorReadLine();
                string line;
                while ((line = p.StandardOutput.ReadLine()) != null)
                {
                    if (cancel != null && cancel()) { KillTree(p); return -1; }
                    onLine(line);
                }
                p.WaitForExit();
                return p.ExitCode;
            }
        }

        public static void KillTree(Process p)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("taskkill", "/T /F /PID " + p.Id);
                psi.CreateNoWindow = true; psi.UseShellExecute = false;
                Process.Start(psi).WaitForExit(5000);
            }
            catch { }
        }
    }

    internal static class Diagnostics_
    {
        // Safe-to-share summary: versions and hardware only - no paths, prompts, images or tokens.
        public static void Show(Env env)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("Local3D " + Program.Version);
            sb.AppendLine(WindowsVersion() + (Environment.Is64BitOperatingSystem ? " x64" : ""));
            sb.AppendLine("Runtime " + env.RuntimeTag + " (ComfyUI " + Json.Str(env.Runtime, "comfyui_version") + ", torch " + Json.Str(env.Runtime, "torch") + ")");
            sb.AppendLine("Runtime installed: " + (File.Exists(env.Python) ? "yes" : "no"));
            string gpu = Proc.Capture("nvidia-smi", "--query-gpu=name,memory.total,driver_version --format=csv,noheader", 8000);
            sb.AppendLine("GPU: " + (string.IsNullOrEmpty(gpu) ? "not detected" : gpu.Trim()));
            string script = Path.Combine(env.Root, "scripts", "provision_models.py");
            if (File.Exists(env.Python) && Directory.Exists(env.ModelsDir))
            {
                string c = Proc.Capture(env.Python, Proc.Q(script) + " --models-dir " + Proc.Q(env.ModelsDir) + " --pack core --pack prompt --check", 120000);
                sb.AppendLine("Model files:");
                sb.AppendLine(c == null ? "  (could not check)" : c.TrimEnd());
            }
            string lastErr = LastError(env);
            sb.AppendLine("Last error: " + (lastErr.Length == 0 ? "none recorded" : lastErr));
            string text = sb.ToString();
            using (Form f = new Form())
            {
                f.Text = "Local3D diagnostics"; f.Icon = Ui.AppIcon(); f.StartPosition = FormStartPosition.CenterScreen; f.ClientSize = new Size(600, 400);
                TextBox t = new TextBox { Text = text.Replace("\n", "\r\n"), Multiline = true, ReadOnly = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Both, WordWrap = false };
                Button copy = new Button { Text = "Copy to clipboard", Dock = DockStyle.Bottom, Height = 34 };
                copy.Click += delegate { Clipboard.SetText(text); copy.Text = "Copied"; };
                f.Controls.Add(t); f.Controls.Add(copy);
                f.ShowDialog();
            }
        }

        // Environment.OSVersion reports 6.2 for programs without a supportedOS manifest: read the real build from the registry.
        private static string WindowsVersion()
        {
            try
            {
                string k = @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion";
                string name = Convert.ToString(Registry.GetValue(k, "ProductName", ""));
                string build = Convert.ToString(Registry.GetValue(k, "CurrentBuildNumber", ""));
                string display = Convert.ToString(Registry.GetValue(k, "DisplayVersion", ""));
                int b; if (int.TryParse(build, out b) && b >= 22000) name = name.Replace("Windows 10", "Windows 11");
                return (name + " " + display + " (build " + build + ")").Trim();
            }
            catch { return "Windows (unknown version)"; }
        }

        private static string LastError(Env env)
        {
            try
            {
                string[] lines = File.ReadAllLines(Path.Combine(env.LogDir, "launcher.log"));
                for (int i = lines.Length - 1; i >= 0; i--)
                {
                    int k = lines[i].IndexOf("ERROR: ");
                    if (k >= 0) { string m = lines[i].Substring(k + 7); int bar = m.IndexOf(" | "); return bar > 0 ? m.Substring(0, bar) : m; }
                }
            }
            catch { }
            return "";
        }
    }

    // Consent + location dialog for the model download.
    internal static class ModelDialog
    {
        private const long Margin = 3000000000L;   // keep 3 GB free on the drive after the download

        public static DialogResult Ask(Env env, long core, long prompt, bool?[] result, long free, Func<string, long[]> rescan)
        {
            if (Ui.AutoYes) { result[0] = true; result[1] = prompt > 0; return DialogResult.OK; }
            using (Form f = new Form())
            {
                f.Text = "Local3D - download models";
                f.Icon = Ui.AppIcon();
                f.StartPosition = FormStartPosition.CenterScreen;
                f.FormBorderStyle = FormBorderStyle.FixedDialog; f.MaximizeBox = false; f.MinimizeBox = false;
                f.ClientSize = new Size(560, 330);
                Label head = new Label { Left = 16, Top = 14, Width = 528, Height = 40, Text = "Local3D needs AI model files. They are downloaded once from Hugging Face and stay on this PC; after that, generation works offline." };
                CheckBox c1 = new CheckBox { Left = 20, Top = 62, Width = 520, Height = 22, Checked = true, Enabled = false };
                CheckBox c2 = new CheckBox { Left = 20, Top = 90, Width = 520, Height = 22, AccessibleName = "Also download the Prompt to 3D reference pictures (optional)" };
                Label licenses = new Label { Left = 20, Top = 120, Width = 520, Height = 58, ForeColor = SystemColors.GrayText,
                    Text = "Each model has its own license (MIT, Apache-2.0, and Meta's DINOv3 license, which includes export-control terms). " +
                           "By downloading you accept them; the list is in THIRD_PARTY_NOTICES.md in the Local3D folder and on the project page." };
                Label loc = new Label { Left = 20, Top = 184, Width = 520, Height = 36 };
                Label space = new Label { Left = 20, Top = 222, Width = 520, Height = 38 };
                Button change = new Button { Left = 20, Top = 266, Width = 150, Height = 28, Text = "Change folder..." };
                Button ok = new Button { Left = 360, Top = 292, Width = 90, Height = 28, Text = "Download", DialogResult = DialogResult.OK };
                Button cancel = new Button { Left = 456, Top = 292, Width = 90, Height = 28, Text = core > 0 ? "Cancel" : "Not now", DialogResult = DialogResult.Cancel };
                Action refresh = delegate
                {
                    c1.Text = "Image to 3D (Pixal3D + TRELLIS.2)  -  " + (core > 0 ? (core / 1e9).ToString("0.0") + " GB to download" : "installed");
                    c1.Visible = core > 0;
                    c2.Enabled = prompt > 0;
                    if (prompt == 0 && !c2.Checked) c2.Checked = false;
                    c2.Text = "Prompt to 3D reference pictures (FLUX.2 klein 4B)  -  " + (prompt > 0 ? (prompt / 1e9).ToString("0.0") + " GB to download (optional)" : "installed");
                    long need = core + (c2.Checked ? prompt : 0);
                    long fr = FreeOf(env.ModelsDir, free);
                    bool enough = fr >= need + Margin;
                    loc.Text = "Saved to: " + env.ModelsDir;
                    space.Text = "Needs " + (need / 1e9).ToString("0.0") + " GB, " + (fr / 1e9).ToString("0.0") + " GB free on that drive." +
                                 (enough ? "" : "\nNot enough space (3 GB must stay free after the download): free some space or choose another folder.");
                    space.ForeColor = enough ? SystemColors.ControlText : Color.Firebrick;
                    ok.Text = need > 0 ? "Download" : "Continue";
                    ok.Enabled = enough;
                };
                c2.Checked = prompt > 0;
                c2.CheckedChanged += delegate { refresh(); };
                change.Click += delegate
                {
                    using (FolderBrowserDialog fb = new FolderBrowserDialog())
                    {
                        fb.Description = "Choose where Local3D stores model files (15 GB, up to 36 GB with Prompt to 3D)";
                        if (fb.ShowDialog() == DialogResult.OK)
                        {
                            env.ModelsDir = fb.SelectedPath; env.SaveSettings();
                            long[] again = rescan(env.ModelsDir);   // files already in that folder do not need downloading
                            core = again[0]; prompt = again[1]; free = FreeOf(env.ModelsDir, free);
                            c2.Checked = prompt > 0;
                            refresh();
                        }
                    }
                };
                f.Controls.AddRange(new Control[] { head, c1, c2, licenses, loc, space, change, ok, cancel });
                f.AcceptButton = ok; f.CancelButton = cancel;
                refresh();
                DialogResult r = f.ShowDialog();
                result[0] = true; result[1] = c2.Checked && prompt > 0;
                return r;
            }
        }

        private static long FreeOf(string path, long fallback)
        {
            try { return new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))).AvailableFreeSpace; } catch { return fallback; }
        }
    }
}
