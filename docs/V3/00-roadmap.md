# v3 Roadmap: Enterprise-Scale Card-Linked Offers Platform

**Project:** Customer Spend Analytics, v3 (Offers Platform)
**Author:** Lakshmi
**Status:** Agreed plan, October 11, 2026 · updated October 20, 2026 to match the Business Problem decisions
**Capacity:** 35 hours per week, including AWS Certified Data Engineer – Associate (DEA-C01) exam study until the exam
**Related docs:** `01-business-problem.md` · `02-architecture.md` (Phase 0) · `adr/`

---

## 1. Decisions already made

| Area | Decision |
|---|---|
| Business model | Third party: ABC Bank → Offers Platform → merchants, including the redemption loop and merchant reporting |
| Attribution | Simple attribution in v3; a holdout flag recorded from day one; incremental lift added later |
| Scale | Design for national (scale factor 50,000, ~2B transactions/month); run at regional (scale factor 5,000, ~200M/month) |
| Source system | ABC Bank core banking on RDS Postgres; change data capture with DMS; Type 2 history for customers |
| Tokenization | A platform capability with two intake modes: raw (tokenize in a quarantine zone) and pre-tokenized (skip it) |
| Outbound to bank | Nightly offer file to S3; batch only |
| Offer channels | Offers shown in both ABC Bank's mobile app and web banking; customers activate from either; activation events carry a `mobile`/`web` channel tag; an offer counts as activated once |
| Late data | 7-day restatement window; after that a month's results are final |
| Settlement | Calculated per redemption (cash back 7 pts, bank 4 pts, platform 4 pts), then summed onto the monthly merchant invoice |
| Retention | 4 weeks per zone, then cold storage. Exceptions: quarantine raw PII deleted right after tokenization; curated history moves to S3 Glacier Instant Retrieval so Athena can still query it |
| Merchant reporting | Monthly S3 files first; QuickSight added later as a showcase |
| Platform | AWS-native lakehouse: S3 + Iceberg + Glue Data Catalog + Lake Formation |
| Query engines | Athena for exploration, data quality, and audit on the lake; Redshift Serverless as the serving warehouse for marts |
| Orchestration | Step Functions for event-driven, per-batch AWS workflows; MWAA for the nightly business-calendar workflow, backfills, and cross-product dependencies. Airflow triggers Step Functions where they meet |
| Legacy | Snowflake kept as the legacy platform; current Phase 2 stack stays until retired |
| AWS accounts | Three accounts (small-organization compromise): **Management + Shared Services** (new), **ABC Bank** (new), **Offers Platform** (existing account) |
| Repos | `customer-spend-analytics` evolves into v3 (the Offers Platform); new `abc-bank` repo for the bank's side and future bank-internal projects |
| FinOps posture | Lean by default (~$50–100/month); Working (~$150–300/month) during heavy build weeks |
| Docs and tracking | Design docs in each repo's `docs/` folder; work tracked in GitHub Issues |

### Default engineering standards (apply unless an ADR says otherwise)
- Single region, us-east-1. Multi-region disaster recovery is described in the architecture doc but not built.
- Human access through IAM Identity Center only; no IAM users.
- Terraform for all infrastructure, with remote state in S3 and locking; one state per account.
- GitHub Actions deploys through OIDC; no long-lived access keys.
- Customer-managed KMS keys per account and per sensitive zone, with cross-account key policies.
- Lake Formation tag-based access control.
- Glue Data Quality at intake; dbt tests in the warehouse.
- Every resource carries mandatory cost-allocation tags: `data-product`, `environment`, `owner`, `cost-center`.

---

## 2. Timeline at a glance

| Phase | Dates (2026–27) | Hours | Outcome |
|---|---|---|---|
| **0. Design, exam, spikes** | Oct 12 – Oct 28 | ~85 | Business and architecture docs, ADRs, three spikes, **DEA-C01 exam** |
| Rest and buffer | Oct 29 – Nov 1 | – | |
| **1. Foundations** | Nov 2 – Nov 8 | 35 | Accounts, Identity Center, Terraform state, networking, keys, lake buckets, FinOps guardrails |
| **2. ABC Bank source** | Nov 9 – Nov 15 | 35 | RDS core banking, scale-factor generator, DMS CDC, cross-account feed |
| **3. Intake and lakehouse** | Nov 16 – Nov 29 | ~60 (Thanksgiving week lighter) | Dual intake modes, quarantine and tokenization, Iceberg tables, Type 2 history, data quality, Step Functions |
| **4. Transform, offers, orchestration** | Nov 30 – Dec 13 | 70 | dbt on Redshift, offer ranking with holdout flag, nightly offer file, activation feed, MWAA nightly DAG |
| **5. Attribution and reporting** | Dec 14 – Dec 20 | 35 | Redemption matching, merchant reports, bank settlement files |
| Holiday buffer | Dec 21 – Jan 3 | light | Catch-up, documentation |
| **6. Scale test and FinOps report** | Jan 4 – Jan 10 | 35 | Run at SF100, then SF5000; tune; publish cost per million transactions |
| **7. Showcase** | Jan onward, at a lighter pace once the Georgia Tech term starts | flexible | QuickSight, incremental lift, Snowflake reading Iceberg, interview materials |

The core build (Phases 1–6) is planned to finish before the Georgia Tech term begins in January.

---

## 3. Phase 0 in detail (Oct 12 – Oct 28)

**Goal:** pass DEA-C01 and finish a design that interviewers can probe. Each spike uses a service you haven't built with yet, so the hands-on work reinforces the exam.

**Exam rule:** book (or confirm) the Oct 28 slot once you score **80% or higher on two consecutive Tutorials Dojo mock exams**. If you're not there by Oct 24, move the exam rather than sit it unready.

### Week 1: Oct 12 – Oct 18 (35 hours)
| Hours | Work |
|---|---|
| 18 | Exam study: Domain 1 (ingestion and transformation) service-selection breadth, then Domain 2 (data store management). First full mock exam by Saturday to find weak areas |
| 2 | Review and finalize `01-business-problem.md` |
| 10 | Write `02-architecture.md` v1: context diagram, account topology, data zones (quarantine, raw, curated, serving), data flows for every feed, security boundaries, scale and cost model |
| 5 | Write ADRs 001–005 (list in section 5) |

### Week 2: Oct 19 – Oct 25 (35 hours)
| Hours | Work |
|---|---|
| 20 | Exam study: mocks 2–4 with weak-area review; Domains 3 (operations) and 4 (security and governance) |
| 4 | **Spike 1, accounts.** Create the new management account (you sign up for it yourself), invite the existing Offers Platform account, create the ABC Bank account, enable Identity Center and a basic tagging policy |
| 6 | **Spike 2, CDC.** Small RDS Postgres in the ABC Bank account → DMS → S3 in the Offers Platform account (cross-account bucket policy and KMS key policy). Insert, update, and delete rows and watch the change records land |
| 5 | **Spike 3, lake and governance.** Glue Data Catalog + Athena over an Iceberg table, then a cross-account Lake Formation grant. Measure actual bytes per row from the v2 Parquet data and replace the ~60-byte assumption in the Business Problem doc. Write the remaining ADRs 006–013 |

Every spike is built with Terraform or the console and **torn down the same day**. Each spike ends with a short write-up in `docs/spikes/` covering what you built, what broke, what it cost, and which exam topics it covered.

### Final days: Oct 26 – Oct 28 (~15 hours)
Exam only: a final mock, a review of flagged questions, and the exam on **Oct 28**.

### Phase 0 exit criteria
- [ ] `01-business-problem.md` final
- [ ] `02-architecture.md` v1 complete, with diagrams
- [ ] ADRs 001–013 written
- [ ] Bytes-per-row measured and the storage estimate updated
- [ ] Three spike write-ups in `docs/spikes/`
- [ ] All spike resources torn down; spend under $25
- [ ] DEA-C01 taken

---

## 4. Phases 1–7: outcomes and exit criteria

### Phase 1: Foundations
- Management + Shared Services account: organization structure, Identity Center, consolidated billing, CloudTrail organization trail, AWS Budgets and Cost Anomaly Detection
- Terraform remote state in each account; GitHub Actions OIDC roles
- Networking for the ABC Bank account (RDS and DMS) using S3 gateway endpoints instead of a NAT gateway
- KMS keys; lake buckets for quarantine, raw, curated, and outbound, with lifecycle rules: 4 weeks then cold storage; curated history to Glacier Instant Retrieval; no archive rule on quarantine (deleted by the pipeline)
- **Exit:** `terraform apply` builds everything and `terraform destroy` removes it cleanly; a test budget alert fires

### Phase 2: ABC Bank source (`abc-bank` repo)
- Core-banking schema on RDS Postgres: customers, accounts, cards, merchants, transactions
- Synthetic data generator driven by a **scale factor**, reusing the 20 personas
- DMS full load plus ongoing CDC to the platform's intake bucket, including updates and deletes
- **Exit:** SF10 data loaded, and customer updates appear as change records in the Offers Platform account

### Phase 3: Intake and lakehouse
- Two intake modes; quarantine zone with its own key and access lockdown
- Tokenization on EMR Serverless; checks that fail the pipeline if personal data is detected; automatic deletion of raw files
- Iceberg tables: transactions (partitioned by day), customers as **Type 2 history** built from CDC
- Glue Data Quality rules; Macie scans of curated zones
- Step Functions per-batch workflow: validate → tokenize → merge into Iceberg → quality checks → register
- **Exit:** a day's CDC batch flows from intake to curated Iceberg tables with no personal data downstream

### Phase 4: Transform, offers, orchestration
- dbt on Redshift Serverless (marts) and Athena (lake-side models); port the existing customer 360 and affinity models
- Offer ranking ported from v2, plus a merchant/campaign catalog and the **holdout flag**
- Nightly offer file to the ABC Bank outbound bucket; simulated activation events back from both mobile app and web banking, tagged by channel and de-duplicated so each offer activates once
- MWAA nightly DAG: CDC merge → dbt → ranking → offer file; triggers the Step Functions workflows
- **Exit:** one full nightly cycle runs unattended and delivers the offer file by the target time

### Phase 5: Attribution and reporting
- Redemption matching: activated offer + qualifying spend inside the offer window
- Late-arriving transaction handling with a 7-day restatement window
- Settlement calculated per redemption, then rolled up to invoice lines
- Monthly merchant campaign reports and bank settlement files to S3
- **Exit:** merchant fees, bank share, and cash back reconcile to the cent

### Phase 6: Scale test and FinOps report
- Run at SF100, fix issues, then run at **SF5000** in a planned burst (Working posture)
- Tune partitioning, file compaction, and Redshift and Athena usage
- Publish `docs/finops-report.md`: cost per million transactions and cost per offer, by service and by scale factor
- **Exit:** regional-scale nightly cycle meets its service levels; cost report published

### Phase 7: Showcase (later releases)
- QuickSight merchant dashboard
- Incremental lift using the holdout group
- Snowflake (legacy) reading the same Iceberg tables
- Interview materials: architecture walkthrough, war stories, decision records

---

## 5. Architecture decision records (ADRs)

| # | Decision | Written in |
|---|---|---|
| 001 | Three-account topology (small-organization compromise) and when to split out Shared Services | Week 1 |
| 002 | AWS-native lakehouse on Iceberg; Snowflake as legacy | Week 1 |
| 003 | Platform-side tokenization with two intake modes | Week 1 |
| 004 | Orchestration split: MWAA vs. Step Functions | Week 1 |
| 005 | Query engine roles: Athena vs. Redshift Serverless | Week 1 |
| 006 | CDC with DMS; Type 2 history in Iceberg | Week 2 |
| 007 | Batch S3 file exchange for offers, activations, reports, settlement | Week 2 |
| 008 | Scale-factor synthetic data generation | Week 2 |
| 009 | FinOps posture, tagging, and guardrails | Week 2 |
| 010 | Simple attribution with a day-one holdout flag | Week 2 |
| 011 | Data retention and S3 lifecycle, with the quarantine and curated-history exceptions | Week 2 |
| 012 | 7-day restatement window for late-arriving transactions | Week 2 |
| 013 | Per-redemption settlement calculation | Week 2 |

Each ADR follows the same short format: context, options considered, decision, consequences, and the exam domain it relates to.

---

## 6. FinOps guardrails (active from Phase 0)

- **Teardown by default.** Every session ends with `terraform destroy` for anything that bills by the hour (RDS, DMS, MWAA, EMR applications).
- **MWAA** is created only for integration and demo sessions; day-to-day DAG development uses the existing local Airflow.
- **No NAT gateway;** S3 and DynamoDB gateway endpoints instead.
- **Redshift Serverless** at 4 RPU base capacity, with a daily RPU-hours usage limit.
- **Athena workgroups** with a per-query data-scanned limit.
- **AWS Budgets** alerts at 50%, 80%, and 100% of the monthly posture limit, plus Cost Anomaly Detection.
- **Snowflake** resource monitor stays in place on the legacy account.
- **Scale tests** (SF5000) are scheduled bursts with an estimate written down beforehand and the actual cost recorded after.

---

## 7. Repositories and layout

**`customer-spend-analytics`** (evolves to v3, the Offers Platform). The existing v1/v2 code stays in place until it is replaced.
```
docs/
  v3/00-roadmap.md
  v3/01-business-problem.md
  v3/02-architecture.md
  adr/
  spikes/
infra/
  platform/                 # Terraform for the Offers Platform account
  management/               # Terraform for the management + shared services account
platform/
  intake/                   # intake modes, quarantine, tokenization
  lakehouse/                # Iceberg table definitions and merges
  transform/                # dbt project (Redshift + Athena)
  offers/                   # ranking, holdout assignment, offer file
  attribution/              # redemption matching, reports, settlement
  orchestration/            # MWAA DAGs, Step Functions definitions
```

**`abc-bank`** (new): the bank's systems and future bank-internal projects.
```
docs/
infra/                      # Terraform for the ABC Bank account
core-banking/               # Postgres schema, migrations
data-generator/             # scale-factor synthetic data
cdc/                        # DMS tasks and endpoints
exchange/                   # outbound feeds, inbound offer and settlement drop
```

---

## 8. How work is tracked

- **GitHub Issues** in both repos.
- **One Milestone per phase** (Phase 0 – Phase 7).
- **Labels:**
  - Exam domains: `dea-domain-1` to `dea-domain-4`
  - Work types: `design`, `spike`, `infra`, `pipeline`, `finops`, `docs`
  - Repo-specific: `abc-bank` and `platform`
- Every issue lists its acceptance criteria, and any issue that creates hourly-billed resources includes a teardown check.
