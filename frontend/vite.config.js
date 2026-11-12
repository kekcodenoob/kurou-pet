import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Built files are served by the pet's FastAPI server at /dashboard/
  base: './',
})
