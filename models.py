"""
SQLAlchemy ORM Models for AuraCRM.

Relational Schema:
───────────────────────────────────────────────────
 sales_reps         ← assigned_to leads
 departments        ← marketing spend departments
 monthly_trends     ← FK → departments (optional, or standalone)
 customers          ← core entity
 leads              ← FK → sales_reps, FK → departments (source dept)
 interactions       ← FK → customers
 purchases          ← FK → customers
 campaigns          ← standalone campaigns
 customer_campaigns ← M2M link: customers ↔ campaigns
 lead_converted     ← FK from leads → customers (nullable, set on Won)
───────────────────────────────────────────────────
"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean,
    DateTime, Date, ForeignKey, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# --- Enums ---

class LeadStatus(str, enum.Enum):
    New = "New"
    Contacted = "Contacted"
    Qualified = "Qualified"
    Proposal = "Proposal"
    Won = "Won"
    Lost = "Lost"


class CustomerStatus(str, enum.Enum):
    Active = "Active"
    Inactive = "Inactive"


class InteractionType(str, enum.Enum):
    Email = "Email"
    Call = "Call"
    Meeting = "Meeting"
    Support_Ticket = "Support Ticket"
    Purchase = "Purchase"


# --- Models ---

class SalesRep(Base):
    __tablename__ = "sales_reps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    email = Column(String(150), nullable=False, unique=True)
    role = Column(String(100), default="Sales Executive")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    leads = relationship("Lead", back_populates="sales_rep")


class Department(Base):
    """A marketing channel and its authored finance inputs.

    `budget` and `spent` are the only figures stored here -- they are finance
    facts that cannot be derived from anything else in the schema. Leads
    generated, customers acquired, revenue and ROAS used to be static columns
    on this table; they are now computed from leads/customers/purchases in
    analytics.py so they actually move when records change.
    """
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    monthly_trends = relationship("MonthlyTrend", back_populates="department")
    leads = relationship("Lead", back_populates="source_department")


class MonthlyTrend(Base):
    __tablename__ = "monthly_trends"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    month = Column(String(20), nullable=False)
    year = Column(Integer, default=2026)
    spend = Column(Float, default=0.0)
    revenue = Column(Float, default=0.0)

    # Relationships
    department = relationship("Department", back_populates="monthly_trends")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False, unique=True)   # e.g. "CUST-001"
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    phone = Column(String(30), nullable=True)
    company = Column(String(200), nullable=False)
    job_title = Column(String(150), nullable=True)
    status = Column(String(20), default="Active")
    ltv = Column(Float, default=0.0)
    acquisition_date = Column(Date, nullable=True)
    # Free-text label kept for display. `acquisition_department_id` is the
    # attribution key: it removes the need to string-match "LinkedIn" against
    # "Social Media" when rolling revenue up to a marketing channel.
    acquisition_channel = Column(String(100), nullable=True)
    acquisition_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    profile_pic = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    acquisition_department = relationship("Department")
    interactions = relationship("Interaction", back_populates="customer", order_by="Interaction.date.desc()")
    purchases = relationship("Purchase", back_populates="customer", order_by="Purchase.date.desc()")
    customer_campaigns = relationship("CustomerCampaign", back_populates="customer")
    converted_leads = relationship("Lead", back_populates="converted_customer")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False, unique=True)   # e.g. "LEAD-101"
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    company = Column(String(200), nullable=False)
    value = Column(Float, default=0.0)
    status = Column(String(20), default="New")
    score = Column(Integer, default=50)
    source = Column(String(100), nullable=True)              # human-readable source label
    source_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=True)
    converted_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sales_rep = relationship("SalesRep", back_populates="leads")
    source_department = relationship("Department", back_populates="leads")
    converted_customer = relationship("Customer", back_populates="converted_leads")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String(50), nullable=False)    # Email, Call, Meeting, Support Ticket, Purchase
    subject = Column(String(300), nullable=True)
    status = Column(String(50), nullable=True)   # Sent, Completed, Opened, Resolved, etc.
    amount = Column(Float, nullable=True)         # only for Purchase-type interactions
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="interactions")


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String(20), nullable=False, unique=True)  # e.g. "ORD-9982"
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    date = Column(Date, nullable=False)
    item = Column(String(300), nullable=False)
    amount = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="purchases")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    budget = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    department = relationship("Department")
    customer_campaigns = relationship("CustomerCampaign", back_populates="campaign")


class CustomerCampaign(Base):
    """Many-to-Many link between customers and campaigns with engagement status."""
    __tablename__ = "customer_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    status = Column(String(50), nullable=True)   # Converted, Opened, Clicked, Registered, Ignored
    engaged_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("customer_id", "campaign_id", name="uq_customer_campaign"),
    )

    # Relationships
    customer = relationship("Customer", back_populates="customer_campaigns")
    campaign = relationship("Campaign", back_populates="customer_campaigns")
