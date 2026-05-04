# danalyze

Terminal UI for analyzing disk space usage.

## Installation

Requires [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install from the private GitHub repo:

```bash
uv tool install "git+ssh://git@github.com/atomichighfive/danalyze@v0.1.0"
```

Or from a downloaded wheel:

```bash
uv tool install ./danalyze-0.1.0-py3-none-any.whl
```

## Usage

```bash
danalyze                      # scan current directory
danalyze /some/path           # scan a specific path
danalyze --debug              # enable debug logging (writes danalyze.log)
danalyze -o notes.csv         # pre-load notes from a previous export
```

## Key bindings

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate |
| → | Enter directory |
| ← | Go up |
| `r` | Scan sizes recursively |
| `s` | Toggle sort (alpha / size) |
| Enter | Add / edit note |
| `w` | Export notes to CSV |
| `q` | Quit |
