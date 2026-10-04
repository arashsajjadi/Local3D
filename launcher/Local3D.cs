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
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Local3D")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyInformationalVersion("0.1.0")]
[assembly: AssemblyProduct("Local3D")]
[assembly: AssemblyCopyright("MIT License")]

namespace Local3D
{
    internal static class Program
    {
        public const string Version = "0.1.0";

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                Cli cli = new Cli(args);
                Ui.AutoYes = cli.Has("--yes");
                if (cli.Has("--version")) { MessageBox.Show("Local3D " + Version, "Local3D"); return 0; }
                Env env = new Env();
                if (cli.Has("--diagnostics")) { Diagnostics_.Show(env); return 0; }
                bool created;
                using (Mutex single = new Mutex(true, "Local3D.Launcher.v1", out created))
                {
                    if (!created) { return Session.ReopenWindow(env, cli) ? 0 : 1; }
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
            Dictionary<string, object> s = Json.ReadFile(SettingsFile);
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
                f.StartPosition = FormStartPosition.CenterScreen;
                f.FormBorderStyle = FormBorderStyle.FixedDialog;
                f.MaximizeBox = false; f.MinimizeBox = false;
                f.ClientSize = new Size(560, 150);
                Label s = new Label { Text = summary, Left = 16, Top = 14, Width = 528, Height = 40, Font = new Font(SystemFonts.MessageBoxFont, FontStyle.Bold) };
                Label g = new Label { Text = suggestion, Left = 16, Top = 56, Width = 528, Height = 48 };
                TextBox t = new TextBox { Text = details ?? "", Left = 16, Top = 156, Width = 528, Height = 150, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, Visible = false, WordWrap = false };
                Button more = new Button { Text = "Technical details", Left = 16, Top = 112, Width = 140, Height = 28 };
                Button ok = new Button { Text = "Close", Left = 454, Top = 112, Width = 90, Height = 28, DialogResult = DialogResult.OK };
                more.Click += delegate
                {
                    t.Visible = !t.Visible;
                    f.ClientSize = new Size(560, t.Visible ? 322 : 150);
                };
                f.Controls.AddRange(new Control[] { s, g, t, more, ok });
                f.AcceptButton = ok;
                f.ShowDialog();
            }
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
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
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
            quit.Click += delegate { CancelRequested = true; if (Cancelled != null) Cancelled(); };
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
            if (p == 0) return false;
            Session tmp = new Session(env, cli);
            tmp.OpenBrowser(p);
            return true;
        }

        public int Run()
        {
            Log.File_ = Path.Combine(env.LogDir, "launcher.log");
            Log.Write("Local3D " + Program.Version + " starting; data=" + env.DataDir);
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
                OpenBrowser(port);
                form.Set("Local3D is running", "You can close this window; Local3D stops when the app window is closed.");
                form.Progress(1, 1);
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
            string o = Proc.Capture("nvidia-smi", "--query-gpu=name,memory.total --format=csv,noheader,nounits", 8000);
            Log.Write("GPU: " + (o ?? "(nvidia-smi unavailable)").Trim());
            if (string.IsNullOrEmpty(o) || o.IndexOf(',') < 0)
            {
                DialogResult r = (DialogResult)Invoke(delegate
                {
                    return MessageBox.Show("Local3D needs an NVIDIA graphics card (RTX 20-series or newer, 12 GB or more recommended) with an up-to-date driver, " +
                        "and none was found.\n\nContinue anyway? (Generation will be extremely slow or fail.)", "Local3D", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                });
                if (r != DialogResult.Yes) { Close(); return false; }
                return true;
            }
            long mib; string[] parts = o.Trim().Split(',');
            if (parts.Length > 1 && long.TryParse(parts[1].Trim(), out mib) && mib < 9000 && !File.Exists(Path.Combine(env.DataDir, "vram-warned")))
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
            Process curl = Proc.Start("curl.exe", "-L --fail --retry 5 --retry-delay 3 -C - -s -S -o \"" + archive + "\" \"" + Json.Str(env.Runtime, "url") + "\"", folder, null);
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
            Process tar = Proc.Start("tar.exe", "-xf \"" + archive + "\" -C \"" + tmp + "\"", folder, null);
            AddChild(tar);
            while (!tar.HasExited) { if (form.CancelRequested) { Proc.KillTree(tar); return false; } Thread.Sleep(300); }
            if (tar.ExitCode != 0)
            {
                Fail(5, "The runtime could not be unpacked.", "Check that the drive has enough free space, then start Local3D again.", "tar exit code " + tar.ExitCode);
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
        private bool EnsureModels()
        {
            string script = Path.Combine(env.Root, "scripts", "provision_models.py");
            form.Set("Checking model files...", null);
            form.Indeterminate();
            string baseArgs = "\"" + script + "\" --models-dir \"" + env.ModelsDir + "\"";
            Dictionary<string, object> check = Json.Parse(Proc.Capture(env.Python, baseArgs + " --pack core --pack prompt --check --json", 120000) ?? "{}")
                                               ?? new Dictionary<string, object>();
            object filesObj; System.Collections.IEnumerable files = null;
            if (check.TryGetValue("files", out filesObj)) files = filesObj as System.Collections.IEnumerable;
            long needCore = 0, needPrompt = 0;
            if (files != null)
                foreach (object o in files)
                {
                    Dictionary<string, object> f = (Dictionary<string, object>)o;
                    if (Json.Str(f, "status") == "ok") continue;
                    if (Json.Str(f, "pack") == "core") needCore += Json.Long(f, "size"); else needPrompt += Json.Long(f, "size");
                }
            // the prompt pack is optional: once declined, only "Local3D.exe --models" asks again
            string declined = Path.Combine(env.DataDir, "prompt-pack-declined");
            if (cli.Has("--models")) { try { File.Delete(declined); } catch { } }
            bool askPrompt = needPrompt > 0 && !File.Exists(declined);
            if (needCore == 0 && !askPrompt) return true;
            bool wantPrompt = false;
            bool?[] result = new bool?[2];
            DialogResult dr = (DialogResult)Invoke(delegate { return ModelDialog.Ask(env, needCore, askPrompt ? needPrompt : 0, result, FreeBytes(env.ModelsDir)); });
            if (dr != DialogResult.OK) { Close(); return false; }
            wantPrompt = askPrompt && result[1] == true;
            if (askPrompt && !wantPrompt) { try { File.WriteAllText(declined, "1"); } catch { } }
            string args = baseArgs + " --pack core" + (wantPrompt ? " --pack prompt" : "") + " --json";
            long total = needCore + (wantPrompt ? needPrompt : 0);
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
            Workspace.Prepare(env);
            port = FreePort();
            string rt = env.RuntimeDir;
            string args = "-s ComfyUI\\main.py --windows-standalone-build --listen 127.0.0.1 --port " + port +
                " --disable-auto-launch --disable-all-custom-nodes --whitelist-custom-nodes local3d_pack --disable-api-nodes" +
                " --base-directory \"" + env.Workspace + "\" --models-directory \"" + env.ModelsDir + "\"" +
                " --input-directory \"" + env.OutputDir + "\" --output-directory \"" + env.OutputDir + "\"";
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
            StreamWriter sw = new StreamWriter(new FileStream(logPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false));
            sw.AutoFlush = true;
            DataReceivedEventHandler h = delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) lock (sw) sw.WriteLine(e.Data); };
            server.OutputDataReceived += h; server.ErrorDataReceived += h;
            server.Start();
            job = Native.KillOnCloseJob();
            Native.AssignProcessToJobObject(job, server.Handle);
            server.BeginOutputReadLine(); server.BeginErrorReadLine();
            Log.Write("ComfyUI started, pid " + server.Id + ", port " + port);

            string sessionFile = Path.Combine(env.DataDir, "session.json");
            File.WriteAllText(sessionFile, "{\"port\":" + port + ",\"pid\":" + server.Id + "}");
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
                if (Http.Ok("http://127.0.0.1:" + port + "/system_stats")) return true;
                Thread.Sleep(500);
            }
            Fail(7, "Local3D's engine did not respond in time.", "Restart Local3D. If it happens again, see the troubleshooting guide.", Tail(logPath, 40));
            return false;
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
            string profile = Path.Combine(env.DataDir, "browser-profile");
            string a = "--app=\"" + url + "\" --user-data-dir=\"" + profile + "\" --window-size=1440,920 --no-first-run --no-default-browser-check" +
                       " --disable-features=msEdgeSidebarV2,msShoppingAssistant --disable-sync";
            ProcessStartInfo psi = new ProcessStartInfo(edge, a);
            psi.UseShellExecute = false;
            browser = Process.Start(psi);
            Log.Write("Edge app window opened, pid " + browser.Id);
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
            while (!browser.HasExited && !server.HasExited) Thread.Sleep(500);
            Log.Write(browser.HasExited ? "App window closed" : "Engine exited");
            if (server.HasExited && !browser.HasExited)
                Invoke(delegate { Ui.Error("Local3D's engine stopped unexpectedly.", "Close the Local3D window and start Local3D again.", Tail(Path.Combine(env.LogDir, "comfyui.log"), 40)); return null; });
        }

        // --- shutdown -----------------------------------------------------------------------------------------
        private void AddChild(Process p) { lock (children) children.Add(p); if (job != IntPtr.Zero) Native.AssignProcessToJobObject(job, p.Handle); }

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
        public static void Prepare(Env env)
        {
            string ws = env.Workspace;
            Directory.CreateDirectory(env.OutputDir);
            foreach (string d in new[] { "custom_nodes", "temp", @"user\default\workflows" }) Directory.CreateDirectory(Path.Combine(ws, d));

            string pack = Path.Combine(env.Root, "local3d_pack");
            string dest = Path.Combine(ws, "custom_nodes", "local3d_pack");
            // never recurse through a junction/symlink (a developer may link the repo's pack here): remove only the link
            if (Directory.Exists(dest))
                Directory.Delete(dest, (File.GetAttributes(dest) & FileAttributes.ReparsePoint) == 0);
            CopyDir(pack, dest);

            // the same apps appear in the Apps sidebar (switch between them without touching templates)
            string wf = Path.Combine(ws, @"user\default\workflows");
            foreach (string f in Directory.GetFiles(Path.Combine(pack, "example_workflows"), "*.app.json"))
            {
                string name = Path.GetFileName(f).Replace("Local3D_", "Local3D - ").Replace("_", " ");
                File.Copy(f, Path.Combine(wf, name), true);
            }

            // first-run sample picture so the Image app never opens on a missing file
            string samples = Path.Combine(env.Root, "assets", "examples");
            if (Directory.Exists(samples))
                foreach (string f in Directory.GetFiles(samples, "Local3D_example_*.png"))
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

        private static void CopyDir(string from, string to)
        {
            Directory.CreateDirectory(to);
            foreach (string f in Directory.GetFiles(from)) File.Copy(f, Path.Combine(to, Path.GetFileName(f)), true);
            foreach (string d in Directory.GetDirectories(from)) CopyDir(d, Path.Combine(to, Path.GetFileName(d)));
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
                using (Process p = Process.Start(psi))
                {
                    p.ErrorDataReceived += delegate { };
                    p.BeginErrorReadLine();
                    string o = p.StandardOutput.ReadToEnd();
                    if (!p.WaitForExit(timeoutMs)) { try { p.Kill(); } catch { } return null; }
                    return o;
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
            sb.AppendLine("Windows " + Environment.OSVersion.Version + (Environment.Is64BitOperatingSystem ? " x64" : ""));
            sb.AppendLine("Runtime " + env.RuntimeTag + " (ComfyUI " + Json.Str(env.Runtime, "comfyui_version") + ", torch " + Json.Str(env.Runtime, "torch") + ")");
            sb.AppendLine("Runtime installed: " + (File.Exists(env.Python) ? "yes" : "no"));
            string gpu = Proc.Capture("nvidia-smi", "--query-gpu=name,memory.total,driver_version --format=csv,noheader", 8000);
            sb.AppendLine("GPU: " + (string.IsNullOrEmpty(gpu) ? "not detected" : gpu.Trim()));
            string script = Path.Combine(env.Root, "scripts", "provision_models.py");
            if (File.Exists(env.Python) && Directory.Exists(env.ModelsDir))
            {
                string c = Proc.Capture(env.Python, "\"" + script + "\" --models-dir \"" + env.ModelsDir + "\" --pack core --pack prompt --check", 120000);
                sb.AppendLine("Model files:");
                sb.AppendLine(c == null ? "  (could not check)" : c.TrimEnd());
            }
            string lastErr = LastError(env);
            sb.AppendLine("Last error: " + (lastErr.Length == 0 ? "none recorded" : lastErr));
            string text = sb.ToString();
            using (Form f = new Form())
            {
                f.Text = "Local3D diagnostics"; f.StartPosition = FormStartPosition.CenterScreen; f.ClientSize = new Size(600, 400);
                TextBox t = new TextBox { Text = text.Replace("\n", "\r\n"), Multiline = true, ReadOnly = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Both, WordWrap = false };
                Button copy = new Button { Text = "Copy to clipboard", Dock = DockStyle.Bottom, Height = 34 };
                copy.Click += delegate { Clipboard.SetText(text); copy.Text = "Copied"; };
                f.Controls.Add(t); f.Controls.Add(copy);
                f.ShowDialog();
            }
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
        public static DialogResult Ask(Env env, long core, long prompt, bool?[] result, long free)
        {
            if (Ui.AutoYes) { result[0] = true; result[1] = prompt > 0; return DialogResult.OK; }
            using (Form f = new Form())
            {
                f.Text = "Local3D - download models";
                f.StartPosition = FormStartPosition.CenterScreen;
                f.FormBorderStyle = FormBorderStyle.FixedDialog; f.MaximizeBox = false; f.MinimizeBox = false;
                f.ClientSize = new Size(560, 270);
                Label head = new Label { Left = 16, Top = 14, Width = 528, Height = 40, Text = "Local3D needs AI model files. They are downloaded once from Hugging Face and stay on this PC; after that, generation works offline.", };
                CheckBox c1 = new CheckBox { Left = 20, Top = 66, Width = 520, Height = 22, Checked = true, Enabled = false, Text = "Image to 3D (Pixal3D + TRELLIS.2)  -  " + (core > 0 ? (core / 1e9).ToString("0.0") + " GB to download" : "installed") };
                CheckBox c2 = new CheckBox { Left = 20, Top = 94, Width = 520, Height = 22, Checked = prompt > 0, Enabled = prompt > 0, Text = "Prompt to 3D reference pictures (FLUX.2 klein 4B)  -  " + (prompt > 0 ? (prompt / 1e9).ToString("0.0") + " GB to download (optional)" : "installed") };
                Label loc = new Label { Left = 20, Top = 130, Width = 520, Height = 40 };
                Label space = new Label { Left = 20, Top = 172, Width = 520, Height = 22 };
                Button change = new Button { Left = 20, Top = 202, Width = 150, Height = 28, Text = "Change folder..." };
                Button ok = new Button { Left = 360, Top = 228, Width = 90, Height = 28, Text = "Download", DialogResult = DialogResult.OK };
                Button cancel = new Button { Left = 456, Top = 228, Width = 90, Height = 28, Text = "Cancel", DialogResult = DialogResult.Cancel };
                Action refresh = delegate
                {
                    long need = core + (c2.Checked ? prompt : 0);
                    long fr = FreeOf(env.ModelsDir, free);
                    loc.Text = "Saved to: " + env.ModelsDir;
                    space.Text = "Needs " + (need / 1e9).ToString("0.0") + " GB, " + (fr / 1e9).ToString("0.0") + " GB free on that drive.";
                    space.ForeColor = fr < need + 3000000000L ? Color.Firebrick : SystemColors.ControlText;
                    ok.Enabled = fr >= need + 3000000000L;
                };
                c2.CheckedChanged += delegate { refresh(); };
                change.Click += delegate
                {
                    using (FolderBrowserDialog fb = new FolderBrowserDialog())
                    {
                        fb.Description = "Choose where Local3D stores model files (about 22 GB)";
                        if (fb.ShowDialog() == DialogResult.OK) { env.ModelsDir = fb.SelectedPath; env.SaveSettings(); refresh(); }
                    }
                };
                f.Controls.AddRange(new Control[] { head, c1, c2, loc, space, change, ok, cancel });
                f.AcceptButton = ok; f.CancelButton = cancel;
                refresh();
                DialogResult r = f.ShowDialog();
                result[0] = true; result[1] = c2.Checked;
                return r;
            }
        }

        private static long FreeOf(string path, long fallback)
        {
            try { return new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))).AvailableFreeSpace; } catch { return fallback; }
        }
    }
}
