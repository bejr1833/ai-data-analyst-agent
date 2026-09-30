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

export function uploadDataset(file, onProgress) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Please select a file."));
      return;
    }

    console.log("========================================");
    console.log("uploadDataset() START - XHR");
    console.log("File:", file?.name);
    console.log("File size:", file?.size);
    console.log("API BASE:", BASE);
    console.log("Upload URL:", `${BASE}/upload`);
    console.log("Browser origin:", window.location.origin);
    console.log("Online status:", navigator.onLine);
    console.log("========================================");

    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();

    xhr.open("POST", `${BASE}/upload`, true);
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(Math.min(percent, 100));
      }
    };

    xhr.onload = () => {
      console.log("XHR response received.");
      console.log("HTTP status:", xhr.status);
      console.log("HTTP status text:", xhr.statusText);

      if (xhr.status < 200 || xhr.status >= 300) {
        let message = xhr.statusText || "Upload failed.";

        try {
          const data = JSON.parse(xhr.responseText);
          message = data?.detail || message;
        } catch {}

        reject(new Error(`${xhr.status}: ${message}`));
        return;
      }

      try {
        const data = JSON.parse(xhr.responseText);

        console.log("Server response:", data);

        if (!data || !data.dataset_id) {
          reject(
            new Error(
              "Upload succeeded, but the server did not return a dataset ID."
            )
          );
          return;
        }

        if (onProgress) {
          onProgress(100);
        }

        console.log("Dataset upload completed successfully.");
        console.log("Dataset ID:", data.dataset_id);
        console.log("========================================");
        console.log("uploadDataset() SUCCESS - XHR");
        console.log("========================================");

        resolve(data);
      } catch (error) {
        reject(
          new Error(
            `Invalid server response: ${
              error?.message || "Unable to parse response"
            }`
          )
        );
      }
    };

    xhr.onerror = () => {
      console.error("========================================");
      console.error("XHR UPLOAD FAILED");
      console.error("Error type: Network error");
      console.error("API BASE:", BASE);
      console.error("Upload URL:", `${BASE}/upload`);
      console.error("Browser origin:", window.location.origin);
      console.error("Online status:", navigator.onLine);
      console.error("User agent:", navigator.userAgent);
      console.error("========================================");

      const message = [
        "Network upload failed: XMLHttpRequest network error",
        `API: ${BASE}/upload`,
        `Origin: ${window.location.origin}`,
        `Online: ${navigator.onLine}`,
        "Error: XMLHttpRequest network error",
        `Browser: ${navigator.userAgent}`,
      ].join("\n");

      reject(new Error(message));
    };

    xhr.onabort = () => {
      reject(new Error("Upload was cancelled."));
    };

    xhr.ontimeout = () => {
      reject(new Error("Upload timed out. Please try again."));
    };

    xhr.timeout = 120000;

    xhr.send(form);
  });
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


