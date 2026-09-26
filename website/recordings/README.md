# CLI recordings

Terminal recordings of `sqb` for the README and the website, rendered with
[VHS](https://github.com/charmbracelet/vhs) from the `.tape` scripts in `tapes/`. The tapes and
scripts are the source; the rendered GIF, MP4 and PNG files go to `out/`, which is not committed.

| Demo | Shows |
|------|-------|
| `rename` | A model is moved and renamed, and `sqb plan` migrates the existing table. |
| `contract` | A renamed column fails `sqb compile` against an enforced contract. |
| `rules` | A custom rule and a missing test mock fail `sqb compile`. |
| `scope` | `sqb scope --as-path` previews what a move would lose. |
| `janitor` | `sqb janitor` archives a stale table before anything is deleted. |
| `compile` | `sqb compile` catches an unknown column and a type mismatch. Not used yet: the column checks it shows are unreleased. |

The README uses `rename`, `contract`, `rules` and `scope`, copied into `.github/demos/`. Each demo
runs locally on DuckDB, using the projects in [`../examples`](../examples).

## Requirements

- `vhs`, `ttyd` and `ffmpeg` on `PATH`, plus a Chromium or Chrome that VHS can find (it downloads
  one if none is on `PATH`).
- DejaVu Sans Mono, the font the tapes use.
- `tree` (the rename and scope tapes show folder trees).
- `sqb` on `PATH`, or `SQB_BIN` pointing at a directory that contains the `sqb` to record.

## Record

```bash
cd website/recordings
./record.sh rename        # out/rename.gif, out/rename.mp4 and out/rename.png
```

`record.sh` runs `prepare.sh <demo>` to build a clean project under `scratch/<demo>/`, then renders
`tapes/<demo>.tape`. Shared terminal settings and the colour theme, which matches the website's
terminal blocks, are in `tapes/common.tape`.

Look at every recording before publishing it: output such as timings, run IDs and dates changes
between runs.
