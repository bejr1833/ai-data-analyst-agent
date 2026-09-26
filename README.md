# Analyst Bench — AI Data Analyst Agent

An automated exploratory-data-analysis agent: upload a dataset, get row/column
metrics, distribution charts, categorical breakdowns, a correlation heatmap,
a missing-data report, and a downloadable PDF summary — all computed without
loading the full file into memory, so it scales to large datasets.

## Architecture

```
ai-data-analyst-agent/
├── backend/                 FastAPI service
│   └── app/
│       ├── main.py          API routes (upload, overview, columns, charts, report)
│       ├── config.py        Thresholds (sampling, cardinality, upload size)
│       └── services/
│           ├── data_loader.py      Ingests files, registers them with DuckDB
│           ├── profiler.py         SQL aggregate stats + chart-ready data
│           └── report_generator.py PDF report (matplotlib)
├── frontend/                 React (Vite) dashboard
│   └── src/
│       ├── App.jsx           Upload flow + dashboard layout
│       ├── api/client.js     Calls to the backend API
│       └── components/       Metrics grid, histograms, category charts,
│                              correlation heatmap, missing-data chart, table
└── docker-compose.yml
```

### How large datasets are handled

Uploaded CSV/TSV/Parquet files are **not** loaded into a pandas DataFrame.
Instead, DuckDB opens the file on disk and every statistic (row counts,
means, medians, quartiles, standard deviations, correlations, histograms,
missing-value counts) is computed with SQL aggregate queries that stream
through the file rather than materializing it in memory. Only small,
already-aggregated results (a few numbers or a capped list of rows) ever
reach Python. Excel files are the one exception — the `.xlsx`/`.xls` format
has no out-of-core reader, so they're loaded with pandas, but the format
itself caps out around ~1,048,576 rows, keeping memory use bounded.

## Run it locally

**Option A — Docker Compose (recommended, one command):**

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (docs at http://localhost:8000/docs)

**Option B — run each side manually:**

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173.

## Deploying

Each half of the app is a standard containerized service, so you can deploy
them independently on most PaaS platforms (Render, Railway, Fly.io, an EC2
box, etc.):

1. **Backend** — deploy the `backend/` folder's Docker image; expose port
   `8000`. Set `STORAGE_DIR` to a persistent volume/disk if you want uploaded
   datasets to survive restarts.
2. **Frontend** — either:
   - deploy `frontend/` as a static build (`npm run build` → serve `dist/`
     from any static host), pointing it at the backend's public URL, or
   - deploy the provided `frontend/Dockerfile` as-is behind a reverse proxy.
3. Update CORS in `backend/app/main.py` (`allow_origins`) to your frontend's
   deployed origin instead of `"*"` before going to production.

## API summary

| Method | Path                                   | Purpose                          |
|--------|-----------------------------------------|-----------------------------------|
| POST   | `/api/upload`                          | Upload a dataset, get a dataset_id |
| GET    | `/api/datasets/{id}/overview`          | Row/column counts, missing %, duplicates |
| GET    | `/api/datasets/{id}/columns`           | Per-column type, missing %, stats |
| GET    | `/api/datasets/{id}/charts`            | Histograms, categorical bars, missing chart, correlation matrix |
| GET    | `/api/datasets/{id}/sample?limit=50`   | Preview rows |
| GET    | `/api/datasets/{id}/report.pdf`        | Full PDF EDA report              |

## Notes / next steps

- Datasets currently live in an in-memory registry per backend process —
  restarting the backend clears loaded datasets (the files themselves stay
  in `backend/storage/`, so this is easy to extend to reload-on-demand).
- Supported formats: CSV, TSV, Parquet, XLSX, XLS.
- Configurable via env vars in `backend/app/config.py`: sampling thresholds,
  categorical cardinality cutoff, max upload size.
