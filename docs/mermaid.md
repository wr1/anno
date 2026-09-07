# Mermaid sidecar — learned contract

Code is the source of truth: `anno.mermaid_dump` (extract + soften) and `anno.mermaid_live` (save/restore). This file is why those rules exist.

## Preview

- The editor is the **local mermaid.js sidecar**, not VS Code. VS Code markdown-mermaid (and the deprecated bierner extension) goes **blank** on parse errors — no useful message.
- `anno mermaid` returns immediately. The sidecar **polls/SSE** the `.md`. Do not reopen and do not schedule a watch loop unless the user asks.
- First load needs the mermaid.js CDN. **Reconnect** reloads the tab. Same file prefers the **same port** so reload reconnects.

## Dump

- Write the `.md` however it comes out: notes, `where X?`, `add Y`, headings, unclosed fences, raw (unfenced) diagrams.
- Soften (`soften_comments`) turns non-statement lines into `%%` so mermaid can still draw. Do not require the human to write valid mermaid. Do not stop to tidy before dumping.
- Avoid `<!-- … -->` around fences: mermaid `-->` closes the HTML comment.

## Save (do not lose the file)

- `Failed to fetch` means the **sidecar is gone**, not that the buffer was discarded. Stash is `localStorage` keyed by **file**, not port. Click Reconnect or run `anno mermaid <name>` and reload.
- **Never save empty over a non-empty file.** Server returns 409; the client refuses too. An empty editor is not “local edits” — disk restore may replace it.
- An empty pane after a session is often a **blank overwrite**. Restore from git/history, then Reconnect. Do not Save while the textarea is blank.

## Graph shape (agent dumps)

- **Connect node ids**, never subgraph ids. Declare nodes, then wrap in `subgraph sg_pkg [pkg]`. `sg_*` must not appear on any `-->`.
- **Files are edge labels** (`build_w_vtk -->|"01_w.vtp"| realise_webs`), not extra nodes. Solver dumps (gx `K S M`, `anba_out.json`, `*.vtu`, `*.npz`) stay on labels — they are not amber viz boxes.
- Amber `output` / viz nodes are only the things the user called viz (aep, bom, fea results, 2d results). **gx results are not viz** — do not add `gx_results` to `sg_out`.
- Skip a three-column `inputs` / `algos` / `outputs` wrapper and skip `inputs --> algos --> outputs`. Dagre stacks those boxes. Let LR follow the dataflow; package subgraphs are enough.
- VS Code-only previewers also choke on `class` / `classDef`, `stroke:#hex`, unquoted `-->|2d|`, and `direction` inside subgraphs. The sidecar is mermaid 11 and is the target.

## Co-work

Loop prompt and completion rules: `SKILL.md` (**Co-work**).
