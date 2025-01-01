import numpy as np
from moviepy import Effect
from moviepy.Clip import Clip


class AlphaEffect(Effect):
    def __init__(self, background, time=0.2):
        self.background = background
        self.time = time

    def apply(self, clip: Clip):
        def filter(get_frame, t):
            frame = get_frame(t)

            if t < self.time or t > clip.duration - self.time:
                if t < self.time:
                    k = t / self.time
                else:
                    k = (clip.duration - t) / self.time

                x, y = map(int, clip.pos(t))
                bg = self.background.get_frame(clip.start + t)[y:y + clip.h, x:x + clip.w]
                return bg * (1 - k) + k * frame

            return frame

        return clip.transform(filter)
