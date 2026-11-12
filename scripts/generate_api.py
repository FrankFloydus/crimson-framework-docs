# Copyright Francesco Di Blasi 2026 - All Rights Reserved

"""Generate the Mintlify reference from a tagged Crimson release and Godot's bindings."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from html import escape
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile


DOCS_ROOT = Path(__file__).resolve().parents[1]
CLASS_ROUTE = "api/classes"
PROSE_DIR = DOCS_ROOT / "scripts" / "api-prose"
ADDON_PATH = "addons/crimson-framework/crimson-framework.gdextension"
DEBUG_DLL = "crimson_framework.windows.template_debug.x86_64.dll"
NOTICE = "Copyright Francesco Di Blasi 2026 - All Rights Reserved"

MEMBER_PATHS = {
    "methods": "methods/method",
    "properties": "members/member",
    "signals": "signals/signal",
    "constants": "constants/constant",
}
SOURCE_GROUPS = {
    "integration/game": "Game runtime",
    "integration/online/steam": "Steam multiplayer",
    "integration/world_session": "World sessions",
    "modules/inventory": "Inventory",
    "modules/match_runtime": "Match runtime",
    "modules/replication": "Replication",
    "modules/save": "Save and restore",
    "modules/scene_load": "Scene loading",
    "modules/session": "Sessions and transport",
    "modules/steam": "Steamworks",
    "modules/steam/publisher": "Steam publisher",
}
REFLECTED_GROUPS = {
    "Game runtime": "GameOperation GameServices OnlineDirectory OnlineDirectoryRequest SceneService",
    "Inventory": "InventoryTransactionAdapter",
    "Match runtime": "CommandRouter GameTransaction PlayerBindings PlayerPossession TransactionCoordinator",
    "Replication": "StateReplication",
    "Save and restore": "SaveCoordinator SavePresentation SaveRequest SaveSlot",
    "Scene loading": "SceneLoadManager",
    "Sessions and transport": (
        "ENetSessionTransport GameSession SessionAuthenticator SessionAuthRequest SessionEndpoint "
        "SessionIdentity SessionTransport SessionTransportResult"
    ),
}
STEAM_GROUPS = {
    "Client and results": (
        "SteamApps SteamBoolResult SteamBytes SteamClient SteamDlc SteamFloatResult SteamIntResult "
        "SteamJsonResult SteamOperation SteamResult SteamStringResult SteamUtils"
    ),
    "Lobbies and social": (
        "SteamFriend SteamListing SteamLobb SteamOverlay SteamParties SteamParty SteamPresence"
    ),
    "Servers and networking": (
        "SteamConnectionPath SteamDelivery SteamMessage SteamNetworking SteamRelayStatus SteamServer SteamSocket"
    ),
    "Stats and leaderboards": "SteamAchievement SteamLeaderboard SteamScore SteamStats",
    "Inventory and purchases": "SteamCommerce SteamInventory SteamItem SteamPurchase",
    "Cloud and Workshop": "SteamCloud SteamSharedCloud SteamWorkshop",
    "Input and device": (
        "SteamAnalogInput SteamController SteamDevice SteamDigitalInput SteamInput SteamRemotePlay SteamTextEntry"
    ),
    "Media and voice": (
        "SteamBroadcast SteamMusic SteamScreenshot SteamTexture SteamTimeline SteamVideo SteamVoice Timeline"
    ),
    "Auth, HTTP, and diagnostics": (
        "SteamAuth SteamBrowser SteamDiagnostic SteamHttp SteamOwnershipTicket SteamWebTicket"
    ),
}
PUBLISHER_GROUPS = {
    "Host and authorization": (
        "SteamPublisherHost SteamPublisherSettings SteamPublisherAuth SteamPublisherCompletion "
        "SteamPublisherResult SteamPublisher SteamAppOwnership SteamIdentity SteamOwnership"
    ),
    "Commerce and inventory": "SteamPurchase SteamPublisherPurchase SteamPublisherInventory SteamTradeSession",
    "Notifications": "SteamGameNotifications SteamLocalizedText SteamNotification",
    "Moderation and leaderboards": "SteamCheat SteamModeration SteamPublisherModeration SteamPublisherLeaderboards",
}
INTERNAL_CLASSES = {
    "SteamAuthOperation",
    "SteamPeer",
    "SteamPublisherCompletion",
    "SteamTimelinePhaseOperation",
    "SteamVideoOperation",
}
BBCODE = re.compile(r"\[code\](.*?)\[/code\]|\[([A-Za-z_][\w.]*)(?: ([^\]\n]+))?\]", re.DOTALL)


@dataclass
class ClassDoc:
    """Store the authored XML alongside signatures emitted by Godot."""

    name: str
    group: str
    authored: ET.Element | None
    reflected: ET.Element | None


@dataclass
class MemberDoc:
    """Keep the authoritative signature and the authored prose for one binding."""

    element: ET.Element
    description: str


def xml_description(element: ET.Element | None, path: str = ".") -> str:
    """Normalize XML indentation while retaining explicit paragraph breaks."""
    if element is None:
        return ""
    target = element.find(path)
    if target is None:
        return ""
    return "\n\n".join(
        " ".join(block.split()) for block in re.split(r"\n\s*\n", "".join(target.itertext()).strip())
    )


def read_release(framework: Path, ref: str) -> tuple[dict[str, ClassDoc], bytes]:
    """Read the tracked XML and exact packaged addon from the requested release tag."""
    commit = subprocess.check_output(
        ["git", "-C", str(framework), "rev-parse", "--verify", f"refs/tags/{ref}^{{commit}}"],
        text=True,
    ).strip()
    archive = subprocess.check_output(
        ["git", "-C", str(framework), "archive", "--format=zip", commit, "framework/src", "framework/releases"],
    )
    with ZipFile(io.BytesIO(archive)) as contents:
        classes = {}
        for path in contents.namelist():
            if "/doc_classes/" not in path or not path.endswith(".xml"):
                continue
            area = path.removeprefix("framework/src/").split("/doc_classes/")[0]
            root = ET.fromstring(contents.read(path))
            name = root.attrib["name"]
            if name in classes:
                raise ValueError(f"Duplicate authored XML for {name}.")
            classes[name] = ClassDoc(name, SOURCE_GROUPS[area], root, None)
        if not classes:
            raise ValueError(f"No authored class XML at {ref}.")
        addon = contents.read(f"framework/releases/crimson-framework-{ref.removeprefix('v')}.zip")
    return classes, addon


def read_bindings(directory: Path) -> dict[str, ET.Element]:
    """Load a Godot doctool result directory by Godot class name."""
    classes = {}
    for path in sorted(directory.glob("*.xml")):
        root = ET.parse(path).getroot()
        name = root.attrib["name"]
        if name in classes:
            raise ValueError(f"Duplicate binding XML for {name}.")
        classes[name] = root
    if not classes:
        raise ValueError(f"No class XML in {directory}.")
    return classes


def reflect(godot: Path, addon: bytes, publisher_dll: Path | None = None) -> dict[str, ET.Element]:
    """Run Godot's GDExtension doctool against the release in an isolated project."""
    with tempfile.TemporaryDirectory(prefix="crimson-api-") as workspace:
        root = Path(workspace)
        project = root / "project"
        output = root / "output"
        (project / ".godot").mkdir(parents=True)
        output.mkdir()
        (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        (project / ".godot" / "extension_list.cfg").write_text(f"res://{ADDON_PATH}\n", encoding="utf-8")
        with ZipFile(io.BytesIO(addon)) as package:
            package.extractall(project)
        descriptor = project / ADDON_PATH
        if not descriptor.is_file():
            raise ValueError(f"The release archive is missing {ADDON_PATH}.")
        if publisher_dll is not None:
            dll_directory = descriptor.parent / "bin"
            shutil.copyfile(publisher_dll, dll_directory / DEBUG_DLL)
            for name in ("steam_api64.dll", "sdkencryptedappticket64.dll"):
                dependency = publisher_dll.parent / name
                if dependency.is_file():
                    shutil.copyfile(dependency, dll_directory / name)
        result = subprocess.run(
            [str(godot.resolve()), "--headless", "--path", str(project), "--doctool", str(output), "--gdextension-docs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if result.returncode or not (output / "doc_classes").is_dir():
            raise ValueError(f"Godot could not extract extension bindings.\n{result.stdout}{result.stderr}")
        return read_bindings(output / "doc_classes")


def add_bindings(classes: dict[str, ClassDoc], runtime: dict[str, ET.Element], publisher: bool = False) -> None:
    """Merge reflected signatures and place newly exposed classes in their module groups."""
    by_class = {name: group for group, names in REFLECTED_GROUPS.items() for name in names.split()}
    if "GameRuntime" not in runtime:
        raise ValueError("Binding XML is missing GameRuntime. Check which addon Godot loaded.")
    if publisher:
        shared = {name for name, doc in classes.items() if doc.reflected is not None}
        if shared - runtime.keys():
            raise ValueError("The trusted DLL is missing standard bindings. Build it from the same release tag.")
    for name, reflected in runtime.items():
        if name in classes:
            doc = classes[name]
            if publisher == (doc.group == "Steam publisher"):
                doc.reflected = reflected
        elif publisher:
            classes[name] = ClassDoc(name, "Steam publisher", None, reflected)
        else:
            group = "Inventory" if name.startswith("SpatialInventory") else by_class.get(name)
            if group is None:
                raise ValueError(f"Assign newly reflected class {name} to its API group.")
            classes[name] = ClassDoc(name, group, None, reflected)
    expected = {name for name, doc in classes.items() if publisher == (doc.group == "Steam publisher")}
    missing = expected - runtime.keys() - INTERNAL_CLASSES
    if missing:
        raise ValueError(f"Binding XML is missing expected public classes: {', '.join(sorted(missing))}.")


def collect_members(doc: ClassDoc) -> dict[str, dict[str, MemberDoc]]:
    """Use reflected types and defaults, with authored prose and additional accessors."""
    all_members = {}
    accessors = set()
    if doc.reflected is not None:
        for property_xml in doc.reflected.findall(MEMBER_PATHS["properties"]):
            accessors.update(property_xml.get(key) for key in ("getter", "setter"))
    for category, path in MEMBER_PATHS.items():
        authored = {item.attrib["name"]: item for item in doc.authored.findall(path)} if doc.authored is not None else {}
        reflected = {item.attrib["name"]: item for item in doc.reflected.findall(path)} if doc.reflected is not None else {}
        names = authored.keys() if doc.reflected is None else reflected.keys()
        if doc.reflected is not None and category == "methods":
            names = names | (authored.keys() & accessors)
        members = {}
        for name in sorted(names):
            source = authored.get(name)
            signature = reflected.get(name)
            if signature is None:
                signature = source
            elif source is not None:
                for attribute in ("deprecated", "experimental", "default", "enum", "is_bitfield"):
                    if attribute in source.attrib and attribute not in signature.attrib:
                        signature.set(attribute, source.attrib[attribute])
                if category in ("methods", "signals"):
                    source_types = {
                        (child.tag, child.get("index")): child
                        for child in source if child.tag in ("param", "return")
                    }
                    for child in signature:
                        source_type = source_types.get((child.tag, child.get("index")))
                        if source_type is not None and source_type.get("enum") and not child.get("enum"):
                            child.set("enum", source_type.attrib["enum"])
            prose_path = "description" if category in ("methods", "signals") else "."
            prose = xml_description(source, prose_path) or xml_description(signature, prose_path)
            members[name] = MemberDoc(signature, prose)
        all_members[category] = members
    return all_members


def accessor_member(name: str, properties: dict[str, MemberDoc]) -> MemberDoc | None:
    """Create a callable declaration for an accessor omitted by Godot's doctool."""
    for member in properties.values():
        prop = member.element
        if prop.get("overrides"):
            continue
        for accessor in ("getter", "setter"):
            if prop.get(accessor) != name:
                continue
            method = ET.Element("method", name=name)
            value_type = {key: prop.attrib[key] for key in ("type", "enum") if key in prop.attrib}
            if accessor == "getter":
                ET.SubElement(method, "return", value_type)
            else:
                ET.SubElement(method, "return", type="void")
                ET.SubElement(method, "param", value_type, index="0", name="value")
            return MemberDoc(method, "")
    return None


def load_overlays(classes: dict[str, ClassDoc], members: dict) -> dict[str, str]:
    """Apply additional prose only where the source XML has no documentation."""
    descriptions = {}
    for path in sorted(PROSE_DIR.glob("*.json")):
        for name, entries in json.loads(path.read_text(encoding="utf-8-sig")).items():
            if name not in classes:
                raise ValueError(f"{path.name}: unknown class {name}.")
            for category, value in entries.items():
                if category == "description":
                    if name in descriptions or any(xml_description(classes[name].authored, field)
                                                   for field in ("brief_description", "description")):
                        raise ValueError(f"{path.name}: duplicate description for {name}.")
                    descriptions[name] = value
                    continue
                if category not in MEMBER_PATHS:
                    raise ValueError(f"{path.name}: unknown category {category} for {name}.")
                for member_name, description in value.items():
                    member = members[name][category].get(member_name)
                    if member is None and category == "methods":
                        member = accessor_member(member_name, members[name]["properties"])
                        if member is not None:
                            members[name][category][member_name] = member
                    if member is None:
                        raise ValueError(f"{path.name}: unknown {category} entry {name}.{member_name}.")
                    if member.description:
                        raise ValueError(f"{path.name}: duplicate description for {name}.{member_name}.")
                    member.description = description
    return descriptions


def code(value: str) -> str:
    """Wrap one expression in a CommonMark code span."""
    runs = [len(run) for run in re.findall(r"`+", value)]
    fence = "`" * (max(runs, default=0) + 1)
    if value.startswith(("`", " ")) or value.endswith(("`", " ")):
        value = f" {value} "
    return f"{fence}{value}{fence}"


def plain(value: str) -> str:
    """Escape XML prose that would otherwise be parsed as MDX or Markdown syntax."""
    value = escape(value, quote=False).replace("{", "&#123;").replace("}", "&#125;")
    return re.sub(r"([\\\[\]*_|])", r"\\\1", value)


def prose(value: str, known_classes: set[str]) -> str:
    """Render the Godot BBCode used in authored class descriptions."""
    result = []
    position = 0
    for match in BBCODE.finditer(value):
        result.append(plain(value[position:match.start()]))
        literal, tag, argument = match.groups()
        if literal is not None:
            result.append(code(literal))
        elif argument is None and tag in known_classes:
            result.append(class_link(tag, known_classes))
        elif tag in ("constant", "enum", "member", "method", "param", "signal"):
            suffix = "()" if tag == "method" else ""
            result.append(code(f"{argument}{suffix}"))
        elif argument is None:
            result.append(code(tag))
        else:
            result.append(plain(match.group()))
        position = match.end()
    result.append(plain(value[position:]))
    return "".join(result)


def class_link(name: str, known_classes: set[str]) -> str:
    """Link only to a class page that will be generated."""
    label = code(name)
    return f"[{label}](/{CLASS_ROUTE}/{name})" if name in known_classes else label


def type_label(element: ET.Element) -> str:
    """Prefer a declared enum name over its integer storage type."""
    return element.get("enum") or element.attrib["type"]


def call_signature(element: ET.Element, method: bool) -> str:
    """Format a callable declaration with argument names, types, defaults, and return type."""
    parameters = []
    for param in sorted(element.findall("param"), key=lambda p: int(p.attrib["index"])):
        argument = f"{param.attrib['name']}: {type_label(param)}"
        if "default" in param.attrib:
            argument += f" = {param.attrib['default']}"
        parameters.append(argument)
    qualifiers = element.get("qualifiers", "").split()
    if "vararg" in qualifiers:
        parameters.append("...")
    signature = f"{element.attrib['name']}({', '.join(parameters)})"
    if method:
        if "static" in qualifiers:
            signature = f"static {signature}"
        returns = element.find("return")
        signature += f" -> {type_label(returns) if returns is not None else 'void'}"
    return signature


def annotations(element: ET.Element) -> str:
    """Convert API status metadata into short visible labels."""
    labels = []
    if "deprecated" in element.attrib:
        labels.append("Deprecated." if not element.attrib["deprecated"] else f"Deprecated. {element.attrib['deprecated']}")
    if "experimental" in element.attrib:
        labels.append("Experimental." if not element.attrib["experimental"] else f"Experimental. {element.attrib['experimental']}")
    if "virtual" in element.get("qualifiers", "").split():
        labels.append("Virtual method.")
    return " ".join(labels)


def table_cell(value: str) -> str:
    """Keep rendered spans and line breaks within a single Markdown table cell."""
    return re.sub(r"(?<!\\)\|", r"\\|", value).replace("\n", " ")


def render_properties(properties: dict[str, MemberDoc], known_classes: set[str]) -> list[str]:
    """Render properties with their accessor bindings and initial values."""
    if not properties:
        return []
    lines = ["## Properties", "", "| Property | Type | Default | Accessors | Description |", "| --- | --- | --- | --- | --- |"]
    for name, member in properties.items():
        element = member.element
        accessors = []
        if element.get("getter"):
            accessors.append(code(f"{element.attrib['getter']}()"))
        if element.get("setter"):
            accessors.append(code(f"{element.attrib['setter']}(value)"))
        default = code(element.attrib["default"]) if "default" in element.attrib else "—"
        description = prose(member.description, known_classes)
        status = annotations(element)
        if status:
            description = f"{plain(status)} {description}".strip()
        row = (code(name), class_link(type_label(element), known_classes), default, ", ".join(accessors) or "—", description)
        lines.append("| " + " | ".join(map(table_cell, row)) + " |")
    return lines + [""]


def render_callables(entries: dict[str, MemberDoc], method: bool, known_classes: set[str]) -> list[str]:
    """Render each signal or method so readers can jump directly to its declaration."""
    if not entries:
        return []
    lines = ["## Methods" if method else "## Signals", ""]
    for name, member in sorted(entries.items()):
        lines.extend([f"### {code(name)}", "", code(call_signature(member.element, method)), ""])
        status = annotations(member.element)
        if status:
            lines.extend([f"**{plain(status)}**", ""])
        if member.description:
            lines.extend([prose(member.description, known_classes), ""])
    return lines


def render_constants(constants: dict[str, MemberDoc], known_classes: set[str]) -> list[str]:
    """Preserve named enum groups and standalone constants."""
    if not constants:
        return []
    enumerations = defaultdict(list)
    for member in constants.values():
        enumerations[member.element.get("enum", "")].append(member)
    lines = ["## Constants and enums", ""]
    for enum, entries in sorted(enumerations.items()):
        if enum:
            bitfield = any(entry.element.get("is_bitfield") == "true" for entry in entries)
            lines.extend([f"### {code(enum)}", ""])
            if bitfield:
                lines.extend(["Bitfield values can be combined.", ""])
        lines.extend(["| Name | Value | Description |", "| --- | --- | --- |"])
        for member in entries:
            attrs = member.element.attrib
            row = (code(attrs["name"]), code(attrs["value"]), prose(member.description, known_classes))
            lines.append("| " + " | ".join(map(table_cell, row)) + " |")
        lines.append("")
    return lines


def render_class(
    doc: ClassDoc,
    members: dict[str, dict[str, MemberDoc]],
    supplemental: str,
    known_classes: set[str],
) -> str:
    """Render one class and its Godot-visible API as Mintlify MDX."""
    root = doc.reflected if doc.reflected is not None else doc.authored
    brief = xml_description(doc.authored, "brief_description") or supplemental
    description = xml_description(doc.authored, "description")
    summary = BBCODE.sub(lambda match: match.group(1) or match.group(3) or match.group(2), brief)
    summary = " ".join(summary.split()) or f"Godot class reference for {doc.name}."
    lines = [
        "---",
        f"title: {json.dumps(doc.name)}",
        f"description: {json.dumps(summary, ensure_ascii=False)}",
        "---",
        "",
        "{/* " + NOTICE + " */}",
        "{/* Generated by scripts/generate_api.py. Update the class XML or prose overlay instead. */}",
        "",
    ]
    base = root.get("inherits")
    if base:
        lines.extend([f"**Inherits** {class_link(base, known_classes)}", ""])
    if doc.group == "Steam publisher":
        lines.extend(["**Availability** [Trusted Steam publisher addon](/steam/publisher).", ""])
    if doc.name in INTERNAL_CLASSES:
        lines.extend(["Crimson creates this class internally. You can use the instances exposed by the framework.", ""])
    for block in dict.fromkeys((brief, description)):
        if block:
            lines.extend([prose(block, known_classes), ""])
    lines.extend(render_properties(members["properties"], known_classes))
    lines.extend(render_callables(members["methods"], True, known_classes))
    lines.extend(render_callables(members["signals"], False, known_classes))
    lines.extend(render_constants(members["constants"], known_classes))
    links = []
    if doc.authored is not None:
        for item in doc.authored.findall("tutorials/link"):
            url = (item.text or "").strip()
            if urlsplit(url).scheme == "https" and urlsplit(url).netloc:
                links.append(f"- [{plain(item.get('title') or url)}]({url})")
    if links:
        lines.extend(["## See also", "", *links, ""])
    return "\n".join(lines).rstrip() + "\n"


def subsection_pages(names: list[str], sections: dict[str, str]) -> list[dict]:
    """Group Steam class pages by service, with the most specific prefix taking precedence."""
    groups = defaultdict(list)
    prefixes = sorted(
        ((prefix, section) for section, patterns in sections.items() for prefix in patterns.split()),
        key=lambda entry: -len(entry[0]),
    )
    for name in names:
        section = next((label for prefix, label in prefixes if name.startswith(prefix)), None)
        if section is None:
            raise ValueError(f"Assign {name} to a Steam API section.")
        groups[section].append(f"{CLASS_ROUTE}/{name}")
    return [{"group": section, "pages": groups[section]} for section in sections if groups[section]]


def navigation(classes: dict[str, ClassDoc]) -> list[dict]:
    """Produce Mintlify navigation groups for the class catalog."""
    groups = defaultdict(list)
    for name, doc in sorted(classes.items()):
        groups[doc.group].append(name)
    result = []
    for group in SOURCE_GROUPS.values():
        names = groups[group]
        if not names:
            continue
        if group in ("Steamworks", "Steam publisher"):
            sections = STEAM_GROUPS if group == "Steamworks" else PUBLISHER_GROUPS
            pages = subsection_pages(names, sections)
        else:
            pages = [f"{CLASS_ROUTE}/{name}" for name in names]
        result.append({"group": group, "pages": pages})
    return result


def sync_navigation(classes: dict[str, ClassDoc], check: bool) -> None:
    """Update generated groups beneath the authored API overview."""
    path = DOCS_ROOT / "docs.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    api = next(tab for tab in config["navigation"]["tabs"] if tab["tab"] == "API Reference")
    groups = api["groups"]
    if not groups or "api/overview" not in groups[0]["pages"]:
        raise ValueError("The API reference tab must start with the authored overview group.")
    expected = [groups[0], *navigation(classes)]
    if groups == expected:
        return
    if check:
        raise ValueError("API groups in docs.json are out of date. Regenerate the API reference.")
    api["groups"] = expected
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def describe_gaps(classes: dict[str, ClassDoc], members: dict, descriptions: dict[str, str]) -> dict:
    """Report classes and members that still need prose, using the overlay JSON format."""
    missing = {}
    for name, doc in sorted(classes.items()):
        gaps = {}
        if not descriptions.get(name) and not any(xml_description(doc.authored, field)
                                                  for field in ("brief_description", "description")):
            gaps["description"] = ""
        for category, entries in members[name].items():
            undocumented = {key: "" for key, entry in entries.items() if not entry.description}
            if undocumented:
                gaps[category] = undocumented
        if gaps:
            missing[name] = gaps
    return missing


def main() -> None:
    """Generate pages, check reproducibility, or print navigation and prose gaps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", type=Path, default=DOCS_ROOT.parent, help="Path to the Crimson Framework Git checkout")
    parser.add_argument("--ref", required=True, help="Crimson Framework release tag, for example v0.0.3")
    parser.add_argument("--godot", type=Path, help="Path to the matching Windows Godot console executable")
    parser.add_argument("--binding-docs", type=Path, help="Previously extracted standard Godot class XML directory")
    parser.add_argument("--publisher-dll", type=Path, help="Trusted debug DLL built from the same release tag")
    parser.add_argument("--publisher-binding-docs", type=Path, help="Previously extracted trusted Godot class XML directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--nav", action="store_true", help="Print Mintlify groups JSON")
    mode.add_argument("--gaps", action="store_true", help="Print undocumented declarations in overlay JSON format")
    mode.add_argument("--check", action="store_true", help="Check that generated class pages are current")
    args = parser.parse_args()
    if args.binding_docs is None and args.godot is None:
        parser.error("Supply --godot or --binding-docs for the standard release.")
    if args.publisher_dll and args.godot is None:
        parser.error("--publisher-dll requires --godot.")
    if args.publisher_dll is None and args.publisher_binding_docs is None:
        parser.error("Supply --publisher-dll or --publisher-binding-docs for the trusted build.")
    try:
        classes, addon = read_release(args.framework.resolve(), args.ref)
        runtime = read_bindings(args.binding_docs) if args.binding_docs else reflect(args.godot, addon)
        add_bindings(classes, runtime)
        if args.publisher_binding_docs:
            add_bindings(classes, read_bindings(args.publisher_binding_docs), publisher=True)
        elif args.publisher_dll:
            add_bindings(classes, reflect(args.godot, addon, args.publisher_dll), publisher=True)
        members = {name: collect_members(doc) for name, doc in classes.items()}
        descriptions = load_overlays(classes, members)
        if args.nav:
            print(json.dumps(navigation(classes), indent=2))
            return
        missing = describe_gaps(classes, members, descriptions)
        if args.gaps:
            print(json.dumps(missing, indent=2))
            return
        if missing:
            raise ValueError(f"{len(missing)} classes have missing prose. Run with --gaps for the exact entries.")
        output = DOCS_ROOT / CLASS_ROUTE
        if not args.check:
            output.mkdir(parents=True, exist_ok=True)
        stale = []
        existing = {path.stem for path in output.glob("*.mdx")}
        for name, doc in sorted(classes.items()):
            content = render_class(doc, members[name], descriptions.get(name, ""), classes.keys())
            path = output / f"{name}.mdx"
            if args.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != content:
                    stale.append(path.name)
            else:
                path.write_text(content, encoding="utf-8", newline="\n")
        if stale or existing - classes.keys():
            stale.extend(f"{name}.mdx (obsolete)" for name in sorted(existing - classes.keys()))
            raise ValueError(f"Update or remove these API pages: {', '.join(stale)}")
        sync_navigation(classes, args.check)
        print(f"{'Verified' if args.check else 'Generated'} {len(classes)} API reference pages for {args.ref}.")
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
