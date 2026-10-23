import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

// Built into the portal app's static files; Django's marketplace view reads the manifest
// to include the entry's JS and CSS (portal/assets.py).
export default defineConfig({
  base: "/static/marketplace/",
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    // The package is linked from ../../realhrsoft-marketplace-employee-vue, which has its
    // own node_modules: always use this host's single copy of the peer dependencies.
    dedupe: ["vue", "vue-router", "vuetify"],
  },
  build: {
    // On Vercel the "frontend" service serves its own dist/ (see ../vercel.json).
    outDir: process.env.VERCEL
      ? "dist"
      : fileURLToPath(new URL("../portal/static/marketplace", import.meta.url)),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: "src/main.ts" },
  },
});
