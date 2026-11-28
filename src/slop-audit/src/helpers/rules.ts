export type RuleSource = "class" | "text";

export interface RuleCheck {
  regex: RegExp;
  guard?: (value: string, match: RegExpExecArray) => boolean;
  require?: RegExp[];
  forbid?: RegExp[];
}

export interface RuleDefinition {
  name: string;
  message: string;
  suggestion: string;
  source: RuleSource;
  check: RuleCheck;
}

const CLASS_FNS = new Set(["cx", "clsx", "classnames", "cn", "classNames"]);
const TEXT_ATTRS = new Set(["aria-label", "title", "placeholder", "alt"]);

function globalRegex(regex: RegExp): RegExp {
  const flags = regex.flags.includes("g") ? regex.flags : `${regex.flags}g`;
  return new RegExp(regex.source, flags);
}

export function staticString(node: any): string | null {
  if (!node) return null;
  if (node.type === "Literal" && typeof node.value === "string") {
    return node.value;
  }
  if (node.type === "TemplateLiteral" && node.expressions.length === 0) {
    return node.quasis.map((quasi: any) => quasi.value.cooked ?? "").join("");
  }
  if (node.type === "JSXExpressionContainer") {
    return staticString(node.expression);
  }
  return null;
}

function calleeName(node: any): string | null {
  const callee = node?.callee;
  if (!callee) return null;
  if (callee.type === "Identifier") return callee.name;
  if (callee.type === "MemberExpression" && !callee.computed) {
    return callee.property?.name ?? null;
  }
  return null;
}

export function matchesCheck(value: string, check: RuleCheck): boolean {
  const matcher = globalRegex(check.regex);
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(value)) !== null) {
    if (check.require?.some((regex) => !regex.test(value))) continue;
    if (check.forbid?.some((regex) => regex.test(value))) continue;
    if (check.guard && !check.guard(value, match)) continue;
    return true;
  }
  return false;
}

function reportOnce(context: any, node: any, definition: RuleDefinition): void {
  context.report({
    node,
    message: `${definition.message} [fix: ${definition.suggestion}]`,
  });
}

export function createRule(definition: RuleDefinition) {
  const check = (value: string): boolean => matchesCheck(value, definition.check);

  return {
    meta: {
      type: "problem",
      docs: { description: definition.message },
      schema: [],
    },
    create(context: any) {
      const visitValue = (node: any, value: string | null): void => {
        if (value && check(value)) reportOnce(context, node, definition);
      };

      return {
        JSXAttribute(node: any) {
          const attributeName = node?.name?.name;
          if (definition.source === "class") {
            if (attributeName === "className" || attributeName === "class") {
              visitValue(node, staticString(node.value));
            }
            return;
          }
          if (attributeName && TEXT_ATTRS.has(attributeName)) {
            visitValue(node, staticString(node.value));
          }
        },
        JSXText(node: any) {
          if (definition.source === "text") {
            visitValue(node, typeof node.value === "string" ? node.value : null);
          }
        },
        CallExpression(node: any) {
          if (definition.source !== "class") return;
          const name = calleeName(node);
          if (!name || !CLASS_FNS.has(name)) return;
          const parts = (node.arguments ?? [])
            .map((argument: any) => staticString(argument))
            .filter((part: string | null): part is string => Boolean(part));
          if (parts.length) visitValue(node, parts.join(" "));
        },
      };
    },
  };
}

export const regex = (pattern: string, flags = "i"): RegExp =>
  new RegExp(pattern, flags);
