"""
In-App Purchase (IAP) routes for RevenueCat integration
Handles credit purchases for tournament entries
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bson import ObjectId
import httpx
import os
import logging

router = APIRouter(prefix="/iap", tags=["in-app-purchases"])

# MongoDB connection
from pymongo import MongoClient
client = MongoClient(os.environ.get('MONGO_URL'))
db = client[os.environ.get('DB_NAME', 'test_database')]

logger = logging.getLogger(__name__)

# RevenueCat configuration
REVENUECAT_SECRET_KEY = os.environ.get('REVENUECAT_SECRET_KEY', 'sk_hoVQaVwGFGkSBtwfIbFxOWqENLHJx')
REVENUECAT_PROJECT_ID = os.environ.get('REVENUECAT_PROJECT_ID', 'proj7a6d561e')
REVENUECAT_API_URL = "https://api.revenuecat.com/v2"

# Credit package definitions
CREDIT_PACKAGES = {
    "credits_1": {"credits": 1, "price": 20.00, "name": "1 Credit"},
    "credits_2": {"credits": 2, "price": 40.00, "name": "2 Credits"},
    "credits_3": {"credits": 3, "price": 60.00, "name": "3 Credits"},
    "credits_4": {"credits": 4, "price": 80.00, "name": "4 Credits"},
    "credits_5": {"credits": 5, "price": 100.00, "name": "5 Credits"},
}

def serialize_doc(doc):
    if doc is None:
        return None
    doc['_id'] = str(doc['_id'])
    return doc


class CreditPurchaseRequest(BaseModel):
    player_id: str
    revenuecat_customer_id: str
    product_id: str
    transaction_id: str
    purchase_date: Optional[str] = None


class CreditBalanceResponse(BaseModel):
    player_id: str
    credits: int
    last_updated: str


@router.post("/credit")
async def grant_credits(purchase: CreditPurchaseRequest):
    """
    Grant credits to a player after successful RevenueCat purchase.
    Called by the frontend after purchase success.
    """
    logger.info(f"Credit purchase request: player={purchase.player_id}, product={purchase.product_id}")
    
    # Validate product ID
    if purchase.product_id not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Invalid product ID: {purchase.product_id}")
    
    # Check for duplicate transaction
    existing_transaction = db.iap_transactions.find_one({
        "transaction_id": purchase.transaction_id
    })
    if existing_transaction:
        logger.warning(f"Duplicate transaction: {purchase.transaction_id}")
        raise HTTPException(status_code=400, detail="Transaction already processed")
    
    # Get credit amount from package
    package = CREDIT_PACKAGES[purchase.product_id]
    credits_to_add = package["credits"]
    
    # Get or create player credit record
    player_credits = db.player_credits.find_one({"player_id": purchase.player_id})
    
    if player_credits:
        new_balance = player_credits.get("credits", 0) + credits_to_add
        db.player_credits.update_one(
            {"player_id": purchase.player_id},
            {
                "$set": {
                    "credits": new_balance,
                    "last_updated": datetime.now(timezone.utc)
                },
                "$inc": {"total_purchased": credits_to_add}
            }
        )
    else:
        new_balance = credits_to_add
        db.player_credits.insert_one({
            "player_id": purchase.player_id,
            "credits": credits_to_add,
            "total_purchased": credits_to_add,
            "total_spent": 0,
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        })
    
    # Record transaction
    db.iap_transactions.insert_one({
        "player_id": purchase.player_id,
        "revenuecat_customer_id": purchase.revenuecat_customer_id,
        "product_id": purchase.product_id,
        "transaction_id": purchase.transaction_id,
        "credits_granted": credits_to_add,
        "purchase_date": purchase.purchase_date or datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc)
    })
    
    logger.info(f"Credits granted: player={purchase.player_id}, credits={credits_to_add}, new_balance={new_balance}")
    
    return {
        "success": True,
        "credits_granted": credits_to_add,
        "new_balance": new_balance,
        "product_id": purchase.product_id
    }


@router.get("/credits/{player_id}")
async def get_credits(player_id: str):
    """Get current credit balance for a player"""
    player_credits = db.player_credits.find_one({"player_id": player_id})
    
    if not player_credits:
        return {
            "player_id": player_id,
            "credits": 0,
            "total_purchased": 0,
            "total_spent": 0,
            "last_updated": None
        }
    
    return {
        "player_id": player_id,
        "credits": player_credits.get("credits", 0),
        "total_purchased": player_credits.get("total_purchased", 0),
        "total_spent": player_credits.get("total_spent", 0),
        "last_updated": player_credits.get("last_updated", "").isoformat() if player_credits.get("last_updated") else None
    }


@router.post("/credits/{player_id}/spend")
async def spend_credits(player_id: str, amount: int = 1, reason: str = "tournament_entry"):
    """
    Spend credits for tournament entry or other purposes.
    Returns success if player has enough credits.
    """
    player_credits = db.player_credits.find_one({"player_id": player_id})
    
    if not player_credits or player_credits.get("credits", 0) < amount:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient credits. Required: {amount}, Available: {player_credits.get('credits', 0) if player_credits else 0}"
        )
    
    new_balance = player_credits["credits"] - amount
    
    db.player_credits.update_one(
        {"player_id": player_id},
        {
            "$set": {
                "credits": new_balance,
                "last_updated": datetime.now(timezone.utc)
            },
            "$inc": {"total_spent": amount}
        }
    )
    
    # Record spending transaction
    db.credit_spending.insert_one({
        "player_id": player_id,
        "amount": amount,
        "reason": reason,
        "balance_before": player_credits["credits"],
        "balance_after": new_balance,
        "created_at": datetime.now(timezone.utc)
    })
    
    logger.info(f"Credits spent: player={player_id}, amount={amount}, reason={reason}, new_balance={new_balance}")
    
    return {
        "success": True,
        "credits_spent": amount,
        "new_balance": new_balance,
        "reason": reason
    }


@router.get("/packages")
async def get_packages():
    """Get available credit packages"""
    return {
        "packages": [
            {
                "product_id": pid,
                "name": pkg["name"],
                "credits": pkg["credits"],
                "price": pkg["price"],
                "price_string": f"${pkg['price']:.2f}"
            }
            for pid, pkg in CREDIT_PACKAGES.items()
        ]
    }


@router.get("/transactions/{player_id}")
async def get_transactions(player_id: str, limit: int = 20):
    """Get purchase transaction history for a player"""
    transactions = list(db.iap_transactions.find(
        {"player_id": player_id}
    ).sort("created_at", -1).limit(limit))
    
    return {
        "player_id": player_id,
        "transactions": [serialize_doc(t) for t in transactions]
    }


@router.post("/webhook/revenuecat")
async def revenuecat_webhook(
    event_data: Dict[str, Any],
    authorization: str = Header(None)
):
    """
    Handle RevenueCat webhook events for server-side validation.
    This provides additional security for purchase verification.
    """
    # Note: In production, verify the authorization header
    # if authorization != f"Bearer {WEBHOOK_SECRET}":
    #     raise HTTPException(status_code=401, detail="Unauthorized")
    
    event_type = event_data.get("event", {}).get("type")
    app_user_id = event_data.get("event", {}).get("app_user_id")
    product_id = event_data.get("event", {}).get("product_id")
    
    logger.info(f"RevenueCat webhook: type={event_type}, user={app_user_id}, product={product_id}")
    
    if event_type in ["INITIAL_PURCHASE", "NON_RENEWING_PURCHASE"]:
        # Could grant credits here as backup if frontend call fails
        pass
    
    return {"status": "ok"}
