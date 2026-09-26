"""
رسوم متحركة توضيحية (شخص عصوي) لتمرينات الأنموذج التعليمي.
كل تمرين يُرسم بقالب حركي (دالة من الطور p ∈ [0,1) إلى وضعية الجسم والأدوات).
التشغيل: python animations.py  ← يولّد videos/<رمز_التمرين>.gif
"""
import io
import math
import os

import numpy as np

# أطوال الأجزاء (م) للاعب ≈ 1.85 م
L = dict(thigh=0.45, shank=0.45, trunk=0.55, neck=0.12, head=0.11, uarm=0.31, farm=0.29, foot=0.21)
NEAR, FAR, FOCUS, PROP, GROUND = "#1f4e78", "#9db4cc", "#d62728", "#7f7f7f", "#555555"
W, H, DPI, FRAMES, FPS = 4.0, 3.0, 90, 36, 12


# ----------------------------------------------------------------------------
# أدوات
# ----------------------------------------------------------------------------
def ease(u):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, u)))


def kf(p, keys):
    """keys: [(t, dict), ...] مرتبة؛ استيفاء ناعم لكل مفتاح، مع الالتفاف."""
    keys = sorted(keys, key=lambda k: k[0])
    if p <= keys[0][0]:
        return dict(keys[0][1])
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t0 <= p <= t1:
            u = ease((p - t0) / (t1 - t0 if t1 > t0 else 1))
            a, b = dict(a), dict(b)
            if a.get("ya") is None and b.get("ya") is None:
                a["ya"] = b["ya"] = 0.0
                none = True
            else:
                none = False
                for d in (a, b):
                    if d.get("ya") is None:
                        d["ya"] = natural_dy(d)
            out = {k: a.get(k, 0) + (b.get(k, a.get(k, 0)) - a.get(k, 0)) * u for k in set(a) | set(b)}
            if none:
                out["ya"] = None
            return out
    return dict(keys[-1][1])


BASE = dict(x=0.0, t=0.0, lt=0.0, lk=0.0, lf=0.0, rt=0.0, rk=0.0, rf=0.0,
            ls=5.0, le=10.0, rs=-5.0, re=10.0, air=0.0, support=0.0, ya=None)


def pose(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


def V(a):  # متجه اتجاه من زاوية عن العمود للأسفل (موجب = للأمام)
    r = math.radians(a)
    return np.array([math.sin(r), -math.cos(r)])


def skeleton(P):
    """يعيد مواقع المفاصل (قبل تحديد الارتفاع)."""
    hip = np.array([P["x"], 0.0])
    tr = math.radians(P["t"])
    up = np.array([math.sin(tr), math.cos(tr)])
    neck = hip + up * L["trunk"]
    head = neck + up * (L["neck"] + L["head"])
    J = {"hip": hip, "neck": neck, "head": head}
    for s in ("l", "r"):
        knee = hip + V(P[s + "t"]) * L["thigh"]
        ank = knee + V(P[s + "t"] - P[s + "k"]) * L["shank"]
        f = math.radians(P[s + "f"])
        fd = np.array([math.cos(f), math.sin(f)])
        J[s + "knee"], J[s + "ank"] = knee, ank
        J[s + "toe"], J[s + "heel"] = ank + fd * L["foot"] * 0.8, ank - fd * L["foot"] * 0.25
        # الذراع: زاوية الكتف نسبةً إلى الجذع
        sa = P[s + "s"] + P["t"]
        elb = neck + V(sa) * L["uarm"]
        wr = elb + V(sa + P[s + "e"]) * L["farm"]
        J[s + "elb"], J[s + "wr"] = elb, wr
    return J


def natural_dy(P):
    J = skeleton(P)
    pts = np.array([v for k, v in J.items() if k != "head"] + [J["head"] - [0, L["head"]]])
    return P.get("support", 0) + P.get("air", 0) - pts[:, 1].min()


def place(P):
    J = skeleton(P)
    pts = np.array([v for k, v in J.items() if k != "head"] + [J["head"] - [0, L["head"]]])
    if P.get("ya") is not None:
        dy = P["ya"]
    else:
        dy = P["support"] + P["air"] - pts[:, 1].min()
    return {k: v + [0, dy] for k, v in J.items()}


# ----------------------------------------------------------------------------
# الرسم
# ----------------------------------------------------------------------------
class Scene:
    def __init__(self, xlim, ylim):
        self.xlim, self.ylim = xlim, ylim


def draw_person(ax, J, focus=()):
    def seg(a, b, c, w):
        ax.plot([J[a][0], J[b][0]], [J[a][1], J[b][1]], color=c, lw=w, solid_capstyle="round", zorder=3 if c == NEAR else 2)

    for s, c, w in (("l", FAR, 5), ("r", NEAR, 6)):
        seg("neck", s + "elb", c, w - 1); seg(s + "elb", s + "wr", c, w - 1)
        seg("hip", s + "knee", c, w); seg(s + "knee", s + "ank", c, w)
        seg(s + "heel", s + "toe", c, w - 2); seg(s + "ank", s + "heel", c, w - 2)
    seg("hip", "neck", NEAR, 7)
    from matplotlib.patches import Circle
    ax.add_patch(Circle(J["head"], L["head"], color=NEAR, zorder=4))
    for j in focus:
        ax.add_patch(Circle(J[j], 0.055, fill=False, ec=FOCUS, lw=2.2, zorder=5))


def arrow(ax, x, y, dx, dy, c=FOCUS):
    ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color=c, lw=2.2, mutation_scale=14), zorder=6)


def render(frame_fn, xlim, ylim, n=FRAMES):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    imgs = []
    for i in range(n):
        p = i / n
        hh = min(4.2, max(2.2, W * (ylim[1] - ylim[0]) / (xlim[1] - xlim[0])))
        fig = plt.figure(figsize=(W, hh), dpi=DPI)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal"); ax.axis("off")
        fig.patch.set_facecolor("white")
        frame_fn(ax, p)
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        imgs.append(Image.fromarray(buf.copy()).convert("P", palette=Image.ADAPTIVE, colors=64))
        plt.close(fig)
    out = io.BytesIO()
    imgs[0].save(out, format="GIF", save_all=True, append_images=imgs[1:], duration=int(1000 / FPS), loop=0, disposal=2)
    return out.getvalue()


def ground(ax, xlim, y=0.0, marks=None, scroll=0.0):
    ax.plot(xlim, [y, y], color=GROUND, lw=2, zorder=1)
    if marks:
        span = xlim[1] - xlim[0]
        for m in marks:
            xm = xlim[0] + ((m - scroll - xlim[0]) % span)
            ax.plot([xm, xm + 0.25], [y - 0.02, y - 0.02], color="#e39c32", lw=5, zorder=1)


def box(ax, x0, w, h):
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((x0, 0), w, h, fc="#d9c4a0", ec="#8a6d3b", lw=1.5, zorder=1))


def hurdle(ax, x, h):
    ax.plot([x, x], [0, h], color=PROP, lw=2.5)
    ax.plot([x - 0.02, x + 0.02], [h, h], color="#c00000", lw=5)


def mat(ax, x0, w, h=0.5):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x0, 0), w, h, boxstyle="round,pad=0.02", fc="#3b6fb6", ec="#274b7a", alpha=0.85, zorder=1))


def bar(ax, x, h, mat_x=None):
    if mat_x is not None:
        mat(ax, mat_x, 2.2)
    ax.plot([x, x], [0, h + 0.1], color=PROP, lw=2)
    ax.add_patch(__import__("matplotlib.patches", fromlist=["Circle"]).Circle((x, h), 0.035, color="#c00000", zorder=2))


def target(ax, x, h):
    ax.plot([x, x], [h + 0.35, h + 0.05], color=PROP, lw=1)
    ax.add_patch(__import__("matplotlib.patches", fromlist=["Circle"]).Circle((x, h), 0.07, color="#f2c14e", ec="#b8860b", zorder=2))


# ----------------------------------------------------------------------------
# دورات حركية جاهزة
# ----------------------------------------------------------------------------
def run_pose(p, amp=1.0, lean=8, air=0.06):
    """دورة ركض: الرجل القريبة (r) بطور p والبعيدة بطور p+0.5."""
    def leg(q):
        th = 38 * amp * math.sin(2 * math.pi * q)
        kn = 15 + 85 * amp * max(0.0, math.sin(2 * math.pi * (q - 0.35))) ** 1.2
        ft = -10 + 25 * math.sin(2 * math.pi * q)
        return th, kn, ft
    rt, rk, rf = leg(p)
    lt, lk, lf = leg(p + 0.5)
    arm = 45 * amp * math.sin(2 * math.pi * p)
    return pose(t=lean, rt=rt, rk=rk, rf=rf, lt=lt, lk=lk, lf=lf, rs=-arm, re=80, ls=arm, le=80,
                air=air * abs(math.sin(2 * math.pi * p)))


STAND = pose()
CROUCH = pose(t=30, lt=55, lk=95, rt=55, rk=95, lf=0, rf=0, ls=-40, rs=-40, le=20, re=20)


# ----------------------------------------------------------------------------
# القوالب
# ----------------------------------------------------------------------------
def T_run(amp=1.0, lean=8, focus=(), marks_speed=3.0, cue=None):
    xl, yl = (-1.6, 1.6), (-0.15, 2.25)

    def f(ax, p):
        ground(ax, xl, marks=[-1.2, 0.3, 1.1], scroll=p * marks_speed)
        J = place(run_pose(p, amp, lean))
        draw_person(ax, J, focus)
        if cue == "heel":
            q = (p % 1)
            if 0.1 < q < 0.35:
                arrow(ax, J["rank"][0] + 0.4, J["rank"][1] + 0.05, -0.3, 0)
    return f, xl, yl


def T_penultimate(steps_marks=True, end="up", target_h=None, focus=("rknee",), mat_end=False, bar_end=False, arms="double"):
    """اقتراب قصير: خطوة طويلة منخفضة ثم قصيرة سريعة ثم ارتقاء."""
    xl, yl = (-1.25, 2.55), (-0.15, 2.7)
    arm_up = 170 if arms == "double" else 60
    keys = [
        (0.00, pose(x=-0.8, t=5, rt=30, rk=10, rf=10, lt=-25, lk=40, lf=-20, rs=-30, ls=30, re=60, le=60)),
        (0.18, pose(x=-0.2, t=-2, rt=-10, rk=35, rf=0, lt=25, lk=20, lf=10, rs=20, ls=-40, re=40, le=40)),   # خطوة طويلة منخفضة
        (0.32, pose(x=0.35, t=-6, rt=35, rk=8, rf=15, lt=-20, lk=55, lf=-10, rs=-50, ls=-50, re=30, le=30)),  # وضع قدم الارتقاء
        (0.42, pose(x=0.55, t=0, rt=15, rk=25, rf=0, lt=40, lk=90, lf=-20, rs=-60, ls=-60, re=20, le=20)),    # ارتكاز
        (0.52, pose(x=0.7, t=0, rt=-5, rk=2, rf=-45, lt=85, lk=90, lf=-20, rs=arm_up, ls=arm_up, re=10, le=10, air=0.02)),
        (0.68, pose(x=0.95, t=-5, rt=-5, rk=10, rf=-40, lt=80, lk=90, lf=-20, rs=arm_up, ls=arm_up, re=10, le=10, air=0.55)),
        (0.85, pose(x=1.15, t=0, rt=5, rk=20, rf=-10, lt=30, lk=40, lf=0, rs=30, ls=30, re=20, le=20, air=0.1)),
        (1.00, pose(x=-0.8, t=5, rt=30, rk=10, rf=10, lt=-25, lk=40, lf=-20, rs=-30, ls=30, re=60, le=60)),
    ]

    def f(ax, p):
        ground(ax, xl)
        if steps_marks:
            for xm in (-0.2, 0.35):
                ax.plot([xm - 0.1, xm + 0.1], [-0.02, -0.02], color="#e39c32", lw=6)
        if target_h:
            target(ax, 0.95, target_h)
        if mat_end:
            mat(ax, 1.4, 1.6, 0.6)
        P = kf(p, keys)
        if mat_end and p > 0.68:
            P = kf(p, keys[:6] + [(0.85, pose(x=1.9, t=-60, rt=60, rk=60, lt=70, lk=70, rs=30, ls=30, air=0.62)),
                                   (1.0, pose(x=-0.8, t=5, rt=30, rk=10, rf=10, lt=-25, lk=40, lf=-20, rs=-30, ls=30, re=60, le=60))])
        J = place(P)
        draw_person(ax, J, focus)
        if 0.42 <= p <= 0.6:
            arrow(ax, J["hip"][0] + 0.35, J["hip"][1], 0, 0.45)
    return f, xl, yl


def T_bounds(single=False, straight=True, hurdles=False, hurdle_h=0.45, speed=2.2, focus=("rank",)):
    xl, yl = (-1.8, 1.8), (-0.15, 2.4)
    k = 8 if straight else 35

    def f(ax, p):
        ground(ax, xl, marks=None)
        if hurdles:
            for hk in range(-3, 4):
                hx = 1.2 * hk - 2.4 * ((p - 0.3) % 1)
                if xl[0] < hx < xl[1]:
                    hurdle(ax, hx, hurdle_h)
        q = p * 2 % 1
        contact = q < 0.25
        air = 0 if contact else (0.35 if not hurdles else hurdle_h + 0.05) * math.sin(math.pi * (q - 0.25) / 0.75)
        if single:
            P = pose(t=8, rt=10 - 30 * q if contact else -15 + 30 * q, rk=k + (20 if contact else 0), rf=-20 if not contact else 0,
                     lt=60, lk=95, lf=-20, rs=-40 + 80 * q, ls=40 - 80 * q, re=70, le=70, air=air)
        else:
            alt = int(p * 2) % 2
            a, b = ("r", "l") if alt == 0 else ("l", "r")
            P = pose(t=10, air=air, rs=-50 if alt == 0 else 50, ls=50 if alt == 0 else -50, re=60, le=60)
            P[a + "t"], P[a + "k"], P[a + "f"] = (5 - 30 * q, k, 0) if contact else (-25, k + 10, -30)
            P[b + "t"], P[b + "k"], P[b + "f"] = 70, 90, -20
        draw_person(ax, place(P), focus)
    return f, xl, yl


def T_double_hops(hurdle_h=0.45, speed=2.0, pogo=False, focus=("rank",)):
    xl, yl = (-1.6, 1.6), (-0.15, 2.4)

    def f(ax, p):
        ground(ax, xl)
        if not pogo:
            for hk in range(-3, 4):
                hx = 1.2 * hk - 2.4 * ((p - 0.3) % 1)
                if xl[0] < hx < xl[1]:
                    hurdle(ax, hx, hurdle_h)
        q = p * (3 if pogo else 2) % 1
        contact = q < 0.2
        hmax = 0.18 if pogo else hurdle_h + 0.08
        air = 0 if contact else hmax * math.sin(math.pi * (q - 0.2) / 0.8)
        kn = 10 if pogo else (35 if contact else 70 * math.sin(math.pi * (q - 0.2) / 0.8) + 10)
        th = kn * 0.6
        arms = 40 if pogo else (-50 if contact else 120)
        P = pose(t=5 if pogo else 15, rt=th, rk=kn, lt=th + 3, lk=kn, rf=0 if contact else -35, lf=0 if contact else -35,
                 rs=arms, ls=arms, re=20, le=20, air=air)
        draw_person(ax, place(P), focus)
        if pogo and contact:
            arrow(ax, 0.45, 0.35, 0, 0.35)
    return f, xl, yl


def T_drop(single=False, rebound=True, box_h=0.35, focus=("rknee",)):
    xl, yl = (-1.6, 1.6), (-0.15, 2.5)
    bx = -1.3

    def f(ax, p):
        ground(ax, xl)
        box(ax, bx, 0.6, box_h)
        on_box = pose(x=bx + 0.3, support=box_h, t=5, rt=0, rk=5, lt=0 if not single else 40, lk=5 if not single else 80,
                      ls=-10, rs=-10)
        step = pose(x=bx + 0.55, support=box_h, t=5, rt=25, rk=5, rf=10, lt=0, lk=5, ls=-30, rs=-30, air=0.02)
        land = pose(x=0.0, t=20, rt=35, rk=50, rf=0, lt=(35 if not single else 60), lk=(50 if not single else 90), lf=0,
                    rs=-40, ls=-40, re=20, le=20)
        keys = [(0.0, on_box), (0.2, on_box), (0.32, step), (0.45, land)]
        if rebound:
            keys += [(0.52, pose(x=0.05, t=0, rt=0, rk=0, lt=0, lk=0, rf=-40, lf=-40, rs=170, ls=170, air=0.05)),
                     (0.66, pose(x=0.1, t=0, rt=5, rk=10, lt=5, lk=10, rf=-30, lf=-30, rs=160, ls=160, air=0.45)),
                     (0.8, pose(x=0.15, t=15, rt=30, rk=40, lt=30, lk=40, rs=-20, ls=-20)), (1.0, on_box)]
        else:
            keys += [(0.8, land), (1.0, on_box)]
        P = kf(p, keys)
        J = place(P)
        draw_person(ax, J, focus)
        if 0.42 < p < 0.52:
            arrow(ax, J["rknee"][0] + 0.35, J["rknee"][1] + 0.1, 0, 0.3 if rebound else 0.0001)
    return f, xl, yl


def T_split_squat(bulgarian=True, focus=("rknee",)):
    xl, yl = (-1.4, 1.4), (-0.15, 2.3)

    def f(ax, p):
        ground(ax, xl)
        d = 0.5 - 0.5 * math.cos(2 * math.pi * p)
        if bulgarian:
            P = pose(t=8 + 10 * d, rt=20 + 55 * d, rk=10 + 90 * d, rf=0, lt=-40 - 20 * d, lk=70 + 40 * d, lf=-80,
                     rs=-10, ls=-10, re=90, le=90, x=0.1)
        else:
            P = pose(t=15 + 25 * d, rt=15 + 60 * d, rk=10 + 95 * d, rf=0, lt=30 + 40 * d, lk=20 + 20 * d, lf=10,
                     rs=40 + 30 * d, ls=40 + 30 * d, re=0, le=0)
        J = place(P)
        if bulgarian:
            from matplotlib.patches import Rectangle
            top = min(J["ltoe"][1], J["lank"][1]) - 0.02
            ax.add_patch(Rectangle((J["ltoe"][0] - 0.35, 0), 0.5, max(0.2, top), fc="#d9c4a0", ec="#8a6d3b", zorder=1))
        draw_person(ax, J, focus)
    return f, xl, yl


def T_cmj(target_h=None, single=False, focus=("rwr",)):
    xl, yl = (-1.4, 1.4), (-0.15, 3.1)
    keys = [(0.0, STAND), (0.15, STAND),
            (0.3, pose(t=30, rt=55, rk=90, lt=55, lk=90, rs=-60, ls=-60, re=10, le=10)),
            (0.42, pose(t=0, rt=0, rk=0, lt=0 if not single else 70, lk=0 if not single else 90, rf=-45, lf=-45, rs=175, ls=175, re=5, le=5, air=0.03)),
            (0.55, pose(t=0, rt=0, rk=5, lt=0 if not single else 70, lk=5 if not single else 90, rf=-40, lf=-40, rs=178, ls=178, re=5, le=5, air=0.5)),
            (0.7, pose(t=20, rt=35, rk=50, lt=35, lk=50, rs=-20, ls=-20)), (0.85, STAND), (1.0, STAND)]

    def f(ax, p):
        ground(ax, xl)
        if target_h:
            target(ax, 0.2, target_h)
        J = place(kf(p, keys))
        draw_person(ax, J, focus)
        if 0.3 < p < 0.45:
            arrow(ax, J["rwr"][0] + 0.25, J["rwr"][1], 0, 0.35)
    return f, xl, yl


def T_wall_knee(band=False, focus=("lknee",)):
    xl, yl = (-1.2, 1.6), (-0.15, 2.3)

    def f(ax, p):
        ground(ax, xl)
        if not band:
            ax.plot([1.05, 1.05], [0, 2.2], color=PROP, lw=4)
        d = ease((math.sin(2 * math.pi * p) + 1) / 2)
        if band:
            P = pose(t=0, rt=0, rk=0, lt=-5 + 95 * d, lk=5 + 85 * d, lf=-10, rs=0, ls=0)
        else:
            P = pose(x=0.1, t=35, rt=-30, rk=5, rf=-30, lt=-30 + 120 * d, lk=10 + 80 * d, lf=-25, rs=55, ls=55, re=5, le=5)
        J = place(P)
        if band:
            ax.plot([J["lank"][0], -1.0], [J["lank"][1], 0.15], color="#2ca02c", lw=2, ls="--")
            ax.plot([-1.0, -1.0], [0, 0.3], color=PROP, lw=4)
        draw_person(ax, J, focus)
        if d > 0.8:
            arrow(ax, J["lknee"][0] + 0.25, J["lknee"][1] - 0.2, 0, 0.3)
    return f, xl, yl


def T_bridge(focus=("hip",)):
    xl, yl = (-1.6, 1.4), (-0.15, 1.5)
    lying = pose(t=-90, rt=135, rk=115, lt=135, lk=115, rf=0, lf=0, rs=180, ls=180, re=0, le=0)
    prep = pose(t=-90, rt=135, rk=115, lt=135, lk=115, rf=0, lf=0, rs=0, ls=0, re=-150, le=-150)
    wheel = pose(t=-150, rt=35, rk=45, lt=35, lk=45, rf=0, lf=0, rs=150, ls=150, re=0, le=0)

    def f(ax, p):
        ground(ax, xl)
        P = kf(p, [(0.0, lying), (0.15, prep), (0.4, wheel), (0.75, wheel), (0.9, prep), (1.0, lying)])
        J = place(P)
        draw_person(ax, J, focus)
        if 0.3 < p < 0.75:
            arrow(ax, J["hip"][0], J["hip"][1] + 0.1, 0, 0.3)
    return f, xl, yl


def T_backover(from_box=False, legs_kick=True, focus=("hip",)):
    xl, yl = (-2.4, 1.6), (-0.15, 2.4)
    bar_x, bar_h = -0.35, (1.0 if not from_box else 1.15)
    sup = 0.3 if from_box else 0.0

    def f(ax, p):
        ground(ax, xl)
        mat(ax, -2.2, 1.9, 0.5)
        if from_box:
            box(ax, 0.2, 0.9, sup)
        from matplotlib.patches import Circle
        ax.plot([bar_x, bar_x], [0.5, bar_h + 0.1], color=PROP, lw=1.5)
        ax.add_patch(Circle((bar_x, bar_h), 0.03, color="#c00000", zorder=2))
        stand = pose(x=0.55, support=sup, t=0, rs=0, ls=0)
        dip = pose(x=0.55, support=sup, t=20, rt=45, rk=80, lt=45, lk=80, rs=-40, ls=-40, re=10, le=10)
        push = pose(x=0.45, support=sup, t=-15, rt=-5, rk=5, lt=-5, lk=5, rf=-40, lf=-40, rs=-160, ls=-160, air=0.05)
        arch = pose(x=bar_x, t=-150, rt=40, rk=50, lt=40, lk=50, rs=-190, ls=-190, ya=bar_h + 0.05 - 0.0)
        kick = pose(x=bar_x - 0.5, t=-100, rt=150 if legs_kick else 60, rk=5 if legs_kick else 60,
                    lt=150 if legs_kick else 60, lk=5 if legs_kick else 60, rs=-170, ls=-170)
        kick["ya"] = None
        kick["support"] = 0.5
        kick["air"] = 0.25
        land = pose(x=bar_x - 1.0, t=-90, rt=150, rk=30, lt=150, lk=30, rs=-150, ls=-150, support=0.5)
        P = kf(p, [(0.0, stand), (0.15, dip), (0.28, push), (0.45, arch), (0.62, kick), (0.8, land), (1.0, stand)])
        if P.get("ya") is not None and P["t"] < -120:
            # الورك فوق العارضة: نثبت ارتفاع الورك لا أدنى نقطة
            J0 = skeleton(P)
            P["ya"] = bar_h + 0.08 - J0["hip"][1]
        J = place(P)
        draw_person(ax, J, (("rknee", "lknee") if legs_kick and 0.5 < p < 0.7 else focus))
        if 0.33 < p < 0.5:
            arrow(ax, J["hip"][0] + 0.1, J["hip"][1] + 0.1, 0, 0.3)
    return f, xl, yl


def T_leg_kick(focus=("rank",)):
    xl, yl = (-1.4, 1.4), (-0.15, 1.8)
    a = pose(t=-90, rt=100, rk=15, lt=100, lk=15, rf=0, lf=0, rs=180, ls=180, re=0, le=0)
    b = pose(t=-90, rt=175, rk=0, lt=175, lk=0, rf=90, lf=90, rs=180, ls=180, re=0, le=0)

    def f(ax, p):
        ground(ax, xl)
        P = kf(p, [(0.0, a), (0.25, b), (0.35, b), (0.7, a), (1.0, a)])
        J = place(P)
        draw_person(ax, J, focus)
        if 0.05 < p < 0.25:
            arrow(ax, J["rank"][0] + 0.15, J["rank"][1], 0, 0.3)
    return f, xl, yl


def T_scissors(curve=False, focus=("neck",)):
    xl, yl = (-1.4, 2.4), (-0.15, 2.6)

    def f(ax, p):
        ground(ax, xl)
        mat(ax, 1.3, 1.1, 0.5)
        ax.plot([1.2, 1.2], [0, 1.2], color=PROP, lw=2)
        from matplotlib.patches import Circle
        ax.add_patch(Circle((1.2, 1.1), 0.03, color="#c00000"))
        keys = [(0.0, pose(x=-1.0, t=5, rt=30, rk=10, lt=-25, lk=40, rs=-30, ls=30, re=60, le=60)),
                (0.3, pose(x=0.1, t=-5, rt=35, rk=8, rf=15, lt=-20, lk=60, rs=-60, ls=-60, re=20, le=20)),
                (0.45, pose(x=0.6, t=0, rt=-10, rk=5, rf=-40, lt=85, lk=15, lf=0, rs=120, ls=120, re=10, le=10, air=0.3)),
                (0.6, pose(x=1.15, t=0, rt=80, rk=10, rf=0, lt=-10, lk=10, lf=-30, rs=110, ls=110, re=10, le=10, air=0.55)),
                (0.8, pose(x=1.7, t=0, rt=20, rk=20, lt=20, lk=20, rs=20, ls=20, support=0.5)),
                (1.0, pose(x=-1.0, t=5, rt=30, rk=10, lt=-25, lk=40, rs=-30, ls=30, re=60, le=60))]
        J = place(kf(p, keys))
        draw_person(ax, J, focus)
        if 0.4 < p < 0.62:
            arrow(ax, J["head"][0] - 0.3, J["head"][1] - 0.2, 0, 0.35)
    return f, xl, yl


def T_fosbury(focus=("hip",)):
    xl, yl = (-1.9, 3.0), (-0.15, 2.6)
    bar_x, bar_h = 1.35, 1.65

    def f(ax, p):
        ground(ax, xl)
        mat(ax, bar_x - 0.1, 1.6, 0.55)
        from matplotlib.patches import Circle
        ax.plot([bar_x, bar_x], [0, bar_h + 0.15], color=PROP, lw=2)
        ax.add_patch(Circle((bar_x, bar_h), 0.035, color="#c00000", zorder=2))
        run = pose(x=-1.5, t=5, rt=30, rk=10, lt=-25, lk=40, rs=-30, ls=30, re=60, le=60)
        plant = pose(x=0.3, t=-8, rt=35, rk=8, rf=15, lt=-20, lk=60, rs=-60, ls=-60, re=20, le=20)
        off = pose(x=0.55, t=0, rt=-5, rk=3, rf=-45, lt=85, lk=90, rs=170, ls=170, re=10, le=10, air=0.05)
        rise = pose(x=0.95, t=45, rt=-10, rk=20, lt=10, lk=60, rs=150, ls=150, re=10, le=10)
        top = pose(x=bar_x, t=112, rt=-75, rk=-75, lt=-72, lk=-80, rs=205, ls=205, re=0, le=0)
        kick = pose(x=bar_x + 0.45, t=100, rt=-175, rk=0, lt=-170, lk=0, rs=190, ls=190)
        land = pose(x=bar_x + 0.95, t=92, rt=-150, rk=25, lt=-150, lk=25, rs=150, ls=150, support=0.55)
        P = kf(p, [(0.0, run), (0.25, plant), (0.35, off), (0.47, rise), (0.6, top), (0.72, kick), (0.86, land), (1.0, run)])
        J0 = skeleton(P)
        if 0.4 < p < 0.8:
            hip_target = {0.47: 1.35, 0.6: bar_h + 0.08, 0.72: 1.35}
            ts = sorted(hip_target)
            hy = np.interp(p, ts, [hip_target[t] for t in ts])
            P["ya"] = hy - J0["hip"][1]
        J = place(P)
        draw_person(ax, J, focus)
    return f, xl, yl


def T_squat_bar(focus=("rknee",)):
    xl, yl = (-1.4, 1.4), (-0.15, 2.3)

    def f(ax, p):
        ground(ax, xl)
        d = 0.5 - 0.5 * math.cos(2 * math.pi * p)
        P = pose(t=10 + 30 * d, rt=5 + 80 * d, rk=5 + 90 * d, lt=5 + 80 * d, lk=5 + 90 * d, rs=-160, ls=-160, re=-140, le=-140)
        J = place(P)
        ax.plot([J["neck"][0] - 0.05, J["neck"][0] - 0.05], [J["neck"][1] - 0.02, J["neck"][1] - 0.02], "o", ms=14, color="#444")
        ax.plot([J["neck"][0] - 0.45, J["neck"][0] + 0.35], [J["neck"][1] - 0.02] * 2, color="#444", lw=3)
        draw_person(ax, J, focus)
    return f, xl, yl


def T_stretch(focus=()):
    xl, yl = (-1.4, 1.4), (-0.15, 2.0)
    a = pose(t=0, rt=35, rk=0, rf=60, lt=-5, lk=15, rs=0, ls=0)
    b = pose(t=55, rt=35, rk=0, rf=60, lt=-5, lk=20, rs=40, ls=40, re=0, le=0)

    def f(ax, p):
        ground(ax, xl)
        J = place(kf(p, [(0, a), (0.3, b), (0.8, b), (1.0, a)]))
        draw_person(ax, J, focus)
    return f, xl, yl


def T_frontal_band(focus=()):
    """منظر أمامي: المشي الجانبي بمطاط حول الركبتين."""
    xl, yl = (-1.4, 1.4), (-0.15, 2.3)

    def f(ax, p):
        ground(ax, xl)
        q = p * 2 % 1
        base_x = -0.6 + 1.2 * p
        spread = 0.22 + 0.18 * math.sin(math.pi * q)
        hipy, kneey = 0.92, 0.5
        lx, rx = base_x - spread / 2 + (0.0 if q < 0.5 else 0.05), base_x + spread / 2
        hl, hr = np.array([base_x - 0.1, hipy]), np.array([base_x + 0.1, hipy])
        kl, kr = np.array([lx + 0.02, kneey]), np.array([rx - 0.02, kneey])
        al, ar = np.array([lx, 0.05]), np.array([rx, 0.05 + 0.08 * math.sin(math.pi * q)])
        sh = np.array([base_x, hipy + 0.55])
        for a_, b_ in ((hl, kl), (kl, al), (hr, kr), (kr, ar), (hl, hr)):
            ax.plot([a_[0], b_[0]], [a_[1], b_[1]], color=NEAR, lw=6, solid_capstyle="round")
        ax.plot([base_x, base_x], [hipy, sh[1]], color=NEAR, lw=7)
        ax.plot([sh[0] - 0.2, sh[0] + 0.2], [sh[1], sh[1]], color=NEAR, lw=6)
        for sx in (-1, 1):
            ax.plot([sh[0] + 0.2 * sx, sh[0] + 0.25 * sx, sh[0] + 0.15 * sx], [sh[1], sh[1] - 0.3, sh[1] - 0.5], color=NEAR, lw=5)
        from matplotlib.patches import Circle
        ax.add_patch(Circle((sh[0], sh[1] + 0.2), 0.11, color=NEAR))
        ax.plot([kl[0], kr[0]], [kl[1] + 0.03, kr[1] + 0.03], color="#2ca02c", lw=3)
        for k in (kl, kr):
            ax.add_patch(Circle(k, 0.05, fill=False, ec=FOCUS, lw=2))
        arrow(ax, base_x + 0.35, 1.8, 0.35, 0)
    return f, xl, yl


# ----------------------------------------------------------------------------
# منظر علوي (مسار الاقتراب)
# ----------------------------------------------------------------------------
def T_top(kind="j", radius=7.0, marks=True):
    """kind: j = اقتراب على شكل حرف J نحو العارضة، circle = ركض على دائرة."""
    from matplotlib.patches import Circle, Rectangle

    if kind == "circle":
        xl, yl = (-radius - 1.5, radius + 1.5), (-radius - 1.5, radius + 1.5)

        def f(ax, p):
            ax.add_patch(Circle((0, 0), radius, fill=False, ls="--", ec=PROP, lw=1.5))
            ax.plot(0, 0, "+", color=PROP, ms=12)
            th = 2 * math.pi * p
            pos = np.array([radius * math.cos(th), radius * math.sin(th)])
            for k in range(1, 7):
                t2 = th - k * 0.18
                fp = np.array([radius * math.cos(t2), radius * math.sin(t2)]) * (1 + 0.012 * (-1) ** k)
                ax.plot(*fp, "o", ms=4, color=FAR)
            ax.add_patch(Circle(pos, 0.45, color=NEAR, zorder=3))
            arrow(ax, pos[0], pos[1], -pos[0] * 0.18, -pos[1] * 0.18)     # الميل نحو المركز
        return f, xl, yl

    # مسار J (منظر علوي): ركض مستقيم نحو اليمين ثم قوس ينعطف نحو العارضة (عمودية على x = 0)
    R = radius
    straight = [np.array([-13.0 + i * 1.75, -5.0]) for i in range(4)]
    c = np.array([straight[-1][0] + 0.0, -5.0 + R])
    ang = np.linspace(0, 0.87, 6)[1:]
    arc = [c + R * np.array([math.sin(a), -math.cos(a)]) for a in ang]
    pts = np.array(straight + arc)
    shift = -0.7 - pts[-1][0]          # نقطة الارتقاء على بعد 0.7 م من العارضة
    pts[:, 0] += shift
    c = c + [shift, 0]
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    to = pts[-1]
    xl, yl = (pts[0][0] - 1.0, 4.2), (-6.3, 3.0)

    def f(ax, p):
        ax.add_patch(Rectangle((0.15, to[1] - 0.6), 3.0, 4.6, fc="#3b6fb6", alpha=0.35, ec="#274b7a"))
        ax.plot([0, 0], [to[1] - 0.6, to[1] + 3.4], color="#c00000", lw=3)
        for yy in (to[1] - 0.6, to[1] + 3.4):
            ax.plot(0, yy, "s", color=PROP, ms=7)
        ax.plot(pts[:, 0], pts[:, 1], ls=":", color=PROP, lw=1.3)
        if marks:
            for m in (pts[0], pts[3], pts[-1]):
                ax.plot(*m, "s", color="#e39c32", ms=8, zorder=2)
        s_ = min(p * 1.2 * d[-1], d[-1])
        i = max(1, min(int(np.searchsorted(d, s_)), len(pts) - 1))
        u = (s_ - d[i - 1]) / max(1e-9, d[i] - d[i - 1])
        pos = pts[i - 1] + u * (pts[i] - pts[i - 1])
        for k in range(i):
            ax.plot(*pts[k], "o", ms=5, color=FAR)
        ax.add_patch(Circle(pos, 0.35, color=NEAR, zorder=3))
        if i > 3:
            v = (c - pos) / np.linalg.norm(c - pos)
            arrow(ax, pos[0], pos[1], v[0] * 1.2, v[1] * 1.2)
        if s_ >= d[-1]:
            ax.add_patch(Circle(to, 0.6, fill=False, ec=FOCUS, lw=2.5))
    return f, xl, yl


# ----------------------------------------------------------------------------
# ربط التمرينات بالقوالب
# ----------------------------------------------------------------------------
TEMPLATES = {
    "X011": lambda: T_top("circle", 7.0), "X012": lambda: T_top("j"), "X013": lambda: T_run(1.0, 10, ("rknee",), 3.5),
    "X021": lambda: T_penultimate(focus=("hip",)), "X022": lambda: T_penultimate(focus=("hip",)),
    "X023": lambda: T_bounds(single=True, hurdles=True, hurdle_h=0.35), "X031": lambda: T_run(0.55, 3, ("rheel",), 1.2, cue="heel"),
    "X032": lambda: T_bounds(single=False, straight=True), "X033": lambda: T_penultimate(focus=("rknee", "rank")),
    "X041": lambda: T_drop(single=True, rebound=False), "X042": lambda: T_split_squat(True), "X043": lambda: T_drop(False, True),
    "X051": lambda: T_top("circle", 7.0), "X052": lambda: T_penultimate(focus=("neck",)), "X053": lambda: T_top("j"),
    "X061": lambda: T_cmj(target_h=2.75, single=True, focus=("head",)), "X062": lambda: T_scissors(),
    "X063": lambda: T_penultimate(mat_end=True, focus=("hip",)), "X071": lambda: T_wall_knee(False),
    "X072": lambda: T_penultimate(target_h=1.55, focus=("lknee",)), "X073": lambda: T_wall_knee(True),
    "X081": lambda: T_cmj(), "X082": lambda: T_penultimate(focus=("rwr", "lwr")),
    "X091": lambda: T_bounds(single=True, hurdles=True, hurdle_h=0.45), "X092": lambda: T_penultimate(target_h=2.7, focus=("hip",)),
    "X093": lambda: T_double_hops(0.45), "X101": lambda: T_double_hops(pogo=True), "X102": lambda: T_bounds(single=True, straight=False),
    "X103": lambda: T_drop(False, True), "X111": lambda: T_bridge(), "X112": lambda: T_backover(False, False),
    "X113": lambda: T_backover(True, False), "X121": lambda: T_backover(False, True), "X122": lambda: T_leg_kick(),
    "X131": lambda: T_top("j"), "X132": lambda: T_penultimate(focus=("rank",)), "X151": lambda: T_top("circle", 5.0),
    "X152": lambda: T_top("circle", 5.0), "X153": lambda: T_penultimate(mat_end=True, focus=("neck",)),
    "X161": lambda: T_penultimate(target_h=2.7, focus=("neck",)), "X162": lambda: T_scissors(True),
    "X171": lambda: T_split_squat(False), "X172": lambda: T_frontal_band(), "X173": lambda: T_drop(single=True, rebound=False),
    "X181": lambda: T_top("j"), "X182": lambda: T_top("j"), "X141": lambda: T_top("j"), "X142": lambda: T_top("j", marks=False),
    "G001": lambda: T_run(0.6, 4, (), 1.5), "G002": lambda: T_cmj(), "G003": lambda: T_squat_bar(),
    "G004": lambda: T_fosbury(), "G005": lambda: T_stretch(),
}

VIEW = {c: ("علوي" if "T_top" in TEMPLATES[c].__code__.co_names else "أمامي" if c == "X172" else "جانبي") for c in TEMPLATES}


def make(code):
    f, xl, yl = TEMPLATES[code]()
    return render(f, xl, yl)


if __name__ == "__main__":
    import sys
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos")
    os.makedirs(out, exist_ok=True)
    codes = sys.argv[1:] or list(TEMPLATES)
    for c in codes:
        with open(os.path.join(out, f"{c}.gif"), "wb") as fh:
            fh.write(make(c))
        print("ok", c)
