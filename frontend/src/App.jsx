import React, { lazy, Suspense, useEffect, useState } from "react";

import FileUpload from "./components/FileUpload.jsx";
import MetricsGrid from "./components/MetricsGrid.jsx";
const HistogramGrid = lazy(() => import("./components/HistogramGrid.jsx"));
const CategoricalGrid = lazy(() => import("./components/CategoricalGrid.jsx"));
const MissingChart = lazy(() => import("./components/MissingChart.jsx"));
import CorrelationHeatmap from "./components/CorrelationHeatmap.jsx";
import ColumnTable from "./components/ColumnTable.jsx";
import AIAnalyst from "./components/AIAnalyst.jsx";
import DataStory from "./components/DataStory.jsx";

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

      const uploadStartedAt = performance.now();

      const meta = await uploadDataset(
        file,
        (value) => {
          console.log("Upload progress:", value);
          setProgress(value);
        }
      );

      const minimumVisualUploadMs = 900;
      const elapsedUploadMs = performance.now() - uploadStartedAt;
      const remainingVisualMs = Math.max(
        0,
        minimumVisualUploadMs - elapsedUploadMs
      );

      if (remainingVisualMs > 0) {
        console.log(
          `Fast upload detected. Keeping upload animation visible for ${Math.round(remainingVisualMs)}ms.`
        );

        await new Promise((resolve) =>
          setTimeout(resolve, remainingVisualMs)
        );
      }
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

        <div className="brand-lockup">

  <img
    className="brand-lockup-logo"
    src="/alta-scientia-logo.svg"
    alt="Alta Scientia AI"
  />

  <div className="brand-lockup-copy">

    <span className="brand-lockup-name">
      ALTA SCIENTIA AI
    </span>

    <span className="brand-lockup-tagline">
      Where Data Meets Its World
    </span>

  </div>

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

        {phase !== "ready" ? (          <div className="intro">

  <div className="hero-eyebrow">
    AI-POWERED DATA ANALYTICS
  </div>

  <h1 className="intro-title">
    Turn Large Datasets
    <br />
    Into Clear Decisions
  </h1>

  <p className="intro-sub">
    Upload your data. Ask questions in natural language.
    Alta Scientia AI profiles, analyzes, visualizes,
    and explains your data without requiring you
    to write SQL.
  </p>

  <div className="hero-capability-line">
    <span>Upload</span>
    <i>-&gt;</i>
    <span>Profile</span>
    <i>-&gt;</i>
    <span>Ask</span>
    <i>-&gt;</i>
    <span>Analyze</span>
    <i>-&gt;</i>
    <span>Visualize</span>
    <i>-&gt;</i>
    <span>Discover</span>
  </div>

  <div className="analysis-orbit">

    <div className="orbit-feature orbit-feature-left orbit-feature-top">
      <div className="orbit-feature-icon">
        DATA
      </div>

      <div>
        <span className="orbit-feature-label">
          DATA ENGINE
        </span>

        <h3>
          Large Dataset Analysis
        </h3>

        <p>
          Work with CSV, TSV, Parquet, and Excel
          datasets efficiently.
        </p>
      </div>
    </div>

    <div className="orbit-feature orbit-feature-right orbit-feature-top">
      <div className="orbit-feature-icon">
        ASK
      </div>

      <div>
        <span className="orbit-feature-label">
          NATURAL LANGUAGE
        </span>

        <h3>
          Ask Without SQL
        </h3>

        <p>
          Ask questions about your data using
          natural language.
        </p>
      </div>
    </div>

    <div className="orbit-center">

      <div className="orbit-center-line" />

      <div className="upload-section-heading">
        <span className="upload-section-label">
          START YOUR ANALYSIS
        </span>

        <span className="upload-section-text">
          Upload a dataset to begin
        </span>
      </div>

      <FileUpload
        onFile={handleFile}
        busy={phase === "busy"}
        progress={progress}
        error={error}
      />

    </div>

    <div className="orbit-feature orbit-feature-left orbit-feature-bottom">
      <div className="orbit-feature-icon">
        INSIGHT
      </div>

      <div>
        <span className="orbit-feature-label">
          QUICK INSIGHTS
        </span>

        <h3>
          Discover Key Findings
        </h3>

        <p>
          Surface important patterns, trends,
          and findings automatically.
        </p>
      </div>
    </div>

    <div className="orbit-feature orbit-feature-right orbit-feature-bottom">
      <div className="orbit-feature-icon">
        ANALYZE
      </div>

      <div>
        <span className="orbit-feature-label">
          VISUAL ANALYTICS
        </span>

        <h3>
          Explore Your Data
        </h3>

        <p>
          Analyze trends, correlations, statistics,
          and visualizations.
        </p>
      </div>
    </div>

  </div>

  <div className="landing-capability-strip">

    <span>Trends</span>
    <span>Correlations</span>
    <span>Grouped Analysis</span>
    <span>Statistics</span>
    <span>Visualizations</span>

  </div>

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
                  correlation={charts?.correlation || null}
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
                <Suspense fallback={<div className="loading-card">Loading numeric distributions...</div>}>
                <HistogramGrid
                  histograms={
                    charts.histograms || []
                  }
                />
              </Suspense>
              </section>
            )}


            {/* =================================================
                CATEGORICAL CHARTS
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-categorical-section">
                <Suspense fallback={<div className="loading-card">Loading categorical charts...</div>}>
                <CategoricalGrid
                  charts={
                    charts.categorical_charts || []
                  }
                />
              </Suspense>
              </section>
            )}


            {/* =================================================
                CORRELATION HEATMAP
            ================================================= */}

            {charts && (
              <section className="dashboard-section dashboard-correlation-section">
                <CorrelationHeatmap
                  data={
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
                <Suspense fallback={<div className="loading-card">Loading missing-data chart...</div>}>
                <MissingChart
                  missing={
                    charts.missing_chart || []
                  }
                />
              </Suspense>
              </section>
            )}

          </div>

        )}

      </main>

    </div>

  );

}













