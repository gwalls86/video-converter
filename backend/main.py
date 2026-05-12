"""
Video Converter — FastAPI Backend
Conversor de Video e Imagen usando FFmpeg.

Uso:
    pip install fastapi uvicorn
    python main.py

Luego abre frontend/index.html en tu navegador.
Puerto: 8002
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import signal
import tkinter as tk
from tkinter import filedialog
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = "video_converter_config.json"

if sys.platform == "win32":
    DEFAULT_FFMPEG  = str(Path(__file__).parent.parent / "0-FFmpeg" / "bin" / "ffmpeg.exe")
    DEFAULT_FFPROBE = str(Path(__file__).parent.parent / "0-FFmpeg" / "bin" / "ffprobe.exe")
    SUBPROCESS_FLAGS = 0x08000000
else:
    DEFAULT_FFMPEG  = "ffmpeg"
    DEFAULT_FFPROBE = "ffprobe"
    SUBPROCESS_FLAGS = 0

FORMATS = {
    "mp4": {
        "label":       "MP4 (H.264)",
        "ext":         "mp4",
        "vcodec":      "libx264",
        "acodec":      "aac",
        "crf_min":     0,
        "crf_max":     51,
        "crf_default": 23,
        "crf_info":    "H.264 recomienda CRF entre 18 y 28. Valor estándar: 23.",
        "is_image":    False,
        "extra":       "-profile:v high -tune film -pix_fmt yuv420p",
        "input_exts":  [".mov", ".mp4", ".avi", ".mkv", ".webm"],
    },
    "webm": {
        "label":       "WEBM (VP9)",
        "ext":         "webm",
        "vcodec":      "libvpx-vp9",
        "acodec":      "libopus",
        "crf_min":     0,
        "crf_max":     63,
        "crf_default": 30,
        "crf_info":    "VP9 permite CRF entre 0 (sin pérdida) y 63. Recomendado: 24–33.",
        "is_image":    False,
        "extra":       "-b:v 0 -b:a 128k -row-mt 1 -deadline good -cpu-used 2",
        "input_exts":  [".mov", ".mp4", ".avi", ".mkv", ".webm"],
    },
    "av1": {
        "label":       "AV1 Video",
        "ext":         "webm",
        "vcodec":      "libaom-av1",
        "acodec":      "libopus",
        "crf_min":     0,
        "crf_max":     63,
        "crf_default": 30,
        "crf_info":    "AV1 usa CRF entre 0 y 63. Recomendado: 25–35.",
        "is_image":    False,
        "extra":       "-b:v 0 -row-mt 1 -deadline good",
        "input_exts":  [".mov", ".mp4", ".avi", ".mkv", ".webm"],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VideoConverterConfig:
    input_dir:    str   = ""
    output_dir:   str   = ""
    ffmpeg_path:  str   = DEFAULT_FFMPEG
    ffprobe_path: str   = DEFAULT_FFPROBE
    format_id:    str   = "mp4"
    crf:          int   = 23
    remove_audio: bool  = False
    resize_mode:  str   = "none"   # "none" | "width" | "both"
    resize_width: int   = 1280
    resize_height: int  = 720
    av1_cpu_speed: int  = 4
    overwrite_all: bool = False
    open_output:   bool = False


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC
# ─────────────────────────────────────────────────────────────────────────────

class ConvertRequest(BaseModel):
    input_dir:    str
    output_dir:   str
    ffmpeg_path:  str = DEFAULT_FFMPEG
    ffprobe_path: str = DEFAULT_FFPROBE
    format_id:    str = "mp4"
    crf:          int = 23
    remove_audio: bool = False
    resize_mode:  str  = "none"
    resize_width: int  = 1280
    resize_height: int = 720
    av1_cpu_speed: int = 4
    overwrite_all: bool = False
    open_output:   bool = False


class ConfigSaveRequest(BaseModel):
    config: dict


# ─────────────────────────────────────────────────────────────────────────────
# WORKER BRIDGE
# ─────────────────────────────────────────────────────────────────────────────

class OperationCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self.active_process: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        self._cancelled.set()
        proc = self.active_process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                for _ in range(10):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check(self) -> None:
        if self._cancelled.is_set():
            raise OperationCancelled()


class WorkerBridge:
    def __init__(self) -> None:
        self.q: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self.cancel_token = CancellationToken()

    def log(self, message: str, level: str = "INFO") -> None:
        self.q.put(("log", {"message": message, "level": level,
                             "ts": datetime.now().strftime("%H:%M:%S")}))

    def progress(self, current: int, total: int, label: str = "") -> None:
        self.q.put(("progress", {"current": current, "total": total, "label": label}))

    def file_progress(self, pct: float, label: str = "") -> None:
        self.q.put(("file_progress", {"pct": round(pct, 3), "label": label}))

    def stats(self, data: dict) -> None:
        self.q.put(("stats", data))

    def done(self, success: bool, summary: str = "") -> None:
        self.q.put(("done", {"success": success, "summary": summary}))

    def drain(self) -> List[Tuple[str, Any]]:
        events = []
        while True:
            try:
                events.append(self.q.get_nowait())
            except queue.Empty:
                break
        return events


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA DE CONVERSIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _get_duration(ffprobe: str, file_path: str) -> float:
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=15,
            creationflags=SUBPROCESS_FLAGS,
        )
        val = proc.stdout.strip()
        if val and val.replace(".", "", 1).isdigit():
            return float(val)
    except Exception:
        pass
    return 0.0


def _build_ffmpeg_args(fmt: dict, cfg: VideoConverterConfig,
                        input_file: str, output_file: str) -> List[str]:
    args = ["-y", "-i", input_file]

    args += ["-c:v", fmt["vcodec"]]
    args += ["-crf", str(cfg.crf)]

    if fmt.get("format_id") == "av1" or cfg.format_id == "av1":
        extra = f"-cpu-used {cfg.av1_cpu_speed} -pix_fmt yuv420p -b:v 0"
    else:
        extra = fmt["extra"]
    args += extra.split()

    if cfg.resize_mode == "width" and cfg.resize_width > 0:
        args += ["-vf", f"scale={cfg.resize_width}:-1"]
    elif cfg.resize_mode == "both" and cfg.resize_width > 0 and cfg.resize_height > 0:
        args += ["-vf", f"scale={cfg.resize_width}:{cfg.resize_height}"]

    if fmt["is_image"] or cfg.remove_audio:
        args += ["-an"]
    else:
        args += ["-c:a", fmt["acodec"], "-b:a", "128k"]

    args += [output_file, "-progress", "pipe:2", "-nostats"]
    return args


def run_conversion(cfg: VideoConverterConfig, bridge: WorkerBridge) -> None:
    fmt_data = FORMATS.get(cfg.format_id)
    if not fmt_data:
        raise ValueError(f"Formato desconocido: {cfg.format_id}")
    fmt_data = dict(fmt_data)
    fmt_data["format_id"] = cfg.format_id

    if not Path(cfg.input_dir).is_dir():
        raise FileNotFoundError(f"Carpeta de entrada no existe: {cfg.input_dir}")

    for label, path in [("FFmpeg", cfg.ffmpeg_path), ("FFprobe", cfg.ffprobe_path)]:
        if not shutil.which(path):
            raise FileNotFoundError(f"{label} no encontrado: {path}")

    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    bridge.log("Verificando FFmpeg…", "INFO")
    try:
        r = subprocess.run([cfg.ffmpeg_path, "-version"],
                           capture_output=True, text=True,
                           creationflags=SUBPROCESS_FLAGS)
        first = r.stdout.splitlines()[0] if r.stdout else "FFmpeg detectado"
        bridge.log(f"✓ {first}", "SUCCESS")
    except Exception as e:
        raise RuntimeError(f"No se pudo ejecutar FFmpeg: {e}")

    bridge.cancel_token.check()

    exts  = fmt_data["input_exts"]
    files = sorted([f for f in Path(cfg.input_dir).iterdir()
                    if f.is_file() and f.suffix.lower() in exts])
    total = len(files)

    if total == 0:
        raise FileNotFoundError(
            f"No se encontraron archivos compatibles en: {cfg.input_dir}\n"
            f"Extensiones: {', '.join(exts)}"
        )

    bridge.log(f"✓ {total} archivo(s) encontrado(s)", "SUCCESS")
    bridge.log(f"  Formato : {fmt_data['label']}  |  CRF: {cfg.crf}", "INFO")
    bridge.log(f"  Entrada : {cfg.input_dir}", "INFO")
    bridge.log(f"  Salida  : {cfg.output_dir}", "INFO")
    if cfg.resize_mode == "width":
        bridge.log(f"  Resize  : {cfg.resize_width}px de ancho", "INFO")
    elif cfg.resize_mode == "both":
        bridge.log(f"  Resize  : {cfg.resize_width}×{cfg.resize_height}px", "INFO")
    if not fmt_data["is_image"] and cfg.remove_audio:
        bridge.log("  Audio   : eliminado (-an)", "INFO")

    converted = 0
    skipped   = 0
    errors    = 0
    failed_files: List[str] = []
    log_path  = Path(cfg.output_dir) / "conversion_log.txt"
    log_lines = [f"Conversión iniciada: {datetime.now()}"]
    start_time = datetime.now()

    for idx, file_path in enumerate(files, 1):
        bridge.cancel_token.check()
        bridge.progress(idx, total, file_path.name)
        bridge.log(f"[{idx}/{total}] {file_path.name}", "INFO")

        output_file = Path(cfg.output_dir) / f"{file_path.stem}.{fmt_data['ext']}"

        if output_file.exists():
            if not cfg.overwrite_all:
                bridge.log("  ⏭ Ya existe — omitiendo", "WARNING")
                log_lines.append(f"SKIP: {file_path.name}")
                skipped += 1
                bridge.stats({"converted": converted, "skipped": skipped,
                              "errors": errors, "total": total, "current": idx})
                continue
            else:
                try:
                    output_file.unlink()
                except Exception as e:
                    bridge.log(f"  ✗ No se pudo eliminar existente: {e}", "ERROR")
                    skipped += 1
                    bridge.stats({"converted": converted, "skipped": skipped,
                                  "errors": errors, "total": total, "current": idx})
                    continue

        duration = 0.0
        if not fmt_data["is_image"]:
            bridge.log("  Analizando duración…", "DIM")
            duration = _get_duration(cfg.ffprobe_path, str(file_path))
            if duration > 0:
                bridge.log(f"  ✓ Duración: {duration:.1f}s", "DIM")

        args = _build_ffmpeg_args(fmt_data, cfg, str(file_path), str(output_file))
        bridge.log("  Convirtiendo…", "INFO")

        try:
            proc = subprocess.Popen(
                [cfg.ffmpeg_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
                creationflags=SUBPROCESS_FLAGS,
            )
            bridge.cancel_token.active_process = proc

            stderr_lines: List[str] = []

            def _read_stderr():
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_lines.append(line.rstrip())

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            last_pct = -1.0
            assert proc.stdout is not None
            for line in proc.stdout:
                if bridge.cancel_token.is_cancelled():
                    proc.terminate()
                    break
                line = line.rstrip()
                cur_sec = 0.0
                if line.startswith("out_time_ms="):
                    try:
                        cur_sec = int(line.split("=")[1]) / 1_000_000.0
                    except Exception:
                        pass
                elif line.startswith("out_time="):
                    try:
                        t = line.split("=")[1]
                        parts = t.split(":")
                        cur_sec = int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])
                    except Exception:
                        pass
                elif line == "progress=end":
                    bridge.file_progress(1.0, "100%")
                    break

                if duration > 0 and cur_sec > 0:
                    pct = min(1.0, cur_sec / duration)
                    if pct - last_pct >= 0.03:
                        bridge.file_progress(pct, f"{pct*100:.0f}%")
                        last_pct = pct

            proc.wait()
            stderr_thread.join(timeout=2)
            bridge.cancel_token.active_process = None
            bridge.cancel_token.check()

            if proc.returncode == 0 and output_file.exists():
                orig_mb = file_path.stat().st_size / (1024 * 1024)
                out_mb  = output_file.stat().st_size / (1024 * 1024)
                red     = (1 - out_mb / orig_mb) * 100 if orig_mb > 0 else 0
                bridge.log(f"  ✓ {out_mb:.2f} MB  (reducción: {red:.1f}%)", "SUCCESS")
                log_lines.append(f"OK: {file_path.name} -> {output_file.name}")
                converted += 1
            else:
                err_detail = "\n".join(stderr_lines[-5:]) if stderr_lines else f"código {proc.returncode}"
                bridge.log(f"  ✗ Error FFmpeg: {err_detail}", "ERROR")
                log_lines.append(f"ERROR: {file_path.name}")
                failed_files.append(file_path.name)
                errors += 1

        except OperationCancelled:
            bridge.cancel_token.active_process = None
            raise
        except Exception as exc:
            bridge.cancel_token.active_process = None
            bridge.log(f"  ✗ {exc}", "ERROR")
            failed_files.append(file_path.name)
            errors += 1

        bridge.stats({
            "converted": converted, "skipped": skipped,
            "errors": errors, "total": total, "current": idx,
        })

    elapsed = str(datetime.now() - start_time).split(".")[0]
    try:
        log_lines.append(f"Finalizado: {datetime.now()} — OK:{converted} SKIP:{skipped} ERR:{errors}")
        log_path.write_text("\n".join(log_lines), encoding="utf-8")
    except Exception:
        pass

    bridge.file_progress(1.0, "")
    bridge.log(f"Completado en {elapsed} · {converted} convertidos · {skipped} omitidos · {errors} errores", "SUCCESS")

    if failed_files:
        bridge.log("Archivos con errores:", "ERROR")
        for f in failed_files:
            bridge.log(f"  • {f}", "ERROR")

    if cfg.open_output and Path(cfg.output_dir).exists():
        try:
            if sys.platform == "win32":
                os.startfile(cfg.output_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", cfg.output_dir])
            else:
                subprocess.Popen(["xdg-open", cfg.output_dir])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# ESTADO GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

_worker_bridge: Optional[WorkerBridge] = None
_worker_thread: Optional[threading.Thread] = None
CONFIG_PATH = Path(__file__).parent / CONFIG_FILE


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Video Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
def get_config():
    return _load_config()


@app.post("/api/config")
def save_config(req: ConfigSaveRequest):
    _save_config(req.config)
    return {"ok": True}


@app.get("/api/formats")
def get_formats():
    return {k: {x: v[x] for x in ("label", "ext", "crf_min", "crf_max", "crf_default",
                                    "crf_info", "is_image", "input_exts")}
            for k, v in FORMATS.items()}


@app.post("/api/start")
def start_conversion(req: ConvertRequest):
    global _worker_bridge, _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        return {"ok": False, "error": "Ya hay una conversión en curso"}

    cfg = VideoConverterConfig(
        input_dir    = req.input_dir,
        output_dir   = req.output_dir,
        ffmpeg_path  = req.ffmpeg_path,
        ffprobe_path = req.ffprobe_path,
        format_id    = req.format_id,
        crf          = req.crf,
        remove_audio = req.remove_audio,
        resize_mode  = req.resize_mode,
        resize_width = max(1, req.resize_width),
        resize_height= max(1, req.resize_height),
        av1_cpu_speed= max(0, min(8, req.av1_cpu_speed)),
        overwrite_all= req.overwrite_all,
        open_output  = req.open_output,
    )

    _worker_bridge = WorkerBridge()
    bridge = _worker_bridge

    def worker():
        try:
            run_conversion(cfg, bridge)
            bridge.done(True, "Conversión finalizada")
        except OperationCancelled:
            bridge.log("Operación cancelada por el usuario", "WARNING")
            bridge.done(False, "Cancelado")
        except Exception as exc:
            bridge.log(f"Error: {exc}", "ERROR")
            bridge.log(traceback.format_exc(), "DIM")
            bridge.done(False, str(exc))

    _worker_thread = threading.Thread(target=worker, daemon=True)
    _worker_thread.start()
    return {"ok": True}


@app.post("/api/stop")
def stop_conversion():
    if _worker_bridge:
        _worker_bridge.cancel_token.cancel()
        return {"ok": True}
    return {"ok": False, "error": "No hay conversión activa"}


@app.get("/api/status")
def get_status():
    return {"running": bool(_worker_thread and _worker_thread.is_alive())}


@app.post("/api/shutdown")
def shutdown():
    os.kill(os.getpid(), signal.SIGTERM)
    return {"ok": True}


@app.get("/api/select-folder")
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory()
    root.destroy()
    return {"folder": folder}


# Servir Frontend
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")


@app.get("/api/events")
async def event_stream(request: Request):
    async def generator():
        while True:
            if await request.is_disconnected():
                break
            bridge = _worker_bridge
            if bridge:
                for event_type, payload in bridge.drain():
                    data = json.dumps({"type": event_type, "payload": payload})
                    yield f"data: {data}\n\n"
            await asyncio.sleep(0.04)

    return StreamingResponse(generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Video Converter — Backend local")
    print("  http://localhost:8002")
    print("  Abre frontend/index.html en tu navegador")
    print("=" * 55)
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")
