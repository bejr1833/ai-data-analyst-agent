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

  console.log(
    "========================================"
  );

  console.log(
    "uploadDataset() START"
  );

  console.log(
    "File:",
    file?.name
  );

  console.log(
    "File size:",
    file?.size
  );

  console.log(
    "========================================"
  );


  // ----------------------------------------------------------
  // CREATE FORM DATA
  // ----------------------------------------------------------

  const form = new FormData();

  form.append(
    "file",
    file
  );


  // ----------------------------------------------------------
  // SHOW UPLOAD START
  // ----------------------------------------------------------

  if (onProgress) {
    onProgress(10);
  }


  try {

    console.log(
      "Sending fetch request to:",
      `${BASE}/upload`
    );


    // --------------------------------------------------------
    // SEND REQUEST
    // --------------------------------------------------------

    console.log("UPLOAD DEBUG - API BASE:", BASE);
    console.log("UPLOAD DEBUG - URL:", `${BASE}/upload`);
    console.log("UPLOAD DEBUG - Browser origin:", window.location.origin);
    console.log("UPLOAD DEBUG - File name:", file?.name);
    console.log("UPLOAD DEBUG - File size:", file?.size);
    console.log("UPLOAD DEBUG - File type:", file?.type);

    let response;

    try {
      response = await fetch(
        `${BASE}/upload`,
        {
          method: "POST",
          body: form,

          headers: {
            Accept: "application/json",
          },
        }
      );
    } catch (fetchError) {
      console.error("========================================");
      console.error("UPLOAD FETCH FAILED");
      console.error("Error name:", fetchError?.name);
      console.error("Error message:", fetchError?.message);
      console.error("Error stack:", fetchError?.stack);
      console.error("API BASE:", BASE);
      console.error("Upload URL:", `${BASE}/upload`);
      console.error("Browser origin:", window.location.origin);
      console.error("Online status:", navigator.onLine);
      console.error("User agent:", navigator.userAgent);
      console.error("========================================");

      const diagnosticError = new Error(
        `Network upload failed: ${fetchError?.message || "Unknown fetch error"}`
      );

      diagnosticError.name = fetchError?.name || "FetchError";
      diagnosticError.originalError = fetchError;
      diagnosticError.apiBase = BASE;
      diagnosticError.uploadUrl = `${BASE}/upload`;
      diagnosticError.browserOrigin = window.location.origin;
      diagnosticError.online = navigator.onLine;

      throw diagnosticError;
    }


    console.log(
      "Fetch response received."
    );

    console.log(
      "HTTP status:",
      response.status
    );

    console.log(
      "HTTP status text:",
      response.statusText
    );


    // --------------------------------------------------------
    // CHECK RESPONSE
    // --------------------------------------------------------

    if (!response.ok) {

      let detail =
        response.statusText ||
        "Upload failed.";


      try {

        const body =
          await response.json();

        detail =
          body.detail ||
          detail;

      } catch (_) {
        // Ignore invalid JSON.
      }


      throw new Error(
        `${response.status}: ${detail}`
      );
    }


    // --------------------------------------------------------
    // READ JSON RESPONSE
    // --------------------------------------------------------

    const data =
      await response.json();


    console.log(
      "Server response:",
      data
    );


    // --------------------------------------------------------
    // VALIDATE DATASET ID
    // --------------------------------------------------------

    if (
      !data ||
      !data.dataset_id
    ) {

      console.error(
        "Invalid server response:",
        data
      );

      throw new Error(
        "Upload succeeded, but the server did not return a dataset ID."
      );
    }


    // --------------------------------------------------------
    // UPLOAD COMPLETE
    // --------------------------------------------------------

    if (onProgress) {
      onProgress(100);
    }


    console.log(
      "Dataset upload completed successfully."
    );

    console.log(
      "Dataset ID:",
      data.dataset_id
    );


    console.log(
      "========================================"
    );

    console.log(
      "uploadDataset() SUCCESS"
    );

    console.log(
      "========================================"
    );


    return data;


  } catch (error) {

    console.error(
      "uploadDataset() FAILED:",
      error
    );

    throw error;
  }
}


/* ============================================================
   DATASET OVERVIEW
   ============================================================ */

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

