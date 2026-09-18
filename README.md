# Blender Config

This is my repository of Blender configuration.

I use a couple different machines for Blender, and I tend to have it managed by Steam so that I can just allow it to apply the updates, etc. But this led to the situation where I was constantly having things out of sync across my desktops. I also use [Chezmoi](https://www.chezmoi.io/) so it made sense to try to get both of them working together.

What I've set up is a `uv`-based system for installing packages that can be linked into the Blender environment, and then updating them. I suspect this may be more fragile than it appears at first, but I'll address that as I need to. Chezmoi manages linking the startup script into them, which then runs on execution and applies my config stuff and links to `sys.path`.

It's working for now!

## Layout

- `scripts/startup/` - the actual Blender add-on functionality (GIS importers, node
  builders, the dynamic script runner, etc.) - this is what chezmoi symlinks into Blender's
  real startup directory on each machine.
- `config/` - the config-sync system (per-machine preference sync) and its schema. Kept
  separate from `scripts/startup/` since it's a config-management concern, not a Blender
  feature - see `config/README.md` for the full schema and how the two are bridged.
- `cli/` - headless entry points (no Blender GUI needed) for running specific add-on
  operators from the command line - see `cli/HEADLESS.md`.

## Config

See [`config/README.md`](config/README.md) for the full config schema (what each key maps
to, current gaps) and how the rendered `config.json` reaches Blender.
