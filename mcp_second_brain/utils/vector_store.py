from typing import List
from openai import OpenAI
from ..config import get_settings
_client = OpenAI(api_key=get_settings().openai_api_key)
def _upload(p: str) -> str:
    with open(p, "rb") as fp:
        return _client.files.create(file=fp, purpose="assistants").id
def create_vector_store(paths: List[str]) -> str:
    vs = _client.vector_stores.create(name="mcp-second-brain-vs")
    for p in paths:
        _client.vector_stores.files.create(vector_store_id=vs.id, file_id=_upload(p))
    return vs.id
