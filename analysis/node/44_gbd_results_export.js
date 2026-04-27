#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const RESULTS_URL = "https://vizhub.healthdata.org/gbd-results/";
const METADATA_URL = "https://vizhub.healthdata.org/gbd-results/php/metadata/?language=English";
const DATA_URL = "https://vizhub.healthdata.org/gbd-results/php/data.php";
const DEFAULT_VERSION = 8352;
const TOKEN_BUFFER_SECONDS = 300;
const USER_AGENT = "Mozilla/5.0";

function parseArgs(argv) {
  const args = {
    spec: "",
    storageState: "",
    package: "all",
    forceLogin: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--spec") {
      args.spec = argv[++i] || "";
    } else if (arg === "--storage-state") {
      args.storageState = argv[++i] || "";
    } else if (arg === "--package") {
      args.package = argv[++i] || "all";
    } else if (arg === "--force-login") {
      args.forceLogin = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!args.spec) {
    throw new Error("Missing required argument: --spec");
  }
  return args;
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function decodeJwtPayload(token) {
  const parts = token.split(".");
  if (parts.length < 2) {
    return null;
  }
  const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const pad = payload.length % 4 === 0 ? "" : "=".repeat(4 - (payload.length % 4));
  return JSON.parse(Buffer.from(payload + pad, "base64").toString("utf8"));
}

function getStoredAccessToken(storageStatePath) {
  if (!fs.existsSync(storageStatePath)) {
    return null;
  }
  const state = readJson(storageStatePath);
  for (const origin of state.origins || []) {
    if (origin.origin !== "https://vizhub.healthdata.org") {
      continue;
    }
    for (const item of origin.localStorage || []) {
      if (!item.name.includes("accesstoken")) {
        continue;
      }
      const parsed = JSON.parse(item.value);
      const token = parsed.secret;
      const payload = decodeJwtPayload(token);
      if (!payload || !payload.exp) {
        continue;
      }
      if (payload.exp > Math.floor(Date.now() / 1000) + TOKEN_BUFFER_SECONDS) {
        return token;
      }
    }
  }
  return null;
}

async function loginAndSave(storageStatePath, email, password) {
  if (!email || !password) {
    throw new Error(
      "GBD Results login requires GBD_RESULTS_EMAIL and GBD_RESULTS_PASSWORD when no valid storage state is available."
    );
  }
  ensureDir(path.dirname(storageStatePath));
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } });
  const page = await context.newPage();
  await page.goto(RESULTS_URL, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.getByRole("button", { name: "Sign in" }).last().click();
  await page.waitForSelector('input[name="signInName"]', { timeout: 120000 });
  await page.fill('input[name="signInName"]', email);
  await page.fill('input[name="password"]', password);
  await page.locator('input[name="password"]').press("Enter");
  await page.waitForFunction(
    () => document.body.innerText.includes("Sign out") && document.body.innerText.includes("Download"),
    { timeout: 120000 }
  );
  await context.storageState({ path: storageStatePath });
  await browser.close();
}

async function ensureAccessToken(storageStatePath, forceLogin) {
  if (!forceLogin) {
    const token = getStoredAccessToken(storageStatePath);
    if (token) {
      return token;
    }
  }
  await loginAndSave(
    storageStatePath,
    process.env.GBD_RESULTS_EMAIL || "",
    process.env.GBD_RESULTS_PASSWORD || ""
  );
  const refreshed = getStoredAccessToken(storageStatePath);
  if (!refreshed) {
    throw new Error("Unable to recover a valid GBD Results access token after login.");
  }
  return refreshed;
}

async function fetchJson(url, token = "") {
  const headers = { "user-agent": USER_AGENT };
  if (token) {
    headers.authorization = `Bearer ${token}`;
    headers.accept = "application/json, text/plain, */*";
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: HTTP ${response.status}`);
  }
  return await response.json();
}

function buildSearchBody(params) {
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      value.forEach((item, idx) => {
        body.append(`${key}[${idx}]`, String(item));
      });
      continue;
    }
    if (value !== undefined && value !== null && value !== "") {
      body.append(key, String(value));
    }
  }
  return body.toString();
}

async function postData(params, token) {
  const body = buildSearchBody(params);
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    const response = await fetch(DATA_URL, {
      method: "POST",
      headers: {
        "user-agent": USER_AGENT,
        "content-type": "application/x-www-form-urlencoded",
        authorization: `Bearer ${token}`,
        accept: "application/json, text/plain, */*",
      },
      body,
    });
    const text = await response.text();
    if (response.ok) {
      if (text.startsWith("A database error occurred")) {
        return { cols: [], data: [], _warning: text };
      }
      return JSON.parse(text);
    }
    if (response.status >= 500 && attempt < 6) {
      const waitMs = attempt * 2000;
      console.warn(`Retrying GBD Results API after HTTP ${response.status}; attempt ${attempt}/6, waiting ${waitMs} ms`);
      await new Promise((resolve) => setTimeout(resolve, waitMs));
      continue;
    }
    throw new Error(`GBD Results API error ${response.status}: ${text}`);
  }
  throw new Error("GBD Results API failed after retry exhaustion.");
}

function buildIdMaps(metadata) {
  const maps = {};
  for (const section of ["measure", "metric", "sex", "age", "location", "cause", "rei", "population_group"]) {
    maps[section] = {};
    const source = metadata.data[section] || {};
    for (const [id, record] of Object.entries(source)) {
      maps[section][String(id)] = record.name;
    }
  }
  return maps;
}

function rowsToRecords(rows, cols, maps) {
  return rows.map((row) => {
    const record = {};
    cols.forEach((col, idx) => {
      const value = row[idx];
      if (["measure", "metric", "location", "sex", "age", "cause", "rei", "population_group"].includes(col)) {
        record[`${col}_id`] = value;
        record[`${col}_name`] = maps[col][String(value)] || "";
      } else if (col === "year") {
        record.year_id = value;
      } else {
        record[col] = value;
      }
    });
    return record;
  });
}

function sortRecords(records, includeRei) {
  records.sort((a, b) => {
    const keys = includeRei
      ? ["measure_id", "rei_id", "location_id", "age_id", "sex_id", "metric_id", "year_id"]
      : ["measure_id", "location_id", "age_id", "sex_id", "metric_id", "year_id"];
    for (const key of keys) {
      const left = a[key] ?? "";
      const right = b[key] ?? "";
      if (left < right) {
        return -1;
      }
      if (left > right) {
        return 1;
      }
    }
    return 0;
  });
}

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function writeCsv(filePath, records, columns) {
  ensureDir(path.dirname(filePath));
  const lines = [columns.join(",")];
  for (const record of records) {
    lines.push(columns.map((column) => csvEscape(record[column])).join(","));
  }
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf8");
}

function yearsRange(start, end) {
  const years = [];
  for (let year = start; year <= end; year += 1) {
    years.push(year);
  }
  return years;
}

function buildSummary(records, includeRei) {
  const unique = (field) => Array.from(new Set(records.map((row) => row[field]))).sort();
  const summary = {
    rows: records.length,
    locations: unique("location_name"),
    measures: unique("measure_name"),
    ages: unique("age_name"),
    years: unique("year_id"),
  };
  if (includeRei) {
    summary.reis = unique("rei_name");
  }
  return summary;
}

async function exportCore(spec, metadata, token) {
  const maps = buildIdMaps(metadata);
  const locationIds = spec.geography.locations.map((item) => item.location_id);
  const ageIds = spec.population.age_groups_under_40.map((item) => item.age_group_id);
  const years = yearsRange(spec.years.start, spec.years.end);
  const measureIds = [1, 2, 5, 6];
  const allRecords = [];

  for (const measureId of measureIds) {
    const result = await postData(
      {
        context: "cause",
        population_group: 1,
        cause: [515],
        measure: [measureId],
        metric: [1, 3],
        location: locationIds,
        age: ageIds,
        sex: [2],
        year: years,
        base: "single",
        version: DEFAULT_VERSION,
        start_year: spec.years.start,
        fetch_all_years: false,
      },
      token
    );
    allRecords.push(...rowsToRecords(result.data, result.cols, maps));
    console.log(`core measure ${measureId}: ${result.data.length} rows`);
  }

  sortRecords(allRecords, false);
  return allRecords;
}

async function exportRisk(spec, metadata, token, measureId) {
  const maps = buildIdMaps(metadata);
  const locationIds = spec.geography.locations.map((item) => item.location_id);
  const ageIds = spec.population.age_groups_under_40.map((item) => item.age_group_id);
  const years = yearsRange(spec.years.start, spec.years.end);
  const detailedRisks = Object.values(metadata.data.rei)
    .filter((item) => item.type === "risk" && Number(item.most_detailed) === 1)
    .map((item) => item.id)
    .sort((a, b) => a - b);

  const allRecords = [];
  const warnings = [];
  for (let idx = 0; idx < detailedRisks.length; idx += 1) {
    const riskId = detailedRisks[idx];
    let result;
    try {
      result = await postData(
        {
          context: "risk",
          population_group: 1,
          cause: [515],
          risk: [riskId],
          rei: [riskId],
          measure: [measureId],
          metric: [1, 3],
          location: locationIds,
          age: ageIds,
          sex: [2],
          year: years,
          base: "single",
          version: DEFAULT_VERSION,
          start_year: spec.years.start,
          fetch_all_years: false,
        },
        token
      );
    } catch (error) {
      warnings.push({ risk_id: riskId, warning: String(error) });
      continue;
    }
    if (result._warning) {
      warnings.push({ risk_id: riskId, warning: result._warning });
      continue;
    }
    if (result.data.length === 0) {
      continue;
    }
    allRecords.push(...rowsToRecords(result.data, result.cols, maps));
    console.log(`risk measure ${measureId}: ${idx + 1}/${detailedRisks.length} -> risk ${riskId}, ${result.data.length} rows`);
  }

  sortRecords(allRecords, true);
  return { records: allRecords, warnings };
}

async function main() {
  const args = parseArgs(process.argv);
  const spec = readJson(args.spec);
  const storageStatePath =
    args.storageState ||
    path.join(spec.workspace_root, "specs", "gbd_results_storage_state.json");

  const token = await ensureAccessToken(storageStatePath, args.forceLogin);
  const metadata = await fetchJson(METADATA_URL);

  const outputs = [];
  if (args.package === "all" || args.package === "core_burden") {
    const core = await exportCore(spec, metadata, token);
    const coreColumns = [
      "population_group_id",
      "population_group_name",
      "measure_id",
      "measure_name",
      "location_id",
      "location_name",
      "sex_id",
      "sex_name",
      "age_id",
      "age_name",
      "cause_id",
      "cause_name",
      "metric_id",
      "metric_name",
      "year_id",
      "val",
      "upper",
      "lower",
    ];
    const outputFile = spec.export_packages.find((item) => item.package_id === "core_burden").output_file;
    writeCsv(outputFile, core, coreColumns);
    outputs.push({
      package_id: "core_burden",
      output_file: outputFile,
      summary: buildSummary(core, false),
    });
  }

  if (args.package === "all" || args.package === "risk_attributable_deaths") {
    const riskDeaths = await exportRisk(spec, metadata, token, 1);
    const columns = [
      "population_group_id",
      "population_group_name",
      "measure_id",
      "measure_name",
      "location_id",
      "location_name",
      "sex_id",
      "sex_name",
      "age_id",
      "age_name",
      "cause_id",
      "cause_name",
      "rei_id",
      "rei_name",
      "metric_id",
      "metric_name",
      "year_id",
      "val",
      "upper",
      "lower",
    ];
    const outputFile = spec.export_packages.find((item) => item.package_id === "risk_attributable_deaths").output_file;
    writeCsv(outputFile, riskDeaths.records, columns);
    outputs.push({
      package_id: "risk_attributable_deaths",
      output_file: outputFile,
      summary: buildSummary(riskDeaths.records, true),
      warnings: riskDeaths.warnings,
    });
  }

  if (args.package === "all" || args.package === "risk_attributable_dalys") {
    const riskDalys = await exportRisk(spec, metadata, token, 2);
    const columns = [
      "population_group_id",
      "population_group_name",
      "measure_id",
      "measure_name",
      "location_id",
      "location_name",
      "sex_id",
      "sex_name",
      "age_id",
      "age_name",
      "cause_id",
      "cause_name",
      "rei_id",
      "rei_name",
      "metric_id",
      "metric_name",
      "year_id",
      "val",
      "upper",
      "lower",
    ];
    const outputFile = spec.export_packages.find((item) => item.package_id === "risk_attributable_dalys").output_file;
    writeCsv(outputFile, riskDalys.records, columns);
    outputs.push({
      package_id: "risk_attributable_dalys",
      output_file: outputFile,
      summary: buildSummary(riskDalys.records, true),
      warnings: riskDalys.warnings,
    });
  }

  const qcPath = path.join(spec.data_targets.table_root, "gbd_results_export_qc.json");
  ensureDir(path.dirname(qcPath));
  let existingOutputs = [];
  if (fs.existsSync(qcPath)) {
    try {
      existingOutputs = readJson(qcPath).outputs || [];
    } catch (_error) {
      existingOutputs = [];
    }
  }
  const mergedByPackage = {};
  for (const item of existingOutputs) {
    mergedByPackage[item.package_id] = item;
  }
  for (const item of outputs) {
    mergedByPackage[item.package_id] = item;
  }
  fs.writeFileSync(
    qcPath,
    JSON.stringify(
      {
        study_id: spec.study_id,
        generated_at: new Date().toISOString(),
        storage_state: storageStatePath,
        outputs: Object.values(mergedByPackage).sort((a, b) =>
          String(a.package_id).localeCompare(String(b.package_id))
        ),
      },
      null,
      2
    ),
    "utf8"
  );

  console.log(`QC written to ${qcPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
