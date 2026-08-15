"""
FastAPI サーバー - Manga Title Extraction API
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from pipeline import extract_titles

# Load environment variables
load_dotenv()

app = FastAPI(
    title="FindMangaTitle API",
    description="フォルダ名から漫画タイトルを抽出するAPI",
    version=open("VERSION").read().strip(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FolderRequest(BaseModel):
    """リクエストモデル"""
    folder_name: str


class BatchFolderRequest(BaseModel):
    """バッチ処理用リクエストモデル"""
    folder_names: List[str]


class ExtractionResult(BaseModel):
    """結果モデル"""
    original: str
    title: Optional[str]
    confidence: float
    method: str


@app.get("/health")
def health_check():
    return {"status": "ok", "version": open("VERSION").read().strip()}


@app.post("/extract", response_model=ExtractionResult)
def extract_single(request: FolderRequest):
    """単一フォルダ名からタイトルを抽出"""
    result = extract_titles([request.folder_name])
    if not result:
        raise HTTPException(status_code=400, detail="Extract failed")
    return ExtractionResult(**result[0])


@app.post("/extract/batch", response_model=List[ExtractionResult])
def extract_batch(request: BatchFolderRequest):
    """複数フォルダ名からタイトルを抽出"""
    results = extract_titles(request.folder_names)
    if not results:
        raise HTTPException(status_code=400, detail="Extract failed")
    return [ExtractionResult(**r) for r in results]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))