# Video Converter

Una solución de escritorio elegante y potente para la conversión, redimensionamiento y optimización masiva de videos. Esta versión utiliza una interfaz web moderna (Vue 3) conectada a un backend local (FastAPI), utilizando **FFmpeg** como motor de procesamiento.

![Versión](https://img.shields.io/badge/version-1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![FFmpeg](https://img.shields.io/badge/engine-FFmpeg-orange.svg)
![Interfaz](https://img.shields.io/badge/UI-Vue%203-green.svg)

---

## 🎨 Icono del Proyecto

<p align="center">
  <img src="frontend/icon.png" width="160" alt="Video Converter Icon">
</p>

---

## 📁 Estructura del Proyecto

```
video_converter/
├── 0-FFmpeg/            ← Coloca aquí los binarios de FFmpeg (opcional)
│   └── bin/
│       ├── ffmpeg.exe
│       └── ffprobe.exe
├── 1-input/             ← Carpeta por defecto para tus videos originales
├── 2-output/            ← Carpeta donde se guardarán los videos convertidos
├── backend/
│   ├── main.py          ← Servidor FastAPI (puerto 8002)
│   └── video_converter_config.json ← Configuración guardada
├── frontend/
│   └── index.html       ← Interfaz de usuario (Vue 3)
└── start.bat            ← Script de inicio rápido
```

---

## ✨ Características Principales

*   **🔄 Conversión Multi-formato**: Soporte para **MP4 (H.264), WEBM (VP9)** y **AV1 Video**.
*   **📊 Análisis en Tiempo Real**: Doble barra de progreso (lote completo + archivo actual) con datos en tiempo real via Server-Sent Events (SSE).
*   **📏 Redimensionamiento Adaptativo**: Opciones para sin resize, solo ancho (mantiene proporción) o tamaño W×H exacto.
*   **⚡ Control de Calidad**: Ajuste de CRF (Constant Rate Factor) y velocidad de CPU para AV1.
*   **🛠️ Control Total**: Opciones para eliminar audio, sobreescribir existentes y abrir carpeta al terminar.
*   **📝 Registro Detallado**: Log guardado automáticamente en la carpeta de salida (`conversion_log.txt`).
*   **📉 Métrica de Eficiencia**: Calcula y muestra el porcentaje de reducción de tamaño tras la conversión.

---

## 📋 Requisitos del Sistema

### 1. Python 3.8 o superior
Asegúrate de tener Python instalado en tu computadora.
*   **Importante**: Durante la instalación en Windows, asegúrate de marcar la casilla que dice **"Add Python to PATH"**.

#### Instalar dependencias
Para que el script funcione, necesitas instalar un par de librerías. Abre una terminal (Símbolo del sistema / CMD en Windows) y ejecuta el siguiente comando:
```bash
pip install fastapi uvicorn
```

### 2. FFmpeg (El Motor de Procesamiento)
Esta aplicación utiliza FFmpeg para procesar los videos.
*   **Por defecto**: La aplicación intentará usar el comando `ffmpeg` del sistema (si está en el PATH).
*   **Ruta Personalizada**: En la esquina inferior izquierda de la interfaz, puedes escribir la ruta exacta a `ffmpeg` y `ffprobe`.
*   **Opción Recomendada**: Si no quieres instalarlo en el sistema, descarga los binarios y colócalos en `0-FFmpeg/bin/`. Luego, en la interfaz, usa rutas como `0-FFmpeg/bin/ffmpeg.exe` o la ruta absoluta completa.

---

## 🎞️ Formatos Soportados

| Formato | Codec | Entrada | Notas |
|---------|-------|---------|-------|
| MP4 | H.264 (libx264) | .mov .mp4 .avi .mkv .webm | CRF 0-51, recomendado 18-28 |
| WEBM | VP9 (libvpx-vp9) | .mov .mp4 .avi .mkv .webm | CRF 0-63, recomendado 24-33 |
| AV1 | AV1 (libaom-av1) | .mov .mp4 .avi .mkv .webm | Video AV1 (WebM), CRF 0-63 |

---

## 🚀 Cómo Usar

1. **Prepara tus archivos**: Coloca los videos que quieres convertir en la carpeta `1-input/` (o selecciona otra carpeta en la interfaz).
2. **Inicia la aplicación**:
   *   **En Windows**: Haz doble clic en el archivo **`start.bat`**. Esto abrirá la interfaz en tu navegador y encenderá el servidor automáticamente.
   *   **Manual (Cualquier sistema)**: Abre una terminal en la carpeta del proyecto y ejecuta:
       ```bash
       cd backend
       python main.py
       ```
       Luego abre tu navegador y ve a `http://localhost:8002`.

3. **Configura y Convierte**:
   *   **Carpetas**: Puedes hacer clic en los campos de ruta para abrir un selector nativo y elegir carpetas personalizadas.
   *   **Formato**: Selecciona el formato deseado (MP4, WEBM o AV1).
   *   **Calidad**: Ajusta el slider de CRF y otras opciones si lo deseas.
   *   Presiona el botón **"Iniciar conversión"**.
4. **Resultados**: Los videos convertidos aparecerán en la carpeta `2-output/` (o la que hayas seleccionado).

---

## 📝 Notas
- La configuración (rutas, formato, calidad) se guarda automáticamente en `backend/video_converter_config.json` al terminar una conversión.
- El diálogo de selección de carpetas utiliza una ventana nativa (Tkinter) que se abrirá sobre tu navegador cuando hagas clic en el campo de ruta.
- Para cerrar la aplicación correctamente, usa el botón **"Salir"** en la interfaz. Esto detendrá el servidor backend.

---

## 🛠️ Información para Desarrolladores (API)

El backend expone una API en `http://localhost:8002` que puedes usar para integrar con otras herramientas:

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/config` | Carga la configuración guardada |
| POST | `/api/config` | Guarda la configuración |
| GET | `/api/formats` | Obtiene los formatos soportados |
| POST | `/api/start` | Inicia la conversión |
| POST | `/api/stop` | Detiene la conversión |
| GET | `/api/events` | Stream SSE de progreso en tiempo real |
| GET | `/api/status` | Estado del worker (si está corriendo) |
| POST | `/api/shutdown` | Apaga el servidor backend |
| GET | `/api/select-folder` | Abre diálogo para seleccionar carpeta |

---
*Desarrollado por **gwalls86***
