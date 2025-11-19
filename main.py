import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="HANDIQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Utilities -----

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def serialize(doc: dict) -> dict:
    if not doc:
        return doc
    d = doc.copy()
    _id = d.get("_id")
    if _id:
        d["id"] = str(_id)
        del d["_id"]
    # Convert datetimes to iso
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ----- Seed Data on Startup -----

WORKSHOPS = [
    {
        "title": "Scrapbooking Workshop",
        "slug": "scrapbooking",
        "description": "Create calming, memory-filled pages with premium papers and embellishments.",
        "price": 1999.0,
        "duration_minutes": 120,
        "location": "HANDIQ Studio, Indiranagar",
        "instructor": "Aisha Kapoor",
        "includes": ["All materials", "Tea & snacks", "Take-home kit"],
        "images": [
            "https://images.unsplash.com/photo-1519681393784-d120267933ba",
        ],
        "what_you_learn": ["Layering", "Composition", "Binding"],
        "materials_provided": ["Papers", "Stickers", "Glue", "Cutters"],
        "accent_color": "#B58E6D",
    },
    {
        "title": "Pottery Workshop",
        "slug": "pottery",
        "description": "Mindful clay play: hand-building, wheel basics, glazing.",
        "price": 2499.0,
        "duration_minutes": 150,
        "location": "HANDIQ Studio, Indiranagar",
        "instructor": "Raghav Menon",
        "includes": ["Clay & tools", "Firing & glazing", "Refreshments"],
        "images": [
            "https://images.unsplash.com/photo-1513342791620-8d83f05df3fc",
        ],
        "what_you_learn": ["Coiling", "Pinching", "Wheel basics"],
        "materials_provided": ["Clay", "Tools", "Apron"],
        "accent_color": "#3F6E73",
    },
    {
        "title": "Resin Art Workshop",
        "slug": "resin-art",
        "description": "Create glossy, ocean-like pours with resin and pigments.",
        "price": 2899.0,
        "duration_minutes": 120,
        "location": "HANDIQ Studio, Indiranagar",
        "instructor": "Naina Shah",
        "includes": ["Resin & pigments", "Safety gear", "Coasters to take home"],
        "images": [
            "https://images.unsplash.com/photo-1604076936065-c6e5f0505f01",
        ],
        "what_you_learn": ["Mixing", "Pouring", "Finishing"],
        "materials_provided": ["Resin", "Pigments", "Gloves", "Masks"],
        "accent_color": "#F5B21A",
    },
    {
        "title": "Embroidery Workshop",
        "slug": "embroidery",
        "description": "Slow-stitch your calm with modern embroidery techniques.",
        "price": 1799.0,
        "duration_minutes": 120,
        "location": "HANDIQ Studio, Indiranagar",
        "instructor": "Meera Iyer",
        "includes": ["Hoop, needles, threads", "Design templates", "Snacks"],
        "images": [
            "https://images.unsplash.com/photo-1600431521340-491eca880813",
        ],
        "what_you_learn": ["Backstitch", "Satin stitch", "French knots"],
        "materials_provided": ["Hoop", "Fabric", "Threads", "Needles"],
        "accent_color": "#E8DCCF",
    },
]


def ensure_seed():
    if db is None:
        return
    if db["workshop"].count_documents({}) == 0:
        for w in WORKSHOPS:
            create_document("workshop", w)
    # Seed rolling sessions for next days
    if db["session"].count_documents({}) == 0:
        now = datetime.now(timezone.utc)
        for w in WORKSHOPS:
            for d in range(1, 10):
                start = now + timedelta(days=d, hours=10)
                end = start + timedelta(minutes=w["duration_minutes"]) if "duration_minutes" in w else start + timedelta(minutes=120)
                create_document(
                    "session",
                    {
                        "workshop_slug": w["slug"],
                        "start_time": start,
                        "end_time": end,
                        "capacity": 10,
                    },
                )


@app.on_event("startup")
async def startup_event():
    ensure_seed()


# ----- Models for requests -----

class BookingRequest(BaseModel):
    workshop_slug: str
    session_id: str
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    seats: int = 1


class PaymentConfirmRequest(BaseModel):
    booking_id: str
    payment_reference: str


# ----- Public API -----

@app.get("/")
def root():
    return {"brand": "HANDIQ", "status": "ok"}


@app.get("/api/workshops")
def get_workshops():
    items = [serialize(w) for w in get_documents("workshop")]
    return {"items": items}


@app.get("/api/workshops/{slug}")
def get_workshop(slug: str):
    w = db["workshop"].find_one({"slug": slug})
    if not w:
        raise HTTPException(404, "Workshop not found")
    # fetch sessions
    now = datetime.now(timezone.utc)
    sessions = db["session"].find({"workshop_slug": slug, "start_time": {"$gte": now}}).sort("start_time", 1).limit(10)
    return {"workshop": serialize(w), "sessions": [serialize(s) for s in sessions]}


@app.get("/api/sessions/next")
def next_session():
    now = datetime.now(timezone.utc)
    s = db["session"].find({"start_time": {"$gte": now}}).sort("start_time", 1).limit(1)
    sess = list(s)
    if not sess:
        return {"item": None}
    session = sess[0]
    w = db["workshop"].find_one({"slug": session["workshop_slug"]})
    item = serialize(session)
    item["workshop_title"] = w["title"] if w else session["workshop_slug"]
    # calculate available seats
    booked = db["booking"].aggregate([
        {"$match": {"session_id": str(session["_id"]), "status": {"$in": ["pending_payment", "confirmed"]}}},
        {"$group": {"_id": None, "seats": {"$sum": "$seats"}}},
    ])
    total_booked = next(booked, {"seats": 0}).get("seats", 0)
    item["available_seats"] = max(0, session["capacity"] - total_booked)
    return {"item": item}


@app.get("/api/sessions")
def sessions_for_workshop(workshop: str):
    now = datetime.now(timezone.utc)
    sessions = db["session"].find({"workshop_slug": workshop, "start_time": {"$gte": now}}).sort("start_time", 1)
    items = [serialize(s) for s in sessions]
    return {"items": items}


@app.post("/api/bookings")
def create_booking(payload: BookingRequest):
    # Check workshop & session
    w = db["workshop"].find_one({"slug": payload.workshop_slug})
    if not w:
        raise HTTPException(404, "Workshop not found")
    s = db["session"].find_one({"_id": oid(payload.session_id)})
    if not s or s["workshop_slug"] != payload.workshop_slug:
        raise HTTPException(400, "Invalid session")
    # Seats availability
    booked = db["booking"].aggregate([
        {"$match": {"session_id": payload.session_id, "status": {"$in": ["pending_payment", "confirmed"]}}},
        {"$group": {"_id": None, "seats": {"$sum": "$seats"}}},
    ])
    total_booked = next(booked, {"seats": 0}).get("seats", 0)
    available = s["capacity"] - total_booked
    if payload.seats > available:
        raise HTTPException(400, detail=f"Only {available} seats left")

    amount = float(w.get("price", 0)) * payload.seats
    booking_id = create_document(
        "booking",
        {
            "workshop_slug": payload.workshop_slug,
            "session_id": payload.session_id,
            "customer_name": payload.customer_name,
            "customer_email": payload.customer_email,
            "customer_phone": payload.customer_phone,
            "seats": payload.seats,
            "amount": amount,
            "status": "pending_payment",
        },
    )

    # Simulate sending email notifications (stored as logs)
    create_document(
        "email",
        {
            "type": "booking_created",
            "to": payload.customer_email,
            "subject": "Your HANDIQ booking is almost complete",
            "booking_id": booking_id,
        },
    )

    return {"booking_id": booking_id, "amount": amount, "currency": "INR"}


@app.get("/api/bookings/{booking_id}")
def get_booking(booking_id: str):
    b = db["booking"].find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "Booking not found")
    # attach session & workshop
    s = db["session"].find_one({"_id": oid(b["session_id"])})
    w = db["workshop"].find_one({"slug": b["workshop_slug"]})
    data = serialize(b)
    data["session"] = serialize(s) if s else None
    data["workshop"] = serialize(w) if w else None
    return data


@app.post("/api/payments/checkout")
def initiate_payment(booking_id: str):  # simple mock to return a dummy payment token
    b = db["booking"].find_one({"_id": oid(booking_id)})
    if not b:
        raise HTTPException(404, "Booking not found")
    if b["status"] == "confirmed":
        return {"status": "already_paid"}
    token = f"PAY_{booking_id[-6:]}"
    return {"payment_token": token, "amount": b["amount"], "currency": "INR"}


@app.post("/api/payments/confirm")
def confirm_payment(payload: PaymentConfirmRequest):
    res = db["booking"].update_one({"_id": oid(payload.booking_id)}, {"$set": {"status": "confirmed", "payment_reference": payload.payment_reference}})
    if res.matched_count == 0:
        raise HTTPException(404, "Booking not found")

    # Send emails: confirmation to customer and notification to admin
    b = db["booking"].find_one({"_id": oid(payload.booking_id)})
    create_document(
        "email",
        {
            "type": "booking_confirmed",
            "to": b.get("customer_email"),
            "subject": "HANDIQ Booking Confirmed",
            "booking_id": payload.booking_id,
            "payment_reference": payload.payment_reference,
        },
    )
    create_document(
        "email",
        {
            "type": "admin_new_booking",
            "to": "admin@handiq.example",
            "subject": "New HANDIQ Booking",
            "booking_id": payload.booking_id,
        },
    )
    return {"status": "confirmed"}


@app.get("/api/reviews")
def get_reviews(workshop_slug: Optional[str] = None, limit: int = 10):
    q = {"workshop_slug": workshop_slug} if workshop_slug else {}
    items = db["review"].find(q).sort("created_at", -1).limit(limit)
    return {"items": [serialize(i) for i in items]}


@app.post("/api/reviews")
def add_review(workshop_slug: str, name: str, rating: int, comment: str):
    if rating < 1 or rating > 5:
        raise HTTPException(400, "Rating must be 1-5")
    rid = create_document("review", {"workshop_slug": workshop_slug, "name": name, "rating": rating, "comment": comment})
    return {"id": rid}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available" if db is None else "✅ Connected",
    }
    if db is not None:
        response["collections"] = db.list_collection_names()
    return response


# Simple reminder generator endpoint (simulate cron)
@app.post("/admin/send-reminders")
def send_reminders():
    now = datetime.now(timezone.utc)
    in_24h = now + timedelta(hours=24)
    sessions = db["session"].find({"start_time": {"$gte": now, "$lte": in_24h}})
    count = 0
    for s in sessions:
        bookings = db["booking"].find({"session_id": str(s["_id"]), "status": "confirmed"})
        for b in bookings:
            create_document(
                "email",
                {
                    "type": "reminder",
                    "to": b.get("customer_email"),
                    "subject": "Reminder: Your HANDIQ workshop is in 24 hours",
                    "booking_id": str(b["_id"]),
                },
            )
            count += 1
    return {"reminders_created": count}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
