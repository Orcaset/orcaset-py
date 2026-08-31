import { defineConfig } from "blume";

export default defineConfig({
  title: "Orcaset",
  description: "Financial models as code — typed, inspectable, and built for agents.",
  github: {
    owner: "Orcaset",
    repo: "orcaset-py",
  },
  content: {
    root: "docs",
  },
  theme: {
    accent: "teal",
    radius: "md",
    mode: "system",
  },
});
