from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uuid
from datetime import datetime
from bson import ObjectId
from passlib.context import CryptContext

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Redirect root to Expo frontend (workaround for custom domain routing)
from fastapi.responses import RedirectResponse

# Get frontend URL from environment variable
FRONTEND_URL = os.environ.get('FRONTEND_URL', '')

@app.get("/")
async def root_redirect():
    """Redirect root to the Expo frontend preview URL or return API info"""
    if FRONTEND_URL:
        return RedirectResponse(url=FRONTEND_URL, status_code=302)
    return {"message": "RETRO REMATCH API", "status": "running", "docs": "/docs"}

@app.get("/api/health")
async def health_check():
    """Health check endpoint for keep-alive pings"""
    return {"status": "ok", "message": "RETRO REMATCH is running"}

# Game constants - the two supported games
SUPPORTED_GAMES = ["Rainbow Six 3", "Rainbow Six 3: Black Arrow"]

# Helper function to convert ObjectId to string
def serialize_doc(doc):
    if doc:
        doc['_id'] = str(doc['_id'])
    return doc

# Helper function to check if player can manage clan (leader, captain, or co-captain)
async def can_manage_clan(clan_id: str, player_id: str) -> bool:
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        if not clan:
            return False
        return player_id in [clan.get('leader_id'), clan.get('captain_id'), clan.get('co_captain_id')]
    except:
        return False

# Helper function to check if player is captain or above
async def is_captain_or_above(clan_id: str, player_id: str) -> bool:
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        if not clan:
            return False
        return player_id in [clan.get('leader_id'), clan.get('captain_id')]
    except:
        return False

# ==================== MODELS ====================

class PlayerCreate(BaseModel):
    username: str
    password: str  # Required password for signup
    avatar: Optional[str] = None  # base64 encoded image
    bio: Optional[str] = ""
    gamertag_rs3: Optional[str] = ""  # Gamertag for Rainbow Six 3
    gamertag_rs3ba: Optional[str] = ""  # Gamertag for Rainbow Six 3: Black Arrow
    discord_handle: Optional[str] = ""  # Discord username/handle

class PlayerLogin(BaseModel):
    username: str
    password: str

class ForgotPasswordRequest(BaseModel):
    username: str
    email: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

class PlayerUpdate(BaseModel):
    username: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    gamertag_rs3: Optional[str] = None
    gamertag_rs3ba: Optional[str] = None
    discord_handle: Optional[str] = None  # Discord username/handle
    # Payment info for cash tourneys
    cashapp_tag: Optional[str] = None
    venmo_username: Optional[str] = None
    paypal_email: Optional[str] = None

class Player(BaseModel):
    id: str = Field(alias='_id')
    username: str
    avatar: Optional[str] = None
    bio: Optional[str] = ""
    gamertag_rs3: Optional[str] = ""
    gamertag_rs3ba: Optional[str] = ""
    discord_handle: Optional[str] = ""  # Discord username/handle
    clan_id: Optional[str] = None
    # Overall stats
    stats: dict = {"matches_played": 0, "wins": 0, "losses": 0}
    # Per-game stats: {"Rainbow Six 3": {"wins": 0, "losses": 0, "clan_kills": 0, "quick_kills": 0}, ...}
    game_stats: dict = {}
    # Cash tournament wins counter
    cash_tourney_wins: int = 0
    # Payment info
    cashapp_tag: Optional[str] = None
    venmo_username: Optional[str] = None
    paypal_email: Optional[str] = None
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Clan member with role
class ClanMember(BaseModel):
    player_id: str
    role: str  # leader, captain, co_captain, member

class ClanCreate(BaseModel):
    name: str
    tag: str  # Short clan tag like [EPIC]
    game: str  # "Rainbow Six 3" or "Rainbow Six 3: Black Arrow"
    description: Optional[str] = ""
    logo: Optional[str] = None  # base64 encoded image
    avatar_icon: Optional[str] = None  # Preset avatar icon ID
    discord_link: Optional[str] = ""
    twitch_link: Optional[str] = ""
    leader_id: str

class ClanUpdate(BaseModel):
    name: Optional[str] = None
    tag: Optional[str] = None
    description: Optional[str] = None
    logo: Optional[str] = None
    discord_link: Optional[str] = None
    twitch_link: Optional[str] = None
    avatar_icon: Optional[str] = None  # Preset avatar icon ID
    tag: Optional[str] = None  # Clan tag prefix

# Preset retro 2000s gaming avatars for clans
CLAN_AVATAR_PRESETS = [
    {"id": "skull", "name": "Skull", "icon": "skull"},
    {"id": "crosshair", "name": "Crosshair", "icon": "crosshairs"},
    {"id": "grenade", "name": "Grenade", "icon": "bomb"},
    {"id": "military", "name": "Military", "icon": "medal"},
    {"id": "eagle", "name": "Eagle", "icon": "aircraft"},
    {"id": "fire", "name": "Fire", "icon": "flame"},
    {"id": "lightning", "name": "Lightning", "icon": "flash"},
    {"id": "crown", "name": "Crown", "icon": "crown"},
    {"id": "nuclear", "name": "Nuclear", "icon": "nuclear"},
    {"id": "dragon", "name": "Dragon", "icon": "dragon"},
    {"id": "sword", "name": "Sword", "icon": "sword"},
    {"id": "star", "name": "Star", "icon": "star"},
    {"id": "phoenix", "name": "Phoenix", "icon": "flame"},
    {"id": "wolf", "name": "Wolf", "icon": "paw"},
    {"id": "cobra", "name": "Cobra", "icon": "snake"},
    {"id": "viper", "name": "Viper", "icon": "eye"},
]

class RoleAssignment(BaseModel):
    player_id: str
    role: str  # captain, co_captain, member (leader cannot be assigned this way)

class Clan(BaseModel):
    id: str = Field(alias='_id')
    name: str
    tag: str
    game: str  # Which game this clan competes in
    description: Optional[str] = ""
    logo: Optional[str] = None
    avatar_icon: Optional[str] = None  # Preset avatar icon ID (e.g., "skull", "crosshair")
    leader_id: str
    captain_id: Optional[str] = None
    co_captain_id: Optional[str] = None
    members: List[str] = []  # List of player IDs (all members including leader/captain/co-captain)
    stats: dict = {"wins": 0, "losses": 0, "points": 1000}  # ELO-like starting points
    is_verified: bool = False  # Verified clan badge
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Challenge Model
class ChallengeCreate(BaseModel):
    challenger_clan_id: str
    challenged_clan_id: str
    proposed_time: datetime
    message: Optional[str] = ""

class Challenge(BaseModel):
    id: str = Field(alias='_id')
    challenger_clan_id: str
    challenger_clan_name: str
    challenged_clan_id: str
    challenged_clan_name: str
    game: str
    proposed_time: datetime
    message: Optional[str] = ""
    status: str = "pending"  # pending, accepted, declined, expired
    match_id: Optional[str] = None  # Set when challenge is accepted and match is created
    created_by: str  # Player ID who created the challenge
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Join Request Models (for clan membership approval - player requests to join)
class JoinRequestCreate(BaseModel):
    clan_id: str
    player_id: str
    message: Optional[str] = ""

class JoinRequest(BaseModel):
    id: str = Field(alias='_id')
    clan_id: str
    clan_name: str
    player_id: str
    player_username: str
    message: Optional[str] = ""
    status: str = "pending"  # pending, approved, denied
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Clan Invite Models (leader/captain sends invite to player)
class ClanInviteCreate(BaseModel):
    clan_id: str
    player_id: str  # Player being invited
    message: Optional[str] = ""

class ClanInvite(BaseModel):
    id: str = Field(alias='_id')
    clan_id: str
    clan_name: str
    clan_tag: str
    clan_logo: Optional[str] = None
    player_id: str  # Player being invited
    invited_by_id: str  # Leader/captain who sent invite
    invited_by_username: str
    message: Optional[str] = ""
    status: str = "pending"  # pending, accepted, declined
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Chat Message Models
class ChatMessageCreate(BaseModel):
    player_id: str
    message: str
    clan_id: Optional[str] = None  # If set, it's a clan message; if None, it's global

class ChatMessage(BaseModel):
    id: str = Field(alias='_id')
    player_id: str
    player_username: str
    player_avatar: Optional[str] = None
    message: str
    clan_id: Optional[str] = None
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Flash Match Models (for pickup games)
class FlashMatchPlayer(BaseModel):
    name: str
    kills: int = 0

class FlashMatchTeam(BaseModel):
    name: str
    players: List[FlashMatchPlayer] = []

class FlashMatchCreate(BaseModel):
    game: str  # "Rainbow Six 3" or "Rainbow Six 3: Black Arrow"
    team_a_name: str
    team_a_players: List[str]  # List of player names (up to 8)
    team_a_player_ids: Optional[List[Optional[str]]] = None  # Optional player IDs for stat tracking
    team_b_name: str
    team_b_players: List[str]  # List of player names (up to 8)
    team_b_player_ids: Optional[List[Optional[str]]] = None  # Optional player IDs for stat tracking

class FlashMatchScoreReport(BaseModel):
    maps_won_a: int
    maps_won_b: int
    team_a_kills: List[dict]  # [{"name": "player1", "kills": 10}, ...]
    team_b_kills: List[dict]  # [{"name": "player2", "kills": 8}, ...]
    reporter_id: Optional[str] = None  # ID of the player reporting the score
    reporter_name: Optional[str] = None  # Name of the player reporting (for quick match participants)

# ==================== CASH TOURNAMENT MODELS ====================

# Tournament Team Player
class TournamentTeamPlayer(BaseModel):
    player_name: str  # Can be manually entered or from player list
    player_id: Optional[str] = None  # If linked to registered player
    has_paid: bool = False  # Green (True) / Red (False) indicator
    kills: int = 0  # Kill count for the tournament

# Tournament Team (temporary team for cash tourneys)
class TournamentTeamCreate(BaseModel):
    tournament_id: str
    team_name: str
    captain_id: str  # Player ID of team captain
    captain_name: str

class TournamentTeam(BaseModel):
    id: str = Field(alias='_id')
    tournament_id: str
    team_name: str
    captain_id: str
    captain_name: str
    players: List[dict] = []  # List of TournamentTeamPlayer dicts
    team_paid: bool = False  # If captain paid for entire team
    seed: Optional[int] = None
    eliminated: bool = False
    created_at: datetime
    
    class Config:
        populate_by_name = True

# Tournament Match (Best of 5)
class TournamentMatchScoreReport(BaseModel):
    team_a_maps_won: int  # 0-3 for best of 5
    team_b_maps_won: int  # 0-3 for best of 5
    team_a_player_kills: List[dict] = []  # [{"player_name": "...", "kills": 10}, ...]
    team_b_player_kills: List[dict] = []

# Tournament Invite (captain invites player to tournament team)
class TournamentInviteCreate(BaseModel):
    tournament_id: str
    team_id: str
    player_id: str  # Player being invited

class TournamentParticipant(BaseModel):
    clan_id: str
    clan_name: str
    clan_tag: str
    has_paid: bool = False  # Red (False) / Green (True) indicator
    seed: Optional[int] = None

class TournamentMatchResult(BaseModel):
    match_id: str
    round_number: int
    match_number: int
    team_a_id: Optional[str] = None
    team_b_id: Optional[str] = None
    team_a_name: Optional[str] = None
    team_b_name: Optional[str] = None
    winner_id: Optional[str] = None
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    player_kills: List[dict] = []  # Kill stats per player
    status: str = "pending"  # pending, in_progress, completed

class CashTournamentCreate(BaseModel):
    name: str
    game: str
    buy_in_amount: float  # Per player or per team
    payout_amount: float
    max_teams: int = 8  # Must be power of 2 for bracket
    buy_in_per_player: bool = True  # True = each player pays, False = captain pays for team
    description: Optional[str] = ""
    twitch_link_1: Optional[str] = ""  # Stream link 1
    twitch_link_2: Optional[str] = ""  # Stream link 2

class CashTournamentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    twitch_link_1: Optional[str] = None
    twitch_link_2: Optional[str] = None

class CashTournament(BaseModel):
    id: str = Field(alias='_id')
    name: str
    game: str
    buy_in_amount: float
    payout_amount: float
    max_teams: int
    description: Optional[str] = ""
    twitch_link_1: Optional[str] = ""  # Stream link 1
    twitch_link_2: Optional[str] = ""  # Stream link 2
    creator_id: str
    creator_username: str
    participants: List[dict] = []
    bracket: List[dict] = []  # Tournament bracket structure
    status: str = "registration"  # registration, in_progress, completed, cancelled
    winner_id: Optional[str] = None
    winner_name: Optional[str] = None
    created_at: datetime
    
    class Config:
        populate_by_name = True

class MatchCreate(BaseModel):
    clan_a_id: str
    clan_b_id: str
    scheduled_time: datetime
    description: Optional[str] = ""

class MatchUpdate(BaseModel):
    status: Optional[str] = None  # scheduled, in_progress, completed, cancelled
    score_clan_a: Optional[int] = None
    score_clan_b: Optional[int] = None
    winner_id: Optional[str] = None

class PlayerKillReport(BaseModel):
    player_id: str
    player_name: str
    kills: int

class ScoreReport(BaseModel):
    score_clan_a: int
    score_clan_b: int
    reporter_id: str
    clan_a_kills: Optional[List[PlayerKillReport]] = None
    clan_b_kills: Optional[List[PlayerKillReport]] = None

class Match(BaseModel):
    id: str = Field(alias='_id')
    clan_a_id: str
    clan_b_id: str
    clan_a_name: Optional[str] = None
    clan_b_name: Optional[str] = None
    game: str  # Determined by the clans' game
    scheduled_time: datetime
    description: Optional[str] = ""
    status: str = "scheduled"  # scheduled, in_progress, completed, cancelled
    score_clan_a: int = 0
    score_clan_b: int = 0
    winner_id: Optional[str] = None
    challenge_id: Optional[str] = None  # Reference to challenge if created from one
    score_reported_by: Optional[str] = None  # Who reported the final score
    created_at: datetime
    
    class Config:
        populate_by_name = True

# ==================== GAME CONFIG ROUTES ====================

@api_router.get("/games")
async def get_supported_games():
    """Get list of supported games"""
    return {"games": SUPPORTED_GAMES}

@api_router.get("/clan-avatars")
async def get_clan_avatars():
    """Get list of preset clan avatars"""
    return {"avatars": CLAN_AVATAR_PRESETS}

# ==================== PLAYER ROUTES ====================

@api_router.post("/players", response_model=dict)
async def create_player(player: PlayerCreate):
    # Check if username exists
    existing = await db.players.find_one({"username": player.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Validate password
    if len(player.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    
    player_dict = player.dict()
    # Hash the password before storing
    player_dict['password_hash'] = hash_password(player_dict.pop('password'))
    player_dict['clan_id'] = None
    player_dict['stats'] = {"matches_played": 0, "wins": 0, "losses": 0}
    player_dict['created_at'] = datetime.utcnow()
    
    result = await db.players.insert_one(player_dict)
    player_dict['_id'] = str(result.inserted_id)
    # Don't return password hash
    del player_dict['password_hash']
    return serialize_doc(player_dict)

@api_router.post("/players/login", response_model=dict)
async def login_player(login: PlayerLogin):
    """Authenticate a player with username and password (case-insensitive username)"""
    import re
    
    # Case-insensitive username search
    player = await db.players.find_one({
        "username": {"$regex": f"^{re.escape(login.username)}$", "$options": "i"}
    })
    
    if not player:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    # Check if this is an old account without password (needs migration)
    if 'password_hash' not in player:
        raise HTTPException(status_code=400, detail="Account needs password setup. Please contact support.")
    
    if not verify_password(login.password, player['password_hash']):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    # Return player data (without password hash)
    player_data = serialize_doc(player)
    if 'password_hash' in player_data:
        del player_data['password_hash']
    return player_data

@api_router.post("/players/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Request a password reset. Requires username and email for verification."""
    import re
    import secrets
    from datetime import datetime, timedelta
    
    # Case-insensitive username search
    player = await db.players.find_one({
        "username": {"$regex": f"^{re.escape(request.username)}$", "$options": "i"}
    })
    
    if not player:
        # Don't reveal if username exists for security
        return {"message": "If an account with that username and email exists, you will receive reset instructions."}
    
    # Check if player has email set
    player_email = player.get('email', '').lower().strip()
    request_email = request.email.lower().strip()
    
    if not player_email or player_email != request_email:
        # Don't reveal if email matches for security
        return {"message": "If an account with that username and email exists, you will receive reset instructions."}
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    reset_expires = datetime.utcnow() + timedelta(hours=1)
    
    # Store reset token in database
    await db.players.update_one(
        {"_id": player["_id"]},
        {"$set": {
            "reset_token": reset_token,
            "reset_token_expires": reset_expires
        }}
    )
    
    # For now, return the token directly (in production, this would be emailed)
    # TODO: Integrate email service to send reset link
    return {
        "message": "Password reset token generated.",
        "reset_token": reset_token,
        "note": "In production, this token would be emailed to you. For now, use this token to reset your password."
    }

@api_router.post("/players/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using a valid reset token."""
    from datetime import datetime
    
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Find player with this reset token
    player = await db.players.find_one({
        "reset_token": request.reset_token,
        "reset_token_expires": {"$gt": datetime.utcnow()}
    })
    
    if not player:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Hash the new password
    new_password_hash = hash_password(request.new_password)
    
    # Update password and remove reset token
    await db.players.update_one(
        {"_id": player["_id"]},
        {
            "$set": {"password_hash": new_password_hash},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )
    
    return {"message": "Password has been reset successfully. You can now log in with your new password."}

@api_router.post("/players/{player_id}/set-email")
async def set_player_email(player_id: str, email: str):
    """Set or update player's email for password recovery."""
    import re
    
    # Basic email validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    try:
        result = await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"email": email.lower().strip()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Player not found")
        return {"message": "Email updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/players", response_model=List[dict])
async def get_players():
    # Exclude password_hash at query time for security and performance
    players = await db.players.find({}, {'password_hash': 0}).to_list(1000)
    result = []
    for p in players:
        player_data = serialize_doc(p)
        result.append(player_data)
    return result

@api_router.get("/players/{player_id}", response_model=dict)
async def get_player(player_id: str):
    try:
        # Exclude password_hash at query time
        player = await db.players.find_one({"_id": ObjectId(player_id)}, {'password_hash': 0})
    except:
        raise HTTPException(status_code=400, detail="Invalid player ID")
    
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player_data = serialize_doc(player)
    if 'password_hash' in player_data:
        del player_data['password_hash']
    return player_data

@api_router.get("/players/username/{username}", response_model=dict)
async def get_player_by_username(username: str):
    # Exclude password_hash at query time
    player = await db.players.find_one({"username": username}, {'password_hash': 0})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player_data = serialize_doc(player)
    return player_data

@api_router.put("/players/{player_id}", response_model=dict)
async def update_player(player_id: str, update: PlayerUpdate):
    try:
        update_dict = {k: v for k, v in update.dict().items() if v is not None}
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": update_dict}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Exclude password_hash from response
        player = await db.players.find_one({"_id": ObjectId(player_id)}, {'password_hash': 0})
        return serialize_doc(player)
    except HTTPException:
        raise
    except:
        raise HTTPException(status_code=400, detail="Invalid player ID")

# ==================== CLAN ROUTES ====================

@api_router.post("/clans", response_model=dict)
async def create_clan(clan: ClanCreate):
    # Validate game
    if clan.game not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Game must be one of: {SUPPORTED_GAMES}")
    
    # Check if tag exists for this game
    existing = await db.clans.find_one({"tag": clan.tag, "game": clan.game})
    if existing:
        raise HTTPException(status_code=400, detail="Clan tag already exists for this game")
    
    # Check if leader exists and doesn't have a clan for this game
    try:
        leader = await db.players.find_one({"_id": ObjectId(clan.leader_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid leader ID")
    
    if not leader:
        raise HTTPException(status_code=404, detail="Leader player not found")
    
    # Check if player is already in a clan for this game
    existing_clan = await db.clans.find_one({
        "game": clan.game,
        "members": clan.leader_id
    })
    if existing_clan:
        raise HTTPException(status_code=400, detail=f"Leader already in a clan for {clan.game}")
    
    clan_dict = clan.dict()
    clan_dict['members'] = [clan.leader_id]
    clan_dict['captain_id'] = None
    clan_dict['co_captain_id'] = None
    clan_dict['stats'] = {"wins": 0, "losses": 0, "points": 1000}
    clan_dict['created_at'] = datetime.utcnow()
    
    result = await db.clans.insert_one(clan_dict)
    clan_id = str(result.inserted_id)
    
    # Update player's clan_id (for their primary clan)
    await db.players.update_one(
        {"_id": ObjectId(clan.leader_id)},
        {"$set": {"clan_id": clan_id}}
    )
    
    clan_dict['_id'] = clan_id
    return serialize_doc(clan_dict)

@api_router.get("/clans", response_model=List[dict])
async def get_clans(game: Optional[str] = None):
    query = {}
    if game:
        query['game'] = game
    clans = await db.clans.find(query).to_list(1000)
    return [serialize_doc(c) for c in clans]

@api_router.get("/clans/{clan_id}", response_model=dict)
async def get_clan(clan_id: str):
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    return serialize_doc(clan)

@api_router.put("/clans/{clan_id}", response_model=dict)
async def update_clan(clan_id: str, update: ClanUpdate):
    try:
        update_dict = {k: v for k, v in update.dict().items() if v is not None}
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = await db.clans.update_one(
            {"_id": ObjectId(clan_id)},
            {"$set": update_dict}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Clan not found")
        
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        return serialize_doc(clan)
    except HTTPException:
        raise
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")


@api_router.post("/clans/{clan_id}/verify", response_model=dict)
async def verify_clan(clan_id: str, verified: bool = True):
    """Toggle verified status for a clan (admin only - no auth check for simplicity)"""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        if not clan:
            raise HTTPException(status_code=404, detail="Clan not found")
        
        await db.clans.update_one(
            {"_id": ObjectId(clan_id)},
            {"$set": {"is_verified": verified}}
        )
        
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        return serialize_doc(clan)
    except HTTPException:
        raise
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")


@api_router.post("/clans/{clan_id}/assign-role", response_model=dict)
async def assign_role(clan_id: str, assignment: RoleAssignment, requester_id: str):
    """Assign a role to a clan member. Only leader can assign roles."""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        player = await db.players.find_one({"_id": ObjectId(assignment.player_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Only leader can assign roles
    if clan.get('leader_id') != requester_id:
        raise HTTPException(status_code=403, detail="Only the clan leader can assign roles")
    
    # Player must be a member
    if assignment.player_id not in clan.get('members', []):
        raise HTTPException(status_code=400, detail="Player is not a member of this clan")
    
    # Cannot change leader role this way
    if assignment.role == 'leader':
        raise HTTPException(status_code=400, detail="Cannot assign leader role. Use transfer leadership instead.")
    
    # Validate role
    if assignment.role not in ['captain', 'co_captain', 'member']:
        raise HTTPException(status_code=400, detail="Role must be: captain, co_captain, or member")
    
    update_data = {}
    
    if assignment.role == 'captain':
        # Clear old captain if exists
        update_data['captain_id'] = assignment.player_id
    elif assignment.role == 'co_captain':
        # Clear old co-captain if exists
        update_data['co_captain_id'] = assignment.player_id
    elif assignment.role == 'member':
        # If they were captain or co-captain, remove that role
        if clan.get('captain_id') == assignment.player_id:
            update_data['captain_id'] = None
        if clan.get('co_captain_id') == assignment.player_id:
            update_data['co_captain_id'] = None
    
    if update_data:
        await db.clans.update_one(
            {"_id": ObjectId(clan_id)},
            {"$set": update_data}
        )
    
    clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    return serialize_doc(clan)

@api_router.post("/clans/{clan_id}/transfer-leadership", response_model=dict)
async def transfer_leadership(clan_id: str, new_leader_id: str, requester_id: str):
    """Transfer clan leadership to another member."""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        new_leader = await db.players.find_one({"_id": ObjectId(new_leader_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not new_leader:
        raise HTTPException(status_code=404, detail="New leader not found")
    
    # Only current leader can transfer
    if clan.get('leader_id') != requester_id:
        raise HTTPException(status_code=403, detail="Only the current leader can transfer leadership")
    
    # New leader must be a member
    if new_leader_id not in clan.get('members', []):
        raise HTTPException(status_code=400, detail="New leader must be a clan member")
    
    update_data = {'leader_id': new_leader_id}
    
    # If new leader was captain or co-captain, clear that role
    if clan.get('captain_id') == new_leader_id:
        update_data['captain_id'] = None
    if clan.get('co_captain_id') == new_leader_id:
        update_data['co_captain_id'] = None
    
    await db.clans.update_one(
        {"_id": ObjectId(clan_id)},
        {"$set": update_data}
    )
    
    clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    return serialize_doc(clan)

@api_router.post("/clans/{clan_id}/join", response_model=dict)
async def join_clan(clan_id: str, player_id: str):
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        player = await db.players.find_one({"_id": ObjectId(player_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Check if player is already in a clan for this game
    existing_clan = await db.clans.find_one({
        "game": clan['game'],
        "members": player_id
    })
    if existing_clan:
        raise HTTPException(status_code=400, detail=f"Player already in a clan for {clan['game']}")
    
    # Add player to clan
    await db.clans.update_one(
        {"_id": ObjectId(clan_id)},
        {"$push": {"members": player_id}}
    )
    
    # Update player's clan_id to this clan
    await db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"clan_id": clan_id}}
    )
    
    clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    return serialize_doc(clan)

@api_router.post("/clans/{clan_id}/leave", response_model=dict)
async def leave_clan(clan_id: str, player_id: str):
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        player = await db.players.find_one({"_id": ObjectId(player_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player_id not in clan.get('members', []):
        raise HTTPException(status_code=400, detail="Player not in this clan")
    if clan.get('leader_id') == player_id:
        raise HTTPException(status_code=400, detail="Leader cannot leave. Transfer leadership first or delete clan.")
    
    # Remove player from clan
    await db.clans.update_one(
        {"_id": ObjectId(clan_id)},
        {"$pull": {"members": player_id}}
    )
    
    # If player was captain or co-captain, clear that role
    update_data = {}
    if clan.get('captain_id') == player_id:
        update_data['captain_id'] = None
    if clan.get('co_captain_id') == player_id:
        update_data['co_captain_id'] = None
    
    if update_data:
        await db.clans.update_one(
            {"_id": ObjectId(clan_id)},
            {"$set": update_data}
        )
    
    # Clear player's clan_id if this was their primary clan
    if player.get('clan_id') == clan_id:
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"clan_id": None}}
        )
    
    return {"message": "Successfully left clan"}

@api_router.delete("/clans/{clan_id}", response_model=dict)
async def delete_clan(clan_id: str, leader_id: str):
    """Delete a clan (leader only)"""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    if clan.get('leader_id') != leader_id:
        raise HTTPException(status_code=403, detail="Only the clan leader can delete the clan")
    
    # Clear clan_id from all members
    member_ids = clan.get('members', [])
    for member_id in member_ids:
        try:
            await db.players.update_one(
                {"_id": ObjectId(member_id)},
                {"$set": {"clan_id": None}}
            )
        except:
            pass
    
    # Delete the clan
    await db.clans.delete_one({"_id": ObjectId(clan_id)})
    
    # Also delete any pending invites for this clan
    await db.clan_invites.delete_many({"clan_id": clan_id})
    
    # Delete any pending challenges involving this clan
    await db.challenges.delete_many({
        "$or": [
            {"challenger_id": clan_id},
            {"challenged_id": clan_id}
        ],
        "status": "pending"
    })
    
    return {"message": "Clan deleted successfully"}

@api_router.post("/clans/{clan_id}/kick/{member_id}", response_model=dict)
async def kick_member(clan_id: str, member_id: str, requester_id: str):
    """Kick a member from the clan. Only captain or co-captain can kick members."""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        member = await db.players.find_one({"_id": ObjectId(member_id)})
        requester = await db.players.find_one({"_id": ObjectId(requester_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if not requester:
        raise HTTPException(status_code=404, detail="Requester not found")
    
    # Check if requester has permission to kick - only captain or co-captain
    is_captain = clan.get('captain_id') == requester_id
    is_co_captain = clan.get('co_captain_id') == requester_id
    
    if not is_captain and not is_co_captain:
        raise HTTPException(status_code=403, detail="Only captain or co-captain can kick members")
    
    # Check if member is in the clan
    if member_id not in clan.get('members', []):
        raise HTTPException(status_code=400, detail="Player is not a member of this clan")
    
    # Cannot kick the leader
    if clan.get('leader_id') == member_id:
        raise HTTPException(status_code=400, detail="Cannot kick the clan leader")
    
    # Cannot kick other captains or co-captains
    if member_id == clan.get('captain_id') or member_id == clan.get('co_captain_id'):
        raise HTTPException(status_code=403, detail="Cannot kick other captains")
    
    # Remove player from clan
    await db.clans.update_one(
        {"_id": ObjectId(clan_id)},
        {"$pull": {"members": member_id}}
    )
    
    # If kicked member was captain or co-captain, clear that role
    update_data = {}
    if clan.get('captain_id') == member_id:
        update_data['captain_id'] = None
    if clan.get('co_captain_id') == member_id:
        update_data['co_captain_id'] = None
    
    if update_data:
        await db.clans.update_one(
            {"_id": ObjectId(clan_id)},
            {"$set": update_data}
        )
    
    # Clear player's clan_id if this was their primary clan
    if member.get('clan_id') == clan_id:
        await db.players.update_one(
            {"_id": ObjectId(member_id)},
            {"$set": {"clan_id": None}}
        )
    
    return {"message": f"Successfully kicked {member['username']} from the clan"}

@api_router.get("/clans/{clan_id}/members", response_model=List[dict])
async def get_clan_members(clan_id: str):
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    member_ids = [ObjectId(m) for m in clan.get('members', [])]
    # Exclude password_hash at query time for security
    members = await db.players.find({"_id": {"$in": member_ids}}, {'password_hash': 0}).to_list(100)
    
    # Add role information to each member
    result = []
    for member in members:
        member_data = serialize_doc(member)
        member_id = member_data['_id']
        
        if member_id == clan.get('leader_id'):
            member_data['role'] = 'leader'
        elif member_id == clan.get('captain_id'):
            member_data['role'] = 'captain'
        elif member_id == clan.get('co_captain_id'):
            member_data['role'] = 'co_captain'
        else:
            member_data['role'] = 'member'
        
        result.append(member_data)
    
    # Sort by role importance
    role_order = {'leader': 0, 'captain': 1, 'co_captain': 2, 'member': 3}
    result.sort(key=lambda x: role_order.get(x.get('role', 'member'), 3))
    
    return result

@api_router.get("/players/{player_id}/clans", response_model=List[dict])
async def get_player_clans(player_id: str):
    """Get all clans a player is a member of (can be in one clan per game)"""
    clans = await db.clans.find({"members": player_id}).to_list(10)
    return [serialize_doc(c) for c in clans]

# ==================== JOIN REQUEST ROUTES ====================

@api_router.post("/join-requests", response_model=dict)
async def create_join_request(request: JoinRequestCreate):
    """Request to join a clan. Leader must approve."""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(request.clan_id)})
        player = await db.players.find_one({"_id": ObjectId(request.player_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Check if player is already in a clan for this game
    existing_clan = await db.clans.find_one({
        "game": clan['game'],
        "members": request.player_id
    })
    if existing_clan:
        raise HTTPException(status_code=400, detail=f"You are already in a clan for {clan['game']}")
    
    # Check if there's already a pending request
    existing_request = await db.join_requests.find_one({
        "clan_id": request.clan_id,
        "player_id": request.player_id,
        "status": "pending"
    })
    if existing_request:
        raise HTTPException(status_code=400, detail="You already have a pending request for this clan")
    
    join_request = {
        "clan_id": request.clan_id,
        "clan_name": clan['name'],
        "player_id": request.player_id,
        "player_username": player['username'],
        "player_avatar": player.get('avatar'),
        "message": request.message or "",
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    
    result = await db.join_requests.insert_one(join_request)
    join_request['_id'] = str(result.inserted_id)
    return serialize_doc(join_request)

@api_router.get("/join-requests/clan/{clan_id}", response_model=List[dict])
async def get_clan_join_requests(clan_id: str, status: Optional[str] = "pending"):
    """Get all join requests for a clan. Only leader/captain can view."""
    try:
        query = {"clan_id": clan_id}
        if status:
            query["status"] = status
        requests = await db.join_requests.find(query).sort("created_at", -1).to_list(100)
        return [serialize_doc(r) for r in requests]
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")

@api_router.get("/join-requests/player/{player_id}", response_model=List[dict])
async def get_player_join_requests(player_id: str):
    """Get all join requests made by a player."""
    try:
        requests = await db.join_requests.find({"player_id": player_id}).sort("created_at", -1).to_list(100)
        return [serialize_doc(r) for r in requests]
    except:
        raise HTTPException(status_code=400, detail="Invalid player ID")

@api_router.post("/join-requests/{request_id}/approve", response_model=dict)
async def approve_join_request(request_id: str, approver_id: str):
    """Approve a join request. Only leader can approve."""
    try:
        join_request = await db.join_requests.find_one({"_id": ObjectId(request_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid request ID")
    
    if not join_request:
        raise HTTPException(status_code=404, detail="Join request not found")
    
    if join_request['status'] != 'pending':
        raise HTTPException(status_code=400, detail="This request has already been processed")
    
    clan = await db.clans.find_one({"_id": ObjectId(join_request['clan_id'])})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    # Only leader can approve
    if clan.get('leader_id') != approver_id:
        raise HTTPException(status_code=403, detail="Only the clan leader can approve join requests")
    
    player_id = join_request['player_id']
    clan_id = join_request['clan_id']
    
    # Check if player is still not in a clan for this game
    existing_clan = await db.clans.find_one({
        "game": clan['game'],
        "members": player_id
    })
    if existing_clan:
        # Mark request as denied since they joined another clan
        await db.join_requests.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "denied"}}
        )
        raise HTTPException(status_code=400, detail="Player has already joined another clan for this game")
    
    # Add player to clan
    await db.clans.update_one(
        {"_id": ObjectId(clan_id)},
        {"$push": {"members": player_id}}
    )
    
    # Update player's clan_id
    await db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"clan_id": clan_id}}
    )
    
    # Mark request as approved
    await db.join_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "approved"}}
    )
    
    # Deny all other pending requests from this player for this game
    await db.join_requests.update_many(
        {
            "player_id": player_id,
            "status": "pending",
            "_id": {"$ne": ObjectId(request_id)}
        },
        {"$set": {"status": "denied"}}
    )
    
    updated_request = await db.join_requests.find_one({"_id": ObjectId(request_id)})
    return serialize_doc(updated_request)

@api_router.post("/join-requests/{request_id}/deny", response_model=dict)
async def deny_join_request(request_id: str, denier_id: str):
    """Deny a join request. Only leader can deny."""
    try:
        join_request = await db.join_requests.find_one({"_id": ObjectId(request_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid request ID")
    
    if not join_request:
        raise HTTPException(status_code=404, detail="Join request not found")
    
    if join_request['status'] != 'pending':
        raise HTTPException(status_code=400, detail="This request has already been processed")
    
    clan = await db.clans.find_one({"_id": ObjectId(join_request['clan_id'])})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    # Only leader can deny
    if clan.get('leader_id') != denier_id:
        raise HTTPException(status_code=403, detail="Only the clan leader can deny join requests")
    
    # Mark request as denied
    await db.join_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "denied"}}
    )
    
    updated_request = await db.join_requests.find_one({"_id": ObjectId(request_id)})
    return serialize_doc(updated_request)

@api_router.delete("/join-requests/{request_id}", response_model=dict)
async def cancel_join_request(request_id: str, player_id: str):
    """Cancel a pending join request. Only the requester can cancel."""
    try:
        join_request = await db.join_requests.find_one({"_id": ObjectId(request_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid request ID")
    
    if not join_request:
        raise HTTPException(status_code=404, detail="Join request not found")
    
    if join_request['player_id'] != player_id:
        raise HTTPException(status_code=403, detail="You can only cancel your own requests")
    
    if join_request['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Can only cancel pending requests")
    
    await db.join_requests.delete_one({"_id": ObjectId(request_id)})
    return {"message": "Join request cancelled"}

# ==================== CLAN INVITE ROUTES ====================

@api_router.post("/clan-invites", response_model=dict)
async def create_clan_invite(invite: ClanInviteCreate, inviter_id: str):
    """Send an invite to a player to join the clan. Only leader/captain can invite."""
    try:
        clan = await db.clans.find_one({"_id": ObjectId(invite.clan_id)})
        player = await db.players.find_one({"_id": ObjectId(invite.player_id)})
        inviter = await db.players.find_one({"_id": ObjectId(inviter_id)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    if not player:
        raise HTTPException(status_code=404, detail="Player to invite not found")
    if not inviter:
        raise HTTPException(status_code=404, detail="Your session has expired. Please log out and log back in.")
    
    # Only leader or captain can invite
    if not await is_captain_or_above(invite.clan_id, inviter_id):
        raise HTTPException(status_code=403, detail="Only leader or captain can send invites")
    
    # Check if player is already a member of THIS clan
    if invite.player_id in clan.get('members', []):
        raise HTTPException(status_code=400, detail="Player is already a member of this clan")
    
    # Check if there's already a pending invite
    existing_invite = await db.clan_invites.find_one({
        "clan_id": invite.clan_id,
        "player_id": invite.player_id,
        "status": "pending"
    })
    if existing_invite:
        raise HTTPException(status_code=400, detail="An invite is already pending for this player")
    
    clan_invite = {
        "clan_id": invite.clan_id,
        "clan_name": clan['name'],
        "clan_tag": clan['tag'],
        "clan_logo": clan.get('logo'),
        "player_id": invite.player_id,
        "invited_by_id": inviter_id,
        "invited_by_username": inviter['username'],
        "message": invite.message or "",
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    
    result = await db.clan_invites.insert_one(clan_invite)
    clan_invite['_id'] = str(result.inserted_id)
    return serialize_doc(clan_invite)

@api_router.get("/clan-invites/player/{player_id}", response_model=List[dict])
async def get_player_invites(player_id: str, status: Optional[str] = None):
    """Get all clan invites for a player."""
    try:
        query = {"player_id": player_id}
        if status:
            query["status"] = status
        invites = await db.clan_invites.find(query).sort("created_at", -1).to_list(100)
        return [serialize_doc(i) for i in invites]
    except:
        raise HTTPException(status_code=400, detail="Invalid player ID")

@api_router.get("/clan-invites/clan/{clan_id}", response_model=List[dict])
async def get_clan_sent_invites(clan_id: str, status: Optional[str] = None):
    """Get all invites sent by a clan."""
    try:
        query = {"clan_id": clan_id}
        if status:
            query["status"] = status
        invites = await db.clan_invites.find(query).sort("created_at", -1).to_list(100)
        return [serialize_doc(i) for i in invites]
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID")

@api_router.post("/clan-invites/{invite_id}/accept", response_model=dict)
async def accept_clan_invite(invite_id: str, player_id: str):
    """Accept a clan invite. Only the invited player can accept."""
    try:
        invite = await db.clan_invites.find_one({"_id": ObjectId(invite_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid invite ID")
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    if invite['player_id'] != player_id:
        raise HTTPException(status_code=403, detail="You can only accept your own invites")
    
    if invite['status'] != 'pending':
        raise HTTPException(status_code=400, detail="This invite has already been processed")
    
    clan = await db.clans.find_one({"_id": ObjectId(invite['clan_id'])})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan no longer exists")
    
    # Check if player is already in a clan for this game
    existing_clan = await db.clans.find_one({
        "game": clan['game'],
        "members": player_id
    })
    if existing_clan:
        await db.clan_invites.update_one(
            {"_id": ObjectId(invite_id)},
            {"$set": {"status": "declined"}}
        )
        raise HTTPException(status_code=400, detail="You have already joined a clan for this game")
    
    # Add player to clan
    await db.clans.update_one(
        {"_id": ObjectId(invite['clan_id'])},
        {"$push": {"members": player_id}}
    )
    
    # Update player's clan_id
    await db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"clan_id": invite['clan_id']}}
    )
    
    # Mark invite as accepted
    await db.clan_invites.update_one(
        {"_id": ObjectId(invite_id)},
        {"$set": {"status": "accepted"}}
    )
    
    # Decline all other pending invites for this player for same game
    other_clan_ids = [c['_id'] async for c in db.clans.find({"game": clan['game']})]
    await db.clan_invites.update_many(
        {
            "player_id": player_id,
            "status": "pending",
            "_id": {"$ne": ObjectId(invite_id)}
        },
        {"$set": {"status": "declined"}}
    )
    
    updated_invite = await db.clan_invites.find_one({"_id": ObjectId(invite_id)})
    return serialize_doc(updated_invite)

@api_router.post("/clan-invites/{invite_id}/decline", response_model=dict)
async def decline_clan_invite(invite_id: str, player_id: str):
    """Decline a clan invite. Only the invited player can decline."""
    try:
        invite = await db.clan_invites.find_one({"_id": ObjectId(invite_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid invite ID")
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    if invite['player_id'] != player_id:
        raise HTTPException(status_code=403, detail="You can only decline your own invites")
    
    if invite['status'] != 'pending':
        raise HTTPException(status_code=400, detail="This invite has already been processed")
    
    await db.clan_invites.update_one(
        {"_id": ObjectId(invite_id)},
        {"$set": {"status": "declined"}}
    )
    
    updated_invite = await db.clan_invites.find_one({"_id": ObjectId(invite_id)})
    return serialize_doc(updated_invite)

@api_router.delete("/clan-invites/{invite_id}", response_model=dict)
async def cancel_clan_invite(invite_id: str, canceller_id: str):
    """Cancel a pending clan invite. Only the inviter (leader/captain) can cancel."""
    try:
        invite = await db.clan_invites.find_one({"_id": ObjectId(invite_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid invite ID")
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    if invite['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Can only cancel pending invites")
    
    # Check if canceller is the inviter OR is leader/captain of the clan
    clan = await db.clans.find_one({"_id": ObjectId(invite['clan_id'])})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    is_inviter = invite.get('invited_by_id') == canceller_id
    is_leader_or_captain = canceller_id in [clan.get('leader_id'), clan.get('captain_id')]
    
    if not is_inviter and not is_leader_or_captain:
        raise HTTPException(status_code=403, detail="Only the inviter or clan leader/captain can cancel invites")
    
    await db.clan_invites.delete_one({"_id": ObjectId(invite_id)})
    return {"message": "Invite cancelled successfully"}

# ==================== CHALLENGE ROUTES ====================

@api_router.post("/challenges", response_model=dict)
async def create_challenge(challenge: ChallengeCreate, creator_id: str):
    """Create a challenge. Only captain or leader can send challenges."""
    try:
        challenger_clan = await db.clans.find_one({"_id": ObjectId(challenge.challenger_clan_id)})
        challenged_clan = await db.clans.find_one({"_id": ObjectId(challenge.challenged_clan_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID format")
    
    if not challenger_clan or not challenged_clan:
        raise HTTPException(status_code=404, detail="One or both clans not found")
    
    if challenge.challenger_clan_id == challenge.challenged_clan_id:
        raise HTTPException(status_code=400, detail="Cannot challenge your own clan")
    
    # Clans must be from the same game
    if challenger_clan['game'] != challenged_clan['game']:
        raise HTTPException(status_code=400, detail="Clans must be from the same game")
    
    # Check if creator is captain or leader of challenger clan
    if not await is_captain_or_above(challenge.challenger_clan_id, creator_id):
        raise HTTPException(status_code=403, detail="Only captain or leader can send challenges")
    
    # Check for existing pending challenge between these clans
    existing = await db.challenges.find_one({
        "challenger_clan_id": challenge.challenger_clan_id,
        "challenged_clan_id": challenge.challenged_clan_id,
        "status": "pending"
    })
    if existing:
        raise HTTPException(status_code=400, detail="A pending challenge already exists between these clans")
    
    challenge_dict = challenge.dict()
    challenge_dict['challenger_clan_name'] = challenger_clan['name']
    challenge_dict['challenged_clan_name'] = challenged_clan['name']
    challenge_dict['game'] = challenger_clan['game']
    challenge_dict['status'] = 'pending'
    challenge_dict['match_id'] = None
    challenge_dict['created_by'] = creator_id
    challenge_dict['created_at'] = datetime.utcnow()
    
    result = await db.challenges.insert_one(challenge_dict)
    challenge_dict['_id'] = str(result.inserted_id)
    return serialize_doc(challenge_dict)

@api_router.get("/challenges", response_model=List[dict])
async def get_challenges(status: Optional[str] = None, game: Optional[str] = None):
    """Get all challenges, optionally filtered"""
    query = {}
    if status:
        query['status'] = status
    if game:
        query['game'] = game
    challenges = await db.challenges.find(query).sort("created_at", -1).to_list(100)
    return [serialize_doc(c) for c in challenges]

@api_router.get("/challenges/{challenge_id}", response_model=dict)
async def get_challenge(challenge_id: str):
    try:
        challenge = await db.challenges.find_one({"_id": ObjectId(challenge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid challenge ID")
    
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return serialize_doc(challenge)

@api_router.get("/challenges/clan/{clan_id}", response_model=dict)
async def get_clan_challenges(clan_id: str):
    """Get all challenges for a clan (sent and received)"""
    sent = await db.challenges.find({"challenger_clan_id": clan_id}).sort("created_at", -1).to_list(50)
    received = await db.challenges.find({"challenged_clan_id": clan_id}).sort("created_at", -1).to_list(50)
    
    return {
        "sent": [serialize_doc(c) for c in sent],
        "received": [serialize_doc(c) for c in received]
    }

@api_router.post("/challenges/{challenge_id}/accept", response_model=dict)
async def accept_challenge(challenge_id: str, accepter_id: str):
    """Accept a challenge. Only captain or leader of challenged clan can accept."""
    try:
        challenge = await db.challenges.find_one({"_id": ObjectId(challenge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid challenge ID")
    
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    if challenge['status'] != 'pending':
        raise HTTPException(status_code=400, detail=f"Challenge is already {challenge['status']}")
    
    # Check if accepter is captain or leader of challenged clan
    if not await is_captain_or_above(challenge['challenged_clan_id'], accepter_id):
        raise HTTPException(status_code=403, detail="Only captain or leader can accept challenges")
    
    # Create a match from the challenge
    challenger_clan = await db.clans.find_one({"_id": ObjectId(challenge['challenger_clan_id'])})
    challenged_clan = await db.clans.find_one({"_id": ObjectId(challenge['challenged_clan_id'])})
    
    match_dict = {
        'clan_a_id': challenge['challenger_clan_id'],
        'clan_b_id': challenge['challenged_clan_id'],
        'clan_a_name': challenger_clan['name'],
        'clan_b_name': challenged_clan['name'],
        'game': challenge['game'],
        'scheduled_time': challenge['proposed_time'],
        'description': challenge.get('message', ''),
        'status': 'scheduled',
        'score_clan_a': 0,
        'score_clan_b': 0,
        'winner_id': None,
        'challenge_id': challenge_id,
        'score_reported_by': None,
        'created_at': datetime.utcnow()
    }
    
    match_result = await db.matches.insert_one(match_dict)
    match_id = str(match_result.inserted_id)
    
    # Update challenge status
    await db.challenges.update_one(
        {"_id": ObjectId(challenge_id)},
        {"$set": {"status": "accepted", "match_id": match_id}}
    )
    
    # Add system event messages to the new match lobby chat
    from routes.match_lobby import add_system_message
    await add_system_message(match_id, f"Match created: {challenger_clan['name']} vs {challenged_clan['name']}")
    await add_system_message(match_id, f"Challenge accepted by {challenged_clan['name']}")
    
    challenge = await db.challenges.find_one({"_id": ObjectId(challenge_id)})
    return serialize_doc(challenge)

@api_router.post("/challenges/{challenge_id}/decline", response_model=dict)
async def decline_challenge(challenge_id: str, decliner_id: str):
    """Decline a challenge. Only captain or leader of challenged clan can decline."""
    try:
        challenge = await db.challenges.find_one({"_id": ObjectId(challenge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid challenge ID")
    
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    if challenge['status'] != 'pending':
        raise HTTPException(status_code=400, detail=f"Challenge is already {challenge['status']}")
    
    # Check if decliner is captain or leader of challenged clan
    if not await is_captain_or_above(challenge['challenged_clan_id'], decliner_id):
        raise HTTPException(status_code=403, detail="Only captain or leader can decline challenges")
    
    await db.challenges.update_one(
        {"_id": ObjectId(challenge_id)},
        {"$set": {"status": "declined"}}
    )
    
    challenge = await db.challenges.find_one({"_id": ObjectId(challenge_id)})
    return serialize_doc(challenge)

# ==================== FLASH MATCH ROUTES ====================

@api_router.post("/quick-matches", response_model=dict)
async def create_quick_match(match: FlashMatchCreate):
    """Create a quick match for pickup games"""
    if match.game not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Game must be one of: {SUPPORTED_GAMES}")
    
    if len(match.team_a_players) > 8 or len(match.team_b_players) > 8:
        raise HTTPException(status_code=400, detail="Maximum 8 players per team")
    
    if len(match.team_a_players) == 0 or len(match.team_b_players) == 0:
        raise HTTPException(status_code=400, detail="Each team must have at least 1 player")
    
    # Build player arrays with optional player_id for stat tracking
    team_a_player_list = []
    for i, name in enumerate(match.team_a_players):
        player_entry = {"name": name, "kills": 0}
        if match.team_a_player_ids and i < len(match.team_a_player_ids) and match.team_a_player_ids[i]:
            player_entry["player_id"] = match.team_a_player_ids[i]
        team_a_player_list.append(player_entry)
    
    team_b_player_list = []
    for i, name in enumerate(match.team_b_players):
        player_entry = {"name": name, "kills": 0}
        if match.team_b_player_ids and i < len(match.team_b_player_ids) and match.team_b_player_ids[i]:
            player_entry["player_id"] = match.team_b_player_ids[i]
        team_b_player_list.append(player_entry)
    
    quick_match = {
        "game": match.game,
        "team_a": {
            "name": match.team_a_name,
            "players": team_a_player_list,
            "maps_won": 0
        },
        "team_b": {
            "name": match.team_b_name,
            "players": team_b_player_list,
            "maps_won": 0
        },
        "status": "in_progress",
        "winner": None,
        "created_at": datetime.utcnow()
    }
    
    result = await db.quick_matches.insert_one(quick_match)
    quick_match['_id'] = str(result.inserted_id)
    return serialize_doc(quick_match)

@api_router.get("/quick-matches", response_model=List[dict])
async def get_quick_matches(game: Optional[str] = None, status: Optional[str] = None):
    """Get all quick matches"""
    query = {}
    if game:
        query['game'] = game
    if status:
        query['status'] = status
    matches = await db.quick_matches.find(query).sort("created_at", -1).to_list(100)
    return [serialize_doc(m) for m in matches]

@api_router.get("/quick-matches/{match_id}", response_model=dict)
async def get_quick_match(match_id: str):
    """Get a specific quick match"""
    try:
        match = await db.quick_matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    if not match:
        raise HTTPException(status_code=404, detail="Quick match not found")
    return serialize_doc(match)

@api_router.post("/quick-matches/{match_id}/report", response_model=dict)
async def report_quick_match(match_id: str, report: FlashMatchScoreReport):
    """Report final score and kills for a quick match (participants only)"""
    try:
        match = await db.quick_matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    
    if not match:
        raise HTTPException(status_code=404, detail="Quick match not found")
    
    if match.get('status') == 'completed':
        raise HTTPException(status_code=400, detail="Match already completed")
    
    # Check if reporter is a participant in the match
    reporter_id = report.reporter_id if hasattr(report, 'reporter_id') else None
    reporter_name = report.reporter_name if hasattr(report, 'reporter_name') else None
    
    if not reporter_id and not reporter_name:
        raise HTTPException(status_code=400, detail="Reporter identification is required")
    
    # Get all participant names from both teams
    team_a_names = [p['name'].lower() for p in match['team_a']['players']]
    team_b_names = [p['name'].lower() for p in match['team_b']['players']]
    all_participants = team_a_names + team_b_names
    
    # Check if reporter is a participant (by name or by looking up their username)
    is_participant = False
    if reporter_name and reporter_name.lower() in all_participants:
        is_participant = True
    elif reporter_id:
        # Look up the reporter's username
        reporter = await db.players.find_one({"_id": ObjectId(reporter_id)})
        if reporter and reporter.get('username', '').lower() in all_participants:
            is_participant = True
    
    if not is_participant:
        raise HTTPException(status_code=403, detail="Only match participants can report scores")
    
    game = match.get('game', 'Rainbow Six 3')
    
    # Determine winner
    winner = None
    if report.maps_won_a > report.maps_won_b:
        winner = match['team_a']['name']
    elif report.maps_won_b > report.maps_won_a:
        winner = match['team_b']['name']
    
    # Update team A players with kills
    team_a_players = []
    for player in match['team_a']['players']:
        kill_data = next((k for k in report.team_a_kills if k['name'] == player['name']), None)
        kills = kill_data['kills'] if kill_data else 0
        team_a_players.append({
            "name": player['name'],
            "kills": kills
        })
        # Update player stats if they exist in database (by username)
        if kills > 0:
            game_key = f"game_stats.{game}"
            await db.players.update_one(
                {"username": player['name']},
                {"$inc": {f"{game_key}.quick_kills": kills}}
            )
    
    # Update team B players with kills
    team_b_players = []
    for player in match['team_b']['players']:
        kill_data = next((k for k in report.team_b_kills if k['name'] == player['name']), None)
        kills = kill_data['kills'] if kill_data else 0
        team_b_players.append({
            "name": player['name'],
            "kills": kills
        })
        # Update player stats if they exist in database (by username)
        if kills > 0:
            game_key = f"game_stats.{game}"
            await db.players.update_one(
                {"username": player['name']},
                {"$inc": {f"{game_key}.quick_kills": kills}}
            )
    
    await db.quick_matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {
            "team_a.players": team_a_players,
            "team_a.maps_won": report.maps_won_a,
            "team_b.players": team_b_players,
            "team_b.maps_won": report.maps_won_b,
            "status": "completed",
            "winner": winner
        }}
    )
    
    match = await db.quick_matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(match)

# ==================== CASH TOURNAMENT ROUTES ====================

import math

def generate_bracket(num_teams):
    """Generate empty bracket structure for tournament"""
    if num_teams < 2:
        return []
    
    # Calculate number of rounds
    num_rounds = int(math.ceil(math.log2(num_teams)))
    bracket = []
    
    # First round has all the initial matches
    matches_in_round = num_teams // 2
    for round_num in range(num_rounds):
        round_matches = []
        for match_num in range(matches_in_round):
            round_matches.append({
                "round": round_num + 1,
                "match_number": match_num + 1,
                "clan_a_id": None,
                "clan_b_id": None,
                "team_a_name": None,
                "team_b_name": None,
                "winner_id": None,
                "score_a": None,
                "score_b": None,
                "player_kills": [],
                "status": "pending"
            })
        bracket.append(round_matches)
        matches_in_round = max(1, matches_in_round // 2)
    
    return bracket

@api_router.post("/tournaments", response_model=dict)
async def create_tournament(tournament: CashTournamentCreate, creator_id: str):
    """Create a new cash tournament"""
    if tournament.game not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Game must be one of: {SUPPORTED_GAMES}")
    
    if tournament.buy_in_amount < 0:
        raise HTTPException(status_code=400, detail="Buy-in amount cannot be negative")
    
    if tournament.max_teams not in [2, 4, 8, 16]:
        raise HTTPException(status_code=400, detail="Max teams must be 2, 4, 8, or 16")
    
    try:
        creator = await db.players.find_one({"_id": ObjectId(creator_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid creator ID")
    
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    
    tourney = {
        "name": tournament.name,
        "game": tournament.game,
        "buy_in_amount": tournament.buy_in_amount,
        "buy_in_per_player": tournament.buy_in_per_player,
        "payout_amount": tournament.payout_amount,
        "max_teams": tournament.max_teams,
        "description": tournament.description or "",
        "twitch_link_1": tournament.twitch_link_1 or "",
        "twitch_link_2": tournament.twitch_link_2 or "",
        "creator_id": creator_id,
        "creator_username": creator['username'],
        "teams": [],  # List of tournament team IDs
        "bracket": [],
        "status": "registration",  # registration, in_progress, completed
        "winner_team_id": None,
        "winner_team_name": None,
        "created_at": datetime.utcnow()
    }
    
    result = await db.tournaments.insert_one(tourney)
    tourney['_id'] = str(result.inserted_id)
    return serialize_doc(tourney)

@api_router.get("/tournaments", response_model=List[dict])
async def get_tournaments(game: Optional[str] = None, status: Optional[str] = None):
    """Get all tournaments with team counts"""
    query = {}
    if game:
        query['game'] = game
    if status:
        query['status'] = status
    tournaments = await db.tournaments.find(query).sort("created_at", -1).to_list(100)
    result = []
    for t in tournaments:
        tourney = serialize_doc(t)
        # Get team count for this tournament
        team_count = await db.tournament_teams.count_documents({"tournament_id": str(t['_id'])})
        tourney['registered_teams'] = team_count
        result.append(tourney)
    return result

@api_router.get("/tournaments/{tournament_id}", response_model=dict)
async def get_tournament(tournament_id: str):
    """Get a specific tournament"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return serialize_doc(tournament)

@api_router.put("/tournaments/{tournament_id}", response_model=dict)
async def update_tournament(tournament_id: str, update: CashTournamentUpdate, requester_id: str):
    """Update tournament details (creator or team captains can update twitch links)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Check permissions - creator can update everything, team captains can only update twitch links
    is_creator = tournament['creator_id'] == requester_id
    
    # Check if requester is a team captain in this tournament
    is_team_captain = False
    teams = await db.tournament_teams.find({"tournament_id": tournament_id}).to_list(100)
    for team in teams:
        if team.get('captain_id') == requester_id:
            is_team_captain = True
            break
    
    if not is_creator and not is_team_captain:
        raise HTTPException(status_code=403, detail="Only tournament creator or team captains can update")
    
    update_dict = {}
    
    # Creator can update name and description
    if is_creator:
        if update.name is not None:
            update_dict['name'] = update.name
        if update.description is not None:
            update_dict['description'] = update.description
    
    # Both creator and captains can update twitch links
    if update.twitch_link_1 is not None:
        update_dict['twitch_link_1'] = update.twitch_link_1
    if update.twitch_link_2 is not None:
        update_dict['twitch_link_2'] = update.twitch_link_2
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": update_dict}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/register", response_model=dict)
async def register_for_tournament(tournament_id: str, clan_id: str):
    """Register a clan for a tournament"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")
    
    if tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Tournament is not accepting registrations")
    
    if tournament['game'] != clan['game']:
        raise HTTPException(status_code=400, detail="Clan must be from the same game as the tournament")
    
    if len(tournament['participants']) >= tournament['max_teams']:
        raise HTTPException(status_code=400, detail="Tournament is full")
    
    # Check if clan is already registered
    if any(p['clan_id'] == clan_id for p in tournament['participants']):
        raise HTTPException(status_code=400, detail="Clan is already registered")
    
    participant = {
        "clan_id": clan_id,
        "clan_name": clan['name'],
        "clan_tag": clan['tag'],
        "has_paid": False,
        "seed": len(tournament['participants']) + 1
    }
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$push": {"participants": participant}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/toggle-payment", response_model=dict)
async def toggle_payment_status(tournament_id: str, clan_id: str, requester_id: str):
    """Toggle payment status for a participant (host only)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['creator_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only the tournament creator can update payment status")
    
    # Find and toggle the participant's payment status
    participants = tournament['participants']
    updated = False
    for p in participants:
        if p['clan_id'] == clan_id:
            p['has_paid'] = not p['has_paid']
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Clan not found in participants")
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"participants": participants}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/start", response_model=dict)
async def start_tournament(tournament_id: str, requester_id: str):
    """Start the tournament and generate bracket (host only)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['creator_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only the tournament creator can start the tournament")
    
    if tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Tournament has already started or is completed")
    
    participants = tournament['participants']
    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to start")
    
    # Check if all participants have paid
    unpaid = [p for p in participants if not p['has_paid']]
    if unpaid:
        unpaid_names = ", ".join([p['clan_name'] for p in unpaid])
        raise HTTPException(status_code=400, detail=f"The following teams have not paid: {unpaid_names}")
    
    # Generate bracket
    bracket = generate_bracket(len(participants))
    
    # Seed first round matches
    if bracket:
        first_round = bracket[0]
        for i, match in enumerate(first_round):
            idx_a = i * 2
            idx_b = i * 2 + 1
            if idx_a < len(participants):
                match['clan_a_id'] = participants[idx_a]['clan_id']
                match['clan_a_name'] = participants[idx_a]['clan_name']
            if idx_b < len(participants):
                match['clan_b_id'] = participants[idx_b]['clan_id']
                match['clan_b_name'] = participants[idx_b]['clan_name']
            match['status'] = 'pending'
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {
            "bracket": bracket,
            "status": "in_progress"
        }}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/report-match", response_model=dict)
async def report_tournament_match(
    tournament_id: str, 
    round_num: int, 
    match_num: int, 
    score_a: int, 
    score_b: int,
    requester_id: str
):
    """Report match result in tournament (host only)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['creator_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only the tournament creator can report matches")
    
    if tournament['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail="Tournament is not in progress")
    
    bracket = tournament['bracket']
    
    # Find the match
    if round_num < 1 or round_num > len(bracket):
        raise HTTPException(status_code=400, detail="Invalid round number")
    
    round_matches = bracket[round_num - 1]
    if match_num < 1 or match_num > len(round_matches):
        raise HTTPException(status_code=400, detail="Invalid match number")
    
    match = round_matches[match_num - 1]
    
    if not match['clan_a_id'] or not match['clan_b_id']:
        raise HTTPException(status_code=400, detail="Match does not have both teams yet")
    
    # Determine winner
    if score_a > score_b:
        winner_id = match['clan_a_id']
        winner_name = match['clan_a_name']
    elif score_b > score_a:
        winner_id = match['clan_b_id']
        winner_name = match['clan_b_name']
    else:
        raise HTTPException(status_code=400, detail="Matches cannot end in a tie")
    
    # Update match result
    match['score_a'] = score_a
    match['score_b'] = score_b
    match['winner_id'] = winner_id
    match['status'] = 'completed'
    
    # Advance winner to next round if not final
    if round_num < len(bracket):
        next_round = bracket[round_num]
        next_match_idx = (match_num - 1) // 2
        if next_match_idx < len(next_round):
            next_match = next_round[next_match_idx]
            if (match_num - 1) % 2 == 0:
                next_match['clan_a_id'] = winner_id
                next_match['clan_a_name'] = winner_name
            else:
                next_match['clan_b_id'] = winner_id
                next_match['clan_b_name'] = winner_name
    else:
        # This was the final - tournament is complete
        await db.tournaments.update_one(
            {"_id": ObjectId(tournament_id)},
            {"$set": {
                "winner_id": winner_id,
                "winner_name": winner_name,
                "status": "completed"
            }}
        )
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"bracket": bracket}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.delete("/tournaments/{tournament_id}/unregister", response_model=dict)
async def unregister_from_tournament(tournament_id: str, clan_id: str):
    """Unregister a clan from tournament"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Cannot unregister after tournament has started")
    
    participants = [p for p in tournament['participants'] if p['clan_id'] != clan_id]
    
    if len(participants) == len(tournament['participants']):
        raise HTTPException(status_code=404, detail="Clan not found in participants")
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"participants": participants}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

# ==================== TOURNAMENT TEAM ROUTES ====================

@api_router.post("/tournaments/{tournament_id}/teams", response_model=dict)
async def create_tournament_team(tournament_id: str, team_name: str, captain_id: str):
    """Create a tournament team (captain creates team)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
        captain = await db.players.find_one({"_id": ObjectId(captain_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not captain:
        raise HTTPException(status_code=404, detail="Captain not found")
    
    if tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Tournament is not open for registration")
    
    # Check if max teams reached
    team_count = await db.tournament_teams.count_documents({"tournament_id": tournament_id})
    if team_count >= tournament['max_teams']:
        raise HTTPException(status_code=400, detail="Tournament is full")
    
    # Check if captain already has a team in this tournament
    existing_team = await db.tournament_teams.find_one({
        "tournament_id": tournament_id,
        "captain_id": captain_id
    })
    if existing_team:
        raise HTTPException(status_code=400, detail="You already have a team in this tournament")
    
    team = {
        "tournament_id": tournament_id,
        "team_name": team_name,
        "captain_id": captain_id,
        "captain_name": captain['username'],
        "players": [{
            "player_name": captain['username'],
            "player_id": captain_id,
            "has_paid": False,
            "kills": 0
        }],  # Captain auto-added
        "team_paid": False,
        "seed": None,
        "eliminated": False,
        "created_at": datetime.utcnow()
    }
    
    result = await db.tournament_teams.insert_one(team)
    team['_id'] = str(result.inserted_id)
    return serialize_doc(team)

@api_router.get("/tournaments/{tournament_id}/teams", response_model=List[dict])
async def get_tournament_teams(tournament_id: str):
    """Get all teams in a tournament"""
    teams = await db.tournament_teams.find({"tournament_id": tournament_id}).to_list(100)
    return [serialize_doc(t) for t in teams]

@api_router.get("/tournaments/teams/{team_id}", response_model=dict)
async def get_tournament_team(team_id: str):
    """Get a specific tournament team with roster"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    return serialize_doc(team)

@api_router.post("/tournaments/teams/{team_id}/add-player", response_model=dict)
async def add_player_to_team(team_id: str, player_name: str, player_id: Optional[str] = None, requester_id: str = None):
    """Add a player to tournament team roster (captain only, max 8 players)"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if requester_id and team['captain_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only team captain can add players")
    
    if len(team.get('players', [])) >= 8:
        raise HTTPException(status_code=400, detail="Team roster is full (max 8 players)")
    
    # Check if player already on roster
    for p in team.get('players', []):
        if p['player_name'].lower() == player_name.lower():
            raise HTTPException(status_code=400, detail="Player already on roster")
    
    new_player = {
        "player_name": player_name,
        "player_id": player_id,
        "has_paid": False,
        "kills": 0
    }
    
    await db.tournament_teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"players": new_player}}
    )
    
    # Send invite notification if player_id is provided
    if player_id:
        tournament = await db.tournaments.find_one({"_id": ObjectId(team['tournament_id'])})
        invite = {
            "type": "tournament_invite",
            "tournament_id": team['tournament_id'],
            "tournament_name": tournament['name'] if tournament else "Unknown Tournament",
            "team_id": team_id,
            "team_name": team['team_name'],
            "player_id": player_id,
            "player_name": player_name,
            "captain_name": team['captain_name'],
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        await db.tournament_invites.insert_one(invite)
    
    team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    return serialize_doc(team)

@api_router.delete("/tournaments/teams/{team_id}/remove-player", response_model=dict)
async def remove_player_from_team(team_id: str, player_name: str, requester_id: str):
    """Remove a player from tournament team roster (captain only)"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if team['captain_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only team captain can remove players")
    
    # Can't remove captain
    if player_name.lower() == team['captain_name'].lower():
        raise HTTPException(status_code=400, detail="Cannot remove the team captain")
    
    players = [p for p in team.get('players', []) if p['player_name'].lower() != player_name.lower()]
    
    if len(players) == len(team.get('players', [])):
        raise HTTPException(status_code=404, detail="Player not found on roster")
    
    await db.tournament_teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"players": players}}
    )
    
    team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    return serialize_doc(team)

@api_router.post("/tournaments/teams/{team_id}/toggle-player-paid", response_model=dict)
async def toggle_player_paid(team_id: str, player_name: str, requester_id: str):
    """Toggle player's paid status (green/red indicator) - captain only"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if team['captain_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only team captain can update payment status")
    
    players = team.get('players', [])
    updated = False
    for p in players:
        if p['player_name'].lower() == player_name.lower():
            p['has_paid'] = not p['has_paid']
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Player not found on roster")
    
    await db.tournament_teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"players": players}}
    )
    
    team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    return serialize_doc(team)

@api_router.post("/tournaments/teams/{team_id}/toggle-team-paid", response_model=dict)
async def toggle_team_paid(team_id: str, requester_id: str):
    """Toggle if captain paid for entire team - marks all players as paid"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(team['tournament_id'])})
    if tournament and tournament['creator_id'] != requester_id and team['captain_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only team captain or tournament creator can update team payment")
    
    new_team_paid = not team.get('team_paid', False)
    
    # If captain pays for team, mark all players as paid
    players = team.get('players', [])
    for p in players:
        p['has_paid'] = new_team_paid
    
    await db.tournament_teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"team_paid": new_team_paid, "players": players}}
    )
    
    team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    return serialize_doc(team)

@api_router.get("/tournaments/invites/{player_id}", response_model=List[dict])
async def get_tournament_invites(player_id: str, status: Optional[str] = "pending"):
    """Get tournament invites for a player"""
    query = {"player_id": player_id}
    if status:
        query["status"] = status
    invites = await db.tournament_invites.find(query).sort("created_at", -1).to_list(50)
    return [serialize_doc(i) for i in invites]

@api_router.post("/tournaments/invites/{invite_id}/respond", response_model=dict)
async def respond_to_tournament_invite(invite_id: str, accept: bool):
    """Accept or decline a tournament team invite"""
    try:
        invite = await db.tournament_invites.find_one({"_id": ObjectId(invite_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid invite ID")
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    if invite['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Invite has already been responded to")
    
    new_status = "accepted" if accept else "declined"
    
    await db.tournament_invites.update_one(
        {"_id": ObjectId(invite_id)},
        {"$set": {"status": new_status}}
    )
    
    invite['status'] = new_status
    return serialize_doc(invite)

@api_router.post("/tournaments/{tournament_id}/start-with-teams", response_model=dict)
async def start_tournament_with_teams(tournament_id: str, requester_id: str):
    """Start tournament and generate bracket from registered teams"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['creator_id'] != requester_id:
        raise HTTPException(status_code=403, detail="Only tournament creator can start the tournament")
    
    if tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Tournament has already started")
    
    # Get all teams
    teams = await db.tournament_teams.find({"tournament_id": tournament_id}).to_list(100)
    
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to start")
    
    # Check if all teams have paid (if buy_in_per_player is False, check team_paid)
    if not tournament.get('buy_in_per_player', True):
        unpaid_teams = [t for t in teams if not t.get('team_paid', False)]
        if unpaid_teams:
            names = ", ".join([t['team_name'] for t in unpaid_teams])
            raise HTTPException(status_code=400, detail=f"Teams with unpaid captain fee: {names}")
    else:
        # Check individual player payments (check both 'paid' and 'has_paid' for compatibility)
        for team in teams:
            unpaid_players = [p for p in team.get('players', []) if not p.get('has_paid', False) and not p.get('paid', False)]
            if unpaid_players:
                names = ", ".join([p['player_name'] for p in unpaid_players])
                raise HTTPException(status_code=400, detail=f"Team {team['team_name']} has unpaid players: {names}")
    
    # Generate bracket
    bracket = generate_bracket(len(teams))
    
    # Seed first round
    if bracket:
        first_round = bracket[0]
        for i, match in enumerate(first_round):
            idx_a = i * 2
            idx_b = i * 2 + 1
            if idx_a < len(teams):
                match['team_a_id'] = str(teams[idx_a]['_id'])
                match['team_a_name'] = teams[idx_a]['team_name']
            if idx_b < len(teams):
                match['team_b_id'] = str(teams[idx_b]['_id'])
                match['team_b_name'] = teams[idx_b]['team_name']
            match['status'] = 'pending'
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"bracket": bracket, "status": "in_progress"}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/report-team-match", response_model=dict)
async def report_team_match(
    tournament_id: str,
    round_num: int,
    match_num: int,
    team_a_maps_won: int,
    team_b_maps_won: int,
    requester_id: str,
    team_a_player_kills: List[dict] = [],
    team_b_player_kills: List[dict] = []
):
    """Report tournament match result with kill counts (best of 5) - captain or creator can report"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail="Tournament is not in progress")
    
    # Validate best of 5 scoring
    if team_a_maps_won < 0 or team_a_maps_won > 3 or team_b_maps_won < 0 or team_b_maps_won > 3:
        raise HTTPException(status_code=400, detail="Maps won must be between 0 and 3 (best of 5)")
    
    if team_a_maps_won < 3 and team_b_maps_won < 3:
        raise HTTPException(status_code=400, detail="One team must win 3 maps (best of 5)")
    
    if team_a_maps_won == 3 and team_b_maps_won == 3:
        raise HTTPException(status_code=400, detail="Both teams cannot win 3 maps")
    
    bracket = tournament['bracket']
    
    if round_num < 1 or round_num > len(bracket):
        raise HTTPException(status_code=400, detail="Invalid round number")
    
    round_matches = bracket[round_num - 1]
    if match_num < 1 or match_num > len(round_matches):
        raise HTTPException(status_code=400, detail="Invalid match number")
    
    match = round_matches[match_num - 1]
    
    # Check if requester can report (tournament creator or team captain)
    team_a = await db.tournament_teams.find_one({"_id": ObjectId(match.get('team_a_id'))}) if match.get('team_a_id') else None
    team_b = await db.tournament_teams.find_one({"_id": ObjectId(match.get('team_b_id'))}) if match.get('team_b_id') else None
    
    is_creator = tournament['creator_id'] == requester_id
    is_team_a_captain = team_a and team_a['captain_id'] == requester_id
    is_team_b_captain = team_b and team_b['captain_id'] == requester_id
    
    if not is_creator and not is_team_a_captain and not is_team_b_captain:
        raise HTTPException(status_code=403, detail="Only tournament creator or team captains can report scores")
    
    # Determine winner
    if team_a_maps_won > team_b_maps_won:
        winner_id = match.get('team_a_id')
        winner_name = match.get('team_a_name')
        loser_id = match.get('team_b_id')
    else:
        winner_id = match.get('team_b_id')
        winner_name = match.get('team_b_name')
        loser_id = match.get('team_a_id')
    
    # Update match
    match['score_a'] = team_a_maps_won
    match['score_b'] = team_b_maps_won
    match['winner_id'] = winner_id
    match['player_kills'] = team_a_player_kills + team_b_player_kills
    match['status'] = 'completed'
    
    # Mark losing team as eliminated
    if loser_id:
        await db.tournament_teams.update_one(
            {"_id": ObjectId(loser_id)},
            {"$set": {"eliminated": True}}
        )
    
    # Update player kill stats on team documents
    if team_a and team_a_player_kills:
        players = team_a.get('players', [])
        for kill_stat in team_a_player_kills:
            for p in players:
                if p['player_name'].lower() == kill_stat.get('player_name', '').lower():
                    p['kills'] = p.get('kills', 0) + kill_stat.get('kills', 0)
        await db.tournament_teams.update_one({"_id": team_a['_id']}, {"$set": {"players": players}})
    
    if team_b and team_b_player_kills:
        players = team_b.get('players', [])
        for kill_stat in team_b_player_kills:
            for p in players:
                if p['player_name'].lower() == kill_stat.get('player_name', '').lower():
                    p['kills'] = p.get('kills', 0) + kill_stat.get('kills', 0)
        await db.tournament_teams.update_one({"_id": team_b['_id']}, {"$set": {"players": players}})
    
    # Post tournament match result to activity feed
    feed_entry = {
        "type": "tournament_match",
        "tournament_id": tournament_id,
        "tournament_name": tournament.get('name', 'Tournament'),
        "match_id": f"{tournament_id}_r{round_num}_m{match_num}",
        "team_a": {
            "id": match.get('team_a_id'),
            "name": match.get('team_a_name'),
            "score": team_a_maps_won,
            "players": team_a_player_kills
        },
        "team_b": {
            "id": match.get('team_b_id'),
            "name": match.get('team_b_name'),
            "score": team_b_maps_won,
            "players": team_b_player_kills
        },
        "winner_id": winner_id,
        "winner_name": winner_name,
        "round": round_num,
        "round_name": "Finals" if round_num == len(bracket) else f"Round {round_num}",
        "game": tournament.get('game'),
        "created_at": datetime.utcnow()
    }
    await db.activity_feed.insert_one(feed_entry)
    
    # Auto-advance winner to next round
    if round_num < len(bracket):
        next_round = bracket[round_num]
        next_match_idx = (match_num - 1) // 2
        if next_match_idx < len(next_round):
            next_match = next_round[next_match_idx]
            if (match_num - 1) % 2 == 0:
                next_match['team_a_id'] = winner_id
                next_match['team_a_name'] = winner_name
            else:
                next_match['team_b_id'] = winner_id
                next_match['team_b_name'] = winner_name
    else:
        # Final match - tournament complete
        await db.tournaments.update_one(
            {"_id": ObjectId(tournament_id)},
            {"$set": {
                "winner_team_id": winner_id,
                "winner_team_name": winner_name,
                "status": "completed"
            }}
        )
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"bracket": bracket}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.post("/tournaments/{tournament_id}/report-match-detailed", response_model=dict)
async def report_tournament_match_detailed(
    tournament_id: str,
    round_num: int,
    match_num: int,
    report: TournamentMatchScoreReport,
    requester_id: str
):
    """Report match result with detailed kill stats (POST body version)"""
    try:
        tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid tournament ID")
    
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament['status'] != 'in_progress':
        raise HTTPException(status_code=400, detail="Tournament is not in progress")
    
    team_a_maps_won = report.team_a_maps_won
    team_b_maps_won = report.team_b_maps_won
    team_a_player_kills = report.team_a_player_kills
    team_b_player_kills = report.team_b_player_kills
    
    if team_a_maps_won < 0 or team_a_maps_won > 3 or team_b_maps_won < 0 or team_b_maps_won > 3:
        raise HTTPException(status_code=400, detail="Maps won must be between 0 and 3 (best of 5)")
    
    if team_a_maps_won < 3 and team_b_maps_won < 3:
        raise HTTPException(status_code=400, detail="One team must win 3 maps (best of 5)")
    
    if team_a_maps_won == 3 and team_b_maps_won == 3:
        raise HTTPException(status_code=400, detail="Both teams cannot win 3 maps")
    
    bracket = tournament['bracket']
    
    if round_num < 1 or round_num > len(bracket):
        raise HTTPException(status_code=400, detail="Invalid round number")
    
    round_matches = bracket[round_num - 1]
    
    # Handle both old format (list of matches) and new format (dict with matches key)
    if isinstance(round_matches, dict):
        matches_list = round_matches.get('matches', [])
    else:
        matches_list = round_matches
    
    if match_num < 1 or match_num > len(matches_list):
        raise HTTPException(status_code=400, detail="Invalid match number")
    
    match = matches_list[match_num - 1]
    
    # Check if requester can report (tournament creator or team captain)
    team_a = await db.tournament_teams.find_one({"_id": ObjectId(match.get('team_a_id'))}) if match.get('team_a_id') else None
    team_b = await db.tournament_teams.find_one({"_id": ObjectId(match.get('team_b_id'))}) if match.get('team_b_id') else None
    
    is_creator = tournament['creator_id'] == requester_id
    is_team_a_captain = team_a and team_a['captain_id'] == requester_id
    is_team_b_captain = team_b and team_b['captain_id'] == requester_id
    
    if not is_creator and not is_team_a_captain and not is_team_b_captain:
        raise HTTPException(status_code=403, detail="Only tournament creator or team captains can report scores")
    
    # Determine winner
    if team_a_maps_won > team_b_maps_won:
        winner_id = match.get('team_a_id')
        winner_name = match.get('team_a_name')
        loser_id = match.get('team_b_id')
    else:
        winner_id = match.get('team_b_id')
        winner_name = match.get('team_b_name')
        loser_id = match.get('team_a_id')
    
    # Update match
    match['score_a'] = team_a_maps_won
    match['score_b'] = team_b_maps_won
    match['winner_id'] = winner_id
    match['player_kills'] = team_a_player_kills + team_b_player_kills
    match['status'] = 'completed'
    
    # Mark losing team as eliminated
    if loser_id:
        await db.tournament_teams.update_one(
            {"_id": ObjectId(loser_id)},
            {"$set": {"eliminated": True}}
        )
    
    # Update player kill stats on team documents
    if team_a and team_a_player_kills:
        players = team_a.get('players', [])
        for kill_stat in team_a_player_kills:
            for p in players:
                if p['player_name'].lower() == kill_stat.get('player_name', '').lower():
                    p['kills'] = p.get('kills', 0) + kill_stat.get('kills', 0)
        await db.tournament_teams.update_one({"_id": team_a['_id']}, {"$set": {"players": players}})
    
    if team_b and team_b_player_kills:
        players = team_b.get('players', [])
        for kill_stat in team_b_player_kills:
            for p in players:
                if p['player_name'].lower() == kill_stat.get('player_name', '').lower():
                    p['kills'] = p.get('kills', 0) + kill_stat.get('kills', 0)
        await db.tournament_teams.update_one({"_id": team_b['_id']}, {"$set": {"players": players}})
    
    # Post tournament match result to activity feed
    feed_entry = {
        "type": "tournament_match",
        "tournament_id": tournament_id,
        "tournament_name": tournament.get('name', 'Tournament'),
        "match_id": f"{tournament_id}_r{round_num}_m{match_num}",
        "team_a": {
            "id": match.get('team_a_id'),
            "name": match.get('team_a_name'),
            "score": team_a_maps_won,
            "players": team_a_player_kills
        },
        "team_b": {
            "id": match.get('team_b_id'),
            "name": match.get('team_b_name'),
            "score": team_b_maps_won,
            "players": team_b_player_kills
        },
        "winner_id": winner_id,
        "winner_name": winner_name,
        "round": round_num,
        "round_name": "Finals" if round_num == len(bracket) else f"Round {round_num}",
        "game": tournament.get('game'),
        "created_at": datetime.utcnow()
    }
    await db.activity_feed.insert_one(feed_entry)
    
    # Auto-advance winner to next round
    if round_num < len(bracket):
        next_round = bracket[round_num]
        if isinstance(next_round, dict):
            next_matches = next_round.get('matches', [])
        else:
            next_matches = next_round
        
        next_match_idx = (match_num - 1) // 2
        if next_match_idx < len(next_matches):
            next_match = next_matches[next_match_idx]
            if (match_num - 1) % 2 == 0:
                next_match['team_a_id'] = winner_id
                next_match['team_a_name'] = winner_name
            else:
                next_match['team_b_id'] = winner_id
                next_match['team_b_name'] = winner_name
    else:
        # Finals completed - set tournament winner
        await db.tournaments.update_one(
            {"_id": ObjectId(tournament_id)},
            {"$set": {
                "status": "completed",
                "winner_team_id": winner_id,
                "winner_team_name": winner_name
            }}
        )
        
        # Increment cash_tourney_wins for all winning team players
        if winner_id:
            winning_team = await db.tournament_teams.find_one({"_id": ObjectId(winner_id)})
            if winning_team:
                for player in winning_team.get('players', []):
                    player_id = player.get('player_id')
                    if player_id:
                        await db.players.update_one(
                            {"_id": ObjectId(player_id)},
                            {"$inc": {"cash_tourney_wins": 1}}
                        )
    
    await db.tournaments.update_one(
        {"_id": ObjectId(tournament_id)},
        {"$set": {"bracket": bracket}}
    )
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(tournament_id)})
    return serialize_doc(tournament)

@api_router.delete("/tournaments/teams/{team_id}", response_model=dict)
async def delete_tournament_team(team_id: str, requester_id: str):
    """Delete a tournament team (captain or tournament creator only)"""
    try:
        team = await db.tournament_teams.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    tournament = await db.tournaments.find_one({"_id": ObjectId(team['tournament_id'])})
    
    if team['captain_id'] != requester_id and (not tournament or tournament['creator_id'] != requester_id):
        raise HTTPException(status_code=403, detail="Only team captain or tournament creator can delete team")
    
    if tournament and tournament['status'] != 'registration':
        raise HTTPException(status_code=400, detail="Cannot delete team after tournament has started")
    
    await db.tournament_teams.delete_one({"_id": ObjectId(team_id)})
    
    return {"message": "Team deleted successfully"}

# ==================== MATCH ROUTES ====================

@api_router.post("/matches", response_model=dict)
async def create_match(match: MatchCreate):
    try:
        clan_a = await db.clans.find_one({"_id": ObjectId(match.clan_a_id)})
        clan_b = await db.clans.find_one({"_id": ObjectId(match.clan_b_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid clan ID format")
    
    if not clan_a or not clan_b:
        raise HTTPException(status_code=404, detail="One or both clans not found")
    
    if match.clan_a_id == match.clan_b_id:
        raise HTTPException(status_code=400, detail="A clan cannot play against itself")
    
    # Clans must be from the same game
    if clan_a['game'] != clan_b['game']:
        raise HTTPException(status_code=400, detail="Clans must be from the same game to compete")
    
    match_dict = match.dict()
    match_dict['game'] = clan_a['game']  # Set game from clan
    match_dict['clan_a_name'] = clan_a['name']
    match_dict['clan_b_name'] = clan_b['name']
    match_dict['status'] = "scheduled"
    match_dict['score_clan_a'] = 0
    match_dict['score_clan_b'] = 0
    match_dict['winner_id'] = None
    match_dict['challenge_id'] = None
    match_dict['score_reported_by'] = None
    match_dict['created_at'] = datetime.utcnow()
    
    result = await db.matches.insert_one(match_dict)
    match_dict['_id'] = str(result.inserted_id)
    return serialize_doc(match_dict)

@api_router.get("/matches", response_model=List[dict])
async def get_matches(status: Optional[str] = None, game: Optional[str] = None):
    query = {}
    if status:
        query['status'] = status
    if game:
        query['game'] = game
    matches = await db.matches.find(query).sort("scheduled_time", -1).to_list(1000)
    return [serialize_doc(m) for m in matches]

@api_router.get("/matches/{match_id}", response_model=dict)
async def get_match(match_id: str):
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return serialize_doc(match)

@api_router.get("/matches/clan/{clan_id}", response_model=List[dict])
async def get_clan_matches(clan_id: str):
    matches = await db.matches.find({
        "$or": [{"clan_a_id": clan_id}, {"clan_b_id": clan_id}]
    }).sort("scheduled_time", -1).to_list(100)
    return [serialize_doc(m) for m in matches]

@api_router.put("/matches/{match_id}", response_model=dict)
async def update_match(match_id: str, update: MatchUpdate):
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": update_dict}
    )
    
    match = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(match)

@api_router.post("/matches/{match_id}/report-score", response_model=dict)
async def report_score(match_id: str, report: ScoreReport):
    """Report score for a match. Captain, co-captain, or leader can report."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if match.get('status') == 'completed':
        raise HTTPException(status_code=400, detail="Match already completed")
    
    # Check if reporter can manage either clan
    can_manage_a = await can_manage_clan(match['clan_a_id'], report.reporter_id)
    can_manage_b = await can_manage_clan(match['clan_b_id'], report.reporter_id)
    
    if not can_manage_a and not can_manage_b:
        raise HTTPException(status_code=403, detail="Only captain, co-captain, or leader can report scores")
    
    # Determine winner
    winner_id = None
    loser_id = None
    if report.score_clan_a > report.score_clan_b:
        winner_id = match['clan_a_id']
        loser_id = match['clan_b_id']
    elif report.score_clan_b > report.score_clan_a:
        winner_id = match['clan_b_id']
        loser_id = match['clan_a_id']
    
    # Prepare kills data
    clan_a_kills_data = None
    clan_b_kills_data = None
    if report.clan_a_kills:
        clan_a_kills_data = [{"player_id": k.player_id, "player_name": k.player_name, "kills": k.kills} for k in report.clan_a_kills]
    if report.clan_b_kills:
        clan_b_kills_data = [{"player_id": k.player_id, "player_name": k.player_name, "kills": k.kills} for k in report.clan_b_kills]
    
    # Update match
    update_data = {
        "status": "completed",
        "score_clan_a": report.score_clan_a,
        "score_clan_b": report.score_clan_b,
        "winner_id": winner_id,
        "score_reported_by": report.reporter_id
    }
    if clan_a_kills_data:
        update_data["clan_a_kills"] = clan_a_kills_data
    if clan_b_kills_data:
        update_data["clan_b_kills"] = clan_b_kills_data
    
    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": update_data}
    )
    
    # Update clan stats and ladder points
    if winner_id:
        points_transfer = 25
        
        await db.clans.update_one(
            {"_id": ObjectId(winner_id)},
            {"$inc": {"stats.wins": 1, "stats.points": points_transfer}}
        )
        
        await db.clans.update_one(
            {"_id": ObjectId(loser_id)},
            {"$inc": {"stats.losses": 1, "stats.points": -points_transfer}}
        )
    else:
        # Draw
        await db.clans.update_one(
            {"_id": ObjectId(match['clan_a_id'])},
            {"$inc": {"stats.points": 5}}
        )
        await db.clans.update_one(
            {"_id": ObjectId(match['clan_b_id'])},
            {"$inc": {"stats.points": 5}}
        )
    
    # Update player stats (overall + per-game)
    clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
    clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
    game = match.get('game', 'Rainbow Six 3')
    
    # Create a lookup dict for kills
    kills_lookup_a = {}
    kills_lookup_b = {}
    if clan_a_kills_data:
        for k in clan_a_kills_data:
            kills_lookup_a[k['player_id']] = k['kills']
    if clan_b_kills_data:
        for k in clan_b_kills_data:
            kills_lookup_b[k['player_id']] = k['kills']
    
    # Update Clan A members
    for member_id in clan_a.get('members', []):
        # Overall stats increment
        inc_update = {"stats.matches_played": 1}
        if winner_id == match['clan_a_id']:
            inc_update["stats.wins"] = 1
        elif winner_id == match['clan_b_id']:
            inc_update["stats.losses"] = 1
        
        # Per-game stats increment
        game_key = f"game_stats.{game}"
        if winner_id == match['clan_a_id']:
            inc_update[f"{game_key}.wins"] = 1
        elif winner_id == match['clan_b_id']:
            inc_update[f"{game_key}.losses"] = 1
        inc_update[f"{game_key}.matches_played"] = 1
        
        # Add clan match kills if reported
        if member_id in kills_lookup_a:
            inc_update[f"{game_key}.clan_kills"] = kills_lookup_a[member_id]
        
        await db.players.update_one({"_id": ObjectId(member_id)}, {"$inc": inc_update})
    
    # Update Clan B members
    for member_id in clan_b.get('members', []):
        # Overall stats increment
        inc_update = {"stats.matches_played": 1}
        if winner_id == match['clan_b_id']:
            inc_update["stats.wins"] = 1
        elif winner_id == match['clan_a_id']:
            inc_update["stats.losses"] = 1
        
        # Per-game stats increment
        game_key = f"game_stats.{game}"
        if winner_id == match['clan_b_id']:
            inc_update[f"{game_key}.wins"] = 1
        elif winner_id == match['clan_a_id']:
            inc_update[f"{game_key}.losses"] = 1
        inc_update[f"{game_key}.matches_played"] = 1
        
        # Add clan match kills if reported
        if member_id in kills_lookup_b:
            inc_update[f"{game_key}.clan_kills"] = kills_lookup_b[member_id]
        
        await db.players.update_one({"_id": ObjectId(member_id)}, {"$inc": inc_update})
    
    match = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(match)

@api_router.post("/matches/{match_id}/complete", response_model=dict)
async def complete_match(match_id: str, score_clan_a: int, score_clan_b: int):
    """Legacy endpoint for completing a match (for backward compatibility)"""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if match.get('status') == 'completed':
        raise HTTPException(status_code=400, detail="Match already completed")
    
    # Determine winner
    winner_id = None
    loser_id = None
    if score_clan_a > score_clan_b:
        winner_id = match['clan_a_id']
        loser_id = match['clan_b_id']
    elif score_clan_b > score_clan_a:
        winner_id = match['clan_b_id']
        loser_id = match['clan_a_id']
    
    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {
            "status": "completed",
            "score_clan_a": score_clan_a,
            "score_clan_b": score_clan_b,
            "winner_id": winner_id
        }}
    )
    
    if winner_id:
        points_transfer = 25
        await db.clans.update_one(
            {"_id": ObjectId(winner_id)},
            {"$inc": {"stats.wins": 1, "stats.points": points_transfer}}
        )
        await db.clans.update_one(
            {"_id": ObjectId(loser_id)},
            {"$inc": {"stats.losses": 1, "stats.points": -points_transfer}}
        )
    else:
        await db.clans.update_one(
            {"_id": ObjectId(match['clan_a_id'])},
            {"$inc": {"stats.points": 5}}
        )
        await db.clans.update_one(
            {"_id": ObjectId(match['clan_b_id'])},
            {"$inc": {"stats.points": 5}}
        )
    
    clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
    clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
    
    for member_id in clan_a.get('members', []):
        inc_update = {"stats.matches_played": 1}
        if winner_id == match['clan_a_id']:
            inc_update["stats.wins"] = 1
        elif winner_id == match['clan_b_id']:
            inc_update["stats.losses"] = 1
        await db.players.update_one({"_id": ObjectId(member_id)}, {"$inc": inc_update})
    
    for member_id in clan_b.get('members', []):
        inc_update = {"stats.matches_played": 1}
        if winner_id == match['clan_b_id']:
            inc_update["stats.wins"] = 1
        elif winner_id == match['clan_a_id']:
            inc_update["stats.losses"] = 1
        await db.players.update_one({"_id": ObjectId(member_id)}, {"$inc": inc_update})
    
    match = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(match)

# ==================== LADDER ROUTES ====================

@api_router.get("/ladder", response_model=List[dict])
async def get_ladder(game: Optional[str] = None):
    """Get clans sorted by ladder points (ELO ranking). Filter by game for separate ladders."""
    query = {}
    if game:
        if game not in SUPPORTED_GAMES:
            raise HTTPException(status_code=400, detail=f"Game must be one of: {SUPPORTED_GAMES}")
        query['game'] = game
    
    clans = await db.clans.find(query).sort("stats.points", -1).to_list(100)
    
    for i, clan in enumerate(clans):
        clan['rank'] = i + 1
    return [serialize_doc(c) for c in clans]

@api_router.get("/ladder/{game}", response_model=List[dict])
async def get_game_ladder(game: str):
    """Get ladder for a specific game"""
    if game not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Game must be one of: {SUPPORTED_GAMES}")
    
    clans = await db.clans.find({"game": game}).sort("stats.points", -1).to_list(100)
    
    for i, clan in enumerate(clans):
        clan['rank'] = i + 1
    return [serialize_doc(c) for c in clans]

# ==================== GENERAL ROUTES ====================

@api_router.get("/")
async def root():
    return {"message": "Clan Management API", "version": "2.0", "games": SUPPORTED_GAMES}

@api_router.get("/stats")
async def get_stats(game: Optional[str] = None):
    """Get overall platform statistics, optionally filtered by game"""
    query = {}
    if game:
        query['game'] = game
    
    player_count = await db.players.count_documents({})
    clan_count = await db.clans.count_documents(query)
    
    match_query = {}
    if game:
        match_query['game'] = game
    
    match_count = await db.matches.count_documents(match_query)
    completed_matches = await db.matches.count_documents({**match_query, "status": "completed"})
    pending_challenges = await db.challenges.count_documents({**query, "status": "pending"}) if not game else await db.challenges.count_documents({"game": game, "status": "pending"})
    
    return {
        "total_players": player_count,
        "total_clans": clan_count,
        "total_matches": match_count,
        "completed_matches": completed_matches,
        "pending_challenges": pending_challenges,
        "games": SUPPORTED_GAMES
    }

# ==================== CHAT ROUTES ====================

@api_router.post("/chat/messages", response_model=dict)
async def create_chat_message(message: ChatMessageCreate):
    """Create a new chat message (global or clan-specific)"""
    player = await db.players.find_one({"_id": ObjectId(message.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # If clan_id is provided, verify player is a member of that clan
    if message.clan_id:
        clan = await db.clans.find_one({"_id": ObjectId(message.clan_id)})
        if not clan:
            raise HTTPException(status_code=404, detail="Clan not found")
        if message.player_id not in clan.get('members', []):
            raise HTTPException(status_code=403, detail="You must be a clan member to post in clan chat")
    
    chat_message = {
        "player_id": message.player_id,
        "player_username": player['username'],
        "player_avatar": player.get('avatar'),
        "message": message.message[:500],  # Limit message length
        "clan_id": message.clan_id,
        "created_at": datetime.utcnow()
    }
    
    result = await db.chat_messages.insert_one(chat_message)
    chat_message['_id'] = str(result.inserted_id)
    return serialize_doc(chat_message)

@api_router.get("/chat/messages", response_model=List[dict])
async def get_global_chat_messages(limit: int = 50, before: Optional[str] = None):
    """Get global chat messages (clan_id is None)"""
    query = {"clan_id": None}
    if before:
        try:
            query["_id"] = {"$lt": ObjectId(before)}
        except:
            pass
    
    messages = await db.chat_messages.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    return [serialize_doc(m) for m in reversed(messages)]

@api_router.get("/chat/messages/clan/{clan_id}", response_model=List[dict])
async def get_clan_chat_messages(clan_id: str, limit: int = 50, before: Optional[str] = None):
    """Get clan-specific chat messages"""
    query = {"clan_id": clan_id}
    if before:
        try:
            query["_id"] = {"$lt": ObjectId(before)}
        except:
            pass
    
    messages = await db.chat_messages.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    return [serialize_doc(m) for m in reversed(messages)]

# ==================== RETRO FEED ROUTES ====================

@api_router.get("/feed", response_model=List[dict])
async def get_activity_feed(limit: int = 20):
    """Get recent activity feed including completed matches, upcoming matches, quick matches, and tournament matches"""
    feed_items = []
    
    # Get completed clan matches
    completed_matches = await db.matches.find({"status": "completed"}).sort("created_at", -1).limit(limit).to_list(limit)
    for match in completed_matches:
        clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
        clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
        winner = await db.clans.find_one({"_id": ObjectId(match['winner_id'])}) if match.get('winner_id') else None
        
        feed_items.append({
            "type": "clan_match",
            "status": "completed",
            "match_id": str(match['_id']),
            "clan_a_name": clan_a['name'] if clan_a else "Unknown",
            "clan_a_tag": clan_a['tag'] if clan_a else "???",
            "clan_a_score": match.get('score_clan_a', 0),
            "clan_b_name": clan_b['name'] if clan_b else "Unknown",
            "clan_b_tag": clan_b['tag'] if clan_b else "???",
            "clan_b_score": match.get('score_clan_b', 0),
            "winner_name": winner['name'] if winner else None,
            "winner_tag": winner['tag'] if winner else None,
            "game": match.get('game', 'Unknown'),
            "completed_at": match.get('created_at'),
            "scheduled_time": match.get('scheduled_time')
        })
    
    # Get upcoming/scheduled clan matches
    upcoming_matches = await db.matches.find({"status": "scheduled"}).sort("scheduled_time", 1).limit(limit).to_list(limit)
    for match in upcoming_matches:
        clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
        clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
        
        feed_items.append({
            "type": "clan_match",
            "status": "upcoming",
            "match_id": str(match['_id']),
            "clan_a_name": clan_a['name'] if clan_a else "Unknown",
            "clan_a_tag": clan_a['tag'] if clan_a else "???",
            "clan_a_score": 0,
            "clan_b_name": clan_b['name'] if clan_b else "Unknown",
            "clan_b_tag": clan_b['tag'] if clan_b else "???",
            "clan_b_score": 0,
            "winner_name": None,
            "winner_tag": None,
            "game": match.get('game', 'Unknown'),
            "completed_at": match.get('scheduled_time'),
            "scheduled_time": match.get('scheduled_time')
        })
    
    # Get recent quick matches
    quick_matches = await db.quick_matches.find({"status": "completed"}).sort("created_at", -1).limit(limit).to_list(limit)
    for qm in quick_matches:
        team_a = qm.get('team_a', {})
        team_b = qm.get('team_b', {})
        feed_items.append({
            "type": "quick_match",
            "match_id": str(qm['_id']),
            "team_a_name": team_a.get('name', 'Team A'),
            "team_a_score": team_a.get('maps_won', 0),
            "team_b_name": team_b.get('name', 'Team B'),
            "team_b_score": team_b.get('maps_won', 0),
            "winner_name": qm.get('winner'),
            "game": qm.get('game', 'Quick Match'),
            "completed_at": qm.get('created_at')
        })
    
    # Get tournament match results from activity_feed
    tourney_matches = await db.activity_feed.find({"type": "tournament_match"}).sort("completed_at", -1).limit(limit).to_list(limit)
    for tm in tourney_matches:
        feed_items.append({
            "type": "tournament_match",
            "match_id": tm.get('match_id', str(tm['_id'])),
            "tournament_name": tm.get('tournament_name'),
            "tournament_id": tm.get('tournament_id'),
            "round_name": tm.get('round_name', 'Match'),
            "team_a_name": tm.get('team_a_name', 'Team A'),
            "team_a_score": tm.get('team_a_score', 0),
            "team_b_name": tm.get('team_b_name', 'Team B'),
            "team_b_score": tm.get('team_b_score', 0),
            "winner_name": tm.get('winner_name'),
            "game": tm.get('game', 'Tournament'),
            "completed_at": tm.get('completed_at')
        })
    
    # Sort all items by completed_at descending
    feed_items.sort(key=lambda x: x.get('completed_at') or datetime.min, reverse=True)
    
    return feed_items[:limit]

# Include the router in the main app
app.include_router(api_router)

# Include forum routes
from routes.forum import router as forum_router
app.include_router(forum_router)

# Include IAP routes
from routes.iap import router as iap_router
app.include_router(iap_router, prefix="/api")

# Include match lobby routes
from routes.match_lobby import router as match_lobby_router
app.include_router(match_lobby_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
