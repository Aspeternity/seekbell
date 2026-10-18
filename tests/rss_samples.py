from xml.etree.ElementTree import Element, SubElement, tostring

from httpx import AsyncByteStream

DC = "http://purl.org/dc/elements/1.1/"


def rss(items=()):
    root = Element("rss", version="2.0")
    channel = SubElement(root, "channel")
    for tag, text in (
        ("title", "SeekBell synthetic feed"),
        ("link", "https://www.nodeseek.com/"),
        ("description", "Synthetic test data"),
    ):
        SubElement(channel, tag).text = text
    for value in items:
        item = SubElement(channel, "item")
        fields = {
            "guid": value.get("guid", str(value["id"])),
            "title": value.get("title", "Synthetic title"),
            "link": value.get("link", f"https://www.nodeseek.com/post-{value['id']}-1"),
            "description": value.get("summary"),
            f"{{{DC}}}creator": value.get("author", "fixture-user"),
            "category": value.get("category", "fixture-section"),
            "pubDate": value.get("published", "Sun, 18 Oct 2026 12:00:00 GMT"),
        }
        for tag, text in fields.items():
            if text is None:
                continue
            child = SubElement(item, tag)
            if tag == "guid":
                child.set("isPermaLink", "false")
            child.text = text
    return tostring(root, encoding="utf-8", xml_declaration=True)


class Chunks(AsyncByteStream):
    def __init__(self, *parts):
        self.parts = parts
        self.closed = False

    async def __aiter__(self):
        for part in self.parts:
            yield part

    async def aclose(self):
        self.closed = True
