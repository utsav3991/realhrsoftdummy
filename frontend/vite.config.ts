import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

export default defineConfig({
  base: "/static/marketplace/",
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    // The package is vendored as a tarball (npm run vendor:employee): always use this
    // host's single copy of the peer dependencies.
    dedupe: ["vue", "vue-router", "vuetify"],
  },
  build: {
    outDir: fileURLToPath(new URL("../portal/static/marketplace", import.meta.url)),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: "src/main.ts" },
  },
});
