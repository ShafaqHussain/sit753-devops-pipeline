import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
  },
  resolve: {
    alias: {
      // libsodium-wrappers' ESM build ("exports"."import") has a broken
      // relative import ("./libsodium.mjs") that only resolves inside the
      // sibling `libsodium` package, not its own folder. Point straight at
      // the CJS build's absolute path instead — an absolute-path alias
      // bypasses the package's "exports" map, which otherwise blocks
      // reaching this file via a bare deep-import specifier.
      "libsodium-wrappers": fileURLToPath(
        new URL(
          "./node_modules/libsodium-wrappers/dist/modules/libsodium-wrappers.js",
          import.meta.url
        )
      ),
    },
  },
});
