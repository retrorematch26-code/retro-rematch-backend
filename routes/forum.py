from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
import os
from pymongo import MongoClient, DESCENDING, ASCENDING
from models.forum import (
    ForumCategory, ForumThread, ForumPost, 
    ForumModerator, ForumBan, ForumSignature, 
    parse_emojis, CLASSIC_EMOJIS
)

router = APIRouter(prefix="/api/forum", tags=["forum"])

# MongoDB connection
client = MongoClient(os.environ.get('MONGO_URL'))
db = client[os.environ.get('DB_NAME', 'test_database')]

def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    doc['_id'] = str(doc['_id'])
    return doc

# ============ CATEGORIES ============

@router.get("/categories")
async def get_categories():
    """Get all forum categories with thread counts"""
    try:
        categories = list(db.forum_categories.find().sort("order", ASCENDING))
        print(f"[Forum] Found {len(categories)} categories in DB")
        result = []
        for cat in categories:
            cat = serialize_doc(cat)
            # Get thread count and last post info
            thread_count = db.forum_threads.count_documents({"category_id": cat['_id']})
            last_thread = db.forum_threads.find_one(
                {"category_id": cat['_id']},
                sort=[("last_post_at", DESCENDING)]
            )
            cat['thread_count'] = thread_count
            cat['last_thread'] = serialize_doc(last_thread) if last_thread else None
            result.append(cat)
        print(f"[Forum] Returning {len(result)} categories")
        return result
    except Exception as e:
        print(f"[Forum] Error getting categories: {e}")
        return []

@router.post("/categories")
async def create_category(category: dict):
    """Create a new forum category (master admin only)"""
    creator_id = category.get('created_by')
    if not creator_id:
        raise HTTPException(status_code=400, detail="Creator ID is required")
    
    # Check if creator is a master admin
    try:
        creator = db.players.find_one({"_id": ObjectId(creator_id)})
    except:
        creator = db.players.find_one({"_id": creator_id})
    
    if not creator or not creator.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can create forum categories")
    
    category['created_at'] = datetime.now(timezone.utc)
    result = db.forum_categories.insert_one(category)
    category['_id'] = str(result.inserted_id)
    return category

@router.put("/categories/{category_id}")
async def update_category(category_id: str, updates: dict):
    """Update a category (master admin only)"""
    updater_id = updates.get('updated_by')
    if not updater_id:
        raise HTTPException(status_code=400, detail="Updater ID is required")
    
    # Check if updater is a master admin
    try:
        updater = db.players.find_one({"_id": ObjectId(updater_id)})
    except:
        updater = db.players.find_one({"_id": updater_id})
    
    if not updater or not updater.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can update forum categories")
    
    # Remove updated_by from the updates so it's not stored
    updates.pop('updated_by', None)
    
    db.forum_categories.update_one(
        {"_id": ObjectId(category_id)},
        {"$set": updates}
    )
    return {"success": True}

@router.delete("/categories/{category_id}")
async def delete_category(category_id: str, deleted_by: str = None):
    """Delete a category (master admin only)"""
    if not deleted_by:
        raise HTTPException(status_code=400, detail="Deleter ID is required")
    
    # Check if deleter is a master admin
    try:
        deleter = db.players.find_one({"_id": ObjectId(deleted_by)})
    except:
        deleter = db.players.find_one({"_id": deleted_by})
    
    if not deleter or not deleter.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can delete forum categories")
    
    db.forum_categories.delete_one({"_id": ObjectId(category_id)})
    return {"success": True}

# ============ THREADS ============

@router.get("/categories/{category_id}/threads")
async def get_threads(
    category_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50)
):
    """Get threads in a category with pagination"""
    skip = (page - 1) * limit
    
    # Get pinned threads first, then by last_post_at
    pipeline = [
        {"$match": {"category_id": category_id}},
        {"$sort": {"is_pinned": -1, "last_post_at": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    
    threads = list(db.forum_threads.aggregate(pipeline))
    total = db.forum_threads.count_documents({"category_id": category_id})
    
    # Get author info for each thread
    for thread in threads:
        thread = serialize_doc(thread)
        author = db.players.find_one({"_id": ObjectId(thread['author_id'])}, {"username": 1, "avatar": 1})
        if author:
            thread['author'] = {"username": author.get('username'), "avatar": author.get('avatar')}
    
    return {
        "threads": [serialize_doc(t) for t in threads],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get a single thread with its posts"""
    thread = db.forum_threads.find_one({"_id": ObjectId(thread_id)})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Increment view count
    db.forum_threads.update_one(
        {"_id": ObjectId(thread_id)},
        {"$inc": {"view_count": 1}}
    )
    
    thread = serialize_doc(thread)
    
    # Get category info
    category = db.forum_categories.find_one({"_id": ObjectId(thread['category_id'])})
    thread['category'] = serialize_doc(category) if category else None
    
    return thread

@router.post("/threads")
async def create_thread(thread_data: dict):
    """Create a new thread"""
    # Check if user is banned
    ban = db.forum_bans.find_one({
        "player_id": thread_data['author_id'],
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": datetime.now(timezone.utc)}}
        ]
    })
    if ban:
        raise HTTPException(status_code=403, detail="You are banned from the forum")
    
    # Get author name
    author = db.players.find_one({"_id": ObjectId(thread_data['author_id'])})
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    now = datetime.now(timezone.utc)
    thread = {
        "category_id": thread_data['category_id'],
        "title": thread_data['title'],
        "author_id": thread_data['author_id'],
        "author_name": author.get('username', 'Unknown'),
        "is_pinned": False,
        "is_locked": False,
        "is_announcement": False,
        "view_count": 0,
        "reply_count": 0,
        "last_post_at": now,
        "last_post_by": thread_data['author_id'],
        "last_post_by_name": author.get('username', 'Unknown'),
        "created_at": now,
        "tags": thread_data.get('tags', [])
    }
    
    result = db.forum_threads.insert_one(thread)
    thread_id = str(result.inserted_id)
    
    # Create the first post (thread content)
    first_post = {
        "thread_id": thread_id,
        "author_id": thread_data['author_id'],
        "author_name": author.get('username', 'Unknown'),
        "content": parse_emojis(thread_data.get('content', '')),
        "is_edited": False,
        "is_deleted": False,
        "reactions": {},
        "created_at": now
    }
    db.forum_posts.insert_one(first_post)
    
    thread['_id'] = thread_id
    return thread

@router.put("/threads/{thread_id}")
async def update_thread(thread_id: str, updates: dict, moderator_id: str = None):
    """Update a thread (author or moderator)"""
    thread = db.forum_threads.find_one({"_id": ObjectId(thread_id)})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Only allow certain fields to be updated
    allowed_fields = ["title", "tags"]
    mod_fields = ["is_pinned", "is_locked", "is_announcement"]
    
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    
    # Check if moderator is updating
    if moderator_id:
        is_mod = db.forum_moderators.find_one({"player_id": moderator_id})
        if is_mod:
            for field in mod_fields:
                if field in updates:
                    update_data[field] = updates[field]
    
    if update_data:
        db.forum_threads.update_one(
            {"_id": ObjectId(thread_id)},
            {"$set": update_data}
        )
    
    return {"success": True}

@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, moderator_id: str):
    """Delete a thread (moderator only)"""
    is_mod = db.forum_moderators.find_one({"player_id": moderator_id})
    if not is_mod:
        raise HTTPException(status_code=403, detail="Moderator access required")
    
    # Delete all posts in thread
    db.forum_posts.delete_many({"thread_id": thread_id})
    db.forum_threads.delete_one({"_id": ObjectId(thread_id)})
    
    return {"success": True}

# ============ POSTS ============

@router.get("/threads/{thread_id}/posts")
async def get_posts(
    thread_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50)
):
    """Get posts in a thread with author signatures"""
    skip = (page - 1) * limit
    
    posts = list(db.forum_posts.find(
        {"thread_id": thread_id, "is_deleted": False}
    ).sort("created_at", ASCENDING).skip(skip).limit(limit))
    
    total = db.forum_posts.count_documents({"thread_id": thread_id, "is_deleted": False})
    
    # Enrich with author info and signatures
    for post in posts:
        post = serialize_doc(post)
        author = db.players.find_one(
            {"_id": ObjectId(post['author_id'])},
            {"username": 1, "avatar": 1, "forum_signature": 1, "stats": 1, "created_at": 1}
        )
        if author:
            post['author'] = {
                "username": author.get('username'),
                "avatar": author.get('avatar'),
                "signature": author.get('forum_signature'),
                "post_count": db.forum_posts.count_documents({"author_id": post['author_id'], "is_deleted": False}),
                "joined": author.get('created_at'),
                "stats": author.get('stats', {})
            }
    
    return {
        "posts": [serialize_doc(p) for p in posts],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.post("/posts")
async def create_post(post_data: dict):
    """Create a reply post"""
    # Check if user is banned
    ban = db.forum_bans.find_one({
        "player_id": post_data['author_id'],
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": datetime.now(timezone.utc)}}
        ]
    })
    if ban:
        raise HTTPException(status_code=403, detail="You are banned from the forum")
    
    # Check if thread is locked
    thread = db.forum_threads.find_one({"_id": ObjectId(post_data['thread_id'])})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.get('is_locked'):
        raise HTTPException(status_code=403, detail="Thread is locked")
    
    # Get author info
    author = db.players.find_one({"_id": ObjectId(post_data['author_id'])})
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    now = datetime.now(timezone.utc)
    post = {
        "thread_id": post_data['thread_id'],
        "author_id": post_data['author_id'],
        "author_name": author.get('username', 'Unknown'),
        "content": parse_emojis(post_data['content']),
        "is_edited": False,
        "is_deleted": False,
        "reactions": {},
        "quote_post_id": post_data.get('quote_post_id'),
        "created_at": now
    }
    
    result = db.forum_posts.insert_one(post)
    post['_id'] = str(result.inserted_id)
    
    # Update thread stats
    db.forum_threads.update_one(
        {"_id": ObjectId(post_data['thread_id'])},
        {
            "$inc": {"reply_count": 1},
            "$set": {
                "last_post_at": now,
                "last_post_by": post_data['author_id'],
                "last_post_by_name": author.get('username', 'Unknown')
            }
        }
    )
    
    return post

@router.put("/posts/{post_id}")
async def update_post(post_id: str, updates: dict, editor_id: str):
    """Edit a post (author or moderator)"""
    post = db.forum_posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check if editor is author or moderator
    is_author = post['author_id'] == editor_id
    is_mod = db.forum_moderators.find_one({"player_id": editor_id})
    
    if not is_author and not is_mod:
        raise HTTPException(status_code=403, detail="Not authorized to edit this post")
    
    db.forum_posts.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {
            "content": parse_emojis(updates['content']),
            "is_edited": True,
            "edited_at": datetime.now(timezone.utc),
            "edited_by": editor_id
        }}
    )
    
    return {"success": True}

@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, moderator_id: str):
    """Delete a post (soft delete, moderator only)"""
    is_mod = db.forum_moderators.find_one({"player_id": moderator_id})
    if not is_mod:
        raise HTTPException(status_code=403, detail="Moderator access required")
    
    post = db.forum_posts.find_one({"_id": ObjectId(post_id)})
    if post:
        db.forum_posts.update_one(
            {"_id": ObjectId(post_id)},
            {"$set": {"is_deleted": True, "deleted_by": moderator_id}}
        )
        # Update thread reply count
        db.forum_threads.update_one(
            {"_id": ObjectId(post['thread_id'])},
            {"$inc": {"reply_count": -1}}
        )
    
    return {"success": True}

@router.post("/posts/{post_id}/react")
async def react_to_post(post_id: str, reaction: str, player_id: str):
    """Add a reaction to a post"""
    valid_reactions = ["lol", "gg", "owned", "rip", "fire", "goat"]
    if reaction not in valid_reactions:
        raise HTTPException(status_code=400, detail="Invalid reaction")
    
    post = db.forum_posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    reactions = post.get('reactions', {})
    if reaction not in reactions:
        reactions[reaction] = []
    
    if player_id in reactions[reaction]:
        # Remove reaction
        reactions[reaction].remove(player_id)
    else:
        # Add reaction
        reactions[reaction].append(player_id)
    
    db.forum_posts.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"reactions": reactions}}
    )
    
    return {"reactions": reactions}

# ============ SIGNATURES ============

# Signature constraints - 2000s forum style!
MAX_SIGNATURE_WIDTH = 600
MAX_SIGNATURE_HEIGHT = 180
MAX_SIGNATURE_FILE_SIZE = 2 * 1024 * 1024  # 2MB
ALLOWED_SIGNATURE_TYPES = ['image/png', 'image/gif']

@router.put("/signature/{player_id}")
async def update_signature(player_id: str, signature: dict):
    """Update a player's forum signature"""
    db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"forum_signature": signature}}
    )
    return {"success": True}

@router.get("/signature/{player_id}")
async def get_signature(player_id: str):
    """Get a player's forum signature"""
    # Validate player_id format
    if not player_id or len(player_id) != 24:
        raise HTTPException(status_code=400, detail="Invalid player ID format")
    try:
        player = db.players.find_one(
            {"_id": ObjectId(player_id)},
            {"forum_signature": 1}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid player ID format")
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player.get('forum_signature', {})

@router.post("/signature/{player_id}/upload")
async def upload_signature(player_id: str, image_data: dict):
    """
    Upload a signature image (direct upload, base64 encoded)
    Validates: PNG/GIF only, max 600x180px, max 2MB
    """
    import base64
    from io import BytesIO
    
    # Check player exists
    player = db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get base64 image data
    base64_str = image_data.get('image')
    if not base64_str:
        raise HTTPException(status_code=400, detail="No image data provided")
    
    # Parse data URL format: data:image/png;base64,xxxx
    try:
        if ',' in base64_str:
            header, base64_data = base64_str.split(',', 1)
            # Extract mime type
            if 'image/png' in header:
                mime_type = 'image/png'
                extension = 'png'
            elif 'image/gif' in header:
                mime_type = 'image/gif'
                extension = 'gif'
            else:
                raise HTTPException(status_code=400, detail="Only PNG and GIF images are allowed for signatures")
        else:
            base64_data = base64_str
            mime_type = 'image/png'  # Default
            extension = 'png'
        
        # Decode base64
        image_bytes = base64.b64decode(base64_data)
        
        # Check file size (2MB max)
        if len(image_bytes) > MAX_SIGNATURE_FILE_SIZE:
            raise HTTPException(
                status_code=400, 
                detail=f"Signature image too large. Max size is 2MB, yours is {len(image_bytes) / (1024*1024):.1f}MB"
            )
        
        # Validate image dimensions using PIL
        try:
            from PIL import Image
            img = Image.open(BytesIO(image_bytes))
            width, height = img.size
            
            if width > MAX_SIGNATURE_WIDTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Signature too wide. Max width is {MAX_SIGNATURE_WIDTH}px, yours is {width}px"
                )
            if height > MAX_SIGNATURE_HEIGHT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Signature too tall. Max height is {MAX_SIGNATURE_HEIGHT}px, yours is {height}px"
                )
                
            # For GIF, check if it's animated (has multiple frames)
            is_animated = hasattr(img, 'n_frames') and img.n_frames > 1
            
        except ImportError:
            # PIL not available, skip dimension check but warn
            width = MAX_SIGNATURE_WIDTH
            height = MAX_SIGNATURE_HEIGHT
            is_animated = extension == 'gif'
        
        # Store the image as base64 in the database (for simplicity)
        # In production, you'd upload to S3/GCS
        signature_data = {
            'image_url': base64_str,  # Store the full data URL
            'image_width': width,
            'image_height': height,
            'is_animated': is_animated,
            'file_size': len(image_bytes),
            'mime_type': mime_type,
            'enabled': True,
            'text': image_data.get('text', ''),
            'uploaded_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Update player's signature
        db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"forum_signature": signature_data}}
        )
        
        return {
            "success": True,
            "signature": signature_data,
            "message": f"Signature uploaded successfully! ({width}x{height}px, {len(image_bytes)/1024:.1f}KB)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Forum] Signature upload error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(e)}")

@router.delete("/signature/{player_id}")
async def delete_signature(player_id: str):
    """Delete a player's forum signature"""
    player = db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$unset": {"forum_signature": ""}}
    )
    return {"success": True, "message": "Signature deleted"}

# ============ MODERATORS ============

@router.get("/moderators")
async def get_moderators():
    """Get all forum moderators"""
    mods = list(db.forum_moderators.find())
    return [serialize_doc(m) for m in mods]

@router.post("/moderators")
async def add_moderator(mod_data: dict):
    """Add a new moderator (master admin only)"""
    # Verify the appointer is a master admin
    appointer_id = mod_data.get('appointed_by')
    if not appointer_id:
        raise HTTPException(status_code=400, detail="Appointer ID is required")
    
    # Check if appointer is a master admin
    try:
        appointer = db.players.find_one({"_id": ObjectId(appointer_id)})
    except:
        appointer = db.players.find_one({"_id": appointer_id})
    
    if not appointer or not appointer.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can appoint forum moderators")
    
    # Check if player exists
    player = db.players.find_one({"_id": ObjectId(mod_data['player_id'])})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Check if already a moderator
    existing = db.forum_moderators.find_one({"player_id": mod_data['player_id']})
    if existing:
        raise HTTPException(status_code=400, detail="Player is already a moderator")
    
    mod = {
        "player_id": mod_data['player_id'],
        "player_name": player.get('username', 'Unknown'),
        "category_ids": mod_data.get('category_ids', []),
        "can_pin": mod_data.get('can_pin', True),
        "can_lock": mod_data.get('can_lock', True),
        "can_delete": mod_data.get('can_delete', True),
        "can_edit": mod_data.get('can_edit', True),
        "can_ban": mod_data.get('can_ban', False),
        "appointed_by": appointer_id,
        "appointed_at": datetime.now(timezone.utc)
    }
    
    result = db.forum_moderators.insert_one(mod)
    mod['_id'] = str(result.inserted_id)
    return mod

@router.delete("/moderators/{mod_id}")
async def remove_moderator(mod_id: str, removed_by: str = None):
    """Remove a moderator (master admin only)"""
    if not removed_by:
        raise HTTPException(status_code=400, detail="Remover ID is required")
    
    # Check if remover is a master admin
    try:
        remover = db.players.find_one({"_id": ObjectId(removed_by)})
    except:
        remover = db.players.find_one({"_id": removed_by})
    
    if not remover or not remover.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can remove forum moderators")
    
    db.forum_moderators.delete_one({"_id": ObjectId(mod_id)})
    return {"success": True}

@router.get("/moderators/check/{player_id}")
async def check_moderator(player_id: str):
    """Check if a player is a moderator"""
    mod = db.forum_moderators.find_one({"player_id": player_id})
    return {"is_moderator": mod is not None, "moderator": serialize_doc(mod) if mod else None}

# ============ BANS ============

@router.post("/bans")
async def ban_player(ban_data: dict):
    """Ban a player from the forum (moderator with can_ban)"""
    mod = db.forum_moderators.find_one({"player_id": ban_data['banned_by']})
    if not mod or not mod.get('can_ban'):
        raise HTTPException(status_code=403, detail="Not authorized to ban users")
    
    banner = db.players.find_one({"_id": ObjectId(ban_data['banned_by'])})
    player = db.players.find_one({"_id": ObjectId(ban_data['player_id'])})
    
    ban = {
        "player_id": ban_data['player_id'],
        "player_name": player.get('username', 'Unknown') if player else 'Unknown',
        "reason": ban_data['reason'],
        "banned_by": ban_data['banned_by'],
        "banned_by_name": banner.get('username', 'Unknown') if banner else 'Unknown',
        "expires_at": ban_data.get('expires_at'),
        "created_at": datetime.now(timezone.utc)
    }
    
    result = db.forum_bans.insert_one(ban)
    ban['_id'] = str(result.inserted_id)
    return ban

@router.delete("/bans/{ban_id}")
async def unban_player(ban_id: str):
    """Remove a ban"""
    db.forum_bans.delete_one({"_id": ObjectId(ban_id)})
    return {"success": True}

# ============ EMOJI LIST ============

@router.get("/emojis")
async def get_emojis():
    """Get list of classic emojis"""
    return CLASSIC_EMOJIS

# ============ SEARCH ============

@router.get("/search")
async def search_forum(
    q: str = Query(..., min_length=3),
    category_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50)
):
    """Search forum threads and posts"""
    skip = (page - 1) * limit
    
    # Search threads by title
    thread_query = {"title": {"$regex": q, "$options": "i"}}
    if category_id:
        thread_query["category_id"] = category_id
    
    threads = list(db.forum_threads.find(thread_query).sort("last_post_at", DESCENDING).skip(skip).limit(limit))
    
    # Also search posts by content
    post_query = {"content": {"$regex": q, "$options": "i"}, "is_deleted": False}
    posts = list(db.forum_posts.find(post_query).limit(10))
    
    # Get unique thread IDs from posts
    post_thread_ids = list(set([p['thread_id'] for p in posts]))
    additional_threads = list(db.forum_threads.find({"_id": {"$in": [ObjectId(tid) for tid in post_thread_ids]}}))
    
    # Combine results, avoiding duplicates
    seen_ids = set([str(t['_id']) for t in threads])
    for t in additional_threads:
        if str(t['_id']) not in seen_ids:
            threads.append(t)
            seen_ids.add(str(t['_id']))
    
    return {
        "threads": [serialize_doc(t) for t in threads],
        "total": len(threads),
        "page": page
    }

# ============ STATS ============

@router.get("/stats")
async def get_forum_stats():
    """Get overall forum statistics"""
    return {
        "total_threads": db.forum_threads.count_documents({}),
        "total_posts": db.forum_posts.count_documents({"is_deleted": False}),
        "total_members": db.players.count_documents({}),
        "newest_member": serialize_doc(db.players.find_one(sort=[("created_at", DESCENDING)])),
        "latest_post": serialize_doc(db.forum_posts.find_one({"is_deleted": False}, sort=[("created_at", DESCENDING)]))
    }

# ============ ADMIN MANAGEMENT ============

@router.get("/admin/check/{player_id}")
async def check_admin_status(player_id: str):
    """Check if a player is a master admin"""
    player = None
    try:
        player = db.players.find_one({"_id": ObjectId(player_id)})
    except Exception as e:
        print(f"[Admin Check] Error with ObjectId: {e}")
        try:
            player = db.players.find_one({"_id": player_id})
        except Exception as e2:
            print(f"[Admin Check] Error with string: {e2}")
    
    if not player:
        print(f"[Admin Check] Player not found: {player_id}")
        return {"is_master_admin": False, "role": None}
    
    print(f"[Admin Check] Found player: {player.get('username')}, is_master_admin: {player.get('is_master_admin')}")
    return {
        "is_master_admin": player.get('is_master_admin', False),
        "role": player.get('role', 'user')
    }

@router.post("/admin/grant")
async def grant_admin(data: dict):
    """Grant admin role to a player (master admin only)"""
    granter_id = data.get('granter_id')
    target_player_id = data.get('player_id')
    role = data.get('role', 'admin')  # 'admin' or 'moderator'
    
    if not granter_id or not target_player_id:
        raise HTTPException(status_code=400, detail="Granter ID and Player ID are required")
    
    # Check if granter is master admin
    try:
        granter = db.players.find_one({"_id": ObjectId(granter_id)})
    except:
        granter = db.players.find_one({"_id": granter_id})
    
    if not granter or not granter.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can grant admin roles")
    
    # Update target player
    try:
        result = db.players.update_one(
            {"_id": ObjectId(target_player_id)},
            {"$set": {"role": role, "is_admin": role in ['admin', 'master_admin']}}
        )
    except:
        result = db.players.update_one(
            {"_id": target_player_id},
            {"$set": {"role": role, "is_admin": role in ['admin', 'master_admin']}}
        )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return {"success": True, "message": f"Granted {role} role to player"}

@router.post("/admin/revoke")
async def revoke_admin(data: dict):
    """Revoke admin role from a player (master admin only)"""
    revoker_id = data.get('revoker_id')
    target_player_id = data.get('player_id')
    
    if not revoker_id or not target_player_id:
        raise HTTPException(status_code=400, detail="Revoker ID and Player ID are required")
    
    # Check if revoker is master admin
    try:
        revoker = db.players.find_one({"_id": ObjectId(revoker_id)})
    except:
        revoker = db.players.find_one({"_id": revoker_id})
    
    if not revoker or not revoker.get('is_master_admin'):
        raise HTTPException(status_code=403, detail="Only master admin can revoke admin roles")
    
    # Update target player
    try:
        result = db.players.update_one(
            {"_id": ObjectId(target_player_id)},
            {"$set": {"role": "user", "is_admin": False}}
        )
    except:
        result = db.players.update_one(
            {"_id": target_player_id},
            {"$set": {"role": "user", "is_admin": False}}
        )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return {"success": True, "message": "Revoked admin role from player"}

@router.get("/admins")
async def get_all_admins():
    """Get list of all admins and moderators"""
    admins = list(db.players.find(
        {"$or": [{"is_master_admin": True}, {"is_admin": True}, {"role": {"$in": ["admin", "master_admin", "moderator"]}}]},
        {"username": 1, "role": 1, "is_master_admin": 1, "is_admin": 1, "email": 1}
    ))
    return [serialize_doc(a) for a in admins]

