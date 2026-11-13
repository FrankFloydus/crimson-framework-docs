<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

- Edit this checkout as a standalone Git repository. Run Mintlify commands from the directory containing `docs.json`. Use `npx mint@latest instructions` and the relevant topic for current CLI guidance.
- Use Crimson Framework and Godot terms from the addon build documented in `README.md`. Put script identifiers and file paths in code spans, and bold editor UI labels. Use active voice and sentence case headings.
- Use the matching addon and fixtures to check example behavior. Lead new-project guides with the code-first API and cover compatible setup types in migration or lower-level reference. Write customer guides for the purchased addon and keep framework source, build, and repository download links out of public pages.
- Keep **Docs** and **API Reference** as the two top-level tabs. Put articles and examples in **Docs** and the Godot class catalog in **API Reference**.
- Link named Crimson APIs in guide prose to their owning class or member in **API Reference**. Keep code examples copyable. Show a GDScript example for each distinct way of completing a workflow described in a guide.
- Write guide examples as complete scripts with their own dependencies and stated scene setup. Use explicit GDScript types, named constants for meaningful literal values, and top-level typed constants for preloaded scenes and assets.
- Make each guide example runnable from the setup on its own page. List the scene, asset, and control requirements briefly. Teach the Crimson calls in the order the reader uses them, explaining what each changes and what the reader should see. Use plain language and link to Godot's own docs for editor procedures.
- Order the Docs sidebar by framework domain. Introduce each domain's main concepts and classes, then lead into a small runnable example before advanced workflows.
- Give each reference example a concrete game or tool task. In one or two sentences, say when the code runs and what it does. Mention only prerequisites the script needs and link to the relevant Crimson guide for more context. Keep the script focused on the API it illustrates.
- Generate `api/classes/` and `api/modules/` using the command in `README.md`. Keep class and member descriptions in the framework class XML or, where that XML lacks prose, in `scripts/api-prose/`. Keep module descriptions in `scripts/api-module-prose.json`, shared examples in `scripts/api-workflow-examples/`, and individual examples in `scripts/api-member-examples.json`. Use the generator to check coverage and avoid hand edits to generated pages.
- Validate the Mintlify build and check internal links before proposing a documentation change.
