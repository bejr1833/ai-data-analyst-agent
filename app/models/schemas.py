from pydantic import BaseModel


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[str]
