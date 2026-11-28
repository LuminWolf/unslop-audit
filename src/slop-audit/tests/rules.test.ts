import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { rules } from "../src/rules/index";

type Surface = "tsx" | "jsx" | "ts" | "js";

interface Expectation {
  rule: string;
  line: number;
}

interface SharedCase {
  name: string;
  surface: Surface;
  kind: "class-attr" | "class-call" | "text";
  source: string;
  expect: Expectation[];
}

interface Fixture {
  rule: string;
  cases: SharedCase[];
}

const TS_SURFACES = new Set<Surface>(["tsx", "jsx", "ts", "js"]);
const casesDir = new URL("../../../tests/shared/cases/", import.meta.url);

const fixtures: Fixture[] = readdirSync(casesDir)
  .filter((name) => name.endsWith(".json"))
  .map((name) => JSON.parse(readFileSync(new URL(name, casesDir), "utf8")));

function lineOf(source: string, offset: number): number {
  return source.slice(0, offset).split("\n").length;
}

function classAttributeNodes(source: string) {
  const nodes: any[] = [];
  const pattern = /\b(className|class)\s*=\s*"([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    nodes.push({
      type: "JSXAttribute",
      name: { name: match[1] },
      value: { type: "Literal", value: match[2] },
      loc: { start: { line: lineOf(source, match.index) } },
    });
  }
  return nodes;
}

function classCallNodes(source: string) {
  const nodes: any[] = [];
  const pattern = /\b(cx|clsx|classnames|cn|classNames)\s*\(\s*"([^"]*)"\s*\)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    nodes.push({
      type: "CallExpression",
      callee: { type: "Identifier", name: match[1] },
      arguments: [{ type: "Literal", value: match[2] }],
      loc: { start: { line: lineOf(source, match.index) } },
    });
  }
  return nodes;
}

function textNodes(source: string) {
  const nodes: any[] = [];
  const pattern = />([^<>]+)</g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    nodes.push({
      type: "JSXText",
      value: match[1],
      loc: { start: { line: lineOf(source, match.index + 1) } },
    });
  }
  return nodes;
}

function visitorsFor(testCase: SharedCase): Record<string, any[]> {
  switch (testCase.kind) {
    case "class-attr":
      return { JSXAttribute: classAttributeNodes(testCase.source) };
    case "class-call":
      return { CallExpression: classCallNodes(testCase.source) };
    case "text":
      return { JSXText: textNodes(testCase.source) };
    default:
      return {};
  }
}

function collect(rule: any, visitors: Record<string, any[]>) {
  const reports: any[] = [];
  const context = { report: (descriptor: any) => reports.push(descriptor) };
  const listeners = rule.create(context);

  for (const [type, nodes] of Object.entries(visitors)) {
    for (const node of nodes) {
      listeners[type]?.(node);
    }
  }
  return reports;
}

describe("shared rule cases", () => {
  for (const fixture of fixtures) {
    for (const testCase of fixture.cases) {
      if (!TS_SURFACES.has(testCase.surface)) continue;

      it(`${fixture.rule}/${testCase.name}`, () => {
        const rule = rules[fixture.rule];
        expect(rule).toBeDefined();

        const reports = collect(rule, visitorsFor(testCase));
        const expected = testCase.expect.filter(
          (item) => item.rule === fixture.rule || item.rule === `slop-audit/${fixture.rule}`,
        );

        expect(reports).toHaveLength(expected.length);
        const actualLines = reports
          .map((report) => report.node?.loc?.start?.line)
          .sort((a, b) => a - b);
        const expectedLines = expected.map((item) => item.line).sort((a, b) => a - b);
        expect(actualLines).toEqual(expectedLines);
      });
    }
  }
});
