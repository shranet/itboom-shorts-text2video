import argparse
import os
from functools import cached_property
from typing import List

import numpy as np
import cv2

from PIL import Image, ImageFont
from markdown import Markdown
from moviepy import *

parser = argparse.ArgumentParser(prog='Text2Video', description='This app converts text to video.')
parser.add_argument("markdown_file")
parser.add_argument("--width", required=False, default=1080, type=int)
parser.add_argument("--height", required=False, default=1920, type=int)
parser.add_argument("--fps", required=False, default=30, type=int)
parser.add_argument("-o", "--output-directory", required=False, default=".")
parser.add_argument("--font-path", required=False, default="./assets")
parser.add_argument("--font-name", required=False, default="roboto")
parser.add_argument("--font-size", required=False, default=80, type=int)
parser.add_argument("--text-padding", required=False, default=20, type=int)

args = parser.parse_args()

FONT_HEIGHT = 0

# font = ImageFont.truetype(args.font, self.size)
# ascent, descent = font.getmetrics()
# line_height = ascent + descent

class ContentText:
    def __init__(self, text, is_bold=False, is_italic=False, is_code=False):
        self.inline = "\n" not in text
        self.text = text
        self.font = self.get_font_path(is_bold, is_italic, is_code)

    @s
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
    def __init__(self):
        self.clips = []
        self.__width = args.width - 2 * args.text_padding
        self.__height = 0

    def add_clips(self, clips: List[TextClip]):
        self.clips.append([])
        line_width = 0
        while clips:
            clip = clips.pop(0)
            if line_width + clip.size[0]:
                pass
        pass

    def add_clip(self, clip: TextClip):
        self.clips.append(clip)
        self.__height += clip.size[1]

    @property
    def height(self):
        return self.__height

    def __len__(self):
        return len(self.clips)


class ContentShort:
    def __init__(self):
        self.pages = []

    def add_text(self, text: ContentText):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        clips = text.clips
        while clips:
            self.pages[-1].add_clips(clips)
            self.pages.append(ContentPage())

    def add_image(self, img: ContentImage):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        if len(self.pages[-1]) > 0:
            self.pages.append(ContentPage())

        self.pages[-1].add_clip(img.clip)
        self.pages.append(ContentPage())


class Content:
    def __init__(self):
        self.shorts = []

    def add_short(self):
        self.shorts.append(ContentShort())

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
        # child_count = len(elm)

        text = elm.text.strip() if elm.text is not None else ""
        if elm.tag == "hr":
            content.add_short()
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

        tags.pop()

    walk(root, [])

    return content


def main():
    content = parse_markdown(args.markdown_file)

if __name__ == "__main__":
    main()
