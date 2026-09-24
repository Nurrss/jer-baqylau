import { setWorkerUrl } from 'maplibre-gl'
// MapLibre 6 resolves its worker relative to its own module URL, which bundling breaks.
// Point it at the worker bundled by Vite (?worker&url bundles its shared chunk) instead (works in dev and production).
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

setWorkerUrl(workerUrl)
