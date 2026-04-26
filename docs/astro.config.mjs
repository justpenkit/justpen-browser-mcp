// @ts-check
import { readFileSync } from "node:fs";
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

const pyproject = readFileSync(
  new URL("../pyproject.toml", import.meta.url),
  "utf-8",
);
const VERSION = pyproject.match(/^version = "(.+)"/m)?.[1] ?? "0.0.0";

export default defineConfig({
  site: "https://justpenkit.github.io/justpen-browser-mcp/",
  integrations: [
    starlight({
      title: "justpen-browser-mcp",
      description:
        "Camoufox-based MCP server with multi-instance browser session isolation.",
      logo: { src: "./src/assets/logo.svg" },
      favicon: "/favicon.svg",
      lastUpdated: true,
      customCss: ["./src/styles/custom.css"],
      expressiveCode: {
        themes: ["github-dark-default", "github-light-default"],
      },
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/justpenkit/justpen-browser-mcp",
        },
      ],
      sidebar: [
        {
          label: "Getting started",
          items: [
            { label: "Install", slug: "getting-started/install" },
            { label: "Run the server", slug: "getting-started/run-server" },
            { label: "Configuration", slug: "getting-started/configuration" },
          ],
        },
        {
          label: "Concepts",
          items: [
            { label: "Response envelope", slug: "concepts/response-envelope" },
            {
              label: "Instances & isolation",
              slug: "concepts/instances-isolation",
            },
            { label: "Refs & snapshots", slug: "concepts/refs-snapshots" },
            { label: "Modal state", slug: "concepts/modal-state" },
          ],
        },
        {
          label: "Client setup",
          items: [
            { label: "Claude Code", slug: "client-setup/claude-code" },
            { label: "Copilot CLI", slug: "client-setup/copilot-cli" },
            { label: "Gemini CLI", slug: "client-setup/gemini-cli" },
          ],
        },
        {
          label: "Tools reference",
          items: [
            { label: "Lifecycle", slug: "tools-reference/lifecycle" },
            { label: "Navigation", slug: "tools-reference/navigation" },
            { label: "Interaction", slug: "tools-reference/interaction" },
            { label: "Mouse", slug: "tools-reference/mouse" },
            { label: "Inspection", slug: "tools-reference/inspection" },
            { label: "Verification", slug: "tools-reference/verification" },
            { label: "Code execution", slug: "tools-reference/code-execution" },
            { label: "Cookies & storage", slug: "tools-reference/cookies" },
            { label: "Utility", slug: "tools-reference/utility" },
            { label: "Page", slug: "tools-reference/page" },
          ],
        },
        {
          label: "Contributing",
          items: [
            { label: "Getting started", slug: "contributing/getting-started" },
            { label: "PR checklist", slug: "contributing/pr-checklist" },
            { label: "Lint & typing", slug: "contributing/lint-typing" },
          ],
        },
      ],
    }),
  ],
  vite: {
    define: {
      "import.meta.env.PUBLIC_VERSION": JSON.stringify(VERSION),
    },
  },
});
