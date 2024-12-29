import argparse
import hashlib
import itertools
import os
from functools import cached_property
from typing import List

import numpy as np
import cv2
import requests
from dotenv import load_dotenv

from PIL import Image, ImageFont, ImageDraw
from markdown import Markdown
from moviepy import *

parser = argparse.ArgumentParser(prog='Text2Video', description='This app converts text to video.')
parser.add_argument("markdown_file")
parser.add_argument("--width", required=False, default=1080, type=int)
parser.add_argument("--height", required=False, default=1920, type=int)
parser.add_argument("--fps", required=False, default=30, type=int)
parser.add_argument("-a", "--audio-directory", required=False, default="./audio")
parser.add_argument("-o", "--output-directory", required=False, default="./output")
parser.add_argument("--font-path", required=False, default="./assets")
parser.add_argument("--font-name", required=False, default="roboto")
parser.add_argument("--font-size", required=False, default=100, type=int)
parser.add_argument("--text-padding", required=False, default=20, type=int)

args = parser.parse_args()

FONT_HEIGHT = 0
SPACE_WIDTH = 0

class ContentText:
    def __init__(self, text, is_bold=False, is_italic=False, is_code=False):
        self.inline = "\n" not in text
        self.text = text
        self.font = self.get_font_path(is_bold, is_italic, is_code)

    @classmethod
    def get_font_max_height(cls):
        all_combos = list(itertools.product([False, True], repeat=3))

        max_height = 0
        for is_bold, is_italic, is_code in all_combos:
            height = cls.get_font_height(is_bold, is_italic, is_code)
            if height > max_height:
                max_height = height
        return max_height

    @classmethod
    def get_font_height(cls, is_bold=False, is_italic=False, is_code=False):
        font = ImageFont.truetype(cls.get_font_path(is_bold, is_italic, is_code), size=args.font_size)
        ascent, descent = font.getmetrics()
        return ascent + descent

    @staticmethod
    def get_font_path(is_bold=False, is_italic=False, is_code=False):
        font_file_name = [
            args.font_name
        ]
        if is_code:
            font_file_name.append("mono")

        if is_bold:
            font_file_name.append("bold")

        if is_italic:
            font_file_name.append("italic")

        return os.path.join(args.font_path, "-".join(font_file_name) + ".ttf")

    @cached_property
    def clips(self):
        result = []
        for word in self.text.split():
            result.append(TextClip(
                text=word,
                font=self.font,
                font_size=args.font_size,
            ))
        return result


class ContentImage:
    def __init__(self, file, alt):
        self.alt = alt
        self.file = file

    @staticmethod
    def resize_contain(img, margin=0):
        width, height, _ = img.shape
        original_aspect = width / height
        target_aspect = args.width / args.height

        if original_aspect > target_aspect:
            new_width = args.width - 2 * margin
            new_height = int((args.width - 2 * margin) / original_aspect)
        else:
            new_height = args.height - 2 * margin
            new_width = int((args.height - 2 * margin) * original_aspect)

        return cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)

    @cached_property
    def clip(self):
        # calc duration
        return ImageClip(self.file, duration=10)


class ContentPage:
    WIDTH = args.width - 2 * args.text_padding
    HEIGHT = args.height // 2

    def __init__(self):
        self.audio = None
        self.is_image = False
        self.clips = [[]]
        self.__height = FONT_HEIGHT
        self.__line_width = 0

    def add_text_clips(self, clips: List[TextClip]):
        while clips:
            clip = clips.pop(0)
            if self.__line_width + clip.size[0] > self.WIDTH:
                if self.__height >= self.HEIGHT:
                    clips.insert(0, clip)
                    return True

                self.clips.append([])
                self.__height += FONT_HEIGHT
                self.__line_width = 0

            self.clips[-1].append(clip)
            self.__line_width += clip.size[0]

        return False

    def add_image_clip(self, clip: ImageClip, alt: str):
        self.is_image = True
        self.clips[-1].append(clip)
        self.clips[-1].append(alt)
        self.__height = clip.size[1]

    @property
    def height(self):
        return self.__height

    def __len__(self):
        return len(self.clips)


class ContentShort:
    def __init__(self, name):
        self.name = name
        self.pages = []

    def add_text(self, text: ContentText):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        clips = text.clips
        while clips:
            if self.pages[-1].add_text_clips(clips):
                self.pages.append(ContentPage())

    def add_image(self, img: ContentImage):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        if len(self.pages[-1]) > 0:
            self.pages.append(ContentPage())

        self.pages[-1].add_image_clip(img.clip, img.alt)
        self.pages.append(ContentPage())


class Content:
    def __init__(self):
        self.shorts = []

    def add_short(self, name):
        self.shorts.append(ContentShort(name))

    def add_text(self, text: ContentText):
        if len(self.shorts) == 0:
            self.add_short()

        self.shorts[-1].add_text(text)

    def add_image(self, img: ContentImage):
        if len(self.shorts) == 0:
            self.add_short()

        self.shorts[-1].add_image(img)


def parse_markdown(filename):
    md = Markdown(extensions=["attr_list"])

    with open(filename, "r") as f:
        source = f.read()

    md.lines = source.split("\n")
    for prep in md.preprocessors:
        md.lines = prep.run(md.lines)

    root = md.parser.parseDocument(md.lines).getroot()

    for treeprocessor in md.treeprocessors:
        newRoot = treeprocessor.run(root)
        if newRoot is not None:
            root = newRoot

    content = Content()

    def walk(elm, tags):
        tags.append(elm.tag)

        text = elm.text.strip() if elm.text is not None else ""
        if elm.tag == "h1":
            content.add_short(elm.text)
        else:
            if text:
                content.add_text(ContentText(
                    text=text,
                    is_bold="string" in tags,
                    is_italic="em" in tags,
                    is_code="code" in tags
                ))

            if elm.tag == "img":
                content.add_image(ContentImage(
                    file=os.path.join(os.path.dirname(args.markdown_file), elm.attrib.get("src")),
                    alt=elm.attrib.get("alt", "")
                ))

        for child in elm:
            walk(child, tags)

        if elm.tail:
            content.add_text(ContentText(
                text=elm.tail,
                is_bold="string" in tags,
                is_italic="em" in tags,
                is_code="code" in tags
            ))

        tags.pop()

    walk(root, [])

    return content

def load_audio(short: ContentShort):
    for page in short.pages: # type: ContentPage
        if page.is_image:
            text = page.clips[0][1]
        else:
            lines = []
            for line in page.clips:
                lines.append(" ".join(map(lambda c: c.text, line)))

            text = " ".join(lines)

        audio_file = os.path.join("./audio", hashlib.md5(text.encode('utf-8')).hexdigest() + ".mp3")
        if os.path.exists(audio_file):
            page.audio = AudioFileClip(audio_file)
            continue

        req = requests.post(
            "https://back.aisha.group/api/v1/tts/post/",
            data={
                "transcript": text,
                "language": "uz",
                "run_diarization": "false",
                "model": "jaxongir"
            },
            headers={
                "x-api-key": os.getenv('AISHA_TOKEN'),
                "X-Channels": "stereo",
                "X-Quality": "64k",
                "X-Rate": "16000",
                "X-Format": "mp3"
            }
        )

        audio_path = req.json()["audio_path"]
        response = requests.get("https://back.aisha.group" + audio_path, stream=True)

        # Check if the request was successful
        if response.status_code == 200:
            # Save the file locally
            with open(audio_file, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            print(f"File downloaded and saved as {audio_file}")

        page.audio = AudioFileClip(audio_file)


def render_short(short: ContentShort):
    print(f"Render {short.name} ... ", end="")
    output_file = os.path.join(args.output_directory, short.name + ".mp4")
    if os.path.exists(output_file):
        print("already exists")
        return

    duration = 0
    for page in short.pages:
        duration += page.audio.duration

    def make_frame(t):
        # im = Image.fromarray(background.get_frame(t))
        im = Image.new("RGB", (args.width, args.height), color=(255, 255, 255))
        draw = ImageDraw.Draw(im)

        return np.array(im, dtype=np.uint8)

    clip = VideoClip(make_frame, duration=duration)  # 5 soniyali video

    clip.write_videofile(output_file, fps=args.fps, codec='libx264')


def main():
    content = parse_markdown(args.markdown_file)
    for short in content.shorts:
        load_audio(short)
        render_short(short)

if __name__ == "__main__":
    load_dotenv(".env.production")

    FONT_HEIGHT = ContentText.get_font_max_height()
    SPACE_WIDTH = TextClip(
        text=" ",
        font=ContentText.get_font_path(True, False, False),
        font_size=args.font_size
    ).size[0]
    main()
