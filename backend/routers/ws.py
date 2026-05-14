from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.download_manager import register_ws, unregister_ws

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/progress/{task_id}")
async def progress_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()
    register_ws(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        unregister_ws(task_id, websocket)


@router.websocket("/ws/progress")
async def progress_all_ws(websocket: WebSocket):
    await websocket.accept()
    register_ws("__all__", websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        unregister_ws("__all__", websocket)
