import os
import re
from typing import List, Literal, Optional
from pydantic import HttpUrl
from pydantic_xml import BaseXmlModel, attr, element
from fastapi.staticfiles import StaticFiles
from fastapi_restful.tasks import repeat_every
from yt_dlp import YoutubeDL
import requests
from fastapi import FastAPI, Request, Response
import logging

LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logging.basicConfig(level=LOGLEVEL)

ns_map = dict(
    itunes="http://www.itunes.com/dtds/podcast-1.0.dtd",
    content="http://purl.org/rss/1.0/modules/content/",
)


class Enclosure(BaseXmlModel):
    url: HttpUrl = attr()
    length: int = attr()
    type: Literal["audio/x-m4a"] = attr(default="audio/x-m4a")


class Item(BaseXmlModel):
    title: str = element()
    enclosure: Enclosure = element()


class Image(BaseXmlModel):
    href: HttpUrl = attr(ns="itunes")


class Category(BaseXmlModel):
    text: str = attr(ns="itunes")
    category: Optional["Category"] = element(default=None)


class Channel(BaseXmlModel, nsmap=ns_map):
    title: str = element()
    description: str = element()
    image: Image = element(ns="itunes")
    language: str = element()
    category: Category = element(ns="itunes")
    explicit: bool = element(ns="itunes", default=False)
    link: HttpUrl = element()
    items: Optional[List[Item]] = element(tag="item", default=None)


class Rss(BaseXmlModel, tag="rss", nsmap=ns_map):
    channel: Optional[Channel] = element()
    version: float = attr(default=2.0)


ZIB2_FEED = Rss(
    channel=Channel(
        title="ZIB 2 - Ganze Sendung",
        description="Gesamtausgaben der ORF ZIB 2",
        image=Image(
            href="https://podcast.orf.at/podcast/tv/tv_zib2/tv_zib2_premium.png"
        ),
        language="de-at",
        category=Category(text="News", category=Category(text="Daily News")),
        link="https://tvthek.orf.at/profile/ZIB-2/1211/episodes",
    )
)

YTDL_OPTS = {
    "outtmpl": "%(id)s.%(ext)s",
    "paths": {"home": "app/static", "temp": "/tmp"},
    "overwrites": False,
    "concurrent_fragment_downloads": 5,
    "postprocessors": [
        {
            "key": "FFmpegConcat",
            "only_multi_video": False,
            "when": "playlist",
        },
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": 0,
            "nopostoverwrites": False,
        },
    ],
}


def download_all():
    urls = get_episode_urls()

    for id, url in urls.items():
        logging.info(f"Processing: {url}")

        request = requests.get(url)

        uncomplete_regex = r"segments_complete(&quot;)?\s*:\s*false"
        if re.search(uncomplete_regex, request.text):
            logging.info(f"Skipping uncomplete: {url}")
            continue

        date_regex = r'<span class="date">(?P<date>.+)</span>'
        date_match = re.search(date_regex, request.text)
        if not date_match:
            logging.warning(f"Skipping without a date: {url}")
            continue

        date_encoded = date_match.group("date").replace(" ", "_")
        filename_template = f"%(id)s-{date_encoded}.%(ext)s"

        if os.path.exists(
            os.path.join("app", "static", filename_template % {"id": id, "ext": "m4a"})
        ):
            logging.info(f"Skipping existing: {url}")
            continue

        logging.info(f"Downloading: {url}")
        ytdl_opts = YTDL_OPTS.copy()
        ytdl_opts["outtmpl"] = filename_template
        with YoutubeDL(ytdl_opts) as ydl:
            ydl.download([url])


def get_episode_urls():
    program_url = "https://tvthek.orf.at/profile/ZIB-2/1211/episodes"
    regex = r"https://tvthek\.orf\.at/profile/ZIB-2/1211/ZIB-2/(?P<id>\d+)"
    request = requests.get(program_url)
    matches = re.finditer(regex, request.text)
    urls = {match.group("id"): match.group() for match in matches}
    logging.info(f"Got episode urls: {urls}")
    return urls


class XmlResponse(Response):
    media_type = "application/xml"

    def render(self, content: type[BaseXmlModel]) -> bytes:
        return content.to_xml(encoding="utf-8", xml_declaration=True)


app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.head("/", response_class=XmlResponse)
@app.get("/", response_class=XmlResponse)
async def podcast(request: Request):
    dirlist = list(os.scandir("app/static/"))
    dirlist.sort(reverse=True, key=lambda x: x.name)
    items = []

    if dirlist:
        for entry in dirlist:
            if not entry.name.endswith(".m4a"):
                continue
            (_, date_enc) = entry.name[:-4].split("-")
            title = f"ZIB 2 - {date_enc.replace('_', ' ')}"
            item = Item(
                title=title,
                enclosure=Enclosure(
                    url=f"{request.url.components.scheme}://{request.url.components.netloc}/static/{entry.name}",
                    length=entry.stat().st_size,
                ),
            )
            items.append(item)
    rss = ZIB2_FEED
    rss.channel.items = items

    return XmlResponse(rss)


@app.on_event("startup")
@repeat_every(seconds=5 * 60)
def download_all_task() -> None:
    download_all()


if __name__ == "__main__":
    download_all()
