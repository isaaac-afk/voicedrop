# VoiceDrop 🎙️

A free, offline voice dictation tool for Windows. Press a hotkey, speak, and your words appear in any text field — browser, Word, email, anywhere. No subscriptions, no cloud, no data leaves your machine.

Built as a free alternative to Wispr Flow using OpenAI's Whisper model running fully locally.

## Features

- 🔒 **100% offline** — audio never leaves your computer
- ⚡ **Works anywhere** — browsers, documents, messaging apps, any text field
- 🎯 **Auto-stop on silence** — pause for 3 seconds and it transcribes automatically
- 🧠 **Hallucination filtering** — removes common Whisper artifacts on silence
- 📋 **Clipboard-safe** — preserves your original clipboard contents
- 💰 **Free forever** — no API keys, no subscriptions

## Demo

```
========================================================
  VoiceDrop - Offline Voice Dictation
========================================================
  Model loaded!
  Press CTRL+SHIFT+SPACE to START. Press again to STOP.
  Auto-stop after 3s of silence.
========================================================
  >>> Recording... (CTRL+SHIFT+SPACE to stop, or pause 3s)
  Auto-stopped (silence detected)
  Transcribing...
  Done: 'Hey, this is a test of my voice dictation tool.'
```

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install ffmpeg

```bash
winget install ffmpeg
```

### 3. Run

```bash
set KMP_DUPLICATE_LIB_OK=TRUE
python dictate.py
```

**Note:** Run Command Prompt as Administrator for the global hotkey to work.

The first run downloads the Whisper model (~140MB for `base`). One-time only.

## Usage

1. Click into any text field
2. Press **Ctrl + Shift + Space**
3. Speak
4. Pause 3 seconds (or press hotkey again) — text appears

Press **Esc** in the terminal to quit.

## Configuration

Edit the top of `dictate.py` to customize:

| Setting | Description | Default |
|---|---|---|
| `WHISPER_MODEL` | `tiny`, `base`, `small`, `medium`, `large` | `base` |
| `SILENCE_LIMIT` | Seconds of silence before auto-stop | `3.0` |
| `MAX_DURATION` | Hard cap on recording length | `60.0` |
| `HOTKEY` | The keyboard shortcut | `ctrl+shift+space` |

### Model selection

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| tiny | 75MB | Fastest | OK |
| base | 140MB | Fast | Good ✅ |
| small | 460MB | Medium | Better |
| medium | 1.5GB | Slow | Great |
| large | 3GB | Slowest | Best |

## How It Works

1. PyAudio captures microphone input in real-time
2. RMS energy detection identifies silence
3. Audio is saved to a temp WAV file
4. OpenAI Whisper transcribes locally
5. Hallucination filter removes common artifacts
6. PyAutoGUI pastes the result into your active window

## Tech Stack

- **OpenAI Whisper** — speech recognition
- **PyAudio** — microphone capture
- **keyboard** — global hotkeys
- **pyperclip + pyautogui** — text injection

## License

MIT

## Author

Built by Isaac as an alternative to paid dictation tools.
