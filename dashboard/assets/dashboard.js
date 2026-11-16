(() => {
  "use strict";

  const main = document.querySelector("#main");
  const integer = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
  const percentTick = new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 2 });
  const pages = {
    overview: "Executive Overview", details: "Analysis Details", visualizations: "Visualizations",
  };
  const colors = {};
  const charts = new Map();
  let dataset;
  let currentPage;
  const themeToggle = document.querySelector("#theme-toggle");

  const text = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
  const number = (value) => value == null ? "—" : integer.format(Number(value));
  const decimal = (value, precision = 2) => value == null ? "—" : Number(value).toFixed(precision);
  const percent = (value, precision = 2) => value == null ? "—" : `${decimal(Number(value) * 100, precision)}%`;
  const signed = (value, precision = 2) => value == null ? "—" : `${value < 0 ? "−" : "+"}${decimal(Math.abs(value), precision)}`;
  const points = (value) => value == null ? "—" : `${signed(value * 100)} pp`;
  const interval = (values) => values == null ? "—" : `${signed(values[0] * 100)} to ${signed(values[1] * 100)} pp`;
  const rowFor = (name, value) => dataset.history.segments.find((row) =>
    row.breakdown === name && row.breakdown_value === value);
  const primary = () => dataset.experiment.metrics.activated_14d;

  function table(columns, rows, caption, disclosure = false) {
    const content = `<div class="table-scroll" role="region" aria-label="${text(caption)}" tabindex="0">
      <table class="data-table"><caption>${text(caption)}</caption>
        <thead><tr>${columns.map((cell) => `<th scope="col">${text(cell)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${row.map((cell, index) => index === 0
          ? `<th scope="row">${text(cell)}</th>` : `<td>${text(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>`;
    return disclosure ? `<details class="table-disclosure"><summary>View chart data</summary>${content}</details>` : content;
  }

  function heading(label, description) {
    return `<div class="page-title"><h1>${text(label)}</h1><p>${text(description)}</p></div>`;
  }

  function panel(id, label, description, detail) {
    return `<article class="panel"><h2 id="${id}-label">${text(label)}</h2>
      <p class="panel-desc">${text(description)}</p>
      <div id="${id}" class="plot" aria-labelledby="${id}-label"></div>${detail}</article>`;
  }

  function release(id) {
    const entry = charts.get(id);
    if (entry) {
      entry.observer.disconnect();
      entry.chart.dispose();
      charts.delete(id);
    }
  }

  function draw(id, option) {
    const element = document.getElementById(id);
    if (!element) return;
    release(id);
    if (!window.echarts) {
      element.classList.add("plot-fallback");
      element.textContent = "Chart unavailable. The values are in the data table below.";
      return;
    }
    const chart = echarts.init(element, null, { renderer: "canvas" });
    chart.setOption({
      animation: false,
      aria: { enabled: true },
      textStyle: { fontFamily: "Inter, system-ui, sans-serif", fontSize: 11 },
      color: [colors.blue, colors.slate, colors.cyan],
      ...option,
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    charts.set(id, { chart, observer });
  }

  const axisText = { fontSize: 11 };
  const grid = { top: 25, bottom: 34, left: 15, right: 27, containLabel: true };
  const valueAxis = (formatter) => ({
    type: "value", axisLabel: { ...axisText, formatter: (value) => formatter(value) }, splitLine: { lineStyle: { color: colors.line } },
  });
  const categoryAxis = (names) => ({
    type: "category", data: names, axisLabel: axisText, axisTick: { show: false },
    axisLine: { show: false },
  });
  const tooltip = (format) => ({
    trigger: "axis", confine: true,
    valueFormatter: (value) => format(value), backgroundColor: colors.paper, borderColor: colors.line, textStyle: { color: colors.ink },
  });

  function bars(id, names, series, format, { horizontal = false, axisFormat = format } = {}) {
    const categories = categoryAxis(names);
    const axis = valueAxis(axisFormat);
    draw(id, {
      grid: { ...grid, top: series.length > 1 ? 38 : 23 },
      tooltip: { ...tooltip(format), axisPointer: { type: "shadow" } },
      legend: series.length > 1 ? { top: 4, left: "center", textStyle: axisText } : undefined,
      xAxis: horizontal ? axis : categories,
      yAxis: horizontal ? { ...categories, inverse: true } : { ...axis, min: 0 },
      series: series.map(({ name, values, color, label }) => ({
        name, data: values, type: "bar", barMaxWidth: horizontal ? 24 : 34,
        itemStyle: { color, borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
        label: label ? { show: true, position: horizontal ? "right" : "top", color: colors.ink,
          formatter: (params) => format(params.value) } : undefined,
      })),
    });
  }

  const repository = "https://github.com/bonnerjosh/marketing-analytics-campaign-analysis";
  const emailDesign = "Both groups were assigned the same follow-up email. The first email used either standard copy or personalized, goal-oriented copy.";
  const reminderDesign = "Both groups were assigned the same standard email. Only the second group was eligible to see an in-app reminder.";
  const repeatDefinition = "Made a first deposit within 14 days and a second within 30 days of the first.";

  function experiments() {
    const rows = [{
      label: "Email personalization", control: "Standard email", treatment: "Personalized email",
      design: emailDesign, result: primary(),
    }];
    if (dataset.reminder?.warehouse_verified) {
      rows.push({
        label: "In-app reminder", control: "Standard email", treatment: "Email + in-app reminder",
        design: reminderDesign, result: dataset.reminder.primary,
      });
    }
    return rows;
  }

  function overview() {
    const funnel = dataset.history.funnel;
    const comparisons = experiments();
    const repeat = dataset.experiment.metrics.sustained_saving;

    main.innerHTML = `<section class="overview-intro">
        <div class="overview-copy">
          <h1>New Year, New Savings</h1>
          <p class="overview-lede">A marketing analytics case study for a fictional fintech, using synthetic customer and campaign data.</p>
          <p><strong>The problem.</strong> Many customers opened a savings account and left it unfunded. Only <strong>${percent(funnel.activation_rate, 1)}</strong> of the ${number(funnel.opened)} customers who opened savings within 30 days of signup made a first deposit in the following 30 days.</p>
          <p><strong>The thesis.</strong> A personalized savings email or an in-app reminder could help more customers with unfunded accounts make their first deposit.</p>
          <p>I designed the experiments, generated the synthetic data in Python, and used BigQuery to measure first deposits from posted transactions.</p>
        </div>
        <div class="deposit-visual" role="img" aria-label="Illustration of a mobile banking app confirming a first deposit into savings">
          <div class="deposit-phone" aria-hidden="true">
            <div class="deposit-screen">
              <div class="deposit-confirmation">
                <span class="deposit-check">&#10003;</span>
                <strong>Deposit complete</strong>
                <span>Your first savings deposit</span>
              </div>
              <dl class="deposit-details">
                <div><dt>From</dt><dd>Checking</dd></div>
                <div><dt>To</dt><dd>Savings</dd></div>
              </dl>
            </div>
          </div>
        </div>
        <div class="overview-cta">
          <p>For full analysis details</p>
          <a href="${repository}">View on GitHub</a>
        </div>
      </section>
      <section class="panel overview-section">
        <h2>What I tested and found</h2>
        <p>Each test randomly assigned eligible customers to two groups and counted first deposits within 14 days for everyone assigned.</p>
        ${table(["Test", "Standard approach", "Campaign change", "Lift (95% confidence interval)"], comparisons.map(({ label, control, treatment, result }) =>
          [label, `${control} · ${percent(result.control.rate)}`, `${treatment} · ${percent(result.treatment.rate)}`,
            `${signed(result.absolute_lift * 100)} percentage points (${interval(result.ci95)})`]), "14-day first deposits")}
        <p>The simulator was designed to produce a lift ${comparisons.length > 1 ? "in each test. The two tests had different control experiences, so choosing between personalization and the in-app reminder would require a direct comparison." : "in the email test."} The results demonstrate how I would measure lift in a real campaign.</p>
        <p>Both groups in the email test were assigned the same follow-up email.</p>
        <p>In the email test, ${percent(repeat.treatment.rate)} of customers assigned to personalization started and made a second deposit, compared with ${percent(repeat.control.rate)} on standard email. That exploratory result gives the real test a reason to track repeat saving.</p>
      </section>
      <section class="panel overview-section">
        <h2>Next Steps</h2>
        <p>This simulation measured first deposits. To estimate ROI, the next step is to run a real customer test, estimate the business value of the additional funded accounts, and compare that value with the extra cost of running each campaign.</p>
      </section>`;
  }

  function details() {
    const funnel = dataset.history.funnel;
    const comparisons = experiments();
    const email = primary();
    const reminder = comparisons[1]?.result;
    const repeat = dataset.experiment.metrics.sustained_saving;
    const power = dataset.power;
    const attribution = dataset.campaign.attribution;
    const firstCredit = attribution.first_touch_campaign.ny_savings_index;
    const lastCredit = attribution.last_touch_campaign.ny_savings_index;
    const profileRules = [
      ["A · Engaged but unfunded", "At least 6 app sessions, 2 savings-related sessions and 4 checking transactions."],
      ["B · Financially active, low savings engagement", "At least 6 checking transactions and 2 app sessions, with at most 1 savings-related session."],
      ["C · Dormant or low engagement", "Everyone who met neither preceding rule."],
    ];

    main.innerHTML = heading("Analysis Details", "The eligible audience, randomized comparisons, and checks behind the synthetic results.")
      + `<section class="panel overview-section">
        <h2>Who qualified</h2>
        <p>The historical funnel followed ${number(funnel.signups)} signups with 90 days of observation. Within 30 days of signup, ${number(funnel.opened)} opened savings. Of those, ${number(funnel.activated)} made a first deposit within the next 30 days.</p>
        <p>For each experiment, the eligible population was the same ${number(email.control.n + email.treatment.n)} customers who had an open savings account and no prior qualifying savings deposit on January 1, 2027. Eligibility and behavioral profiles were fixed before random assignment.</p>
        <details><summary>See behavioral profiles</summary>
          <p>Rules use activity from the prior 30 days and are applied in order.</p>
          ${table(["Profile", "Rule", "Eligible customers"], profileRules.map(([label, rule]) =>
            [label, rule, number(rowFor("profile", label[0]).eligible_customers)]), "Predefined behavioral profiles")}
        </details>
      </section>
      <section class="panel overview-section">
        <h2>How the tests worked</h2>
        <p>The primary outcome was a positive, completed first savings deposit within 14 days of assignment. In the reminder test, the deposit had to post to the eligible account identified at assignment. Everyone counted in their assigned group, including customers who never saw a message.</p>
        ${comparisons.map(({ label, control, treatment, design, result }) => `<h3>${label}</h3>
          <p>${design}</p>
          ${table(["Group", "Assigned customers", "First deposits", "Rate"], [[control, result.control], [treatment, result.treatment]].map(([name, arm]) =>
            [name, number(arm.n), number(arm.events), percent(arm.rate)]), `${label} results`)}`).join("")}
        ${reminder ? `<p>The in-app reminder appeared for ${number(dataset.reminder.shown)} of ${number(reminder.treatment.n)} customers assigned to receive it. Keeping the whole group in the comparison measures the effect of assigning the reminder under this delivery policy.</p>` : ""}
      </section>
      <section class="panel overview-section">
        <h2>What the results can tell us</h2>
        ${table(["Test", "Lift in first deposits", "95% confidence interval"], comparisons.map(({ label, result }) =>
          [label, points(result.absolute_lift), interval(result.ci95)]), "Difference in 14-day first-deposit rates")}
        <p><strong>Repeat saving.</strong> ${repeatDefinition} This applied to ${percent(repeat.treatment.rate)} of the personalized group and ${percent(repeat.control.rate)} of the standard group. The exploratory measure combines starting and returning, so the effect on saving behavior after the first deposit remains open.</p>
        <p>The results reflect programmed effects in synthetic data. Each test changed one part of the campaign. Estimating the effect of sending any savings email would require a group that receives no campaign message.</p>
        <details><summary>See sample-size and power assumptions</summary>
          <p>For email personalization, the planned baseline was ${percent(power.profile_mixture.control_assumption)}, with ${percent(power.profile_mixture.power_at_target, 1)} power to detect a ${points(power.target_lift)} lift. The minimum detectable lift at 80% power was ${points(power.profile_mixture.mde_absolute)}${reminder ? ` for personalization and ${points(dataset.reminder.mde)} for the in-app reminder` : ""}. The primary tests used a two-sided 5% threshold.</p>
        </details>
      </section>
      <section class="panel overview-section">
        <h2>How I checked the measurement</h2>
        <p><strong>Email personalization.</strong> Crediting the earliest versus latest eligible delivery changed the first email’s credit from ${number(firstCredit)} to ${number(lastCredit)} deposits. Both methods accounted for all ${number(email.control.events + email.treatment.events)} first deposits, including unattributed deposits. The randomized estimate uses assigned groups and posted deposits.</p>
        ${reminder ? `<p><strong>In-app reminder.</strong> BigQuery and an independent Python implementation matched across all ${number(reminder.control.n + reminder.treatment.n)} assigned customers. They reconciled assignment, funding, impressions, and touch credit. See the <a href="${repository}/blob/main/sql/marts/mart_reminder_customers.sql">reminder SQL</a> and <a href="${repository}/blob/main/tests/test_reminder.py">edge-case tests</a>.</p>` : ""}
        <p><a href="${repository}/blob/main/docs/EXPERIMENT_DESIGN.md">Email experiment design</a> · <a href="${repository}/blob/main/sql/marts/mart_experiment_customers.sql">Email outcome SQL</a> · <a href="${repository}/blob/main/tests/experiment_marts.sql">Warehouse checks</a></p>
      </section>`;
  }

  function visualizations() {
    const funnel = dataset.history.funnel;
    const comparisons = experiments();
    const repeat = dataset.experiment.metrics.sustained_saving;
    const stages = [["Signed up", funnel.signups], ["Opened savings", funnel.opened], ["First deposit", funnel.activated]];
    const attribution = dataset.campaign.attribution;
    const credits = [
      ["Initial email", "ny_savings_index", colors.blue],
      ["Follow-up email", "ny_savings_reminder", colors.cyan],
      ["Unattributed", "unattributed", colors.slate],
    ].map(([name, key, color]) => ({
      name, color, values: [attribution.first_touch_campaign[key] ?? 0, attribution.last_touch_campaign[key] ?? 0],
    }));
    const total = credits.reduce((sum, credit) => sum + credit.values[0], 0);

    main.innerHTML = heading("Visualizations", "From the historical funding gap to the results of the randomized campaign tests.")
      + panel("funding-gap", "Where customers stopped in the savings journey",
        `Only ${percent(funnel.activation_rate, 1)} of customers who opened savings within 30 days of signup made a first deposit in the following 30 days.`,
        table(["Stage", "Customers"], stages.map(([stage, count]) => [stage, number(count)]), "Historical savings funnel", true))
      + panel("campaign-lift", "Did either campaign change increase first deposits?",
        "Both comparisons use the share of assigned customers who made a first deposit within 14 days.",
        `<p class="chart-takeaway">${comparisons.map(({ label, result }) => `${label} ${points(result.absolute_lift)}`).join(" · ")}</p>
        ${table(["Test", "Standard approach", "Campaign change"], comparisons.map(({ label, result }) =>
          [label, percent(result.control.rate), percent(result.treatment.rate)]), "First-deposit rates", true)}`)
      + panel("repeat-saving", "Did customers come back to save again?",
        `${repeatDefinition} This was an exploratory outcome in the email test.`,
        table(["Group", "Started and returned"], [["Standard email", percent(repeat.control.rate)],
          ["Personalized email", percent(repeat.treatment.rate)]], "Repeat saving rates", true))
      + panel("touch-credit", "How does the attribution rule change which email gets credit?",
        `Crediting the earliest or latest eligible email shifts credit between messages. Both rules account for the same ${number(total)} first deposits, including unattributed deposits.`,
        table(["Credit", "First-touch", "Last-touch"], credits.map(({ name, values }) =>
          [name, ...values.map(number)]), "Email attribution counts", true));

    bars("funding-gap", stages.map(([label]) => label), [{
      name: "Customers", label: true, values: stages.map(([, value], index) => ({
        value, itemStyle: { color: index === 2 ? colors.blue : colors.slate },
      })),
    }], number, { horizontal: true });
    bars("campaign-lift", comparisons.map(({ label }) => label), [
      { name: "Standard approach", values: comparisons.map(({ result }) => result.control.rate), color: colors.slate, label: true },
      { name: "Campaign change", values: comparisons.map(({ result }) => result.treatment.rate), color: colors.blue, label: true },
    ], percent, { axisFormat: percentTick.format });
    bars("repeat-saving", ["Standard email", "Personalized email"], [{
      name: "Started and returned", label: true, values: [
        { value: repeat.control.rate, itemStyle: { color: colors.slate } },
        { value: repeat.treatment.rate, itemStyle: { color: colors.blue } },
      ],
    }], percent, { axisFormat: percentTick.format });
    draw("touch-credit", {
      grid: { ...grid, top: 54 },
      tooltip: tooltip(number),
      legend: { top: 4, textStyle: axisText },
      xAxis: valueAxis(number),
      yAxis: { ...categoryAxis(["First-touch", "Last-touch"]), inverse: true },
      series: credits.map(({ name, values, color }) => ({
        name, type: "bar", stack: "credit", data: values, itemStyle: { color }, barMaxWidth: 30,
      })),
    });
  }

  const views = { overview, details, visualizations };
  const legacyPages = { customers: "details", experiment: "details", lifecycle: "visualizations", campaign: "visualizations" };

  function displayPage() {
    if (!dataset) return;
    const fragment = window.location.hash.slice(1);
    if (fragment === "main") return;
    const route = Object.hasOwn(legacyPages, fragment) ? legacyPages[fragment] : fragment;
    const page = Object.hasOwn(views, route) ? route : "overview";
    if (route !== fragment) history.replaceState(null, "", `#${route}`);
    if (currentPage === page) return;
    for (const id of charts.keys()) release(id);
    document.querySelector("#breadcrumb").textContent = pages[page];
    document.title = `${pages[page]} | New Year, New Savings`;
    document.querySelectorAll(".navigation a").forEach((anchor) => {
      if (anchor.getAttribute("href") === `#${page}`) anchor.setAttribute("aria-current", "page");
      else anchor.removeAttribute("aria-current");
    });
    views[page]();
    if (currentPage) {
      window.scrollTo(0, 0);
      main.focus({ preventScroll: true });
    }
    currentPage = page;
  }

  function setTheme(dark) {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    themeToggle.setAttribute("aria-pressed", String(dark));
    const styles = getComputedStyle(document.documentElement);
    for (const key of ["cyan", "blue", "slate", "ink", "line", "paper"]) {
      colors[key] = styles.getPropertyValue(`--${key}`).trim();
    }
    axisText.color = colors.ink;
  }

  let prefersDark = false;
  try {
    prefersDark = localStorage.getItem("savings-dashboard-theme") === "dark";
  } catch {
    // The toggle still works when the browser blocks storage.
  }
  setTheme(prefersDark);
  themeToggle.addEventListener("click", () => {
    const dark = themeToggle.getAttribute("aria-pressed") !== "true";
    setTheme(dark);
    try {
      localStorage.setItem("savings-dashboard-theme", dark ? "dark" : "light");
    } catch {
      // The current page keeps its theme without saved preferences.
    }
    if (!currentPage) return;
    const disclosures = Array.from(main.querySelectorAll("details"), (details) => details.open);
    for (const id of charts.keys()) release(id);
    views[currentPage]();
    main.querySelectorAll("details").forEach((details, index) => { details.open = disclosures[index]; });
  });

  window.addEventListener("hashchange", displayPage);
  async function start() {
    try {
      const [response, reminderResponse] = await Promise.all([
        fetch("./data/analytics.json"), fetch("./data/reminder.json").catch(() => null),
      ]);
      if (!response.ok) throw new Error("Analytics snapshot could not be loaded");
      const payload = await response.json();
      if (payload.schema_version !== 1 || payload.synthetic !== true || !payload.experiment || !payload.history) {
        throw new Error("Incorrect analytics snapshot");
      }
      if (reminderResponse?.ok) {
        payload.reminder = await reminderResponse.json().catch(() => null);
      }
      dataset = payload;
      if (window.location.hash === "#main") history.replaceState(null, "", "#overview");
      displayPage();
    } catch (error) {
      main.innerHTML = `<p class="load-state" role="alert">The analytics snapshot could not be displayed. Refresh the page or open the dashboard through its local HTTP server.</p>`;
      console.error(error);
    }
  }
  start();
})();
