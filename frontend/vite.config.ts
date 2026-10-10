import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
export default defineConfig({
  plugins: [react()],
  base: "./",
  resolve: {
    alias: {
      "@deykit/validators": fileURLToPath(
        new URL("./src/api/generated/validators.cjs", import.meta.url),
      ),
    },
  },
  // Prebundle the local CommonJS validators for browser imports in development.
  optimizeDeps: { include: ["@deykit/validators"] },
  build: { outDir: "dist", sourcemap: false, license: true },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
