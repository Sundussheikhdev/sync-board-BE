from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class DrawData(BaseModel):
    x: float
    y: float
    color: str
    brush_size: int
    is_drawing: bool

class ChatMessage(BaseModel):
    user_id: str
    message: str
    timestamp: datetime
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None

class UserInfo(BaseModel):
    id: str
    room_id: str
    joined_at: datetime
    is_online: bool = True

class RoomInfo(BaseModel):
    id: str
    users: List[str]
    created_at: datetime
    last_activity: datetime

class FileUploadResponse(BaseModel):
    success: bool
    file_url: str
    filename: str
    content_type: str

class WebSocketMessage(BaseModel):
    type: str  # "draw", "chat", "join", "leave"
    data: Dict[str, Any]
    timestamp: Optional[datetime] = None 