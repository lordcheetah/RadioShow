# config_manager.py
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from dataclasses import dataclass, field

@dataclass
class AppConfig:
    default_tts_engine: str = "Coqui XTTS"
    audio_quality: str = "high"  # low, medium, high
    auto_normalize: bool = True
    silence_padding_ms: int = 200
    max_line_length: int = 400
    backup_projects: bool = True
    theme: str = "system"
    training_envs: dict = field(default_factory=dict)  # map engine name -> python executable path
    last_used_dirs: dict = field(default_factory=dict)  # map dialog_key -> last used directory path
    
class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = AppConfig()
        self.load_config()
    
    def load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
            except Exception:
                pass  # Use defaults if config is corrupted
    
    def save_config(self):
        self.config_path.parent.mkdir(exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(asdict(self.config), f, indent=2)
    
    def get(self, key: str, default=None):
        return getattr(self.config, key, default)
    
    def set(self, key: str, value):
        if hasattr(self.config, key):
            setattr(self.config, key, value)
            self.save_config()

    # Convenience helpers for managing last-used directories per dialog
    def get_last_dir(self, dialog_key: str) -> Path | None:
        d = getattr(self.config, 'last_used_dirs', {}) or {}
        val = d.get(dialog_key)
        return Path(val) if val else None

    def set_last_dir(self, dialog_key: str, path: str | Path):
        d = getattr(self.config, 'last_used_dirs', {}) or {}
        d[dialog_key] = str(path)
        # Persist back to the config and save
        self.set('last_used_dirs', d)