import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" makes the build path-relative so it deploys to GitHub Pages
// (or any subdirectory) without knowing the repo name.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
