# Video Converter — Web UI

Conversor de Video e Imagen en lote con interfaz web moderna, usando FFmpeg.

## Estructura

```
video_converter/
├── backend/
│   └── main.py        ← FastAPI backend (puerto 8002)
└── frontend/
    └── index.html     ← Interfaz Vue 3 (abrir en navegador)
```

## Requisitos

- Python 3.8+
- FFmpeg:
  - El proyecto está configurado para usar FFmpeg desde la carpeta `0-FFmpeg/bin/` en la raíz del proyecto.
  - Si deseas usar la versión del sistema, asegúrate de que esté en el PATH o ajusta la ruta en la interfaz.
- Paquetes de Python:

```bash
pip install fastapi uvicorn
```

## Uso

### 1. Iniciar el backend

```bash
cd backend
python main.py
```

### 2. Abrir el frontend

Abre `frontend/index.html` en el navegador (doble clic).

---

## Formatos soportados

| Formato | Codec | Entrada | Notas |
|---------|-------|---------|-------|
| MP4 | H.264 (libx264) | .mov .mp4 .avi .mkv .webm | CRF 0-51, recomendado 18-28 |
| WEBM | VP9 (libvpx-vp9) | .mov .mp4 .avi .mkv .webm | CRF 0-63, recomendado 24-33 |
| AVIF | AV1 (libaom-av1) | .jpg .jpeg .png .bmp .tiff .webp | Imágenes a AVIF, CRF 0-63 |

## Características

- **Doble barra de progreso**: lote completo + archivo actual en tiempo real
- El progreso del archivo actual viene del `pipe:2` de FFmpeg (`out_time_ms`)
- Log guardado en `output_dir/conversion_log.txt`
- AV1 speed configurable (0=mejor calidad, 8=más rápido)
- Resize: sin resize / solo ancho (mantiene proporción) / W×H exacto


