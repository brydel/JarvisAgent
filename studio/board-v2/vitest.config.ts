import { defineConfig } from "vitest/config";

// Tests unitaires de la couche de données (src/donnees) : modules sans React ni réseau, exécutés sous Node.
export default defineConfig({
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
