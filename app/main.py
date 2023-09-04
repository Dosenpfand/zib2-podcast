from dataclasses import field
import os
import re
from typing import List, Literal, Optional
import typing
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl
from pydantic_xml import BaseXmlModel, attr, element
from yt_dlp import YoutubeDL
import requests
from fastapi import BackgroundTasks, FastAPI, Request, Response


class Enclosure(BaseXmlModel):
    url: HttpUrl = attr()
    length: int = attr()
    type: Literal["audio/x-m4a"] = attr(default="audio/x-m4a")


class Item(BaseXmlModel):
    title: str = element()
    enclosure: Enclosure = element()


ns_map = dict(
    itunes="http://www.itunes.com/dtds/podcast-1.0.dtd",
    content="http://purl.org/rss/1.0/modules/content/",
)


class Channel(BaseXmlModel, nsmap=ns_map):
    title: str = element()
    description: str = element()
    image: HttpUrl = element(ns="itunes")
    language: str = element()
    category: str = element(ns="itunes")
    explicit: bool = element(ns="itunes", default=False)
    link: HttpUrl = element()
    items: Optional[List[Item]] = element(tag="item", default=None)


class Rss(BaseXmlModel, tag="rss", nsmap=ns_map):
    channel: Optional[Channel] = field()
    version: float = attr(default=2.0)


ZIB2_FEED = Rss(
    channel=Channel(
        title="ZIB 2 Podcast",
        description="ORF ZIB 2 Podcast",
        image="https://tv.orf.at/zib2/zib2-neu100~_v-epg__large__16__9_-5412e775eb65789c908def5fa9fdf24a7b895a8f.jpg",
        language="de-at",
        category="Daily News",
        link="https://tvthek.orf.at/profile/ZIB-2/1211/episodes",
    )
)

YTDL_OPTS = {
    "outtmpl": "%(id)s.%(ext)s",
    "paths": {"home": "./static", "temp": "/tmp"},
    "overwrites": False,
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

    for _, url in urls.items():
        regex = r'<span class="date">(?P<date>.+)</span>'
        request = requests.get(url)
        match = re.search(regex, request.text)

        ytdl_opts = YTDL_OPTS.copy()
        ytdl_opts["outtmpl"] = f"%(id)s-{match.group('date').replace(' ', '_')}.%(ext)s"
        with YoutubeDL(ytdl_opts) as ydl:
            ydl.download([url])


def get_episode_urls():
    program_url = "https://tvthek.orf.at/profile/ZIB-2/1211/episodes"
    regex = r"https://tvthek\.orf\.at/profile/ZIB-2/1211/ZIB-2/(?P<id>\d+)"
    request = requests.get(program_url)
    matches = re.finditer(regex, request.text)
    urls = {match.group("id"): match.group() for match in matches}
    return urls


class XmlResponse(Response):
    media_type = "application/xml"

    def __init__(
        self,
        content: typing.Any = None,
        status_code: int = 200,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        media_type: typing.Optional[str] = None,
        background: typing.Optional[BackgroundTasks] = None,
    ) -> None:
        super().__init__(content, status_code, headers, media_type, background)

    def render(self, content: type[BaseXmlModel]) -> bytes:
        return content.to_xml(encoding="utf-8", xml_declaration=True)


app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=XmlResponse)
async def podcast(request: Request):
    print(request.url.components)

    filenames = os.listdir("app/static/")
    items = []
    for filename in filenames:
        if len(filename.split("-")) != 2:
            continue
        (_, date_enc) = filename.split("-")
        date = date_enc.replace("_", " ")
        size = os.path.getsize(f"app/static/{filename}")
        item = Item(
            title=date,
            enclosure=Enclosure(
                url=f"{request.url.components.scheme}://{request.url.components.netloc}/static/{filename}",
                length=size,
            ),
        )
        items.append(item)
    rss = ZIB2_FEED
    rss.channel.items = items

    return XmlResponse(rss)


if __name__ == "__main__":
    download_all()
