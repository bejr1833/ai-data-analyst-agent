import React, { useEffect, useState } from "react";

import FileUpload from "./components/FileUpload.jsx";
import MetricsGrid from "./components/MetricsGrid.jsx";
import HistogramGrid from "./components/HistogramGrid.jsx";
import CategoricalGrid from "./components/CategoricalGrid.jsx";
import MissingChart from "./components/MissingChart.jsx";
import CorrelationHeatmap from "./components/CorrelationHeatmap.jsx";
import ColumnTable from "./components/ColumnTable.jsx";
import AIAnalyst from "./components/AIAnalyst.jsx";

import "./App.css";

import {
  uploadDataset,
  getOverview,
  getColumns,
  getCharts,
  reportUrl,
} from "./api/client.js";


export default function App() {

  // ============================================================
  // APPLICATION STATE
  // ============================================================

  const [phase, setPhase] = useState("upload");

  const [progress, setProgress] = useState(0);

  const [error, setError] = useState(null);

  const [dataset, setDataset] = useState(null);

  const [overview, setOverview] = useState(null);

  const [columns, setColumns] = useState(null);

  const [charts, setCharts] = useState(null);

  const [columnsLoading, setColumnsLoading] = useState(false);

  const [chartsLoading, setChartsLoading] = useState(false);

  // ============================================================
  // DATASET PERSISTENCE
  // ============================================================

  const DATASET_STORAGE_KEY = "ai-data-analyst-active-dataset";

  async function loadDatasetData(datasetMeta) {
    if (!datasetMeta?.dataset_id) {
      return;
    }

    const datasetId = datasetMeta.dataset_id;

    setDataset(datasetMeta);
    setProgress(100);
    setError(null);
    setPhase("ready");

    setOverview(null);
    setColumns(null);
    setCharts(null);

    setColumnsLoading(true);
    setChartsLoading(true);

    console.log("Restoring dataset:", datasetId);

    getOverview(datasetId)
      .then((ov) => {
        console.log("Restored overview:", ov);
        setOverview(ov);
      })
      .catch((e) => {
        console.error("Restored overview error:", e);
        setOverview(null);
      });

    getColumns(datasetId)
      .then((cols) => {
        console.log("Restored columns:", cols);
        setColumns(cols?.columns || []);
      })
      .catch((e) => {
        console.error("Restored columns error:", e);
        setColumns([]);
      })
      .finally(() => {
        setColumnsLoading(false);
      });

    getCharts(datasetId)
      .then((ch) => {
        console.log("Restored charts:", ch);
        setCharts(ch || {});
      })
      .catch((e) => {
        console.error("Restored charts error:", e);
        setCharts({});
      })
      .finally(() => {
        setChartsLoading(false);
      });
  }

  // Restore the last uploaded dataset after a browser refresh.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(
        DATASET_STORAGE_KEY
      );

      if (!saved) {
        return;
      }

      const savedDataset = JSON.parse(saved);

      if (!savedDataset?.dataset_id) {
        localStorage.removeItem(
          DATASET_STORAGE_KEY
        );
        return;
      }

      loadDatasetData(savedDataset);
    } catch (e) {
      console.error(
        "Unable to restore saved dataset:",
        e
      );

      localStorage.removeItem(
        DATASET_STORAGE_KEY
      );
    }
  }, []);


  // ============================================================
  // FILE UPLOAD
  // ============================================================

  async function handleFile(file) {

    console.log("========================================");
    console.log("STARTING DATASET UPLOAD");
    console.log("File:", file?.name);
    console.log("Size:", file?.size);
    console.log("========================================");

    setError(null);

    setPhase("busy");

    setProgress(0);

    setDataset(null);
    setOverview(null);
    setColumns(null);
    setCharts(null);

    setColumnsLoading(false);
    setChartsLoading(false);


    try {

      // ========================================================
      // 1. UPLOAD DATASET
      // ========================================================

      console.log("1. Uploading dataset...");

      const meta = await uploadDataset(
        file,
        (value) => {
          console.log("Upload progress:", value);
          setProgress(value);
        }
      );

      console.log("2. Upload response received:");
      console.log(meta);


      // ========================================================
      // 2. VALIDATE SERVER RESPONSE
      // ========================================================

      if (!meta) {
        throw new Error(
          "The server returned an empty response."
        );
      }

      if (!meta.dataset_id) {
        console.error(
          "Server response does not contain dataset_id:",
          meta
        );

        throw new Error(
          "Upload succeeded, but the server did not return a dataset ID."
        );
      }


      console.log(
        "3. Dataset ID:",
        meta.dataset_id
      );

      // Persist the active dataset so browser refresh
      // restores the dashboard automatically.
      localStorage.setItem(
        DATASET_STORAGE_KEY,
        JSON.stringify(meta)
      );


      // ========================================================
      // 3. STORE DATASET
      // ========================================================

      setDataset(meta);

      setProgress(100);


      // ========================================================
      // 4. SHOW DASHBOARD IMMEDIATELY
      // ========================================================

      console.log(
        "4. Switching application to READY state..."
      );

      setPhase("ready");


      // ========================================================
      // 5. LOAD OVERVIEW IN BACKGROUND
      // ========================================================

      console.log(
        "5. Loading dataset overview..."
      );

      getOverview(meta.dataset_id)
        .then((ov) => {

          console.log(
            "Overview loaded successfully:",
            ov
          );

          setOverview(ov);

        })
        .catch((e) => {

          console.error(
            "Overview loading error:",
            e
          );

          // Do NOT change phase.
          // Dashboard should remain visible.

          setOverview(null);

        });


      // ========================================================
      // 6. LOAD COLUMNS IN BACKGROUND
      // ========================================================

      console.log(
        "6. Loading column information..."
      );

      setColumnsLoading(true);

      getColumns(meta.dataset_id)
        .then((cols) => {

          console.log(
            "Columns loaded successfully:",
            cols
          );

          setColumns(
            cols?.columns || []
          );

        })
        .catch((e) => {

          console.error(
            "Column loading error:",
            e
          );

          setColumns([]);

        })
        .finally(() => {

          setColumnsLoading(false);

        });


      // ========================================================
      // 7. LOAD CHARTS IN BACKGROUND
      // ========================================================

      console.log(
        "7. Loading charts..."
      );

      setChartsLoading(true);

      getCharts(meta.dataset_id)
        .then((ch) => {

          console.log(
            "Charts loaded successfully:",
            ch
          );

          setCharts(ch || {});

        })
        .catch((e) => {

          console.error(
            "Chart loading error:",
            e
          );

          setCharts({});

        })
        .finally(() => {

          setChartsLoading(false);

        });


      // ========================================================
      // UPLOAD FLOW COMPLETE
      // ========================================================

      console.log(
        "========================================"
      );

      console.log(
        "DATASET READY"
      );

      console.log(
        "Dashboard should now be visible."
      );

      console.log(
        "========================================"
      );


    } catch (e) {

      console.error(
        "DATASET UPLOAD ERROR:",
        e
      );

      setError(
        e?.message ||
        "Something went wrong while processing that file."
      );

      setPhase("upload");

    }

  }


  // ============================================================
  // RESET DATASET
  // ============================================================

  function reset() {

    console.log(
      "Resetting dataset..."
    );

    setPhase("upload");

    setDataset(null);

    setOverview(null);

    setColumns(null);

    setCharts(null);

    setError(null);

    setProgress(0);

    setColumnsLoading(false);

    setChartsLoading(false);

    try {
      localStorage.removeItem(
        DATASET_STORAGE_KEY
      );
    } catch {
      // Ignore localStorage errors.
    }

  }


  // ============================================================
  // RENDER
  // ============================================================

  return (

    <div className="app-shell">

      {/* ======================================================
          HEADER
      ======================================================= */}

      <header className="app-header">

        <div className="brand">

          <span className="brand-mark">
            ▤
          </span>

          <span className="brand-name">
            Analyst Bench
          </span>

        </div>


        {/* ====================================================
            HEADER ACTIONS
        ===================================================== */}

        {phase === "ready" && dataset && (

          <div className="header-actions">

            <span className="header-filename">
              {dataset.filename}
            </span>


            <a
              className="btn-primary"
              href={reportUrl(dataset.dataset_id)}
              target="_blank"
              rel="noreferrer"
            >
              Download PDF report
            </a>


            <button
              className="btn-secondary"
              onClick={reset}
            >
              New dataset
            </button>

          </div>

        )}

      </header>


      {/* ======================================================
          MAIN CONTENT
      ======================================================= */}

      <main className="app-main">

        {/* ====================================================
            UPLOAD SCREEN
        ===================================================== */}

        {phase !== "ready" ? (

          <div className="intro">

            <h1 className="intro-title">

              Point it at a dataset.

              <br />

              Get the shape of it back.

            </h1>


            <p className="intro-sub">

              Upload a CSV, TSV, Parquet,
              or Excel file. Aggregate
              statistics run directly
              against the file on disk,
              so multi-million-row datasets
              profile without loading fully
              into memory.

            </p>


            <FileUpload
              onFile={handleFile}
              busy={phase === "busy"}
              progress={progress}
              error={error}
            />

          </div>

        ) : (

          /* ==================================================
             DASHBOARD
          =================================================== */

          <div className="dashboard">


            {/* =================================================
                AI DATA ANALYST
            ================================================= */}

            {dataset && (
              <section className="dashboard-section dashboard-ai-section">
                <AIAnalyst
                  datasetId={dataset.dataset_id}
                />
              </section>
            )}


            {/* =================================================
                DATASET METRICS
            ================================================= */}

            {overview && (
              <section className="dashboard-section dashboard-overview-heading-section">
                <div className="dataset-overview-heading">
                  <span>DATASET OVERVIEW</span>
                  <h2>Dataset profile</h2>
                  <p>Explore the structure, quality, and visual patterns in your uploaded data.</p>
                </div>
              </section>
            )}

            {overview && (
              <section className="dashboard-section dashboard-metrics-section">
                <MetricsGrid
                  overview={overview}
                />
              </section>
            )}


            {/* =================================================
                OVERVIEW LOADING
            ================================================= */}

            {!overview && (
              <section className="dashboard-section dashboard-loading-section">
                <div className="loading-card">
                  Loading dataset overview...
                </div>
              </section>
            )}


            {/* =================================================
                COLUMN INFORMATION
            ================================================= */}

            {columnsLoading && !columns && (
              <section className="dashboard-section dashboard-loading-section">
                <div className="loading-card">
                  Loading column information...
                </div>
              </section>
            )}


            {columns && (
              <section className="dashboard-section dashboard-columns-section">
                <ColumnTable
                  columns={columns}
                />
              </section>
            )}


            {/* =================================================
                CHART LOADING
            ================================================= */}

            {chartsLoading && !charts && (
              <section className="dashboard-section dashboard-loading-section">
                <div className="loading-card">
                  Loading visualizations...
                </div>
              </section>
            )}


            {/* =================================================
                NUMERIC HISTOGRAMS
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-histograms-section">
                <HistogramGrid
                  histograms={
                    charts.histograms || []
                  }
                />
              </section>
            )}


            {/* =================================================
                CATEGORICAL CHARTS
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-categorical-section">
                <CategoricalGrid
                  charts={
                    charts.categorical_charts || []
                  }
                />
              </section>
            )}


            {/* =================================================
                CORRELATION HEATMAP
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-correlation-section">
                <CorrelationHeatmap
                  correlation={
                    charts.correlation || []
                  }
                />
              </section>
            )}


            {/* =================================================
                MISSING VALUES
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-missing-section">
                <MissingChart
                  missing={
                    charts.missing_chart || []
                  }
                />
              </section>
            )}

          </div>

        )}

      </main>

    </div>

  );

}

