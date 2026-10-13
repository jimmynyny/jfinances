import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// `npm run demo -w @mooney/ui` — a gallery of every component, no Storybook.
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  resolve: { alias: { "@mooney/ui": fileURLToPath(new URL("../src/index.ts", import.meta.url)) } },
  server: { port: 5174 },
});
