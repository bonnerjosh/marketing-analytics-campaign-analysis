# Experiment design

## Assignment and estimand

Use the frozen eligible customer list at 2027-01-01 00:00 UTC. Assign each customer once with an independently seeded Bernoulli(0.5) draw in stable customer ID order. The realized count may vary around 50/50. Control receives a standard savings email and treatment receives a goal-oriented email with actionable guidance. Keep send timing, channel, reminder and eligibility rules identical. Schedule the index email at assignment and the common reminder three days later. No additional campaign arms, delivery gating or adjustments after observing results.

The primary estimand is the treatment-minus-control risk difference in 14-day first-deposit activation for the randomized eligible population under this protocol. H₀ is equality of arm probabilities; H₁ is a difference. Use a two-sided 0.05 threshold. This estimates personalization versus standard messaging. A no-contact holdout would be needed to estimate the value of sending either campaign.

## Planning inputs and power

Freeze an 8% pooled control assumption and a +2 percentage-point planning target before outcomes. Treat both as illustrative assumptions. Profile-specific control probabilities are 12% (A), 8% (B), 4% (C). The power calculation uses the frozen profile counts to estimate the overall control rate and tests sensitivity at 4%, 8% and 12%, before outcomes are simulated.

Use the normal two-proportion power calculation with pooled variance under H₀, arm-specific variance under H₁, two-sided alpha 0.05 and 80% target power. Solve for required customers per arm, rounding up. With floor(actual eligible N / 2) as planned size per arm, solve for the smallest positive absolute effect at 80% power and report achieved power for +2 pp. At 8% versus 10% this is about 3,213 customers per arm. Recalculate with realized group sizes if materially imbalanced, using prespecified baseline assumptions. No observed-effect post-hoc power or sample-size changes. Report any shortfall and its implications for precision.

## Simulation protocol

- Freeze profile rules and analysis before assignment and generate identical history for both scenarios. Use a shared uniform draw per customer for potential day-14 activation under each arm, independent of the assignment draw. The null scenario adds zero and the nonzero scenario adds 2 pp in treatment for every profile, so subgroup estimates differ through noise despite a common true absolute lift. Use the nonzero scenario for the portfolio and validate the null without requiring a particular p-value.
- Simulate activation timing, later first deposits, repeat deposits and amounts with documented profile-dependent rules and seeded draws. For timely activators, apply the same repeat process in both arms, allowing the joint sustained endpoint to change through activation. For nonactivators at day 14, generate some later first deposits using a common continuation rule. Apply no direct treatment rule to app engagement or delivery. Associated changes through generated journeys are possible. Keep delivery and clicks separate from the activation mechanism; this is an illustrative assignment-level effect, not a simulation of delivery-mediated causation.
- Use profile and pretreatment engagement to generate app use and clicks. Write account- and event-level facts with plausible ordering rather than passing synthetic labels to the analysis. SQL reconstructs outcomes from facts. Validate historical fingerprints, unchanged assignment under scenario switch, and identical potential day-14 outcomes across arms under the null per customer. Outcomes never feed into assignment.

## Inference and interpretation

1. Verify assignment IDs and count against the frozen population, dates, coverage, and mutually exclusive arm flags. Run a two-sided exact binomial sample ratio mismatch check (p₀ = 0.5, flag p < 0.01). Investigate any flag and halt reporting if a data or assignment issue is unresolved. Log pre-assignment summaries by arm as diagnostics.
2. From the mart report events, n, arm rates, absolute lift (percentage points), relative lift (difference/control rate, undefined at zero), and an estimated incremental count for the number actually assigned to treatment (risk difference × treatment n). Scale the risk-difference interval for the incremental-count interval. Apply a two-sided pooled proportions z-test and a 95% Newcombe interval for the risk difference. If any expected cell in the arm-by-outcome table is below five, use two-sided Fisher exact and flag the changed test. Explain that independently constructed tests and intervals can differ near the cutoff. [statsmodels Newcombe interval](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.confint_proportions_2indep.html)
3. Report secondary binary outcomes with arm rates and 95% risk-difference intervals, and the amount outcome with mean difference and a seeded 5,000-resample within-arm customer bootstrap percentile interval. Keep the primary test as the sole confirmatory decision. Treat secondary intervals and profile intervals as nominal and exploratory.
4. For predefined profiles, show arm denominators, arm rates, absolute lift and 95% Newcombe intervals. Test the two assignment-by-profile interaction terms jointly with a two-degree-of-freedom Wald test in a linear probability model with HC3 robust covariance, matching the absolute-lift scale. If sparse or degenerate strata prevent reliable estimation, report that limitation and show descriptive estimates where defined. Require the joint result before suggesting heterogeneity, and label any signal exploratory. No geographic or demographic hypothesis tests in the MVP.
5. Write recommendations after analysis. An imprecise interval can support a better-powered follow-up. A favorable synthetic result demonstrates a decision workflow, while real rollout would require a real randomized validation and campaign cost/benefit inputs.

The implemented simulator uses profile A/B/C continuation probabilities of
4.8%/3.5%/2.2% among customers who have yet to fund by day 14 and conditional
repeat probabilities of 40%/32%/22%. Repeat deposits occur after 2–29 days plus
0–120 minutes. First and repeat amounts are drawn uniformly on $5–$300 and
$5–$250 ranges and scaled by 1.30/1.15/1.00 by profile. Both arms have a 96.5%
delivery probability per message; conditional index click probabilities are
19%/11%/6.5% by profile. The reminder uses 80% of those click probabilities.
These parameters are scenario inputs and do not describe real customers.

See [validated findings](EXPERIMENT_FINDINGS.md) for the realized estimates.
