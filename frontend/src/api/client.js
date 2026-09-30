const BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";


/* ============================================================
   GENERIC RESPONSE HANDLER
   ============================================================ */

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText || "Request failed.";

    try {
      const body = await res.json();

      detail =
        body.detail ||
        detail;
    } catch (_) {
      // Ignore JSON parsing errors.
    }

    const error = new Error(detail);
    error.status = res.status;
    error.detail = detail;

    throw error;
  }

  return res.json();
}


/* ============================================================
   UPLOAD DATASET
   ============================================================ */

export async function uploadDataset(file, onProgress) {
  if (!file) {
    throw new Error("Please select a file.");
  }

  console.log("========================================");
  console.log("uploadDataset() START - FETCH");
  console.log("File:", file?.name);
  console.log("File size:", file?.size);
  console.log("API BASE:", BASE);
  console.log("Upload URL:", `${BASE}/upload`);
  console.log("Browser origin:", window.location.origin);
  console.log("Online status:", navigator.onLine);
  console.log("========================================");

  const form = new FormData();
  form.append("file", file);

  try {
    if (onProgress) {
      onProgress(10);
    }

    const response = await fetch(`${BASE}/upload`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      body: form,
    });

    console.log("FETCH response received.");
    console.log("HTTP status:", response.status);
    console.log("HTTP status text:", response.statusText);

    let data;

    try {
      data = await response.json();
    } catch (error) {
      throw new Error(
        `Invalid server response: ${
          error?.message || "Unable to parse response"
        }`
      );
    }

    console.log("Server response:", data);

    if (!response.ok) {
      const message =
        data?.detail ||
        response.statusText ||
        "Upload failed.";

      throw new Error(`${response.status}: ${message}`);
    }

    if (!data || !data.dataset_id) {
      throw new Error(
        "Upload succeeded, but the server did not return a dataset ID."
      );
    }

    if (onProgress) {
      onProgress(100);
    }

    console.log("Dataset upload completed successfully.");
    console.log("Dataset ID:", data.dataset_id);
    console.log("========================================");
    console.log("uploadDataset() SUCCESS - FETCH");
    console.log("========================================");

    return data;
  } catch (error) {
    console.error("========================================");
    console.error("FETCH UPLOAD FAILED");
    console.error("Error:", error);
    console.error("API BASE:", BASE);
    console.error("Upload URL:", `${BASE}/upload`);
    console.error("Browser origin:", window.location.origin);
    console.error("Online status:", navigator.onLine);
    console.error("User agent:", navigator.userAgent);
    console.error("========================================");

    throw error instanceof Error
      ? error
      : new Error("Network upload failed.");
  }
}
export async function getOverview(
  datasetId
) {

  console.log(
    "Loading overview:",
    datasetId
  );


  const response =
    await fetch(
      `${BASE}/datasets/${datasetId}/overview`
    );


  return handle(response);
}


/* ============================================================
   COLUMN PROFILES
   ============================================================ */

export async function getColumns(
  datasetId
) {

  console.log(
    "Loading columns:",
    datasetId
  );


  const response =
    await fetch(
      `${BASE}/datasets/${datasetId}/columns`
    );


  return handle(response);
}


/* ============================================================
   CHARTS
   ============================================================ */

export async function getCharts(
  datasetId
) {

  console.log(
    "Loading charts:",
    datasetId
  );


  const response =
    await fetch(
      `${BASE}/datasets/${datasetId}/charts`
    );


  return handle(response);
}


/* ============================================================
   SAMPLE DATA
   ============================================================ */

export async function getSample(
  datasetId,
  limit = 20
) {

  const response =
    await fetch(
      `${BASE}/datasets/${datasetId}/sample?limit=${limit}`
    );


  return handle(response);
}


/* ============================================================
   AI DATA ANALYST
   ============================================================ */

export async function askDataset(
  datasetId,
  question,
  conversationHistory = []
) {

  const trimmedQuestion =
    question.trim();


  if (!trimmedQuestion) {

    throw new Error(
      "Please enter a question."
    );
  }


  console.log(
    "Sending AI analyst question:",
    trimmedQuestion
  );


  const response =
    await fetch(
      `${BASE}/datasets/${datasetId}/ask`,
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },

        body: JSON.stringify({
          question:
            trimmedQuestion,

          conversation_history:
            conversationHistory,
        }),
      }
    );


  return handle(response);
}


/* ============================================================
   PDF REPORT
   ============================================================ */

export function reportUrl(
  datasetId
) {

  return `${BASE}/datasets/${datasetId}/report.pdf`;
}

