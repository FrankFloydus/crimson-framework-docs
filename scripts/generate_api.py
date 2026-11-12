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


def render_member_index(class_name: str, members: dict[str, dict[str, MemberDoc]], known_classes: set[str]) -> list[str]:
    """Give linked identifiers a full-width line, preserving their class-page anchors."""
    def entries(category: str, rows: list[tuple[str, MemberDoc]], level: str) -> list[str]:
        lines = []
        for name, member in rows:
            summary = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\n", member.description, maxsplit=1)[0]
            route = member_route(class_name, category, name)
            link = f"[{code(name)}](/{route})"
            title = f"{level} {link}" if level else f"**{link}**"
            lines.extend([title, "", prose(summary, known_classes), ""])
        return lines

    properties = members["properties"]
    methods = members["methods"]
    lines = []
    if properties:
        lines.extend(["## Properties", "", *entries("properties", sorted(properties.items()), "")])
    if not methods:
        return lines

    accessors = {member.element.get(accessor) for member in properties.values() for accessor in ("getter", "setter")}
    groups = {"Static methods": [], "Instance methods": [], "Virtual methods": [], "Property accessors": []}
    for name, member in sorted(methods.items()):
        qualifiers = member.element.get("qualifiers", "").split()
        category = "Instance methods"
        if name in accessors:
            category = "Property accessors"
        elif "static" in qualifiers:
            category = "Static methods"
        elif "virtual" in qualifiers:
            category = "Virtual methods"
        groups[category].append((name, member))
    lines.extend(["## Methods", ""])
    for category, rows in groups.items():
        if rows:
            lines.extend([f"### {category}", "", *entries("methods", rows, "####")])
    return lines


def render_signals(entries: dict[str, MemberDoc], known_classes: set[str]) -> list[str]:
    """Keep signal signatures and their stable anchors on the class page."""
    if not entries:
        return []
    lines = ["## Signals", ""]
    for name, member in sorted(entries.items()):
        lines.extend([f"### {code(name)}", "", code(call_signature(member.element, False)), ""])
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


def api_breadcrumb(doc: ClassDoc, category: str | None = None) -> str:
    """Link the API index, module, optional service area, and owning class section."""
    links = ["[API Reference](/api/overview)", f"[{plain(doc.group)}](/{module_route(doc.group)})"]
    section = class_section(doc)
    if section:
        links.append(f"[{plain(section)}](/{module_route(doc.group, section)})")
    if category:
        route = f"/{CLASS_ROUTE}/{doc.name}"
        links.extend([f"[{code(doc.name)}]({route})", f"[{category.title()}]({route}#{category})"])
    return " › ".join(links)


def render_class(
    doc: ClassDoc,
    members: dict[str, dict[str, MemberDoc]],
    supplemental: str,
    known_classes: set[str],
) -> str:
    """Render one class and its Godot-visible API as Mintlify MDX."""
    root = doc.reflected if doc.reflected is not None else doc.authored
    brief = class_purpose(doc, supplemental)
    description = xml_description(doc.authored, "description")
    summary = BBCODE.sub(lambda match: match.group(1) or match.group(3) or match.group(2), brief)
    summary = " ".join(summary.split()) or f"Godot class reference for {doc.name}."
    lines = [
        "---",
        f"title: {json.dumps(doc.name)}",
        f"description: {json.dumps(summary, ensure_ascii=False)}",
    ]
    if not (members["properties"] or members["methods"]):
        lines.append('icon: "cube"')
    lines.extend([
        "---",
        "",
        "{/* " + NOTICE + " */}",
        "{/* Generated by scripts/generate_api.py. Update the class XML or prose overlay instead. */}",
        "",
        api_breadcrumb(doc),
        "",
    ])
    base = root.get("inherits")
    if base:
        lines.extend([f"**Inherits** {class_link(base, known_classes)}", ""])
    if doc.group == "Steam publisher":
        lines.extend(["**Availability** [Trusted Steam publisher addon](/steam/publisher).", ""])
    if doc.name in INTERNAL_CLASSES:
        lines.extend(["Crimson creates this class internally. You can use the instances exposed by the framework.", ""])
    if description and description != brief:
        lines.extend(["## Description", "", prose(description, known_classes), ""])
    lines.extend(render_member_index(doc.name, members, known_classes))
    lines.extend(render_signals(members["signals"], known_classes))
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


def module_route(group: str, section: str | None = None) -> str:
    """Return the route of a module or service area landing page."""
    labels = (group, section) if section else (group,)
    slugs = [re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") for label in labels]
    return "/".join(("api/modules", *slugs))


def service_sections(group: str) -> dict[str, str]:
    """Return the service areas defined for a module."""
    return {"Steamworks": STEAM_GROUPS, "Steam publisher": PUBLISHER_GROUPS}.get(group, {})


def class_section(doc: ClassDoc) -> str | None:
    """Assign a Steam class to the service area with the most specific name prefix."""
    sections = service_sections(doc.group)
    if not sections:
        return None
    matches = ((len(prefix), section) for section, patterns in sections.items()
               for prefix in patterns.split() if doc.name.startswith(prefix))
    _, section = max(matches, key=lambda match: match[0], default=(0, None))
    if section is None:
        raise ValueError(f"Assign {doc.name} to a Steam API section.")
    return section


def class_purpose(doc: ClassDoc, supplemental: str) -> str:
    """Use the same authored purpose on class pages and in the catalog."""
    return (xml_description(doc.authored, "brief_description") or supplemental
            or xml_description(doc.authored, "description").partition("\n\n")[0])


def module_catalog(classes: dict[str, ClassDoc]) -> dict[str, dict[str | None, list[ClassDoc]]]:
    """Build the ordered catalog shared by module pages and sidebar navigation."""
    groups = {
        group: {section: [] for section in (service_sections(group) or (None,))}
        for group in SOURCE_GROUPS.values()
    }
    for _, doc in sorted(classes.items()):
        groups[doc.group][class_section(doc)].append(doc)
    return {group: {section: docs for section, docs in sections.items() if docs}
            for group, sections in groups.items() if any(sections.values())}


def render_catalog_listing(docs: list[ClassDoc], members: dict, descriptions: dict[str, str],
                           known_classes: set[str]) -> list[str]:
    """List classes with their purpose and named enums with their owning class."""
    lines = ["## Classes", "", "| Class | Purpose |", "| --- | --- |"]
    enums = []
    for doc in docs:
        purpose = class_purpose(doc, descriptions.get(doc.name, ""))
        summary = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", purpose, maxsplit=1)[0]
        lines.append(f"| {class_link(doc.name, known_classes)} | {table_cell(prose(summary, known_classes))} |")
        names = {entry.element.get("enum") for entry in members[doc.name]["constants"].values()}
        enums.extend((doc.name, name) for name in sorted(names - {None, ""}))
    lines.append("")
    if enums:
        lines.extend(["## Enums", "", "| Enum | Declared by |", "| --- | --- |"])
        for owner, name in enums:
            href = f"/{CLASS_ROUTE}/{owner}#{name.lower()}"
            lines.append(f"| [{code(f'{owner}.{name}')}]({href}) | {class_link(owner, known_classes)} |")
        lines.append("")
    return lines


def catalog_heading(title: str, entry: dict) -> list[str]:
    """Start a generated catalog page with its authored module purpose."""
    return ["---", f"title: {json.dumps(title)}",
            f"description: {json.dumps(entry['summary'], ensure_ascii=False)}", "---", "",
            "{/* " + NOTICE + " */}",
            "{/* Generated by scripts/generate_api.py. Update scripts/api-module-prose.json for module prose. */}",
            "", plain(entry["description"]), ""]


def catalog_text(lines: list[str], entry: dict) -> str:
    """Append optional related guides and serialize one catalog page."""
    guides = entry.get("guides", {})
    if guides:
        lines.extend(["## Related guides", "", *[f"- [{plain(label)}]({path})" for label, path in guides.items()], ""])
    return "\n".join(lines).rstrip() + "\n"


def render_module_pages(classes: dict[str, ClassDoc], members: dict,
                        descriptions: dict[str, str]) -> dict[str, str]:
    """Render each module and its service areas from the same catalog as navigation."""
    content = json.loads((DOCS_ROOT / "scripts" / "api-module-prose.json").read_text(encoding="utf-8"))
    known_classes = set(classes)
    pages = {}
    for group, sections in module_catalog(classes).items():
        entry = content[group]
        route = module_route(group)
        lines = catalog_heading(group, entry)
        if None in sections:
            lines.extend(render_catalog_listing(sections[None], members, descriptions, known_classes))
        else:
            lines.extend(["## Service areas", "", "| Service area | Purpose |", "| --- | --- |"])
            for section, docs in sections.items():
                area = entry["sections"][section]
                section_route = module_route(group, section)
                lines.append(f"| [{plain(section)}](/{section_route}) | {table_cell(plain(area['summary']))} |")
                area_lines = catalog_heading(section, area)
                area_lines.extend([f"**Module** [{plain(group)}](/{route})", ""])
                area_lines.extend(render_catalog_listing(docs, members, descriptions, known_classes))
                pages[section_route] = catalog_text(area_lines, area)
            lines.append("")
        pages[route] = catalog_text(lines, entry)
    return pages


def class_navigation(name: str, members: dict[str, dict[str, MemberDoc]]) -> str | dict:
    """Expose member pages in collapsible groups beneath their owning class."""
    class_route = f"{CLASS_ROUTE}/{name}"
    groups = [
        {"group": category.title(), "icon": icon, "expanded": False,
         "pages": [member_route(name, category, member) for member in sorted(members[category])]}
        for category, icon in (("properties", "sliders"), ("methods", "code")) if members[category]
    ]
    if not groups:
        return class_route
    return {"group": name, "icon": "cube", "root": class_route, "expanded": False, "pages": groups}


def navigation(classes: dict[str, ClassDoc], members: dict) -> list[dict]:
    """Give modules, classes, and their members a predictable sidebar path."""
    modules = []
    for group, sections in module_catalog(classes).items():
        pages = []
        for section, docs in sections.items():
            class_pages = [class_navigation(doc.name, members[doc.name]) for doc in docs]
            if section is None:
                pages.extend(class_pages)
            else:
                pages.append({"group": section, "icon": "folder", "root": module_route(group, section),
                              "expanded": False, "pages": class_pages})
        modules.append({"group": group, "icon": "layer-group", "root": module_route(group),
                        "expanded": False, "pages": pages})
    return [{"group": "Modules", "pages": modules}]


def sync_navigation(classes: dict[str, ClassDoc], members: dict, check: bool) -> None:
    """Update generated groups beneath the authored API overview."""
    path = DOCS_ROOT / "docs.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    api = next(tab for tab in config["navigation"]["tabs"] if tab["tab"] == "API Reference")
    groups = api["groups"]
    if not groups or "api/overview" not in groups[0]["pages"]:
        raise ValueError("The API reference tab must start with the authored overview group.")
    expected = [groups[0], *navigation(classes, members)]
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


def sync_pages(output_route: str, pages: dict[str, str], check: bool) -> None:
    """Write or check generated pages and report obsolete files without deleting them."""
    expected = {DOCS_ROOT / f"{route}.mdx": content for route, content in pages.items()}
    existing = set((DOCS_ROOT / output_route).rglob("*.mdx"))
    stale = [f"{path.relative_to(DOCS_ROOT).as_posix()} (obsolete)" for path in sorted(existing - expected.keys())]
    for path, content in expected.items():
        if check:
            if path not in existing or path.read_text(encoding="utf-8") != content:
                stale.append(path.relative_to(DOCS_ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        raise ValueError(f"Update or remove these generated API pages: {', '.join(stale)}")


def member_route(class_name: str, category: str, name: str) -> str:
    """Return the detail page for a method or property of a Crimson class."""
    return f"{CLASS_ROUTE}/{class_name}/{category}/{name}"


def add_property_accessors(members: dict) -> None:
    """Add reflected accessors Godot groups with properties instead of methods."""
    path = DOCS_ROOT / "scripts" / "api-accessor-parameters.json"
    parameter_names = json.loads(path.read_text(encoding="utf-8"))
    for class_name, categories in members.items():
        methods = categories["methods"]
        properties = categories["properties"]
        for property_name, prop in properties.items():
            if prop.element.get("overrides"):
                continue
            for attribute, action in (("getter", "Returns the value of"), ("setter", "Sets the value of")):
                name = prop.element.get(attribute)
                if not name or name in methods:
                    continue
                method = accessor_member(name, properties)
                if method is None:
                    raise ValueError(f"Could not resolve accessor {name} for {property_name}.")
                method.description = f"{action} the [member {property_name}] property."
                if attribute == "setter":
                    parameter = method.element.find("param")
                    parameter.set("name", parameter_names.pop(f"{class_name}.{name}", "value"))
                methods[name] = method
    if parameter_names:
        raise ValueError(f"Unused accessor parameters in {path.name}: {', '.join(sorted(parameter_names))}.")


def render_member_parameters(element: ET.Element, known_classes: set[str]) -> list[str]:
    """List parameters and defaults from the binding's callable declaration."""
    params = sorted(element.findall("param"), key=lambda param: int(param.attrib["index"]))
    varargs = "vararg" in element.get("qualifiers", "").split()
    if not params and not varargs:
        return []
    lines = ["## Parameters", "", "| Parameter | Type | Default |", "| --- | --- | --- |"]
    for param in params:
        default = code(param.attrib["default"]) if "default" in param.attrib else "—"
        row = (code(param.attrib["name"]), class_link(type_label(param), known_classes), default)
        lines.append("| " + " | ".join(map(table_cell, row)) + " |")
    if varargs:
        lines.append("| `...` | `Variant` | — |")
    return lines + [""]


def render_member_return(element: ET.Element, description: str, known_classes: set[str]) -> list[str]:
    """Show the declared type and any explicitly documented awaited result."""
    returns = element.find("return")
    if returns is None or returns.get("type") == "void":
        return []
    declared = type_label(returns)
    lines = ["## Return value", "", class_link(declared, known_classes), ""]
    if declared != "Variant" or not re.search(r"\bawait(?:ing)?\b|\bcompletion signal\b", description, re.I):
        return lines

    types = set(re.findall(r"\[(\w+Result)\]", description)) & known_classes
    if len(types) == 1:
        awaited = class_link(next(iter(types)), known_classes)
    elif re.search(r"\bresult dictionary\b", description, re.I):
        awaited = code("Dictionary")
    else:
        return lines
    lines.extend([f"Await the call to receive {awaited}.", ""])
    return lines


def render_member_property(class_name: str, element: ET.Element, methods: dict[str, MemberDoc],
                           known_classes: set[str]) -> list[str]:
    """Show a property's reflected type, access, and accessor declarations."""
    getter = element.get("getter")
    setter = element.get("setter")
    access = "Read and write" if getter and setter else "Read only" if getter else "Write only"
    rows = [
        ("Type", class_link(type_label(element), known_classes)),
        ("Access", access),
    ]
    if "default" in element.attrib:
        rows.append(("Default", code(element.attrib["default"])))
    if element.get("overrides"):
        rows.append(("Inherited from", class_link(element.attrib["overrides"], known_classes)))
    for label, name in (("Getter", getter), ("Setter", setter)):
        if name:
            accessor = code(f"{name}()")
            if name in methods:
                accessor = f"[{accessor}](/{member_route(class_name, 'methods', name)})"
            rows.append((label, accessor))
    return ["## Property details", "", "| Detail | Value |", "| --- | --- |",
            *["| " + " | ".join(map(table_cell, row)) + " |" for row in rows], ""]


def render_member_page(doc: ClassDoc, category: str, name: str, member: MemberDoc,
                       class_members: dict[str, dict[str, MemberDoc]], known_classes: set[str],
                       example: str) -> str:
    """Render one documented binding as its own Mintlify page."""
    is_method = category == "methods"
    element = member.element
    summary_parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])|\n\n", member.description, maxsplit=1)
    summary = BBCODE.sub(lambda match: match.group(1) or match.group(3) or match.group(2), summary_parts[0])
    summary = " ".join(summary.split())
    title = f"{name}()" if is_method else name
    lines = [
        "---",
        f"title: {json.dumps(title)}",
        f"sidebarTitle: {json.dumps(name)}",
        f"description: {json.dumps(summary, ensure_ascii=False)}",
        "---",
        "",
        "{/* " + NOTICE + " */}",
        "{/* Generated by scripts/generate_api.py. Update the binding documentation or example inputs instead. */}",
        "",
        api_breadcrumb(doc, category),
        "",
    ]
    if doc.group == "Steam publisher":
        lines.extend(["**Availability** [Trusted Steam publisher addon](/steam/publisher).", ""])
    status = annotations(element)
    if status:
        lines.extend([f"**{plain(status)}**", ""])
    if is_method:
        for property_name, prop in class_members["properties"].items():
            if name in (prop.element.get("getter"), prop.element.get("setter")):
                lines.extend([
                    f"**Property** [{code(property_name)}](/{member_route(doc.name, 'properties', property_name)})",
                    "",
                ])
        signature = call_signature(element, True)
    else:
        signature = f"var {name}: {type_label(element)}"
        if "default" in element.attrib:
            signature += f" = {element.attrib['default']}"
    lines.extend(["## Signature", "", "```text", signature, "```", ""])
    if is_method:
        lines.extend(render_member_parameters(element, known_classes))
        lines.extend(render_member_return(element, member.description, known_classes))
    else:
        lines.extend(render_member_property(doc.name, element, class_members["methods"], known_classes))
    if len(summary_parts) > 1:
        lines.extend(["## Description", "", prose(summary_parts[1], known_classes), ""])
    lines.extend(["## Example", "", "```gdscript", example.rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def example_factories(members: dict[str, dict[str, dict[str, MemberDoc]]]) -> dict[str, tuple[str, str]]:
    """Find safe service accessors and builders that can supply an example receiver."""
    sources = {
        "SteamScope": {"messages", "networking", "purchases"},
        "SteamClient": set("""
            apps auth browser cloud device diagnostics friends http input inventory leaderboards lobbies
            music overlay parties presence remote_play screenshots server_browser sockets stats timeline
            utils video voice workshop
        """.split()),
        "SteamPublisher": {"auth", "game_notifications", "inventory", "leaderboards", "moderation", "purchases"},
        "GameRuntime": {"get_possession", "get_transactions", "invites", "voice"},
        "SteamDedicatedServer": {"status"},
        "SteamLobbies": {"query"},
        "SteamServerBrowser": {"query"},
        "SteamLobby": {"edit"},
        "SteamStats": {"edit"},
        "SteamServerPlayerStats": {"edit"},
    }
    factories = {}
    for owner, names in sources.items():
        for name, member in sorted(members.get(owner, {}).get("methods", {}).items()):
            if name not in names:
                continue
            element = member.element
            qualifiers = element.get("qualifiers", "").split()
            if "static" in qualifiers or "virtual" in qualifiers:
                continue
            if any("default" not in param.attrib for param in element.findall("param")):
                continue
            result = element.find("return")
            if result is not None and result.get("type") in members and result.get("type") != owner:
                factories.setdefault(result.attrib["type"], (owner, name))
    return factories


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
    mode.add_argument("--check", action="store_true", help="Check that generated API pages and navigation are current")
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
        add_property_accessors(members)
        if args.nav:
            print(json.dumps(navigation(classes, members), indent=2))
            return
        missing = describe_gaps(classes, members, descriptions)
        if args.gaps:
            print(json.dumps(missing, indent=2))
            return
        if missing:
            raise ValueError(f"{len(missing)} classes have missing prose. Run with --gaps for the exact entries.")
        class_pages = {
            f"{CLASS_ROUTE}/{name}": render_class(doc, members[name], descriptions.get(name, ""), classes.keys())
            for name, doc in sorted(classes.items())
        }
        from api_examples import render_example

        examples_path = DOCS_ROOT / "scripts" / "api-member-examples.json"
        overrides = json.loads(examples_path.read_text(encoding="utf-8-sig")) if examples_path.is_file() else {}
        factories = example_factories(members)
        parents = {name: (doc.reflected if doc.reflected is not None else doc.authored).get("inherits", "")
                   for name, doc in classes.items()}
        example_keys = set()
        member_pages = {}
        for name, doc in sorted(classes.items()):
            for category in ("methods", "properties"):
                for member_name, member in sorted(members[name][category].items()):
                    example_keys.add(f"{name}.{category}.{member_name}")
                    example = render_example(name, category, member.element, member.description, overrides,
                                             catalog=members, factories=factories, parents=parents)
                    member_pages[member_route(name, category, member_name)] = render_member_page(
                        doc, category, member_name, member, members[name], classes.keys(), example,
                    )
        if obsolete_examples := overrides.keys() - example_keys:
            raise ValueError(f"Unknown member example overrides: {', '.join(sorted(obsolete_examples))}.")
        module_pages = render_module_pages(classes, members, descriptions)
        sync_pages(CLASS_ROUTE, class_pages | member_pages, args.check)
        sync_pages("api/modules", module_pages, args.check)
        sync_navigation(classes, members, args.check)
        print(f"{'Verified' if args.check else 'Generated'} {len(class_pages)} class pages, {len(member_pages)} member pages, and "
              f"{len(module_pages)} module and service area pages for {args.ref}.")
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
