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

function writeJson(filePath, payload) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
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
  for (const section of ["measure", "metric", "sex", "age", "location", "cause", "population_group"]) {
    maps[section] = {};
    const source = metadata.data[section] || {};
    for (const [id, record] of Object.entries(source)) {
      maps[section][String(id)] = record.name;
    }
  }
  return maps;
}

function yearsRange(start, end) {
  const years = [];
  for (let year = start; year <= end; year += 1) {
    years.push(year);
  }
  return years;
}

function chunkArray(items, chunkSize) {
  const chunks = [];
  for (let idx = 0; idx < items.length; idx += chunkSize) {
    chunks.push(items.slice(idx, idx + chunkSize));
  }
  return chunks;
}

function rowsToRecords(rows, cols, maps) {
  return rows.map((row) => {
    const record = {};
    cols.forEach((col, idx) => {
      const value = row[idx];
      if (["measure", "metric", "location", "sex", "age", "cause", "population_group"].includes(col)) {
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

function sortRecords(records) {
  records.sort((a, b) => {
    const keys = [
      "measure_id",
      "location_id",
      "sex_id",
      "age_id",
      "metric_id",
      "year_id",
    ];
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

function uniqueValues(records, field) {
  return Array.from(new Set(records.map((row) => row[field]))).filter(Boolean).sort();
}

function buildSummary(records, pkg) {
  return {
    rows: records.length,
    expected_rows_if_complete: pkg.expected_rows_if_complete || null,
    completion_ratio:
      pkg.expected_rows_if_complete && pkg.expected_rows_if_complete > 0
        ? records.length / pkg.expected_rows_if_complete
        : null,
    measures: uniqueValues(records, "measure_name"),
    locations: uniqueValues(records, "location_name"),
    sexes: uniqueValues(records, "sex_name"),
    ages: uniqueValues(records, "age_name"),
    years: uniqueValues(records, "year_id"),
    metrics: uniqueValues(records, "metric_name"),
  };
}

function packageLookup(spec) {
  const map = {};
  for (const pkg of spec.packages || []) {
    map[pkg.package_id] = pkg;
  }
  return map;
}

async function exportCorePackage(pkg, spec, metadata, token) {
  const maps = buildIdMaps(metadata);
  const years = yearsRange(pkg.filters.year_range[0], pkg.filters.year_range[1]);
  const locationIds = [...pkg.filters.region_ids, ...pkg.filters.country_ids];
  const locationChunks = chunkArray(locationIds, 10);
  const allRecords = [];

  for (const measureId of pkg.filters.measure_ids) {
    let measureRows = 0;
    for (let idx = 0; idx < locationChunks.length; idx += 1) {
      const locationChunk = locationChunks[idx];
      const result = await postData(
        {
          context: pkg.context || "cause",
          population_group: spec.population_group_id || 1,
          cause: pkg.filters.cause_ids,
          measure: [measureId],
          metric: pkg.filters.metric_ids,
          location: locationChunk,
          age: pkg.filters.age_ids,
          sex: pkg.filters.sex_ids,
          year: years,
          base: "single",
          version: spec.gbd_results_version || DEFAULT_VERSION,
          start_year: pkg.filters.year_range[0],
          fetch_all_years: false,
        },
        token
      );
      if (result._warning) {
        throw new Error(
          `GBD Results warning for package ${pkg.package_id}, measure ${measureId}, location chunk ${idx + 1}: ${result._warning}`
        );
      }
      const records = rowsToRecords(result.data, result.cols, maps);
      measureRows += records.length;
      allRecords.push(...records);
      console.log(
        `${pkg.package_id}: measure ${measureId}, location chunk ${idx + 1}/${locationChunks.length} -> ${records.length} rows`
      );
    }
    console.log(`${pkg.package_id}: measure ${measureId} total -> ${measureRows} rows`);
  }

  sortRecords(allRecords);
  return allRecords;
}

async function main() {
  const args = parseArgs(process.argv);
  const spec = readJson(args.spec);
  const storageStatePath =
    args.storageState ||
    path.join(path.dirname(args.spec), "gbd_results_storage_state.json");
  const pkgMap = packageLookup(spec);

  const selectedPackages =
    args.package === "all"
      ? Object.values(pkgMap)
      : [pkgMap[args.package]].filter(Boolean);
  if (!selectedPackages.length) {
    throw new Error(`No package matched selection: ${args.package}`);
  }

  const token = await ensureAccessToken(storageStatePath, args.forceLogin);
  const metadata = await fetchJson(METADATA_URL);
  const outputs = [];

  for (const pkg of selectedPackages) {
    const records = await exportCorePackage(pkg, spec, metadata, token);
    writeCsv(pkg.output_file, records, pkg.required_columns);
    const summary = buildSummary(records, pkg);
    const summaryPath = pkg.output_file.replace(/\.csv$/i, "_summary.json");
    writeJson(summaryPath, summary);
    outputs.push({
      package_id: pkg.package_id,
      output_file: pkg.output_file,
      summary_file: summaryPath,
      summary,
    });
  }

  console.log(JSON.stringify({ study_id: spec.study_id, outputs }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
