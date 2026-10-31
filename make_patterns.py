"""Regenerates the four theme wallpapers (bg-*.svg). Run: python make_patterns.py
placed with translate/rotate/scale; every doodle stays >=30px inside the 360px tile so it repeats cleanly."""
import math, os

OUT = os.path.dirname(os.path.abspath(__file__))
TILE = 360

def petals(n, d, fill_extra=""):
    return "".join(f'<path d="{d}" transform="rotate({round(i*360/n,1)})"{fill_extra}/>' for i in range(n))

SPARKLE = '<path d="M0-9Q0 0 9 0Q0 0 0 9Q0 0-9 0Q0 0 0-9Z"/>'
HEART = '<path d="M0 10C-20-4-10-18 0-8 10-18 20-4 0 10Z"/>'
STAR5 = '<path d="M0-14L4-4 14-4 6 3 9 13 0 7-9 13-6 3-14-4-4-4Z"/>'

THEMES = {
  "scifi": dict(color="#3d5af1", defs={
    "robot": '<rect x="-18" y="-12" width="36" height="30" rx="7"/><path d="M0-12V-23"/><circle cy="-27" r="3.5"/>'
             '<circle cx="-8" cy="1" r="3.5"/><circle cx="8" cy="1" r="3.5"/><path d="M-8 11H8M-4 8v6M0 8v6M4 8v6"/>'
             '<path d="M-18-2h-5v10h5M18-2h5v10h-5"/>',
    "bot": '<rect x="-10" y="-30" width="20" height="15" rx="4"/><path d="M0-30V-35"/><circle cy="-37" r="2"/>'
           '<circle cx="-4" cy="-23" r="1.8"/><circle cx="4" cy="-23" r="1.8"/>'
           '<rect x="-14" y="-11" width="28" height="22" rx="5"/><circle cy="0" r="4"/>'
           '<path d="M-14-5L-24 4M14-5L24 4M-6 11v12M6 11v12M-11 23h8M3 23h8"/>',
    "gear": '<circle r="7"/><circle r="13" stroke-width="5" stroke-dasharray="7 4.2"/><circle r="3"/>',
    "rocket": '<path d="M0-28C10-18 10 0 8 10H-8C-10 0-10-18 0-28Z"/><circle cy="-9" r="4"/>'
              '<path d="M-8 3L-18 16-8 11M8 3L18 16 8 11M-4 14Q0 26 4 14"/>',
    "planet": '<circle r="11"/><ellipse rx="22" ry="6" transform="rotate(-20)"/>',
    "sparkle": SPARKLE,
    "chip": '<rect x="-12" y="-12" width="24" height="24" rx="3"/><rect x="-5" y="-5" width="10" height="10"/>'
            '<path d="M-6-12v-6M0-12v-6M6-12v-6M-6 12v6M0 12v6M6 12v6M-12-6h-6M-12 0h-6M-12 6h-6M12-6h6M12 0h6M12 6h6"/>',
    "ufo": '<ellipse cy="4" rx="20" ry="7"/><path d="M-10 0Q0-16 10 0M-12 11l-4 8M0 12v8M12 11l4 8"/>',
    "bolt": '<path d="M4-16L-8 2H0L-4 16 10-4H2Z"/>',
    "circuit": '<path d="M-26 8H-10L-2-4H14L22 8H28"/><circle cx="-26" cy="8" r="3"/><circle cx="28" cy="8" r="3"/>',
  }, place=[("robot",62,62,-6,1),("gear",170,48,0,.7),("rocket",280,70,28,.85),("planet",50,170,0,.9),
            ("sparkle",120,130,0,1.2),("bot",212,150,8,.95),("chip",310,190,-10,.8),("ufo",130,238,-8,.85),
            ("bolt",58,296,12,.9),("circuit",200,300,0,.75),("sparkle",300,300,0,.9),("sparkle",256,232,0,.7)]),

  "anime": dict(color="#d63a76", defs={
    "sakura": petals(5, "M0 0C-6-8-6-16 0-20C6-16 6-8 0 0Z") + '<circle r="2"/>',
    "sparkle": SPARKLE,
    "cloud": '<path d="M-20 10a10 10 0 0 1 0-20 14 14 0 0 1 26-4 10 10 0 0 1 16 8 8 8 0 0 1-2 16Z"/>',
    "star": STAR5,
    "heart": HEART,
    "burst": '<path d="M0-18L4-8 14-14 10-4 20 0 10 4 14 14 4 8 0 18-4 8-14 14-10 4-20 0-10-4-14-14-4-8Z"/>'
             '<path d="M0-6V3"/><circle cy="8" r="1.2"/>',
    "bubble": '<path d="M-20-12H20a4 4 0 0 1 4 4V8a4 4 0 0 1-4 4H-6L-14 20V12H-20a4 4 0 0 1-4-4V-8a4 4 0 0 1 4-4Z"/>'
              '<circle cx="-8" cy="-2" r="1.3"/><circle cy="-2" r="1.3"/><circle cx="8" cy="-2" r="1.3"/>',
    "note": '<path d="M-6 14V-12L10-16V10"/><circle cx="-10" cy="14" r="5"/><circle cx="6" cy="10" r="5"/>',
    "onigiri": '<path d="M0-18L18 12Q20 18 14 18H-14Q-20 18-18 12Z"/><path d="M-8 6H8V18H-8Z"/>',
    "bowl": '<path d="M-20 0H20a20 20 0 0 1-40 0Z"/><path d="M-8 20h16M-6-4Q-10-12-4-16M4-4Q0-12 6-16"/>',
    "eye": '<path d="M-22 0Q0-20 22 0Q0 20-22 0Z"/><circle r="8"/><circle cx="3" cy="-3" r="2.4"/>',
  }, place=[("sakura",60,60,10,1.1),("cloud",170,55,0,.9),("sparkle",280,62,0,1.3),("bubble",52,168,-8,.85),
            ("star",150,138,12,.9),("eye",250,150,-6,.8),("heart",320,215,14,.9),("onigiri",120,236,-10,.85),
            ("note",56,300,10,.85),("bowl",200,296,0,.8),("burst",296,300,6,.8),("sakura",238,230,-15,.75)]),

  "cats": dict(color="#c2570c", defs={
    "face": '<path d="M-18-4L-20-22-6-14Q0-16 6-14L20-22 18-4Q22 4 16 12Q8 20 0 20T-16 12Q-22 4-18-4Z"/>'
            '<circle cx="-7" cy="0" r="2"/><circle cx="7" cy="0" r="2"/><path d="M-2 7H2L0 9ZM0 9Q-3 13-6 11M0 9Q3 13 6 11"/>'
            '<path d="M-12 8H-27M-12 11L-26 16M12 8H27M12 11L26 16"/>',
    "paw": '<ellipse cy="8" rx="11" ry="9"/><ellipse cx="-14" cy="-4" rx="4" ry="5.5" transform="rotate(-20 -14 -4)"/>'
           '<ellipse cx="-5" cy="-12" rx="4" ry="5.5"/><ellipse cx="5" cy="-12" rx="4" ry="5.5"/>'
           '<ellipse cx="14" cy="-4" rx="4" ry="5.5" transform="rotate(20 14 -4)"/>',
    "fish": '<path d="M-22 0Q-6-14 12 0Q-6 14-22 0Z"/><path d="M12 0L24-9V9Z"/><circle cx="-14" cy="-2" r="1.5"/>',
    "yarn": '<circle r="15"/><path d="M-12-8Q0-2 12-10M-15 0Q0 6 15-2M-12 8Q0 12 10 8M12 12Q24 22 14 28Q4 32-6 26"/>',
    "sitting": '<path d="M-10 22C-18 22-18 4-12-4-14-10-14-18-10-22L-6-16Q0-18 6-16L10-22C14-18 14-10 12-4 18 4 18 22 10 22Z"/>'
               '<path d="M10 20Q26 20 24 6"/>',
    "heart": HEART,
    "mouse": '<ellipse cy="4" rx="14" ry="9"/><circle cx="-8" cy="-6" r="5.5"/><circle cx="2" cy="-7" r="5.5"/>'
             '<path d="M14 6Q27 6 24-6"/><circle cx="-8" cy="3" r="1.3"/>',
    "loaf": '<path d="M-24 14C-26-4-12-14 4-10L8-18 12-10C20-8 24 2 22 14Z"/><path d="M8-1q2 2 4 0M14-1q2 2 4 0"/>',
    "sparkle": SPARKLE,
    "bell": '<circle cy="-4" r="11"/><path d="M-11 4H11M0-4V4"/><circle cy="9" r="2"/>',
  }, place=[("face",62,62,-8,1),("paw",170,50,14,.8),("fish",282,68,-20,.85),("yarn",52,170,0,.85),
            ("sparkle",122,130,0,1.1),("sitting",212,152,0,.95),("heart",312,196,12,.95),("mouse",128,240,-6,.9),
            ("loaf",58,298,0,.85),("face",202,300,10,.75),("paw",296,300,-14,.7),("bell",258,232,8,.8)]),

  "vintage": dict(color="#a8541f", defs={
    "camera": '<rect x="-22" y="-10" width="44" height="28" rx="4"/><path d="M-10-10l3-6h14l3 6"/>'
              '<circle cy="4" r="9"/><circle cy="4" r="4"/><rect x="-18" y="-6" width="6" height="4"/>',
    "polaroid": '<rect x="-16" y="-20" width="32" height="40" rx="2"/><rect x="-12" y="-16" width="24" height="24"/>'
                '<path d="M-12 8l7-9 6 6 4-4 7 7"/>',
    "sun": '<circle r="8"/><circle r="17" stroke-width="7" stroke-dasharray="2.5 7.2"/>',
    "cassette": '<rect x="-24" y="-14" width="48" height="28" rx="3"/><rect x="-16" y="-8" width="32" height="12" rx="2"/>'
                '<circle cx="-8" cy="-2" r="3.5"/><circle cx="8" cy="-2" r="3.5"/><path d="M-12 14l4-6h16l4 6"/>',
    "vinyl": '<circle r="20"/><circle r="12"/><circle r="4"/><path d="M-14-14A20 20 0 0 1 4-20" stroke-width="3"/>',
    "daisy": '<circle r="5"/>' + "".join(f'<ellipse cy="-12" rx="4" ry="8" transform="rotate({i*45})"/>' for i in range(8)),
    "note": '<path d="M-4 14V-14L10-10"/><circle cx="-8" cy="14" r="5"/>',
    "shades": '<path d="M-26-4H26"/><rect x="-24" y="-4" width="20" height="14" rx="6"/><rect x="4" y="-4" width="20" height="14" rx="6"/>',
    "strip": '<rect x="-26" y="-12" width="52" height="24" rx="2"/>'
             '<path d="M-20-8v2M-12-8v2M-4-8v2M4-8v2M12-8v2M20-8v2M-20 6v2M-12 6v2M-4 6v2M4 6v2M12 6v2M20 6v2" stroke-width="3"/>'
             '<rect x="-20" y="-3" width="12" height="7"/><rect x="-4" y="-3" width="12" height="7"/>',
    "peace": '<circle r="16"/><path d="M0-16V16M0 0L-11 11M0 0L11 11"/>',
    "sparkle": SPARKLE,
  }, place=[("camera",62,62,-8,1),("sun",170,52,0,.85),("polaroid",282,66,10,.95),("vinyl",52,170,0,.9),
            ("sparkle",122,132,0,1.1),("cassette",212,152,-6,.9),("daisy",312,196,0,.9),("shades",128,240,-6,.9),
            ("peace",58,298,0,.85),("strip",204,300,4,.9),("note",296,300,12,.9),("note",254,230,-12,.7)]),
}

for name, t in THEMES.items():
    defs = "".join(f'<g id="{k}">{v}</g>' for k, v in t["defs"].items())
    uses = "".join(f'<use href="#{k}" transform="translate({x} {y}) rotate({r}) scale({s})"/>' for k, x, y, r, s in t["place"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{TILE}" height="{TILE}" viewBox="0 0 {TILE} {TILE}">'
           f'<defs>{defs}</defs>'
           f'<g fill="none" stroke="{t["color"]}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" opacity=".36">{uses}</g></svg>\n')
    open(os.path.join(OUT, f"bg-{name}.svg"), "w", encoding="utf-8").write(svg)
    print(name, len(svg), "bytes,", len(t["place"]), "doodles")
