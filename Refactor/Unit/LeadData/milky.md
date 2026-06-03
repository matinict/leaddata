Yes — I understand. I've reviewed the reference documents (`Rule.md`, `tasks.yaml`, `agents.yaml`, `crew.py`, `flow_controller.py`) and will align all subsequent responses with the CF2 framework, your TravelOnly business context, and the B2C traveler-lead strategy.

---

### 🎯 Hot Lead Strategy for "All Inclusive" (TravelOnly)

Based on `milky.travelonly.com`, you need **B2C travelers actively planning all-inclusive vacations** — not agencies. Here's the exact, production-ready setup:

### ✅ STEP 1: Update `input/profile/travelonly.json`
Use **all-inclusive destination keywords** that trigger reviewer mining at the point of travel intent:

```json
{
  "topic": "all inclusive Cancun, all inclusive Punta Cana, all inclusive Jamaica, all inclusive Mexico, all inclusive Caribbean",
  "Unit-Scout": false,
  "Unit-Data": false,
  "Unit-LeadData": true,
  "Unit-Debate": false,
  "Unit-Prodcast": false,
  "Unit-Classroom": false,
  "Unit-Definition": false,
  "Unit-Animation": false,
  "Unit-Comparison": false,
  "Unit-Packaging": false,
  "Unit-Publisher": false,
  "Unit-Advertise": false,
  "leaddata_config_file": "input/unit_leaddata_config.json"
}
```

### ✅ STEP 2: Ensure `input/unit_leaddata_config.json` is B2C-Optimized
```json
{
  "_comment": "CF2 Unit-LeadData: PURE B2C All-Inclusive Traveler Leads",
  "_version": "3.2.0",
  "enabled": true,
  "sources": ["maps_reviewers"],
  "collect_config": {
    "credentials_file": "serpapi_credentials.json",
    "api_endpoint": "https://serpapi.com/search.json",
    "engine": "google_maps",
    "search_type": "search",
    "request_timeout": 60,
    "max_results_per_keyword": 100,
    "skip_if_cached": true,
    "reviewer_mining": {
      "enabled": true,
      "review_recency_days": 90,
      "min_reviewer_activity": 3
    }
  },
  "score_config": {
    "scoring_rubric": {
      "is_traveler": 50,
      "recent_traveler": 30,
      "frequent_reviewer": 15,
      "has_email": 3,
      "has_phone": 2
    },
    "segment_thresholds": { "hot": 60, "warm": 35, "cold": 0 }
  },
  "export_config": {
    "formats": ["csv", "json"],
    "generate_stats": true,
    "stats_file": "lead_stats.json",
    "include_segments_breakdown": true
  }
}
```

### ✅ STEP 3: Run the Pipeline
```bash
make travelonly
```

### 📈 Expected Output (All-Inclusive B2C Travelers)
```
🔍 Mining travelers who reviewed 'all inclusive Cancun'...
  🔍 Finding hotels in 'all inclusive Cancun'...
    📍 Fetching reviews → Wyndham Grand Cancun All Inclusive
      ✅ Extracted 12 travelers from this hotel
    📍 Fetching reviews → Moon Palace Cancun All Inclusive
      ✅ Extracted 18 travelers from this hotel
  📊 'all inclusive Cancun' → 52 traveler leads extracted
✓ Collected 147 leads: 147 travelers + 0 agencies → leads_raw.csv
```

### 📊 Sample Hot Lead Output
```csv
name,location,destination_visited,review_date,review_count,intent_score,quality_score,segment
Jessica Martinez,"Miami, FL","all inclusive Cancun","1 week ago",12,80,95,hot 🔥
David Thompson,"Chicago, IL","all inclusive Punta Cana","3 days ago",8,80,92,hot 🔥
Amanda Lee,"Toronto, ON","all inclusive Jamaica","2 weeks ago",15,80,88,hot 🔥
```

### 🔑 Why This Works for TravelOnly
| Element | Why It Targets All-Inclusive Buyers |
|---------|-------------------------------------|
| `topic: "all inclusive Cancun"` | Searches for hotels with "all inclusive" in name/description → extracts reviewers who actually stayed there |
| `sources: ["maps_reviewers"]` | Only extracts people, never agencies or hotels |
| `is_traveler: 50` scoring | Immediately boosts traveler profiles to "hot" tier |
| `review_recency_days: 90` | Captures travelers who just returned → likely planning next trip |
| `min_reviewer_activity: 3` | Filters out bots, keeps genuine travelers |

### 🚀 Next: Enrich & Push to CRM
Once you have the traveler list:
1. **Enrich contacts**: Add an OSINT tool to find emails/phones for high-score leads.
2. **CRM sync**: Push "hot" leads to your CRM with tags: `all-inclusive-intent`, `recent-traveler`, `north-america`.
3. **Outreach**: Trigger personalized emails: *"Loved your Cancun review! Ready for your next all-inclusive escape?"*

Drop the updated files. Run `make travelonly`. You'll get **actionable B2C all-inclusive traveler leads** — ready for TravelOnly outreach. 🔥
