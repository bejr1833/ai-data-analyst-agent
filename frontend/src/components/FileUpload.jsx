import React, { useCallback, useRef, useState } from "react";

export default function FileUpload({ onFile, busy, progress, error }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);

      if (busy) return;

      const file = e.dataTransfer.files?.[0];

      if (file) {
        onFile(file);
      }
    },
    [onFile, busy]
  );

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];

    if (file) {
      onFile(file);
    }

    e.target.value = "";
  };

  const handleKeyDown = (e) => {
    if (busy) return;

    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  const openFileBrowser = (e) => {
    e.stopPropagation();

    if (!busy) {
      inputRef.current?.click();
    }
  };

  return (
    <div className="upload-wrap">
      <div
        className={`upload-zone premium-upload-zone ${
          dragOver ? "is-drag" : ""
        } ${busy ? "is-busy" : ""} ${
          error ? "has-error" : ""
        }`}
        role="button"
        tabIndex={busy ? -1 : 0}
        aria-label="Upload dataset"
        onKeyDown={handleKeyDown}
        onDragOver={(e) => {
          e.preventDefault();

          if (!busy) {
            setDragOver(true);
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();

          if (!busy) {
            setDragOver(true);
          }
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) {
            setDragOver(false);
          }
        }}
        onDrop={handleDrop}
        onClick={() => {
          if (!busy) {
            inputRef.current?.click();
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.tsv,.parquet,.xlsx,.xls"
          hidden
          disabled={busy}
          onChange={handleFileChange}
        />

        {!busy ? (
          <>
            <div className="upload-visual">
              <div className="upload-orbit upload-orbit-one" />
              <div className="upload-orbit upload-orbit-two" />

              <div className="upload-icon-shell">
                <svg
                  className="upload-svg"
                  viewBox="0 0 64 64"
                  aria-hidden="true"
                >
                  <path
                    d="M32 42V13"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />

                  <path
                    d="M21 24L32 13L43 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  <path
                    d="M15 42V49C15 51.2 16.8 53 19 53H45C47.2 53 49 51.2 49 49V42"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
            </div>

            <div className="upload-eyebrow">
              DATA INTAKE
            </div>

            <h3 className="upload-title">
              Drop your dataset here
            </h3>

            <div className="upload-browse-row">
              <span>or</span>

              <button
                type="button"
                className="upload-browse-button"
                onClick={openFileBrowser}
              >
                Browse files
              </button>
            </div>

            <div className="upload-format-list">
              <span className="upload-format">CSV</span>
              <span className="upload-format">XLSX</span>
              <span className="upload-format">TSV</span>
              <span className="upload-format">PARQUET</span>
            </div>

            <div className="upload-support">
              <span className="upload-status-dot" />
              Large files supported
              <span className="upload-divider" />
              Fast profiling
              <span className="upload-divider" />
              No SQL required
            </div>
          </>
        ) : (
          <>
            <div className="upload-visual upload-processing">
              <div className="upload-orbit upload-orbit-one" />
              <div className="upload-orbit upload-orbit-two" />

              <div className="upload-icon-shell">
                <svg
                  className="upload-svg"
                  viewBox="0 0 64 64"
                  aria-hidden="true"
                >
                  <path
                    d="M32 42V13"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />

                  <path
                    d="M21 24L32 13L43 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  <path
                    d="M15 42V49C15 51.2 16.8 53 19 53H45C47.2 53 49 51.2 49 49V42"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
            </div>

            <div className="upload-eyebrow">
              {progress >= 100 ? "ANALYZING DATA" : "DATA UPLOAD"}
            </div>

            <h3 className="upload-title">
              {progress >= 100
                ? "Processing your dataset"
                : "Uploading your dataset"}
            </h3>

            <div className="progress-track premium-progress">
              <div
                className="progress-fill"
                style={{
                  width: `${Math.min(progress, 100)}%`,
                }}
              />
            </div>

            <div className="upload-progress-meta">
              <span>
                {progress >= 100
                  ? "Upload complete"
                  : "Preparing your data"}
              </span>

              <strong>
                {Math.min(progress, 100)}%
              </strong>
            </div>

            <p className="upload-sub">
              {progress >= 100
                ? "Your dataset is ready for analysis."
                : "Please keep this window open while your dataset is uploaded."}
            </p>
          </>
        )}
      </div>

      {error && (
        <div className="upload-error premium-upload-error" role="alert">
          <span className="upload-error-icon">!</span>

          <div>
            <strong>Upload failed</strong>
            <p>{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
