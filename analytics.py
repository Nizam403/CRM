"""
Marketing attribution and channel performance analytics for AuraCRM.

ONE definition of channel return is used across the whole application:

    ROAS = attributed revenue / spend        (a multiplier, e.g. "3.1x")

Revenue and spend are always held to the SAME window. `Department.spent` is an
authored year-to-date figure with no date column, so the default window is
year-to-date, and revenue is the sum of *realised purchases* inside that window
-- not lifetime LTV, which accumulates over several years and badly inflates any
ratio it is divided into.

Attribution resolves a customer to a marketing department in two passes:

  1. First-party: the customer was converted from a lead, so that lead's
     `source_department_id` is authoritative.
  2. Fallback: match `Customer.acquisition_channel` against the alias table
     below. Seeded customers carry department names ("Social Media") while
     lead conversion writes lead-source labels ("LinkedIn"); the alias table
     is what makes those two vocabularies agree.

The fallback exists because `acquisition_channel` is free text with no foreign
key. Adding `Customer.acquisition_department_id` removes the need for it.
"""
from datetime import date
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from models import Department, Lead, Customer, Purchase, Campaign, CustomerCampaign


# ──────────────────────────────
# Channel vocabulary
# ──────────────────────────────

# Department name → every label that should resolve to it. Lead sources and
# customer acquisition channels are both matched against this, case-insensitively.
CHANNEL_ALIASES: Dict[str, tuple] = {
    "Social Media":         ("social media", "linkedin", "facebook", "instagram", "twitter"),
    "Search Engine (PPC)":  ("search engine (ppc)", "google", "ppc", "search", "adwords"),
    "Email Marketing":      ("email marketing", "email", "newsletter"),
    "Events & Webinars":    ("events & webinars", "event", "events", "webinar", "conference"),
    "Content Marketing":    ("content marketing", "content", "blog", "whitepaper"),
    "Influencer Marketing": ("influencer marketing", "influencer"),
}

# Labels that are legitimately not paid marketing channels. These are attributed
# to no department rather than being silently dropped or mis-assigned.
UNATTRIBUTED_CHANNELS = ("referral", "word of mouth", "direct", "organic", "")

_ALIAS_TO_DEPT_NAME = {
    alias: dept_name
    for dept_name, aliases in CHANNEL_ALIASES.items()
    for alias in aliases
}

MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def resolve_department_id(label: Optional[str], dept_ids_by_name: Dict[str, int]) -> Optional[int]:
    """Map a free-text channel/source label to a department id, or None."""
    if not label:
        return None
    key = label.strip().lower()
    if key in UNATTRIBUTED_CHANNELS:
        return None
    dept_name = _ALIAS_TO_DEPT_NAME.get(key)
    return dept_ids_by_name.get(dept_name) if dept_name else None


# ──────────────────────────────
# Math helpers
# ──────────────────────────────

def safe_div(numerator, denominator) -> Optional[float]:
    """Divide, returning None (never Infinity or NaN) when undefined.

    The frontend renders None as an em dash. Returning Infinity here is what
    previously produced "AED ∞" in the cost-per-lead column and silently
    erased channels from the budget simulator's forecast.
    """
    if not denominator:
        return None
    return numerator / denominator


def _pct(numerator, denominator) -> Optional[float]:
    ratio = safe_div(numerator, denominator)
    return round(ratio * 100, 1) if ratio is not None else None


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None else None


def elapsed_share_of_year(as_of: date) -> float:
    """Fraction of the calendar year gone by, used for budget pacing."""
    start = date(as_of.year, 1, 1)
    days_in_year = (date(as_of.year + 1, 1, 1) - start).days
    return ((as_of - start).days + 1) / days_in_year


def _pace_index(spent: float, budget: float, elapsed: float) -> Optional[float]:
    """Spend rate against time elapsed. 1.0 is exactly on plan, >1 is ahead.

    A channel at 92% of budget in September is pacing to overspend; one at 92%
    in December is on plan. Raw utilisation cannot tell those apart.
    """
    utilisation = safe_div(spent, budget)
    if utilisation is None or not elapsed:
        return None
    return utilisation / elapsed


# ──────────────────────────────
# Window resolution
# ──────────────────────────────

def resolve_window(start: Optional[date], end: Optional[date]) -> Dict[str, date]:
    """Default to year-to-date, matching the authored `Department.spent` figure."""
    today = date.today()
    resolved_end = end or today
    resolved_start = start or date(resolved_end.year, 1, 1)
    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start
    return {"start": resolved_start, "end": resolved_end}


def window_label(start: date, end: date) -> str:
    if start == date(end.year, 1, 1) and end == date.today():
        return f"YTD {end.year}"
    return f"{start.isoformat()} to {end.isoformat()}"


# ──────────────────────────────
# Attribution
# ──────────────────────────────

def build_customer_attribution(db: Session, dept_ids_by_name: Dict[str, int]) -> Dict[int, Optional[int]]:
    """Return {customer_id: department_id or None}.

    `Customer.acquisition_department_id` is the attribution key and is trusted
    whenever it is set. The label and lead-source passes below only cover rows
    written before that column existed; `migrate.py` backfills them, so in a
    migrated database they are no-ops.
    """
    attribution: Dict[int, Optional[int]] = {}

    rows = db.query(
        Customer.id, Customer.acquisition_channel, Customer.acquisition_department_id
    ).all()
    legacy: List[int] = []
    for cust_id, channel, dept_id in rows:
        if dept_id is not None:
            attribution[cust_id] = dept_id
        else:
            attribution[cust_id] = resolve_department_id(channel, dept_ids_by_name)
            legacy.append(cust_id)

    # First-party lead source wins, but only for rows the FK has not settled.
    if legacy:
        converted = (
            db.query(Lead.converted_customer_id, Lead.source_department_id)
            .filter(Lead.converted_customer_id.in_(legacy))
            .all()
        )
        for cust_id, dept_id in converted:
            if dept_id is not None:
                attribution[cust_id] = dept_id

    return attribution


def _revenue_by_customer(db: Session, start: date, end: date) -> Dict[int, float]:
    """Realised purchase revenue per customer inside the window."""
    rows = (
        db.query(Purchase.customer_id, Purchase.amount)
        .filter(Purchase.date >= start, Purchase.date <= end)
        .all()
    )
    revenue: Dict[int, float] = {}
    for cust_id, amount in rows:
        revenue[cust_id] = revenue.get(cust_id, 0.0) + float(amount or 0.0)
    return revenue


# ──────────────────────────────
# Department performance
# ──────────────────────────────

def department_performance(db: Session, start: date, end: date) -> Dict:
    """Derive every channel metric from the relational data.

    Only `budget` and `spent` are read from the Department row -- those are
    authored finance inputs. Lead counts, acquired customers, revenue, CPL,
    CAC, win rate and ROAS are all computed from leads, customers and
    purchases, so they move when the underlying records move.
    """
    departments = db.query(Department).order_by(Department.name).all()
    dept_ids_by_name = {d.name: d.id for d in departments}

    attribution = build_customer_attribution(db, dept_ids_by_name)
    revenue_by_customer = _revenue_by_customer(db, start, end)

    # Seed each department's accumulator.
    acc = {
        d.id: {"leads": 0, "score_total": 0, "customers": set(), "revenue": 0.0}
        for d in departments
    }

    # Leads sourced to each department inside the window.
    lead_rows = db.query(
        Lead.source_department_id, Lead.score, Lead.created_at
    ).all()
    for dept_id, score, created_at in lead_rows:
        if dept_id not in acc:
            continue
        created_on = created_at.date() if created_at else None
        if created_on and not (start <= created_on <= end):
            continue
        acc[dept_id]["leads"] += 1
        acc[dept_id]["score_total"] += score or 0

    # Customers and their realised revenue, attributed to a department.
    for cust_id, dept_id in attribution.items():
        if dept_id not in acc:
            continue
        acc[dept_id]["customers"].add(cust_id)
        acc[dept_id]["revenue"] += revenue_by_customer.get(cust_id, 0.0)

    elapsed = elapsed_share_of_year(min(end, date.today()))

    rows: List[Dict] = []
    for d in departments:
        a = acc[d.id]
        leads = a["leads"]
        customers = len(a["customers"])
        revenue = a["revenue"]
        spent = float(d.spent or 0.0)

        rows.append({
            "name": d.name,
            "budget": float(d.budget or 0.0),
            "spent": spent,
            "utilization": _pct(d.spent, d.budget),
            "pace_index": _round(_pace_index(spent, float(d.budget or 0.0), elapsed)),
            "leads_generated": leads,
            "customers_acquired": customers,
            "cpl": _round(safe_div(d.spent, leads)),
            "cac": _round(safe_div(d.spent, customers)),
            "win_rate": _pct(customers, leads),
            "revenue": round(revenue, 2),
            "roas": _round(safe_div(revenue, d.spent)),
            "avg_lead_score": _round(safe_div(a["score_total"], leads), 1),
            # Diminishing-returns coefficients, calibrated so the curve passes
            # through this channel's observed (spend, leads) and (spend, revenue).
            "response": response_coefficients(spent, leads, revenue),
        })

    total_budget = sum(r["budget"] for r in rows)
    total_spent = sum(r["spent"] for r in rows)
    total_leads = sum(r["leads_generated"] for r in rows)
    total_customers = sum(r["customers_acquired"] for r in rows)
    total_revenue = sum(r["revenue"] for r in rows)

    # Revenue that landed in the window but resolved to no paid channel
    # (referrals, direct, unknown labels). Surfaced rather than hidden so the
    # channel rows and the company total visibly reconcile.
    attributed_customer_ids = {
        cust_id for cust_id, dept_id in attribution.items() if dept_id in acc
    }
    unattributed_revenue = sum(
        amount for cust_id, amount in revenue_by_customer.items()
        if cust_id not in attributed_customer_ids
    )

    return {
        "departments": rows,
        "totals": {
            "budget": round(total_budget, 2),
            "spent": round(total_spent, 2),
            "leads_generated": total_leads,
            "customers_acquired": total_customers,
            "attributed_revenue": round(total_revenue, 2),
            "unattributed_revenue": round(unattributed_revenue, 2),
            "total_revenue": round(total_revenue + unattributed_revenue, 2),
            "utilization": _pct(total_spent, total_budget),
            "pace_index": _round(_pace_index(total_spent, total_budget, elapsed)),
            "year_elapsed": _pct(elapsed, 1),
            "cpl": _round(safe_div(total_spent, total_leads)),
            "cac": _round(safe_div(total_spent, total_customers)),
            # Two ROAS figures, named apart on purpose. `attributed` counts only
            # revenue traceable to a paid channel and is what the channel rows
            # sum to. `blended` counts all realised revenue, including referral
            # and direct, and is the company-level number on the dashboard.
            "attributed_roas": _round(safe_div(total_revenue, total_spent)),
            "blended_roas": _round(safe_div(total_revenue + unattributed_revenue, total_spent)),
        },
    }


# ──────────────────────────────
# Channel response model
# ──────────────────────────────
#
# Marketing channels saturate: the tenth thousand dirhams buys fewer leads than
# the first. The old simulator modelled `revenue = budget x roas`, which is
# linear and unbounded, so its advice was always "move the entire budget to the
# single highest-ROAS channel" -- an artefact of the model, not a finding.
#
# We use a square-root response curve instead:
#
#     y(x) = k * sqrt(x)
#
# calibrated per channel so the curve passes exactly through what that channel
# actually did: k = y_observed / sqrt(x_observed). It reproduces today's numbers
# at today's spend, and concedes diminishing returns in both directions.

DEFAULT_MAX_SPEND_MULTIPLE = 2.0   # no channel may be given more than 2x its current spend


def response_coefficients(spent: float, leads: int, revenue: float) -> Dict[str, Optional[float]]:
    """Calibrate y = k*sqrt(x) for leads and revenue against observed spend."""
    if not spent or spent <= 0:
        return {"lead_k": None, "revenue_k": None}
    root = spent ** 0.5
    return {
        "lead_k": round(leads / root, 6) if leads else 0.0,
        "revenue_k": round(revenue / root, 6) if revenue else 0.0,
    }


def project_channel(coefficient: Optional[float], budget: float) -> float:
    """Projected output for a channel at a given budget under the curve."""
    if not coefficient or budget <= 0:
        return 0.0
    return coefficient * (budget ** 0.5)


def optimize_allocation(
    channels: List[Dict],
    total_budget: float,
    max_spend_multiple: float = DEFAULT_MAX_SPEND_MULTIPLE,
) -> Dict:
    """Allocate `total_budget` across channels to maximise projected revenue.

    Maximising sum(k_i * sqrt(x_i)) subject to sum(x_i) = B has a closed-form
    solution: the marginal return k_i / (2*sqrt(x_i)) must be equal across all
    funded channels, which gives x_i proportional to k_i^2.

    Channels are then capped at `max_spend_multiple` times their current spend
    and the surplus is redistributed over the remaining ones, because an
    uncapped optimum routinely recommends a 10x increase that no channel could
    actually absorb in a year.
    """
    funded = [c for c in channels if (c.get("revenue_k") or 0) > 0]
    if not funded or total_budget <= 0:
        return {
            "feasible": False,
            "reason": "No channel has enough history to model a response curve.",
            "allocations": [],
        }

    caps = {
        c["name"]: (c["spent"] * max_spend_multiple if c["spent"] > 0 else total_budget)
        for c in funded
    }
    weights = {c["name"]: (c["revenue_k"] ** 2) for c in funded}

    allocation: Dict[str, float] = {}
    remaining_budget = float(total_budget)
    pool = [c["name"] for c in funded]

    # Water-filling: allocate by weight, freeze anything that hits its cap,
    # then redistribute what is left over the channels still below cap.
    while pool:
        weight_sum = sum(weights[n] for n in pool)
        if weight_sum <= 0:
            break
        overflowed = []
        for name in pool:
            share = remaining_budget * weights[name] / weight_sum
            if share > caps[name]:
                overflowed.append(name)
        if not overflowed:
            for name in pool:
                allocation[name] = remaining_budget * weights[name] / weight_sum
            break
        for name in overflowed:
            allocation[name] = caps[name]
            remaining_budget -= caps[name]
            pool.remove(name)
        if remaining_budget <= 0:
            break

    # Anything the caps left unspent cannot be deployed productively.
    unallocated = round(total_budget - sum(allocation.values()), 2)

    rows = []
    for c in channels:
        recommended = allocation.get(c["name"], 0.0)
        current = c["spent"]
        rows.append({
            "name": c["name"],
            "current": round(current, 2),
            "recommended": round(recommended, 2),
            "delta": round(recommended - current, 2),
            "delta_pct": _pct(recommended - current, current),
            "projected_revenue": round(project_channel(c.get("revenue_k"), recommended), 2),
            "projected_leads": round(project_channel(c.get("lead_k"), recommended), 1),
            "capped": round(recommended, 2) >= round(caps.get(c["name"], 0.0), 2) > 0,
        })

    current_revenue = sum(project_channel(c.get("revenue_k"), c["spent"]) for c in channels)
    optimised_revenue = sum(r["projected_revenue"] for r in rows)
    current_leads = sum(project_channel(c.get("lead_k"), c["spent"]) for c in channels)
    optimised_leads = sum(r["projected_leads"] for r in rows)

    return {
        "feasible": True,
        "total_budget": round(float(total_budget), 2),
        "unallocated": max(unallocated, 0.0),
        "max_spend_multiple": max_spend_multiple,
        "allocations": rows,
        "current_projection": {
            "revenue": round(current_revenue, 2),
            "leads": round(current_leads, 1),
        },
        "optimised_projection": {
            "revenue": round(optimised_revenue, 2),
            "leads": round(optimised_leads, 1),
        },
        "revenue_uplift": round(optimised_revenue - current_revenue, 2),
        "revenue_uplift_pct": _pct(optimised_revenue - current_revenue, current_revenue),
    }


# ──────────────────────────────
# Campaign performance
# ──────────────────────────────

# Engagement statuses on customer_campaigns, ordered from weakest to strongest.
ENGAGEMENT_STATUSES = ("Ignored", "Opened", "Clicked", "Registered", "Converted")


def campaign_performance(db: Session, start: date, end: date) -> List[Dict]:
    """Per-campaign engagement and revenue, drilled down from the channel view.

    Revenue is counted only for customers whose engagement reached "Converted",
    so an opened newsletter does not claim credit for a deal.

    Caveat: this is last-touch at the campaign level. A customer marked
    "Converted" on two campaigns credits full revenue to both, so campaign
    revenue can sum above channel revenue. Splitting credit across touchpoints
    needs a weighting rule the business has to choose.
    """
    revenue_by_customer = _revenue_by_customer(db, start, end)

    campaigns = db.query(Campaign).order_by(Campaign.name).all()
    dept_names = {d.id: d.name for d in db.query(Department).all()}

    links = db.query(
        CustomerCampaign.campaign_id, CustomerCampaign.customer_id, CustomerCampaign.status
    ).all()

    by_campaign: Dict[int, List] = {}
    for campaign_id, customer_id, status in links:
        by_campaign.setdefault(campaign_id, []).append((customer_id, status))

    rows: List[Dict] = []
    for c in campaigns:
        members = by_campaign.get(c.id, [])
        engagement = {status: 0 for status in ENGAGEMENT_STATUSES}
        converted_customers = []
        for customer_id, status in members:
            if status in engagement:
                engagement[status] += 1
            if status == "Converted":
                converted_customers.append(customer_id)

        revenue = sum(revenue_by_customer.get(cid, 0.0) for cid in converted_customers)
        budget = float(c.budget or 0.0)
        reached = len(members)

        rows.append({
            "name": c.name,
            "department": dept_names.get(c.department_id) or "Unassigned",
            "budget": budget,
            "customers_reached": reached,
            "engagement": engagement,
            "conversions": len(converted_customers),
            "conversion_rate": _pct(len(converted_customers), reached),
            "revenue": round(revenue, 2),
            "roas": _round(safe_div(revenue, budget)),
            "cost_per_conversion": _round(safe_div(budget, len(converted_customers))),
        })

    rows.sort(key=lambda r: (r["roas"] is None, -(r["roas"] or 0)))
    return rows


# ──────────────────────────────
# Monthly trend
# ──────────────────────────────

def monthly_trend(db: Session, start: date, end: date, authored_spend: Dict) -> List[Dict]:
    """Monthly spend vs revenue, with revenue derived from realised purchases.

    Spend stays authored: `Department.spent` and `MonthlyTrend.spend` are the
    only record of what was actually paid out, and neither carries enough
    date detail to derive a monthly figure from transactions.
    """
    rows = (
        db.query(Purchase.date, Purchase.amount)
        .filter(Purchase.date >= start, Purchase.date <= end)
        .all()
    )
    revenue_by_month: Dict[tuple, float] = {}
    for purchase_date, amount in rows:
        if not purchase_date:
            continue
        key = (purchase_date.year, purchase_date.month)
        revenue_by_month[key] = revenue_by_month.get(key, 0.0) + float(amount or 0.0)

    trend: List[Dict] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        key = (year, month)
        trend.append({
            "month": MONTH_ABBR[month - 1],
            "year": year,
            "spend": round(authored_spend.get(key, 0.0), 2),
            "revenue": round(revenue_by_month.get(key, 0.0), 2),
        })
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    return trend
