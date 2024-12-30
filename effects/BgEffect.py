from moviepy.Clip import Clip
from moviepy.Effect import Effect
import cv2


class BgEffect(Effect):
    MODE_IN = 0
    MODE_OUT = 1
    MODE_IN_OUT = 2
    MODE_OUT_IN = 3

    def __init__(self, width, height, duration, scale_factor=1, mode=MODE_IN, easing=None):
        self.width = width
        self.height = height
        self.duration = duration
        self.scale_factor = scale_factor
        self.mode = mode
        self.easing = easing

    def calc_factor(self, k):
        if self.easing is not None:
            k = self.easing(k)

        return 1 + self.scale_factor * k

    def blur(self, frame):
        return cv2.GaussianBlur(frame, (15, 15), cv2.BORDER_DEFAULT)

    def darken(self, frame):
        return cv2.convertScaleAbs(frame, alpha=0.75, beta=0)

    def resize(self, frame):
        height, width, _ = frame.shape
        original_aspect = width / height
        target_aspect = self.width / self.height

        if original_aspect > target_aspect:
            scale = self.height / height
            new_width = int(width * scale)
            new_height = self.height
        else:
            scale = self.width / width
            new_width = self.width
            new_height = int(height * scale)

        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

        start_x = (new_width - self.width) // 2
        start_y = (new_height - self.height) // 2

        return self.darken(self.blur(frame[start_y:start_y + self.height, start_x:start_x + self.width]))

    def zoom(self, get_frame, t):
        frame = get_frame(t)
        k = (t % self.duration) / self.duration
        if self.mode == self.MODE_IN:
            factor = self.calc_factor(1 - k)
        elif self.mode == self.MODE_OUT:
            factor = self.calc_factor(k)
        elif self.mode == self.MODE_IN_OUT:
            if k < 0.5:
                factor = self.calc_factor(1 - k / 0.5)
            else:
                factor = self.calc_factor((k - 0.5) / 0.5)
        else:
            if k < 0.5:
                factor = self.calc_factor(k / 0.5)
            else:
                factor = self.calc_factor((1 - k) / 0.5)

        new_width, new_height = int(factor * self.width), int(factor * self.height)
        if new_width % 2 != 0:
            new_width += 1

        if new_height % 2 != 0:
            new_height += 1

        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        center_x, center_y = new_width // 2, new_height // 2

        x1, x2 = center_x - self.width // 2, center_x + self.width // 2
        y1, y2 = center_y - self.height // 2, center_y + self.height // 2
        return frame[y1:y2, x1:x2]


    def apply(self, clip: Clip):
        return clip.image_transform(self.resize).transform(self.zoom)


