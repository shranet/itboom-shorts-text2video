import cv2
from moviepy import Effect
from moviepy.Clip import Clip


class ImgEffect(Effect):
    TIME = 0.3

    def __init__(self, background):
        self.background = background

    def apply(self, clip: Clip) -> Clip:
        def fade(gf, t):
            if t < self.TIME or t > clip.duration - self.TIME:
                if t < self.TIME:
                    k = t / self.TIME
                else:
                    k = (clip.duration - t) / self.TIME

                x, y = map(int, clip.pos(t))

                bg = self.background.get_frame(clip.start + t)[y:y + clip.h,x:x + clip.w]
                im = gf(t)

                return bg * (1 - k) + k * im

            return gf(t)

        return clip.transform(fade)
