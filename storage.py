# storage.py
import json
from pathlib import Path


class ChatStorage:
    """Работа с json-файлами чатов."""

    def __init__(self, chats_dir: str | Path = "chats"):
        self.chats_dir = Path(chats_dir)
        self.chats_dir.mkdir(exist_ok=True)

    def list_chat_names(self) -> list[str]:
        return sorted(p.stem for p in self.chats_dir.glob("*.json"))

    def load_chat(self, name: str) -> list[dict]:
        path = self.chats_dir / f"{name}.json"
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_chat(self, name: str, messages: list[dict]) -> None:
        path = self.chats_dir / f"{name}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    def delete_chat(self, name: str) -> None:
        path = self.chats_dir / f"{name}.json"
        if path.exists():
            path.unlink()

    def rename_chat(self, old_name: str, new_name: str) -> None:
        old_path = self.chats_dir / f"{old_name}.json"
        new_path = self.chats_dir / f"{new_name}.json"
        if old_path.exists():
            old_path.rename(new_path)

    def chat_exists(self, name: str) -> bool:
        return (self.chats_dir / f"{name}.json").exists()
