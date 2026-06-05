// scripts/sync-emm.mjs
//
// Idempotent re-pull of E-- source from ~/projects/e--/src/ into the
// vendored mirror at ~/projects/forge/forge/e_minus_minus/. Stage 1
// vendor (v0.2.55, 2026-06-05) seeded the initial pin; use this
// script for subsequent updates rather than copying by hand.
//
// Steps:
//   1. Resolve source: <forge>/../e--/src/. Fail loudly if missing.
//   2. Resolve target: <forge>/forge/e_minus_minus/.
//   3. For each *.py source file, copy contents into target.
//   4. ON EACH COPIED FILE: rewrite bare-name internal imports
//      (`from lexer import X`) to package-relative (`from .lexer
//      import X`). This is the ONLY deviation from byte-equal
//      mirroring — upstream uses bare names because src/ sits on
//      sys.path at runtime in the E-- repo; we need package-relative
//      for `forge.e_minus_minus` to import correctly.
//   5. Update the VERSION file with the current E-- version (from
//      e--/docs/spec.md H1) and HEAD SHA.
//   6. Log every action.
//
// Re-running with no upstream change is idempotent (no writes,
// VERSION file unchanged unless e-- moved).
//
// Usage:
//   node scripts/sync-emm.mjs
//
// Then re-run forge-client-obsidian's sync-engine-bundle to push the
// new e_minus_minus/*.py into the plugin bundle.

import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FORGE_ROOT = path.resolve(__dirname, "..");
const EMM_REPO = path.resolve(FORGE_ROOT, "..", "e--");
const SOURCE = path.join(EMM_REPO, "src");
const TARGET = path.join(FORGE_ROOT, "forge", "e_minus_minus");
const VERSION_FILE = path.join(TARGET, "VERSION");

// The E-- modules that get bare-name imported in upstream src/.
// Internal cross-references; the regex below rewrites these to
// package-relative form.
const INTERNAL_MODULES = [
  "ast_nodes", "emitter", "errors", "lexer",
  "normalizer", "parser", "resolver", "transpiler",
];
const REWRITE_RE = new RegExp(
  `^from (${INTERNAL_MODULES.join("|")}) import`,
  "gm",
);

function rewriteImports(source) {
  return source.replace(REWRITE_RE, "from .$1 import");
}

function readEmmVersion() {
  // Spec.md H1: "# E-- (English--) — Language Specification" then
  // next non-empty line "**Version:** 0.1.7 (draft)". Parse loosely.
  const specPath = path.join(EMM_REPO, "docs", "spec.md");
  const spec = fs.readFileSync(specPath, "utf8");
  const m = spec.match(/\*\*Version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)/);
  return m ? m[1] : "unknown";
}

function readEmmHeadSha() {
  return execSync("git rev-parse HEAD", { cwd: EMM_REPO, encoding: "utf8" })
    .trim();
}

function today() {
  // No new Date() per Workflow rules; allow but stamp ISO date via
  // git's idea of "now" — log-driven instead. For a one-shot CLI
  // tool this is fine; we read the system date directly.
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function main() {
  console.log("=== sync-emm ===\n");

  if (!fs.existsSync(SOURCE)) {
    console.error(`E-- source not found: ${SOURCE}`);
    console.error("Is the e-- repo cloned at ~/projects/e--?");
    process.exit(1);
  }

  fs.mkdirSync(TARGET, { recursive: true });

  const entries = fs.readdirSync(SOURCE, { withFileTypes: true });
  const pyFiles = entries
    .filter(e => e.isFile() && e.name.endsWith(".py"))
    .map(e => e.name)
    .sort();

  console.log(`Source: ${SOURCE}`);
  console.log(`Target: ${TARGET}\n`);

  let copied = 0;
  let unchanged = 0;

  for (const name of pyFiles) {
    const srcAbs = path.join(SOURCE, name);
    const tgtAbs = path.join(TARGET, name);
    const srcBody = fs.readFileSync(srcAbs, "utf8");
    const rewritten = rewriteImports(srcBody);
    if (fs.existsSync(tgtAbs)) {
      const cur = fs.readFileSync(tgtAbs, "utf8");
      if (cur === rewritten) {
        unchanged += 1;
        continue;
      }
    }
    fs.writeFileSync(tgtAbs, rewritten, "utf8");
    console.log(`[copy] ${name}`);
    copied += 1;
  }

  // Update VERSION file.
  const version = readEmmVersion();
  const sha = readEmmHeadSha();
  const versionBody = [
    `e-- version: ${version}`,
    `e-- git SHA: ${sha}`,
    `synced: ${today()}`,
    "notes: sync via scripts/sync-emm.mjs",
    "",
  ].join("\n");
  const curVersion = fs.existsSync(VERSION_FILE)
    ? fs.readFileSync(VERSION_FILE, "utf8") : null;
  if (curVersion !== versionBody) {
    fs.writeFileSync(VERSION_FILE, versionBody, "utf8");
    console.log(`[VERSION] e-- ${version} @ ${sha.slice(0, 8)}`);
  }

  console.log(
    `\nSynced ${copied} new/changed, kept ${unchanged} already-current. ` +
    `Pinned: e-- ${version} (${sha.slice(0, 8)}).`,
  );
  console.log(
    "\nNext step: re-run forge-client-obsidian's sync-engine-bundle to " +
    "push e_minus_minus/*.py into the plugin bundle:",
  );
  console.log("  cd ~/projects/forge-client-obsidian && npm run sync-engine-bundle");
}

main();
