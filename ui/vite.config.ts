import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const API = "http://127.0.0.1:8500"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
  build: { outDir: "../web", emptyOutDir: true },
  server: { proxy: { "/tenants": API, "/faults": API } },
})
