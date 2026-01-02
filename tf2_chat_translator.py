#!/usr/bin/env python3
"""
TF2 Chat Translator
Monitors Team Fortress 2 console log and translates chat messages to English.

Usage:
    python tf2_chat_translator.py [--log-path PATH] [--no-color]

Requirements:
    - TF2 must be launched with -condebug in Steam launch options
    - Install dependencies: pip install -r requirements.txt
"""

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator

# Third-party imports
try:
    from langdetect import detect, DetectorFactory
    from deep_translator import GoogleTranslator
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install -r requirements.txt")
    sys.exit(1)

# Make language detection deterministic
DetectorFactory.seed = 0

# Rich console for pretty output
console = Console()


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
    
    # TF2 chat messages have a SPECIFIC format:
    # [*DEAD*] [(TEAM)] PlayerName :  message
    # Note: There is a SPACE before the colon, and TWO SPACES after the colon
    # This distinguishes them from system messages which use "Name: text" (one space)
    
    CHAT_PATTERN = re.compile(
        r'^(?P<dead>\*DEAD\*\s*)?'          # Optional *DEAD* prefix with optional space
        r'(?P<team>\(TEAM\)\s*)?'           # Optional (TEAM) prefix with optional space
        r'(?P<player_name>.+?)'             # Player name (non-greedy)
        r'\s:\s\s'                          # " :  " - space, colon, TWO spaces (TF2 chat signature)
        r'(?P<message>.+)$'                 # The actual message
    )
    
    # Lines to explicitly skip
    SKIP_PATTERNS = [
        # Kill feed messages
        re.compile(r'.+\skilled\s.+\swith\s'),
        re.compile(r'.+\ssuicided\.?$'),
        # Connection messages  
        re.compile(r'.+\sconnected$'),
        re.compile(r'.+\sdisconnected$'),
        # System messages
        re.compile(r'^(Steam|Map|Players|Build|Server|Network|Voice_|CAsync|Host_|Differing|qhull|Creating|SetupBones|Cannot|Attemped|Parent|Proto|Lobby|Client|Team Fortress|Connecting|Connected|Cleaning|Loading|Current|CTF|Shutdown|Unable|Sending|Disconnecting|Recognizing|The server|ProtoDefs|maxplayers|Connection|For FCVAR)'),
        re.compile(r'^\['),                 # Lines starting with [brackets]
        re.compile(r'^\s*$'),               # Empty lines
        re.compile(r'^---'),                # Separator lines
        re.compile(r'^\d'),                 # Lines starting with numbers
        re.compile(r'^pair\.'),             # qhull continuation
        re.compile(r'^magnitude'),          # qhull continuation
        re.compile(r'^try '),               # qhull continuation
    ]
    
    @classmethod
    def parse_line(cls, line: str) -> Optional[ChatMessage]:
        """
        Parse a single line from console.log.
        Returns ChatMessage if it's a chat message, None otherwise.
        """
        line = line.strip()
        
        if not line:
            return None
        
        # Skip known non-chat patterns
        for pattern in cls.SKIP_PATTERNS:
            if pattern.search(line):
                return None
        
        # Try to match chat pattern - requires " :  " (space-colon-space-space)
        match = cls.CHAT_PATTERN.match(line)
        
        if match:
            player_name = match.group('player_name').strip()
            message = match.group('message').strip()
            
            # Additional validation: skip if message looks like system output
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
        """Check if a message looks like system output rather than player chat."""
        # File path patterns
        if ':\\' in message or message.count('\\') > 1:
            return True
        if message.count('/') > 2:
            return True
            
        # Technical file extensions
        tech_extensions = ['.dll', '.wav', '.cfg', '.log', '.exe', '.txt', '.html']
        message_lower = message.lower()
        for ext in tech_extensions:
            if ext in message_lower:
                return True
        
        # Technical terms that wouldn't appear in chat
        tech_terms = ['bytes', ' mb ', 'capacity', 'precache', 'convexity']
        for term in tech_terms:
            if term in message_lower:
                return True
        
        return False

class Translator:
    """Handles language detection and translation."""
    
    # Languages we can translate from
    SUPPORTED_LANGUAGES = {
        'ru': 'Russian',
        'fr': 'French', 
        'de': 'German',
        'it': 'Italian',
        'es': 'Spanish',
        'pt': 'Portuguese',
        'pl': 'Polish',
        'nl': 'Dutch',
        'sv': 'Swedish',
        'da': 'Danish',
        'no': 'Norwegian',
        'fi': 'Finnish',
        'cs': 'Czech',
        'sk': 'Slovak',
        'hu': 'Hungarian',
        'ro': 'Romanian',
        'bg': 'Bulgarian',
        'uk': 'Ukrainian',
        'hr': 'Croatian',
        'sl': 'Slovenian',
        'et': 'Estonian',
        'lv': 'Latvian',
        'lt': 'Lithuanian',
        'el': 'Greek',
        'tr': 'Turkish',
        'ja': 'Japanese',
        'ko': 'Korean',
        'zh-cn': 'Chinese (Simplified)',
        'zh-tw': 'Chinese (Traditional)',
        'ar': 'Arabic',
        'he': 'Hebrew',
        'th': 'Thai',
        'vi': 'Vietnamese',
        'id': 'Indonesian',
    }
    
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='en')
        self._cache: dict[str, tuple[str, str]] = {}  # message -> (detected_lang, translation)
        self._translation_available = True
        self._error_shown = False
    
    def detect_language(self, text: str) -> Optional[str]:
        """Detect the language of text. Returns language code or None."""
        if len(text.strip()) < 3:
            return None
        
        try:
            lang = detect(text)
            return lang
        except Exception:
            return None
    
    def translate(self, text: str) -> tuple[str, str, str]:
        """
        Translate text to English.
        Returns: (original_text, detected_language, translated_text)
        """
        # Check cache first
        if text in self._cache:
            lang, translated = self._cache[text]
            return (text, lang, translated)
        
        # Detect language
        detected_lang = self.detect_language(text)
        
        # If English or detection failed, return original
        if detected_lang is None or detected_lang == 'en':
            return (text, 'en', text)
        
        # If translation API not available, return original with detected lang
        if not self._translation_available:
            return (text, detected_lang, text)
        
        try:
            translated = self.translator.translate(text)
            self._cache[text] = (detected_lang, translated)
            return (text, detected_lang, translated)
        except Exception as e:
            # On first translation failure, show warning
            if not self._error_shown:
                console.print(f"[yellow]⚠ Translation API unavailable: {type(e).__name__}[/yellow]")
                console.print("[yellow]  Messages will show detected language only.[/yellow]")
                console.print("[dim]  Check your internet connection or try again later.[/dim]\n")
                self._error_shown = True
                self._translation_available = False
            
            return (text, detected_lang, text)
    
    def get_language_name(self, code: str) -> str:
        """Get human-readable language name from code."""
        return self.SUPPORTED_LANGUAGES.get(code, code.upper())


class LogTailer:
    """Tails a log file, yielding new lines as they appear."""
    
    def __init__(self, filepath: Path, poll_interval: float = 0.1):
        self.filepath = filepath
        self.poll_interval = poll_interval
        self._position = 0
    
    def tail(self, start_from_end: bool = True) -> Generator[str, None, None]:
        """
        Generator that yields new lines from the log file.
        If start_from_end is True, only yields lines added after starting.
        """
        # Wait for file to exist
        while not self.filepath.exists():
            console.print(f"[yellow]Waiting for log file: {self.filepath}[/yellow]")
            time.sleep(2)
        
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            if start_from_end:
                # Seek to end
                f.seek(0, 2)
                self._position = f.tell()
            
            while True:
                line = f.readline()
                if line:
                    yield line
                else:
                    # No new line, wait and check for file truncation
                    time.sleep(self.poll_interval)
                    current_pos = f.tell()
                    f.seek(0, 2)
                    end_pos = f.tell()
                    
                    if end_pos < current_pos:
                        # File was truncated (e.g., -conclearlog on restart)
                        f.seek(0)
                    else:
                        f.seek(current_pos)


class ChatTranslatorApp:
    """Main application class."""
    
    def __init__(self, log_path: Path, use_color: bool = True, tail_only: bool = False):
        self.log_path = log_path
        self.use_color = use_color
        self.tail_only = tail_only
        self.parser = TF2LogParser()
        self.translator = Translator()
        self.tailer = LogTailer(log_path)
        self.message_count = 0
        self.translated_count = 0
    
    def format_message(self, chat: ChatMessage, detected_lang: str, translated: str) -> None:
        """Format and display a chat message with translation."""
        self.message_count += 1
        
        # Build prefix
        prefix_parts = []
        if chat.is_dead:
            prefix_parts.append("[dim]*DEAD*[/dim]")
        if chat.is_team:
            prefix_parts.append("[blue](TEAM)[/blue]")
        prefix = "".join(prefix_parts)
        
        # Determine if translation occurred or if we just detected the language
        is_foreign = detected_lang != 'en'
        is_translated = is_foreign and chat.message != translated
        
        if is_foreign:
            self.translated_count += 1
            lang_name = self.translator.get_language_name(detected_lang)
            
            if self.use_color:
                console.print(
                    f"{prefix}[bold cyan]{chat.player_name}[/bold cyan]: "
                    f"[dim]{chat.message}[/dim]"
                )
                if is_translated:
                    console.print(
                        f"  [green]→ [{lang_name}][/green] [white]{translated}[/white]"
                    )
                else:
                    # Show detected language even without translation
                    console.print(
                        f"  [yellow]  [{lang_name}][/yellow]"
                    )
            else:
                print(f"{chat.player_name}: {chat.message}")
                if is_translated:
                    print(f"  → [{lang_name}] {translated}")
                else:
                    print(f"    [{lang_name}]")
        else:
            # English message, display normally
            if self.use_color:
                console.print(
                    f"{prefix}[bold cyan]{chat.player_name}[/bold cyan]: "
                    f"[white]{chat.message}[/white]"
                )
            else:
                print(f"{chat.player_name}: {chat.message}")
    
    def run(self) -> None:
        """Main application loop."""
        mode_text = "New messages only" if self.tail_only else "Processing existing + new messages"
        
        if self.use_color:
            console.print(Panel.fit(
                "[bold green]TF2 Chat Translator[/bold green]\n"
                f"Monitoring: [cyan]{self.log_path}[/cyan]\n"
                f"Mode: [yellow]{mode_text}[/yellow]\n"
                "[dim]Press Ctrl+C to stop[/dim]",
                title="🎮 Starting",
                border_style="green"
            ))
        else:
            print("=" * 50)
            print("TF2 Chat Translator")
            print(f"Monitoring: {self.log_path}")
            print(f"Mode: {mode_text}")
            print("Press Ctrl+C to stop")
            print("=" * 50)
        
        try:
            for line in self.tailer.tail(start_from_end=self.tail_only):
                chat = self.parser.parse_line(line)
                if chat:
                    original, detected_lang, translated = self.translator.translate(chat.message)
                    self.format_message(chat, detected_lang, translated)
        
        except KeyboardInterrupt:
            if self.use_color:
                console.print(f"\n[yellow]Stopped.[/yellow] "
                             f"Processed {self.message_count} messages, "
                             f"translated {self.translated_count}.")
            else:
                print(f"\nStopped. Processed {self.message_count} messages, "
                      f"translated {self.translated_count}.")


def get_default_log_path() -> Path:
    """Get the default TF2 console.log path based on OS."""
    if sys.platform == 'win32':
        # Common Windows paths
        paths = [
            Path(r"D:\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
            Path(r"C:\Program Files\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
            Path(r"C:\Steam\steamapps\common\Team Fortress 2\tf\console.log"),
            Path.home() / "Steam/steamapps/common/Team Fortress 2/tf/console.log",
        ]
    elif sys.platform == 'darwin':
        # macOS
        paths = [
            Path.home() / "Library/Application Support/Steam/steamapps/common/Team Fortress 2/tf/console.log",
        ]
    else:
        # Linux
        paths = [
            Path.home() / ".steam/steam/steamapps/common/Team Fortress 2/tf/console.log",
            Path.home() / ".local/share/Steam/steamapps/common/Team Fortress 2/tf/console.log",
        ]
    
    for path in paths:
        if path.exists():
            return path
    
    # Return first path as default even if it doesn't exist
    return paths[0]


def main():
    parser = argparse.ArgumentParser(
        description="Monitor TF2 chat and translate messages to English",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tf2_chat_translator.py                    # Process all existing + new messages
  python tf2_chat_translator.py --tail-only        # Only show new messages
  python tf2_chat_translator.py --log-path D:\\path\\to\\console.log
  python tf2_chat_translator.py --no-color

Setup:
  1. Add -condebug to TF2's Steam launch options
     (Right-click TF2 → Properties → Set Launch Options)
  2. Optionally add -conclearlog to clear the log on each launch
  3. Run this script while playing TF2
        """
    )
    
    parser.add_argument(
        '--log-path', '-l',
        type=Path,
        default=None,
        help="Path to TF2 console.log (auto-detected if not specified)"
    )
    
    parser.add_argument(
        '--no-color',
        action='store_true',
        help="Disable colored output"
    )
    
    parser.add_argument(
        '--tail-only',
        action='store_true',
        help="Only show new messages (skip existing log content)"
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help="Run with test messages instead of monitoring log file"
    )
    
    args = parser.parse_args()
    
    if args.test:
        run_test_mode(not args.no_color)
        return
    
    log_path = args.log_path or get_default_log_path()
    
    if not log_path.exists():
        console.print(f"[yellow]Warning:[/yellow] Log file not found: {log_path}")
        console.print("[dim]Make sure TF2 is running with -condebug launch option[/dim]")
        console.print("[dim]The script will wait for the file to be created...[/dim]\n")
    
    app = ChatTranslatorApp(log_path, use_color=not args.no_color, tail_only=args.tail_only)
    app.run()


def run_test_mode(use_color: bool = True):
    """Run with test messages to verify parsing works and show expected output."""
    
    # Test data with pre-translated messages for demonstration
    # Format: (console_line, detected_lang, translation)
    test_data = [
        ("Player1 :  Hello everyone!", "en", "Hello everyone!"),
        ("*DEAD* RussianGamer :  Привет, как дела?", "ru", "Hi, how are you?"),
        ("(TEAM) FrenchPlayer :  Bonjour, quelqu'un peut m'aider?", "fr", "Hello, can someone help me?"),
        ("GermanSniper :  Guten Tag! Das Spiel ist toll!", "de", "Good day! The game is great!"),
        ("*DEAD*(TEAM) ItalianMedic :  Aiutatemi, ho bisogno di un medico!", "it", "Help me, I need a doctor!"),
        ("SpanishScout :  ¡Hola amigos! ¿Cómo están?", "es", "Hello friends! How are you?"),
        ("JapanesePlayer :  こんにちは、よろしくお願いします", "ja", "Hello, nice to meet you"),
        ("PolishEngineer :  Cześć wszystkim, zbudujmy razem!", "pl", "Hi everyone, let's build together!"),
        ("DutchHeavy :  Goedemiddag, ik heb munitie nodig", "nl", "Good afternoon, I need ammunition"),
        ("ChinesePlayer :  大家好，我是新来的", "zh-cn", "Hello everyone, I'm new here"),
        ("KoreanPlayer :  안녕하세요, 게임 잘 하시네요!", "ko", "Hello, you're good at the game!"),
    ]
    
    parser = TF2LogParser()
    translator = Translator()
    
    if use_color:
        console.print(Panel.fit(
            "[bold green]TF2 Chat Translator - Test Mode[/bold green]\n"
            "[dim]Demonstrating parsing and translation output...[/dim]\n"
            "[yellow]Note: Translations shown are pre-defined examples.[/yellow]\n"
            "[yellow]Run on your own PC for live translation.[/yellow]",
            title="🧪 Test",
            border_style="yellow"
        ))
    else:
        print("=" * 50)
        print("TF2 Chat Translator - Test Mode")
        print("Demonstrating parsing and translation output...")
        print("Note: Run on your own PC for live translation.")
        print("=" * 50)
    
    print()
    
    for line, detected_lang, translation in test_data:
        chat = parser.parse_line(line)
        if chat:
            # Build prefix
            prefix_parts = []
            if chat.is_dead:
                prefix_parts.append("[dim]*DEAD*[/dim]" if use_color else "*DEAD*")
            if chat.is_team:
                prefix_parts.append("[blue](TEAM)[/blue]" if use_color else "(TEAM)")
            prefix = "".join(prefix_parts)
            
            is_translated = detected_lang != 'en'
            
            if use_color:
                console.print(
                    f"{prefix}[bold cyan]{chat.player_name}[/bold cyan]: "
                    f"[dim]{chat.message}[/dim]"
                )
                if is_translated:
                    lang_name = translator.get_language_name(detected_lang)
                    console.print(
                        f"  [green]→ [{lang_name}][/green] [white]{translation}[/white]"
                    )
            else:
                print(f"{prefix}{chat.player_name}: {chat.message}")
                if is_translated:
                    lang_name = translator.get_language_name(detected_lang)
                    print(f"  → [{lang_name}] {translation}")
            
            print()
            time.sleep(0.3)  # Pause between messages for readability
    
    if use_color:
        console.print("[green]✓ Test complete![/green]")
        console.print("\n[dim]To use live translation, run this on your PC with internet access.[/dim]")
    else:
        print("Test complete!")
        print("\nTo use live translation, run this on your PC with internet access.")


if __name__ == "__main__":
    main()
