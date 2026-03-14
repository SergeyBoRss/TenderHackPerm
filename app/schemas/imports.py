from pydantic import BaseModel


class ImportResultResponse(BaseModel):
    mode: str
    cte_file: str
    contracts_file: str
    cte_rows_processed: int
    contracts_rows_processed: int
    contracts_upserted: int
    contract_items_inserted: int


class ClearImportDataResponse(BaseModel):
    status: str
