# Synthetic experiment findings

A fictional fintech tested a goal-oriented New Year savings email against its standard savings email. Both groups received the same reminder. The test randomized 10,701 customers with an open, never-funded savings account on January 1, 2027 UTC. Results describe simulated outcomes.

## First deposits

| Scenario | Control | Personalized | Difference (95% CI) | Two-sided p |
|---|---:|---:|---:|---:|
| Nonzero simulation | 377 / 5,310 (7.10%) | 543 / 5,391 (10.07%) | +2.97 pp (+1.91 to +4.03) | 4.15 × 10⁻⁸ |
| Null simulation | 377 / 5,310 (7.10%) | 433 / 5,391 (8.03%) | +0.93 pp (−0.07 to +1.94) | 0.068 |

The primary comparison counts all randomized customers, including those who never received or clicked an email. In the nonzero scenario the estimated relative lift was 41.9%, equivalent to about **160 incremental first deposits** among the 5,391 customers assigned to personalization (95% CI 103 to 218). The generator injected a +2-point effect for every profile in this scenario. Finite-sample variation explains why the observed lift differs from that input. Assignment was identical across scenarios. The exact sample ratio check gave p = 0.439.

Before simulation, the 7.25% weighted baseline and 2-point design alternative implied 2,970 required customers per arm, 96.4% power at the frozen eligible count, and a 1.47-point minimum detectable effect at 80% power. The 4%, 8% and 12% baseline sensitivities gave 99.7%, 95.1% and 86.8% power at the same design alternative. These calculations address the overall primary outcome.

## Secondary outcomes

| Nonzero scenario | Control | Personalized | Difference (nominal 95% CI) |
|---|---:|---:|---:|
| 30-day activation | 10.09% | 13.26% | +3.17 pp (+1.95 to +4.38) |
| First deposit by day 14 and a second within 30 days of it | 2.56% | 3.34% | +0.78 pp (+0.14 to +1.42) |
| 30-day qualifying amount per assigned customer | $23.75 | $27.63 | +$3.87 (+$0.64 to +$7.08) |
| 30-day savings app engagement | 44.09% | 43.81% | −0.27 pp (−2.15 to +1.61) |

All rates and amounts use the full assigned arm. The repeat outcome counts people who started and returned. The simulation used the same conditional repeat process in both arms, so the result does not isolate a change in post-activation behavior. Secondary intervals are exploratory. In the null simulation, the nominal 30-day activation interval excluded zero despite no programmed treatment effect, illustrating why the primary decision was fixed in advance.

## Behavioral profiles and campaign credit

| Profile | Control n / rate | Personalized n / rate | Lift (nominal 95% CI) |
|---|---:|---:|---:|
| A · Engaged but unfunded | 1,770 / 11.58% | 1,739 / 15.01% | +3.43 pp (+1.18 to +5.68) |
| B · Financially active, low savings engagement | 787 / 8.51% | 889 / 10.80% | +2.29 pp (−0.57 to +5.11) |
| C · Dormant or low engagement | 2,753 / 3.81% | 2,763 / 6.73% | +2.92 pp (+1.74 to +4.11) |

The joint interaction test yielded p = 0.824. These results provide no evidence for changing campaign investment by profile. Profile differences in baseline activation remain useful for describing the audience.

The index and reminder delivered at 96.52% and 96.71%. Recipient click-through was 11.69% and 9.05%. First-touch rules credited 442 activations to the index and 191 to the reminder. Last-touch rules credited 209 and 424, respectively. Both rules left 287 of the 920 first deposits unattributed. This shift shows how delivery order and credit rules can change campaign reporting without changing the randomized comparison.

See the [case study summary](../README.md#key-findings) for the decision and suggested follow-up.

## Reconciliation

Both scenarios were built in BigQuery and analyzed from the experiment customer mart. Python matched every mart customer's assignment, selected account, frozen profile, deposit times, outcome flags and deposit total to the local facts. Independent SQL arm summaries and attribution counts reconciled. The dashboard uses aggregate results from the verified nonzero scenario.
