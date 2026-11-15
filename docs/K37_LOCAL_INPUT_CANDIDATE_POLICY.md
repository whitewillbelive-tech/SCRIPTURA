# SCRIPTURA K-3~K-7 — Private input-note display tier

## Why this tier exists
The actual D-13 + D-14 Work increments include 145 short `statement_ko` values and 145 short `reasoning_ko` values, but their individual self-authored/nonquotation attestation fields are not populated. The former rule concealed **all** such content, even though the UI's primary purpose is to let its owner inspect the imported research notes privately. Missing metadata is **not** evidence of copyright infringement, nor is it proof of legal permission.

## Three independent states
- **`recorded_unverified`**: field-specific source chain, no conflicting rights/privacy signal, and the existing individual self-summary marker and no-original-text record are present. This remains **not** scholarly or doctrinal confirmation.
- **`local_input_candidate`**: field-specific source chain, **exactly one linked evidence record**, bounded safe input text and no explicit prohibitions; the private work record exists but its independent self-authorship, nonquotation, accuracy and reuse rights are **unverified**. Display only on the authenticated local machine, prominently labeled “비공개 연구 입력 메모 · 독립 확인·비인용 여부 미확인”. Do not treat this as a license or a reviewed/official claim.
- **`pending_review`**: missing/unsafe field, missing source chain, conflicting evidence, privacy flags, explicit field/action restriction or original-quote/original-stored flag. Do not make it searchable or visible.

The same rule applies **separately** to the interpretation summary and reasoning, and cannot promote a writer into a verified speaker or create any rebuttal or affiliation. The old D-12 sealed values and denial logic are preserved. In the newer D-16 private viewer only, the same separately labelled candidate tier also applies to the 35 previously hidden D-12 claim notes; historical K-2/D-12 behavior and source rights records are not rewritten.

### Data boundary
The input note is the already-existing private research record, not scraped source text. Never publish it in GitHub, CI, logs, model output, downloads, or unrestricted APIs. An authenticated loopback API may show it to the individual in the local browser, with `no-store` and no outbound requests. Unknown rights remain unknown for reuse, redistribution, sending to AI, indexing full text or public display. If source notes contain a direct excerpt or licensed material, retain a visible pending label and resolve the rights separately rather than grant them by default. Explicit original-text-storage, quotation, sensitive/private markers, field-level restrictions and denial decisions still prevent candidate display.

### Tests and acceptance
Verify the real input counts privately against pinned D-13 + D-14–D-16 (no research values in output). Expected input totals: D-13 47 claims, D-14 98 claims; don't assert display counts until actual code has run on these bytes. Synthetic tests must cover (a) prior attested state retained; (b) missing attestation maps to distinct local candidate, **not verified**; (c) explicit denial, stored original, quotation, missing evidence and confidential records remain hidden; (d) browser displays status and label; (e) K-2/2.1 prior search and Windows 7/7 behavior regression; (f) no source data in GitHub CI or logs.

**This is a private data-access/UI policy**, not an independent scholarly adjudication, doctrinal adoption or copyright clearance. Academic/human review can remain zero while private research browsing works correctly.
