# Metric contract

All intervals use UTC, with inclusive starts and exclusive ends unless specified. History is [2026-01-01, 2027-01-01). Assignment is 2027-01-01 00:00. Follow-up coverage ends 2027-03-01 00:00. A zero represents observed absence of a qualifying event within a complete window. An undefined rate with a zero denominator is null.

A qualifying deposit is a positive, completed deposit into a savings account. Pending, failed and reversed rows, withdrawals and checking activity do not qualify. Count each unique transaction once and order deposits across all of a customer's savings accounts. A deposit initiation or confirmation screen is an app interaction. Use posted transactions for financial outcomes.

## Historical lifecycle and market analysis

- **Signup funnel.** Use one common base of signups with 90 days of historical coverage. Count first savings opening within 30 days of signup, first qualifying deposit within 30 days of that opening, then a second qualifying deposit within 30 days of the first. Each stage requires all previous stages. Divide by the previous stage for step conversion and subtract from one for drop-off. Also show counts and share of signups. Compare elapsed time to opening or activation using medians among those who reached the milestone in time.
- **Opening cohorts.** Use first-time savings openers with 60 days of historical coverage from first open. Activation is first deposit within 30 days after first opening, divided by mature openers. Repeat is a second deposit within 30 days after first deposit among timely activators. A later deposit on a different account qualifies. Tied posting timestamps are ordered by unique transaction ID. In the monthly series, omit any month where the full calendar cohort cannot mature. Use the same maturity rules for channel, signup segment, region, market type and exploratory age-band comparisons. Show counts alongside rates and use signup cohorts for adoption. Historical profile cuts apply only to activity summaries of the frozen eligible population, since by definition that group has zero prior activations.
- **Eligibility by region.** Divide eligible customers by all customers signed up strictly before assignment in each region. Show regional counts, profile mix among eligible customers and comparable 30-day session and checking activity summaries. Region and age cuts are descriptive and conditional on the synthetic generator.
- **GA4-style engagement.** Count sessions, active customers and savings interactions from distinct events. Sequence start → savings view → deposit initiation → confirmation within a session for ordered app steps. Report customer-level reach for each ordered step, counting each customer once across sessions; use earlier-step reach for step conversion. Show distinct customers with an initiation and distinct customers with a qualifying deposit in the same stated window and population, plus overlap. Separate goal starts/completions can be described as engagement. App and financial events can diverge.

## Frozen eligibility and profiles

Start with customers signed up before assignment. Require at least one savings account opened strictly before the cutoff and still open immediately before it. Use the historical snapshot, so a later closure does not alter eligibility. Exclude anyone with any qualifying deposit before the cutoff across all savings accounts, including closed accounts. Synthetic lifetime history starts at signup. Require no demographic or engagement threshold for eligibility.

Compute integer counts in [2026-12-02 00:00, 2027-01-01 00:00). Count distinct app sessions S, distinct sessions with a savings view, goal start/completion or deposit attempt G, and completed checking debits or credits C across checking accounts. Left-join and fill absent counts with zero. New signups have less exposure, so show tenure and interpret their low counts accordingly.

| Precedence | Rule | Label |
|---|---|---|
| 1 | S ≥ 6 AND G ≥ 2 AND C ≥ 4 | A · Engaged but unfunded |
| 2 | C ≥ 6 AND S ≥ 2 AND G ≤ 1, after rule 1 | B · Financially active, low savings engagement |
| 3 | All other eligible customers | C · Dormant or low engagement |

Profile C includes everyone who meets neither of the first two rules, so it can contain a mix of activity patterns. The rules were fixed before assignment and outcome generation.

## Campaign and attribution

- **Delivery.** Distinct sent messages and distinct delivered messages among sends. Delivery rate is delivered / sent. Count unique clicking recipients by campaign or breakdown. Recipient CTR is delivered recipients with a valid click within seven days of delivery / distinct delivered recipients, using mature deliveries.
- **Following engagement.** For the 14-day experiment activation set, match valid campaign clicks at or after assignment, strictly before the first deposit and with deposit fewer than seven days after click. Report the count and descriptive conversion rate among unique clickers within the 14-day window, with the full window stated. Clicks must match deliveries and fall within seven days of delivery.
- **Touch credit.** Use eligible delivered messages strictly before the customer's first deposit, with deposit fewer than seven days after delivery. Rank touches by timestamp, then message ID, and credit one campaign each under first-touch and last-touch rules. Report unattributed activations and reconcile both methods to the same 14-day conversion set. One standard/personalized index email plus one identical scheduled reminder in both arms gives distinct touch campaigns with possible overlap. Delivery credit is descriptive, and either rule may yield similar totals.
- Group campaign metrics by campaign with one breakdown at a time (acquisition channel, profile, region or assignment). Report message and recipient denominators explicitly. Never sum unique customers across breakdowns or campaigns with overlapping reach.

## Experiment outcomes

All causal outcomes use every assigned eligible customer, regardless of sending, delivery, app use or activation. Day 14 ends Jan 15 00:00; day 30 ends Jan 31 00:00.

| Outcome | Definition |
|---|---|
| Primary 14-day activation | At least one qualifying deposit within day 14. With frozen eligibility, this is the customer's first. |
| 30-day activation | At least one qualifying deposit within day 30. |
| 30-day amount per assigned customer | Sum of qualifying deposit amounts within day 30, with zero for customers who make none. |
| Sustained saving | Activated within day 14 and made a second qualifying deposit within 30 days of that first deposit. Divide by all assigned customers. Latest required follow-up ends before Feb 14 00:00. |
| App engagement | At least one savings-related app session within day 30, divided by all assigned customers. |
| Delivery and clicks | Operational campaign diagnostics with their message/recipient denominators. They do not determine inclusion in outcome analysis. |

An optional conditional repeat share among timely activators explains customer behavior. It is descriptive because the campaign can change who activates. The sustained outcome measures the joint effect on activating and returning, and cannot isolate habit formation after activation.
