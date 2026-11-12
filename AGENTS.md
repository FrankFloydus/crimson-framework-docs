<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

- Edit this checkout as a standalone Git repository. Run Mintlify commands from the directory containing `docs.json`. Use `npx mint@latest instructions` and the relevant topic for current CLI guidance.
- Use Crimson Framework and Godot terms from the supported framework release. Put script identifiers and file paths in code spans, and bold editor UI labels. Use active voice and sentence case headings.
- Use the framework release and fixtures to check example behavior. Write customer guides for the purchased addon and keep framework source, build, and repository download links out of public pages. Keep guides and reference aligned with the version in `README.md`.
- Keep **Docs** and **API Reference** as the two top-level tabs. Put articles and examples in **Docs** and the Godot class catalog in **API Reference**.
- Link named Crimson APIs in guide prose to their owning class or member in **API Reference**. Keep code examples copyable. Show a GDScript example for each distinct way of completing a workflow described in a guide.
- Write guide examples as complete scripts with their own dependencies and stated scene setup. Use explicit GDScript types, named constants for meaningful literal values, and top-level typed constants for preloaded scenes and assets.
- Give every API example a task. Show how the caller obtains the required object or state and how it uses the result or applies the change. A function that only forwards the documented call does not demonstrate its purpose.
- Generate `api/classes/` and `api/modules/` using the command in `README.md`. Keep class and member descriptions in the framework class XML or, where that XML lacks prose, in `scripts/api-prose/`. Keep module and service descriptions in `scripts/api-module-prose.json` and custom member examples in `scripts/api-member-examples.json`. Use the generator to check coverage and avoid hand edits to generated pages.
- Validate the Mintlify build and check internal links before proposing a documentation change.
