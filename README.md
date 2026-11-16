# New Year, New Savings

A marketing analytics case study for a fictional fintech, using synthetic customer and campaign data. Of the 7,085 customers who opened savings within 30 days of signup, only **24.5%** made a first deposit in the following 30 days. I designed two randomized simulations to show how a lifecycle marketing team could measure whether better messaging helps customers fund their accounts.

[Open the interactive dashboard](https://bonnerjosh.github.io/marketing-analytics-campaign-analysis/) · [Run locally](#view-the-dashboard) · [Reproduce the analysis](#reproduce-the-analysis)

## What I tested and found

Each experiment used the same 10,701 eligible customers. The outcome was a first qualifying deposit within 14 days, measured from posted transactions for everyone assigned.

| Test | Standard approach | Campaign change | Lift (95% confidence interval) |
|---|---|---|---|
| Email personalization | Standard email · 377 / 5,310 (7.10%) | Personalized email · 543 / 5,391 (10.07%) | **+2.97 percentage points** (+1.91 to +4.03) |
| In-app reminder | Standard email alone · 369 / 5,350 (6.90%) | Same email + in-app reminder eligibility · 473 / 5,351 (8.84%) | **+1.94 percentage points** (+0.92 to +2.96) |

Both groups in the email test were assigned the same follow-up email. The simulator was designed to produce a lift in each test. The tests demonstrate how to measure lift in a real campaign. Choosing between the changes would require a direct comparison because each test used a different control experience.

In the email test, **3.34%** of customers assigned to personalization made a first deposit within 14 days and a second within 30 days of the first, compared with **2.56%** of customers assigned to standard email. The exploratory result supports tracking repeat saving in a real customer test. A rollout decision would compare the business value of additional funded accounts with the extra cost of the campaign.

[Email experiment findings](docs/EXPERIMENT_FINDINGS.md) · [Reminder design](docs/REMINDER_DESIGN.md) · [Reminder SQL](sql/marts/mart_reminder_customers.sql) · [Reminder tests](tests/test_reminder.py) · [Attribution reconciliation](docs/AI_VALIDATION.md)

## Analytical approach

- **Customer segmentation.** Identify customers who had an open, never-funded savings account at assignment. Use the prior 30 days of app sessions, savings interactions and checking activity to assign one of three predefined profiles. Freeze eligibility and profiles before randomization.
- **Savings lifecycle.** Use account records to measure savings opening and completed transactions to measure first and repeat deposits. Compare cohorts with complete follow-up. Use GA4-style app events to measure behavior such as viewing savings or starting a deposit. The transaction record determines when money moved.
- **Campaign measurement.** Measure delivery and clicks using their own denominators. Compare first-touch and last-touch attribution to see how the order of messages changes which email receives credit. Use random assignment to estimate incremental impact.
- **Randomized tests.** Run separate comparisons for email personalization and the in-app reminder. Use a two-sided test and a 95% interval for the absolute difference in funding rates. A separate null scenario checked the email analysis with no programmed effect. For the in-app reminder test, the BigQuery results matched an independent Python calculation for all 10,701 assigned customers.

See [definitions and windows](docs/METRICS.md), [experiment design and statistical assumptions](docs/EXPERIMENT_DESIGN.md), and [full findings](docs/EXPERIMENT_FINDINGS.md).

## Architecture and repository

Python generates seeded customer, account, transaction and GA4-style event data. BigQuery SQL loads and transforms those records into tables for cohorts, campaign activity and customer-level experiment outcomes. Python reconciles the warehouse results with the underlying facts and calculates uncertainty. A static ECharts dashboard renders the checked-in aggregate JSON.

| Path | Contents |
|---|---|
| `src/` | Generation, BigQuery jobs, simulation, statistical analysis and dashboard export |
| `sql/` | Staging views and historical, campaign and experiment models |
| `tests/` | Python validation and BigQuery reconciliation checks |
| `dashboard/` | Static dashboard assets and aggregate results |
| `docs/` | [Data model](docs/DATA_MODEL.md), metrics, experiment design and detailed findings |

## View the dashboard

The local dashboard shows the Executive Overview, Analysis Details, and Visualizations. From the repository root, run the static server.

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory dashboard
```

Open [the local dashboard](http://127.0.0.1:8765/). It uses the included aggregate snapshot and vendored chart assets, so this preview needs no BigQuery access.

## Reproduce the analysis

Use Python 3.12 and the BigQuery CLI and access to a dedicated dataset in the US location. The full run submits BigQuery jobs and stores tables. Review the project's billing and permissions first. The runner dry-runs analytical queries and caps each job at 1 GiB.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

export BQ_PROJECT=your-project-id
export BQ_DATASET=new_year_new_savings
export BQ_LOCATION=US

python src/generate_data.py --customers 40000 --seed 20270101
python src/run_sql.py create-dataset  # Skip when the dedicated dataset already exists.
python src/run_sql.py smoke
python src/run_sql.py history

python src/experiment_plan.py data/history data/experiment/power_plan.json
python src/simulate_experiment.py data/history data/experiment
python src/run_experiment_sql.py data/history data/experiment
python src/analyze_experiment.py data/history data/experiment
python src/build_dashboard.py data/history data/experiment
HISTORY_DIR=data/history python -m unittest discover -s tests -v
```

The root `data/` directory holds generated rows and validation receipts and is ignored by Git. Run the historical build before follow-up facts are loaded. If the history load succeeds but the historical SQL fails, use `python src/run_sql.py marts` to resume without reloading the raw files. For the unit tests alone, run the final command without `HISTORY_DIR`.

### Reproduce the reminder analysis

After building the original frozen historical population, run:

```bash
python src/reminder_experiment.py data/history data/reminder dashboard/data/reminder.json --warehouse
```

The command uses the US dataset in the validated history receipt, replaces its dedicated synthetic `raw_reminder_events` table, and reads the customer model under the existing 1 GiB cap. It compares each row with the independent Python calculation before writing the dashboard snapshot. Omitting `--warehouse` produces a locally reconciled snapshot that the dashboard excludes from its experiment results. The historical email outputs use their existing, separate pipeline.

## Limitations

The generator specifies the response probabilities, so the estimates demonstrate a workflow for making a decision under uncertainty. They cannot establish how real customers would respond. The standard-email comparison estimates the value of personalization relative to the standard message. The exploratory repeat result combines first funding and a return deposit within a fixed window, and cannot establish longer-term saving habits. Channel and regional comparisons are descriptive and may reflect differences in customer mix.
