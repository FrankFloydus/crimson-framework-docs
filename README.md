<!-- Copyright Francesco Di Blasi 2026 - All Rights Reserved -->

# Crimson Framework documentation

This repository contains the Mintlify guides and Godot scripting API reference for [Crimson Framework](https://github.com/FrankFloydus/crimson-framework). The current documentation covers [v0.0.3](https://github.com/FrankFloydus/crimson-framework/releases/tag/v0.0.3).

## Preview and check a change

Run these commands from the directory containing `docs.json`. Install Node.js and use the Mintlify CLI through `npx`.

```powershell
npx mint@latest dev --no-open
```

Open the local URL printed by Mintlify. Run these checks before opening a pull request.

```powershell
npx mint@latest validate
npx mint@latest broken-links --check-anchors
```

## Update the API reference

The reference generator combines the framework's class XML prose with signatures exported by Godot from the release addon. The `scripts/api-prose/` files supply descriptions that have yet to be added to the framework's class XML. Update descriptions in the framework XML when you change a binding there. Remove any overlapping supplement when you regenerate this site.

Keep the guides and the generated reference tied to the same framework release. Review the release notes, update affected examples and download links, regenerate the reference, and review class and navigation changes together. Use the class pages in `api/classes/` as generated output. Edit guides and `api/overview.mdx` directly.

Fetch the release tag in your local framework checkout. Build a trusted Debug publisher DLL from that tag with the fixture transport disabled. The standard addon comes from the ZIP already tracked in the release tag. The publisher build steps are in the [trusted publisher guide](https://github.com/FrankFloydus/crimson-framework/blob/v0.0.3/framework/docs/STEAM_PUBLISHER.md).

Run from the docs repository. Here `..` is the framework checkout. Update the DLL paths for your machine.

```powershell
$godot = 'C:\path\to\Godot_v4.7-stable_win64_console.exe'
$publisher = '..\framework\bin\publisher\windows\crimson_framework.windows.template_debug.x86_64.dll'
python scripts/generate_api.py --framework .. --ref v0.0.3 --godot $godot --publisher-dll $publisher
```

The generator writes the class pages and their navigation. Add `--check` to compare the checkout with the expected output. Add `--gaps` to list descriptions that still need prose. Use `--binding-docs` and `--publisher-binding-docs` if you already exported the Godot class XML for both builds. Run `python scripts/generate_api.py --help` for all options.
