from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

# Forum Category Model
class ForumCategory(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: str
    icon: str = "chatbubbles"  # Ionicons name
    order: int = 0
    parent_id: Optional[str] = None  # For sub-categories
    game_filter: Optional[str] = None  # "rs3", "rs3ba", or None for general
    is_locked: bool = False
    moderator_only: bool = False  # Only mods can post
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True

# Forum Thread Model
class ForumThread(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    category_id: str
    title: str
    author_id: str
    author_name: str
    is_pinned: bool = False
    is_locked: bool = False
    is_announcement: bool = False
    view_count: int = 0
    reply_count: int = 0
    last_post_at: datetime = Field(default_factory=datetime.utcnow)
    last_post_by: Optional[str] = None
    last_post_by_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: List[str] = []
    
    class Config:
        populate_by_name = True

# Forum Post Model
class ForumPost(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    thread_id: str
    author_id: str
    author_name: str
    content: str
    is_edited: bool = False
    edited_at: Optional[datetime] = None
    edited_by: Optional[str] = None
    is_deleted: bool = False
    deleted_by: Optional[str] = None
    reactions: dict = {}  # {"lol": ["user_id1"], "gg": ["user_id2"]}
    quote_post_id: Optional[str] = None  # If replying to specific post
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True

# User Signature Model (stored in player document)
class ForumSignature(BaseModel):
    image_url: Optional[str] = None
    image_width: int = 500  # Max width
    image_height: int = 150  # Max height
    text: Optional[str] = None  # Optional text above/below image
    enabled: bool = True

# Moderator Model
class ForumModerator(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    player_id: str
    player_name: str
    category_ids: List[str] = []  # Empty = global mod
    can_pin: bool = True
    can_lock: bool = True
    can_delete: bool = True
    can_edit: bool = True
    can_ban: bool = False  # Only super mods
    appointed_by: str
    appointed_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True

# Forum Ban Model
class ForumBan(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    player_id: str
    player_name: str
    reason: str
    banned_by: str
    banned_by_name: str
    expires_at: Optional[datetime] = None  # None = permanent
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True

# Classic 2000s Emojis
CLASSIC_EMOJIS = {
    ":)": "😊",
    ":(": "😢", 
    ":D": "😃",
    ";)": "😉",
    ":P": "😛",
    ":O": "😮",
    "B)": "😎",
    ">:(": "😠",
    ":'(": "😭",
    ":lol:": "🤣",
    ":gg:": "🤝",
    ":owned:": "💀",
    ":noob:": "👶",
    ":pro:": "👑",
    ":gg:": "🏆",
    ":rage:": "🔥",
    ":rip:": "⚰️",
    ":ez:": "😏",
    ":clutch:": "🎯",
    ":ace:": "♠️",
    ":headshot:": "🎯",
    ":camp:": "⛺",
    ":rush:": "🏃",
    ":nade:": "💣",
    ":snipe:": "🔫",
}

def parse_emojis(text: str) -> str:
    """Convert classic text emojis to unicode"""
    for code, emoji in CLASSIC_EMOJIS.items():
        text = text.replace(code, emoji)
    return text
