# itboom-shorts-text2video

Barcha ./assets/background dagi rasmlar pixels.com dan olingan va https://www.pexels.com/license/ litsensiya asosida boshqariladi.

# Dasturdan foydalanish
Dastlab https://github.com/mixn/carbon-now-cli dasturini o'rnatishi lozim. Keyin:

1. https://aisha.group/ saytidan ro'yxatdan o'tib, token olish kerak (https://space.aisha.group/api-keys)
2. .env.production fayl yaratib, `AISHA_TOKEN=...` o'zgaruvchisini yozish kerak
3. Terminalda `python3 -m venv .env` shaklida python muhit yaratish kerak
4. `. .env/bin/activate` qilib muhitni faollashtirish lozim
5. `pip install -r requirements.txt` qilib zarur kutubxonalarni o'rnatish kerak
6. Oxirqi qadam, `python main.py ./demo/raqamlar.md` shaklida dasturni ishga tushirish kerak
