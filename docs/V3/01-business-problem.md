# Business Problem: Card-Linked Offers for ABC Bank

**Project:** Customer Spend Analytics, v3 (Offers Platform)
**Author:** Lakshmi
**Status:** Draft for review, October 2026
**Related docs:** `00-roadmap.md` · `02-architecture.md` (next) · `adr/` (decision records)

> All companies, people, and figures in this document are fictional or illustrative.
> Figures marked *assumption* are planning inputs, not market data.

---

## 1. Summary

ABC Bank is a fictional US regional bank with about 5 million cardholders. It wants to give its customers more reasons to use its debit and credit cards and its digital banking channels (mobile app and web banking). Merchants want to reach new and lapsed customers and pay only when a customer actually spends. Neither side can build the bridge alone:

- The bank has the spend data but no merchant relationships and no offer-targeting capability.
- Merchants have marketing budgets but, by law and by policy, can never see the bank's customer data.

The **Offers Platform** is a third party that sits between them. It runs a **card-linked offers (CLO)** program:

1. It receives the bank's transaction data under a data-sharing agreement.
2. It tokenizes the data so no personal data is ever used for analytics.
3. It learns each customer's spending patterns.
4. It returns personalized merchant offers to the bank every night.
5. It closes the loop by detecting which offers were redeemed, then bills merchants and reports results.

The bank earns a revenue share and a more engaged customer base. Customers earn cash back. Merchants get measurable, pay-for-performance marketing.

This document defines that business problem, the value each party gets, how success is measured, and the constraints the data platform must respect. The architecture follows from it.

---

## 2. The three parties and what each wants

| Party | Who they are | What they want | What they are afraid of |
|---|---|---|---|
| **ABC Bank** | Data provider and offer distributor. Regional bank; offers appear in both its mobile app and its web banking site, and customers can activate them from either. | Card "top-of-wallet" status, digital engagement, new non-interest revenue | Data breaches, regulatory findings, vendor risk, a cluttered or irrelevant digital experience |
| **Offers Platform** | Third-party analytics and offers operator (this project) | Accurate targeting, trustworthy attribution, low cost per transaction processed, ability to onboard more banks | Losing a bank's trust over data handling; merchants disputing results; runaway cloud cost at national scale |
| **Merchants** | Advertisers that fund the offers (restaurants, retail, travel, and so on) | New and repeat customers, spend they can verify, and paying only for results | Paying for sales that would have happened anyway; opaque reporting |
| **Cardholders** | ABC Bank's customers | Relevant savings with no extra effort | Feeling tracked; spam |

---

## 3. Problem statements

**For ABC Bank.** Cardholders have many cards in their wallets. ABC Bank needs a differentiated, low-cost reason for customers to choose its card and log in to its mobile app or web banking, without building a merchant network or an offers engine itself.

**For merchants.** Traditional discounts and digital ads are paid for up front and are hard to tie to actual sales. Merchants need a channel where they pay only when a targeted customer actually spends, with reporting they trust.

**For the Offers Platform (the data engineering problem).** The platform must:

- reliably take in a bank's daily transaction and customer-change data;
- strip or tokenize all personal data at a controlled trust boundary;
- maintain accurate customer profiles that track how those customers change over time;
- produce relevant offers every night on time;
- match later transactions to offers to determine redemptions;
- bill and report to merchants accurately;
- do all of the above at national-bank scale, auditably and at a cost per transaction that keeps the business profitable.

---

## 4. How the business loop works

```
       ┌──────────────────── ABC BANK ────────────────────┐
       │  Core banking system      Mobile app + Web banking│
       │  (customers, cards,       (show offers; customer │
       │   transactions)            activates in either)  │
       └──────┬──────────────────────────▲────────┬───────┘
   (1) daily  │                    (4) nightly    │ (5) daily
   transactions + customer changes  offer file    │ activation events
              ▼                          │        ▼
       ┌──────────────────── OFFERS PLATFORM ─────────────┐
       │ (2) tokenize & profile  →  (3) select offers      │
       │ (6) match later spend to activated offers         │
       │ (7) bill merchants, pay bank share, fund cashback │
       └──────────────────────────┬──────────────────────┘
                                  │ (8) monthly results report
                                  ▼
                              MERCHANTS
```

1. ABC Bank sends yesterday's card transactions and any changes to customer records.
2. The platform tokenizes personal data and updates spend profiles and segments.
3. It ranks the merchant offers available to each customer.
4. It sends a nightly offer file back to the bank. A small random **holdout group** (about 5%) is recorded but receives no offers.
5. ABC Bank shows each customer's offers in both its mobile app and its web banking site, and the customer can activate an offer from either one. The bank sends all activation events back daily, each tagged with its channel (`mobile` or `web`). An offer counts as activated once, whichever channel it was activated in.
6. Later transactions at a participating merchant by a customer with an activated offer count as a **redemption**.
7. Merchants are billed a fee on redeemed spend. Part of the fee funds the customer's cash back and part is shared with the bank.
8. Merchants receive monthly campaign results.

**Attribution approach (v3).** v3 uses **simple attribution**: a redemption is counted when an activated customer spends at the merchant within the offer window. It's easy to explain, but it overstates value, because some of that spend would have happened anyway.

The holdout flag is recorded **from day one** so that a later release can measure **incremental lift**, the extra spend in the offer group compared with the holdout group. A randomized control group cannot be created after the fact, so this costs one column now and saves months of waiting later.

---

## 5. Value: an illustrative business case for ABC Bank

All inputs below are *assumptions* for a regional bank and are meant to show the shape of the economics, not to predict them.

| Input | Value |
|---|---|
| Cardholders | 5,000,000 |
| Digitally active customers (use the mobile app or web banking; 60%) | 3,000,000 |
| Customers who activate at least one offer each month (10% of digital) | 300,000 |
| Qualifying purchases (redemptions) per activating customer, per month | 1.5 purchases |
| Average amount **per redeemed purchase** | $60 |
| → Redeemed spend per activating customer, per month (1.5 × $60) | $90 |
| Merchant fee, **charged on each redeemed purchase** (paid by the merchant) | 15% → $9 on a $60 purchase |
| Split of that fee **per redeemed purchase**: customer cash back / bank share / platform | 7 / 4 / 4 pts → $4.20 / $2.40 / $2.40 |

| Result | Monthly | Annual |
|---|---|---|
| Redemptions (300,000 customers × 1.5 purchases) | 450,000 | 5.4M |
| Redeemed (attributed) merchant spend (450,000 × $60) | $27.0M | $324M |
| Merchant fees | $4.05M | $48.6M |
| Cash back to ABC Bank customers | $1.89M | $22.7M |
| **Revenue share to ABC Bank** | **$1.08M** | **$12.96M** |
| Platform revenue | $1.08M | $12.96M |

On top of the revenue share, the bank gets value that is real but harder to price: more mobile and web banking logins, more card use (interchange revenue), and better retention.

**Unit economics for the platform.**

| Step | Value |
|---|---|
| Platform revenue per month | $1.08M |
| Card transactions the platform processes per month (all ABC Bank spend, not just redemptions) | ~200M |
| **Revenue per million transactions processed** ($1.08M ÷ 200) | **~$5,400** |
| **FinOps target: cloud run cost ≤ 1% of revenue** | **≤ ~$54 per million transactions** (≈ $10,800 per month at regional scale) |

The platform must process every transaction to find the few that are redemptions, so cloud cost scales with total volume while revenue scales with redemptions. The 1% target keeps data infrastructure a rounding error in the business. In the portfolio build we will measure the actual cost per million transactions at each scale factor and report it against this target.

---

## 6. Success metrics

### Business KPIs (what the parties judge us on)
| KPI | Owner | Initial target |
|---|---|---|
| Offer activation rate (activating customers ÷ digital customers) | Bank | ≥ 10% monthly |
| Redemption rate (redemptions ÷ activations) | Merchants | Tracked per campaign |
| Attributed merchant spend | Merchants | Tracked per campaign |
| Bank revenue share delivered | Bank | Reconciles to merchant billing to the cent |
| Merchant billing disputes | Platform | < 1% of invoices |

### Data platform service levels (what the data engineering team owns)
| Service level | Target |
|---|---|
| Nightly offer file delivered to the bank | By 05:00 ET, ≥ 99% of days |
| Data freshness | Profiles reflect all transactions through the previous day (T+1) |
| Monthly merchant reports | By the 3rd business day of each month |
| Personal data downstream of the tokenization boundary | Zero findings from Amazon Macie scans of curated zones |
| Pipeline run success without manual intervention | ≥ 99% |
| Reprocessing a past month (backfill) | Completes within one business day |
| Data quality | All blocking checks pass before any file leaves the platform |

### FinOps metrics
| Metric | Target |
|---|---|
| Cost per million transactions processed | Measured at SF100 and SF5000; production goal ≤ $54 |
| Cost per offer delivered | Measured and trended |
| Share of spend carrying cost-allocation tags | 100% |
| Monthly spend vs. budget (portfolio build) | Within the Lean / Working posture limits |

---

## 7. Data exchanged

| Feed | Direction | Cadence | Contains personal data? |
|---|---|---|---|
| Card transactions (CDC from core banking) | Bank → Platform | Daily | Yes in raw-intake mode; no in pre-tokenized mode |
| Customer and account changes (CDC) | Bank → Platform | Daily | Same as above |
| Merchant and campaign catalog | Merchants → Platform | On change | No |
| Offer file (per-customer offers, holdout flag) | Platform → Bank | Nightly | Tokens only; the bank maps them back |
| Offer activation events (from mobile app and web banking; each tagged with channel) | Bank → Platform | Daily | Tokens only |
| Merchant campaign results | Platform → Merchants | Monthly | No; aggregated only |
| Settlement (bank share, cash back amounts) | Platform → Bank | Monthly | Tokens only |

**Two intake modes.** Tokenization is a capability of the platform, so the platform supports both kinds of bank:

- **Raw-intake mode.** The bank sends raw data and the platform tokenizes it inside a locked-down quarantine zone. The raw files are deleted automatically once tokenization succeeds.
- **Pre-tokenized mode.** Banks that tokenize on their side skip the quarantine zone entirely.

ABC Bank uses raw-intake mode, so v3 exercises the harder path.

---

## 8. Constraints

**Privacy and regulation.**
- Customer financial data is protected under US financial privacy rules (for example, the Gramm-Leach-Bliley Act).
- Card data handling must follow industry security standards (PCI DSS); full card numbers are never stored downstream of intake.
- As a third-party service provider, the platform will be subject to the bank's vendor risk management, which means audit trails, access reviews, and evidence of encryption and data deletion.
- Merchants never receive customer-level data.

**Scale.** We design for a national bank and run at regional scale:

| | Regional (what we run) | National (what we design for) |
|---|---|---|
| Cardholders | 5M (scale factor 5,000) | 50M (scale factor 50,000) |
| Transactions per month | ~200M | ~2B |
| Approx. compressed storage per month (*assumption*: ~60 bytes per row) | ~12 GB | ~120 GB |
| 24-month history | ~290 GB | ~2.9 TB |

Scale factor 1 is today's dataset: 1,000 customers and 1.6M transactions over 24 months.

**Timeliness.** v3 is batch only: nightly offers and monthly reports. Real-time offers at the point of sale are out of scope.

**Cost.** The portfolio build follows a Lean posture (everything torn down between sessions, about $50–100 per month), stepping up to a Working posture (about $150–300 per month) during heavy build weeks.

---

## 9. Scope

**In v3**
- Three-account AWS setup (ABC Bank, Offers Platform, and a management account that also provides shared services)
- ABC Bank core-banking database on RDS Postgres, with CDC through DMS
- Both intake modes, with platform-side tokenization in raw-intake mode
- Iceberg lakehouse on S3 with full change history for customers (slowly changing dimensions, Type 2)
- Nightly offers with the holdout flag; activation feed; simple attribution
- Merchant results and bank settlement delivered as S3 files
- Athena for exploration and audit; Redshift Serverless for serving marts
- MWAA and Step Functions with clearly separate roles
- FinOps guardrails and the cost-per-million-transactions metric
- A scale test at regional scale (scale factor 5,000)

**Later releases**
- Incremental lift measurement against the holdout group
- QuickSight dashboards for merchants
- Snowflake (the legacy platform) reading the same Iceberg tables
- Additional ABC Bank use cases on the shared enterprise (for example, fraud and regulatory reporting)

**Out of scope**
- Real-time offers at the point of sale
- The bank's mobile app and web banking site themselves; we simulate activation events from both channels
- Actual payment movement; settlement amounts are produced as files only

---

## 10. Risks and open questions

| Risk | Impact | Mitigation |
|---|---|---|
| Raw personal data leaks past the quarantine zone | Severe: breach of contract and regulation | Isolated zone and encryption key, column checks that fail the pipeline, Macie scans, automatic deletion |
| Simple attribution overstates value and merchants push back | Billing disputes | Transparent methodology; holdout flag in place for the lift upgrade |
| Late-arriving transactions change past redemptions | Restated reports and invoices | 7-day restatement window; reports versioned |
| Costs grow faster than volume at national scale | Unprofitable unit economics | Scale-factor cost testing, tagging, budgets, scan limits |
| Customer record changes (address, income band) corrupt history | Wrong targeting and audit gaps | Type 2 history from CDC |

**Decisions (October 20, 2026)**
- **Restatement window: 7 days.** Transactions that arrive up to 7 days late can still create or change redemptions; after that, the month's results are final.
- **Retention: 4 weeks in each zone, then archived to cold storage** through S3 lifecycle rules, with two exceptions:
  - **Quarantine zone (raw PII):** files are **deleted** as soon as tokenization succeeds. They are never archived.
  - **Curated history:** after 4 weeks it moves to **S3 Glacier Instant Retrieval**, which Athena can still query. That keeps the 24 months of history the models need available without a restore step.
- **Settlement is calculated per redemption.** The bank's share (4 pts), the customer's cash back (7 pts), and the platform's share (4 pts) are computed on each redeemed purchase and then summed onto the monthly invoice. Every cent traces back to a specific purchase.

---

## 11. Glossary

- **CLO (card-linked offer):** a merchant offer tied to a customer's card that is redeemed simply by paying with that card.
- **Activation:** the customer choosing an offer in the bank's mobile app or web banking site, which makes it eligible for redemption.
- **Redemption:** a qualifying purchase at the merchant after activation, within the offer window.
- **Attribution:** deciding which spend counts as caused by an offer.
- **Holdout group:** a random set of customers who are eligible but receive no offers, used later to measure incremental lift.
- **Incremental lift:** spend in the offer group minus spend in the holdout group.
- **CDC (change data capture):** streaming the changes in a source database instead of re-copying it.
- **SCD Type 2:** keeping a full history of how a record changed, with effective dates.
- **Scale factor (SF):** a size multiplier for the synthetic data; SF1 is 1,000 customers.
