import { defineConfig } from "vitest/config";


export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/app/**/*.{ts,tsx}", "src/components/map/**/*.{ts,tsx}"],
      exclude: ["src/app/layout.tsx"],
      thresholds: {
        lines: 80,
        branches: 80,
        functions: 80,
        statements: 80,
        "src/components/map/**/*.{ts,tsx}": {
          lines: 80,
          branches: 80,
          functions: 80,
          statements: 80,
        },
      },
    },
  },
});
