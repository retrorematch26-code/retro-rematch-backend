from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional, List
import os

router = APIRouter(prefix="/api/match-lobby")

# DB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

MASTER_ADMIN_USERNAME = "Retroadmin"


def serialize_doc(doc):
    if doc:
        doc['_id'] = str(doc['_id'])
    return doc


# ==================== MODELS ====================

class ChatMessageCreate(BaseModel):
    player_id: str
    message: str

class TeamReadyRequest(BaseModel):
    player_id: str
    clan_id: str

class SubmitResultRequest(BaseModel):
    player_id: str
    score_clan_a: int
    score_clan_b: int

class DisputeRequest(BaseModel):
    player_id: str
    reason: str


# ==================== PERMISSION HELPERS ====================

async def get_player(player_id: str):
    try:
        return await db.players.find_one({"_id": ObjectId(player_id)}, {"password_hash": 0})
    except:
        return None

async def is_admin(player_id: str) -> bool:
    player = await get_player(player_id)
    if not player:
        return False
    return player.get("username", "").lower() == MASTER_ADMIN_USERNAME.lower()

async def is_match_participant(match: dict, player_id: str) -> bool:
    """Check if player is a member of either clan in the match."""
    clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
    clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
    in_a = clan_a and player_id in clan_a.get('members', [])
    in_b = clan_b and player_id in clan_b.get('members', [])
    return in_a or in_b

async def is_captain_of_clan(clan_id: str, player_id: str) -> bool:
    try:
        clan = await db.clans.find_one({"_id": ObjectId(clan_id)})
        if not clan:
            return False
        return player_id in [clan.get('leader_id'), clan.get('captain_id'), clan.get('co_captain_id')]
    except:
        return False

async def get_player_team(match: dict, player_id: str) -> Optional[str]:
    """Return 'a' or 'b' or None depending on which team the player is on."""
    clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
    if clan_a and player_id in clan_a.get('members', []):
        return 'a'
    clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})
    if clan_b and player_id in clan_b.get('members', []):
        return 'b'
    return None

async def add_system_message(match_id: str, message: str):
    """Add a system event message to the match chat."""
    chat_msg = {
        "match_id": match_id,
        "user_id": None,
        "username": "SYSTEM",
        "team_id": None,
        "message": message,
        "message_type": "system_event",
        "created_at": datetime.now(timezone.utc),
    }
    await db.match_chat.insert_one(chat_msg)


# ==================== ROUTES ====================

@router.get("/{match_id}")
async def get_lobby(match_id: str, player_id: str):
    """Get full match lobby data. Only participants and admins can access."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    admin = await is_admin(player_id)
    participant = await is_match_participant(match, player_id)

    if not admin and not participant:
        raise HTTPException(status_code=403, detail="You do not have permission to access this lobby")

    # Enrich with roster data
    clan_a = await db.clans.find_one({"_id": ObjectId(match['clan_a_id'])})
    clan_b = await db.clans.find_one({"_id": ObjectId(match['clan_b_id'])})

    async def build_roster(clan):
        if not clan:
            return []
        member_ids = [ObjectId(m) for m in clan.get('members', [])]
        members = await db.players.find({"_id": {"$in": member_ids}}, {"password_hash": 0}).to_list(50)
        roster = []
        for m in members:
            mid = str(m['_id'])
            role = 'member'
            if mid == clan.get('leader_id'):
                role = 'leader'
            elif mid == clan.get('captain_id'):
                role = 'captain'
            elif mid == clan.get('co_captain_id'):
                role = 'co_captain'
            roster.append({
                "player_id": mid,
                "username": m.get('username'),
                "avatar": m.get('avatar'),
                "role": role,
                "is_captain": role in ['leader', 'captain', 'co_captain'],
            })
        role_order = {'leader': 0, 'captain': 1, 'co_captain': 2, 'member': 3}
        roster.sort(key=lambda x: role_order.get(x['role'], 3))
        return roster

    roster_a = await build_roster(clan_a)
    roster_b = await build_roster(clan_b)

    team = await get_player_team(match, player_id)
    is_captain_a = await is_captain_of_clan(match['clan_a_id'], player_id)
    is_captain_b = await is_captain_of_clan(match['clan_b_id'], player_id)

    match_data = serialize_doc(match)
    # Convert datetime fields to ISO strings
    for k in ['scheduled_time', 'created_at']:
        if k in match_data and isinstance(match_data[k], datetime):
            match_data[k] = match_data[k].isoformat()

    return {
        "match": match_data,
        "clan_a": {
            "id": str(clan_a['_id']) if clan_a else None,
            "name": clan_a.get('name') if clan_a else 'Unknown',
            "tag": clan_a.get('tag') if clan_a else '',
            "avatar_icon": clan_a.get('avatar_icon') if clan_a else None,
            "logo": clan_a.get('logo') if clan_a else None,
            "roster": roster_a,
        },
        "clan_b": {
            "id": str(clan_b['_id']) if clan_b else None,
            "name": clan_b.get('name') if clan_b else 'Unknown',
            "tag": clan_b.get('tag') if clan_b else '',
            "avatar_icon": clan_b.get('avatar_icon') if clan_b else None,
            "logo": clan_b.get('logo') if clan_b else None,
            "roster": roster_b,
        },
        "user_team": team,
        "is_captain": is_captain_a or is_captain_b,
        "is_admin": admin,
    }


@router.get("/{match_id}/chat")
async def get_lobby_chat(match_id: str, player_id: str, limit: int = 100):
    """Get match lobby chat messages. Only participants and admins can access."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    admin = await is_admin(player_id)
    participant = await is_match_participant(match, player_id)

    if not admin and not participant:
        raise HTTPException(status_code=403, detail="You do not have permission to access this lobby chat")

    messages = await db.match_chat.find(
        {"match_id": match_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(limit)

    # Convert datetimes to ISO strings
    for msg in messages:
        if isinstance(msg.get('created_at'), datetime):
            msg['created_at'] = msg['created_at'].isoformat()

    return {"messages": messages}


@router.post("/{match_id}/chat")
async def send_lobby_message(match_id: str, body: ChatMessageCreate):
    """Send a chat message in the match lobby. Only participants."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    admin = await is_admin(body.player_id)
    participant = await is_match_participant(match, body.player_id)

    if not admin and not participant:
        raise HTTPException(status_code=403, detail="Only match participants can send messages")

    player = await get_player(body.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    team = await get_player_team(match, body.player_id)
    team_id = match.get(f'clan_{team}_id') if team else None

    chat_msg = {
        "match_id": match_id,
        "user_id": body.player_id,
        "username": player.get('username', 'Unknown'),
        "team_id": team_id,
        "message": body.message.strip(),
        "message_type": "player_message",
        "created_at": datetime.now(timezone.utc),
    }

    await db.match_chat.insert_one(chat_msg)
    return {"status": "sent"}


@router.post("/{match_id}/ready")
async def mark_team_ready(match_id: str, body: TeamReadyRequest):
    """Mark a team as ready. Only captains/leaders can mark ready."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.get('status') not in ['scheduled', 'accepted']:
        raise HTTPException(status_code=400, detail=f"Cannot mark ready when match status is '{match.get('status')}'")

    is_cap = await is_captain_of_clan(body.clan_id, body.player_id)
    admin = await is_admin(body.player_id)
    if not is_cap and not admin:
        raise HTTPException(status_code=403, detail="Only team captains or admins can mark ready")

    # Determine which team
    if body.clan_id == match['clan_a_id']:
        field = 'team_a_ready'
    elif body.clan_id == match['clan_b_id']:
        field = 'team_b_ready'
    else:
        raise HTTPException(status_code=400, detail="Clan is not part of this match")

    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {field: True}}
    )

    # Get team name for system message
    clan = await db.clans.find_one({"_id": ObjectId(body.clan_id)})
    team_name = clan.get('name', 'Unknown') if clan else 'Unknown'
    await add_system_message(match_id, f"{team_name} marked ready")

    # Check if both teams are ready
    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    if updated.get('team_a_ready') and updated.get('team_b_ready'):
        await db.matches.update_one(
            {"_id": ObjectId(match_id)},
            {"$set": {"status": "ready"}}
        )
        await add_system_message(match_id, "Both teams marked ready")

    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(updated)


@router.post("/{match_id}/start")
async def start_match(match_id: str, player_id: str):
    """Start the match. Only captains/admins. Match must be ready or scheduled."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.get('status') not in ['scheduled', 'accepted', 'ready']:
        raise HTTPException(status_code=400, detail=f"Cannot start match with status '{match.get('status')}'")

    is_cap_a = await is_captain_of_clan(match['clan_a_id'], player_id)
    is_cap_b = await is_captain_of_clan(match['clan_b_id'], player_id)
    admin = await is_admin(player_id)

    if not is_cap_a and not is_cap_b and not admin:
        raise HTTPException(status_code=403, detail="Only captains or admins can start the match")

    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {"status": "in_progress"}}
    )

    player = await get_player(player_id)
    name = player.get('username', 'Unknown') if player else 'Unknown'
    await add_system_message(match_id, f"Match started by {name}")

    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(updated)


@router.post("/{match_id}/result")
async def submit_result(match_id: str, body: SubmitResultRequest):
    """Submit match result. Only captains/admins."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.get('status') in ['completed', 'disputed']:
        raise HTTPException(status_code=400, detail="Match already completed or disputed")

    is_cap_a = await is_captain_of_clan(match['clan_a_id'], body.player_id)
    is_cap_b = await is_captain_of_clan(match['clan_b_id'], body.player_id)
    admin = await is_admin(body.player_id)

    if not is_cap_a and not is_cap_b and not admin:
        raise HTTPException(status_code=403, detail="Only captains or admins can submit results")

    winner_id = None
    if body.score_clan_a > body.score_clan_b:
        winner_id = match['clan_a_id']
    elif body.score_clan_b > body.score_clan_a:
        winner_id = match['clan_b_id']

    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {
            "status": "awaiting_result",
            "score_clan_a": body.score_clan_a,
            "score_clan_b": body.score_clan_b,
            "winner_id": winner_id,
            "score_reported_by": body.player_id,
        }}
    )

    player = await get_player(body.player_id)
    name = player.get('username', 'Unknown') if player else 'Unknown'
    await add_system_message(
        match_id,
        f"Result submitted by {name}: {match.get('clan_a_name', 'A')} {body.score_clan_a} - {body.score_clan_b} {match.get('clan_b_name', 'B')}"
    )

    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(updated)


@router.post("/{match_id}/confirm-result")
async def confirm_result(match_id: str, player_id: str):
    """Confirm the submitted result and finalize the match. Captains/admins only."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.get('status') != 'awaiting_result':
        raise HTTPException(status_code=400, detail="Match is not awaiting result confirmation")

    is_cap_a = await is_captain_of_clan(match['clan_a_id'], player_id)
    is_cap_b = await is_captain_of_clan(match['clan_b_id'], player_id)
    admin = await is_admin(player_id)

    if not is_cap_a and not is_cap_b and not admin:
        raise HTTPException(status_code=403, detail="Only captains or admins can confirm results")

    # Finalize as completed
    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {"status": "completed"}}
    )

    # Update clan stats
    winner_id = match.get('winner_id')
    loser_id = None
    if winner_id:
        loser_id = match['clan_b_id'] if winner_id == match['clan_a_id'] else match['clan_a_id']
        await db.clans.update_one(
            {"_id": ObjectId(winner_id)},
            {"$inc": {"stats.wins": 1, "stats.points": 25}}
        )
        await db.clans.update_one(
            {"_id": ObjectId(loser_id)},
            {"$inc": {"stats.losses": 1, "stats.points": -25}}
        )

    await add_system_message(match_id, "Match result confirmed. Match completed!")

    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(updated)


@router.post("/{match_id}/dispute")
async def open_dispute(match_id: str, body: DisputeRequest):
    """Open a dispute on the match. Only captains/admins."""
    try:
        match = await db.matches.find_one({"_id": ObjectId(match_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid match ID")

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    is_cap_a = await is_captain_of_clan(match['clan_a_id'], body.player_id)
    is_cap_b = await is_captain_of_clan(match['clan_b_id'], body.player_id)
    admin = await is_admin(body.player_id)

    if not is_cap_a and not is_cap_b and not admin:
        raise HTTPException(status_code=403, detail="Only captains or admins can open disputes")

    await db.matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$set": {
            "status": "disputed",
            "dispute_reason": body.reason,
            "dispute_by": body.player_id,
        }}
    )

    player = await get_player(body.player_id)
    name = player.get('username', 'Unknown') if player else 'Unknown'
    await add_system_message(match_id, f"Dispute opened by {name}: {body.reason}")

    updated = await db.matches.find_one({"_id": ObjectId(match_id)})
    return serialize_doc(updated)
