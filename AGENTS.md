<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->


## SCRIPTURA — mandatory real-data preflight and truthful completion contract

This repository includes a **private-local** research viewer. The Work research
archives live in ChatGPT Library and are NOT available to Codex merely because
another chat can read them. GitHub Actions does not contain those research
archives. Repeating "read the Library" does not grant the required access.

### Before any work involving actual D-13/D-14–D-16 research records

1. Identify the required **actual input bytes**, their expected hashes, the
   current execution environment, and which file tools/mounts are available.
   Verify local existence *in this environment*, not in another chat. Never
   infer access from a filename, a previous chat report, or a checksum alone.
2. For D-13 and D-14–D-16, both are separate required inputs:
   - D-13 SHA-256: b109240d6e47df1e6a822fb530285bc4f0bfc39594123c72c90eaf7a277e72fe
   - D-14–D-16 SHA-256: d78dd6ce2e467db91ba615ed7bf4a1fe962e137ac43ceafd9bc77ab80c95e800
   - Run the repository read-only audit script only **after both private
     files have actually been made available to this runner**.
3. If one input is not accessible, **stop that specific data-dependent work
   immediately**. Do not expend a whole session rebuilding synthetic tests or
   report the complete integration as done. Instead switch the work to a
   supported execution environment with **both** authorized Library access and
   GitHub write access, or use one explicit user-authorized, private, one-time
   file handoff. A status statement is not a data-transfer mechanism.
4. Do not ask the user to re-upload already readable archives. Ask for transfer
   only after establishing that the current execution environment has no
   supported shared storage access. Do not repeatedly ask for the same approval.
5. Actual Work ZIPs and the K-3 generic \`scriptura.research-archive.v1\`
   contract have **different schemas and paths**. Passing a generic synthetic
   fixture does not prove Work archive compatibility. Build a verified adapter
   for the actual historical Work D-13 plus D-14–D-16 split-baseline layout.

### Completion criteria (must all be evidenced; otherwise label scope precisely)

- Real private archives are present and hash/structure/read-only verification
  succeeds inside the same runtime performing the integration.
- D-13 and D-14 data are linked into the **actual local application's UI**,
  including attributed claims, source chain, rights-limited \`statement_ko\`
  and \`reasoning_ko\` when independently eligible.
- D-16 comparison-set references are checked and joined into the UI without
  invented rebuttal, cross-corpus merges, or unverified official attribution.
- Historical D-12 viewer search, passage comparison and source navigation
  remain intact, with regression tests.
- Local actual-data tests and synthetic GitHub CI are reported as **separate**
  evidence. Windows GitHub runner success is NOT user Windows acceptance.
- Avoid forcing every claim to be displayed: restricted or pending field-level
  content must stay hidden. Report accepted and withheld counts by reason.

### Data protection and output rules

Never put actual research ZIPs, private identifiers, URLs from nonpublic
datasets, protected text, quoted originals, secrets, or private paths into
public GitHub, CI artifacts, source files, issue comments, or tool diagnostics.
Use bounded counters/booleans and fixed error codes. Don't upload original
bytes to third-party services without authorization. Keep prior artifacts
immutable; no automatic DB promotion or public deployment.

If an access gate fails, summarize the single actionable blocker immediately,
not after running many unrelated tests. Do not claim "all complete" when the
actual dataset path has never been exercised. Preserve preflight state and
resume from the exact blocked step once input access is legitimately fixed.
