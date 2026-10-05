import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Exists so tests can use the same `@/*` imports as source files (tsconfig.json
 * declares the alias for the typechecker; Vitest needs it at resolve time).
 * Without this, test files would have to use relative paths and would break
 * every time a folder moves.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
