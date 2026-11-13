import { fileURLToPath } from "node:url";

const vitestConfig = {
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      include: ["src/app/**/*.{ts,tsx}"],
      exclude: [
        "src/app/**/*.test.{ts,tsx}",
        "src/app/**/layout.tsx",
        "src/app/**/loading.tsx",
        "src/app/**/error.tsx",
      ],
      thresholds: {
        lines: 80,
        branches: 80,
        functions: 80,
        statements: 80,
      },
      reporter: ["text", "json-summary"],
    },
  },
};

export default vitestConfig;
