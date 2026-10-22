#!/usr/bin/env node
"use strict";
/**
 * Parses one JS/TS/JSX/TSX file with the TypeScript compiler API and prints its outline
 * (functions, classes, schema-like types, their fields) and its imports as one JSON object
 * on stdout. Called as a subprocess, once per file, from languages/javascript/outline.py
 * and languages/javascript/imports.py - never imported into anything else.
 *
 * Usage: node analyze.js <path to the file>
 *
 * The file is read from disk (not stdin) so the compiler API can use its real extension to
 * pick the right parser (.tsx needs JSX mode, .js doesn't).
 */
const fs = require("fs");
const path = require("path");
const ts = require("typescript");

const SCRIPT_KIND = { ".ts": ts.ScriptKind.TS, ".tsx": ts.ScriptKind.TSX, ".jsx": ts.ScriptKind.JSX, ".js": ts.ScriptKind.JS };
const MAX_FIELDS = 24;

function main() {
  const filePath = process.argv[2];
  const text = fs.readFileSync(filePath, "utf8");
  const kind = SCRIPT_KIND[path.extname(filePath)] || ts.ScriptKind.JS;
  const source = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, kind);

  const functions = [];
  const classes = [];
  const schemas = [];
  const imports = [];
  let hasMainGuard = false;

  const lineOf = (node) => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;

  function isAsync(node) {
    const mods = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
    return !!mods && mods.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);
  }

  // The first line of the nearest /** ... */ block directly above this node, if any -
  // the JS/TS equivalent of a Python docstring's first line.
  function docFirstLine(node) {
    const ranges = ts.getLeadingCommentRanges(text, node.getFullStart()) || [];
    for (let i = ranges.length - 1; i >= 0; i--) {
      const raw = text.slice(ranges[i].pos, ranges[i].end);
      if (!raw.startsWith("/**")) continue;
      const body = raw.slice(3, raw.length - 2);
      for (const line of body.split("\n")) {
        const cleaned = line.replace(/^\s*\*\s?/, "").trim();
        if (cleaned) return cleaned;
      }
    }
    return null;
  }

  function param(p) {
    const name = ts.isIdentifier(p.name) ? p.name.text : p.name.getText(source);
    return { name, type: p.type ? p.type.getText(source) : null };
  }

  // `docNode` defaults to `node` itself, but for `export const foo = () => {}` the leading
  // JSDoc comment attaches to the outer statement (the `export` keyword's token), not to
  // the arrow function expression being pointed at for its position - so the statement is
  // passed in separately in that case.
  function addFunction(qualname, name, node, paramNodes, docNode) {
    functions.push({
      qualname, name, line: lineOf(node),
      params: paramNodes.map(param),
      returns: node.type ? node.type.getText(source) : null,
      doc: docFirstLine(docNode || node),
      is_async: isAsync(node),
    });
  }

  // interface Foo { a: string; b?: number } and type Foo = { ... } (object-literal aliases
  // only - a union or a mapped type isn't a "shape with fields" the way a schema is).
  function schemaFromMembers(name, node, members, kind) {
    const fields = [];
    for (const m of members) {
      if (fields.length >= MAX_FIELDS) break;
      if ((ts.isPropertySignature(m) || ts.isPropertyDeclaration(m)) && m.name && ts.isIdentifier(m.name)) {
        fields.push({ name: m.name.text, type: m.type ? m.type.getText(source) : null });
      }
    }
    schemas.push({ name, kind, line: lineOf(node), fields, doc: docFirstLine(node) });
  }

  // const Foo = z.object({ a: z.string(), b: z.number().optional() }) - Zod's schema style,
  // common enough in real TS to be worth recognizing without a class or interface in sight.
  function zodSchemaFrom(name, node, call, docNode) {
    const arg = call.arguments[0];
    if (!arg || !ts.isObjectLiteralExpression(arg)) return;
    const fields = [];
    for (const prop of arg.properties) {
      if (fields.length >= MAX_FIELDS) break;
      if (ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name)) {
        fields.push({ name: prop.name.text, type: prop.initializer.getText(source) });
      }
    }
    schemas.push({ name, kind: "zod", line: lineOf(node), fields, doc: docFirstLine(docNode || node) });
  }

  function isZodObjectCall(expr) {
    if (!ts.isCallExpression(expr)) return false;
    const callee = expr.expression;
    return ts.isPropertyAccessExpression(callee) && callee.name.text === "object" && ts.isIdentifier(callee.expression) && callee.expression.text === "z";
  }

  // Walks a list of statements (a file's top level, or one class's members) and nothing
  // deeper - a nested function inside another function's body is an implementation detail,
  // not part of what this file defines, the same distinction analysis/outline.py's ast pass
  // draws by only walking module and class bodies, never a function's own body.
  function walkStatements(statements, prefix) {
    for (const node of statements) {
      if (ts.isFunctionDeclaration(node) && node.name) {
        addFunction(prefix + node.name.text, node.name.text, node, node.parameters);
      } else if (ts.isClassDeclaration(node) && node.name) {
        const qualname = prefix + node.name.text;
        classes.push(qualname);
        for (const member of node.members) {
          if (ts.isMethodDeclaration(member) || ts.isConstructorDeclaration(member)) {
            const mname = member.name ? member.name.getText(source) : "constructor";
            addFunction(`${qualname}.${mname}`, mname, member, member.parameters);
          } else if (ts.isPropertyDeclaration(member) && member.name && member.initializer &&
                     (ts.isArrowFunction(member.initializer) || ts.isFunctionExpression(member.initializer))) {
            // a class field holding an arrow function - the common "foo = () => {}" method style
            const mname = member.name.getText(source);
            addFunction(`${qualname}.${mname}`, mname, member.initializer, member.initializer.parameters, member);
          }
        }
      } else if (ts.isInterfaceDeclaration(node)) {
        schemaFromMembers(prefix + node.name.text, node, node.members, "interface");
      } else if (ts.isTypeAliasDeclaration(node) && node.type && ts.isTypeLiteralNode(node.type)) {
        schemaFromMembers(prefix + node.name.text, node, node.type.members, "type");
      } else if (ts.isEnumDeclaration(node)) {
        const fields = node.members.slice(0, MAX_FIELDS).map((m) => ({ name: m.name.getText(source), type: null }));
        schemas.push({ name: prefix + node.name.text, kind: "enum", line: lineOf(node), fields, doc: docFirstLine(node) });
      } else if (ts.isVariableStatement(node)) {
        for (const decl of node.declarationList.declarations) {
          if (!decl.initializer || !ts.isIdentifier(decl.name)) continue;
          const name = decl.name.text;
          if (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer)) {
            addFunction(prefix + name, name, decl.initializer, decl.initializer.parameters, node);
          } else if (isZodObjectCall(decl.initializer)) {
            zodSchemaFrom(prefix + name, decl, decl.initializer, node);
          }
        }
      } else if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
        const names = [];
        const clause = node.importClause;
        if (clause) {
          if (clause.name) names.push(clause.name.text); // default import
          if (clause.namedBindings) {
            if (ts.isNamedImports(clause.namedBindings)) {
              for (const el of clause.namedBindings.elements) names.push(el.name.text);
            } else if (ts.isNamespaceImport(clause.namedBindings)) {
              names.push("*");
            }
          }
        }
        imports.push({ specifier: node.moduleSpecifier.text, names });
      } else if (ts.isExportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
        // export { a, b } from "./foo" and export * from "./foo" - a re-export is still a
        // real dependency on that file (the common "barrel file" pattern), the same way
        // Wayfinder already follows a Python __init__.py's re-exports to the real definer.
        const names = [];
        if (node.exportClause && ts.isNamedExports(node.exportClause)) {
          for (const el of node.exportClause.elements) names.push(el.name.text);
        } else {
          names.push("*"); // export * from "./foo"
        }
        imports.push({ specifier: node.moduleSpecifier.text, names });
      } else if (ts.isIfStatement(node) && /require\.main\s*===\s*module/.test(node.expression.getText(source))) {
        hasMainGuard = true;
      } else if (ts.isModuleDeclaration(node) && node.body && ts.isModuleBlock(node.body)) {
        // namespace Foo { ... } - rare, but its members are defined here just as plainly
        walkStatements(node.body.statements, `${prefix}${node.name.getText(source)}.`);
      }
    }
  }

  walkStatements(source.statements, "");
  process.stdout.write(JSON.stringify({ functions, classes, schemas, imports, has_main_guard: hasMainGuard }));
}

try {
  main();
} catch (e) {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
}
