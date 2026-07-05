"""HF Docker Space 진입점 (읽기 전용).

- GET /api/healthz : 헬스체크
- GET /api/status  : data_status.json 반환
- /                : Gradio UI 마운트
refresh 엔드포인트는 없다. 데이터 갱신은 GitHub Actions가 담당한다.
"""
from __future__ import annotations

import gradio as gr
from fastapi import FastAPI

from riskradar import cache_store
from riskradar.ui import build_app

app = FastAPI(title="RiskRadar")


@app.get("/api/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/status")
def status():
    try:
        return cache_store.get_store().load_status()
    except Exception as e:  # noqa: BLE001
        return {"status": "no_cache", "error": str(e)}


app = gr.mount_gradio_app(app, build_app(), path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
