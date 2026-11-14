# Actual Work ZIP receipt audit (D13 + D14–D16)

This standalone script only validates the pinned, **real** private Work archive format in local memory. It never sends research data to an API, writes a research database, or prints names, IDs, URLs, or text.

Run:

```powershell
py -3 scripts/k37_work_archive_compat.py "<private D13 ZIP path>" "<private D14-D16 ZIP path>"
```

Required inputs remain **two separate local files**. The D14–D16 delta references the frozen D13 base; it does not embed D13. SHA anchors are hardcoded for the two artifacts. An earlier management-chat verification reported 14 nested layers, 45 checksum entries, 96 source records, 98 claims, 45 passage records, 80 D16 comparison sets, 864 unknown rights decisions, and no detected ID collisions or failed checked references. Those are prior reported results; the current Codex session cannot independently reproduce them because the two private files are not accessible here. The script checks a subset of their structure and reports incomplete D15/D16 reference verification explicitly.

**The script is not the missing compatibility adapter for the interactive UI.** The K3 generic receiver expects `scriptura.research-archive.v1` and `records/*.jsonl`; actual D14–D16 is `MANIFEST.json`, `d14/records/*.jsonl`, `d15/records/*.jsonl`, and `d16/records/*.jsonl` with a separate D13 baseline. Follow issue #1 to implement private two-file UI intake and verifiable source/claim attribution. Do not mark K3–K5 complete until actual data is connected and locally tested.

Do not copy research ZIPs, confidential paths, raw records, extensive quoted passages, or identity data into GitHub/CI/LLM logs. Actual archive access is required for private-local receipt tests; synthetic CI cannot prove it.
