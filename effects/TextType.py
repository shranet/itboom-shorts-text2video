from moviepy import Effect, TextClip
from moviepy.Clip import Clip


class TextType(Effect):
    def apply(self, clip):
        if not isinstance(clip, TextClip):
            raise ValueError("Clip must be of type TextClip.")


        return clip
