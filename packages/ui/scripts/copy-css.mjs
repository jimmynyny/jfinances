// Concatenate the stylesheet layers into dist/styles.css and copy tokens.css
// on its own so a consumer can take the tokens without the component CSS.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src/styles");
const dist = resolve(here, "../dist");
mkdirSync(dist, { recursive: true });
const tokens = readFileSync(resolve(src, "tokens.css"), "utf8");
const base = readFileSync(resolve(src, "base.css"), "utf8");
const components = readFileSync(resolve(src, "components.css"), "utf8");
const charts = readFileSync(resolve(src, "charts.css"), "utf8");
writeFileSync(resolve(dist, "tokens.css"), tokens);
writeFileSync(resolve(dist, "styles.css"), [tokens, base, components, charts].join("\n\n"));
console.log("css written to dist/");
