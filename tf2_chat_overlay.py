#!/usr/bin/env python3
"""
TF2 Chat Translator - Overlay GUI Version
A transparent, click-through overlay that displays translated chat messages while gaming.

Requirements:
    - Windows OS (uses win32 API for click-through)
    - TF2 must be in "Borderless Windowed" or "Windowed" mode (not fullscreen exclusive)
    - Install dependencies: pip install -r requirements.txt

Usage:
    python tf2_chat_overlay.py [--log-path PATH] [--opacity 0.8] [--position top-right]
"""

import argparse
import os
import re
import sys
import time
import threading
import queue
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator
from collections import deque

# Check for Windows
if sys.platform != 'win32':
    print("Error: Overlay mode requires Windows OS")
    print("Use tf2_chat_translator.py for terminal-based translation on other platforms")
    sys.exit(1)

# GUI imports
import tkinter as tk
from tkinter import font as tkfont

# Windows API for click-through
import win32gui
import win32con
import win32api

# Translation imports
try:
    from langdetect import detect, DetectorFactory
    from deep_translator import GoogleTranslator
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install langdetect deep-translator")
    sys.exit(1)

# Make language detection deterministic
DetectorFactory.seed = 0


# ============================================================================
# Data Classes and Parser (same as terminal version)
# ============================================================================

@dataclass
class ChatMessage:
    """Represents a parsed chat message from TF2 console."""
    timestamp: datetime
    player_name: str
    message: str
    is_dead: bool = False
    is_team: bool = False
    original_line: str = ""


class TF2LogParser:
    """Parses TF2 console.log for chat messages."""
    
    CHAT_PATTERN = re.compile(
        r'^(?P<dead>\*DEAD\*\s*)?'
        r'(?P<team>\(TEAM\)\s*)?'
        r'(?P<player_name>.+?)'
        r'\s:\s\s'  # " :  " - TF2's specific chat format
        r'(?P<message>.+)$'
    )
    
    SKIP_PATTERNS = [
        re.compile(r'.+\skilled\s.+\swith\s'),
        re.compile(r'.+\ssuicided\.?$'),
        re.compile(r'.+\sconnected$'),
        re.compile(r'.+\sdisconnected$'),
        re.compile(r'^(Steam|Map|Players|Build|Server|Network|Voice_|CAsync|Host_|Differing|qhull|Creating|SetupBones|Cannot|Attemped|Parent|Proto|Lobby|Client|Team Fortress|Connecting|Connected|Cleaning|Loading|Current|CTF|Shutdown|Unable|Sending|Disconnecting|Recognizing|The server|ProtoDefs|maxplayers|Connection|For FCVAR)'),
        re.compile(r'^\['),
        re.compile(r'^\s*$'),
        re.compile(r'^---'),
        re.compile(r'^\d'),
        re.compile(r'^pair\.'),
        re.compile(r'^magnitude'),
        re.compile(r'^try '),
    ]
    
    @classmethod
    def parse_line(cls, line: str) -> Optional[ChatMessage]:
        line = line.strip()
        if not line:
            return None
        
        for pattern in cls.SKIP_PATTERNS:
            if pattern.search(line):
                return None
        
        match = cls.CHAT_PATTERN.match(line)
        if match:
            player_name = match.group('player_name').strip()
            message = match.group('message').strip()
            
            if cls._looks_like_system_message(message):
                return None
            
            return ChatMessage(
                timestamp=datetime.now(),
                player_name=player_name,
                message=message,
                is_dead=bool(match.group('dead')),
                is_team=bool(match.group('team')),
                original_line=line
            )
        return None
    
    @staticmethod
    def _looks_like_system_message(message: str) -> bool:
        if ':\\' in message or message.count('\\') > 1:
            return True
        if message.count('/') > 2:
            return True
        tech_extensions = ['.dll', '.wav', '.cfg', '.log', '.exe', '.txt', '.html']
        message_lower = message.lower()
        for ext in tech_extensions:
            if ext in message_lower:
                return True
        tech_terms = ['bytes', ' mb ', 'capacity', 'precache', 'convexity']
        for term in tech_terms:
            if term in message_lower:
                return True
        return False


class Translator:
    """Handles language detection and translation."""
    
    SUPPORTED_LANGUAGES = {
        'ru': 'Russian', 'fr': 'French', 'de': 'German', 'it': 'Italian',
        'es': 'Spanish', 'pt': 'Portuguese', 'pl': 'Polish', 'nl': 'Dutch',
        'sv': 'Swedish', 'da': 'Danish', 'no': 'Norwegian', 'fi': 'Finnish',
        'cs': 'Czech', 'sk': 'Slovak', 'hu': 'Hungarian', 'ro': 'Romanian',
        'bg': 'Bulgarian', 'uk': 'Ukrainian', 'hr': 'Croatian', 'sl': 'Slovenian',
        'et': 'Estonian', 'lv': 'Latvian', 'lt': 'Lithuanian', 'el': 'Greek',
        'tr': 'Turkish', 'ja': 'Japanese', 'ko': 'Korean',
        'zh-cn': 'Chinese', 'zh-tw': 'Chinese', 'ar': 'Arabic', 'he': 'Hebrew',
        'th': 'Thai', 'vi': 'Vietnamese', 'id': 'Indonesian',
    }
    
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='en')
        self._cache = {}
        self._translation_available = True
        self._error_shown = False
    
    def detect_language(self, text: str) -> Optional[str]:
        if len(text.strip()) < 3:
            return None
        try:
            return detect(text)
        except:
            return None
    
    def translate(self, text: str) -> tuple:
        if text in self._cache:
            lang, translated = self._cache[text]
            return (text, lang, translated)
        
        detected_lang = self.detect_language(text)
        if detected_lang is None or detected_lang == 'en':
            return (text, 'en', text)
        
        if not self._translation_available:
            return (text, detected_lang, text)
        
        try:
            translated = self.translator.translate(text)
            self._cache[text] = (detected_lang, translated)
            return (text, detected_lang, translated)
        except Exception as e:
            if not self._error_shown:
                print(f"Translation API unavailable: {e}")
                self._error_shown = True
                self._translation_available = False
            return (text, detected_lang, text)
    
    def get_language_name(self, code: str) -> str:
        return self.SUPPORTED_LANGUAGES.get(code, code.upper())


class LogTailer:
    """Tails a log file, yielding new lines as they appear."""
    
    def __init__(self, filepath: Path, poll_interval: float = 0.1):
        self.filepath = filepath
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
    
    def stop(self):
        self._stop_event.set()
    
    def tail(self, start_from_end: bool = False) -> Generator[str, None, None]:
        while not self.filepath.exists() and not self._stop_event.is_set():
            time.sleep(1)
        
        if self._stop_event.is_set():
            return
        
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            if start_from_end:
                f.seek(0, 2)
            
            while not self._stop_event.is_set():
                line = f.readline()
                if line:
                    yield line
                else:
                    time.sleep(self.poll_interval)
                    current_pos = f.tell()
                    f.seek(0, 2)
                    end_pos = f.tell()
                    if end_pos < current_pos:
                        f.seek(0)
                    else:
                        f.seek(current_pos)


# ============================================================================
# Overlay GUI
# ============================================================================

class TranslatorOverlay:
    """Transparent, click-through overlay window for displaying translated chat."""
    
    # Color scheme
    BG_COLOR = '#1a1a2e'  # Dark blue background
    TEXT_COLOR = '#ffffff'
    TRANSLATED_COLOR = '#00ff88'  # Green for translations
    PLAYER_COLOR = '#00d4ff'  # Cyan for player names
    DEAD_COLOR = '#ff6b6b'  # Red for *DEAD*
    TEAM_COLOR = '#ffd93d'  # Yellow for (TEAM)
    LANG_COLOR = '#b388ff'  # Purple for language tag
    
    def __init__(self, log_path: Path, opacity: float = 0.85, 
                 position: str = 'top-right', max_messages: int = 8,
                 tail_only: bool = True):
        self.log_path = log_path
        self.opacity = opacity
        self.position = position
        self.max_messages = max_messages
        self.tail_only = tail_only
        
        self.parser = TF2LogParser()
        self.translator = Translator()
        self.tailer = LogTailer(log_path)
        
        self.message_queue = queue.Queue()
        self.messages = deque(maxlen=max_messages)
        
        self._setup_window()
        self._setup_styles()
        self._position_window()
        self._make_click_through()
        
        self.monitor_thread = None
        self.running = False
    
    def _setup_window(self):
        """Initialize the tkinter window."""
        self.root = tk.Tk()
        self.root.title("TF2 Chat Translator")
        
        # Remove window decorations
        self.root.overrideredirect(True)
        
        # Set transparency
        self.root.attributes('-alpha', self.opacity)
        self.root.attributes('-topmost', True)
        
        # Background color (will be made transparent for click-through)
        self.root.configure(bg=self.BG_COLOR)
        
        # Create main frame
        self.frame = tk.Frame(self.root, bg=self.BG_COLOR, padx=10, pady=8)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Header with drag handle and controls
        self.header = tk.Frame(self.frame, bg=self.BG_COLOR)
        self.header.pack(fill=tk.X, pady=(0, 5))
        
        # Title (also serves as drag handle)
        self.title_label = tk.Label(
            self.header, 
            text="🎮 TF2 Chat Translator", 
            fg=self.TEXT_COLOR, 
            bg=self.BG_COLOR,
            font=('Segoe UI', 9, 'bold'),
            cursor='fleur'
        )
        self.title_label.pack(side=tk.LEFT)
        
        # Close button
        self.close_btn = tk.Label(
            self.header,
            text="✕",
            fg='#ff6b6b',
            bg=self.BG_COLOR,
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2'
        )
        self.close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.close_btn.bind('<Button-1>', lambda e: self.stop())
        
        # Lock/unlock button (toggle click-through)
        self.lock_btn = tk.Label(
            self.header,
            text="🔓",  # Unlocked = click-through enabled
            fg=self.TEXT_COLOR,
            bg=self.BG_COLOR,
            font=('Segoe UI', 10),
            cursor='hand2'
        )
        self.lock_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.lock_btn.bind('<Button-1>', self._toggle_click_through)
        
        # Separator
        separator = tk.Frame(self.frame, bg='#404060', height=1)
        separator.pack(fill=tk.X, pady=5)
        
        # Message container
        self.message_frame = tk.Frame(self.frame, bg=self.BG_COLOR)
        self.message_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status label
        self.status_label = tk.Label(
            self.frame,
            text="Waiting for messages...",
            fg='#666680',
            bg=self.BG_COLOR,
            font=('Segoe UI', 8),
            anchor='w'
        )
        self.status_label.pack(fill=tk.X, pady=(5, 0))
        
        # Bind drag events to header
        self.title_label.bind('<Button-1>', self._start_drag)
        self.title_label.bind('<B1-Motion>', self._do_drag)
        
        # Store click-through state
        self.click_through = True
        
        # Store drag offset
        self._drag_x = 0
        self._drag_y = 0
    
    def _setup_styles(self):
        """Set up text fonts."""
        self.font_player = tkfont.Font(family='Segoe UI', size=10, weight='bold')
        self.font_message = tkfont.Font(family='Segoe UI', size=10)
        self.font_translation = tkfont.Font(family='Segoe UI', size=9)
        self.font_tag = tkfont.Font(family='Segoe UI', size=8)
    
    def _position_window(self):
        """Position the window based on settings."""
        # Window size
        width = 400
        height = 300
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate position
        padding = 20
        positions = {
            'top-left': (padding, padding),
            'top-right': (screen_width - width - padding, padding),
            'bottom-left': (padding, screen_height - height - padding - 50),
            'bottom-right': (screen_width - width - padding, screen_height - height - padding - 50),
            'center': ((screen_width - width) // 2, (screen_height - height) // 2),
        }
        
        x, y = positions.get(self.position, positions['top-right'])
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _make_click_through(self):
        """Make the window click-through using Windows API."""
        # Get the window handle
        hwnd = win32gui.FindWindow(None, "TF2 Chat Translator")
        if not hwnd:
            # Try to get it from tkinter
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            # Get the actual top-level window
            hwnd = win32gui.GetParent(hwnd)
            if not hwnd:
                hwnd = win32gui.GetAncestor(self.root.winfo_id(), win32con.GA_ROOT)
        
        self.hwnd = hwnd
        
        if self.click_through and hwnd:
            try:
                # Get current extended style
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                # Add layered and transparent flags
                new_style = ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
            except Exception as e:
                print(f"Warning: Could not set click-through: {e}")
    
    def _disable_click_through(self):
        """Disable click-through so window can be interacted with."""
        if hasattr(self, 'hwnd') and self.hwnd:
            try:
                ex_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
                # Remove transparent flag but keep layered
                new_style = (ex_style | win32con.WS_EX_LAYERED) & ~win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, new_style)
            except Exception as e:
                print(f"Warning: Could not disable click-through: {e}")
    
    def _toggle_click_through(self, event=None):
        """Toggle click-through mode."""
        self.click_through = not self.click_through
        
        if self.click_through:
            self.lock_btn.config(text="🔓")  # Unlocked
            self._make_click_through()
        else:
            self.lock_btn.config(text="🔒")  # Locked
            self._disable_click_through()
    
    def _start_drag(self, event):
        """Start dragging the window."""
        # Temporarily disable click-through for drag
        if self.click_through:
            self._disable_click_through()
        self._drag_x = event.x
        self._drag_y = event.y
    
    def _do_drag(self, event):
        """Handle window dragging."""
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f'+{x}+{y}')
    
    def _add_message_widget(self, chat: ChatMessage, detected_lang: str, translated: str):
        """Add a message to the display - newest at top, oldest scrolls out."""
        # Store message data (not widget) - newest first
        msg_data = {
            'chat': chat,
            'detected_lang': detected_lang,
            'translated': translated
        }
        self.messages.appendleft(msg_data)
        
        # Trim to max messages
        while len(self.messages) > self.max_messages:
            self.messages.pop()
        
        # Rebuild the display
        self._rebuild_message_display()
    
    def _rebuild_message_display(self):
        """Rebuild the message display from the messages deque."""
        # Clear existing widgets
        for widget in self.message_frame.winfo_children():
            widget.destroy()
        
        # Rebuild from messages (newest first in deque)
        for msg_data in self.messages:
            self._create_message_widget(
                msg_data['chat'],
                msg_data['detected_lang'],
                msg_data['translated']
            )
    
    def _create_message_widget(self, chat: ChatMessage, detected_lang: str, translated: str):
        """Create a single message widget."""
        # Create message container
        msg_frame = tk.Frame(self.message_frame, bg=self.BG_COLOR)
        msg_frame.pack(fill=tk.X, pady=2, anchor='w')
        
        # First line: player name and original message
        line1 = tk.Frame(msg_frame, bg=self.BG_COLOR)
        line1.pack(fill=tk.X, anchor='w')
        
        # Prefix (*DEAD*, (TEAM))
        if chat.is_dead:
            tk.Label(line1, text="*DEAD*", fg=self.DEAD_COLOR, bg=self.BG_COLOR,
                    font=self.font_tag).pack(side=tk.LEFT)
        if chat.is_team:
            tk.Label(line1, text="(TEAM)", fg=self.TEAM_COLOR, bg=self.BG_COLOR,
                    font=self.font_tag).pack(side=tk.LEFT)
        
        # Player name
        tk.Label(line1, text=f"{chat.player_name}: ", fg=self.PLAYER_COLOR, 
                bg=self.BG_COLOR, font=self.font_player).pack(side=tk.LEFT)
        
        # Original message
        tk.Label(line1, text=chat.message, fg=self.TEXT_COLOR, bg=self.BG_COLOR,
                font=self.font_message, wraplength=350, justify='left').pack(side=tk.LEFT, fill=tk.X)
        
        # Second line: translation (if not English)
        is_foreign = detected_lang != 'en'
        is_translated = is_foreign and chat.message != translated
        
        if is_foreign:
            line2 = tk.Frame(msg_frame, bg=self.BG_COLOR)
            line2.pack(fill=tk.X, anchor='w', padx=(15, 0))
            
            lang_name = self.translator.get_language_name(detected_lang)
            
            if is_translated:
                tk.Label(line2, text=f"→ [{lang_name}] ", fg=self.LANG_COLOR, 
                        bg=self.BG_COLOR, font=self.font_tag).pack(side=tk.LEFT)
                tk.Label(line2, text=translated, fg=self.TRANSLATED_COLOR, 
                        bg=self.BG_COLOR, font=self.font_translation,
                        wraplength=330, justify='left').pack(side=tk.LEFT, fill=tk.X)
            else:
                tk.Label(line2, text=f"[{lang_name}]", fg=self.LANG_COLOR, 
                        bg=self.BG_COLOR, font=self.font_tag).pack(side=tk.LEFT)
    
    def _update_status(self, text: str):
        """Update the status label."""
        self.status_label.config(text=text)
    
    def _monitor_log(self):
        """Background thread to monitor log file."""
        msg_count = 0
        
        for line in self.tailer.tail(start_from_end=self.tail_only):
            if not self.running:
                break
            
            chat = self.parser.parse_line(line)
            if chat:
                original, detected_lang, translated = self.translator.translate(chat.message)
                self.message_queue.put((chat, detected_lang, translated))
                msg_count += 1
    
    def _process_queue(self):
        """Process messages from the queue (runs in main thread)."""
        try:
            while True:
                chat, detected_lang, translated = self.message_queue.get_nowait()
                self._add_message_widget(chat, detected_lang, translated)
                
                # Update status
                is_translated = detected_lang != 'en' and chat.message != translated
                if is_translated:
                    lang_name = self.translator.get_language_name(detected_lang)
                    self._update_status(f"Translated from {lang_name}")
                else:
                    self._update_status("Monitoring chat...")
        except queue.Empty:
            pass
        
        if self.running:
            self.root.after(100, self._process_queue)
    
    def start(self):
        """Start the overlay."""
        self.running = True
        
        # Check if log exists
        if not self.log_path.exists():
            self._update_status(f"Waiting for: {self.log_path.name}")
        else:
            self._update_status("Monitoring chat...")
        
        # Start log monitoring in background thread
        self.monitor_thread = threading.Thread(target=self._monitor_log, daemon=True)
        self.monitor_thread.start()
        
        # Start queue processing
        self.root.after(100, self._process_queue)
        
        # Re-apply click-through after window is shown
        self.root.after(500, self._make_click_through)
        
        # Run the GUI
        self.root.mainloop()
    
    def stop(self):
        """Stop the overlay."""
        self.running = False
        self.tailer.stop()
        self.root.quit()
        self.root.destroy()


# ============================================================================
# Main
# ============================================================================

def get_default_log_path() -> Path:
    """Get the default TF2 console.log path."""
    paths = [
        Path(r"D:\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
        Path(r"C:\Program Files\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
        Path(r"C:\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
        Path.home() / "Steam/steamapps/common/Team Fortress 2/tf/console.log",
    ]
    
    for path in paths:
        if path.exists():
            return path
    
    return paths[0]


def main():
    parser = argparse.ArgumentParser(
        description="TF2 Chat Translator - Transparent Overlay",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tf2_chat_overlay.py
  python tf2_chat_overlay.py --position bottom-left --opacity 0.9
  python tf2_chat_overlay.py --max-messages 10

Positions: top-left, top-right, bottom-left, bottom-right, center

Controls:
  🔓/🔒  Toggle click-through (click lock icon)
  ✕      Close overlay
  Drag title to move window

IMPORTANT: TF2 must be in "Borderless Windowed" or "Windowed" mode!
           Overlay will NOT appear over fullscreen exclusive mode.
        """
    )
    
    parser.add_argument('--log-path', '-l', type=Path, default=None,
                       help="Path to TF2 console.log")
    parser.add_argument('--opacity', '-o', type=float, default=0.85,
                       help="Window opacity (0.0-1.0, default: 0.85)")
    parser.add_argument('--position', '-p', type=str, default='top-right',
                       choices=['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center'],
                       help="Window position (default: top-right)")
    parser.add_argument('--max-messages', '-m', type=int, default=8,
                       help="Maximum messages to display (default: 8)")
    parser.add_argument('--tail-only', action='store_true',
                       help="Only show new messages (skip existing log)")
    
    args = parser.parse_args()
    
    log_path = args.log_path or get_default_log_path()
    
    print("=" * 50)
    print("TF2 Chat Translator - Overlay Mode")
    print("=" * 50)
    print(f"Log file: {log_path}")
    print(f"Position: {args.position}")
    print(f"Opacity: {args.opacity}")
    print()
    print("IMPORTANT: TF2 must be in 'Borderless Windowed' mode!")
    print("           (Options → Video → Display Mode)")
    print()
    print("Controls:")
    print("  🔓/🔒  Click to toggle click-through mode")
    print("  ✕      Close overlay")
    print("  Drag title bar to reposition")
    print("=" * 50)
    
    if not log_path.exists():
        print(f"\nWarning: Log file not found: {log_path}")
        print("Make sure TF2 is running with -condebug launch option")
        print("The overlay will wait for the file to be created...")
    
    overlay = TranslatorOverlay(
        log_path=log_path,
        opacity=args.opacity,
        position=args.position,
        max_messages=args.max_messages,
        tail_only=args.tail_only
    )
    
    try:
        overlay.start()
    except KeyboardInterrupt:
        overlay.stop()


if __name__ == "__main__":
    main()
