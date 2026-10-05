"""
Seed script: Creates all tables and populates them with realistic data.
Run once: python seed.py
"""
from datetime import datetime, timedelta, date
from database import engine, SessionLocal, Base
from models import (
    SalesRep, Department, MonthlyTrend,
    Customer, Lead, Interaction, Purchase,
    Campaign, CustomerCampaign
)


def days_ago(n: int) -> date:
    return (datetime.now() - timedelta(days=n)).date()


def seed():
    # Create all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ========================
        # 1. SALES REPS
        # ========================
        rep_alex = SalesRep(name="Alex Mercer", email="alex.mercer@auracrm.com", role="Sr. Account Executive")
        rep_emma = SalesRep(name="Emma Watson", email="emma.watson@auracrm.com", role="Account Executive")
        db.add_all([rep_alex, rep_emma])
        db.flush()

        # ========================
        # 2. DEPARTMENTS
        # ========================
        # Only budget and spent are authored. Leads, customers, revenue and ROAS
        # are derived at query time from the leads/customers/purchases below.
        dept_social = Department(name="Social Media", budget=120000, spent=98500)
        dept_ppc = Department(name="Search Engine (PPC)", budget=150000, spent=142000)
        dept_email = Department(name="Email Marketing", budget=40000, spent=32000)
        dept_events = Department(name="Events & Webinars", budget=200000, spent=185000)
        dept_content = Department(name="Content Marketing", budget=80000, spent=75000)
        dept_influencer = Department(name="Influencer Marketing", budget=90000, spent=88000)
        departments = [dept_social, dept_ppc, dept_email, dept_events, dept_content, dept_influencer]
        db.add_all(departments)
        db.flush()

        # ========================
        # 3. MONTHLY TRENDS (global, linked to PPC dept for attribution)
        # ========================
        trends_data = [
            ("Jan", 45000, 120000), ("Feb", 48000, 135000),
            ("Mar", 55000, 160000), ("Apr", 52000, 155000),
            ("May", 60000, 190000), ("Jun", 65000, 210000),
            ("Jul", 72000, 240000), ("Aug", 68000, 230000),
        ]
        for month, spend, revenue in trends_data:
            db.add(MonthlyTrend(month=month, year=2026, spend=spend, revenue=revenue, department_id=None))
        db.flush()

        # ========================
        # 4. CAMPAIGNS
        # ========================
        campaigns_data = [
            ("Google Search - Enterprise B2B", dept_ppc.id, 25000),
            ("Q2 Product Update Newsletter", dept_email.id, 5000),
            ("AI Analytics Feature Launch", dept_content.id, 15000),
            ("LinkedIn Retargeting - Design Teams", dept_social.id, 12000),
            ("Design Leadership Webinar", dept_events.id, 18000),
            ("BlackHat Conference 2025 Lead", dept_events.id, 30000),
            ("Quarterly Security Briefing", dept_email.id, 3000),
            ("E-commerce Automation Campaign", dept_content.id, 10000),
            ("Winback Campaign Q3", dept_email.id, 4000),
            ("Whitepaper: Future of Open Banking API", dept_content.id, 8000),
            ("Developer API Newsletter", dept_email.id, 2000),
        ]
        campaign_objs = {}
        for name, dept_id, budget in campaigns_data:
            c = Campaign(name=name, department_id=dept_id, budget=budget)
            db.add(c)
            campaign_objs[name] = c
        db.flush()

        # ========================
        # 5. CUSTOMERS
        # ========================
        cust1 = Customer(
            code="CUST-001", name="Sarah Jenkins", email="sarah.j@techcorp.com",
            phone="+1 (555) 234-5678", company="TechCorp Solutions",
            job_title="VP of Marketing", status="Active", ltv=48500.00,
            acquisition_date=days_ago(240), acquisition_channel="Search Engine (PPC)", acquisition_department_id=dept_ppc.id,
            profile_pic="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150"
        )
        cust2 = Customer(
            code="CUST-002", name="Marcus Chen", email="m.chen@innovatedesign.io",
            phone="+1 (555) 876-5432", company="Innovate Design",
            job_title="Creative Director", status="Active", ltv=12400.00,
            acquisition_date=days_ago(120), acquisition_channel="Social Media", acquisition_department_id=dept_social.id,
            profile_pic="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150"
        )
        cust3 = Customer(
            code="CUST-003", name="Elena Rostova", email="elena.rostova@globalsecure.net",
            phone="+44 20 7946 0192", company="Global Secure Net",
            job_title="Head of Cyber Security", status="Active", ltv=85000.00,
            acquisition_date=days_ago(360), acquisition_channel="Events & Webinars", acquisition_department_id=dept_events.id,
            profile_pic="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150"
        )
        cust4 = Customer(
            code="CUST-004", name="David Miller", email="d.miller@retailflow.com",
            phone="+1 (555) 432-1098", company="RetailFlow Inc.",
            job_title="Director of E-commerce", status="Inactive", ltv=3200.00,
            acquisition_date=days_ago(180), acquisition_channel="Email Marketing", acquisition_department_id=dept_email.id,
            profile_pic="https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150"
        )
        cust5 = Customer(
            code="CUST-005", name="Aisha Rahman", email="aisha@fintech-labs.ae",
            phone="+971 4 321 4567", company="FinTech Labs Middle East",
            job_title="Co-Founder & CTO", status="Active", ltv=112000.00,
            acquisition_date=days_ago(420), acquisition_channel="Content Marketing", acquisition_department_id=dept_content.id,
            profile_pic="https://images.unsplash.com/photo-1567532939604-b6b5b0db2604?w=150"
        )
        customers = [cust1, cust2, cust3, cust4, cust5]
        db.add_all(customers)
        db.flush()

        # ========================
        # 6. INTERACTIONS (linked to customers)
        # ========================
        interactions_data = [
            # Customer 1 - Sarah Jenkins
            (cust1.id, days_ago(2), "Email", "Follow-up on Q3 Enterprise Plan renewal", "Sent", None),
            (cust1.id, days_ago(5), "Meeting", "Product Feedback & Roadmap Review", "Completed", None),
            (cust1.id, days_ago(12), "Support Ticket", "API integration rate limits", "Resolved", None),
            (cust1.id, days_ago(30), "Purchase", "Add-on License Purchase - 50 seats", "Completed", 7500.00),
            (cust1.id, days_ago(90), "Email", "Newsletter: Introducing AI Analytics", "Opened", None),
            (cust1.id, days_ago(180), "Meeting", "Q1 Business Review", "Completed", None),
            (cust1.id, days_ago(240), "Purchase", "Enterprise Annual Subscription", "Completed", 41000.00),
            # Customer 2 - Marcus Chen
            (cust2.id, days_ago(1), "Support Ticket", "Custom font rendering issue", "Open", None),
            (cust2.id, days_ago(15), "Email", "Invitation to Design Leadership Webinar", "Clicked", None),
            (cust2.id, days_ago(45), "Call", "Account Check-in & Upsell Discussion", "Completed", None),
            (cust2.id, days_ago(120), "Purchase", "Professional Monthly Plan (Annual prepay)", "Completed", 12400.00),
            # Customer 3 - Elena Rostova
            (cust3.id, days_ago(8), "Meeting", "Custom SLA & Security Addendum Review", "Completed", None),
            (cust3.id, days_ago(40), "Email", "Security Patch Release Notes", "Sent", None),
            (cust3.id, days_ago(180), "Purchase", "Custom Security Pack Add-on", "Completed", 15000.00),
            (cust3.id, days_ago(360), "Purchase", "Enterprise Premium Plan", "Completed", 70000.00),
            # Customer 4 - David Miller
            (cust4.id, days_ago(60), "Email", "We miss you! Special offer inside", "Sent", None),
            (cust4.id, days_ago(90), "Support Ticket", "Cancellation request - budget constraints", "Resolved", None),
            (cust4.id, days_ago(150), "Call", "Onboarding Assistance Call", "No Answer", None),
            (cust4.id, days_ago(180), "Purchase", "Starter Plan - Monthly", "Completed", 3200.00),
            # Customer 5 - Aisha Rahman
            (cust5.id, days_ago(3), "Meeting", "Partnership Expansion & API Access", "Completed", None),
            (cust5.id, days_ago(10), "Email", "API Documentation Update Notification", "Opened", None),
            (cust5.id, days_ago(60), "Purchase", "Custom API Tier Upgrade", "Completed", 42000.00),
            (cust5.id, days_ago(200), "Meeting", "Annual Review & Feedback Session", "Completed", None),
            (cust5.id, days_ago(420), "Purchase", "Enterprise Platform License", "Completed", 70000.00),
        ]
        for cid, dt, typ, subj, stat, amt in interactions_data:
            db.add(Interaction(customer_id=cid, date=dt, type=typ, subject=subj, status=stat, amount=amt))
        db.flush()

        # ========================
        # 7. PURCHASES (linked to customers)
        # ========================
        purchases_data = [
            ("ORD-9982", cust1.id, days_ago(30), "Add-on License Purchase - 50 seats", 7500.00),
            ("ORD-8812", cust1.id, days_ago(240), "Enterprise Annual Subscription", 41000.00),
            ("ORD-8102", cust2.id, days_ago(120), "Professional Monthly Plan (Annual prepay)", 12400.00),
            ("ORD-7621", cust3.id, days_ago(180), "Custom Security Pack Add-on", 15000.00),
            ("ORD-5412", cust3.id, days_ago(360), "Enterprise Premium Plan", 70000.00),
            ("ORD-6123", cust4.id, days_ago(180), "Starter Plan - Monthly (Prepaid 6mo)", 3200.00),
            ("ORD-9012", cust5.id, days_ago(60), "Custom API Tier Upgrade", 42000.00),
            ("ORD-4123", cust5.id, days_ago(420), "Enterprise Platform License", 70000.00),
        ]
        for code, cid, dt, item, amt in purchases_data:
            db.add(Purchase(order_code=code, customer_id=cid, date=dt, item=item, amount=amt))
        db.flush()

        # ========================
        # 8. CUSTOMER ↔ CAMPAIGN LINKS (M2M)
        # ========================
        campaign_links = [
            (cust1.id, "Google Search - Enterprise B2B", "Converted"),
            (cust1.id, "Q2 Product Update Newsletter", "Opened"),
            (cust1.id, "AI Analytics Feature Launch", "Clicked"),
            (cust2.id, "LinkedIn Retargeting - Design Teams", "Converted"),
            (cust2.id, "Design Leadership Webinar", "Registered"),
            (cust3.id, "BlackHat Conference 2025 Lead", "Converted"),
            (cust3.id, "Quarterly Security Briefing", "Opened"),
            (cust4.id, "E-commerce Automation Campaign", "Converted"),
            (cust4.id, "Winback Campaign Q3", "Ignored"),
            (cust5.id, "Whitepaper: Future of Open Banking API", "Converted"),
            (cust5.id, "Developer API Newsletter", "Clicked"),
        ]
        for cid, camp_name, status in campaign_links:
            camp = campaign_objs[camp_name]
            db.add(CustomerCampaign(customer_id=cid, campaign_id=camp.id, status=status))
        db.flush()

        # ========================
        # 9. LEADS (linked to sales_reps AND source departments)
        # ========================
        source_dept_map = {
            "LinkedIn": dept_social.id,
            "Google": dept_ppc.id,
            "Event": dept_events.id,
            "Email": dept_email.id,
            "Referral": None,
            "Content": dept_content.id,
        }

        leads_data = [
            ("LEAD-101", "Robert Chen", "robert@apexretail.com", "+1 (555) 111-2233",
             "Apex Retail Group", 15000, "New", 85, "LinkedIn", rep_alex.id, None),
            ("LEAD-102", "Sophia Martinez", "s.martinez@healthpulse.org", "+1 (555) 222-3344",
             "HealthPulse Diagnostics", 28000, "Contacted", 65, "Google", rep_emma.id, None),
            ("LEAD-103", "James O'Connor", "j.oconnor@greenenergy.ie", "+353 1 234 5678",
             "Green Energy Solutions", 45000, "Qualified", 92, "Event", rep_alex.id, None),
            ("LEAD-104", "Emily Watson", "emily@brighteducation.edu", "+1 (555) 333-4455",
             "Bright Path Education", 9500, "Proposal", 78, "Email", rep_emma.id, None),
            ("LEAD-105", "Vikram Singh", "vsingh@indialogistics.in", "+91 98765 43210",
             "Bharat Logistics Ltd", 62000, "Contacted", 45, "Referral", rep_alex.id, None),
            ("LEAD-106", "Clara Dupont", "c.dupont@luxe-fashion.fr", "+33 1 23 45 67 89",
             "Luxe Retail Group", 18000, "Won", 98, "LinkedIn", rep_emma.id, None),
            ("LEAD-107", "Thomas Kael", "tkael@nordicbuild.no", "+47 21 23 45 67",
             "Nordic Build Corp", 35000, "Lost", 20, "Google", rep_alex.id, None),
        ]
        for (code, name, email, phone, company, value, status, score,
             source, rep_id, conv_cust_id) in leads_data:
            db.add(Lead(
                code=code, name=name, email=email, phone=phone,
                company=company, value=value, status=status, score=score,
                source=source, source_department_id=source_dept_map.get(source),
                assigned_to_id=rep_id, converted_customer_id=conv_cust_id
            ))
        db.flush()

        db.commit()
        print("✅ Database seeded successfully!")
        print(f"   - {len(customers)} Customers")
        print(f"   - {len(leads_data)} Leads")
        print(f"   - {len(interactions_data)} Interactions")
        print(f"   - {len(purchases_data)} Purchases")
        print(f"   - {len(departments)} Departments")
        print(f"   - {len(campaigns_data)} Campaigns")
        print(f"   - {len(campaign_links)} Customer↔Campaign Links")
        print(f"   - 2 Sales Reps")
        print(f"   - {len(trends_data)} Monthly Trends")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
