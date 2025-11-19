import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApprovalItemIn(BaseModel):
    title: str = Field(..., description="Item title")
    description: Optional[str] = Field(None, description="Short description")
    requester: str = Field(..., description="Person who requested")
    amount: Optional[float] = Field(None, ge=0, description="Optional amount")


# Helpers

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def serialize_item(doc: dict) -> dict:
    if not doc:
        return None
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title"),
        "description": doc.get("description"),
        "requester": doc.get("requester"),
        "amount": doc.get("amount"),
        "status": doc.get("status", "pending"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@app.get("/")
def read_root():
    return {"message": "Approvals API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# API: Approvals
@app.get("/api/approvals")
def list_approvals(status: Optional[str] = Query("pending", pattern="^(pending|approved|rejected)$")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    filter_dict = {"status": status} if status else {}
    docs = db["approvalitem"].find(filter_dict).sort("created_at", -1)
    return [serialize_item(d) for d in docs]


@app.post("/api/approvals", status_code=201)
def create_approval(item: ApprovalItemIn):
    # default status pending
    data = item.model_dump()
    data["status"] = "pending"
    inserted_id = create_document("approvalitem", data)
    doc = db["approvalitem"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_item(doc)


@app.post("/api/approvals/{item_id}/approve")
def approve_item(item_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    res = db["approvalitem"].update_one({"_id": oid(item_id)}, {"$set": {"status": "approved", "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    doc = db["approvalitem"].find_one({"_id": oid(item_id)})
    return serialize_item(doc)


@app.post("/api/approvals/{item_id}/reject")
def reject_item(item_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    res = db["approvalitem"].update_one({"_id": oid(item_id)}, {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    doc = db["approvalitem"].find_one({"_id": oid(item_id)})
    return serialize_item(doc)


@app.post("/api/approvals/seed")
def seed_data():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    count = db["approvalitem"].count_documents({})
    if count > 0:
        return {"inserted": 0, "message": "Data already present"}
    samples = [
        {"title": "Marketing Spend Q1", "description": "Campaign boost on socials", "requester": "Ava", "amount": 1200.0, "status": "pending"},
        {"title": "Laptop Purchase", "description": "Designer MacBook Pro", "requester": "Leo", "amount": 2499.0, "status": "pending"},
        {"title": "SaaS Renewal", "description": "Analytics tool annual plan", "requester": "Mia", "amount": 780.0, "status": "pending"},
        {"title": "Team Offsite", "description": "Venue deposit", "requester": "Noah", "amount": 1500.0, "status": "pending"},
    ]
    for s in samples:
        create_document("approvalitem", s)
    return {"inserted": len(samples)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
