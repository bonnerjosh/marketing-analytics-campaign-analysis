# AI-assisted attribution reconciliation

The original email dashboard gives the initial email different funding credit under first- and last-touch rules. I used AI to suggest a quick way to distinguish a change in credit allocation from dropped activations. It proposed grouping the saved attribution matrix on each touch column separately, retaining the null group, and comparing each total with the independent experiment arm export.

I ran that check on the original nonzero experiment's `attribution_counts.json` and `arm_counts.json` exports. Group the former on `first_touch_campaign`, then on `last_touch_campaign`, summing `activations` in each group. Compare both totals with the sum of `activated_14d` across the arms.

| Credit rule | Initial email | Reminder | Unattributed | Total |
|---|---:|---:|---:|---:|
| First touch | 442 | 191 | 287 | 920 |
| Last touch | 209 | 424 | 287 | 920 |

The independent assignment-based count was 377 + 543 = 920. The cross-tab showed 233 activations shifting from the initial email to the reminder and no activations disappearing. This confirms that the difference came from the credit rule in this synthetic extract. The randomized comparison uses assigned arms and posted deposits. See the [attribution SQL](../sql/marts/mart_campaign_attribution.sql) and [warehouse reconciliation checks](../tests/experiment_marts.sql).
