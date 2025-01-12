import argparse
import hashlib
import itertools
import os
import random
import re
import datetime
import subprocess

from functools import cached_property
from pathlib import Path
from typing import List

import requests
from PIL import ImageFont
from dotenv import load_dotenv
from markdown import Markdown
from moviepy import *
from urllib3.util.ssl_match_hostname import match_hostname

from effects.AlphaEffect import AlphaEffect
from effects.BgEffect import BgEffect

parser = argparse.ArgumentParser(prog='Text2Video', description='This app converts text to video.')
parser.add_argument("markdown_file")
parser.add_argument("--width", required=False, default=1080, type=int)
parser.add_argument("--height", required=False, default=1920, type=int)
parser.add_argument("--fps", required=False, default=30, type=int)
parser.add_argument("-a", "--audio-directory", required=False, default="./audio")
parser.add_argument("-c", "--code-directory", required=False, default="./code")
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
SHORT_DELAY = 0.5
AUDIO_MODEL = "jaxongir"

class ContentText:
    def __init__(self, text, is_bold=False, is_italic=False):
        self.text = text
        self.font = self.get_font_path(is_bold, is_italic)

    @classmethod
    def get_font_max_height(cls):
        all_combos = list(itertools.product([False, True], repeat=2))

        max_height = 0
        for is_bold, is_italic in all_combos:
            height = cls.get_font_height(is_bold, is_italic)
            if height > max_height:
                max_height = height
        return max_height

    @classmethod
    def get_font_height(cls, is_bold=False, is_italic=False):
        font = ImageFont.truetype(cls.get_font_path(is_bold, is_italic), size=args.font_size)
        ascent, descent = font.getmetrics()
        return ascent + descent

    @staticmethod
    def get_font_path(is_bold=False, is_italic=False):
        font_file_name = [
            args.font_name
        ]

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

        pattern = r"(\w+)@ai\(([^)]+)\)"
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


class ContentCode(ContentImage):
    FILE_EXT = {
        "c": ".c",
        "python": ".py"
    }

    def __init__(self, code):
        lines = code.splitlines()
        language = lines.pop(0).lower()
        if language not in self.FILE_EXT:
            raise Exception(f"{language} not allowed")

        pattern = r".*@ai\(([^)]+)\).*"
        alt = []
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            m = re.match(pattern, line)
            if not m:
                continue

            lines.pop(i)
            alt.append(m.group(1))

        if not alt:
            alt.append("dastur kodi")

        source = "\n".join(lines)
        code_file_name = hashlib.md5(source.encode('utf-8')).hexdigest()
        code_file = os.path.join(args.code_directory, code_file_name + ".png")
        if not os.path.exists(code_file):
            example_file_name = f"code{self.FILE_EXT[language]}"
            with open(example_file_name, "w") as f:
                f.write(source)

            subprocess.run([
                "carbon-now",
                example_file_name,
                "--save-to",
                args.code_directory, "--save-as",
                code_file_name, "--config", "./carbon-config.json"
            ])

            os.remove(example_file_name)

        super().__init__(code_file, "\n".join(alt))


class ContentPage:
    WIDTH = args.width - 2 * args.text_padding
    HEIGHT = args.height // 2

    def __init__(self):
        self.is_image = False
        self.with_audio = True
        self.clips: List[List[TextClip | ImageClip | str]] = [[]]
        self.__height = FONT_HEIGHT
        self.__line_width = 0
        self.__audio = None

    @property
    def duration(self):
        return self.clips[0][0].duration + SHORT_DELAY

    def set_duration(self, duration):
        for i, line_clip in enumerate(self.clips):
            for j, clip in enumerate(line_clip):
                self.clips[i][j] = clip.with_duration(duration)

        self.with_audio = False

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
        height = FONT_HEIGHT * len(self.clips)  # FH * LINES
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
        if not self.clips:
            return 0

        return len(self.clips[0])


class ContentShort:
    def __init__(self, name):
        self.name = name
        self.pages = []

        self.add_text(ContentText(name.upper()))
        for page in self.pages:
            page.set_duration(2)

        self.pages.append(ContentPage())

    def add_text(self, text: ContentText):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        if self.pages[-1].is_image:
            self.pages.append(ContentPage())

        clips = text.clips
        while clips:
            if self.pages[-1].add_text_clips(clips):
                self.pages.append(ContentPage())

    def add_image(self, img: ContentImage | ContentCode):
        if len(self.pages) == 0:
            self.pages.append(ContentPage())

        if len(self.pages[-1]) > 0:
            self.pages.append(ContentPage())

        self.pages[-1].add_image_clip(img.clip, img.alt)


class Content:
    def __init__(self):
        self.shorts = []

    def add_short(self, name):
        self.shorts.append(ContentShort(name))

    def add_text(self, text: ContentText):
        self.shorts[-1].add_text(text)

    def add_image(self, img: ContentImage | ContentCode):
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
                is_code = "code" in tags
                inline = "\n" not in text
                if is_code and not inline:
                    content.add_image(ContentCode(text))
                else:
                    content.add_text(ContentText(
                        text=text,
                        is_bold="strong" in tags,
                        is_italic="em" in tags
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
            tail = elm.tail.strip()
            if tail:
                is_code = "code" in tags
                inline = "\n" not in tail
                if is_code and not inline:
                    content.add_image(ContentCode(tail))
                else:
                    content.add_text(ContentText(
                        text=tail,
                        is_bold="strong" in tags,
                        is_italic="em" in tags
                    ))

    walk(root, [])

    return content


def load_audio(short: ContentShort):
    offset = SHORT_DELAY
    for page in short.pages:  # type: ContentPage
        if not page.with_audio:
            offset += page.duration
            continue

        if page.is_image:
            text = page.clips[0][1]
        else:
            lines = []
            for line in page.clips:
                lines.append(" ".join(map(lambda c: c.ai_text, line)))

            text = " ".join(lines)

        audio_file = os.path.join("./audio", AUDIO_MODEL + "-" + hashlib.md5(text.encode('utf-8')).hexdigest() + ".mp3")
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
                "model": AUDIO_MODEL
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
    output_file = os.path.join(args.output_directory, AUDIO_MODEL + " - " + short.name + ".mp4")
    if os.path.exists(output_file):
        print("already exists")
        return

    audio_clips, video_clips = [], []
    offset = duration = SHORT_DELAY
    color_padding = (20, 10)

    def color_pos(pos_fn):
        def calc(t):
            pos = pos_fn(t)
            return pos[0] - color_padding[0] / 2, pos[1] - color_padding[1] / 2

        return calc

    for page in short.pages:
        page.calculate_positions()

        for line_clips in page.clips:
            for clip in line_clips:
                if page.with_audio:
                    color_duration = clip.duration + 0.1
                    video_clips.append(ColorClip(
                        (clip.size[0] + color_padding[0], clip.size[1] + color_padding[1]),
                        color=(255, 111, 6)
                    ).with_layer_index(1).with_start(offset - 0.1).with_duration(
                        color_duration
                    ).with_position(color_pos(clip.pos)))

                    video_clips.append(clip.with_start(duration).with_layer_index(2).with_duration(
                        page.audio.duration
                    ))

                    offset += clip.duration
                else:
                    video_clips.append(clip.with_start(duration).with_layer_index(2))

        if not page.with_audio:
            duration += page.duration
            offset += page.duration
        else:
            audio_clips.append(page.audio)
            duration += page.audio.duration

    logo = ImageClip(
        img="./assets/itboom-uz-logo-white.png",
        duration=duration + SHORT_DELAY,
    ).with_position(("center", 50))

    footer = TextClip(
        text=f"{datetime.date.today().year} © itboom.uz",
        text_align="center",
        font=ContentText.get_font_path(True, False),
        font_size=50,
        color="black",
        stroke_color="white",
        stroke_width=3,
        margin=(50, 50),
        duration=duration + SHORT_DELAY,
    ).with_position(("center", "bottom"))

    background = ImageClip(bg_image, duration=duration + SHORT_DELAY).with_effects([
        BgEffect(width=args.width, height=args.height, duration=duration + SHORT_DELAY)
    ])

    for i, clip in enumerate(video_clips):
        if type(clip) in {ImageClip, ColorClip}:
            video_clips[i] = clip.with_effects([AlphaEffect(background)])

    video = CompositeVideoClip([background, logo, footer, *video_clips])
    video.audio = CompositeAudioClip(audio_clips)
    video.write_videofile(output_file, fps=args.fps, codec='libx264', audio_codec="aac")


def main():
    content = parse_markdown(args.markdown_file)

    p = Path(args.bg_path)
    bg_files = list(
        sorted([str(f.resolve()) for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()]))

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
