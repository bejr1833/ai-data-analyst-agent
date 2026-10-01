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

  const uploadBase = import.meta.env.VITE_UPLOAD_API_BASE_URL || BASE;

  const uploadUrl = uploadBase + "/upload";

  console.log("========================================");
  console.log("uploadDataset() START - DIRECT RENDER XHR + MEMORY");
  console.log("File:", file?.name);
  console.log("File size:", file?.size);
  console.log("Upload URL:", uploadUrl);
  console.log("Browser origin:", window.location.origin);
  console.log("Online status:", navigator.onLine);
  console.log("========================================");

  try {
    if (onProgress) onProgress(5);
    console.log("Reading selected file into memory...");
    const buffer = await file.arrayBuffer();
    console.log("File read successfully:", buffer.byteLength, "bytes");

    const blob = new Blob([buffer], {
      type: file.type || "application/octet-stream",
    });
    console.log("Created in-memory Blob:", blob.size, blob.type);

    return await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", uploadUrl, true);
      xhr.setRequestHeader("Accept", "application/json");

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };

      xhr.onload = () => {
        console.log("XHR response received.");
        console.log("HTTP status:", xhr.status);
        console.log("HTTP status text:", xhr.statusText);

        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch (error) {
          console.error("Failed to parse XHR response:", error);
        }

        console.log("Server response:", data);

        if (xhr.status < 200 || xhr.status >= 300) {
          const message = data?.detail || xhr.statusText || "Upload failed.";
          const error = new Error(xhr.status + ": " + message);
          error.status = xhr.status;
          error.detail = message;
          console.error("DIRECT RENDER XHR HTTP FAILED:", error);
          reject(error);
          return;
        }

        if (!data || !data.dataset_id) {
          const error = new Error("Upload succeeded, but the server did not return a dataset ID.");
          console.error("DIRECT RENDER XHR INVALID RESPONSE:", error);
          reject(error);
          return;
        }

        if (onProgress) onProgress(100);
        console.log("Dataset upload completed successfully.");
        console.log("Dataset ID:", data.dataset_id);
        console.log("========================================");
        console.log("uploadDataset() SUCCESS - DIRECT RENDER XHR + MEMORY");
        console.log("========================================");
        resolve(data);
      };

      xhr.onerror = () => {
        const error = new Error("Network upload failed: XMLHttpRequest");
        console.error("DIRECT RENDER XHR MEMORY NETWORK FAILED", error);
        console.error("Upload URL:", uploadUrl);
        console.error("Browser origin:", window.location.origin);
        console.error("Online status:", navigator.onLine);
        console.error("User agent:", navigator.userAgent);
        reject(error);
      };

      xhr.ontimeout = () => reject(new Error("Upload request timed out."));
      xhr.onabort = () => reject(new Error("Upload request was aborted."));
      xhr.timeout = 120000;

      const form = new FormData();
      form.append("file", blob, file.name);

      if (onProgress) onProgress(10);
      console.log("Sending in-memory Blob via DIRECT RENDER XHR...");
      xhr.send(form);
    });
  } catch (error) {
    console.error("DIRECT RENDER XHR + MEMORY FAILED:", error);
    console.error("Message:", error?.message);
    throw error;
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

  return `${BASE}/datasets/${datasetId}/report.pdf?v=${Date.now()}`;
}



