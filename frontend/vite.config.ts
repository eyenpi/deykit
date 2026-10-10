import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
export default defineConfig({
  plugins: [react()],
  base: "./",
  // Standalone AJV validators are CommonJS and need ESM conversion during dev.
  resolve: {
    alias: {
      "@deykit/api-validators": fileURLToPath(
        new URL("./src/api/generated/validators.cjs", import.meta.url),
      ),
    },
  },
  optimizeDeps: { include: ["@deykit/api-validators"] },
  build: { outDir: "dist", sourcemap: false, license: true },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
