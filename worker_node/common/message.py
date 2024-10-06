# message.py
from enum import Enum
from pydantic import BaseModel
from typing import Dict, Any


class MessageType(str, Enum):
    BUILD = "build"
    MONITOR = "monitor"
    STATUS = "status"
    HEARTBEAT = "heartbeat"


class Message(BaseModel):
    type: MessageType
    task_id: str
    content: Dict[str, Any]
    version: str = "1.0"

    def to_json(self) -> str:
        """Serialize the message to a JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str):
        """Deserialize a JSON string to a Message object."""
        return cls.model_validate_json(json_str)
