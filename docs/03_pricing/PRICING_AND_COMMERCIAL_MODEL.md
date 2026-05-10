# Verixa — Pricing & Commercial Model

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Initial commercial framework · Audience: CFO, procurement officer, sales lead, board

---

## 1. Pricing philosophy

Verixa is priced as **strategic infrastructure**, not as a per-seat SaaS tool. Three principles anchor every pricing decision:

**1. Land with a fixed-fee outcome, expand on usage.** The first commercial relationship with a regulated enterprise customer is a fixed-fee pilot scoped to one high-value workflow with defined success criteria. Once the substrate is in place, expansion is metered on operational usage of the platform.

**2. Meter on governance value, not on tokens.** Token-based pricing signals raw LLM infrastructure economics; Verixa's value is governance. Verixa meters on **governed actions** (every action the Runtime Gateway processes), **replay runs** (Replay Vault reconstructions on demand), and **triad volume** (Triad Review invocations on high-risk decisions). These metrics scale with the customer's actual governance consumption rather than with raw LLM spend.

**3. Sovereign deployment is a first-class commercial option, not a premium add-on.** The customer's deployment topology choice — on-premises, private cloud, sovereign managed, or Verixa-hosted SaaS — is reflected in pricing structure but does not multiply the licence fee in punitive ways. Sovereign customers are Verixa's strategic core; they cannot be punished for sovereignty.

---

## 2. Tier structure

Verixa offers four commercial tiers reflecting the deployment topologies plus a research/educational tier.

### Tier 1: Pilot (entry tier)

- **Shape:** Fixed-fee 8–12 week enterprise pilot
- **Fee:** £150,000 GBP (or local-currency equivalent)
- **Scope:** One high-value regulated workflow, single-environment deployment, Verixa Phase 1 capabilities (Runtime Gateway + Policy + Risk + Triad + Audit Ledger + Replay Vault + basic Compliance Dossier)
- **Compute:** Customer-provided MI300X access via AMD Developer Cloud sovereign tenancy or customer-deployed
- **Outcomes:** Regulator-acceptable Compliance Dossier on the pilot workflow, replay demonstration on a real production decision, joint test plan completion
- **What this is:** Procurement-friendly, finance-friendly, low-risk path for a regulated enterprise to evaluate Verixa against a real workflow. Not a sales gimmick — the pilot is the first commercial relationship and is structured to convert into Tier 2 or Tier 3 procurement.

### Tier 2: Enterprise (post-pilot full deployment)

- **Shape:** Annual licence + usage metering + add-ons
- **Annual licence:** £500,000 GBP minimum, scaling with deployment size
- **Usage metering:**
  - Governed actions — first 5 million per month included; £0.001 per action above
  - Replay runs — first 1,000 per month included; £25 per replay above
  - Triad Review volume — first 50,000 per month included; £0.10 per invocation above
- **Add-ons (priced separately):**
  - Compliance packs (sector-specific Rego policy libraries — financial services, healthcare, public sector, defence, energy)
  - Premium triad (additional reviewer model families beyond the standard three)
  - Managed review (WET Ops human reviewer pool)
  - Extended retention (cold immutable evidence vault beyond standard tier)
  - Custom integrations (sidecar mesh, ServiceNow, Salesforce, ITSM)
- **Compute:** Customer-deployed MI300X, customer's existing private cloud, or Verixa Sovereign Managed tenancy
- **Typical first-year contract value:** £500,000–£2,000,000 GBP depending on workflow count, usage commitment, and add-ons
- **Net Revenue Retention target:** 130%+ (workflow expansion, add-on attach, usage growth)

### Tier 3: Sovereign Managed (Verixa-operated dedicated tenancy on AMD Developer Cloud)

- **Shape:** Annual licence + managed compute + usage metering
- **Annual licence:** £750,000 GBP minimum (Tier 2 plus managed-service premium)
- **Compute:** Verixa-operated dedicated MI300X tenancy on AMD Developer Cloud, billed at cost-plus
- **Usage metering:** Same as Tier 2
- **Operational SLA:** 99.5% availability, 24/7 support, regulated-sector incident response
- **Use case:** Regulated mid-market enterprise that wants sovereign deployment without buying their own MI300X clusters
- **Typical first-year contract value:** £1,000,000–£3,000,000 GBP

### Tier 4: Hosted SaaS (lower-risk customers)

- **Shape:** Annual subscription + usage metering
- **Annual subscription:** £100,000 GBP minimum
- **Compute:** Verixa-hosted multi-tenant on AMD Developer Cloud
- **Usage metering:** Same metric structure as Tier 2 with adjusted included quotas
- **Use case:** Mid-market customers, internal AI workflows that do not require sovereign deployment, departmental deployments below the regulated-data threshold
- **Typical first-year contract value:** £100,000–£500,000 GBP

### Tier 0: Research / Educational

- **Shape:** Free for non-commercial research, accredited universities, accredited public-interest research bodies, regulatory authorities and supervisory bodies
- **Compute:** Limited to community quotas on Hugging Face Spaces and Verixa-hosted reference deployment
- **Use case:** Academic researchers, regulators, NGOs evaluating AI governance frameworks
- **Strategic purpose:** Standards-body and academic legitimacy, AAGATE-aligned reference deployment availability, pipeline-building for regulator relationships

---

## 3. Pricing rationale

The pricing structure above is calibrated against three reference points.

**Reference 1: AI-GRC SaaS vendors.** Credo AI, Holistic AI, and Trustible deals in regulated UK/EU enterprise typically range from £100,000 to £400,000 first-year ACV (annual contract value). Verixa's Tier 2 entry of £500,000 reflects the additional capability surface (runtime governance, sovereign deployment, multi-model triad, replay, Annex IV-aligned dossier) and the structural moat the buyer is contracting for, not just feature parity.

**Reference 2: Enterprise GRC platforms with AI modules.** OneTrust and ServiceNow GRC enterprise deals range from £500,000 to £3,000,000+ depending on scope. Verixa's Tier 2 and Tier 3 sit comfortably within this band while delivering AI-specific capabilities the GRC platforms cannot.

**Reference 3: Cloud AI governance suites.** Microsoft Purview AI features and Vertex AI governance are bundled into broader cloud commitments at unclear AI-specific pricing. The substantive comparison is "Verixa standalone vs the AI governance value the customer extracts from their existing cloud commitment." Verixa wins on cross-cloud, cross-model, and sovereign — for which the customer is willing to pay a dedicated line item.

**Pilot fee rationale.** £150,000 for an 8–12 week pilot with a regulated UK/EU enterprise sits at the low end of "named-vendor consulting engagement" pricing in this sector. It is procurement-friendly: most enterprise procurement teams can approve £150,000 against a project budget without going to a full vendor onboarding cycle. It is also a credible commitment from Verixa: the pilot is delivered, with success criteria met, by a senior team, against a real workflow.

---

## 4. Land-and-expand sequence

The strategic sequence is designed for customer Net Revenue Retention growth from Year 1 (pilot) through Year 5+ (platform).

**Year 1 — Land via Pilot.** £150,000 fixed-fee Tier 1 pilot. Single workflow. Phase 1 capabilities. Conversion target: 60%+ of pilots convert to Tier 2 by month 12.

**Year 1 (post-pilot) — First Tier 2 deployment.** Customer commits to enterprise licence for 1–3 governed workflows. £500,000–£900,000 first-year ACV. Includes Phase 1 + Phase 2 capability rollout.

**Year 2 — Expand workflows.** Customer adds 3–10 workflows. £900,000–£1,500,000 ACV with usage growth. Phase 3 capabilities (Sovereign Runtime, Drift Monitor) deploy.

**Year 3 — Trust Graph + WET Ops.** Customer enables Phase 4 capabilities. Trust Graph and WET Ops are usage-driven add-ons. ACV expansion to £1,500,000–£3,000,000.

**Year 4 — Third-party AI governance.** Customer extends Verixa to govern Copilot, Salesforce, ServiceNow, and other third-party AI products. Phase 5 wrappers + connectors. ACV expansion to £2,500,000–£5,000,000.

**Year 5+ — Federated Trust Mesh.** Customer joins the Verixa cross-company attestation mesh. Trust posture becomes a competitive advantage for the customer's own market. ACV expansion to £3,000,000–£7,000,000+.

**Net Revenue Retention compound:** A typical Tier 2 customer growing through Phases 2–6 reaches 5–8x first-year ACV by Year 5. The compound is driven by workflow expansion, add-on attach, and usage growth — each phase of the platform unlocks new revenue surface.

---

## 5. Procurement-friendly artefacts

Verixa's pricing structure is designed to align with how regulated enterprise procurement actually works.

**Pre-pilot artefacts:**
- Executive Brief and Product Vision (this documentation pack)
- Competitive Landscape with feature matrix
- Regulatory Mapping Matrix (extends AAGATE/CSA crosswalk)
- Pilot Statement of Work (template, customised per pilot)
- Reference architecture deck

**Pilot-conversion artefacts:**
- Pilot success criteria document with joint sign-off
- Compliance Dossier output samples from pilot workflow
- Replay demonstration recording
- Big 4 advisor review letter (where customer requires)

**Tier 2 procurement artefacts:**
- Master Services Agreement (MSA) template
- Data Processing Agreement (DPA) — UK GDPR + EU GDPR + sector-specific
- Sovereign deployment topology agreement
- Three-year roadmap commitment
- SLA schedule
- Information Security questionnaire response template (typically 200–400 questions in regulated sector RFPs)

**Annual renewal artefacts:**
- Operational metrics summary (governed actions, replay runs, triad volume, incidents)
- Phase capability rollout report
- Trust Graph utilisation summary
- Roadmap commitment for renewal year

---

## 6. Discount policy

Verixa's discount policy is conservative and defensible. Three categories of discount are pre-approved:

**Multi-year commitment discount.** Up to 15% off annual licence for 3-year commitment, up to 25% off for 5-year commitment. Usage metering rates do not discount.

**Sector reference discount.** Up to 20% off Tier 2 annual licence for first-three customers in a named regulated sector (financial services, healthcare, public sector, defence, energy) in exchange for full reference rights and case study participation. Strategic — used to seed the reference pool.

**Standards-body / regulator engagement discount.** Up to 50% off Tier 2 annual licence for accredited standards bodies, regulatory supervisory authorities, and NGOs evaluating AI governance frameworks. Strategic — used to build standards-body legitimacy and regulator-side familiarity with the platform.

**No volume discount on usage metering** at any tier. Usage metering rates are fixed; included quotas scale with annual licence size. This protects the unit economics of the metered services.

**No "free pilot" discounting.** The £150,000 pilot fee is the floor. Discounting to zero erodes the procurement signalling that says "this is a serious commercial relationship from day 1." If a strategic customer requires a zero-fee evaluation, it is structured as a Tier 0 reference deployment with explicit conversion criteria, not as a discounted pilot.

---

## 7. Pricing risks and mitigations

**Risk: Hyperscaler bundling.** Microsoft, Google, AWS will increasingly bundle AI governance features into existing cloud commitments at near-zero marginal cost. Mitigation: Verixa's cross-cloud, cross-model, sovereign positioning is structurally outside the hyperscaler bundle. Customers buying Verixa are explicitly choosing not to lock to one cloud provider's governance; the bundle is not a substitute. Pricing is calibrated to win on category-of-one, not on being cheaper than a free bundle.

**Risk: AI-GRC commoditisation.** Credo AI, Holistic AI, Trustible may converge on lower price points as the market matures. Mitigation: Verixa's pricing is anchored on the runtime + replay + multi-model + sovereign capability surface, not on the governance program management feature surface. Even if AI-GRC dashboards commoditise, Verixa's runtime control plane sits above that layer and is priced accordingly.

**Risk: Open-source pressure.** AAGATE's MVP is open-source; future open-source projects may emerge that implement runtime governance primitives. Mitigation: Verixa's open-source contribution strategy (open Rego policy templates, open audit ledger format, open AAGATE compatibility layer) wins community legitimacy without commoditising the commercial platform. Enterprise customers buy the SLA, the Trust Graph, the Sovereign Runtime, the WET Ops, and the platform integrations — not the runtime primitives that any open-source project can replicate.

**Risk: Regulator-mandated pricing transparency.** The EU AI Act may evolve toward requiring AI governance vendors to publish pricing for fairness reasons. Mitigation: Verixa's pricing structure as defined here is publishable. Standard tiers, standard usage rates, standard discount policy. No covert side-deals that would be problematic if disclosed.

---

## 8. Internal pricing-decision authority

For commercial discipline, Verixa pricing decisions are tiered:

- **Account Executive level:** Tier 1 pilot fee, no discount. Tier 2 annual licence at list price.
- **Sales Director level:** Multi-year commitment discount up to standard policy. Sector reference discount up to 20%.
- **Chief Revenue Officer level:** Discount above standard policy. Strategic deals over £3,000,000 ACV.
- **CEO + Board level:** Standards-body discount above 50%. Pricing structure changes. New tier introduction.

This authority structure is published internally; commercial teams know what they can sign without escalation.

---

## 9. Pricing review cadence

Pricing structure reviewed quarterly. Annual major review with board approval. Triggers for off-cycle review:

- Significant regulatory change (e.g. EU AI Act enforcement specifics)
- Hyperscaler bundling or pricing shift
- Loss of three or more deals on price
- Win of a strategic customer at materially different pricing
- New tier introduction (e.g. when third-party AI governance Phase 5 launches as a distinct commercial tier)

Pricing-change communication to existing customers: 90 days advance notice for any usage metering rate change; existing annual licences are honoured at the contracted rate through their renewal date.

---

*This Pricing & Commercial Model document is the canonical commercial framework for Verixa. The Build Plan and Product Vision reference the phasing assumptions. The Master Services Agreement and Data Processing Agreement templates operationalise the contractual mechanics. Pricing is reviewed quarterly; structural changes require board approval.*
