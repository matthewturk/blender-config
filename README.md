# Blender Config

This is my repository of Blender configuration.

I use a couple different machines for Blender, and I tend to have it managed by Steam so that I can just allow it to apply the updates, etc.  But this led to the situation where I was constantly having things out of sync across my desktops.  I also use [Chezmoi](https://www.chezmoi.io/) so it made sense to try to get both of them working together.

What I've set up is a `uv`-based system for installing packages that can be linked into the Blender environment, and then updating them.  I suspect this may be more fragile than it appears at first, but I'll address that as I need to.  Chezmoi manages linking the startup script into them, which then runs on execution and applies my config stuff and links to `sys.path`.

It's working for now!
