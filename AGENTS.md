<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

- Edit this checkout as a standalone Git repository. Run Mintlify commands from the directory containing `docs.json`. Use `npx mint@latest instructions` and the relevant topic for current CLI guidance.
- Use Crimson Framework and Godot terms from the supported framework release. Put script identifiers and file paths in code spans, and bold editor UI labels. Use active voice and sentence case headings.
- Use the framework release and fixtures to check example behavior. Write customer guides for the purchased addon and keep framework source, build, and repository download links out of public pages. Keep guides and reference aligned with the version in `README.md`.
- Keep **Docs** and **API Reference** as the two top-level tabs. Put articles and examples in **Docs** and the Godot class catalog in **API Reference**.
- Generate `api/classes/` using the command in `README.md`. Keep API descriptions in the framework class XML or, where that XML lacks prose, in `scripts/api-prose/`. Use the generator to check coverage and avoid hand edits to generated pages.
- Validate the Mintlify build and check internal links before proposing a documentation change.
