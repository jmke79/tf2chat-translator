# TF2 Chat Translator 🎮🌍

A Python application that monitors Team Fortress 2's console output in real-time and automatically translates chat messages from any language to English.

**Two modes available:**
- **Terminal Mode** (`tf2_chat_translator.py`) - Color-coded terminal output
- **Overlay Mode** (`tf2_chat_overlay.py`) - Transparent, click-through GUI overlay for gaming (Windows only)

## Features

- **Real-time monitoring** - Watches TF2's console log as you play
- **Automatic language detection** - Detects 30+ languages including Russian, French, German, Chinese, Japanese, Korean, etc.
- **Instant translation** - Translates non-English messages to English using Google Translate
- **Overlay mode** - Transparent, click-through window that stays on top while gaming
- **No game modification** - Uses TF2's built-in console logging (VAC-safe)

## Screenshots

### Terminal Mode
```
╭─────────────────────────────────────────────────────────────────┐
│ 🎮 TF2 Chat Translator                                          │
│ Monitoring: D:\Steam\...\Team Fortress 2\tf\console.log         │
│ Press Ctrl+C to stop                                            │
╰─────────────────────────────────────────────────────────────────╯

Player1: Hello everyone!
*DEAD* RussianGamer: Привет, как дела?
  → [Russian] Hi, how are you?
(TEAM) FrenchPlayer: Bonjour, quelqu'un peut m'aider?
  → [French] Hello, can someone help me?
```

### Overlay Mode (Windows)
![Overlay Preview](https://github.com/jmke79/tf2chat-translator/blob/main/image-2026-01-02-102815.png?raw=true)
- Transparent background
- Click-through (doesn't capture mouse)
- Stays on top of game
- Draggable window
- Toggle lock to interact

## Requirements

- Python 3.9+
- Anaconda or Miniconda (recommended)
- Team Fortress 2
- Internet connection (for translation API)
- **Windows** (for overlay mode only)

## Installation

### 1. Set up Conda Environment

**Option A: Using environment.yml (recommended)**
```bash
# Create environment from file
conda env create -f environment.yml

# Activate the environment
conda activate tf2translator
```

**Option B: Manual setup**
```bash
# Create a new conda environment
conda create -n tf2translator python=3.11

# Activate the environment
conda activate tf2translator

# Install dependencies
pip install -r requirements.txt
```

> **Note:** Each time you open a new terminal to run the translator, you'll need to activate the environment first with `conda activate tf2translator`

### 2. Configure TF2 to output console logs

In Steam:
- Right-click **Team Fortress 2** in your library
- Click **Properties**
- In the **Launch Options** field, add:
  ```
  -condebug -conclearlog
  ```

This tells TF2 to:
- `-condebug` - Write all console output to `console.log`
- `-conclearlog` - Clear the log file each time the game starts (optional but recommended)

### 3. Configure TF2 Display Mode (for Overlay)

**⚠️ IMPORTANT for Overlay Mode:**

TF2 must be in **Borderless Windowed** or **Windowed** mode. The overlay will NOT appear over fullscreen exclusive mode.

In TF2:
- Go to **Options → Video → Display Mode**
- Select **Borderless Window** (recommended) or **Windowed**

## Usage

### Terminal Mode (All Platforms)
```bash
# Process all existing messages in log + continue monitoring
python tf2_chat_translator.py

# Only show new messages (skip existing log content)
python tf2_chat_translator.py --tail-only

# Test mode (verify translation works)
python tf2_chat_translator.py --test
```

### Overlay Mode (Windows Only)
```bash
# Launch overlay with default settings
python tf2_chat_overlay.py

# Customize position and opacity
python tf2_chat_overlay.py --position bottom-left --opacity 0.9

# Show more messages
python tf2_chat_overlay.py --max-messages 12

# Only show new messages
python tf2_chat_overlay.py --tail-only
```

### Overlay Controls

| Control | Action |
|---------|--------|
| 🔓/🔒 | Toggle click-through mode (click the lock icon) |
| ✕ | Close overlay |
| Drag title | Move overlay window |

When **🔓 unlocked**: Window is click-through, you can play the game normally
When **🔒 locked**: Window captures mouse, you can interact with it

### Command Line Options

**Terminal mode:**
```bash
python tf2_chat_translator.py --help
```

**Overlay mode:**
```bash
python tf2_chat_overlay.py --help
```

| Option | Description |
|--------|-------------|
| `--log-path`, `-l` | Custom path to console.log |
| `--tail-only` | Only show new messages |
| `--no-color` | Disable colors (terminal only) |
| `--opacity`, `-o` | Window opacity 0.0-1.0 (overlay only) |
| `--position`, `-p` | Window position: top-left, top-right, bottom-left, bottom-right, center (overlay only) |
| `--max-messages`, `-m` | Max messages to display (overlay only) |
| `--test` | Test mode with sample messages (terminal only) |

## How It Works

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│    TF2      │───▶│   console.log    │───▶│  Chat Translator    │
│  -condebug  │    │   (text file)    │    │  • Parse messages   │
└─────────────┘    └──────────────────┘    │  • Detect language  │
                                           │  • Translate        │
                                           │  • Display          │
                                           └─────────────────────┘
```

1. TF2's `-condebug` launch option writes all console output to a text file
2. The script monitors this file in real-time (like `tail -f`)
3. Chat messages are parsed using regex patterns
4. `langdetect` library identifies the source language
5. `deep-translator` translates non-English messages via Google Translate
6. Results are displayed with color coding in your terminal

## Default Log File Locations

The script auto-detects these paths:

| OS | Path |
|----|------|
| Windows | `D:\Steam\steamapps\common\Team Fortress 2\tf\console.log` |
| Windows (alt) | `C:\Program Files (x86)\Steam\steamapps\common\Team Fortress 2\tf\console.log` |
| Linux | `~/.steam/steam/steamapps/common/Team Fortress 2/tf/console.log` |
| macOS | `~/Library/Application Support/Steam/steamapps/common/Team Fortress 2/tf/console.log` |

If your Steam library is in a different location, use the `--log-path` option:
```bash
python tf2_chat_translator.py --log-path "E:\Games\Steam\steamapps\common\Team Fortress 2\tf\console.log"
```

## Supported Languages

The translator supports 30+ languages including:

- **European:** Russian, French, German, Spanish, Portuguese, Italian, Polish, Dutch, Swedish, Danish, Norwegian, Finnish, Czech, Slovak, Hungarian, Romanian, Bulgarian, Ukrainian, Croatian, Slovenian, Estonian, Latvian, Lithuanian, Greek
- **Asian:** Japanese, Korean, Chinese (Simplified & Traditional), Thai, Vietnamese, Indonesian
- **Middle Eastern:** Turkish, Arabic, Hebrew

## Troubleshooting

### "Log file not found"
- Make sure TF2 is running with `-condebug` in launch options
- The log file is only created when TF2 starts
- Check if your Steam installation is in a non-standard location

### Messages not being detected
- Some servers use custom chat formats that may not be recognized
- Very short messages (< 3 characters) are skipped
- System messages and notifications are filtered out

### Translation errors
- Requires internet connection
- Google Translate may rate-limit if you're in a very chatty server
- Some slang/gaming terms may not translate well

### High CPU usage
- The script polls the file every 100ms by default
- This is minimal but you can modify `poll_interval` in the code if needed

## VAC Safety

This application is **VAC-safe** because it:
- Does NOT hook into the game process
- Does NOT modify any game files
- Does NOT inject code
- Only reads a plain text log file that TF2 creates
- Uses only official Valve-supported launch options

This is the same method used by other community tools like `tf2mon`, `TF2ChatToSpeech`, and various log analyzers.

## Contributing

Contributions are welcome! Some ideas for improvements:
- GUI interface
- Overlay display on top of the game
- Custom translation targets (not just English)
- Local translation models (offline support)
- Chat filtering/moderation features

## License

MIT License - feel free to use, modify, and distribute.

## Credits

- Uses [langdetect](https://github.com/Mimino666/langdetect) for language detection
- Uses [deep-translator](https://github.com/nidhaloff/deep-translator) for translation
- Uses [rich](https://github.com/Textualize/rich) for terminal formatting
- Inspired by the TF2 community's various console parsing tools
