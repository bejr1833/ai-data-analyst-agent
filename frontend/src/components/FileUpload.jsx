import { useCallback, useRef, useState } from "react";

export default function FileUpload({ onFile, busy, progress, error }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);

      const file = e.dataTransfer.files?.[0];

      if (file) {
        onFile(file);
      }
    },
    [onFile]
  );

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];

    if (file) {
      onFile(file);
    }

    // Allows selecting the same file again
    e.target.value = "";
  };

  return (
    <div className="upload-wrap">
      <div
        className={`upload-zone ${
          dragOver ? "is-drag" : ""
        } ${busy ? "is-busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) {
            setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
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
            <div className="upload-mark">＋</div>

            <p className="upload-title">
              Drop a dataset here, or click to browse
            </p>

            <p className="upload-sub">
              CSV, TSV, Parquet, or Excel — large files are
              streamed and profiled without loading fully into memory
            </p>
          </>
        ) : (
          <>
            <div className="upload-mark">
              {progress >= 100 ? "⚙" : "↑"}
            </div>

            <p className="upload-title">
              {progress >= 100
                ? "Processing dataset…"
                : "Uploading dataset…"}
            </p>

            <div className="progress-track">
              <div
                className="progress-fill"
                style={{
                  width: `${Math.min(progress, 100)}%`,
                }}
              />
            </div>

            <p className="upload-sub">
              {progress >= 100
                ? "Upload complete — analyzing your dataset…"
                : `${progress}% uploaded`}
            </p>
          </>
        )}
      </div>

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}