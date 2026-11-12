# Copyright Francesco Di Blasi 2026 - All Rights Reserved

"""Render GDScript examples that use Crimson bindings in a caller's workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from xml.etree.ElementTree import Element


# GDScript keywords that can appear as native binding argument names.
KEYWORDS = frozenset("""
    and as assert await break breakpoint class class_name const continue elif else enum
    extends false for func if in is match namespace not null or pass preload return self
    signal static super trait true var void while yield
""".split())


# Use public reads to show what a caller can do with an acquired service.
SERVICE_READS = {
    "SteamApps": ("current_language", "language"),
    "SteamAuth": ("web_ticket", "web_ticket"),
    "SteamBroadcastStatus": ("get_viewers", "viewers"),
    "SteamClient": ("get_app_id", "app_id"),
    "SteamCloud": ("quota", "cloud_quota"),
    "SteamDedicatedServer": ("status", "server_status"),
    "SteamDevice": ("hardware", "hardware"),
    "SteamFriends": ("list", "friends"),
    "SteamInput": ("controllers", "controllers"),
    "SteamLobby": ("members", "members"),
    "SteamMusic": ("status", "playback"),
    "SteamOverlay": ("is_ready", "overlay_ready"),
    "SteamPurchases": ("catalog", "purchase_catalog"),
    "SteamScope": ("get_app_id", "app_id"),
    "SteamServerBrowser": ("is_available", "available"),
    "SteamUtils": ("ui_language", "language"),
    "SteamWorkshop": ("query", "workshop_query"),
}

COMMIT_DRAFTS = {
    "SaveRequest": "submit",
    "SteamHttpRequest": "send",
    "SteamLeaderboardQuery": "fetch",
    "SteamLobbyEdit": "submit",
    "SteamLobbyQuery": "fetch",
    "SteamScreenshotRequest": "submit",
    "SteamServerQuery": "fetch",
    "SteamServerStatsEdit": "submit",
    "SteamStatsEdit": "submit",
    "SteamWorkshopPublishRequest": "submit",
    "SteamWorkshopQuery": "fetch",
}

DISPLAY_TYPES = frozenset({"String", "StringName", "int", "float", "Vector2", "Vector2i", "NodePath"})
SUMMARY_FIELDS = ("display_name", "title", "name", "starting_world", "world_id", "phase", "state",
                  "status_code", "map", "count", "total_bytes", "size_bytes", "quantity", "score", "rank",
                  "published_id", "app_id", "revision")


def gd_type(element: Element) -> str:
    """Translate a reflected XML type to its GDScript annotation."""
    name = element.get("enum") or element.attrib["type"]
    if name.endswith("[]"):
        return f"Array[{name[:-2]}]"
    return name.removeprefix("@GlobalScope.")


def snake_case(name: str) -> str:
    """Use a class name as an idiomatic local variable."""
    name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def argument_name(name: str, used: set[str]) -> str:
    """Keep a binding argument readable while avoiding reserved or duplicate names."""
    candidate = name
    while candidate in KEYWORDS or candidate in used:
        candidate += "_value"
    used.add(candidate)
    return candidate


def function_example(name: str, parameters: list[str], result: str, body: list[str]) -> str:
    """Format a typed function, wrapping a long declaration before the call body."""
    signature = f"func {name}({', '.join(parameters)}) -> {result}:"
    if len(signature) > 96:
        arguments = ",\n".join(f"    {item}" for item in parameters)
        signature = f"func {name}(\n{arguments}\n) -> {result}:"
    return "\n".join([signature, *(f"    {line}" for line in body)])


@dataclass
class Scenario:
    """Typed inputs and statements for one game, UI, or backend action."""

    parameters: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    names: set[str] = field(default_factory=set)

    def input(self, name: str, value_type: str) -> str:
        """Declare a value provided by the calling scene or game code."""
        name = argument_name(name, self.names)
        self.parameters.append(f"{name}: {value_type}")
        return name

    def variable(self, name: str, value_type: str, expression: str) -> str:
        """Capture a binding result in an explicitly typed variable."""
        name = argument_name(name, self.names)
        lines = expression.splitlines()
        self.body.append(f"var {name}: {value_type} = {lines[0]}")
        self.body.extend(lines[1:])
        return name


def lookup(catalog: dict, parents: dict[str, str], owner: str, category: str, name: str):
    """Look up a public declaration, including an inherited one."""
    while owner:
        member = catalog.get(owner, {}).get(category, {}).get(name)
        if member is not None:
            return member
        owner = parents.get(owner, "")
    return None


def acquire_receiver(scenario: Scenario, class_name: str, factories: dict[str, tuple[str, str]],
                     catalog: dict, parents: dict[str, str]) -> str:
    """Acquire a scoped service from its public owner or accept an existing game object."""
    name = snake_case(class_name)
    if class_name not in factories:
        return scenario.input(name, class_name)

    owner_type, factory = factories[class_name]
    owner = scenario.input(snake_case(owner_type), owner_type)
    if lookup(catalog, parents, owner_type, "methods", "is_ready"):
        scenario.body.extend([f"if not {owner}.is_ready():", "    return"])
    receiver = scenario.variable(name, class_name, f"{owner}.{factory}()")
    scenario.body.extend([f"if {receiver} == null:", "    return"])
    return receiver


def invoke(target: str, method: str, arguments: list[str], *, deferred: bool = False) -> str:
    """Write a call on several lines when its supplied inputs are long."""
    call = f"{'await ' if deferred else ''}{target}.{method}("
    expression = f"{call}{', '.join(arguments)})"
    if arguments and len(expression) > 82:
        return "\n".join([call, *(f"    {argument}," for argument in arguments), ")"])
    return expression


def member_subject(name: str) -> str:
    """Name the value shown in a view or passed to the next game step."""
    for prefix in ("get_", "set_", "is_", "has_", "can_", "with_"):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def deferred_type(owner: str, name: str, description: str, catalog: dict, parents: dict[str, str]) -> str:
    """Resolve a documented completion payload instead of treating it as an arbitrary Variant."""
    if owner == "GameOperation" and name == "wait":
        return "Dictionary"
    if owner == "SteamLobbyQuery" and name == "fetch":
        return "SteamListingsResult"
    if name == "wait":
        completed = lookup(catalog, parents, owner, "signals", "completed")
        if completed is not None:
            value = completed.element.find("param")
            if value is not None:
                return gd_type(value)
    results = re.findall(r"\b(Steam\w*Result)\b", description)
    return next((result for result in results if result in catalog), "Variant")


def list_element(value_type: str) -> str | None:
    """Resolve an element type for a GDScript collection example."""
    if value_type.startswith("Array["):
        return value_type[6:-1]
    if value_type == "Array":
        return "Variant"
    return {"PackedStringArray": "String", "PackedInt32Array": "int", "PackedInt64Array": "int"}.get(value_type)


def is_steam_result(value_type: str, parents: dict[str, str]) -> bool:
    """Only use the success envelope for classes that inherit SteamResult."""
    while value_type:
        if value_type == "SteamResult":
            return True
        value_type = parents.get(value_type, "")
    return False


def private_value(owner: str, subject: str) -> bool:
    """Keep credentials and other application data out of UI examples."""
    fields = ("secret", "password", "token", "ticket", "proof", "steam_id", "publisher_key")
    return (any(field in subject for field in fields)
            or owner in {"SteamOwnershipTicket", "SteamWebTicket", "SteamDiagnosticMessage"}
            or owner == "SteamHttpResponse" and subject in {"header", "headers", "body", "payload", "bytes"})


def backend_workflow(owner: str) -> bool:
    """Keep headless publisher examples independent of a scene's UI."""
    return owner.startswith(("SteamPublisher", "SteamNotification", "SteamModeration", "SteamPurchaseStore",
                             "SteamOwnershipChallenge", "SteamCheatReport"))


def reject_failed_result(scenario: Scenario, receiver: str) -> None:
    """Stop before reading a payload from a missing or failed Steam result."""
    scenario.body.extend([f"if {receiver} == null:", "    return", f"if not {receiver}.ok:",
                          f"    push_warning({receiver}.message)", "    return"])


def send_ticket(scenario: Scenario, ticket: str, data: str) -> None:
    """Hand off ticket bytes and release the exact ticket after verification finishes."""
    backend = scenario.input("verify_ticket_on_backend", "Callable")
    scenario.body.extend([f"if {data}.is_empty():", f"    {ticket}.close()", "    return",
                          "# This callback sends bytes over your authenticated backend connection."])
    verified = scenario.variable("verified", "bool", f"await {backend}.call({data})")
    scenario.body.extend([f"{ticket}.close()", f"if not {verified}:",
                          '    push_warning("The backend did not verify the Steam ticket.")'])


def use_value(scenario: Scenario, value: str, value_type: str, owner: str, subject: str,
              catalog: dict, parents: dict[str, str]) -> None:
    """Show what the calling code does with the returned value."""
    caption = subject.replace("_", " ").capitalize()
    if value_type == "bool" and not backend_workflow(owner):
        if subject in {"available", "connected", "online", "ready", "enabled", "finished"}:
            button = scenario.input("action_button", "Button")
            scenario.body.append(f"{button}.disabled = not {value}")
        else:
            label = scenario.input("status_label", "Label")
            scenario.body.append(f'{label}.text = "{caption}: yes" if {value} else "{caption}: no"')
        return

    if value_type in DISPLAY_TYPES or "." in value_type:
        if not private_value(owner, subject) and not backend_workflow(owner):
            label = scenario.input(f"{subject}_label", "Label")
            scenario.body.append(f'{label}.text = "{caption}: %s" % str({value})')
            return

    if value_type == "Texture2D":
        preview = scenario.input("preview", "TextureRect")
        scenario.body.append(f"{preview}.texture = {value}")
        return

    if value_type == "Image":
        preview = scenario.input("preview", "TextureRect")
        scenario.body.extend([f"if {value} == null or {value}.is_empty():", "    return",
                              f"{preview}.texture = ImageTexture.create_from_image({value})"])
        return

    if value_type == "SteamWebTicket":
        scenario.body.extend([f"if {value} == null:", "    return"])
        data = scenario.variable("ticket_bytes", "PackedByteArray", f"{value}.bytes()")
        send_ticket(scenario, value, data)
        return

    item_type = list_element(value_type)
    if item_type:
        name = argument_name("entry", scenario.names)
        scenario.body.append(f"for {name}: {item_type} in {value}:")
        presentation = next((prop for prop in ("display_name", "title", "name", "filename")
                             if lookup(catalog, parents, item_type, "properties", prop)), None)
        if presentation and not private_value(owner, subject) and not backend_workflow(owner):
            item_list = scenario.input("results_list", "ItemList")
            scenario.body[-1:-1] = [f"{item_list}.clear()"]
            scenario.body.append(f"    {item_list}.add_item(str({name}.{presentation}))")
        elif item_type in DISPLAY_TYPES and not private_value(owner, subject) and not backend_workflow(owner):
            item_list = scenario.input("results_list", "ItemList")
            scenario.body[-1:-1] = [f"{item_list}.clear()"]
            scenario.body.append(f"    {item_list}.add_item(str({name}))")
        else:
            add_entry = scenario.input(f"add_{subject}_entry", "Callable")
            scenario.body.append(f"    {add_entry}.call({name})")
        return

    if value_type == "Callable" and not backend_workflow(owner):
        button = scenario.input("action_button", "Button")
        scenario.body.append(f"{button}.disabled = not {value}.is_valid()")
        return

    if value_type in catalog or value_type in {"Node", "Node3D", "Camera3D", "PackedScene", "InputEvent", "MultiplayerPeer"}:
        scenario.body.extend([f"if {value} == null:", "    return"])

    if value_type in {"Node", "Node3D", "Camera3D"} and not backend_workflow(owner):
        label = scenario.input(f"{subject}_label", "Label")
        scenario.body.append(f"{label}.text = str({value}.name)")
        return

    if value_type == "PackedByteArray" and owner not in {"SteamCloud", "SteamSharedCloudFile", "SteamCloudFile"}:
        if not private_value(owner, subject) and not backend_workflow(owner):
            label = scenario.input("byte_count_label", "Label")
            scenario.body.append(f'{label}.text = "%d bytes" % {value}.size()')
            return

    if value_type in catalog and not private_value(owner, subject) and not backend_workflow(owner):
        for field_name in SUMMARY_FIELDS:
            member = lookup(catalog, parents, value_type, "properties", field_name)
            if member and gd_type(member.element) in DISPLAY_TYPES and not private_value(value_type, field_name):
                field_value = scenario.variable(field_name, gd_type(member.element), f"{value}.{field_name}")
                use_value(scenario, field_value, gd_type(member.element), value_type, field_name, catalog, parents)
                return

    if value_type == "PackedByteArray" or value_type.startswith("Dictionary"):
        scenario.body.extend([f"if {value}.is_empty():", "    return"])
    consumer_name = {
        "PackedByteArray": "load_file_bytes" if owner in {"SteamCloud", "SteamSharedCloudFile", "SteamCloudFile"}
        else "process_private_payload",
    }.get(value_type, f"apply_{subject}")
    consumer = scenario.input(consumer_name, "Callable")
    scenario.body.append(f"{consumer}.call({value})")


def use_outcome(scenario: Scenario, value: str, value_type: str, owner: str, name: str,
                catalog: dict, parents: dict[str, str]) -> None:
    """Handle a completion status and use its payload only after a successful result."""
    subject = member_subject(name)
    if value_type == "Error":
        if backend_workflow(owner):
            report_status = scenario.input("report_status", "Callable")
            scenario.body.extend([f"if {value} != OK:", f"    push_warning(error_string({value}))",
                                  "    return", f"{report_status}.call({value})"])
            return
        label = scenario.input("status_label", "Label")
        scenario.body.extend([f"if {value} != OK:", f"    {label}.text = error_string({value})", "    return",
                              f'{label}.text = "{name.replace("_", " ").capitalize()} accepted."'])
        return

    if value_type == "SessionTransportResult":
        scenario.body.extend([f"if {value} == null:", "    return", f"if {value}.get_error() != OK:",
                              f"    push_warning(error_string({value}.get_error()))", "    return"])
        peer = scenario.variable("peer", "MultiplayerPeer", f"{value}.get_peer()")
        install_peer = scenario.input("install_peer", "Callable")
        scenario.body.append(f"{install_peer}.call({peer})")
        return

    if is_steam_result(value_type, parents):
        reject_failed_result(scenario, value)
        payload = lookup(catalog, parents, value_type, "properties", "value")
        if payload is not None:
            payload_type = gd_type(payload.element)
            data = scenario.variable("payload", payload_type, f"{value}.value")
            use_value(scenario, data, payload_type, owner, subject, catalog, parents)
        elif backend_workflow(owner):
            on_success = scenario.input("record_completion", "Callable")
            scenario.body.append(f"{on_success}.call({value})")
        else:
            label = scenario.input("status_label", "Label")
            scenario.body.append(f'{label}.text = "{name.replace("_", " ").capitalize()} succeeded."')
        return

    use_value(scenario, value, value_type, owner, subject, catalog, parents)


def apply_configuration(scenario: Scenario, value: str, value_type: str) -> bool:
    """Apply common builder results to the actual object that consumes the configuration."""
    if value_type not in {"SteamProvider", "GameDefinition", "WorldSessionDefinition", "MultiplayerRules", "SteamServer"}:
        return False
    scenario.body.extend([f"if {value} == null:", "    return"])
    if value_type == "SteamProvider":
        definition = scenario.input("definition", "GameDefinition")
        game = scenario.input("game", "GameRuntime")
        scenario.body.extend(["# The provider is captured when GameRuntime enters the scene tree.",
                              f"if {game}.is_inside_tree():", "    return"])
        scenario.body.append(f"{game}.definition = {definition}.with_provider({value})")
    elif value_type == "GameDefinition":
        game = scenario.input("game", "GameRuntime")
        scenario.body.extend([f"if {game}.is_inside_tree():", "    return"])
        scenario.body.append(f"{game}.definition = {value}")
    elif value_type == "WorldSessionDefinition":
        session = scenario.input("session", "WorldSession")
        scenario.body.append(f"{session}.definition = {value}")
    elif value_type == "MultiplayerRules":
        definition = scenario.input("definition", "GameDefinition")
        scenario.body.append(f"{definition}.multiplayer_rules = {value}")
    else:
        provider = scenario.input("provider", "SteamProvider")
        definition = scenario.input("definition", "GameDefinition")
        game = scenario.input("game", "GameRuntime")
        scenario.body.extend(["# Set the dedicated provider before adding GameRuntime to the tree.",
                              f"if {game}.is_inside_tree():", "    return"])
        scenario.body.append(f"{game}.definition = {definition}.with_provider({provider}.dedicated({value}))")
    return True


def use_operation(scenario: Scenario, operation: str, operation_type: str, owner: str, name: str,
                  catalog: dict, parents: dict[str, str]) -> bool:
    """Await retained operations, preserving the documented completion payload type."""
    wait = lookup(catalog, parents, operation_type, "methods", "wait")
    if wait is None:
        return False
    scenario.body.extend([f"if {operation} == null:", "    return"])
    result_type = deferred_type(operation_type, "wait", wait.description, catalog, parents)
    value = scenario.variable("result", result_type, f"await {operation}.wait()")
    if operation_type == "GameOperation":
        label = scenario.input("status_label", "Label")
        scenario.body.extend([f'if not {value}.get("ok", false):',
                              f'    {label}.text = str({value}.get("message", "Operation failed."))',
                              "    return", f'{label}.text = "{name.replace("_", " ").capitalize()} completed."'])
    else:
        use_outcome(scenario, value, result_type, owner, name, catalog, parents)
    return True


def continue_with_method(scenario: Scenario, receiver: str, receiver_type: str, method: str,
                         subject: str, catalog: dict, parents: dict[str, str],
                         *, confirm: bool = False) -> bool:
    """Show a second public action on an acquired service or configured draft."""
    member = lookup(catalog, parents, receiver_type, "methods", method)
    if member is None:
        return False
    returns = member.element.find("return")
    if returns is None or gd_type(returns) == "void":
        return False
    scenario.body.extend([f"if {receiver} == null:", "    return"])
    if confirm:
        confirmed = scenario.input("confirmed", "bool")
        scenario.body.extend([f"if not {confirmed}:", "    return"])
    params = sorted(member.element.findall("param"), key=lambda item: int(item.attrib["index"]))
    arguments = [scenario.input(item.attrib["name"], gd_type(item)) for item in params if "default" not in item.attrib]
    value_type = gd_type(returns)
    deferred = value_type == "Variant"
    if deferred:
        value_type = deferred_type(receiver_type, method, member.description, catalog, parents)
    value = scenario.variable(subject, value_type, invoke(receiver, method, arguments, deferred=deferred))
    if value_type == "SteamWorkshopQuery" and method == "query":
        return continue_with_method(scenario, value, value_type, "fetch", "workshop_results", catalog, parents)
    if not use_operation(scenario, value, value_type, receiver_type, method, catalog, parents):
        use_outcome(scenario, value, value_type, receiver_type, subject, catalog, parents)
    return True


def use_builder(scenario: Scenario, value: str, value_type: str, name: str,
                catalog: dict, parents: dict[str, str]) -> bool:
    """Apply the returned branch of a configuration or complete a prepared draft."""
    if name == "configure" and value_type == "GameDefinition":
        world = scenario.input("world_id", "StringName")
        world_scene = scenario.input("world_scene", "PackedScene")
        player_scene = scenario.input("player_scene", "PackedScene")
        scenario.body.extend([f"{value} = {value}.with_starting_world({world}, {world_scene})",
                              f"{value} = {value}.with_player({player_scene})"])
    if apply_configuration(scenario, value, value_type):
        return True
    if value_type == "SteamLobbyOptions":
        client = scenario.input("steam_client", "SteamClient")
        confirmed = scenario.input("create_lobby_confirmed", "bool")
        scenario.body.extend([f"if {value} == null or not {client}.is_ready() or not {confirmed}:", "    return"])
        lobbies = scenario.variable("lobbies", "SteamLobbies", f"{client}.lobbies()")
        scenario.body.extend([f"if {lobbies} == null:", "    return"])
        operation = scenario.variable("operation", "SteamLobbyOperation", f"{lobbies}.create({value})")
        return use_operation(scenario, operation, "SteamLobbyOperation", "SteamLobbies", "create", catalog, parents)
    if value_type == "SteamHttpOptions":
        return continue_with_method(scenario, value, value_type, "fetch", "response", catalog, parents)
    commit = COMMIT_DRAFTS.get(value_type)
    return bool(commit and continue_with_method(scenario, value, value_type, commit, "completion", catalog, parents,
                                               confirm=commit == "submit"))


def prepare_draft(scenario: Scenario, value: str, value_type: str, name: str,
                  catalog: dict, parents: dict[str, str]) -> bool:
    """Use a new query or populate an empty draft with game-supplied data."""
    if name == "query" and value_type in COMMIT_DRAFTS:
        return continue_with_method(scenario, value, value_type, "fetch", "search_result", catalog, parents)

    if (name, value_type) not in {("save", "SaveRequest"), ("edit", "SteamStatsEdit"),
                                  ("edit", "SteamServerStatsEdit"), ("edit", "SteamLobbyEdit"),
                                  ("new_item", "SteamWorkshopPublishRequest")}:
        return False
    scenario.body.extend([f"if {value} == null:", "    return"])
    if value_type in {"SteamStatsEdit", "SteamServerStatsEdit"}:
        stat = scenario.input("stat_name", "StringName")
        total = scenario.input("new_total", "int")
        prepared = scenario.variable("staged_edit", value_type, f"{value}.set_int({stat}, {total})")
    else:
        title = scenario.input("display_name", "String")
        prepared = scenario.variable("named_draft", value_type, f"{value}.named({title})")
    if value_type == "SteamWorkshopPublishRequest":
        open_editor = scenario.input("open_publish_editor", "Callable")
        scenario.body.append(f"{open_editor}.call({prepared})")
        return True
    return continue_with_method(scenario, prepared, value_type, "submit", "completion", catalog, parents,
                                confirm=True)


def finish_void(scenario: Scenario, receiver: str, owner: str, name: str, catalog: dict,
                parents: dict[str, str]) -> None:
    """Update the caller after a state-changing method without a return value."""
    follow_up = {
        ("GameSession", "leave"): ("session_controls", "Control", "hide()"),
        ("SpatialInventorySorter", "cancel_preview"): ("preview_panel", "Control", "hide()"),
        ("StateReplication", "clear_projection"): ("projection_rows", "ItemList", "clear()"),
        ("StateReplication", "reset"): ("peer_rows", "ItemList", "clear()"),
        ("SteamBrowserPage", "close"): ("browser_panel", "Control", "hide()"),
        ("SteamClient", "stop"): ("steam_controls", "Control", "hide()"),
        ("SteamDiagnostics", "stop"): ("capture_indicator", "Control", "hide()"),
        ("SteamInput", "stop"): ("controller_rows", "ItemList", "clear()"),
    }.get((owner, name))
    if follow_up:
        input_name, input_type, action = follow_up
        control = scenario.input(input_name, input_type)
        scenario.body.append(f"{control}.{action}")
        return
    if lookup(catalog, parents, owner, "methods", "is_available"):
        if continue_with_method(scenario, receiver, owner, "is_available", "available", catalog, parents):
            return
    next_step = scenario.input(f"after_{name}", "Callable")
    scenario.body.append(f"{next_step}.call()")


def render_example(
    class_name: str,
    category: str,
    element: Element,
    description: str,
    overrides: dict[str, str],
    *,
    catalog: dict | None = None,
    factories: dict[str, tuple[str, str]] | None = None,
    parents: dict[str, str] | None = None,
) -> str:
    """Return an authored workflow or a typed example with a concrete next step."""
    name = element.attrib["name"]
    key = f"{class_name}.{category}.{name}"
    if key in overrides:
        return overrides[key].strip()

    catalog = catalog or {}
    factories = factories or {}
    parents = parents or {}
    scenario = Scenario()
    subject = member_subject(name)
    if category == "properties":
        value_type = gd_type(element)
        receiver = acquire_receiver(scenario, class_name, factories, catalog, parents)
        expression = f"{receiver}.{name}"
        if element.get("setter"):
            value = scenario.input(f"new_{subject}", value_type)
            assignment = f"{expression} = {value}"
            if apply_configuration(scenario, receiver, class_name):
                scenario.body.insert(-1, assignment)
            else:
                scenario.body.append(assignment)
                readback = scenario.variable(f"active_{subject}", value_type, expression)
                use_value(scenario, readback, value_type, class_name, subject, catalog, parents)
            action = f"update_{subject}"
        else:
            if name == "value" and is_steam_result(class_name, parents):
                reject_failed_result(scenario, receiver)
            value = scenario.variable(subject, value_type, expression)
            use_outcome(scenario, value, value_type, class_name, name, catalog, parents)
            action = f"refresh_{subject}"
    else:
        qualifiers = element.get("qualifiers", "").split()
        if "virtual" in qualifiers:
            raise ValueError(f"Write a GDScript override example for {key}.")
        target = class_name if "static" in qualifiers else acquire_receiver(scenario, class_name, factories, catalog, parents)
        if name == "get_value" and is_steam_result(class_name, parents):
            reject_failed_result(scenario, target)
        if (class_name, name) == ("SteamInventory", "consume"):
            confirmed = scenario.input("consumption_confirmed", "bool")
            scenario.body.extend([f"if not {confirmed}:", "    return"])
        params = sorted(element.findall("param"), key=lambda item: int(item.attrib["index"]))
        arguments = [scenario.input(param.attrib["name"], gd_type(param)) for param in params]
        returns = element.find("return")
        result_type = gd_type(returns) if returns is not None else "void"
        deferred = result_type == "Variant" and (not name.startswith("get_") or "await" in description.lower())
        expression = invoke(target, name, arguments, deferred=deferred)
        action = f"run_{name}"
        if result_type == "void":
            property_doc = next((prop for prop in catalog.get(class_name, {}).get("properties", {}).values()
                                 if prop.element.get("setter") == name), None)
            if apply_configuration(scenario, target, class_name):
                scenario.body[-1:-1] = expression.splitlines()
            else:
                scenario.body.extend(expression.splitlines())
                if property_doc is not None:
                    property_name = property_doc.element.attrib["name"]
                    property_type = gd_type(property_doc.element)
                    value = scenario.variable(f"active_{property_name}", property_type, f"{target}.{property_name}")
                    use_value(scenario, value, property_type, class_name, property_name, catalog, parents)
                else:
                    finish_void(scenario, target, class_name, name, catalog, parents)
        else:
            if deferred:
                result_type = deferred_type(class_name, name, description, catalog, parents)
            value = scenario.variable("result", result_type, expression)
            is_builder = "static" in qualifiers or result_type == class_name
            service = SERVICE_READS.get(result_type)
            handled = is_builder and use_builder(scenario, value, result_type, name, catalog, parents)
            if not handled:
                handled = prepare_draft(scenario, value, result_type, name, catalog, parents)
            if class_name == "SteamWebTicket" and name == "bytes":
                send_ticket(scenario, target, value)
                handled = True
            if not handled and service and (class_name, name) != ("SteamClient", "purchases"):
                handled = continue_with_method(scenario, value, result_type, *service, catalog, parents)
            if not handled:
                handled = use_operation(scenario, value, result_type, class_name, name, catalog, parents)
            if not handled:
                use_outcome(scenario, value, result_type, class_name, name, catalog, parents)

    return "extends Node\n\n" + function_example(action, scenario.parameters, "void", scenario.body)
