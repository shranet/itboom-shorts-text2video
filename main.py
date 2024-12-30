import argparse
import hashlib
import itertools
import os
import random
from functools import cached_property
from pathlib import Path
from typing import List

import cv2
import requests
from PIL import ImageFont
from dotenv import load_dotenv
from markdown import Markdown
from moviepy import *

from effects.BgEffect import BgEffect
from effects.ImgEffect import ImgEffect

parser = argparse.ArgumentParser(prog='Text2Video', description='This app converts text to video.')
parser.add_argument("markdown_file")
parser.add_argument("--width", required=False, default=1080, type=int)
parser.add_argument("--height", required=False, default=1920, type=int)
parser.add_argument("--fps", required=False, default=30, type=int)
parser.add_argument("-a", "--audio-directory", required=False, default="./audio")
parser.add_argument("-o", "--output-directory", required=False, default="./output")
parser.add_argument("--bg-path", required=False, default="./assets/background")
parser.add_argument("--font-path", required=False, default="./assets/fonts")
parser.add_argument("--font-name", required=False, default="roboto")
parser.add_argument("--font-size", required=False, default=100, type=int)
parser.add_argument("--text-padding", required=False, default=50, type=int)

args = parser.parse_args()

FONT_HEIGHT = 0
SPACE_WIDTH = 0
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}

import re


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

    @property
    def clips(self):
        result = []
        for word in self.text.split():
            clip = TextClip(
                text=self.process_text(word, False),
                font=self.font,
                font_size=args.font_size,
                color="white",
                stroke_color="#000000",
                stroke_width=5,
                margin=(10, 10)
            )
            clip.ai_text = self.process_text(word, True)
            result.append(clip)
        return result

    def process_text(self, input_text, ai=True):
        def replace_pattern(match):
            normal_text = match.group(1)
            ai_text = match.group(2)
            return ai_text if ai else normal_text

        pattern = r"(\w+)@ai\((\w+)\)"
        processed_text = re.sub(pattern, replace_pattern, input_text)

        return processed_text


class ContentImage:
    def __init__(self, file, alt):
        self.alt = alt
        self.file = file

    @cached_property
    def clip(self):
        clip = ImageClip(self.file, duration=10).with_position('center', 'center')

        margin = 20
        target_width, target_height = args.width - 2 * margin, args.height - 2 * margin
        target_aspect = target_width / target_height
        clip_aspect = clip.w / clip.h

        if clip_aspect > target_aspect:
            clip = clip.resized(width=target_width)
        else:
            clip = clip.resized(height=target_height)

        return clip


class ContentPage:
    WIDTH = args.width - 2 * args.text_padding
    HEIGHT = args.height // 2

    def __init__(self):
        self.is_image = False
        self.clips: List[List[TextClip|ImageClip|str]] = [[]]
        self.__height = FONT_HEIGHT
        self.__line_width = 0
        self.__audio = None

    @property
    def audio(self):
        return self.__audio

    @audio.setter
    def audio(self, audio):
        self.__audio = audio

        if self.is_image:
            clip, alt = self.clips[0]
            self.clips[0] = [clip.with_duration(audio.duration)]
            return

        total_letters = 0
        for line_clips in self.clips:
            for clip in line_clips:
                total_letters += len(clip.text)

        if total_letters == 0:
            return

        per_letter_time = audio.duration / total_letters
        for i, line_clips in enumerate(self.clips):
            for j, clip in enumerate(line_clips):
                duration = len(clip.text) * per_letter_time
                self.clips[i][j] = clip.with_duration(duration)


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

    def calculate_positions(self):
        height = FONT_HEIGHT * len(self.clips) # FH * LINES
        pos_y = (args.height - height) / 2 + FONT_HEIGHT / 2
        for i, line_clips in enumerate(self.clips):
            line_width = 0
            for clip in line_clips:
                line_width += clip.size[0] + SPACE_WIDTH

            if line_width > 0: line_width -= SPACE_WIDTH

            pos_x = (args.width - line_width) / 2
            for j, clip in enumerate(line_clips):
                self.clips[i][j] = clip.with_position((pos_x, pos_y - clip.size[1] / 2))
                pos_x += clip.size[0] + SPACE_WIDTH

            pos_y += FONT_HEIGHT

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
                    is_bold="strong" in tags,
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

        if elm.tail:
            content.add_text(ContentText(
                text=elm.tail,
                is_bold="strong" in tags,
                is_italic="em" in tags,
                is_code="code" in tags
            ))

    walk(root, [])

    return content

def load_audio(short: ContentShort):
    offset = 0
    for page in short.pages: # type: ContentPage
        if page.is_image:
            text = page.clips[0][1]
        else:
            lines = []
            for line in page.clips:
                lines.append(" ".join(map(lambda c: c.ai_text, line)))

            text = " ".join(lines)

        audio_file = os.path.join("./audio", hashlib.md5(text.encode('utf-8')).hexdigest() + ".mp3")
        if os.path.exists(audio_file):
            page.audio = AudioFileClip(audio_file).with_start(offset)
            offset += page.audio.duration
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

        page.audio = AudioFileClip(audio_file).with_start(offset)
        offset += page.audio.duration


def render_short(short: ContentShort, bg_image):
    print(f"Render {short.name} ... ", end="")
    output_file = os.path.join(args.output_directory, short.name + ".mp4")
    if os.path.exists(output_file):
        print("already exists")
        return

    audio_clips, video_clips = [], []
    duration = 0
    offset = 0
    color_padding = 20

    def color_pos(pos_fn):
        def calc(t):
            pos = pos_fn(t)
            return pos[0] - color_padding / 2, pos[1] - color_padding / 2

        return calc

    for page in short.pages:
        page.calculate_positions()

        for line_clips in page.clips:
            for clip in line_clips:
                video_clips.append(ColorClip(
                    (clip.size[0] + color_padding, clip.size[1] + color_padding),
                    (255, 111, 6)
                ).with_layer_index(1).with_start(offset).with_duration(
                    clip.duration
                ).with_position(color_pos(clip.pos)))

                offset += clip.duration

                video_clips.append(clip.with_start(duration).with_layer_index(2).with_duration(
                    page.audio.duration
                ))


        audio_clips.append(page.audio)
        duration += page.audio.duration

    background = ImageClip(bg_image, duration=duration).with_effects([
        BgEffect(width=args.width, height=args.height, duration=duration)
    ])

    for i, clip in enumerate(video_clips):
        if type(clip) == ImageClip:
            print("Found img", i)
            video_clips[i] = clip.with_effects([ImgEffect(background)])

    video = CompositeVideoClip([background, *video_clips])
    video.audio = CompositeAudioClip(audio_clips)
    video.write_videofile(output_file, fps=args.fps, codec='libx264', audio_codec="aac")


def main():
    content = parse_markdown(args.markdown_file)

    p = Path(args.bg_path)
    bg_files = list(sorted([str(f.resolve()) for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()]))

    for short in content.shorts:
        load_audio(short)
        render_short(short, random.choice(bg_files))


if __name__ == "__main__":
    load_dotenv(".env.production")

    FONT_HEIGHT = ContentText.get_font_max_height()
    # SPACE_WIDTH = TextClip(
    #     text=" ",
    #     font=ContentText.get_font_path(True, False, False),
    #     font_size=args.font_size
    # ).size[0]
    main()
