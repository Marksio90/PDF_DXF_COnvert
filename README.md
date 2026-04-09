# PDF → DXF Converter V001

Local, cost-free conversion of technical CAD PDFs to DXF 2D files, optimised for CNC production. Runs entirely in Docker — no cloud, no API keys, no AI.

## Key features

- **Native circles and arcs** — 4-arc Bézier sequences are detected and written as `CIRCLE` entities, not polylines. Lasers don't skip.
- **Path joining** — disconnected line segments closer than 0.1 mm are merged into continuous `LWPOLYLINE` chains.
- **Correct Y-axis** — PDF coordinate space (Y grows down) is flipped to DXF space (Y grows up).
- **Frame removal** — drawing borders (> 92 % of page size) are isolated on the `FRAME` layer so auto-scale in nesting software is not thrown off.
- **Transparent confidence** — scale detection is labelled `verified / assumed / unverified`. If scale cannot be determined, a clear warning is shown instead of silently producing a wrong file.
- **Automatic cleanup** — files and DB records older than 48 hours are purged by a background task.

## Layers in the output DXF

| Layer | Content |
|---|---|
| `GEOMETRY` | Main vector geometry — contours, holes, profiles |
| `FRAME` | Drawing border rectangles |
| `TEXT` | Text objects extracted from the PDF |
| `DIMENSIONS_HINTS` | Reserved for dimension entities (future) |

## Quick start

```bash
git clone <repo>
cd PDF_DXF_COnvert
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Architecture

```
[Next.js frontend :3000]
        |  HTTP upload / poll / download
        v
[FastAPI backend :8000]
        |
        |-- pdf_analyzer      -> classifies PDF (vector/mixed/raster)
        |-- geometry_extractor -> extracts raw paths via PyMuPDF
        |-- geometry_optimizer -> circle detection, path joining, frame filter
        |-- scale_detector    -> parses scale/unit from text; confidence rating
        |-- dxf_writer        -> Y-flip, scaling, native circles -> ezdxf
        |-- preview_service   -> PNG thumbnail via PyMuPDF
        |-- qa_report         -> confidence score + warnings JSON
        └-- garbage_collector -> async background cleanup (48 h TTL)
        |
[SQLite /data/jobs.db]   [Files /data/{uploads,outputs,previews}]
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jobs` | Upload PDF, start conversion |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}` | Get job status and QA report |
| `DELETE` | `/api/jobs/{id}` | Delete job and associated files |
| `GET` | `/api/jobs/{id}/preview` | PNG preview of first page |
| `GET` | `/api/jobs/{id}/download` | Download converted DXF |
| `POST` | `/api/jobs/{id}/reconvert` | Re-run with different unit override |

### Upload with forced unit

```bash
curl -F "file=@drawing.pdf" -F "forced_unit=mm" http://localhost:8000/api/jobs
```

## Confidence score

Score 0-100 shown next to each conversion:

| Condition | Penalty |
|---|---|
| Scale not found in PDF | -40 |
| Unit or ratio only (partial) | -15 |
| Raster PDF | -50 |
| Mixed PDF | -10 |
| No geometry extracted | -30 |

## V001 limitations

- First page only (multi-page PDFs: first page is converted).
- Scans and raster-heavy PDFs will produce poor results (low confidence score).
- Spline curves more complex than 90 degree arcs are tessellated into polylines.
- Text is copied to the TEXT layer for reference but is not parsed as dimension values.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy, SQLite |
| PDF parsing | PyMuPDF (fitz) |
| DXF output | ezdxf |
| Preview | PyMuPDF rasteriser |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Infrastructure | Docker, Docker Compose |
