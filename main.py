"""
AuraCRM - FastAPI Backend (PostgreSQL Edition)
All data is read/written from PostgreSQL via SQLAlchemy ORM.
"""
import os
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
import random

from database import get_db, engine, Base
from models import (
    SalesRep, Department, MonthlyTrend,
    Customer, Lead, Interaction, Purchase,
)
from analytics import (
    department_performance, monthly_trend, resolve_window, window_label,
    resolve_department_id, safe_div, campaign_performance, optimize_allocation,
    DEFAULT_MAX_SPEND_MULTIPLE, MONTH_ABBR,
)

app = FastAPI(title="AuraCRM - Marketing & Customer 360 Dashboard")


# ──────────────────────────────
# Pydantic Request / Response Schemas
# ──────────────────────────────

class LeadCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=150)
    phone: str = Field("", max_length=30)
    company: str = Field(..., min_length=2, max_length=200)
    value: float = Field(..., ge=0)
    status: str = Field("New", pattern="^(New|Contacted|Qualified|Proposal|Won|Lost)$")
    score: int = Field(50, ge=0, le=100)
    source: str = Field(..., min_length=2, max_length=100)
    assigned_to: str = Field("Alex Mercer", min_length=2, max_length=100)

class LeadUpdateStatusSchema(BaseModel):
    status: str = Field(..., pattern="^(New|Contacted|Qualified|Proposal|Won|Lost)$")

class CustomerCreateSchema(BaseModel):
    name: str
    email: str
    phone: str = ""
    company: str
    job_title: str = ""
    status: str = "Active"
    ltv: float = 0.0
    acquisition_channel: str = ""


# ──────────────────────────────
# Helper: format a Customer ORM object → dict for the frontend
# ──────────────────────────────

def customer_to_dict(c: Customer, db: Session) -> dict:
    """Build the full Customer 360 dict from ORM relationships."""
    interactions = []
    for i in c.interactions:
        item = {
            "date": i.date.isoformat() if i.date else None,
            "type": i.type,
            "subject": i.subject,
            "status": i.status,
        }
        if i.amount is not None:
            item["amount"] = i.amount
        interactions.append(item)

    purchases = []
    for p in c.purchases:
        purchases.append({
            "id": p.order_code,
            "date": p.date.isoformat() if p.date else None,
            "item": p.item,
            "amount": p.amount,
        })

    campaigns = []
    for cc in c.customer_campaigns:
        campaigns.append({
            "name": cc.campaign.name if cc.campaign else "Unknown",
            "status": cc.status,
        })

    return {
        "id": c.code,
        "name": c.name,
        "email": c.email,
        "phone": c.phone or "",
        "company": c.company,
        "job_title": c.job_title or "",
        "status": c.status,
        "ltv": c.ltv,
        "acquisition_date": c.acquisition_date.isoformat() if c.acquisition_date else None,
        "acquisition_channel": c.acquisition_channel or "",
        "profile_pic": c.profile_pic or "",
        "interactions": interactions,
        "purchases": purchases,
        "campaigns": campaigns,
    }


def next_order_code(db: Session) -> str:
    """Sequential order code.

    Replaces `ORD-{random.randint(1000, 9999)}`, which wrote into a unique
    column from a 9,000-value space -- a collision became likely after a few
    hundred orders.
    """
    last = db.query(sqlfunc.max(Purchase.id)).scalar() or 0
    return f"ORD-{10000 + last + 1}"


def lead_to_dict(l: Lead) -> dict:
    return {
        "id": l.code,
        "name": l.name,
        "email": l.email,
        "phone": l.phone or "",
        "company": l.company,
        "value": l.value,
        "status": l.status,
        "score": l.score,
        "source": l.source or "",
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "assigned_to": l.sales_rep.name if l.sales_rep else "Unassigned",
    }


# ──────────────────────────────
# API: Dashboard Stats
# ──────────────────────────────

@app.get("/api/dashboard/stats")
def get_dashboard_stats(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Headline KPIs for the period, on the same basis as the marketing page.

    Revenue is *realised* purchase revenue inside the window, not lifetime LTV.
    Dividing multi-year LTV by year-to-date spend is what previously made this
    endpoint disagree with the channel table by an order of magnitude.
    """
    window = resolve_window(start, end)
    period_start, period_end = window["start"], window["end"]

    total_revenue = (
        db.query(sqlfunc.coalesce(sqlfunc.sum(Purchase.amount), 0))
        .filter(Purchase.date >= period_start, Purchase.date <= period_end)
        .scalar()
    )

    # Active Leads (not Won or Lost)
    active_leads = db.query(sqlfunc.count(Lead.id)).filter(
        Lead.status.notin_(["Won", "Lost"])
    ).scalar()

    # Total Marketing Spend
    total_spend = db.query(sqlfunc.coalesce(sqlfunc.sum(Department.spent), 0)).scalar()

    # Conversion Rate
    total_leads = db.query(sqlfunc.count(Lead.id)).scalar()
    won_leads_count = db.query(sqlfunc.count(Lead.id)).filter(Lead.status == "Won").scalar()
    conversion_rate = safe_div(won_leads_count * 100, total_leads)

    # Blended ROAS -- all realised revenue per AED spent. The marketing page
    # also reports attributed ROAS, which counts only channel-traceable revenue;
    # the two are named apart so they are never mistaken for one another.
    roas = safe_div(float(total_revenue), float(total_spend))

    return {
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "label": window_label(period_start, period_end),
        },
        "total_revenue": round(float(total_revenue), 2),
        "active_leads": active_leads,
        "total_spend": round(float(total_spend), 2),
        "conversion_rate": round(conversion_rate, 1) if conversion_rate is not None else None,
        "roas": round(roas, 2) if roas is not None else None,
    }


# ──────────────────────────────
# API: Marketing Spends
# ──────────────────────────────

@app.get("/api/marketing/spends")
def get_marketing_spends(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Channel performance derived from leads, customers and purchases.

    Every metric except `budget` and `spent` is computed at query time, so
    adding a lead or converting a customer moves these numbers immediately.
    """
    window = resolve_window(start, end)
    period_start, period_end = window["start"], window["end"]

    performance = department_performance(db, period_start, period_end)

    # Authored monthly spend, keyed by (year, month) for the trend series.
    month_index = {name: i + 1 for i, name in enumerate(MONTH_ABBR)}
    authored_spend = {}
    for t in db.query(MonthlyTrend).all():
        month_num = month_index.get((t.month or "")[:3].title())
        if month_num:
            key = (t.year or period_end.year, month_num)
            authored_spend[key] = authored_spend.get(key, 0.0) + float(t.spend or 0.0)

    return {
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "label": window_label(period_start, period_end),
        },
        "departments": performance["departments"],
        "totals": performance["totals"],
        "monthly_trend": monthly_trend(db, period_start, period_end, authored_spend),
    }


@app.get("/api/marketing/campaigns")
def get_campaign_performance(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Campaign-level drilldown beneath the channel view.

    Engagement counts come from customer_campaigns; revenue is credited only to
    customers whose engagement reached "Converted".
    """
    window = resolve_window(start, end)
    period_start, period_end = window["start"], window["end"]

    return {
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "label": window_label(period_start, period_end),
        },
        "campaigns": campaign_performance(db, period_start, period_end),
    }


@app.get("/api/marketing/optimize")
def get_optimal_allocation(
    budget: Optional[float] = None,
    max_spend_multiple: float = DEFAULT_MAX_SPEND_MULTIPLE,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Recommend a budget split that maximises projected revenue.

    Defaults to reallocating the current total spend, which answers the useful
    question: what would the same money have returned, spent differently?
    """
    if max_spend_multiple < 1.0:
        raise HTTPException(
            status_code=422,
            detail="max_spend_multiple must be at least 1.0",
        )

    window = resolve_window(start, end)
    performance = department_performance(db, window["start"], window["end"])

    channels = [
        {
            "name": d["name"],
            "spent": d["spent"],
            "lead_k": d["response"]["lead_k"],
            "revenue_k": d["response"]["revenue_k"],
        }
        for d in performance["departments"]
    ]

    total_budget = budget if budget is not None else performance["totals"]["spent"]
    if total_budget < 0:
        raise HTTPException(status_code=422, detail="budget must not be negative")

    return optimize_allocation(channels, total_budget, max_spend_multiple)


# ──────────────────────────────
# API: Customers (Customer 360)
# ──────────────────────────────

@app.get("/api/customers")
def get_customers(search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Customer)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(search_pattern)) |
            (Customer.company.ilike(search_pattern)) |
            (Customer.email.ilike(search_pattern))
        )
    customers = query.order_by(Customer.ltv.desc()).all()
    return [customer_to_dict(c, db) for c in customers]


@app.get("/api/customers/{customer_code}")
def get_customer_details(customer_code: str, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.code == customer_code).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer_to_dict(c, db)


@app.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreateSchema, db: Session = Depends(get_db)):
    # Generate next code
    max_id = db.query(sqlfunc.max(Customer.id)).scalar() or 0
    new_code = f"CUST-{max_id + 1:03d}"

    pics = [
        "photo-1494790108377-be9c29b29330",
        "photo-1507003211169-0a1dd7228f2d",
        "photo-1573496359142-b8d87734a5a2",
        "photo-1500648767791-00dcc994a43e",
        "photo-1567532939604-b6b5b0db2604",
    ]
    # Resolve the channel label to a department so this customer's revenue rolls
    # up into channel ROAS instead of landing in "unattributed".
    dept_ids_by_name = {name: did for name, did in db.query(Department.name, Department.id).all()}
    acquisition_department_id = resolve_department_id(payload.acquisition_channel, dept_ids_by_name)

    new_customer = Customer(
        code=new_code,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        job_title=payload.job_title,
        status=payload.status,
        ltv=payload.ltv,
        acquisition_date=datetime.now().date(),
        acquisition_channel=payload.acquisition_channel,
        acquisition_department_id=acquisition_department_id,
        profile_pic=f"https://images.unsplash.com/{random.choice(pics)}?w=150",
    )
    db.add(new_customer)
    db.flush()

    # Add welcome interaction
    db.add(Interaction(
        customer_id=new_customer.id,
        date=datetime.now().date(),
        type="Email",
        subject="Welcome onboarding email sent",
        status="Sent",
    ))
    db.commit()
    db.refresh(new_customer)
    return customer_to_dict(new_customer, db)


# ──────────────────────────────
# API: Leads
# ──────────────────────────────

@app.get("/api/leads")
def get_leads(db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.id).all()
    return [lead_to_dict(l) for l in leads]


@app.post("/api/leads", status_code=status.HTTP_201_CREATED)
def create_lead(payload: LeadCreateSchema, db: Session = Depends(get_db)):
    # Generate next code
    max_id = db.query(sqlfunc.max(Lead.id)).scalar() or 0
    new_code = f"LEAD-{max_id + 101}"

    # Find the sales rep
    rep = db.query(SalesRep).filter(SalesRep.name == payload.assigned_to).first()

    # Resolve the source label to a department through the shared alias table,
    # so lead sourcing and revenue attribution always agree on the vocabulary.
    dept_ids_by_name = {name: did for name, did in db.query(Department.name, Department.id).all()}
    source_department_id = resolve_department_id(payload.source, dept_ids_by_name)

    new_lead = Lead(
        code=new_code,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        value=payload.value,
        status=payload.status,
        score=payload.score,
        source=payload.source,
        source_department_id=source_department_id,
        assigned_to_id=rep.id if rep else None,
    )
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)
    return lead_to_dict(new_lead)


@app.patch("/api/leads/{lead_code}/status")
def update_lead_status(lead_code: str, payload: LeadUpdateStatusSchema, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.code == lead_code).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_status = lead.status
    lead.status = payload.status

    # If Won → auto-convert to Customer
    if payload.status == "Won" and old_status != "Won":
        existing_customer = db.query(Customer).filter(
            sqlfunc.lower(Customer.email) == lead.email.lower()
        ).first()

        if not existing_customer:
            max_cust_id = db.query(sqlfunc.max(Customer.id)).scalar() or 0
            new_code = f"CUST-{max_cust_id + 1:03d}"

            # Record the canonical department name where the source resolves to
            # one, so converted customers and seeded customers share a single
            # channel vocabulary instead of "LinkedIn" vs "Social Media".
            acquisition_channel = lead.source
            if lead.source_department_id:
                dept = db.query(Department).get(lead.source_department_id)
                if dept:
                    acquisition_channel = dept.name

            new_customer = Customer(
                code=new_code,
                name=lead.name,
                email=lead.email,
                phone=lead.phone,
                company=lead.company,
                job_title="Decision Maker",
                status="Active",
                ltv=lead.value,
                acquisition_date=datetime.now().date(),
                acquisition_channel=acquisition_channel,
                acquisition_department_id=lead.source_department_id,
                profile_pic="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
            )
            db.add(new_customer)
            db.flush()

            # Link the lead to the new customer
            lead.converted_customer_id = new_customer.id

            # Create initial interaction
            db.add(Interaction(
                customer_id=new_customer.id,
                date=datetime.now().date(),
                type="Purchase",
                subject=f"Initial purchase from converted lead {lead_code}",
                status="Completed",
                amount=lead.value,
            ))

            # Create initial purchase
            db.add(Purchase(
                order_code=next_order_code(db),
                customer_id=new_customer.id,
                date=datetime.now().date(),
                item="Initial Purchase",
                amount=lead.value,
            ))

            # No campaign is minted here. Conversion used to create a
            # zero-budget "Lead Source: ..." campaign per won lead, which
            # carried no marketing meaning and swamped campaign reporting with
            # single-customer rows. Channel attribution is already recorded on
            # the customer via acquisition_department_id; campaigns are created
            # by marketing, not as a side effect of a sale.
        else:
            lead.converted_customer_id = existing_customer.id

    db.commit()
    db.refresh(lead)
    return lead_to_dict(lead)


@app.delete("/api/leads/{lead_code}")
def delete_lead(lead_code: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.code == lead_code).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()
    return {"detail": "Lead deleted successfully"}


# ──────────────────────────────
# Serve Static Files & Root
# ──────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("HOST", "127.0.0.1"), port=8000, reload=True)
