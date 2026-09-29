import os
import tempfile

from contextlib import contextmanager

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import MAX_UPLOAD_SIZE_BYTES
from app.models.schemas import UploadResponse

from app.services import (
    data_loader,
    profiler,
    report_generator,
)

from app.services.orchestrator import AnalystOrchestrator


app = FastAPI(
    title="AI Data Analyst Agent",
    version="1.0.0",
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "AI Data Analyst API is running",
        "docs": "/docs",
        "health": "/health",
    }


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://ai-data-analyst-agent-3eb0zixx2-insight-forge-ai.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ALLOWED FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".parquet",
    ".xlsx",
    ".xls",
}


# ============================================================
# REQUEST MODELS
# ============================================================

class QuestionRequest(BaseModel):
    question: str
    conversation_history: list[dict] = Field(default_factory=list)


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# ============================================================
# UPLOAD DATASET
# ============================================================

@app.post(
    "/api/upload",
    response_model=UploadResponse,
)
async def upload_dataset(
    file: UploadFile = File(...),
):
    ext = os.path.splitext(
        file.filename or ""
    )[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            (
                f"Unsupported file type '{ext}'. "
                f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    # Stream the upload to disk in chunks.
    # This prevents large files from being held
    # completely in memory during upload.

    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=ext
    )

    total = 0

    try:
        with os.fdopen(
            tmp_fd,
            "wb",
        ) as out:

            while chunk := await file.read(
                8 * 1024 * 1024
            ):

                total += len(chunk)

                if total > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        413,
                        "File exceeds maximum allowed upload size.",
                    )

                out.write(chunk)

    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    try:
        dataset = data_loader.load_dataset(
            file.filename,
            tmp_path,
        )

    except Exception as e:
        raise HTTPException(
            400,
            f"Failed to parse file: {e}",
        )

    finally:
        # The dataset has already been loaded into DuckDB,
        # so the temporary upload file is no longer required.
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return UploadResponse(
        dataset_id=dataset.dataset_id,
        filename=dataset.filename,
        row_count=dataset.row_count,
        column_count=len(dataset.columns),
        columns=dataset.columns,
    )


# ============================================================
# DATASET LOOKUP
# ============================================================

def _get_dataset_or_404(
    dataset_id: str,
):
    try:
        return data_loader.get_dataset(
            dataset_id
        )

    except KeyError:
        raise HTTPException(
            404,
            (
                "Dataset not found. "
                "It may have expired - please re-upload."
                "please re-upload."
            ),
        )


# ============================================================
# DATASET LOCK
# ============================================================
#
# Each Dataset now owns a threading.RLock() in data_loader.py.
# DuckDB connections are shared by the profiler and AI agent,
# so requests using the same dataset must not execute against
# the same connection concurrently.
#
# RLock is used so nested service calls can safely acquire the
# same dataset lock without deadlocking.
# ============================================================

@contextmanager
def dataset_lock(dataset):
    with dataset.lock:
        yield dataset


# ============================================================
# OVERVIEW
# ============================================================

@app.get(
    "/api/datasets/{dataset_id}/overview"
)
def get_overview(
    dataset_id: str,
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    with dataset_lock(dataset):
        return profiler.overview_metrics(
            dataset
        )


# ============================================================
# COLUMN PROFILES
# ============================================================

@app.get(
    "/api/datasets/{dataset_id}/columns"
)
def get_columns(
    dataset_id: str,
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    with dataset_lock(dataset):
        return {
            "columns": profiler.column_profiles(
                dataset
            )
        }


# ============================================================
# CHARTS
# ============================================================

@app.get(
    "/api/datasets/{dataset_id}/charts"
)
def get_charts(
    dataset_id: str,
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    with dataset_lock(dataset):

        num_cols = data_loader.numeric_columns(
            dataset
        )

        cat_cols = (
            profiler.categorical_summary_columns(
                dataset
            )
        )

        return {
            "histograms": [
                profiler.histogram(
                    dataset,
                    c,
                )
                for c in num_cols[:12]
            ],

            "categorical_charts": [
                profiler.top_categories(
                    dataset,
                    c,
                )
                for c in cat_cols[:8]
            ],

            "missing_chart":
                profiler.missing_values_chart(
                    dataset
                ),

            "correlation": (
                profiler.correlation_matrix(
                    dataset
                )
                if len(num_cols) >= 2
                else None
            ),
        }


# ============================================================
# SAMPLE DATA
# ============================================================

@app.get(
    "/api/datasets/{dataset_id}/sample"
)
def get_sample(
    dataset_id: str,
    limit: int = Query(
        50,
        ge=1,
        le=500,
    ),
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    with dataset_lock(dataset):
        return {
            "rows": profiler.sample_rows(
                dataset,
                limit,
            )
        }


# ============================================================
# AI DATA ANALYST AGENT
# ============================================================

@app.post(
    "/api/datasets/{dataset_id}/ask"
)
def ask_dataset(
    dataset_id: str,
    request: QuestionRequest,
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    # --------------------------------------------------------
    # Validate question
    # --------------------------------------------------------

    question = request.question.strip()

    if not question:
        raise HTTPException(
            400,
            "Question cannot be empty.",
        )

    # --------------------------------------------------------
    # Agentic analysis
    #
    # The entire agent execution is serialized per dataset
    # because local analytical tools use the dataset's shared
    # DuckDB connection.
    # --------------------------------------------------------

    try:
        with dataset_lock(dataset):

            orchestrator = AnalystOrchestrator(
                dataset
            )

            result = orchestrator.analyze(
                question,
                request.conversation_history,
            )

        return result

    except HTTPException:
        raise

    except Exception as e:
        print(
            "AI Analyst Agent Error:",
            repr(e),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"AI Analyst Agent error: {str(e)}"
            ),
        )


# ============================================================
# PDF REPORT
# ============================================================

@app.get(
    "/api/datasets/{dataset_id}/report.pdf"
)
def download_report(
    dataset_id: str,
):
    dataset = _get_dataset_or_404(
        dataset_id
    )

    with dataset_lock(dataset):
        pdf_bytes = (
            report_generator.generate_pdf_report(
                dataset
            )
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; '
                f'filename="{dataset.filename}_report.pdf"'
            )
        }
    )






