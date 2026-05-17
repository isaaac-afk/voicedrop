"""
VoiceDrop - Offline Voice Dictation for Windows (GUI Edition)

Press SHIFT+SPACE to start. Press again (or stay silent 1.5s) to stop.
A small status window in the corner shows what's happening.
Runs 100% locally using OpenAI Whisper.
"""

import os
import sys
import time
import tempfile
import threading
import wave
import tkinter as tk

import numpy as np
import pyaudio
import whisper
import keyboard
import pyperclip
import pyautogui

# ── Settings ──────────────────────────────────────────────────────────────────
WHISPER_MODEL    = "base"     # tiny | base | small | medium | large
SAMPLE_RATE      = 16000
CHANNELS         = 1
CHUNK            = 1024

SILENCE_LIMIT    = 1.5        # seconds of silence before auto-stop
SILENCE_THRESH   = 500
MIN_DURATION     = 0.4
MAX_DURATION     = 60.0
HOTKEY           = "shift+space"

HALLUCINATIONS = {
    "you", "you.", "thank you.", "thanks for watching.",
    "thanks for watching!", "bye.", "bye", ".", "thank you",
    "subtitles by the amara.org community", "subtitles by",
    "subscribe to my channel.", "see you next time.",
    "♪", "[music]", "[silence]", "okay.", "okay", "uh.", "um.",
}
# ──────────────────────────────────────────────────────────────────────────────

# ── State ─────────────────────────────────────────────────────────────────────
recording      = False
is_recording   = False
busy           = False
audio_frames   = []
state_lock     = threading.Lock()
pa             = pyaudio.PyAudio()
model          = None


# ── GUI ───────────────────────────────────────────────────────────────────────
class VoiceDropGUI:
    """A small status-only window — no clickable button (so focus stays in your browser)."""

    def __init__(self, root):
        self.root = root
        root.title("VoiceDrop")
        root.geometry("240x90")
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.92)
        root.resizable(False, False)
        root.configure(bg="#1e1e1e")

        # Bottom-right corner
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"240x90+{sw - 260}+{sh - 160}")

        # Big colored dot indicator
        self.dot = tk.Label(
            root,
            text="●",
            font=("Segoe UI", 24, "bold"),
            fg="#888888",
            bg="#1e1e1e",
        )
        self.dot.pack(side="left", padx=(14, 6), pady=8)

        right_frame = tk.Frame(root, bg="#1e1e1e")
        right_frame.pack(side="left", fill="both", expand=True)

        self.title_lbl = tk.Label(
            right_frame,
            text="VoiceDrop",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg="#1e1e1e",
            anchor="w",
        )
        self.title_lbl.pack(fill="x", pady=(10, 0))

        self.status = tk.Label(
            right_frame,
            text="Loading model...",
            font=("Segoe UI", 9),
            fg="#aaaaaa",
            bg="#1e1e1e",
            anchor="w",
            wraplength=170,
            justify="left",
        )
        self.status.pack(fill="x")

        self.hint = tk.Label(
            right_frame,
            text="Press SHIFT+SPACE",
            font=("Segoe UI", 8),
            fg="#666666",
            bg="#1e1e1e",
            anchor="w",
        )
        self.hint.pack(fill="x", pady=(2, 0))

    def set_idle(self):
        self.dot.config(fg="#4a8feb")
        self.status.config(text="Ready", fg="#aaaaaa")

    def set_recording(self):
        self.dot.config(fg="#e23a3a")
        self.status.config(text="Recording...", fg="#e23a3a")

    def set_transcribing(self):
        self.dot.config(fg="#f0c14b")
        self.status.config(text="Transcribing...", fg="#f0c14b")

    def set_result(self, text):
        self.dot.config(fg="#7bd17b")
        preview = text[:30] + ("..." if len(text) > 30 else "")
        self.status.config(text=preview, fg="#7bd17b")

    def set_filtered(self, msg="Filtered"):
        self.dot.config(fg="#888888")
        self.status.config(text=msg, fg="#aaaaaa")


gui = None


def gui_call(method, *args):
    if gui is not None:
        gui.root.after(0, lambda: method(*args))


# ── Mic check ─────────────────────────────────────────────────────────────────
def check_microphone():
    try:
        pa.get_default_input_device_info()
        return True
    except Exception:
        return False


# ── Recording ─────────────────────────────────────────────────────────────────
def start_recording():
    global recording, audio_frames, is_recording

    with state_lock:
        audio_frames = []
        recording    = True

    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"  ERROR: Can't open microphone: {e}")
        with state_lock:
            recording = False
        is_recording = False
        gui_call(gui.set_idle)
        return

    print("  >>> Recording...")
    gui_call(gui.set_recording)

    silence_start = None
    start_time    = time.time()
    auto_stopped  = False

    try:
        while True:
            with state_lock:
                if not recording:
                    break

            if time.time() - start_time >= MAX_DURATION:
                print(f"  Auto-stopped (max {MAX_DURATION:.0f}s)")
                auto_stopped = True
                break

            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
            except OSError as e:
                print(f"  WARNING: Audio device issue: {e}")
                break

            with state_lock:
                audio_frames.append(data)

            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms     = np.sqrt(np.mean(samples ** 2)) if samples.size else 0

            if rms < SILENCE_THRESH:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= SILENCE_LIMIT:
                    print("  Auto-stopped (silence)")
                    auto_stopped = True
                    break
            else:
                silence_start = None
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass

    with state_lock:
        recording = False
    is_recording = False

    if auto_stopped:
        threading.Thread(target=stop_and_transcribe, daemon=True).start()


# ── Transcription ─────────────────────────────────────────────────────────────
def is_hallucination(text):
    cleaned = text.strip().lower()
    if not cleaned or len(cleaned) <= 1:
        return True
    return cleaned in HALLUCINATIONS


def paste_text(text):
    try:
        original = pyperclip.paste()
    except Exception:
        original = ""

    try:
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
    except Exception as e:
        print(f"  WARNING: Paste failed: {e}")
    finally:
        try:
            pyperclip.copy(original)
        except Exception:
            pass


def stop_and_transcribe():
    global busy

    if busy:
        return
    busy = True
    gui_call(gui.set_transcribing)

    try:
        with state_lock:
            frames = list(audio_frames)

        if not frames:
            print("  No audio.")
            gui_call(gui.set_filtered, "No audio")
            return

        total_samples = sum(len(f) // 2 for f in frames)
        duration      = total_samples / SAMPLE_RATE
        if duration < MIN_DURATION:
            print(f"  Too short ({duration:.2f}s)")
            gui_call(gui.set_filtered, "Too short")
            return

        all_audio   = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32)
        overall_rms = np.sqrt(np.mean(all_audio ** 2)) if all_audio.size else 0
        if overall_rms < SILENCE_THRESH * 0.6:
            print("  Silent.")
            gui_call(gui.set_filtered, "Silent")
            return

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name

            wf = wave.open(tmp_path, "wb")
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
            wf.close()

            print("  Transcribing...")
            try:
                result = model.transcribe(
                    tmp_path,
                    fp16=False,
                    language="en",
                    no_speech_threshold=0.6,
                    logprob_threshold=-1.0,
                    condition_on_previous_text=False,
                )
                text = result.get("text", "").strip()
            except Exception as e:
                print(f"  ERROR: {e}")
                gui_call(gui.set_filtered, "Error")
                return

            if is_hallucination(text):
                print(f"  Filtered: '{text}'")
                gui_call(gui.set_filtered, "Filtered (silence)")
                return

            print(f"  Done: '{text}'")
            paste_text(text)
            gui_call(gui.set_result, text)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    finally:
        busy = False
        if gui is not None:
            gui.root.after(2500, gui.set_idle)


# ── Hotkey ────────────────────────────────────────────────────────────────────
def on_hotkey():
    global is_recording, recording

    if busy:
        print("  Still transcribing...")
        return

    if not is_recording:
        is_recording = True
        threading.Thread(target=start_recording, daemon=True).start()
    else:
        is_recording = False
        with state_lock:
            recording = False
        threading.Thread(target=stop_and_transcribe, daemon=True).start()


# ── Background model load ─────────────────────────────────────────────────────
def load_model_background():
    global model
    print(f"  Loading Whisper '{WHISPER_MODEL}' model...")
    try:
        model = whisper.load_model(WHISPER_MODEL)
        print("  Model loaded!")
        gui_call(gui.set_idle)
    except Exception as e:
        print(f"  ERROR loading model: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global gui

    print("=" * 56)
    print("  VoiceDrop - Offline Voice Dictation (GUI)")
    print("=" * 56)

    if not check_microphone():
        print("  ERROR: No microphone detected.")
        pa.terminate()
        sys.exit(1)

    root = tk.Tk()
    gui  = VoiceDropGUI(root)

    threading.Thread(target=load_model_background, daemon=True).start()

    try:
        keyboard.add_hotkey(HOTKEY, on_hotkey)
        print(f"  Hotkey registered: {HOTKEY.upper()}")
    except Exception as e:
        print(f"  WARNING: Hotkey not registered ({e})")

    def on_close():
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            pa.terminate()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
