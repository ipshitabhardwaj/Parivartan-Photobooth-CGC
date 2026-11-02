#!/usr/bin/env python
"""
CGC SQUARE: start everything with ONE command.

    start_kiosk.bat            (double-click it, or run it in a terminal)      or:   py run_kiosk.py

What it does, in order (anything already fine is skipped, so later starts take seconds):
  1. checks the Python libraries and installs what is missing; fixes the OpenCV/NumPy mismatch
  2. if there is an NVIDIA GPU: installs the CUDA build of PyTorch (about 3 GB, asks once)
  3. Google Drive: runs the one-time sign-in if credentials.json is there but you haven't signed in yet
  4. starts Ollama if the quick looks need it (not needed once the AI painter is working)
  5. starts the kiosk server and waits until it is ready, including the AI model being loaded
  6. opens the kiosk in a full-screen Chrome/Edge window
Press Ctrl+C in this window to stop everything it started. In the full-screen window, Alt+F4 closes it.

Useful options:   --check       only report what is missing, change nothing
                  --yes         answer every question with yes (for unattended setup)
                  --window      open a normal browser window instead of full screen
                  --no-browser  don't open a browser    --no-ai  never install/use the AI painter
                  --no-install  never install anything  --port N  use another port
"""
import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
STATE_FILE = os.path.join(HERE, ".launcher_state.json")
IS_WINDOWS = os.name == "nt"

# import name -> pip name
CORE = {
    "flask": "flask", "PIL": "pillow", "requests": "requests", "numpy": "numpy", "onnxruntime": "onnxruntime",
    "segno": "segno", "googleapiclient": "google-api-python-client", "google.oauth2": "google-auth",
    "google_auth_oauthlib": "google-auth-oauthlib",
}
AI_LIBS = {
    "diffusers": "diffusers", "transformers": "transformers", "accelerate": "accelerate", "peft": "peft",
    "safetensors": "safetensors", "huggingface_hub": "huggingface_hub",
}
OPENCV_PACKAGES = ("opencv-python", "opencv-python-headless", "opencv-contrib-python")
TORCH_CHANNELS = ("cu126", "cu124")          # tried in this order


def say(message):
    print(f"[start] {message}", flush=True)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    except OSError:
        pass


def ask(question, assume_yes, default_yes=True):
    if assume_yes or not sys.stdin or not sys.stdin.isatty():
        say(f"{question} -> {'yes' if default_yes else 'no'} (automatic)")
        return default_yes
    reply = input(f"[start] {question} [{'Y/n' if default_yes else 'y/N'}] ").strip().lower()
    return default_yes if not reply else reply.startswith("y")


def run_py(code, timeout=180):
    """Run a snippet in a fresh interpreter, so a crash or half-broken library can't take the launcher down."""
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout)


def pip(*args):
    return subprocess.call([sys.executable, "-m", "pip", *args])


def installed_pip_names():
    try:
        out = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], capture_output=True, text=True, timeout=120)
        return {item["name"].lower().replace("_", "-") for item in json.loads(out.stdout)}
    except Exception:
        return set()


def missing(libs):
    out = []
    for module, pip_name in libs.items():
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(pip_name)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------------------------------------------------
def check_opencv():
    """(ok, explanation). The usual failure: OpenCV built for NumPy 1.x running with NumPy 2.x."""
    probe = run_py("import cv2, numpy; cv2.cvtColor(numpy.zeros((4, 4, 3), 'uint8'), cv2.COLOR_RGB2GRAY); print(cv2.__version__)")
    if probe.returncode == 0:
        return True, probe.stdout.strip()
    text = (probe.stderr or "") + (probe.stdout or "")
    if "_ARRAY_API" in text or "NumPy 1.x" in text or "numpy.core.multiarray" in text:
        return False, "OpenCV was built for NumPy 1.x but NumPy 2.x is installed"
    if "No module named 'cv2'" in text:
        return False, "OpenCV is not installed"
    return False, "OpenCV does not load"


def has_nvidia_gpu():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "-L"], capture_output=True, text=True, timeout=20).returncode == 0
    except Exception:
        return False


def check_torch():
    """(has_torch, has_cuda)."""
    probe = run_py("import torch; print(torch.cuda.is_available())")
    if probe.returncode != 0:
        return False, False
    return True, probe.stdout.strip() == "True"


def ollama_up():
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2).read()
        return True
    except Exception:
        return False


def server_status(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return None


def diagnose():
    """Collect everything we can check without changing anything."""
    info = {}
    info["opencv"] = check_opencv()
    info["core_missing"] = missing(CORE)
    info["gpu"] = has_nvidia_gpu()
    info["torch"] = check_torch()
    info["ai_missing"] = missing(AI_LIBS)
    info["drive_credentials"] = os.path.exists(os.path.join(HERE, "credentials.json"))
    info["drive_signed_in"] = os.path.exists(os.path.join(HERE, "token.json"))
    info["ollama_installed"] = shutil.which("ollama") is not None
    info["ollama_running"] = ollama_up()
    return info


def print_report(info):
    ok_cv, why_cv = info["opencv"]
    has_torch, has_cuda = info["torch"]
    say("What I found:")
    print(f"        Python libraries : {'all present' if not info['core_missing'] else 'missing ' + ', '.join(info['core_missing'])}")
    print(f"        OpenCV           : {('working (' + why_cv + ')') if ok_cv else 'PROBLEM: ' + why_cv}")
    print(f"        NVIDIA GPU       : {'yes' if info['gpu'] else 'not found (AI painter needs one)'}")
    print(f"        PyTorch          : {'CUDA ready' if has_cuda else ('installed, but without GPU support' if has_torch else 'not installed')}")
    print(f"        AI libraries     : {'all present' if not info['ai_missing'] else 'missing ' + ', '.join(info['ai_missing'])}")
    print(f"        Google Drive     : {'signed in' if info['drive_signed_in'] else ('credentials.json found, not signed in yet' if info['drive_credentials'] else 'no credentials.json (QR code will not appear)')}")
    print(f"        Ollama           : {'running' if info['ollama_running'] else ('installed, not running' if info['ollama_installed'] else 'not installed')}")


# ---------------------------------------------------------------------------------------------------------------------
# Fixes
# ---------------------------------------------------------------------------------------------------------------------
def install_core(args):
    gone = missing(CORE)
    if gone:
        say(f"Installing missing libraries: {', '.join(gone)}")
        if pip("install", *gone) != 0:
            say("WARNING: some libraries could not be installed (is the internet connected?). Continuing anyway.")


def fix_opencv(args):
    ok, why = check_opencv()
    if ok:
        return
    say(f"OpenCV problem: {why}. Fixing (this only takes a minute)...")
    have = [name for name in OPENCV_PACKAGES if name in installed_pip_names()] or ["opencv-python-headless"]
    pip("install", "--upgrade", *have)
    ok, why = check_opencv()
    say("OpenCV is working now." if ok else f"WARNING: OpenCV is still not working ({why}). The kiosk will run, with reduced image quality.")


def install_ai(args, state):
    """CUDA PyTorch + diffusers libraries. Returns True if the AI painter can run."""
    if args.no_ai or state.get("ai") == "declined":
        return False
    if not has_nvidia_gpu():
        say("No NVIDIA GPU found, so the AI painter is skipped (the quick looks are used).")
        return False
    has_torch, has_cuda = check_torch()
    need_libs = missing(AI_LIBS)
    if has_cuda and not need_libs:
        return True
    if args.no_install:
        say("AI painter is not fully installed (skipping because of --no-install).")
        return False
    if state.get("ai") != "installed" and not ask(
            "Install the AI painter now? It downloads about 3 GB (PyTorch) plus 2.3 GB (the model) once, "
            "and makes photos real AI repaints instead of filters.", args.yes):
        state["ai"] = "declined"
        save_state(state)
        say("OK, skipping it. Delete .launcher_state.json to be asked again.")
        return False
    if need_libs:
        say(f"Installing AI libraries: {', '.join(need_libs)}")
        pip("install", *need_libs)
    if not has_cuda:
        say("Installing PyTorch with GPU support (large download, please wait)...")
        if has_torch:
            pip("uninstall", "-y", "torch", "torchvision", "torchaudio")
        for channel in TORCH_CHANNELS:
            if pip("install", "torch", "--index-url", f"https://download.pytorch.org/whl/{channel}") == 0 and check_torch()[1]:
                break
        else:
            say("WARNING: could not install GPU PyTorch. The quick looks will be used. See the README (AI repainting).")
            return False
    fix_opencv(args)                         # installing torch can pull in NumPy 2: re-check OpenCV afterwards
    state["ai"] = "installed"
    save_state(state)
    return True


def drive_signin(args):
    creds, token = os.path.join(HERE, "credentials.json"), os.path.join(HERE, "token.json")
    if os.path.exists(token):
        return
    if not os.path.exists(creds):
        say("Google Drive is off: put credentials.json in this folder to get the QR code (see README, Google Drive setup).")
        return
    if args.no_install:
        return
    say("One-time Google sign-in: your browser will open. Sign in, click Allow, then come back here.")
    if subprocess.call([sys.executable, "setup_drive.py"]) != 0:
        say("Drive sign-in did not finish. Photos are still saved here; run  py setup_drive.py  to try again later.")


def start_ollama(args):
    """Start `ollama serve` if it isn't running. Returns the process we started (or None)."""
    if ollama_up():
        return None
    exe = shutil.which("ollama")
    if not exe:
        say("Ollama is not installed, so the quick looks use their built-in settings (still works).")
        return None
    say("Starting Ollama...")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
    proc = subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    for _ in range(30):
        if ollama_up():
            return proc
        time.sleep(0.5)
    say("Ollama did not respond in time; continuing without it.")
    return proc


def ensure_ollama_model(args):
    exe = shutil.which("ollama")
    if not exe or not ollama_up():
        return
    try:
        listing = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30).stdout.lower()
    except Exception:
        return
    known = ("moondream", "llava", "qwen2.5vl", "gemma3", "minicpm", "qwen3-vl", "llama3.2-vision", "bakllava")
    if any(name in listing for name in known) or args.no_install:
        return
    if ask("No Ollama vision model is installed. Download 'moondream' (1.7 GB, fast, fits your GPU)?", args.yes):
        subprocess.call([exe, "pull", "moondream"])


# ---------------------------------------------------------------------------------------------------------------------
# Server + browser
# ---------------------------------------------------------------------------------------------------------------------
def start_server(args, state):
    env = dict(os.environ, PORT=str(args.port), PYTHONUNBUFFERED="1",
               PYTHONWARNINGS="ignore::FutureWarning,ignore::UserWarning",      # library notices that mean nothing to a kiosk operator
               TRANSFORMERS_VERBOSITY="error", HF_HUB_DISABLE_SYMLINKS_WARNING="1", HF_HUB_DISABLE_TELEMETRY="1")
    if os.path.exists(os.path.join(HERE, ".ai_model_ok")):
        env["HF_HUB_OFFLINE"] = "1"          # the model is already on this computer: never wait for the network
    env["PYTHONIOENCODING"] = "utf-8"
    say("Starting the kiosk server... (everything it prints is also saved in kiosk.log)")
    log_path = os.path.join(HERE, "kiosk.log")
    try:                                         # keep the previous run's log as kiosk.previous.log
        if os.path.exists(log_path):
            os.replace(log_path, os.path.join(HERE, "kiosk.previous.log"))
    except OSError:
        pass
    proc = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    threading.Thread(target=_pump, args=(proc.stdout, log_path), daemon=True).start()
    return proc


def _pump(stream, log_path):
    """Show the server's output in this window AND write it to kiosk.log (raw bytes, so progress bars still work)."""
    try:
        log = open(log_path, "ab")
    except OSError:
        log = None
    try:
        while True:
            chunk = stream.read1(4096) if hasattr(stream, "read1") else stream.read(1)
            if not chunk:
                break
            try:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            except Exception:
                pass
            if log:
                log.write(chunk)
                log.flush()
    finally:
        if log:
            log.close()


def wait_for_server(proc, port, timeout=180):
    started = time.time()
    while time.time() - started < timeout:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2).read()
            return True
        except Exception:
            time.sleep(1)
    return False


def wait_for_ai(proc, port, soft_timeout=150, hard_timeout=3600):
    """
    Wait for the AI model to be in GPU memory (then the first photo is fast).
    Returns "ready", "later" (still downloading/loading after soft_timeout: carry on, it switches on by itself),
    "failed" (the background loader stopped without success) or "off" (AI painter not available at all).
    """
    status = server_status(port)
    if not status or not status.get("ai", {}).get("available"):
        return "off"
    started, last_note = time.time(), 0
    while proc.poll() is None and time.time() - started < hard_timeout:
        ai = (server_status(port) or {}).get("ai", {})
        if ai.get("loaded"):
            return "ready"
        if not ai.get("warming"):
            return "failed"
        if time.time() - started > soft_timeout:
            return "later"
        if time.time() - last_note > 30:
            say("Loading the AI model (the first time it downloads about 2.3 GB, please wait)...")
            last_note = time.time()
        time.sleep(3)
    return "failed"


def find_browser():
    candidates = []
    if IS_WINDOWS:
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
        for root in filter(None, roots):
            candidates += [os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                           os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe")]
    else:
        candidates += [shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def open_browser(args):
    url = f"http://127.0.0.1:{args.port}/"
    exe = find_browser()
    if not exe:
        import webbrowser
        say(f"Opening {url} in your default browser (Chrome or Edge is recommended for the camera).")
        webbrowser.open(url)
        return None
    profile = os.path.join(HERE, ".browser_profile")        # its own profile: the camera permission is remembered
    flags = [exe, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--noerrdialogs",
             "--disable-session-crashed-bubble", "--overscroll-history-navigation=0", "--disable-pinch"]
    flags += [f"--app={url}"] if args.window else ["--kiosk", url]
    say("Opening the kiosk" + (" in a window." if args.window else " full screen. Allow the camera the first time. Alt+F4 closes it."))
    return subprocess.Popen(flags)


def stop(proc, name):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        say(f"{name} stopped.")


def main():
    parser = argparse.ArgumentParser(description="Start the CGC SQUARE kiosk with one command.")
    parser.add_argument("--check", action="store_true", help="only report what is missing; change nothing")
    parser.add_argument("--yes", action="store_true", help="answer yes to every question")
    parser.add_argument("--window", action="store_true", help="normal browser window instead of full screen")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    args = parser.parse_args()

    def _terminate(signum, frame):          # closing the console window or killing the launcher must stop the children too
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _terminate)

    say(f"CGC SQUARE kiosk launcher (Python {sys.version.split()[0]})")
    if sys.version_info < (3, 9):
        say("This needs Python 3.9 or newer. Install it from python.org and try again.")
        return 1
    if args.check:
        print_report(diagnose())
        return 0

    state = load_state()
    if not args.no_install:
        install_core(args)
        fix_opencv(args)
    ai_ready = install_ai(args, state)
    drive_signin(args)

    ollama_proc = None
    if not ai_ready:                              # the AI painter owns the GPU; Ollama is only the quick look's helper
        ollama_proc = start_ollama(args)
        ensure_ollama_model(args)

    print_report(diagnose())
    server = start_server(args, state)
    browser = None
    try:
        if not wait_for_server(server, args.port):
            say("The server did not start. Scroll up for the error message.")
            return 1
        if ai_ready:
            outcome = wait_for_ai(server, args.port)
            if outcome == "ready":
                say("AI painter is loaded and ready.")
            elif outcome == "later":
                say("The AI model is still downloading. Starting now with the quick looks: the AI turns on by itself "
                    "for the next photo after it finishes (watch for '[AI] ready' below). Keep this window open.")
            else:
                say("The AI painter could not start (see the [AI] lines above). Photos will use the quick looks.")
        say(f"Ready: http://127.0.0.1:{args.port}/   (A B C D = look, SPACE = photo, Ctrl+C here = stop everything)")
        if not args.no_browser:
            browser = open_browser(args)
        while server.poll() is None:
            time.sleep(1)
        say("The server stopped. Scroll up for the reason.")
        return server.returncode or 0
    except KeyboardInterrupt:
        say("Stopping...")
        return 0
    finally:
        stop(server, "Server")
        stop(ollama_proc, "Ollama")
        if browser and browser.poll() is None:
            stop(browser, "Browser")


if __name__ == "__main__":
    sys.exit(main())
