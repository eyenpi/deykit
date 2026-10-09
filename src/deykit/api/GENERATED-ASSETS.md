`static/` contains only the production build of the repository's actual frontend.
Rebuild with `npm run build` in frontend, then `uv run python scripts/bundle-ui.py`.
Verify with the same command's `--check` option. Python package builds require no Node.
