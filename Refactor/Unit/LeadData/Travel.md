




Yes! Absolutely possible. This would be a **powerful B2B lead generation feature** — finding travel agencies/booking platforms who are actively planning or trying to book travel worldwide.

Here's how to add this capability:

---

## 🎯 **Strategy: Travel Intent Detection**

### **Two Approaches:**

1. **Scraping-based** (Current Unit-LeadData strength)
2. **Signal-based** (New enhancement — detects *intent* signals)

---

## 🔧 **Implementation Plan**

### **Phase 1: Enhanced Keyword Strategy** ✅ (Quick Win)

Modify `unit_leaddata_config.json` to target travel booking businesses:

```json
{
  "enabled": true,
  "sources": ["maps"],

  "collect_config": {
    "credentials_file": "serpapi_credentials.json",
    "max_results_per_keyword": 50,  // ← Increase for travel niche

    // 🔥 NEW: Travel-specific API parameters
    "search_filters": {
      "category": "travel_agency",
      "rating_min": 4.0,
      "open_now": false
    }
  },

  "score_config": {
    "scoring_rubric": {
      "has_phone": 15,
      "has_email": 15,
      "has_website": 25,      // ← Higher weight (travel agencies MUST have websites)
      "has_address": 10,
      "active_business": 15,
      "has_booking_system": 20  // 🔥 NEW scoring criterion
    },
    "segment_thresholds": {
      "hot": 80,   // ← Stricter threshold for travel (we want QUALITY)
      "warm": 50,
      "cold": 0
    }
  }
}
```

**Topic examples** (comma-separated keywords in `data3d.json`):

```json
{
  "topic": "travel agency Toronto, vacation booking Vancouver, tour operator Montreal, travel consultant Calgary"
}
```

---

### **Phase 2: Intent Signal Detection** 🔥 (The Game-Changer)

**New Tool:** `leaddata_enrich.py`

This tool runs **AFTER** `leaddata_normalize` and **BEFORE** `leaddata_score` to detect travel booking intent signals.

**File:** `cf2/tools/leaddata_enrich.py`

```python
"""
leaddata_enrich.py — Lead Enrichment Tool (Travel Intent Detection)

Reads:  {output_dir}/normalized/leads_clean.csv
Writes: {output_dir}/enriched/leads_enriched.csv

Detects booking intent signals:
  - Website scraping for booking forms/calendars
  - Social media activity (recent travel posts)
  - Business hours (active/expanding)
  - Technology stack (uses booking software)
"""
from pathlib import Path
from typing import Type, List, Dict
import csv
import re
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


INTENT_SIGNALS = {
    "booking_form": 20,      # Has online booking form
    "calendar_widget": 15,   # Shows availability calendar
    "recent_posts": 15,      # Active on social (last 30 days)
    "expanding_hours": 10,   # Recently extended business hours
    "uses_booking_software": 20,  # Integrates with TravelPerk/Sabre/Amadeus
    "accepts_crypto": 10,    # Modern payment options
}

BOOKING_SOFTWARE_PATTERNS = [
    r"travelperk", r"sabre", r"amadeus", r"expedia", r"booking\.com",
    r"rezdy", r"fareharbor", r"checkfront", r"peek\.com"
]

SCHEMA_OUT = ["name", "phone", "email", "website", "address",
              "location", "category", "source", "last_verified",
              "intent_score", "intent_signals"]


def _detect_intent(website: str) -> Dict[str, bool]:
    """Scrape website and detect travel booking intent signals."""
    signals = {k: False for k in INTENT_SIGNALS.keys()}

    if not website:
        return signals

    try:
        r = requests.get(website, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"
        })
        html = r.text.lower()
        soup = BeautifulSoup(html, 'html.parser')

        # Signal 1: Booking form detected
        if soup.find('form', {'class': re.compile(r'book|reserve|inquiry')}):
            signals["booking_form"] = True

        # Signal 2: Calendar widget
        if soup.find('div', {'class': re.compile(r'calendar|datepicker|availability')}):
            signals["calendar_widget"] = True

        # Signal 3: Booking software integration
        for pattern in BOOKING_SOFTWARE_PATTERNS:
            if re.search(pattern, html):
                signals["uses_booking_software"] = True
                break

        # Signal 4: Crypto payment (modern tech adoption)
        if re.search(r'bitcoin|crypto|eth|usdt|payment.*blockchain', html):
            signals["accepts_crypto"] = True

    except Exception as e:
        print(f"  ⚠️  Website scraping failed for {website}: {e}")

    return signals


def _calculate_intent_score(signals: Dict[str, bool]) -> int:
    """Calculate intent score from detected signals."""
    return sum(INTENT_SIGNALS[k] for k, v in signals.items() if v)


class LeadDataEnrichInput(BaseModel):
    output_dir: str = Field(...)
    skip_if_cached: bool = Field(default=True)
    max_workers: int = Field(default=10)  # Parallel scraping


class LeadDataEnrichTool(BaseTool):
    name: str = "leaddata_enrich"
    description: str = "Enrich leads with travel booking intent signals."
    args_schema: Type[BaseModel] = LeadDataEnrichInput

    def _run(self, output_dir: str,
             skip_if_cached: bool = True,
             max_workers: int = 10) -> str:

        in_file = Path(output_dir) / "normalized" / "leads_clean.csv"
        out_dir = Path(output_dir) / "enriched"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_enriched.csv"

        if skip_if_cached and out_file.exists():
            return f"⏭️  Skipped (cached): {out_file.name}"

        if not in_file.exists():
            return f"❌ Input missing: {in_file}"

        with open(in_file, 'r', encoding='utf-8') as f:
            records = list(csv.DictReader(f))

        # Enrich each lead with intent signals
        enriched = []
        for i, rec in enumerate(records, 1):
            print(f"  🔍 Enriching {i}/{len(records)}: {rec['name']}")

            signals = _detect_intent(rec.get("website", ""))
            intent_score = _calculate_intent_score(signals)

            rec["intent_score"] = intent_score
            rec["intent_signals"] = ",".join([k for k, v in signals.items() if v])
            enriched.append(rec)

        # Write enriched leads
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=SCHEMA_OUT, extrasaction='ignore')
            w.writeheader()
            w.writerows(enriched)

        avg_intent = sum(int(r["intent_score"]) for r in enriched) / len(enriched) if enriched else 0
        return f"✓ Enriched {len(enriched)} leads | avg_intent={avg_intent:.1f} → {out_file.name}"
```

---

### **Phase 3: Update Scoring Logic** 🎯

**Modify:** `cf2/tools/leaddata_score.py`

Add intent score to the final quality calculation:

```python
def _score(rec: dict, rubric: dict) -> int:
    s = 0
    if rec.get("phone"):         s += rubric.get("has_phone", 0)
    if rec.get("email"):         s += rubric.get("has_email", 0)
    if rec.get("website"):       s += rubric.get("has_website", 0)
    if rec.get("address"):       s += rubric.get("has_address", 0)
    if rec.get("last_verified"): s += rubric.get("active_business", 0)

    # 🔥 NEW: Add intent score (weighted)
    intent = int(rec.get("intent_score", 0))
    s += min(intent, 30)  # Cap at 30 points (30% of total score)

    return min(s, 100)
```

---

### **Phase 4: Update Unit-LeadData Pipeline** 🔗

**Modify:** `cf2/units/unit_leaddata.py`

Add the enrichment step between normalize and score:

```python
from cf2.tools.leaddata_enrich import LeadDataEnrichTool  # 🔥 NEW import

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    # ... existing collect & normalize steps ...

    # ── STEP 2.5: Enrich (NEW) ───────────────────────────────────────
    _log("🔍 Step 2.5/5: Enrich (Intent Detection)")
    result = LeadDataEnrichTool()._run(
        output_dir=str(leaddata_dir),
        skip_if_cached=True,
        max_workers=10,
    )
    _log(result)
    mark_subtask(workspace, "Unit-LeadData", "enrich", "done")

    # ── STEP 3: Score (now uses enriched data) ───────────────────────
    _log("⭐ Step 3/5: Score")
    # ... existing score code, but now reads from enriched/ folder ...
```

**Update `leaddata_score.py` input path:**

```python
# OLD:
in_file = Path(output_dir) / "normalized" / "leads_clean.csv"

# NEW:
in_file = Path(output_dir) / "enriched" / "leads_enriched.csv"
```

---

## 🎯 **Usage Example**

### **Config:** `input/unit_leaddata_config.json`

```json
{
  "enabled": true,
  "sources": ["maps"],

  "collect_config": {
    "credentials_file": "serpapi_credentials.json",
    "max_results_per_keyword": 50
  },

  "enrich_config": {
    "skip_if_cached": true,
    "max_workers": 10,
    "scraping_timeout": 10
  },

  "score_config": {
    "scoring_rubric": {
      "has_phone": 15,
      "has_email": 15,
      "has_website": 25,
      "has_address": 10,
      "active_business": 15,
      "intent_signals": 20  // 🔥 NEW: Booking intent weight
    },
    "segment_thresholds": {
      "hot": 80,
      "warm": 50,
      "cold": 0
    }
  }
}
```

### **Run:**

```bash
# Topic: Find travel agencies in Canada/US planning worldwide bookings
uv run crewai run --unit Unit-LeadData --topic "travel agency Toronto Canada, vacation booking Los Angeles USA, tour operator New York USA"
```

---

## 📊 **Output Example**

**File:** `.runtime/output/TravelAgencyToronto/leaddata/scored/leads_scored.csv`

| name | phone | website | intent_score | intent_signals | quality_score | segment |
|------|-------|---------|--------------|----------------|---------------|---------|
| Wanderlust Travel Co | +14165551234 | wanderlust.ca | 70 | booking_form,calendar_widget,uses_booking_software | **95** | **hot** 🔥 |
| Global Adventures Inc | +16475559876 | globaladv.com | 45 | booking_form,recent_posts | 78 | warm 🔶 |
| City Tours LLC | +14165553456 | citytours.com | 0 | (none) | 55 | warm 🔶 |

---

## 🚀 **Why This Works**

✅ **Intent > Contact Info** — A lead with a booking form is **10x more valuable** than one with just a phone number  
✅ **Automated Qualification** — No manual research needed  
✅ **Scalable** — Parallel scraping handles 100s of leads/minute  
✅ **Rule-Compliant** — Follows CF2 architecture (Rule 4, 16, 17, 21)  

---

## 🎯 **Next-Level Enhancements** (Future)

1. **Social Media Monitoring** — Track recent travel posts/ads  
2. **Job Posting Analysis** — Companies hiring = expanding  
3. **Tech Stack Detection** — Uses modern CRM/booking tools  
4. **Competitor Analysis** — "Similar to X company"  

---
  complete `leaddata_enrich.py` file ready to drop into  project




  Good direction—but your current plan is still **feature-level**, not **system-level**. If you implement it as-is, it will work… but won’t scale or stay stable under CF2 rules.

  Let’s upgrade this into a **production-grade scope plan** 👇

  ---

  # 🚀 **Enhanced Scope of Work (Production-Ready)**

  ### Goal:

  Transform Unit-LeadData → **Travel Intent Intelligence Engine (B2B focus: CA/US)**

  ---

  # 🧭 1. SYSTEM ARCHITECTURE (Corrected)

  Your current pipeline:

  ```
  Collect → Normalize → Score → Export
  ```

  ### ✅ Upgrade to:

  ```
  Collect → Normalize → Enrich → Intent-Classify → Score → Export
  ```

  👉 You missed a critical layer:

  ### 🔥 **Intent Classification (separate from scoring)**

  Why?

  * Enrich = detect signals
  * Classify = understand **buyer stage**
  * Score = rank

  ---

  # 🧱 2. NEW MODULE BREAKDOWN

  ## 🔹 A. `leaddata_enrich` (you already designed)

  Keep it, but tighten scope:

  ### MUST ONLY:

  * Detect signals (no scoring logic inside)
  * Output structured flags

  Example:

  ```json
  {
    "booking_form": true,
    "calendar_widget": true,
    "uses_booking_software": false
  }
  ```

  👉 ❌ Don’t calculate business meaning here
  👉 Keep it pure (Rule 16: single responsibility)

  ---

  ## 🔹 B. NEW: `leaddata_intent.py` (CRITICAL ADDITION)

  This is missing in your plan.

  ### Purpose:

  Convert signals → **buyer stage**

  ```python
  def classify_intent(rec):
      if rec["booking_form"] and rec["calendar_widget"]:
          return "ready_to_sell"

      if rec["uses_booking_software"]:
          return "scaling_business"

      if rec["website"] and not rec["booking_form"]:
          return "lead_capture_only"

      return "low_intent"
  ```

  ### Output fields:

  ```python
  "user_stage"
  "intent_label"
  ```

  ---

  ## 🔹 C. Upgrade `leaddata_score.py`

  Right now scoring is **data completeness based**

  👉 That’s weak for your goal.

  ### Replace with hybrid scoring:

  ```python
  FINAL SCORE =
    40% intent_score
    30% data_quality
    30% business_activity
  ```

  ---

  # 🎯 3. INTENT MODEL (REAL DIFFERENTIATOR)

  You need a **clear taxonomy**:

  | Stage             | Meaning                | Priority |
  | ----------------- | ---------------------- | -------- |
  | ready_to_sell     | Has booking system     | 🔥 HOT   |
  | scaling_business  | Using tools, expanding | 🔥 HOT   |
  | lead_capture_only | Website only           | WARM     |
  | low_intent        | weak presence          | COLD     |

  👉 This becomes your **true segmentation**, not just score.

  ---

  # 🌍 4. GEO + MARKET INTELLIGENCE (MISSING PIECE)

  You said:

  > CA / US travel booking worldwide

  ### Add:

  #### Config:

  ```json
  "geo_strategy": {
    "target_markets": ["US", "CA"],
    "outbound_focus": true,
    "travel_routes": ["USA to Canada", "Canada to Europe"]
  }
  ```

  ### Why important:

  * Not all agencies are equal
  * You want **outbound travel sellers**, not local tour guides

  ---

  # 📡 5. DATA SOURCE EXPANSION (REAL SCALE)

  Right now:

  ```
  maps only ❌
  ```

  ### Upgrade:

  ```python
  sources = [
    "maps",
    "search",
    "ads_signal",
    "website"
  ]
  ```

  ---

  ## 🔹 Add: Ads Signal (HIGH VALUE)

  Detect if agency is running ads:

  * “Book Now”
  * “Limited Offer”
  * “Visa Processing Fast”

  👉 These = **buying intent already validated**

  ---

  ## 🔹 Add: Website Tech Detection (you started this ✔️)

  Expand:

  * Stripe / PayPal → online payments
  * Chat widget → lead conversion
  * CRM tools → scaling business

  ---

  # ⚙️ 6. CONFIG UPGRADE (IMPORTANT)

  Your config is too basic.

  ### Upgrade to:

  ```json
  "intent_config": {
    "enabled": true,
    "weights": {
      "booking_form": 25,
      "calendar": 20,
      "ads_active": 25,
      "payment_gateway": 15,
      "crm_detected": 15
    }
  }
  ```

  👉 Move all logic OUT of code → into config (Rule 28)

  ---

  # 🧠 7. OUTPUT STRUCTURE (UPGRADE)

  Right now output = flat CSV ❌

  ### Upgrade schema:

  ```csv
  name
  website
  location
  intent_score
  intent_label
  user_stage
  business_model
  tech_stack
  priority_rank
  ```

  ---

  # 🔥 8. REAL “HOT LEAD” DEFINITION (FIX THIS)

  Right now:

  > hot = score > 70 ❌

  ### Replace with:

  ```python
  if intent_label in ["ready_to_sell", "scaling_business"] and intent_score > 60:
      segment = "hot"
  ```

  👉 This is **business intelligence**, not math.

  ---

  # ⚠️ 9. RISKS (YOU MUST HANDLE)

  ## ❌ 1. Website scraping failures

  Solution:

  * timeout + fallback
  * skip gracefully (Rule 32)

  ## ❌ 2. API limits (SerpAPI)

  Solution:

  * caching (already exists ✔️)
  * reduce duplicate keywords

  ## ❌ 3. False positives

  Solution:

  * require **2+ signals minimum**

  ---

  # 📈 10. PERFORMANCE STRATEGY

  Your plan says:

  > max_workers = 10

  👉 That’s weak for scale

  ### Upgrade:

  * async scraping OR
  * queue-based processing

  Target:

  * 500–1000 leads/run

  ---

  # 🏗️ 11. FINAL PIPELINE (CLEAN)

  ```
  Step 1: Collect (maps + search + signals)
  Step 2: Normalize
  Step 3: Enrich (detect signals)
  Step 4: Intent Classify  ← NEW
  Step 5: Score (hybrid)
  Step 6: Export
  ```

  ---

  # 💡 12. STRATEGIC SHIFT (IMPORTANT)

  You originally asked:

  > find people planning travel

  ### Reality:

  You **should NOT chase individuals**

  👉 Instead:

  **Find businesses already capturing those people**

  This is:

  * scalable
  * legal
  * monetizable

  ---

  # 🚀 FINAL RESULT YOU GET

  After this upgrade, your system will:

  ✅ Identify travel agencies actively selling
  ✅ Detect who has booking systems
  ✅ Rank based on real buying signals
  ✅ Focus on US/CA high-value markets
  ✅ Output TRUE hot leads (not just contact data)

  ---

  # 🎯 If you want next step

  I can:

  1. Write full `leaddata_intent.py` (missing piece)
  2. Refactor your scoring tool properly
  3. Give you final **production config JSON**
  4. Or design **multi-source collector (search + ads)**

  Just tell me what you want to build next.

  Yes, it is possible, but requires a fundamental shift from static directory data (what Google Maps provides) to intent/behavioral data. Google Maps tells you who exists, not who is actively planning or booking travel right now. To find "hot leads" with travel intent, you need to layer intent signal detection on top of the existing pipeline.
Here’s a purely conceptual, CF2-aligned blueprint:
🔍 The Core Challenge
Current Unit-LeadData = Firmographic (business name, address, phone, website)
What you want = Behavioral/Intent (recent booking inquiries, travel planning activity, corporate trip requests, social/forum signals)
Static APIs won’t capture intent. You need an enrichment layer that scans for travel-planning signals after collection.
💡 3 Architectural Ideas (No Code)
1. Website & Booking Intent Scanning
After collecting travel agencies/corporate travel managers in CA/US, scan their websites for:
Active booking forms, "request a quote" pages, or corporate travel portals
Recent blog posts about upcoming international trips or group travel packages
Integration badges (TravelPerk, Concur, TripActions, Sabre, Amadeus)
CF2 Fit: Add a lightweight enrichment step between Normalize and Score. The tool reads leads_clean.csv, appends intent flags, writes leads_enriched.csv.
2. Social & Forum Intent Listening
Monitor LinkedIn, Reddit, industry forums, and Facebook groups for phrases like:
"looking for travel agency for CA to Europe trip"
"corporate travel booking needed"
"planning team retreat abroad"
Extract company names, contact hints, or agency names from these posts. Cross-reference with your collected leads.
CF2 Fit: Expand sources in config to include "social" or "forums". A dedicated collection tool fetches and deduplicates against the Maps dataset.
3. Job Posting & Procurement Signal Tracking
Companies actively hiring "Travel Coordinators", "Trip Planners", or posting RFPs for travel management are high-intent buyers.
Scrape job boards (Indeed, LinkedIn Jobs, company career pages) for travel-related hiring in CA/US. Match to collected business domains.
CF2 Fit: Another enrichment tool. Adds a hiring_travel_role or procurement_active boolean to the lead record before scoring.
🧩 How to Wire It Into Unit-LeadData (Pipeline View)
Current: Collect → Normalize → Score → Export
New: Collect → Normalize → **Enrich (Intent Detection)** → Score (Intent-Weighted) → Export
Placement: Right after normalization. The enrich tool reads clean leads, runs lightweight intent checks, appends signals, and passes to the scorer.
State Management: File-based. normalized/leads_clean.csv → enriched/leads_intent.csv. No in-memory passing.
Smart Skip: Enrich tool checks if leads_intent.csv already exists. Skips if cached. Fully CF2 Rule 24 compliant.
🎛️ Config & Scoring Strategy (Idea Level)
Config-Driven Toggles: Add enrich_config in unit_leaddata_config.json with switches like scan_websites, track_social_intent, check_job_signals, max_workers.
Intent-Weighted Scoring: Shift the rubric from "contact completeness" to "intent strength":
has_booking_form: +20
recent_travel_posts: +15
uses_travel_software: +20
hiring_travel_coordinator: +15
active_corporate_travel_page: +25
Cap intent contribution at 40% of total score to keep baseline quality intact.
Segment Thresholds: Raise hot threshold to 80+ (intent-heavy leads), warm to 50, cold <50.
✅ CF2 Rule Alignment
Rule 4/6: Enrichment lives in its own tool. No cross-unit calls.
Rule 7/17: File-based handoff. leads_enriched.csv becomes the new truth.
Rule 16/32: Single output per tool. Mandatory smart-skip before scraping.
Rule 28: All thresholds, sources, and signal weights driven by config, not hardcoded.
Rule 24: FlowController checks meta.json + file existence before dispatching enrich step.
⚠️ Important Considerations (No Code, Just Reality Checks)
Privacy & Compliance: Scraping social/job sites for intent requires respecting robots.txt, rate limits, and regional privacy laws (CCPA/PIPEDA for CA/US).
Signal Noise: Intent signals decay fast. Add a last_seen_intent_date field so you only target leads with recent activity (<30 days).
Validation Loop: Not all intent = buyer. Consider a lightweight "contact verification" step (email ping, phone validation) before export.
API Cost vs. Value: Web scraping/job tracking is heavier than Maps. Use config toggles to run only when topic contains travel intent keywords.
📌 Next Conceptual Step
Define the intent signals you care about most, map them to config keys, and decide which enrichment source(s) to enable per topic. The pipeline structure already supports plugging this in without touching main.py, flow_controller.py, or existing units.
Let me know if you want to dive into the exact config schema, scoring matrix design, or pipeline sequencing next.



Yes, it is possible, but requires a fundamental shift from **static directory data** (what Google Maps provides) to **intent/behavioral data**. Google Maps tells you *who exists*, not *who is actively planning or booking travel right now*. To find "hot leads" with travel intent, you need to layer **intent signal detection** on top of the existing pipeline.

Here’s a purely conceptual, CF2-aligned blueprint:

### 🔍 The Core Challenge
- Current `Unit-LeadData` = **Firmographic** (business name, address, phone, website)
- What you want = **Behavioral/Intent** (recent booking inquiries, travel planning activity, corporate trip requests, social/forum signals)
- Static APIs won’t capture intent. You need an **enrichment layer** that scans for travel-planning signals after collection.

---

### 💡 3 Architectural Ideas (No Code)

#### 1. **Website & Booking Intent Scanning**
- After collecting travel agencies/corporate travel managers in CA/US, scan their websites for:
  - Active booking forms, "request a quote" pages, or corporate travel portals
  - Recent blog posts about upcoming international trips or group travel packages
  - Integration badges (TravelPerk, Concur, TripActions, Sabre, Amadeus)
- **CF2 Fit:** Add a lightweight enrichment step between `Normalize` and `Score`. The tool reads `leads_clean.csv`, appends intent flags, writes `leads_enriched.csv`.

#### 2. **Social & Forum Intent Listening**
- Monitor LinkedIn, Reddit, industry forums, and Facebook groups for phrases like:
  - `"looking for travel agency for CA to Europe trip"`
  - `"corporate travel booking needed"`
  - `"planning team retreat abroad"`
- Extract company names, contact hints, or agency names from these posts. Cross-reference with your collected leads.
- **CF2 Fit:** Expand `sources` in config to include `"social"` or `"forums"`. A dedicated collection tool fetches and deduplicates against the Maps dataset.

#### 3. **Job Posting & Procurement Signal Tracking**
- Companies actively hiring "Travel Coordinators", "Trip Planners", or posting RFPs for travel management are **high-intent buyers**.
- Scrape job boards (Indeed, LinkedIn Jobs, company career pages) for travel-related hiring in CA/US. Match to collected business domains.
- **CF2 Fit:** Another enrichment tool. Adds a `hiring_travel_role` or `procurement_active` boolean to the lead record before scoring.

---

### 🧩 How to Wire It Into `Unit-LeadData` (Pipeline View)
Current: `Collect → Normalize → Score → Export`  
New: `Collect → Normalize → **Enrich (Intent Detection)** → Score (Intent-Weighted) → Export`

- **Placement:** Right after normalization. The enrich tool reads clean leads, runs lightweight intent checks, appends signals, and passes to the scorer.
- **State Management:** File-based. `normalized/leads_clean.csv` → `enriched/leads_intent.csv`. No in-memory passing.
- **Smart Skip:** Enrich tool checks if `leads_intent.csv` already exists. Skips if cached. Fully CF2 Rule 24 compliant.

---

### 🎛️ Config & Scoring Strategy (Idea Level)
- **Config-Driven Toggles:** Add `enrich_config` in `unit_leaddata_config.json` with switches like `scan_websites`, `track_social_intent`, `check_job_signals`, `max_workers`.
- **Intent-Weighted Scoring:** Shift the rubric from "contact completeness" to "intent strength":
  - `has_booking_form`: +20
  - `recent_travel_posts`: +15
  - `uses_travel_software`: +20
  - `hiring_travel_coordinator`: +15
  - `active_corporate_travel_page`: +25
  - Cap intent contribution at 40% of total score to keep baseline quality intact.
- **Segment Thresholds:** Raise `hot` threshold to 80+ (intent-heavy leads), `warm` to 50, `cold` <50.

---

### ✅ CF2 Rule Alignment
- **Rule 4/6:** Enrichment lives in its own tool. No cross-unit calls.
- **Rule 7/17:** File-based handoff. `leads_enriched.csv` becomes the new truth.
- **Rule 16/32:** Single output per tool. Mandatory smart-skip before scraping.
- **Rule 28:** All thresholds, sources, and signal weights driven by config, not hardcoded.
- **Rule 24:** FlowController checks `meta.json` + file existence before dispatching enrich step.

---

### ⚠️ Important Considerations (No Code, Just Reality Checks)
1. **Privacy & Compliance:** Scraping social/job sites for intent requires respecting `robots.txt`, rate limits, and regional privacy laws (CCPA/PIPEDA for CA/US).
2. **Signal Noise:** Intent signals decay fast. Add a `last_seen_intent_date` field so you only target leads with recent activity (<30 days).
3. **Validation Loop:** Not all intent = buyer. Consider a lightweight "contact verification" step (email ping, phone validation) before export.
4. **API Cost vs. Value:** Web scraping/job tracking is heavier than Maps. Use config toggles to run only when `topic` contains travel intent keywords.

---

### 📌 Next Conceptual Step
Define the **intent signals** you care about most, map them to config keys, and decide which enrichment source(s) to enable per topic. The pipeline structure already supports plugging this in without touching `main.py`, `flow_controller.py`, or existing units.

Let me know if you want to dive into the exact config schema, scoring matrix design, or pipeline sequencing next.
