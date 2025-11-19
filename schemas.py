"""
Database Schemas for HANDIQ Creative Workshops

Each Pydantic model maps to a MongoDB collection (lowercased class name).
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime


class Workshop(BaseModel):
    title: str
    slug: str = Field(..., description="URL-friendly unique identifier")
    description: str
    price: float = Field(..., ge=0)
    duration_minutes: int = Field(..., ge=30)
    location: str
    instructor: str
    includes: List[str] = []
    images: List[str] = []
    what_you_learn: List[str] = []
    materials_provided: List[str] = []
    accent_color: Optional[str] = None


class Session(BaseModel):
    workshop_slug: str
    start_time: datetime
    end_time: datetime
    capacity: int = Field(..., ge=1)


class Booking(BaseModel):
    workshop_slug: str
    session_id: str
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    seats: int = Field(1, ge=1, le=10)
    amount: float
    status: str = Field("pending_payment", description="pending_payment | confirmed | cancelled | failed")
    payment_reference: Optional[str] = None


class Review(BaseModel):
    workshop_slug: str
    name: str
    rating: int = Field(..., ge=1, le=5)
    comment: str


class Voucher(BaseModel):
    code: str
    value: float = Field(..., ge=0)
    currency: str = "INR"
    is_active: bool = True


# Example schemas kept for reference by the database viewer (not used by the app)
class User(BaseModel):
    name: str
    email: EmailStr
    address: str
    age: Optional[int] = Field(None, ge=0, le=120)
    is_active: bool = True


class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    category: str
    in_stock: bool = True
