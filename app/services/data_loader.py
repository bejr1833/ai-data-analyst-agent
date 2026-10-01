import os
import uuid
import re
import threading

import duckdb
import pandas as pd


# ============================================================
# DATASET MODEL
# ============================================================

class Dataset:

    def __init__(
        self,
        dataset_id,
        filename,
        con,
        columns,
        row_count,
    ):
        self.dataset_id = dataset_id
        self.filename = filename
        self.con = con
        self.columns = columns
        self.row_count = row_count

        # FastAPI can process multiple requests at the same time.
        # DuckDB connections should not be used concurrently from
        # different request handlers, so serialize access per dataset.
        self.lock = threading.RLock()


# ============================================================
# DATASET STORAGE
# ============================================================

# Persistent storage directory.
#
# Local development:
#     ./data/datasets
#
# Render:
#     Set DATASET_STORAGE_DIR to the path of the mounted
#     persistent disk, for example:
#     /var/data/datasets
#
# IMPORTANT:
# The directory must be located on persistent storage in
# production. Render's normal filesystem is ephemeral.
# ============================================================

DATASET_STORAGE_DIR = os.getenv(
    "DATASET_STORAGE_DIR",
    os.path.join(
        os.getcwd(),
        "data",
        "datasets",
    ),
)

os.makedirs(
    DATASET_STORAGE_DIR,
    exist_ok=True,
)


# In-process cache.
#
# This is only a performance cache. The actual dataset lives
# inside its persistent DuckDB database.
_DATASETS = {}


def _dataset_database_path(
    dataset_id,
):
    """
    Return the persistent DuckDB path for a dataset.
    """

    return os.path.join(
        DATASET_STORAGE_DIR,
        f"{dataset_id}.duckdb",
    )



# ============================================================
# COLUMN CLEANING
# ============================================================

def _clean_column_name(name):

    if name is None:
        return ""

    name = str(name).strip()

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    name = name.replace(
        "\n",
        " ",
    )

    name = name.replace(
        "\r",
        " ",
    )

    return name.strip()


def _make_unique_columns(columns):

    result = []
    counts = {}

    for column in columns:

        column = _clean_column_name(
            column
        )

        if not column:
            column = "Unnamed"

        if column not in counts:

            counts[column] = 0
            result.append(column)

        else:

            counts[column] += 1

            result.append(
                f"{column}_{counts[column]}"
            )

    return result


# ============================================================
# EXCEL HEADER DETECTION
# ============================================================

def _find_excel_header_row(
    raw_df,
):

    """
    Find the actual table header in a messy Excel workbook.

    The Village Health Profile contains report/title rows
    before the actual 'S No' header.
    """

    for index in range(
        min(len(raw_df), 30)
    ):

        row = raw_df.iloc[index]

        values = [
            str(value)
            .strip()
            .lower()
            for value in row.tolist()
            if pd.notna(value)
        ]

        for value in values:

            if (
                value == "s no"
                or value.startswith("s no")
            ):

                return index

    return 0


# ============================================================
# EXCEL LOADING
# ============================================================

def _read_excel_clean(
    path,
):

    """
    Read Excel files while handling:

    - title rows
    - merged headers
    - empty rows
    - empty columns
    - duplicate column names
    - numeric-looking text
    """

    raw = pd.read_excel(
        path,
        header=None,
        engine="openpyxl",
    )

    if raw.empty:

        raise ValueError(
            "The Excel file contains no data."
        )

    # --------------------------------------------------------
    # Detect actual header
    # --------------------------------------------------------

    header_row = _find_excel_header_row(
        raw
    )

    headers = raw.iloc[
        header_row
    ].tolist()

    headers = _make_unique_columns(
        headers
    )

    # --------------------------------------------------------
    # Data begins after header
    # --------------------------------------------------------

    df = raw.iloc[
        header_row + 1:
    ].copy()

    df.columns = headers

    # --------------------------------------------------------
    # Remove completely empty rows
    # --------------------------------------------------------

    df = df.dropna(
        how="all"
    )

    # --------------------------------------------------------
    # Remove completely empty columns
    # --------------------------------------------------------

    df = df.dropna(
        axis=1,
        how="all",
    )

    # --------------------------------------------------------
    # Ensure unique column names
    # --------------------------------------------------------

    df.columns = _make_unique_columns(
        df.columns.tolist()
    )

    # --------------------------------------------------------
    # Remove accidental repeated headers
    # --------------------------------------------------------

    if len(df) > 0:

        first_column = df.columns[0]

        df = df[
            df[first_column]
            .astype(str)
            .str.strip()
            .str.lower()
            != first_column.strip().lower()
        ]

    # --------------------------------------------------------
    # Strip string values
    # --------------------------------------------------------

    for column in df.columns:

        if df[column].dtype == "object":

            df[column] = df[column].apply(
                lambda value:
                    value.strip()
                    if isinstance(
                        value,
                        str,
                    )
                    else value
            )

    # --------------------------------------------------------
    # Convert mostly numeric columns
    # --------------------------------------------------------

    for column in df.columns:

        if df[column].dtype != "object":
            continue

        converted = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        non_empty = (
            df[column]
            .notna()
            .sum()
        )

        if non_empty == 0:
            continue

        numeric_count = (
            converted
            .notna()
            .sum()
        )

        if (
            numeric_count / non_empty
            >= 0.80
        ):

            df[column] = converted

    # --------------------------------------------------------
    # Reset index
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )

    if df.empty:

        raise ValueError(
            "No usable tabular data was found "
            "in the Excel file."
        )

    return df


# ============================================================
# CSV / TSV
# ============================================================

def _read_delimited(
    path,
):

    extension = os.path.splitext(
        path
    )[1].lower()

    separator = (
        "\t"
        if extension == ".tsv"
        else ","
    )

    df = pd.read_csv(
        path,
        sep=separator,
    )

    df = df.dropna(
        how="all"
    )

    df = df.dropna(
        axis=1,
        how="all",
    )

    df.columns = _make_unique_columns(
        df.columns.tolist()
    )

    return df


# ============================================================
# PARQUET
# ============================================================

def _read_parquet(
    path,
):

    df = pd.read_parquet(
        path
    )

    df = df.dropna(
        how="all"
    )

    df = df.dropna(
        axis=1,
        how="all",
    )

    df.columns = _make_unique_columns(
        df.columns.tolist()
    )

    return df


# ============================================================
# MAIN FILE READER
# ============================================================

def _read_file(
    filename,
    path,
):

    extension = os.path.splitext(
        filename
    )[1].lower()

    if extension in {
        ".xlsx",
        ".xls",
    }:

        return _read_excel_clean(
            path
        )

    if extension in {
        ".csv",
        ".tsv",
    }:

        return _read_delimited(
            path
        )

    if extension == ".parquet":

        return _read_parquet(
            path
        )

    raise ValueError(
        f"Unsupported file type: {extension}"
    )


# ============================================================
# LOAD DATASET
# ============================================================

# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset(
    filename,
    path,
):

    extension = os.path.splitext(
        filename
    )[1].lower()

    dataset_id = str(
        uuid.uuid4()
    )

    # --------------------------------------------------------
    # DuckDB connection
    # --------------------------------------------------------

    database_path = _dataset_database_path(
        dataset_id
    )

    con = duckdb.connect(
        database=database_path
    )

    # --------------------------------------------------------
    # LARGE-DATASET PATH
    #
    # CSV / TSV / Parquet are loaded directly by DuckDB.
    # This avoids creating a complete Pandas DataFrame first.
    # --------------------------------------------------------

    if extension in {
        ".csv",
        ".tsv",
    }:

        separator = (
            "\t"
            if extension == ".tsv"
            else ","
        )

        escaped_path = (
            str(path)
            .replace(
                "'",
                "''",
            )
        )

        con.execute(
            f"""
            CREATE TABLE main_table AS
            SELECT *
            FROM read_csv_auto(
                '{escaped_path}',
                header = true,
                delim = '{separator}'
            )
            """
        )

    elif extension == ".parquet":

        escaped_path = (
            str(path)
            .replace(
                "'",
                "''",
            )
        )

        con.execute(
            f"""
            CREATE TABLE main_table AS
            SELECT *
            FROM read_parquet(
                '{escaped_path}'
            )
            """
        )

    # --------------------------------------------------------
    # EXCEL PATH
    #
    # Excel continues using the existing Pandas cleaning
    # pipeline because it contains custom header detection
    # and workbook cleanup logic.
    # --------------------------------------------------------

    elif extension in {
        ".xlsx",
        ".xls",
    }:

        df = _read_excel_clean(
            path
        )

        con.register(
            "uploaded_dataframe",
            df,
        )

        con.execute(
            """
            CREATE TABLE main_table AS
            SELECT *
            FROM uploaded_dataframe
            """
        )

    else:

        con.close()

        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    # --------------------------------------------------------
    # COLUMN INFORMATION
    # --------------------------------------------------------

    columns = [
        row[0]
        for row in con.execute(
            """
            SELECT
                column_name
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
            """
        ).fetchall()
    ]

    # --------------------------------------------------------
    # ROW COUNT
    # --------------------------------------------------------

    row_count = con.execute(
        """
        SELECT COUNT(*)
        FROM main_table
        """
    ).fetchone()[0]

    # --------------------------------------------------------
    # PERSIST DATASET METADATA
    # --------------------------------------------------------

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_metadata (
            dataset_id VARCHAR,
            filename VARCHAR,
            row_count BIGINT
        )
        """
    )

    con.execute(
        "DELETE FROM dataset_metadata"
    )

    con.execute(
        """
        INSERT INTO dataset_metadata (
            dataset_id,
            filename,
            row_count
        )
        VALUES (?, ?, ?)
        """,
        [
            dataset_id,
            filename,
            row_count,
        ],
    )

    con.commit()

    # --------------------------------------------------------
    # DATASET OBJECT
    # --------------------------------------------------------

    dataset = Dataset(
        dataset_id=dataset_id,
        filename=filename,
        con=con,
        columns=columns,
        row_count=row_count,
    )

    _DATASETS[
        dataset_id
    ] = dataset

    return dataset

# ============================================================
# GET DATASET
# ============================================================

def get_dataset(
    dataset_id,
):

    # --------------------------------------------------------
    # RETURN CACHED DATASET
    # --------------------------------------------------------

    if dataset_id in _DATASETS:

        return _DATASETS[
            dataset_id
        ]

    # --------------------------------------------------------
    # REOPEN PERSISTED DATASET
    # --------------------------------------------------------

    database_path = _dataset_database_path(
        dataset_id
    )

    if not os.path.exists(
        database_path
    ):

        raise KeyError(
            dataset_id
        )

    con = duckdb.connect(
        database=database_path
    )

    # --------------------------------------------------------
    # LOAD PERSISTED METADATA
    # --------------------------------------------------------

    metadata = con.execute(
        """
        SELECT
            dataset_id,
            filename,
            row_count
        FROM dataset_metadata
        LIMIT 1
        """
    ).fetchone()

    if metadata is None:

        con.close()

        raise KeyError(
            dataset_id
        )

    persisted_dataset_id = metadata[0]
    filename = metadata[1]
    row_count = metadata[2]

    # --------------------------------------------------------
    # LOAD COLUMN INFORMATION
    # --------------------------------------------------------

    columns = [
        row[0]
        for row in con.execute(
            """
            SELECT
                column_name
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
            """
        ).fetchall()
    ]

    # --------------------------------------------------------
    # REBUILD DATASET OBJECT
    # --------------------------------------------------------

    dataset = Dataset(
        dataset_id=persisted_dataset_id,
        filename=filename,
        con=con,
        columns=columns,
        row_count=row_count,
    )

    _DATASETS[
        dataset_id
    ] = dataset

    return dataset


# ============================================================
# COLUMN TYPE HELPERS
# ============================================================

def _column_metadata(
    dataset: Dataset,
):

    return dataset.con.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()


# ============================================================
# NUMERIC COLUMNS
# ============================================================

def numeric_columns(
    dataset: Dataset,
):

    rows = _column_metadata(
        dataset
    )

    numeric_types = {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "UHUGEINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
    }

    return [
        column
        for column, dtype in rows
        if any(
            dtype.upper().startswith(
                numeric_type
            )
            for numeric_type
            in numeric_types
        )
    ]


# ============================================================
# CATEGORICAL COLUMNS
# ============================================================

def categorical_columns(
    dataset: Dataset,
):

    rows = _column_metadata(
        dataset
    )

    numeric_types = {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "UHUGEINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
    }

    categorical = []

    for column, dtype in rows:

        dtype_upper = dtype.upper()

        # Text columns are categorical candidates.
        if not any(
            dtype_upper.startswith(
                numeric_type
            )
            for numeric_type
            in numeric_types
        ):

            categorical.append(
                column
            )

    return categorical


# ============================================================
# DATETIME COLUMNS
# ============================================================

def datetime_columns(
    dataset: Dataset,
):

    rows = _column_metadata(
        dataset
    )

    datetime_types = {
        "DATE",
        "TIME",
        "TIMESTAMP",
        "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP_NS",
        "TIMESTAMP_MS",
        "TIMESTAMP_S",
    }

    datetime_result = []

    for column, dtype in rows:

        dtype_upper = dtype.upper()

        if any(
            dtype_upper.startswith(
                datetime_type
            )
            for datetime_type
            in datetime_types
        ):
            datetime_result.append(
                column
            )

    return datetime_result



