#!/usr/bin/env python3
"""Copy repaired structured event metadata from the master feed into split feeds."""
from pathlib import Path
import xml.etree.ElementTree as ET

MASTER_FEED = Path("docs/feed.xml")
SPLIT_GLOBS = ("docs/feeds/*.xml", "docs/categories/*.xml")
IFY_NS = "https://imfromyorkshire.uk.com/ns/events/1.0"
DC_NS = "http://purl.org/dc/elements/1.1/"
ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

ET.register_namespace("ify", IFY_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("atom", ATOM_NS)
ET.register_namespace("content", CONTENT_NS)

STRUCTURED_TAGS = (
    "pubDate",
    f"{{{IFY_NS}}}start",
    f"{{{IFY_NS}}}end",
    f"{{{IFY_NS}}}allDay",
    "location",
    f"{{{IFY_NS}}}location",
)


def item_key(item: ET.Element) -> str:
    return (item.findtext("link") or item.findtext("guid") or "").strip()


def metadata_map() -> dict[str, dict[str, str]]:
    tree = ET.parse(MASTER_FEED)
    result: dict[str, dict[str, str]] = {}
    for item in tree.getroot().findall("./channel/item"):
        key = item_key(item)
        if not key:
            continue
        values = {}
        for tag in STRUCTURED_TAGS:
            value = item.findtext(tag)
            if value:
                values[tag] = value
        result[key] = values
    return result


def set_text(parent: ET.Element, tag: str, value: str) -> None:
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = value


def update_file(path: Path, master: dict[str, dict[str, str]]) -> int:
    tree = ET.parse(path)
    changed = 0
    for item in tree.getroot().findall("./channel/item"):
        values = master.get(item_key(item))
        if not values:
            continue
        for tag, value in values.items():
            if item.findtext(tag) != value:
                set_text(item, tag, value)
                changed += 1
    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def main() -> int:
    if not MASTER_FEED.exists():
        print("Metadata propagation skipped: master feed missing")
        return 0
    master = metadata_map()
    files = []
    for pattern in SPLIT_GLOBS:
        files.extend(Path().glob(pattern))
    total = 0
    for path in files:
        changes = update_file(path, master)
        total += changes
        if changes:
            print(f"  propagated {changes} fields to {path}")
    print(f"Metadata propagation complete: {total} field updates across {len(files)} feeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
