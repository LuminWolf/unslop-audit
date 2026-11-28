import { definePlugin } from "@oxlint/plugins";
import { rules } from "./rules/index.js";

export default definePlugin({
  meta: {
    name: "slop-audit",
  },
  rules,
});
