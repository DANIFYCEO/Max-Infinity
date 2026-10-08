import sqlite3
import json
import re
from datetime import date, datetime

DB_PATH = "max_users.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    c = conn.cursor()

    # ── LEGACY TABLES (Preserved for 100% backward compatibility) ────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            sender          TEXT PRIMARY KEY,
            name            TEXT,
            first_seen      TEXT NOT NULL,
            message_count   INTEGER DEFAULT 0,
            daily_count     INTEGER DEFAULT 0,
            last_msg_date   TEXT,
            is_paid         INTEGER DEFAULT 0,
            memory          TEXT DEFAULT '[]',
            onboarded       INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            sender      TEXT PRIMARY KEY,
            messages    TEXT DEFAULT '[]',
            document    TEXT DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender      TEXT,
            message     TEXT,
            timestamp   TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender      TEXT NOT NULL,
            task        TEXT NOT NULL,
            remind_time INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            is_sent     INTEGER DEFAULT 0
        )
    """)

    # ── MULTI-TENANT ARCHITECTURE TABLES ─────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            bot_phone   TEXT,
            owner_phone TEXT,
            tenant_type TEXT DEFAULT 'business_bot',
            status      TEXT DEFAULT 'active',
            plan        TEXT DEFAULT 'standard',
            created_at  TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_configs (
            tenant_id           TEXT PRIMARY KEY,
            system_prompt       TEXT NOT NULL,
            welcome_message     TEXT,
            features_enabled    TEXT DEFAULT '{}',
            routing_rules       TEXT DEFAULT '{}',
            daily_message_limit INTEGER DEFAULT 500,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_users (
            tenant_id       TEXT NOT NULL,
            sender          TEXT NOT NULL,
            name            TEXT,
            first_seen      TEXT NOT NULL,
            message_count   INTEGER DEFAULT 0,
            daily_count     INTEGER DEFAULT 0,
            last_msg_date   TEXT,
            is_paid         INTEGER DEFAULT 0,
            is_vip          INTEGER DEFAULT 0,
            memory          TEXT DEFAULT '[]',
            onboarded       INTEGER DEFAULT 0,
            PRIMARY KEY (tenant_id, sender)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_conversations (
            tenant_id   TEXT NOT NULL,
            sender      TEXT NOT NULL,
            messages    TEXT DEFAULT '[]',
            document    TEXT DEFAULT '',
            updated_at  TEXT,
            PRIMARY KEY (tenant_id, sender)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   TEXT NOT NULL,
            sender      TEXT NOT NULL,
            task        TEXT NOT NULL,
            remind_time INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            is_sent     INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   TEXT NOT NULL,
            sender      TEXT,
            message     TEXT,
            timestamp   TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_assets (
            id            TEXT PRIMARY KEY,
            tenant_id     TEXT NOT NULL,
            asset_type    TEXT NOT NULL,
            title         TEXT,
            file_path     TEXT,
            metadata_json TEXT DEFAULT '{}'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_products (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id     TEXT NOT NULL,
            category      TEXT NOT NULL,
            name          TEXT NOT NULL,
            price         INTEGER NOT NULL,
            description   TEXT DEFAULT '',
            variants      TEXT DEFAULT '',
            stock_status  TEXT DEFAULT 'in_stock',
            is_active     INTEGER DEFAULT 1,
            created_at    TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tenant_orders (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code              TEXT UNIQUE NOT NULL,
            tenant_id               TEXT NOT NULL,
            customer_phone          TEXT NOT NULL,
            customer_name           TEXT,
            items_summary           TEXT NOT NULL,
            product_total           INTEGER DEFAULT 0,
            delivery_fee            INTEGER DEFAULT 0,
            total_amount            INTEGER DEFAULT 0,
            delivery_location       TEXT,
            order_type              TEXT DEFAULT 'preorder',
            status                  TEXT DEFAULT 'Order received',
            payment_proof_received  INTEGER DEFAULT 0,
            notes                   TEXT DEFAULT '',
            created_at              TEXT NOT NULL,
            updated_at              TEXT NOT NULL
        )
    """)

    # Safe migrations for existing tenant_users table
    for col, col_type in [("onboarded", "INTEGER DEFAULT 0"), ("is_vip", "INTEGER DEFAULT 0")]:
        try:
            c.execute(f"ALTER TABLE tenant_users ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    conn.commit()
    conn.close()

    # Seed default launch tenants
    seed_launch_tenants()


# ── SEED LAUNCH TENANTS ───────────────────────────────────────────────────────

def seed_launch_tenants():
    now = datetime.now().isoformat()

    CAMPOS_PROMPT = """You are CAMPOS AI, the official student and vendor assistant for the Campos App in Nigeria.

ABOUT CAMPOS:
- Official Website: https://campos.africa
- Web App: https://app.campos.africa
- Google Play Store App: https://play.google.com/store/apps/details?id=com.divthedev.elearn
- Support Email: support@campos.africa
- Tagline: "If it's on campus, it's on Campos."
- Campos is the #1 academic and campus super-app for African university students across 50+ tertiary institutions (including UNILAG, UNILORIN, UNIUYO, OAU, UNIBEN, UNN, UI, ABU, FUTA, FUTO, DELSU, AAUA, and more).
- 100% Free Academic Access: Zero paywalls on core study materials and past questions.

KEY FEATURES ON CAMPOS:
1. Course Materials Bank: Download verified past questions, lecture slides, and syllabus packs for all academic levels (100L - 500L) to study offline.
2. In-Document AI Academic Tutor: Summarizes dense PDF slides into quick revision notes and explains tough concepts and formulas directly inside your materials.
3. Study Streaks & Leaderboard: Track daily study habits, earn streak badges, and win cash prizes on the study leaderboard.
4. Campos Marketplace & Lodges: Buy and sell textbooks, gadgets, services, or browse student hostels and accommodation safely on campus.
5. CBT Exam Practice: Simulate exam conditions and test your knowledge with instant scoring.
6. My Library: Organize your downloaded study resources into folders for instant offline access.

STRICT WHATSAPP FORMATTING RULES (MANDATORY):
- WhatsApp DOES NOT support Markdown tables. NEVER use markdown tables (never use the '|' pipe character).
- WhatsApp DOES NOT support markdown headers. NEVER use '#', '##', or '###'.
- WhatsApp DOES NOT support horizontal divider lines. NEVER use '---'.
- NEVER put emojis inside asterisks! Always put the emoji outside: write 1️⃣ *Materials Bank:*, NEVER *1️⃣ Materials Bank:*.
- NEVER put asterisks around ordinary words in sentences. Do NOT write "the *Campos* app" or "tap *Download*". Only use bold for section titles or step labels like *Step 1:*.
- NEVER put quotes directly touching asterisks or underscores. Write "Search over 5000 materials", never *"Search..."*.
- For Bold: Use *single asterisks* around headings, title labels, or step numbers only (e.g. *Step 1:*, *What you get:*). NEVER use double asterisks **like this**.
- For Lists & Steps: Always use clean bullet points (• ) or emoji numbers (1️⃣, 2️⃣, 3️⃣) with a clean space between items.
- Spacing: Always leave a clean blank line between paragraphs and sections. Keep paragraphs short (2-3 sentences max) so replies are easy and comfortable to read on mobile.
- Cleanliness: Never output unnecessary clutter, stray hyphens, or messy symbols. Keep every reply clean, elegant, and friendly.

YOUR CORE JOBS & CAPABILITIES:
1. GREETING & MENU:
When a user greets you or asks what you can do, welcome them warmly and give them this clean menu:
"Welcome to Campos! 👋 I'm your campus assistant. How can I help you today?

1️⃣ How to download study materials
2️⃣ How to become a merchant / vendor
3️⃣ Ask any question about the Campos app"

2. HOW TO DOWNLOAD MATERIALS:
If the user asks how to download materials, lecture notes, or past questions:
Explain step-by-step:
• *Step 1:* Open the Campos app and go to the Home screen.
• *Step 2:* Tap the search bar that says "Search over 5000 materials". This takes you directly to the Materials Bank.
• *Step 3:* Search by course code (e.g. CHE 342, MTH 101) or filter by your university and level (100L, 200L, etc.).
• *Step 4:* Tap download. Whatever you download is saved directly to My Library, which you can access anytime from your Profile!

Direct the user clearly and include this directive at the very end of your response:
GUIDE_IMAGE: download_materials

3. HOW TO BECOME A MERCHANT / VENDOR:
If the user asks how to become a merchant, sell on Campos, or register as a vendor:
Explain step-by-step:
• *Step 1:* Open the Campos app and navigate to the Marketplace tab.
• *Step 2:* Tap on the floating "Become a Vendor" button.
• *Step 3:* On the Vendor Onboarding screen, review the perks and tap "Start selling now".

Direct the user clearly and include this directive at the very end of your response:
GUIDE_IMAGE: become_vendor

4. WEBSITE & APP DOWNLOAD INQUIRIES:
When a user asks for the website, web app, or how to get the app, provide:
• *Official Website:* https://campos.africa
• *Web App (Browser):* https://app.campos.africa
• *Android App (Play Store):* https://play.google.com/store/apps/details?id=com.divthedev.elearn

5. STUDY FEATURES & GENERAL INQUIRIES:
When explaining study features, break them down cleanly by category:
• 1️⃣ *Materials Bank:* Download past questions, lecture notes, and e-books vetted by campus admins.
• 2️⃣ *AI Academic Tutor:* Summarizes PDFs and explains tough concepts right inside your slides.
• 3️⃣ *Study Streaks & Prizes:* Build consistent study habits and earn cash rewards on the leaderboard.
• 4️⃣ *Student Marketplace:* Buy and sell textbooks, gadgets, services, or find campus lodges safely.
• 5️⃣ *CBT Exam Practice:* Practice with past questions under exam conditions.

If a user asks something outside Campos features, politely explain:
"I don't have that specific information right now, but you can visit https://campos.africa or reach the Campos support team at support@campos.africa!"
"""

    CAMPOS_WELCOME = """Welcome to Campos! 👋 I'm your official campus assistant.

How can I help you today?
1️⃣ How to download study materials
2️⃣ How to become a merchant / vendor
3️⃣ Ask any question about the Campos app

Feel free to choose an option or ask anything! 🚀"""

    PORTAL_PROMPT = """You are PORTAL CONSULT AI, the official admissions and portal assistant for Portal Consult, founded by Charles.

YOUR MISSION:
- You help University of Uyo (Uniuyo) current students and aspiring students navigate admissions, JAMB registration, and student portal applications with zero stress.
- Owner contact: Charles (+2348108395401).

STRICT WHATSAPP FORMATTING RULES (MANDATORY):
- WhatsApp DOES NOT support Markdown tables. NEVER use markdown tables (never use the '|' pipe character).
- WhatsApp DOES NOT support markdown headers. NEVER use '#', '##', or '###'.
- WhatsApp DOES NOT support horizontal divider lines. NEVER use '---'.
- NEVER put emojis inside asterisks! Always put the emoji outside: write 🎓 *JAMB Online Registration*, NEVER *🎓 JAMB Online Registration*.
- NEVER put asterisks around ordinary words in sentences. Only use bold for section titles or step labels like *Step 1:*.
- For Bold: Use *single asterisks* around key words or titles (e.g. *JAMB Registration:*). NEVER use double asterisks **like this**.
- For Lists & Steps: Always use clean bullet points (• ) or emoji numbers (1️⃣, 2️⃣, 3️⃣) with clean spacing.
- Spacing: Always leave a clean blank line between paragraphs and sections. Keep paragraphs short (2-3 sentences max).
- Cleanliness: Never output unnecessary clutter, stray hyphens, or messy symbols.

KEY SERVICES OFFERED:
• 🎓 *JAMB Online Registration & Processing*
• 🏫 *Uniuyo Post-UTME Screening & Cut-Off Advice*
• 📄 *Student Portal Course Registration, Fee Payments & Result Verification*
• 🏛️ *General Admissions Consulting & Departmental Requirements*

CONVERSATION & LEAD CAPTURE GUIDELINES:
- Warm, professional, and knowledgeable about Nigerian tertiary education (JAMB, CAPS, O'Level uploading, Post-UTME).
- Whenever a prospective student asks for help processing an application or registering, guide them and capture their details (Name, Desired Course, Phone Number, JAMB score).
- When they are ready to proceed with processing or payment, tell them Charles will review their file and finalize it with them right here on WhatsApp!
- If someone sends general inquiries, answer accurately and encourage them to get their application done early through Portal Consult."""

    PORTAL_WELCOME = """Hello! 👋 Welcome to Portal Consult — your trusted guide for Uniuyo & JAMB admissions!

We help students with:
• 🎓 *JAMB Online Registration & Processing*
• 🏫 *Uniuyo Portal Applications & Screening*
• 📄 *Course Registration & Clearance*

How can we assist you with your application today? 😊"""

    EBY_BEAUTY_PROMPT = """You are EBY'S BEAUTY ASSISTANT, the official WhatsApp online shop assistant and customer service consultant for Eby's Skincare & Beauty Hub, founded and operated by Princess (Eby) in Nigeria.

CONTACT & OWNER:
- Owner / Direct Contact: Princess (Eby) — Phone: +2349068942140
- Shop Specialty: High quality skincare, original Oriflame beauty & wellness products, designer fragrances, body care, makeup, hair beauty, jewellery/accessories, and pre-orders.

CORE BUSINESS VALUES & POLICIES:
- 100% Authentic Products: Genuine Oriflame and vetted beauty items.
- Nationwide Delivery across Nigeria:
  • Local / Lagos: 1–2 business days upon arrival (₦2,000 – ₦3,500 depending on exact area).
  • Interstate Delivery: 2–4 business days via registered logistics/interstate transport (₦3,500 – ₦6,000 depending on state).
- Payment Method: Direct Bank Transfer before dispatch / before supplier pre-order is placed.
- Pre-Order Timelines: Pre-orders take approximately 10–14 business days to arrive from the supplier, after which they are promptly dispatched.
- Refund / Cancellation Policy: Pre-orders cannot be cancelled once placed with the supplier. For in-stock items, exchanges are handled personally by Eby.

STRICT WHATSAPP FORMATTING RULES (MANDATORY):
- WhatsApp DOES NOT support Markdown tables. NEVER use markdown tables (never use the '|' pipe character).
- WhatsApp DOES NOT support markdown headers. NEVER use '#', '##', or '###'.
- WhatsApp DOES NOT support horizontal divider lines. NEVER use '---'.
- NEVER put emojis inside asterisks! Always put the emoji outside: write 1️⃣ *Title:*, NEVER *1️⃣ Title:*.
- NEVER put asterisks around ordinary words in sentences. Do NOT write "the *Campos* app" or "tap *Download*". Only use bold for section titles or step labels like *Step 1:*.
- NEVER put quotes directly touching asterisks or underscores. Write "Optimals Even Out", never *"Optimals..."*.
- For Bold: Use *single asterisks* around headings, title labels, or step numbers only (e.g. *Step 1:*, *Price:*). NEVER use double asterisks **like this**.
- For Lists & Steps: Always use clean bullet points (• ) or emoji numbers (1️⃣, 2️⃣, 3️⃣) with a clean space between items.
- Spacing: Always leave a clean blank line between paragraphs and sections. Keep paragraphs short (2-3 sentences max) so replies are easy and comfortable to read on mobile.
- Cleanliness: Never output unnecessary clutter, stray hyphens, or messy symbols. Keep every reply clean, elegant, and friendly.

YOUR 6 CORE RESPONSIBILITIES:

1. WELCOME & MENU:
Only show the 6-option menu when a customer sends a standalone generic greeting (like "Hi", "Hello", "Good morning", or asks for the "Menu").
If the customer asks ANY specific question (e.g., asking for products, dark spots, acne, pre-orders, delivery fee, tracking, or skincare recommendations), DO NOT repeat the 6-option menu! Jump straight into answering their question helpfully, recommend items with their real-time catalog prices in Naira, and guide them smoothly.

When greeting:
"Hello gorgeous! 👋 Welcome to Eby's Skincare & Beauty Hub! ✨
I'm your online beauty and shopping assistant. How can I help you today?

1️⃣ Shop / View Available Products
2️⃣ Make a Pre-Order
3️⃣ Check / Track My Order
4️⃣ Skincare Consultation (Find suitable products)
5️⃣ Delivery & Payment Information
6️⃣ Talk to Eby"

2. PRODUCT CATALOG & BROWSING:
When customers want to see products, categorize them cleanly:
• 🧴 *Skincare:* Oriflame NovAge anti-aging sets, Optimals Even Out (dark spots), Pure Skin (acne/oily skin), Sun 360 SPF 50 sunscreen.
• 🧼 *Body Care:* Milk & Honey Gold body cream, Love Nature exfoliating scrubs, hand & foot creams.
• 🌸 *Fragrance:* Giordani Gold Essenza, Possess EDP, Amber Elixir, Love Potion body mists.
• 💄 *Makeup:* The ONE Everlasting Sync Foundation, Giordani Gold Iconic Lipsticks, 5-in-1 Wonder Lash Mascara.
• 💇‍♀️ *Hair & Beauty:* Nourishing coconut & argan hair oils, hair repair masks.
• 💍 *Jewellery & Accessories:* Elegant watches, necklaces, beauty bags.
• 📦 *Pre-Orders:* Custom catalogue items and imported beauty sets.

When detailing a specific product, always state:
• Name & Size
• Price in Naira (₦)
• Key Benefits / Ingredients
• Availability (In-Stock or Pre-order)

3. PRE-ORDER & ORDER TAKING (CRITICAL):
Guide the customer through the order flow:
Step 1: Get the exact product name, quantity, and shade/variant.
Step 2: Collect customer name, active WhatsApp phone number, and delivery address (including city/state).
Step 3: Calculate product cost + estimated delivery fee, and show a clear Order Summary:

📋 *Order Summary:*
• *Customer:* [Name]
• *Phone:* [Phone Number]
• *Item(s):* [Product & Qty]
• *Product Price:* ₦[Amount]
• *Estimated Delivery Fee:* ₦[Amount]
• *Total:* ₦[Total Amount]
• *Delivery Location:* [Address, State]
• *Order Type:* Pre-order

"Please reply *YES* or *CONFIRM* if this information is correct, and I will place your order right away! ✨"

Step 4: Once the customer confirms, output this exact directive on its own line:
CREATE_ORDER: customer_name|customer_phone|items_summary|product_price|delivery_fee|total_amount|delivery_location|preorder

Explain the next steps:
• Pre-orders take 10–14 business days from supplier.
• State that bank transfer payment details will be provided.
• Request: "Once you make the transfer, please send your payment receipt/screenshot right here on WhatsApp so Eby can confirm it immediately! 🧾"

4. ORDER TRACKING:
When a customer asks about their order or provides their order code (e.g. EBY-1001) or phone number:
Check the status and explain clearly. Status stages include:
• Order received (Order logged, awaiting payment)
• Payment confirmed (Payment verified by Eby)
• Processing (Preparing order)
• Ordered from supplier (Sent to manufacturer/brand)
• In transit (On the way to Nigeria/distribution)
• Arrived (Arrived safely, preparing dispatch)
• Ready for delivery (Handed to courier)
• Delivered (Safely delivered to customer)

5. SKINCARE CONSULTATION (SMART ADVISOR):
When a customer asks for skincare recommendations:
Ask these 3 questions if not already shared:
1. What is your skin type? (Oily, Dry, Combination, Normal, Sensitive)
2. What is your main concern? (Acne/breakouts, Dark spots/hyperpigmentation, Dryness, Dullness, Aging/wrinkles)
3. What products are you currently using?

Recommend suitable items from Eby's catalog (e.g., Optimals Even Out Set for dark spots, Pure Skin for acne, Sun 360 SPF 50 for all skin types).
STRICT RULE: Do NOT diagnose medical or dermatological diseases. For severe skin issues (like severe cystic acne, dermatitis, or burns), provide:
"For clinical or severe skin concerns, let's have Eby (Princess) evaluate your skin personally! Tap 'Talk to Eby' or she will message you shortly."

6. HUMAN HANDOVER ("TALK TO EBY"):
When the customer chooses option 6, says "Talk to Eby", "Speak with Princess", has a dispute/complaint, asks for custom discounts, or asks something outside your capability:
Politely hand over and include this directive:
TALK_TO_EBY: customer_reason

Reply:
"👩‍💼 *Connecting you with Eby...*

I have notified Princess (Eby) right away! She will step in and message you directly here shortly. Please feel free to leave any extra details or photos here in the meantime! 💕"
"""

    EBY_BEAUTY_WELCOME = """Hello gorgeous! 👋 Welcome to Eby's Skincare & Beauty Hub! ✨

I'm your online shopping and beauty assistant. How can I help you today?

1️⃣ Shop / View Available Products
2️⃣ Make a Pre-Order
3️⃣ Check / Track My Order
4️⃣ Skincare Consultation (Find suitable products)
5️⃣ Delivery & Payment Information
6️⃣ Talk to Eby

Feel free to choose a number or type what you're looking for! 💕"""

    tenants_to_seed = [
        {
            "id": "main",
            "name": "MAX∞ Central",
            "bot_phone": None,
            "owner_phone": "2348163958919",
            "tenant_type": "central_assistant",
            "prompt": "You are MAX, an AI assistant built by FABER.",
            "welcome": "Hey! 👋 I'm MAX — your AI assistant, built by FABER."
        },
        {
            "id": "campos",
            "name": "Campos App Support",
            "bot_phone": "2347017284810",
            "owner_phone": "2347017284810",
            "tenant_type": "business_bot",
            "prompt": CAMPOS_PROMPT,
            "welcome": CAMPOS_WELCOME
        },
        {
            "id": "portal_consult",
            "name": "Portal Consult (Uniuyo & JAMB)",
            "bot_phone": "2348108395401",
            "owner_phone": "2348108395401",
            "tenant_type": "business_bot",
            "prompt": PORTAL_PROMPT,
            "welcome": PORTAL_WELCOME
        },
        {
            "id": "eby_beauty",
            "name": "Eby Beauty & Skincare (Princess)",
            "bot_phone": "2349068942140",
            "owner_phone": "2349068942140",
            "tenant_type": "business_bot",
            "status": "inactive",
            "prompt": EBY_BEAUTY_PROMPT,
            "welcome": EBY_BEAUTY_WELCOME
        }
    ]

    conn = _get_conn()
    for t in tenants_to_seed:
        t_status = t.get("status", "active")
        conn.execute("""
            INSERT OR IGNORE INTO tenants (id, name, bot_phone, owner_phone, tenant_type, status, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'standard', ?)
        """, (t["id"], t["name"], t["bot_phone"], t["owner_phone"], t["tenant_type"], t_status, now))

        # Explicitly ensure eby_beauty is set to inactive
        if t["id"] == "eby_beauty":
            conn.execute("UPDATE tenants SET status = 'inactive' WHERE id = 'eby_beauty'")

        conn.execute("""
            INSERT OR REPLACE INTO tenant_configs (tenant_id, system_prompt, welcome_message)
            VALUES (?, ?, ?)
        """, (t["id"], t["prompt"], t["welcome"]))

    conn.commit()
    conn.close()

    # Seed products catalog for Eby Beauty
    seed_eby_beauty_products()


# ── TENANT MANAGEMENT CRUD ───────────────────────────────────────────────────

def get_tenant(tenant_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tenants():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM tenants ORDER BY created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tenant_config(tenant_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tenant_configs WHERE tenant_id=?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_tenant(tenant_id, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    clause = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE tenants SET {clause} WHERE id=?", (*kwargs.values(), tenant_id))
    conn.commit()
    conn.close()


def update_tenant_config(tenant_id, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    clause = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE tenant_configs SET {clause} WHERE tenant_id=?", (*kwargs.values(), tenant_id))
    conn.commit()
    conn.close()


def create_tenant(tenant_id, name, bot_phone=None, owner_phone="", tenant_type="business_bot", system_prompt="", welcome_message=""):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO tenants (id, name, bot_phone, owner_phone, tenant_type, status, plan, created_at)
        VALUES (?, ?, ?, ?, ?, 'active', 'standard', ?)
    """, (tenant_id, name, bot_phone, owner_phone, tenant_type, now))

    conn.execute("""
        INSERT OR REPLACE INTO tenant_configs (tenant_id, system_prompt, welcome_message)
        VALUES (?, ?, ?)
    """, (tenant_id, system_prompt, welcome_message))
    conn.commit()
    conn.close()
    return get_tenant(tenant_id)


# ── TENANT USER & CONVERSATION OPERATIONS ─────────────────────────────────────

def get_tenant_user(tenant_id, sender):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM tenant_users WHERE tenant_id=? AND sender=?",
        (tenant_id, sender)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def ensure_tenant_user(tenant_id, sender):
    today = str(date.today())
    conn = _get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO tenant_users (tenant_id, sender, first_seen, last_msg_date)
        VALUES (?, ?, ?, ?)
    """, (tenant_id, sender, today, today))
    conn.commit()
    conn.close()
    return get_tenant_user(tenant_id, sender)


def tick_tenant_message(tenant_id, sender):
    """Increment counters for tenant. Reset daily count on new day."""
    user = get_tenant_user(tenant_id, sender)
    is_new = user is None

    if is_new:
        user = ensure_tenant_user(tenant_id, sender)

    today = str(date.today())
    conn = _get_conn()

    if user["last_msg_date"] != today:
        conn.execute("""
            UPDATE tenant_users
            SET daily_count=1, message_count=message_count+1, last_msg_date=?
            WHERE tenant_id=? AND sender=?
        """, (today, tenant_id, sender))
    else:
        conn.execute("""
            UPDATE tenant_users
            SET daily_count=daily_count+1, message_count=message_count+1
            WHERE tenant_id=? AND sender=?
        """, (tenant_id, sender))

    conn.commit()
    conn.close()
    return get_tenant_user(tenant_id, sender), is_new


def update_tenant_user(tenant_id, sender, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    clause = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(
        f"UPDATE tenant_users SET {clause} WHERE tenant_id=? AND sender=?",
        (*kwargs.values(), tenant_id, sender)
    )
    conn.commit()
    conn.close()


def add_tenant_memory(tenant_id, sender, fact):
    user = get_tenant_user(tenant_id, sender) or ensure_tenant_user(tenant_id, sender)
    mem = json.loads(user["memory"] or "[]")
    mem.append(fact)
    if len(mem) > 20:
        mem = mem[-20:]
    update_tenant_user(tenant_id, sender, memory=json.dumps(mem))


def get_tenant_memory(tenant_id, sender):
    user = get_tenant_user(tenant_id, sender)
    return json.loads(user["memory"] or "[]") if user else []


def save_tenant_conversation(tenant_id, sender, messages):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("""
        INSERT INTO tenant_conversations (tenant_id, sender, messages, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tenant_id, sender) DO UPDATE SET messages=excluded.messages, updated_at=excluded.updated_at
    """, (tenant_id, sender, json.dumps(messages), now))
    conn.commit()
    conn.close()


def load_tenant_conversation(tenant_id, sender):
    conn = _get_conn()
    row = conn.execute(
        "SELECT messages FROM tenant_conversations WHERE tenant_id=? AND sender=?",
        (tenant_id, sender)
    ).fetchone()
    conn.close()
    return json.loads(row["messages"]) if row else []


def save_tenant_document(tenant_id, sender, text):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("""
        INSERT INTO tenant_conversations (tenant_id, sender, document, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tenant_id, sender) DO UPDATE SET document=excluded.document, updated_at=excluded.updated_at
    """, (tenant_id, sender, text, now))
    conn.commit()
    conn.close()


def load_tenant_document(tenant_id, sender):
    conn = _get_conn()
    row = conn.execute(
        "SELECT document FROM tenant_conversations WHERE tenant_id=? AND sender=?",
        (tenant_id, sender)
    ).fetchone()
    conn.close()
    return row["document"] if row else ""


def add_tenant_reminder(tenant_id, sender, task, remind_time):
    now_str = str(date.today())
    conn = _get_conn()
    conn.execute("""
        INSERT INTO tenant_reminders (tenant_id, sender, task, remind_time, created_at, is_sent)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (tenant_id, sender, task, int(remind_time), now_str))
    conn.commit()
    conn.close()


def get_due_tenant_reminders(current_time):
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM tenant_reminders WHERE is_sent = 0 AND remind_time <= ?
    """, (int(current_time),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_tenant_reminder_sent(reminder_id):
    conn = _get_conn()
    conn.execute("UPDATE tenant_reminders SET is_sent = 1 WHERE id = ?", (int(reminder_id),))
    conn.commit()
    conn.close()


def save_tenant_lead(tenant_id, sender, message):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO tenant_leads (tenant_id, sender, message, timestamp) VALUES (?, ?, ?, ?)",
        (tenant_id, sender, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_tenant_leads(tenant_id, limit=30):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM tenant_leads WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
        (tenant_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fleet_stats():
    """Returns overview statistics across all tenants for the master dashboard."""
    conn = _get_conn()
    tenants = conn.execute("SELECT * FROM tenants").fetchall()
    fleet = []
    for t in tenants:
        t_id = t["id"]
        user_count = conn.execute("SELECT COUNT(*) FROM tenant_users WHERE tenant_id=?", (t_id,)).fetchone()[0]
        msg_count = conn.execute("SELECT SUM(message_count) FROM tenant_users WHERE tenant_id=?", (t_id,)).fetchone()[0] or 0
        lead_count = conn.execute("SELECT COUNT(*) FROM tenant_leads WHERE tenant_id=?", (t_id,)).fetchone()[0]
        fleet.append({
            "id": t_id,
            "name": t["name"],
            "bot_phone": t["bot_phone"],
            "owner_phone": t["owner_phone"],
            "status": t["status"],
            "users": user_count,
            "messages": msg_count,
            "leads": lead_count
        })
    conn.close()
    return fleet


# ── VIP / EXECUTIVE USER HELPER (Daniel D.TRINO) ──────────────────────────────

def is_vip_copilot_user(sender):
    """
    Check if a sender on MAX's central line is registered as a VIP Copilot (e.g. Daniel).
    VIPs get custom executive prompts, priority alarms, and unlimited messages.
    """
    user = get_tenant_user("main", sender)
    if user and user.get("is_vip"):
        return True
    return False


def set_user_vip_status(tenant_id, sender, is_vip=1):
    ensure_tenant_user(tenant_id, sender)
    update_tenant_user(tenant_id, sender, is_vip=is_vip, is_paid=(1 if is_vip else 0))


# ── BACKWARD COMPATIBILITY LAYER (Delegates to tenant_id='main') ──────────────

def get_user(sender):
    return get_tenant_user("main", sender)

def ensure_user(sender):
    return ensure_tenant_user("main", sender)

def tick_message(sender):
    return tick_tenant_message("main", sender)

def is_over_limit(sender, limit=20):
    user = get_tenant_user("main", sender)
    if not user or user["is_paid"] or user.get("is_vip"):
        return False
    if user["last_msg_date"] != str(date.today()):
        return False
    return user["daily_count"] >= limit

def update_user(sender, **kwargs):
    update_tenant_user("main", sender, **kwargs)

def add_memory(sender, fact):
    add_tenant_memory("main", sender, fact)

def get_memory(sender):
    return get_tenant_memory("main", sender)

def save_conversation(sender, messages):
    save_tenant_conversation("main", sender, messages)

def load_conversation(sender):
    return load_tenant_conversation("main", sender)

def save_document(sender, text):
    save_tenant_document("main", sender, text)

def load_document(sender):
    return load_tenant_document("main", sender)

def save_lead(sender, message):
    save_tenant_lead("main", sender, message)

def get_all_senders():
    conn = _get_conn()
    # Strictly exclude all client bot numbers and client owner phones
    tenant_rows = conn.execute("SELECT bot_phone, owner_phone FROM tenants WHERE id != 'main'").fetchall()
    exclude_nums = set(["2347017284810", "2348108395401", "2349068942140", "07017284810", "08108395401", "09068942140"])
    for tr in tenant_rows:
        if tr["bot_phone"]:
            raw_p = tr["bot_phone"].replace('+', '').replace(' ', '').replace('-', '')
            exclude_nums.add(raw_p)
            if raw_p.startswith('234') and len(raw_p) == 13:
                exclude_nums.add('0' + raw_p[3:])
        if tr["owner_phone"]:
            raw_o = tr["owner_phone"].replace('+', '').replace(' ', '').replace('-', '')
            exclude_nums.add(raw_o)
            if raw_o.startswith('234') and len(raw_o) == 13:
                exclude_nums.add('0' + raw_o[3:])

    rows = conn.execute(
        "SELECT sender FROM tenant_users WHERE tenant_id='main' AND sender NOT LIKE '%status%' AND sender NOT LIKE '%broadcast%'"
    ).fetchall()
    conn.close()

    clean_senders = []
    for r in rows:
        s = r["sender"]
        digits = re.sub(r'[^0-9]', '', s.split('@')[0])
        if digits not in exclude_nums:
            clean_senders.append(s)
    return clean_senders

def get_stats():
    today = str(date.today())
    conn  = _get_conn()
    total_users   = conn.execute("SELECT COUNT(*) FROM tenant_users WHERE tenant_id='main'").fetchone()[0]
    active_today  = conn.execute("SELECT COUNT(*) FROM tenant_users WHERE tenant_id='main' AND last_msg_date=?", (today,)).fetchone()[0]
    total_msgs    = conn.execute("SELECT SUM(message_count) FROM tenant_users WHERE tenant_id='main'").fetchone()[0] or 0
    total_leads   = conn.execute("SELECT COUNT(*) FROM tenant_leads WHERE tenant_id='main'").fetchone()[0]
    paid_users    = conn.execute("SELECT COUNT(*) FROM tenant_users WHERE tenant_id='main' AND is_paid=1").fetchone()[0]
    conn.close()
    return {
        "total_users":  total_users,
        "active_today": active_today,
        "total_msgs":   total_msgs,
        "total_leads":  total_leads,
        "paid_users":   paid_users
    }

def get_recent_leads(limit=20):
    return get_all_leads(limit=limit)

def get_all_leads(tenant_id=None, limit=50):
    conn = _get_conn()
    if tenant_id and tenant_id != "all":
        rows = conn.execute(
            """SELECT id, tenant_id, sender, message, timestamp
               FROM tenant_leads
               WHERE tenant_id=?
               ORDER BY id DESC LIMIT ?""",
            (tenant_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, tenant_id, sender, message, timestamp
               FROM tenant_leads
               ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_detailed_users(tenant_id=None, limit=200):
    conn = _get_conn()
    if tenant_id and tenant_id != "all":
        rows = conn.execute(
            """SELECT tenant_id, sender, name, first_seen, last_msg_date, message_count, daily_count, is_paid, is_vip, onboarded 
               FROM tenant_users 
               WHERE tenant_id=?
               ORDER BY is_vip DESC, is_paid DESC, message_count DESC, first_seen DESC LIMIT ?""",
            (tenant_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT tenant_id, sender, name, first_seen, last_msg_date, message_count, daily_count, is_paid, is_vip, onboarded 
               FROM tenant_users 
               ORDER BY is_vip DESC, is_paid DESC, message_count DESC, first_seen DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_users(limit=20):
    return get_detailed_users(limit=limit)

def get_all_reminders(limit=50):
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, tenant_id, sender, task, remind_time, created_at, is_sent
           FROM tenant_reminders
           ORDER BY id DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_daily_message_stats(days=14):
    conn = _get_conn()
    rows = conn.execute("""
        SELECT last_msg_date as date, SUM(daily_count) as messages
        FROM tenant_users
        WHERE tenant_id='main'
        GROUP BY last_msg_date
        ORDER BY last_msg_date DESC
        LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_reminder(sender, task, remind_time):
    add_tenant_reminder("main", sender, task, remind_time)

def get_due_reminders(current_time):
    return get_due_tenant_reminders(current_time)

def mark_reminder_sent(reminder_id):
    mark_tenant_reminder_sent(reminder_id)


# ── TENANT ORDERS & PRODUCTS OPERATIONS ───────────────────────────────────────

def create_tenant_order(tenant_id, customer_phone, customer_name, items_summary,
                        product_total=0, delivery_fee=0, total_amount=0,
                        delivery_location="", order_type="preorder", notes=""):
    now = datetime.now().isoformat()
    conn = _get_conn()
    prefix = tenant_id[:3].upper()
    count_row = conn.execute("SELECT COUNT(*) FROM tenant_orders WHERE tenant_id=?", (tenant_id,)).fetchone()
    seq = (count_row[0] if count_row else 0) + 1001
    order_code = f"{prefix}-{seq}"

    while conn.execute("SELECT id FROM tenant_orders WHERE order_code=?", (order_code,)).fetchone():
        seq += 1
        order_code = f"{prefix}-{seq}"

    if not total_amount:
        total_amount = product_total + delivery_fee

    conn.execute("""
        INSERT INTO tenant_orders (
            order_code, tenant_id, customer_phone, customer_name,
            items_summary, product_total, delivery_fee, total_amount,
            delivery_location, order_type, status, payment_proof_received, notes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Order received', 0, ?, ?, ?)
    """, (
        order_code, tenant_id, customer_phone, customer_name,
        items_summary, product_total, delivery_fee, total_amount,
        delivery_location, order_type, notes, now, now
    ))
    conn.commit()
    conn.close()
    return get_tenant_order_by_code(tenant_id, order_code)


def get_tenant_order_by_code(tenant_id, order_code):
    conn = _get_conn()
    if tenant_id:
        row = conn.execute(
            "SELECT * FROM tenant_orders WHERE order_code=? AND tenant_id=?",
            (order_code, tenant_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM tenant_orders WHERE order_code=?",
            (order_code,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_tenant_orders(tenant_id=None, limit=100):
    conn = _get_conn()
    if tenant_id and tenant_id != "all":
        rows = conn.execute(
            "SELECT * FROM tenant_orders WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tenant_orders ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tenant_customer_orders(tenant_id, customer_phone, limit=5):
    conn = _get_conn()
    clean_p = re.sub(r'[^0-9]', '', customer_phone)
    rows = conn.execute(
        """SELECT * FROM tenant_orders 
           WHERE tenant_id=? AND (customer_phone=? OR customer_phone LIKE ?)
           ORDER BY id DESC LIMIT ?""",
        (tenant_id, customer_phone, f"%{clean_p[-10:]}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_tenant_order_status(order_code, new_status, notes=None):
    now = datetime.now().isoformat()
    conn = _get_conn()
    if notes is not None:
        conn.execute(
            "UPDATE tenant_orders SET status=?, notes=?, updated_at=? WHERE order_code=?",
            (new_status, notes, now, order_code)
        )
    else:
        conn.execute(
            "UPDATE tenant_orders SET status=?, updated_at=? WHERE order_code=?",
            (new_status, now, order_code)
        )
    conn.commit()
    conn.close()
    return get_tenant_order_by_code(None, order_code)


def mark_tenant_order_payment_proof(order_code):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute(
        "UPDATE tenant_orders SET payment_proof_received=1, updated_at=? WHERE order_code=?",
        (now, order_code)
    )
    conn.commit()
    conn.close()


def get_tenant_products(tenant_id, category=None, only_active=True):
    conn = _get_conn()
    query = "SELECT * FROM tenant_products WHERE tenant_id=?"
    params = [tenant_id]
    if category:
        query += " AND category=?"
        params.append(category)
    if only_active:
        query += " AND is_active=1"
    query += " ORDER BY category ASC, id ASC"
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_tenant_product(tenant_id, category, name, price, description="", variants="", stock_status="in_stock"):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("""
        INSERT INTO tenant_products (tenant_id, category, name, price, description, variants, stock_status, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (tenant_id, category, name, price, description, variants, stock_status, now))
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid


def update_tenant_product(product_id, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    clause = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE tenant_products SET {clause} WHERE id=?", (*kwargs.values(), product_id))
    conn.commit()
    conn.close()


def delete_tenant_product(product_id):
    conn = _get_conn()
    conn.execute("UPDATE tenant_products SET is_active=0 WHERE id=?", (product_id,))
    conn.commit()
    conn.close()


def seed_eby_beauty_products():
    conn = _get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM tenant_products WHERE tenant_id='eby_beauty'").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    now = datetime.now().isoformat()
    products = [
        # Skincare
        ("eby_beauty", "skincare", "Oriflame Optimals Even Out Set", 38000, "Complete 4-piece set (Cleanser, Serum, Day SPF 20 & Night Cream) targeting dark spots, hyperpigmentation and uneven skin tone.", "Full Set", "in_stock"),
        ("eby_beauty", "skincare", "Oriflame NovAge Skinergise Set", 55000, "5-piece premium anti-fatigue & glow set with Taurine Energy & Acai Plant Stem Cell extract. Tightens pores & boosts youth.", "Full Set", "preorder"),
        ("eby_beauty", "skincare", "Pure Skin 2-in-1 Face Wash & Scrub", 8500, "Deep pore exfoliating wash with Salicylic Acid and pomegranate extract. Clears breakouts & controls shine.", "150ml", "in_stock"),
        ("eby_beauty", "skincare", "Sun 360 High Sunscreen SPF 50", 14500, "Broad spectrum UVA/UVB high protection daily sun lotion. Lightweight, non-greasy, zero white cast.", "50ml", "in_stock"),
        ("eby_beauty", "skincare", "Optimals Hydra Radiance Moisture Serum", 13000, "Deep 24hr moisture serum with hyaluronic acid and Swedish herbal antioxidants for dry & dull skin.", "30ml", "in_stock"),

        # Body Care
        ("eby_beauty", "body_care", "Milk & Honey Gold Nourishing Body Cream", 11000, "Iconic rich moisturizing cream with organically sourced milk & honey extracts. Deeply conditions dry skin.", "250ml", "in_stock"),
        ("eby_beauty", "body_care", "Love Nature Refreshing Exfoliating Shower Gel", 7500, "Energizing organic strawberry & lime shower gel with natural exfoliating seeds.", "250ml", "in_stock"),

        # Fragrance
        ("eby_beauty", "fragrance", "Giordani Gold Essenza Parfum", 35000, "Exquisite luxury floral orange blossom & Tuscan wood fragrance. Long-lasting projection.", "50ml", "in_stock"),
        ("eby_beauty", "fragrance", "Possess Eau de Parfum", 28000, "Intoxicating Queen Cleopatra-inspired scent with ylang-ylang, Indonesian patchouli and vanilla.", "50ml", "in_stock"),
        ("eby_beauty", "fragrance", "Love Potion Sensual Body Mist", 12500, "Alluring chocolate and ginger oriental scent. Perfect for everyday wear.", "75ml", "in_stock"),

        # Makeup
        ("eby_beauty", "makeup", "The ONE Everlasting Sync Foundation SPF 30", 12500, "Smart skin-adapting all-day matte foundation. Sweat-resistant with SPF 30. Available in all Nigerian shades.", "30ml", "in_stock"),
        ("eby_beauty", "makeup", "Giordani Gold Iconic Lipstick SPF 15", 9500, "Satin finish creamy lipstick infused with rejuvenating Argan oil. Rich longwear pigment.", "Standard", "in_stock"),
        ("eby_beauty", "makeup", "The ONE 5-in-1 Wonder Lash Waterproof Mascara", 8000, "Multifunctional mascara: length, volume, curl, separation, and all-day conditioning.", "8ml", "in_stock"),

        # Hair & Beauty
        ("eby_beauty", "hair_beauty", "Love Nature Hot Oil Treatment for Dry Hair", 4500, "Intense conditioning wheat & coconut oil warm treatment tube. Restores dry and damaged hair.", "15ml", "in_stock"),
        ("eby_beauty", "hair_beauty", "Eleo Protecting Hair Oil", 15000, "Luxurious leave-in hair oil with golden argan, rose and burdock oils for silky shine.", "50ml", "in_stock"),

        # Jewellery / Accessories
        ("eby_beauty", "jewellery", "Exquisite Gold-Tone Watch & Bracelet Gift Set", 22000, "Timeless stainless steel gold-tone ladies watch with matching crystal accent bracelet.", "Set", "in_stock")
    ]

    for p in products:
        conn.execute("""
            INSERT INTO tenant_products (tenant_id, category, name, price, description, variants, stock_status, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (*p, now))

    conn.commit()
    conn.close()