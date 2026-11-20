import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => {
  if (process.env.DPCIS_PDF_LAYOUT_TEST !== "1") throw new Error("PDF layout harness requires DPCIS_PDF_LAYOUT_TEST=1");
  if (command !== "serve") throw new Error("Test-session config cannot build production assets");
  return {
    plugins: [react(), tailwindcss()],
    define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify("http://127.0.0.1:8031") },
    resolve: { alias: [
      { find: "@/lib/auth", replacement: path.resolve(__dirname, "option-layout-test-auth.ts") },
      { find: "@", replacement: path.resolve(__dirname, "../src") },
    ] },
    server: { host: "127.0.0.1", port: 5181, strictPort: true, hmr: false, watch: null },
  };
});
