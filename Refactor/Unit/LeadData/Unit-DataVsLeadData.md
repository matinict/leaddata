# Unit-Data Vs LeadData

---

## 🧠 🎯 Core Difference

> **Unit-Data (production)** = stable, strict, rule-based
> **Unit-LeadData (planning)** = experimental, flexible, growth-oriented

---

## 🔷 1. Unit-Data [PRODUCTION]

👉 This already exists in your system (based on your structure and rules)

From your setup (see ):

* Uses `input/data.json`
* Uses `input/data.schema.json`
* Strict path system (`OUTPUT_ROOT`)
* Controlled by meta.json (status, skip, lock)

---

## 🎯 Purpose

> “Provide clean, structured, reliable data for video generation”

---

## ⚙️ Characteristics

### ✅ Stable

* schema fixed
* predictable output

### ✅ Deterministic

* same input → same output

### ✅ Integrated

* tightly connected with:

  * Unit-Debate
  * Unit-Packaging
  * rendering pipeline

---

## 📦 Output Type

```text
structured video data

example:
- arguments
- segments
- metadata
```

👉 NOT leads
👉 NOT external business data

---

## 🚫 What it should NOT do

* ❌ scraping
* ❌ API calling (dynamic sources)
* ❌ lead collection
* ❌ enrichment experiments

---

# 🔷 2. Unit-LeadData [PLANNING / NEW]

👉 This is what you are designing

---

## 🎯 Purpose

> “Collect real-world business/user data from multiple sources”

---

## ⚙️ Characteristics

### 🔥 Dynamic

* APIs
* scraping
* directories

### 🔥 Non-deterministic

* results change
* depends on external data

### 🔥 Expandable

* new sources anytime

---

## 📦 Output Type

```text
CSV datasets

- leads_raw.csv
- leads_clean.csv
- leads_enriched.csv
```

---

## 💡 Data Nature

| Type      | Unit-Data      | Unit-LeadData                     |
| --------- | -------------- | --------------------------------- |
| Source    | internal       | external                          |
| Stability | high           | variable                          |
| Format    | strict         | evolving                          |
| Use case  | video pipeline | business / content / monetization |

---

# ⚠️ CRITICAL DESIGN RULE

## ❌ NEVER merge them

Bad idea:

```text
Unit-Data → add scraping → leads → chaos
```

👉 This will break your whole CF2 pipeline

---

## ✅ Keep separation

```text
Unit-Data        → video system
Unit-LeadData    → lead system
```

---

# 🔗 HOW THEY CONNECT (SMART WAY)

👉 They SHOULD connect — but indirectly

---

## ✅ Connection via Unit-Content

```text
Unit-LeadData
   ↓
Unit-LeadIntelligence
   ↓
Unit-Content
   ↓
Unit-Data (optional input)
```

---

### Example

1. LeadData:

   * scrape “AI companies”

2. Intelligence:

   * find top companies

3. Content:

   * generate topic:

     > “Top AI Companies 2026”

4. Unit-Data:

   * uses topic to generate structured debate/video

---

👉 So:

> LeadData feeds ideas → Unit-Data produces structured content

---

# 🧠 THINK LIKE THIS

## Unit-Data = “Script Brain”

* structured
* controlled
* safe

---

## Unit-LeadData = “Reality Scanner”

* messy
* powerful
* money-driven

---

# 🔥 Practical Example (YOUR SYSTEM)

## 🎬 Your current system:

```text
Topic → Unit-Data → Debate → Video
```

---

## 🚀 With Lead System:

```text
Market Data → Unit-LeadData
                ↓
          Insights
                ↓
           Topics
                ↓
            Unit-Data
                ↓
             Video
                ↓
           Lead Capture
```

---

# 💡 FINAL POSITIONING (VERY IMPORTANT)

👉 Don’t think:

> “LeadData vs Data”

Think:

> “LeadData → feeds → Data”

---

# ⚡ Clean Separation Summary

## 🟦 Unit-Data (Production Core)

* input-driven
* schema strict
* video-focused
* stable

---

## 🟧 Unit-LeadData (Growth Engine)

* source-driven
* flexible
* business-focused
* experimental

---

# 🚀 My Honest Advice

If you keep this separation:

👉 your system becomes **enterprise-level**

If you mix them:

👉 system becomes **fragile + unscalable**

---

# 🔥 If you want next step

I can design:

👉 exact **interface between LeadData → Unit-Data**
👉 how to auto-generate **topics from leads**
👉 how to turn leads into **viral debate scripts**

---
