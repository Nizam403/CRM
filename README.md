# AuraCRM - Web-based CRM & Marketing Analytics Dashboard

A premium, glassmorphic CRM and Marketing Analytics Dashboard built with **FastAPI (Python)** and a modern **HTML5/CSS3/JavaScript** frontend.

## Features

1. **Dashboard Overview**:
   - Real-time KPI cards (Total Revenue, Active Leads, Marketing Spend, Conversion Rate, ROI).
   - Interactive charts (Revenue vs. Spend monthly trend, Lead Conversion Funnel).
   - Quick tables for High-Score Leads and Top Customers.

2. **Customer 360**:
   - Comprehensive customer profile view.
   - Searchable customer list.
   - Detailed interaction timeline (Emails, Calls, Support tickets, Purchases).
   - Purchase history and targeted marketing campaigns.

3. **Leads Pipeline**:
   - Interactive Kanban Board with stages: *New, Contacted, Qualified, Proposal, Won, Lost*.
   - Drag-and-drop cards to update lead status.
   - Double-click cards for quick status updates.
   - Automatic conversion of Won leads into Customer 360 profiles.
   - Add new leads via a beautiful modal.

4. **Marketing Department Analysis**:
   - Channel performance derived from live records — budget, spend, utilisation, pacing,
     leads, customers acquired, CPL, CAC, win rate, revenue and ROAS.
   - **Campaign drilldown** beneath each channel, with the engagement funnel
     (ignored → opened → clicked → registered → converted), conversion rate,
     cost per conversion and campaign-level ROAS.
   - **Budget Optimization Simulator**: sliders project leads and revenue through a
     diminishing-returns curve fitted to each channel's own history.
   - **Allocation recommender**: computes the split of a given budget that maximises
     projected revenue, capped so no channel is handed more than it could absorb.

### How the marketing numbers are calculated

Only `Department.budget` and `Department.spent` are stored — they are finance inputs
with no other source. Everything else is computed per request in `analytics.py`, so
adding a lead or converting a customer moves the figures immediately.

- **One definition of return.** `ROAS = revenue / spend`, a multiplier, everywhere.
  `attributed_roas` counts only channel-traceable revenue (what the channel rows sum to);
  `blended_roas` counts all realised revenue including referral and direct.
- **Revenue and spend share a window.** Revenue is *realised purchases* inside the
  period, not lifetime LTV. Both endpoints accept `?start=&end=` and default to
  year-to-date, matching the authored spend figure.
- **Attribution** uses `Customer.acquisition_department_id`. Customers predating that
  column fall back to matching `acquisition_channel` against the alias table in
  `analytics.CHANNEL_ALIASES`, which is also what maps a lead source ("LinkedIn") to
  its department ("Social Media").
- **Undefined ratios return `null`**, rendered as an em dash — never `Infinity` or `NaN`.

5. **Premium Design**:
   - Sleek glassmorphism theme.
   - Dynamic Dark/Light mode toggle.
   - Fully responsive layout.

## How to Run

1. **Activate Virtual Environment**:
   ```bash
   source venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up the database**:

   For a **new** database, seed it (this drops and recreates every table):
   ```bash
   python seed.py
   ```

   For an **existing** database with data you want to keep, migrate in place
   instead — it is idempotent and never drops a row:
   ```bash
   python migrate.py
   ```

4. **Run the Server**:
   ```bash
   uvicorn main:app --reload
   ```

5. **Access the Dashboard**:
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/dashboard/stats` | Headline KPIs for the period |
| `GET /api/marketing/spends` | Channel performance, totals and monthly trend |
| `GET /api/marketing/campaigns` | Campaign-level engagement and revenue |
| `GET /api/marketing/optimize` | Recommended budget allocation |
| `GET /api/customers` · `GET /api/customers/{code}` · `POST /api/customers` | Customer 360 |
| `GET /api/leads` · `POST /api/leads` · `PATCH /api/leads/{code}/status` · `DELETE /api/leads/{code}` | Pipeline |

The marketing endpoints accept `?start=YYYY-MM-DD&end=YYYY-MM-DD`.
`/api/marketing/optimize` also takes `?budget=` (defaults to current total spend) and
`?max_spend_multiple=` (defaults to `2.0`).
