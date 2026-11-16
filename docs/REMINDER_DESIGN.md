# In-app reminder experiment

The fictional lifecycle team must decide whether to test an in-app reminder on top of its standard savings email. This standalone synthetic scenario uses the previously frozen population of customers with an open, never-funded savings account. It preserves the original email-personalization analysis.

## Rules fixed before simulation

- Randomize customers 1:1 on January 1, 2027 UTC, using a seeded shuffle of the sorted frozen population. The control receives the standard email and the treatment receives the same email plus eligibility for an in-app reminder. The primary outcome is a positive, completed deposit into the frozen eligible savings account in the half-open 14-day window after assignment. The simulator only creates follow-up deposits on this account. Keep all assignments, including customers never exposed.
- Use seed 20270102 and the existing profile baselines (12%, 8%, 4%) for background funding. Independently simulate email delivery (97%), an app visit (55%), and an earlier day-2 funding event (25% of baseline funders). A treatment customer visiting on day 4 sees an impression if they have yet to fund. Email delivery occurs on day 1 at 01:00 UTC. The reminder can produce a day-7 deposit for 4% of shown customers who would otherwise not fund. Remaining baseline deposits occur on day 8. This programmed mechanism is illustrative. The same email and background processes apply to both arms.
- Measure absolute risk difference with a Newcombe 95% interval. Estimate 80% power at two-sided alpha 5% using the existing planning method, the weighted profile baseline, and half the frozen population per arm rounded down.
- For descriptive attribution, count only delivered emails and recorded impressions at or after assignment, strictly before the first deposit and less than seven days before it. Deduplicate exact repeated event records by event ID. Rank eligible touches by timestamp then event ID, with both sort keys reversed for last touch. Keep unattributed activations. Campaign credit has no role in the randomized estimate.
- A real test would keep email policy fixed and record event ID, campaign ID, customer ID, assignment ID and timestamp, channel, placement, and actual impression timestamp. Use the assignment log for the denominator. Use an agreed value per additional funded customer to set the cost ceiling before the test.

The first simulated output is retained. This study evaluates a measurement workflow on generated facts.
