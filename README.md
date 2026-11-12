<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

This repository contains the Mintlify documentation for Crimson Framework v0.0.3. **Docs** contains articles and examples for customers using the purchased addon. **API Reference** contains the Godot class catalog.

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

The reference generator combines the framework's class XML prose with signatures exported by Godot from the release addon. The `scripts/api-prose/` files supply descriptions that have yet to be added to the framework's class XML. Update descriptions in the framework XML when you change a binding there. Remove any overlapping supplement when you regenerate this site.

Keep the guides and the generated reference tied to the same framework release. Update affected examples, regenerate the reference, and review class and navigation changes together. Edit guides and `api/overview.mdx` directly. Edit module and service descriptions in `scripts/api-module-prose.json`.

For a shared gameplay example, add an entry to `scripts/api-workflow-examples/` with a task title, a short description of the trigger and result, a complete GDScript script, and the member keys used in the script. Link to a guide if the reader needs editor steps. Member keys use the form `GameDefinition.properties.multiplayer_rules` or `GameRuntime.methods.host_game`. Shared examples take precedence over individual examples in `scripts/api-member-examples.json`.

For maintenance, use a local framework checkout with the matching release tag, the Godot 4.7 console executable, and the trusted Debug publisher DLL for that release. Run from the docs repository. Here `..` is the local framework checkout.

```powershell
$godot = 'C:\path\to\Godot_v4.7-stable_win64_console.exe'
$publisher = 'C:\path\to\trusted\crimson_framework.windows.template_debug.x86_64.dll'
python scripts/generate_api.py --framework .. --ref v0.0.3 --godot $godot --publisher-dll $publisher
```

The generator writes the module indexes, class and member pages, and sidebar navigation. It derives signatures from the binding declarations and includes authored examples where available. Add `--check` to compare the checkout with the expected output. Add `--gaps` to list descriptions that still need prose. Use `--binding-docs` and `--publisher-binding-docs` if you already exported the Godot class XML for both builds. Run `python scripts/generate_api.py --help` for all options.
