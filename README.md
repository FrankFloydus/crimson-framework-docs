<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

This repository contains the Mintlify documentation for the code-first Crimson Framework API. **Docs** contains articles and examples for customers using the purchased addon. **API Reference** contains the Godot class catalog. The current reference was generated from the framework working tree ahead of its next release.

## Preview and check a change

Run these commands from the directory containing `docs.json`. Install Node.js and use the Mintlify CLI through `npx`.

```powershell
npx mint@latest dev --no-open
```

Open the local URL printed by Mintlify. On Windows, run the preview command from the docs directory in WSL. The native Windows CLI can emit backslashes in nested routes, which prevents the sidebar from highlighting the current page.

Run these checks before opening a pull request.

```powershell
npx mint@latest validate
npx mint@latest broken-links --check-anchors
```

## Update the API reference

The reference generator combines the framework's class XML prose with signatures exported by Godot from a matching addon. The `scripts/api-prose/` files supply descriptions that have yet to be added to the framework's class XML. Update descriptions in the framework XML when you change a binding there. Remove any overlapping supplement when you regenerate this site.

Keep the guides and the generated reference tied to the same framework build. Update affected examples, regenerate the reference, and review class and navigation changes together. Edit guides and `api/overview.mdx` directly. Edit module and service descriptions in `scripts/api-module-prose.json`.

For a shared gameplay example, add an entry to `scripts/api-workflow-examples/` with a task title, a short description of the trigger and result, a complete GDScript script, and the member keys used in the script. Link to a guide if the reader needs editor steps. Member keys use the form `GameResult.properties.ok` or `Game.methods.host`. Shared examples take precedence over individual examples in `scripts/api-member-examples.json`.

To update the development reference, use the local framework checkout with the current Windows Debug addon and Godot 4.7 console executable. Run from the docs repository. Here `..` is the local framework checkout.

```powershell
$godot = 'C:\path\to\Godot_v4.7-stable_win64_console.exe'
python scripts/generate_api.py --framework .. --working-tree --godot $godot
```

Add `--check` to compare the checkout with the expected output or `--gaps` to list missing prose. Working tree generation uses the current class XML for trusted publisher pages. Supply a matching `--publisher-dll` or `--publisher-binding-docs` to reflect those bindings too. When tagging the documented API, use its release tag with `--ref` in place of `--working-tree` and supply the matching trusted build or binding export. Run `python scripts/generate_api.py --help` for all options.
